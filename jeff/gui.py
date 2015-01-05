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

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gst
from gi.repository import Gtk

from . import library

#-------------------------------------------------------------------------------
# Classes
#-------------------------------------------------------------------------------

class Application(Gtk.Application):
	def __init__(self):
		Gtk.Application.__init__(self, application_id='com.calindora.jeff')
		Gst.init()

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
		Gtk.ApplicationWindow.__init__(self, title='Jeff')

		self._create_images()
		self._create_widgets()
		self._initialize_player()

		self._library = library.Library(os.path.join(xdg.BaseDirectory.save_config_path('jeff'), 'library.sqlite'))
		self._library.scan_directories()

		if self.skip_forward():
			self._widget_button_playpause.set_sensitive(True)
			self._widget_button_skip_forward.set_sensitive(True)

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

			if not self._player.get_property('uri'):
				if self.skip_forward():
					self._widget_button_playpause.set_sensitive(True)
					self._widget_button_skip_forward.set_sensitive(True)

		dialog.destroy()

	def skip_forward(self):
		track = self._select_next_track()

		if track:
			state = self._player.get_state(Gst.CLOCK_TIME_NONE)[1]
			self._player.set_state(Gst.State.NULL)
			self._player.set_property('uri', GLib.filename_to_uri(track, None))
			self._player.set_state(state)
			self._update_seek_bar()
			return True
		else:
			return False

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

	def on_button_playpause_clicked(self, widget):
		self.playpause()

	def on_button_stop_clicked(self, widget):
		self.stop()

	def on_button_skip_backward_clicked(self, widget):
		pass

	def on_button_skip_forward_clicked(self, widget):
		self.skip_forward()

	def on_player_eos(self, bus, message):
		self.skip_forward()

	def on_player_state_changed(self, bus, message):
		_, state, _ = message.parse_state_changed()

		if state == Gst.State.READY:
			self._widget_button_stop.set_sensitive(False)
		elif state == Gst.State.PAUSED:
			self._widget_button_playpause.set_image(self._image_play)
			self._widget_button_stop.set_sensitive(True)
		elif state == Gst.State.PLAYING:
			self._widget_button_playpause.set_image(self._image_pause)

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

		box = Gtk.HBox(spacing=3)
		main_box.pack_start(box, True, True, 0)

		self._widget_button_playpause = self._create_button(self._image_play, self.on_button_playpause_clicked)
		self._widget_button_stop = self._create_button(self._image_stop, self.on_button_stop_clicked)
		self._widget_button_skip_backward = self._create_button(self._image_skip_backward, self.on_button_skip_backward_clicked)
		self._widget_button_skip_forward = self._create_button(self._image_skip_forward, self.on_button_skip_forward_clicked)

		self._widget_seek_bar = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01)
		self._widget_seek_bar.set_sensitive(False)
		self._widget_seek_bar.set_draw_value(False)
		self._widget_seek_bar.set_size_request(200, -1)

		self._widget_label_time_current = Gtk.Label('-')
		self._widget_label_time_maximum = Gtk.Label('-')

		box.pack_start(self._widget_button_playpause, True, True, 0)
		box.pack_start(self._widget_button_stop, True, True, 0)
		box.pack_start(self._widget_button_skip_backward, True, True, 0)
		box.pack_start(self._widget_button_skip_forward, True, True, 0)
		box.pack_start(self._widget_seek_bar, True, True, 0)
		box.pack_start(self._widget_label_time_current, True, True, 0)
		box.pack_start(Gtk.Label(' / '), True, True, 0)
		box.pack_start(self._widget_label_time_maximum, True, True, 0)

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

	def _select_next_track(self):
		return self._library.get_next()

	def _update_seek_bar(self):
		position = self._player.query_position(Gst.Format.TIME)
		duration = self._player.query_duration(Gst.Format.TIME)

		if position[0] and duration[0] and duration[1] > 0:
			self._widget_label_time_current.set_label(self._format_time(position[1]))
			self._widget_label_time_maximum.set_label(self._format_time(duration[1]))
			self._widget_seek_bar.set_value(position[1] / duration[1])
		else:
			self._widget_seek_bar.set_value(0.0)
