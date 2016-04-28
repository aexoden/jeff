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

#include "player.hh"

Player::Player(const Glib::RefPtr<Glib::MainLoop> & mainloop) :
	_mainloop(mainloop),
	_playbin(Gst::PlayBin::create())
{
	if (_playbin)
	{
		auto bus = _playbin->get_bus();
		bus->add_watch(sigc::mem_fun(this, &Player::on_bus_message));
	}
}

void Player::enqueue(const Glib::ustring & uri)
{
	if (_playbin)
	{
		_playbin->property_uri() = uri;
		_playbin->set_state(Gst::STATE_PLAYING);
	}
	else
	{
		_mainloop->quit();
	}
}

bool Player::on_bus_message(const Glib::RefPtr<Gst::Bus> &, const Glib::RefPtr<Gst::Message> & message)
{
	switch (message->get_message_type())
	{
		case Gst::MESSAGE_EOS:
			_playbin->set_state(Gst::STATE_NULL);
			_mainloop->quit();
			return false;
		default:
			break;
	}

	return true;
}
