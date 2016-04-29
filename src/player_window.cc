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

#include <iomanip>
#include <sstream>

#include "player_window.hh"

PlayerWindow::PlayerWindow(const Glib::RefPtr<Gst::PlayBin> & playbin) :
	Gtk::ApplicationWindow(),
	_playbin{playbin},
	_widget_label_time("0:00 / 0:00"),
	_widget_frame_player("Player"),
	_widget_seek_bar(Gtk::ORIENTATION_HORIZONTAL)
{
	_initialize_widgets();

	_playbin_bus_watch_id = _playbin->get_bus()->add_watch(sigc::mem_fun(*this, &PlayerWindow::_on_bus_message));
	Glib::signal_timeout().connect(sigc::mem_fun(*this, &PlayerWindow::_on_timeout_update), 200);

	_widget_button_playpause.set_sensitive(true);

	_playbin->set_state(Gst::STATE_PLAYING);
}

PlayerWindow::~PlayerWindow()
{
	_playbin->set_state(Gst::STATE_NULL);
	_playbin->get_bus()->remove_watch(_playbin_bus_watch_id);
}

void PlayerWindow::playpause()
{
	Gst::State state, pending;
	_playbin->get_state(state, pending, Gst::CLOCK_TIME_NONE);

	if (state == Gst::STATE_PLAYING)
	{
		_playbin->set_state(Gst::STATE_PAUSED);
	}
	else
	{
		_playbin->set_state(Gst::STATE_PLAYING);
	}
}

void PlayerWindow::stop()
{
	_playbin->set_state(Gst::STATE_READY);
}

void PlayerWindow::_initialize_widgets()
{
	add(_widget_box_main);
	_widget_box_main.pack_start(_widget_frame_player, true, true, 0);

	_widget_frame_player.add(_widget_box_player);

	_widget_box_player.set_spacing(3);
	_widget_box_player.set_border_width(3);
	_widget_box_player.pack_start(_widget_label_playing, true, true, 0);
	_widget_box_player.pack_start(_widget_box_controls, true, true, 0);

	_widget_button_playpause.set_sensitive(false);
	_widget_button_stop.set_sensitive(false);
	_widget_button_skip_backward.set_sensitive(false);
	_widget_button_skip_forward.set_sensitive(false);

	_widget_button_playpause.set_image_from_icon_name("media-playback-start");
	_widget_button_stop.set_image_from_icon_name("media-playback-stop");
	_widget_button_skip_backward.set_image_from_icon_name("media-skip-backward");
	_widget_button_skip_forward.set_image_from_icon_name("media-skip-forward");

	_widget_button_playpause.signal_clicked().connect(sigc::mem_fun(*this, &PlayerWindow::_on_button_playpause_clicked));
	_widget_button_stop.signal_clicked().connect(sigc::mem_fun(*this, &PlayerWindow::_on_button_stop_clicked));
	_widget_button_skip_backward.signal_clicked().connect(sigc::mem_fun(*this, &PlayerWindow::_on_button_skip_backward_clicked));
	_widget_button_skip_forward.signal_clicked().connect(sigc::mem_fun(*this, &PlayerWindow::_on_button_skip_forward_clicked));

	_widget_seek_bar.set_range(0.0, 1.0);
	_widget_seek_bar.set_increments(0.01, 0.1);
	_widget_seek_bar.set_sensitive(false);
	_widget_seek_bar.set_draw_value(false);
	_widget_seek_bar.set_size_request(200, -1),
	_connection_seek_bar_value_changed = _widget_seek_bar.signal_change_value().connect(sigc::mem_fun(*this, &PlayerWindow::_on_seek_bar_value_changed));

	_widget_box_controls.set_spacing(3);
	_widget_box_controls.set_border_width(3);
	_widget_box_controls.pack_start(_widget_button_playpause, true, true, 0);
	_widget_box_controls.pack_start(_widget_button_stop, true, true, 0);
	_widget_box_controls.pack_start(_widget_button_skip_backward, true, true, 0);
	_widget_box_controls.pack_start(_widget_button_skip_forward, true, true, 0);
	_widget_box_controls.pack_start(_widget_seek_bar, true, true, 0);
	_widget_box_controls.pack_start(_widget_label_time, false, false, 0);
}

void PlayerWindow::_update_buttons(Gst::State state)
{
	switch (state)
	{
		case Gst::STATE_NULL:
			_widget_seek_bar.set_sensitive(false);
			break;
		case Gst::STATE_READY:
			_widget_button_stop.set_sensitive(false);
			_widget_seek_bar.set_sensitive(true);
			break;
		case Gst::STATE_PAUSED:
			_widget_button_playpause.set_image_from_icon_name("media-playback-start");
			_widget_button_stop.set_sensitive(true);
			break;
		case Gst::STATE_PLAYING:
			_widget_button_playpause.set_image_from_icon_name("media-playback-pause");
			break;
		default:
			break;
	}
}

bool PlayerWindow::_on_bus_message(const Glib::RefPtr<Gst::Bus> &, const Glib::RefPtr<Gst::Message> & message)
{
	switch (message->get_message_type())
	{
		case Gst::MESSAGE_EOS:
			stop();
			break;
		case Gst::MESSAGE_STATE_CHANGED:
			_update_buttons(Glib::RefPtr<Gst::MessageStateChanged>::cast_static(message)->parse());
			break;
		default:
			break;
	}

	return true;
}

void PlayerWindow::_on_button_playpause_clicked()
{
	playpause();
}

void PlayerWindow::_on_button_stop_clicked()
{
	stop();
}

void PlayerWindow::_on_button_skip_backward_clicked() { }
void PlayerWindow::_on_button_skip_forward_clicked() { }

bool PlayerWindow::_on_seek_bar_value_changed(Gtk::ScrollType, double value) {
	gint64 duration;
	_playbin->query_duration(Gst::FORMAT_TIME, duration);
	_playbin->seek(Gst::FORMAT_TIME, Gst::SEEK_FLAG_FLUSH | Gst::SEEK_FLAG_KEY_UNIT, static_cast<gint64>(value * duration));

	return false;
}

bool PlayerWindow::_on_timeout_update()
{
	_update_seek_bar();

	return true;
}

void PlayerWindow::_update_seek_bar()
{
	gint64 duration = 0;
	gint64 position = 0;

	if (_playbin->query_duration(Gst::FORMAT_TIME, duration) && _playbin->query_position(Gst::FORMAT_TIME, position))
	{
		std::ostringstream position_stream;
		std::ostringstream duration_stream;

		position_stream << std::right << std::setfill('0');
		duration_stream << std::right << std::setfill('0');

		if (Gst::get_hours(duration) > 0)
		{
			position_stream << Gst::get_hours(position) << ":" << std::setw(2);
			duration_stream << Gst::get_hours(duration) << ":" << std::setw(2);
		}

		position_stream << Gst::get_minutes(position) << ":";
		duration_stream << Gst::get_minutes(duration) << ":";

		position_stream << std::setw(2) << Gst::get_seconds(position);
		duration_stream << std::setw(2) << Gst::get_seconds(duration);

		_widget_label_time.set_text(position_stream.str() + " / " + duration_stream.str());

		_connection_seek_bar_value_changed.block();
		_widget_seek_bar.set_value(static_cast<double>(position) / duration);
		_connection_seek_bar_value_changed.unblock();
	}
	else
	{
		_widget_label_time.set_text("0:00 / 0:00");
		_widget_seek_bar.set_value(0.0);
	}
}
