/*
 * Copyright (c) 2016 Jason Lynch <jason@calindora.com>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#ifndef JEFF_PLAYER_WINDOW_HH
#define JEFF_PLAYER_WINDOW_HH

#include <glibmm/main.h>
#include <glibmm/ustring.h>
#include <gstreamermm/bus.h>
#include <gstreamermm/playbin.h>
#include <gtkmm/applicationwindow.h>
#include <gtkmm/button.h>
#include <gtkmm/frame.h>
#include <gtkmm/hvbox.h>
#include <gtkmm/label.h>
#include <gtkmm/image.h>
#include <gtkmm/scale.h>

class PlayerWindow : public Gtk::ApplicationWindow
{
	public:
		PlayerWindow(const Glib::RefPtr<Gst::PlayBin> & playbin);
		virtual ~PlayerWindow();

		void playpause();
		void stop();

	private:
		void _initialize_widgets();

		void _update_buttons(Gst::State state);
		void _update_seek_bar();

		bool _on_bus_message(const Glib::RefPtr<Gst::Bus> &, const Glib::RefPtr<Gst::Message> & message);

		void _on_button_playpause_clicked();
		void _on_button_stop_clicked();
		void _on_button_skip_backward_clicked();
		void _on_button_skip_forward_clicked();

		bool _on_seek_bar_value_changed(Gtk::ScrollType, double value);

		bool _on_timeout_update();

		gint64 _playbin_bus_watch_id;
		sigc::connection _connection_seek_bar_value_changed;

		Glib::RefPtr<Gst::PlayBin> _playbin;

		Gtk::HBox _widget_box_controls;

		Gtk::VBox _widget_box_main;
		Gtk::VBox _widget_box_player;

		Gtk::Label _widget_label_playing;
		Gtk::Label _widget_label_time;

		Gtk::Frame _widget_frame_player;

		Gtk::Button _widget_button_playpause;
		Gtk::Button _widget_button_stop;
		Gtk::Button _widget_button_skip_backward;
		Gtk::Button _widget_button_skip_forward;

		Gtk::Scale _widget_seek_bar;
};

#endif
