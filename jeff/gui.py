#!/usr/bin/env python
#-------------------------------------------------------------------------------
#  Copyright (c) 2015 Jason Lynch <jason@calindora.com>
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
#-------------------------------------------------------------------------------

import os
import xdg.BaseDirectory

from collections import deque

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gst
from gi.repository import Gtk

from . import library

#-------------------------------------------------------------------------------
# Constants
#-------------------------------------------------------------------------------

CHOICES = 2


#-------------------------------------------------------------------------------
# Classes
#-------------------------------------------------------------------------------

class Application(Gtk.Application):
    def __init__(self):
        Gtk.Application.__init__(self, application_id='com.calindora.jeff')
        Gst.init()

        GLib.set_application_name('Jeff')

        self.connect('activate', self.on_activate)
        self.connect('startup', self.on_startup)

    #---------------------------------------------------------------------------
    # Signal Handlers
    #---------------------------------------------------------------------------

    def on_activate(self, _):
        self._window.show_all()

    def on_startup(self, _):
        self._window = MainWindow()
        self.add_window(self._window)

        builder = Gtk.Builder()
        builder.add_from_string('''
            <interface>
                <menu id="app-menu">
                    <section>
                        <item>
                            <attribute name="label" translatable="yes">_Add Directory</attribute>
                            <attribute name="action">app.add_directory</attribute>
                        </item>
                    </section>
                    <section>
                        <item>
                            <attribute name="label" translatable="yes">_Quit</attribute>
                            <attribute name="action">app.quit</attribute>
                            <attribute name="accel">&lt;Primary&gt;q</attribute>
                        </item>
                    </section>
                </menu>
            </interface>
        ''')

        self.set_app_menu(builder.get_object('app-menu'))

        self._add_action('add_directory', self.on_action_add_directory)
        self._add_action('quit', self.on_action_quit)

    def on_action_add_directory(self, action, user_data):
        self._window.add_directory()

    def on_action_quit(self, action, user_data):
        self._window.destroy()

    #---------------------------------------------------------------------------
    # Private Methods
    #---------------------------------------------------------------------------

    def _add_action(self, name, handler):
        action = Gio.SimpleAction.new(name, None)
        action.connect('activate', handler)
        self.add_action(action)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self):
        Gtk.ApplicationWindow.__init__(self)

        self._create_images()
        self._create_widgets()
        self._initialize_player()

        self._library = library.Library(os.path.join(xdg.BaseDirectory.save_config_path('jeff'), 'library.sqlite'))
        self._library.scan_directories()

        self._current_Track = None
        self._preview_state = None

        self._queue = deque()
        self.skip_forward()

        self._update_choices()

        GObject.timeout_add(500, self.on_timeout_update)

    #---------------------------------------------------------------------------
    # Public Methods
    #---------------------------------------------------------------------------

    def add_directory(self):
        dialog = Gtk.FileChooserDialog('Add Directory to Library', self, Gtk.FileChooserAction.SELECT_FOLDER, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        dialog.set_default_response(Gtk.ResponseType.OK)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self._library.add_directory(dialog.get_filename())
            self._library.scan_directories()

            if not self._player.get_property('current-uri'):
                if self.skip_forward():
                    self._widget_button_playpause.set_sensitive(True)
                    self._widget_button_skip_forward.set_sensitive(True)

        dialog.destroy()

        self._update_choices()

    def skip_forward(self):
        if self._preview_state:
            self._preview_end()

        self._update_queue()

        if len(self._queue) == 0:
            return False

        track, losing_tracks = self._queue.popleft()

        state = self._player.get_state(Gst.CLOCK_TIME_NONE)[1]
        self._switch_track(track, state)

        self._library.update_playing(track, losing_tracks)

        self._widget_button_playpause.set_sensitive(True)
        self._widget_button_skip_forward.set_sensitive(True)

        self._update_seek_bar()
        self._update_choices()

        return True

    def playpause(self):
        if self._player.get_state(Gst.CLOCK_TIME_NONE)[1] == Gst.State.PLAYING:
            self._player.set_state(Gst.State.PAUSED)
        else:
            self._player.set_state(Gst.State.PLAYING)

    def stop(self):
        self._player.set_state(Gst.State.READY)

    #---------------------------------------------------------------------------
    # Signal Handlers
    #---------------------------------------------------------------------------

    def on_button_choices_preview_toggled(self, widget, index):
        if self._preview_state:
            if self._preview_state[0] == index:
                if not widget.get_active():
                    self._preview_end()
            else:
                other_widget = self._widget_choices[self._preview_state[0]]['preview']
                other_widget.handler_block_by_func(self.on_button_choices_preview_toggled)
                other_widget.set_active(False)
                other_widget.handler_unblock_by_func(self.on_button_choices_preview_toggled)

                self._preview_state = (index, self._preview_state[1], self._preview_state[2], self._preview_state[3])
                self._switch_track(self._choices[index])
        else:
            state = self._player.get_state(Gst.CLOCK_TIME_NONE)[1]
            track = self._current_track
            position = self._player.query_position(Gst.Format.TIME)[1]

            self._preview_state = (index, track, state, position)
            self._switch_track(self._choices[index])

    def on_button_choices_enqueue_clicked(self, widget, index):
        if self._preview_state:
            self._preview_end()

        choice = self._choices.pop(index)
        self._queue.append((choice, self._choices))
        self._update_choices()

    def on_button_playpause_clicked(self, widget):
        self.playpause()

    def on_button_stop_clicked(self, widget):
        self.stop()

    def on_button_skip_backward_clicked(self, widget):
        pass

    def on_button_skip_forward_clicked(self, widget):
        self.skip_forward()

    def on_player_eos(self, bus, message):
        if self._preview_state:
            self._preview_end()
        else:
            self.skip_forward()

    def on_player_state_changed(self, bus, message):
        _, state, _ = message.parse_state_changed()
        self._update_buttons(state)

    def on_seek_bar_value_changed(self, scale):
        value = scale.get_value()
        duration = self._player.query_duration(Gst.Format.TIME)[1]
        self._player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, duration * value)

    def on_timeout_update(self):
        self._update_seek_bar()
        return True

    #---------------------------------------------------------------------------
    # Private Methods
    #---------------------------------------------------------------------------

    def _create_button(self, image, clicked_handler):
        button = Gtk.Button()
        button.set_image(image)
        button.connect('clicked', clicked_handler)
        button.set_sensitive(False)

        return button

    def _create_images(self):
        self._image_play = Gtk.Image.new_from_icon_name('media-playback-start', Gtk.IconSize.BUTTON)
        self._image_pause = Gtk.Image.new_from_icon_name('media-playback-pause', Gtk.IconSize.BUTTON)
        self._image_stop = Gtk.Image.new_from_icon_name('media-playback-stop', Gtk.IconSize.BUTTON)
        self._image_skip_backward = Gtk.Image.new_from_icon_name('media-skip-backward', Gtk.IconSize.BUTTON)
        self._image_skip_forward = Gtk.Image.new_from_icon_name('media-skip-forward', Gtk.IconSize.BUTTON)

    def _create_widgets(self):
        main_box = Gtk.VBox()
        self.add(main_box)

        frame = Gtk.Frame(label='Player')
        main_box.pack_start(frame, True, True, 0)

        vbox = Gtk.VBox(spacing=3, border_width=3)
        frame.add(vbox)

        self._widget_playing = Gtk.Label()
        vbox.pack_start(self._widget_playing, True, True, 0)

        box = Gtk.HBox(spacing=3, border_width=3)
        vbox.pack_start(box, True, True, 0)

        self._widget_button_playpause = self._create_button(self._image_play, self.on_button_playpause_clicked)
        self._widget_button_stop = self._create_button(self._image_stop, self.on_button_stop_clicked)
        self._widget_button_skip_backward = self._create_button(self._image_skip_backward, self.on_button_skip_backward_clicked)
        self._widget_button_skip_forward = self._create_button(self._image_skip_forward, self.on_button_skip_forward_clicked)

        self._widget_seek_bar = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01)
        self._widget_seek_bar.set_sensitive(False)
        self._widget_seek_bar.set_draw_value(False)
        self._widget_seek_bar.set_size_request(200, -1)
        self._widget_seek_bar.connect('value-changed', self.on_seek_bar_value_changed)

        self._widget_label_time_current = Gtk.Label('-')
        self._widget_label_time_maximum = Gtk.Label('-')

        box.pack_start(self._widget_button_playpause, True, True, 0)
        box.pack_start(self._widget_button_stop, True, True, 0)
        box.pack_start(self._widget_button_skip_backward, True, True, 0)
        box.pack_start(self._widget_button_skip_forward, True, True, 0)
        box.pack_start(self._widget_seek_bar, True, True, 0)
        box.pack_start(self._widget_label_time_current, False, False, 0)
        box.pack_start(Gtk.Label(' / '), False, False, 0)
        box.pack_start(self._widget_label_time_maximum, False, False, 0)

        frame = Gtk.Frame(label='Choices')
        main_box.pack_start(frame, True, True, 0)

        box = Gtk.VBox(spacing=3, border_width=5)
        frame.add(box)

        self._widget_choices = []

        for i in range(CHOICES):
            widgets = {}

            inner_box = Gtk.HBox(spacing=3)
            box.pack_start(inner_box, True, True, 0)

            widgets['preview'] = Gtk.ToggleButton('Preview')
            widgets['preview'].set_sensitive(False)
            widgets['preview'].connect('toggled', self.on_button_choices_preview_toggled, i)

            widgets['enqueue'] = Gtk.Button('Enqueue')
            widgets['enqueue'].set_sensitive(False)
            widgets['enqueue'].connect('clicked', self.on_button_choices_enqueue_clicked, i)

            widgets['label'] = Gtk.Label()

            inner_box.pack_start(widgets['preview'], False, False, 0)
            inner_box.pack_start(widgets['enqueue'], False, False, 0)
            inner_box.pack_start(widgets['label'], False, False, 0)

            self._widget_choices.append(widgets)

    def _format_time(self, nanoseconds):
        seconds = int(nanoseconds / 1000000000 + 0.5)
        minutes = int(seconds / 60)

        if minutes > 60:
            return '{:d}{:02d}:{:02d}'.format(int(minutes / 60), minutes % 60, seconds % 60)
        else:
            return '{:d}:{:02d}'.format(minutes, seconds % 60)

    def _initialize_player(self):
        self._player = Gst.ElementFactory.make('playbin', 'player')

        bus = self._player.get_bus()
        bus.add_signal_watch()
        bus.connect('message::eos', self.on_player_eos)
        bus.connect('message::state-changed', self.on_player_state_changed)

    def _preview_end(self):
        self._switch_track(self._preview_state[1], self._preview_state[2], self._preview_state[3])
        self._preview_state = None

        for widgets in self._widget_choices:
            widgets['preview'].handler_block_by_func(self.on_button_choices_preview_toggled)
            widgets['preview'].set_active(False)
            widgets['preview'].handler_unblock_by_func(self.on_button_choices_preview_toggled)

    def _switch_track(self, track, state=Gst.State.PLAYING, position=None):
        self._player.set_state(Gst.State.NULL)
        self._update_buttons(Gst.State.PAUSED)
        self._current_track = track

        if track:
            self._widget_playing.set_label(track.description)

            self._player.set_property('uri', track.uri)

            if position:
                self._player.set_state(Gst.State.PAUSED)
                self._player.get_state(Gst.CLOCK_TIME_NONE)
                self._player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, position)

            self._player.set_state(state)
        else:
            self._widget_playing.set_label('')

    def _update_buttons(self, state):
        if state == Gst.State.NULL:
            self._widget_seek_bar.set_sensitive(False)
        elif state == Gst.State.READY:
            self._widget_button_stop.set_sensitive(False)
            self._widget_seek_bar.set_sensitive(True)
        elif state == Gst.State.PAUSED:
            self._widget_button_playpause.set_image(self._image_play)
            self._widget_button_stop.set_sensitive(True)
        elif state == Gst.State.PLAYING:
            self._widget_button_playpause.set_image(self._image_pause)

    def _update_choices(self):
        self._choices = self._library.get_next_tracks(CHOICES)

        for index, choice in enumerate(self._choices):
            self._widget_choices[index]['label'].set_label(choice.description)
            self._widget_choices[index]['preview'].set_sensitive(True)
            self._widget_choices[index]['enqueue'].set_sensitive(True)

    def _update_queue(self):
        if len(self._queue) == 0:
            tracks = self._library.get_next_tracks(1)

            if len(tracks) > 0:
                self._queue.append((tracks[0], []))

    def _update_seek_bar(self):
        position = self._player.query_position(Gst.Format.TIME)
        duration = self._player.query_duration(Gst.Format.TIME)

        if position[0] and duration[0] and duration[1] > 0:
            self._widget_label_time_current.set_label(self._format_time(position[1]))
            self._widget_label_time_maximum.set_label(self._format_time(duration[1]))

            self._widget_seek_bar.handler_block_by_func(self.on_seek_bar_value_changed)
            self._widget_seek_bar.set_value(position[1] / duration[1])
            self._widget_seek_bar.handler_unblock_by_func(self.on_seek_bar_value_changed)
        else:
            self._widget_seek_bar.set_value(0.0)
