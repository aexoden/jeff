# SPDX-FileCopyrightText: 2015-present Jason Lynch <jason@aexoden.com>
#
# SPDX-License-Identifier: MIT
"""Qt6-based GUI for JEFF, a music library and rating system."""

from __future__ import annotations

import sys

from collections import deque
from pathlib import Path

import gi
import xdg.BaseDirectory

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from jeff.__version__ import __version__
from jeff.library import Library, Track

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

MINUTES_PER_HOUR = 60


def format_time(nanoseconds: int) -> str:
    """Format time from nanoseconds to MM:SS.

    Args:
        nanoseconds (int): Time in nanoseconds.

    Returns:
        str: Formatted time string in MM:SS or HH:MM:SS format.

    """
    if nanoseconds <= 0:
        return "0:00"

    seconds = int(nanoseconds / 1_000_000_000)
    minutes = seconds // 60
    seconds %= 60

    if minutes >= MINUTES_PER_HOUR:
        hours = minutes // 60
        minutes %= 60
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"


class GStreamerPlayer:
    """GStreamer player wrapper for Qt6 integration."""

    def __init__(self, parent: MainWindow) -> None:
        """Initialize the GStreamer player."""
        self._parent = parent
        Gst.init(None)
        self._init_player()

        bus = self._player.get_bus()

        if bus:
            bus.add_signal_watch()
            bus.connect("message::eos", self._on_eos)

    def _init_player(self) -> None:
        player = Gst.ElementFactory.make("playbin", "player")

        if not player:
            msg = "Failed to create GStreamer playbin element"
            raise RuntimeError(msg)

        self._player = player

    def _on_eos(self, _bus: Gst.Bus, _message: Gst.Message) -> None:
        self._parent.on_track_finished()

    def set_uri(self, uri: str) -> None:
        """Set the URI of the media to play."""
        self._player.set_property("uri", uri)

    def play(self) -> None:
        """Start playback."""
        self._player.set_state(Gst.State.PLAYING)

    def pause(self) -> None:
        """Pause playback."""
        self._player.set_state(Gst.State.PAUSED)

    def stop(self) -> None:
        """Stop playback."""
        self._player.set_state(Gst.State.READY)

    def get_state(self) -> Gst.State:
        """Get the current state of the player.

        Returns:
            Gst.State: The current state of the player.

        """
        return self._player.get_state(Gst.CLOCK_TIME_NONE)[1]

    def get_position(self) -> int:
        """Get the current playback position in nanoseconds.

        Returns:
            int: The current playback position in nanoseconds, or 0 if not available.

        """
        success, position = self._player.query_position(Gst.Format.TIME)
        return position if success else 0

    def get_duration(self) -> int:
        """Get the total duration of the media in nanoseconds.

        Returns:
            int: The total duration of the media in nanoseconds, or 0 if not available.

        """
        success, duration = self._player.query_duration(Gst.Format.TIME)
        return duration if success else 0

    def seek(self, position: int) -> None:
        """Seek to a specific position in the media."""
        self._player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, position)


class ComparisonWidget(QWidget):
    """Widget for displaying a single track in comparison."""

    track_selected = Signal(object)
    preview_requested = Signal(object, bool)

    def __init__(self, parent: QSplitter | None = None) -> None:
        """Initialize the comparison widget."""
        super().__init__(parent)
        self._track = None
        self._is_previewing = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface for the comparison widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Create a frame for the track information
        self._frame = QFrame()
        self._frame.setFrameStyle(QFrame.Shape.Box)
        self._frame.setStyleSheet("""
            QFrame {
                border: 2px solid #ccc;
                border-radius: 8px;
                background-color: #f9f9f9;
                padding: 10px;
            }

            QFrame:hover {
                border-color: #007acc;
                background-color: #f0f8ff;
            }
        """)
        frame_layout = QVBoxLayout(self._frame)

        # Track information labels
        self._title_label = QLabel("Select a track...")
        self._title_label.setFont(QFont("", 12, QFont.Weight.Bold))
        self._title_label.setWordWrap(True)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #666;")
        self._info_label.setWordWrap(True)

        self._rating_label = QLabel("")
        self._rating_label.setStyleSheet("color: #0066cc; font-weight: bold;")

        frame_layout.addWidget(self._title_label)
        frame_layout.addWidget(self._info_label)
        frame_layout.addWidget(self._rating_label)
        frame_layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()

        self._preview_btn = QPushButton("🎧 Preview")
        self._preview_btn.setCheckable(True)
        self._preview_btn.clicked.connect(self._toggle_preview)
        self._preview_btn.setEnabled(False)

        self._choose_btn = QPushButton("⭐ Choose This")
        self._choose_btn.clicked.connect(self._choose_track)
        self._choose_btn.setEnabled(False)
        self._choose_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        button_layout.addWidget(self._preview_btn)
        button_layout.addWidget(self._choose_btn)

        layout.addWidget(self._frame)
        layout.addLayout(button_layout)

    def set_track(self, track: Track | None) -> None:
        """Set the track to display."""
        self._track = track

        if track:
            self._title_label.setText(track.title)

            # Build information string
            info_parts: list[str] = []

            tags = track.tags

            if tags:
                if tags.artist:
                    info_parts.append(f"Artist: {tags.artist}")
                if tags.album:
                    info_parts.append(f"Album: {tags.album}")

            self._info_label.setText("\n".join(info_parts))
            self._rating_label.setText(f"Rating: {track.rating:.1f} | Comparisons: {track.comparisons}")

            self._preview_btn.setEnabled(True)
            self._choose_btn.setEnabled(True)
        else:
            self._title_label.setText("Select a track...")
            self._info_label.setText("")
            self._rating_label.setText("")
            self._preview_btn.setEnabled(False)
            self._choose_btn.setEnabled(False)

    def _toggle_preview(self) -> None:
        """Toggle preview state."""
        self._is_previewing = self._preview_btn.isChecked()

        if self._is_previewing:
            self._preview_btn.setText("⏹ Stop Preview")
            self._frame.setStyleSheet("""
                QFrame {
                    border: 2px solid #ff6b35;
                    border-radius: 8px;
                    background-color: #fff5f2;
                    padding: 10px;
                }
            """)
        else:
            self._preview_btn.setText("🎧 Preview")
            self._frame.setStyleSheet("""
                QFrame {
                    border: 2px solid #ccc;
                    border-radius: 8px;
                    background-color: #f9f9f9;
                    padding: 10px;
                }
                QFrame:hover {
                    border-color: #007acc;
                    background-color: #f0f8ff;
                }
            """)

        self.preview_requested.emit(self._track, self._is_previewing)

    def stop_preview(self) -> None:
        """Stop preview without emitting signal."""
        self._is_previewing = False
        self._preview_btn.setChecked(False)
        self._preview_btn.setText("🎧 Preview")
        self._frame.setStyleSheet("""
            QFrame {
                border: 2px solid #ccc;
                border-radius: 8px;
                background-color: #f9f9f9;
                padding: 10px;
            }
            QFrame:hover {
                border-color: #007acc;
                background-color: #f0f8ff;
            }
        """)

    def _choose_track(self) -> None:
        """Emit signal that this track was chosen."""
        if self._track:
            self.track_selected.emit(self._track)


class MainWindow(QMainWindow):
    """Main window for the JEFF GUI application."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("JEFF")
        self.setMinimumSize(900, 600)

        # Initialize components
        self._player = GStreamerPlayer(self)
        self._library = Library(Path(xdg.BaseDirectory.save_config_path("jeff")) / "library.sqlite")

        # State variables
        self._current_track = None
        self._preview_state = None
        self._queue: deque[tuple[Track, list[Track]]] = deque()
        self._choices = []
        self._disable_seek_updates = False

        # Setup UI
        self._setup_ui()
        self._setup_menu()
        self._setup_timer()

        # Load initial state
        self._library.scan_directories()
        self._skip_forward()
        self._update_choices()

    def _setup_ui(self) -> None:
        """Set up the main user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Create splitter for main content
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Top section: Now Playing
        self._setup_player_section(splitter)

        # Bottom section: Track Comparison
        self._setup_comparison_section(splitter)

        # Set splitter proportions
        splitter.setSizes([150, 400])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def _setup_player_section(self, parent: QLayout | QSplitter) -> None:
        """Set up the now playing section."""
        player_group = QGroupBox("Now Playing")
        player_group.setMaximumHeight(200)
        player_layout = QVBoxLayout(player_group)

        # Track information
        self._current_track_label = QLabel("No track loaded")
        self._current_track_label.setFont(QFont("", 12, QFont.Weight.Bold))
        self._current_track_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._current_path_label = QLabel("")
        self._current_path_label.setStyleSheet("color: #666;")
        self._current_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._current_path_label.setWordWrap(True)

        # Player controls
        controls_layout = QHBoxLayout()

        self._play_pause_btn = QPushButton("▶")
        self._play_pause_btn.setEnabled(False)
        self._play_pause_btn.clicked.connect(self._toggle_playback)

        self._stop_btn = QPushButton("⏹")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_playback)

        self._skip_btn = QPushButton("⏭")
        self._skip_btn.setEnabled(False)
        self._skip_btn.clicked.connect(self._skip_forward)

        # Seek bar and time labels
        self._time_current = QLabel("0:00")
        self._seek_bar = QSlider(Qt.Orientation.Horizontal)
        self._seek_bar.setRange(0, 1000)
        self._seek_bar.setValue(0)
        self._seek_bar.setEnabled(False)
        self._seek_bar.sliderPressed.connect(self._on_seek_pressed)
        self._seek_bar.sliderReleased.connect(self._on_seek_released)
        self._seek_bar.valueChanged.connect(self._on_seek_changed)

        self._time_total = QLabel("0:00")

        controls_layout.addWidget(self._play_pause_btn)
        controls_layout.addWidget(self._stop_btn)
        controls_layout.addWidget(self._skip_btn)
        controls_layout.addWidget(self._time_current)
        controls_layout.addWidget(self._seek_bar, 1)
        controls_layout.addWidget(self._time_total)

        player_layout.addWidget(self._current_track_label)
        player_layout.addWidget(self._current_path_label)
        player_layout.addLayout(controls_layout)

        parent.addWidget(player_group)

    def _setup_comparison_section(self, parent: QLayout | QSplitter) -> None:
        """Set up the track comparison section."""
        comparison_group = QGroupBox("Choose Your Preferred Track")
        comparison_layout = QHBoxLayout(comparison_group)

        # Create two comparison widgets
        self._comparison_widgets: list[ComparisonWidget] = []
        for _ in range(2):
            widget = ComparisonWidget()
            widget.track_selected.connect(self._on_track_chosen)
            widget.preview_requested.connect(self._on_preview_requested)
            self._comparison_widgets.append(widget)
            comparison_layout.addWidget(widget, 1)

        parent.addWidget(comparison_group)

    def _setup_menu(self) -> None:
        """Set up the application menu."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        add_dir_action = QAction("&Add Directory...", self)
        add_dir_action.setShortcut("Ctrl+O")
        add_dir_action.triggered.connect(self._add_directory)
        file_menu.addAction(add_dir_action)

        scan_action = QAction("&Scan Directories", self)
        scan_action.setShortcut("F5")
        scan_action.triggered.connect(self._scan_directories)
        file_menu.addAction(scan_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _setup_timer(self) -> None:
        """Set up the update timer."""
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_ui)
        self._update_timer.start(500)

    # Menu Actions
    def _add_directory(self) -> None:
        """Add a directory to the library."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Add Directory to Library",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )

        if directory:
            self._library.add_directory(Path(directory))
            self._library.scan_directories()

            # If no track is currently loaded, try to load one
            if not self._current_track and self._skip_forward():
                self._play_pause_btn.setEnabled(True)
                self._skip_btn.setEnabled(True)

            self._update_choices()

    def _scan_directories(self) -> None:
        """Rescan all directories."""
        self._library.scan_directories()
        self._update_choices()

    # Player Controls
    def _toggle_playback(self) -> None:
        """Toggle playback state."""
        if self._player.get_state() == Gst.State.PLAYING:
            self._player.pause()
        else:
            self._player.play()

    def _stop_playback(self) -> None:
        """Stop playback."""
        self._player.stop()

    def _skip_forward(self) -> bool:
        """Skip to the next track.

        Returns:
            bool: True if a track was skipped, False if the queue is empty.

        """
        if self._preview_state:
            self._end_preview()

        self._update_queue()

        if len(self._queue) == 0:
            return False

        track, losing_tracks = self._queue.popleft()
        self._library.update_playing(track, losing_tracks)

        state = self._player.get_state()
        self._switch_track(track, state)

        self._play_pause_btn.setEnabled(True)
        self._skip_btn.setEnabled(True)

        self._update_choices()
        return True

    # Track Management
    def _switch_track(self, track: Track, state: Gst.State = Gst.State.PLAYING, position: int | None = None) -> None:
        """Switch to a different track."""
        self._player.stop()
        self._current_track = track

        if track:
            self._current_track_label.setText(track.description)
            self._current_path_label.setText(str(track.path))

            self._player.set_uri(track.uri)

            if position:
                self._player.pause()
                # Wait a moment for the pipeline to be ready
                QTimer.singleShot(100, lambda: self._player.seek(position))

            if state == Gst.State.PLAYING:
                self._player.play()
            elif state == Gst.State.PAUSED:
                self._player.pause()

            self._seek_bar.setEnabled(True)
        else:
            self._current_track_label.setText("No track loaded")
            self._current_path_label.setText("")
            self._seek_bar.setEnabled(False)

    def _update_queue(self) -> None:
        """Update the track queue."""
        if len(self._queue) == 0:
            tracks = self._library.get_next_tracks()
            if len(tracks) > 0:
                self._queue.append((tracks[0], []))

    def _update_choices(self) -> None:
        """Update the comparison choices."""
        self._choices = self._library.get_next_tracks()

        for i, widget in enumerate(self._comparison_widgets):
            if i < len(self._choices):
                widget.set_track(self._choices[i])
            else:
                widget.set_track(None)

    # Comparison Handling
    def _on_track_chosen(self, chosen_track: Track) -> None:
        """Handle when a track is chosen in a comparison."""
        if self._preview_state:
            self._end_preview()

        # Find the chosen track in choices and create losing tracks list
        try:
            chosen_index = self._choices.index(chosen_track)
            losing_tracks = [track for i, track in enumerate(self._choices) if i != chosen_index]

            self._queue.append((chosen_track, losing_tracks))
            self._update_choices()
        except ValueError:
            pass

    def _on_preview_requested(self, track: Track, is_active: bool) -> None:
        """Handle preview requests."""
        if is_active:
            if self._preview_state:
                self._end_preview()

            current_state = self._player.get_state()
            current_position = self._player.get_position() if self._current_track else 0

            self._preview_state = (track, self._current_track, current_state, current_position)
            self._switch_track(track, Gst.State.PLAYING)
        else:
            self._end_preview()

    def _end_preview(self) -> None:
        """End the current preview and restore previous state."""
        if self._preview_state:
            _, previous_track, previous_state, previous_position = self._preview_state
            self._preview_state = None

            for widget in self._comparison_widgets:
                widget.stop_preview()

            if previous_track:
                self._switch_track(previous_track, previous_state, previous_position)

    # UI Updates
    def _update_ui(self) -> None:
        """Update UI elements (called by timer)."""
        if not self._disable_seek_updates:
            self._update_seek_bar()
        self._update_player_buttons()

    def _update_seek_bar(self) -> None:
        """Update the seek bar position."""
        if self._current_track:
            position = self._player.get_position()
            duration = self._player.get_duration()

            if duration > 0:
                self._time_current.setText(format_time(position))
                self._time_total.setText(format_time(duration))

                percentage = int((position / duration) * 1000)
                self._seek_bar.setValue(percentage)
            else:
                self._time_current.setText("0:00")
                self._time_total.setText("0:00")
                self._seek_bar.setValue(0)

    def _update_player_buttons(self) -> None:
        """Update player button states."""
        state = self._player.get_state()

        if state == Gst.State.PLAYING:
            self._play_pause_btn.setText("⏸")
            self._stop_btn.setEnabled(True)
        elif state == Gst.State.PAUSED:
            self._play_pause_btn.setText("▶")
            self._stop_btn.setEnabled(True)
        else:
            self._play_pause_btn.setText("▶")
            self._stop_btn.setEnabled(False)

    # Seek Bar Handling
    def _on_seek_pressed(self) -> None:
        """Handle when seek bar is pressed."""
        self._disable_seek_updates = True

    def _on_seek_released(self) -> None:
        """Handle when seek bar is released."""
        self._disable_seek_updates = False

    def _on_seek_changed(self, value: int) -> None:
        """Handle seek bar value changes."""
        if not self._disable_seek_updates:
            return

        if self._current_track:
            duration = self._player.get_duration()
            if duration > 0:
                position = int((value / 1000.0) * duration)
                self._player.seek(position)

    # Signal Handlers
    def on_track_finished(self) -> None:
        """Handle when a track finishes playing."""
        if self._preview_state:
            self._end_preview()
        else:
            self._skip_forward()


def run() -> int:
    """Run the JEFF GUI application.

    Returns:
        int: Exit code of the application.

    """
    app = QApplication(sys.argv)
    app.setApplicationName("JEFF")
    app.setApplicationVersion(__version__)

    app.setWindowIcon(QIcon.fromTheme("audio-player"))

    window = MainWindow()
    window.show()

    return app.exec()
