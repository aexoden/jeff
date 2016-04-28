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

#include <glibmm/main.h>
#include <glibmm/ustring.h>
#include <gstreamermm/bus.h>
#include <gstreamermm/playbin.h>

class Player
{
	public:
		Player(const Glib::RefPtr<Glib::MainLoop> & mainloop);

		void enqueue(const Glib::ustring & uri);

		bool on_bus_message(const Glib::RefPtr<Gst::Bus> &, const Glib::RefPtr<Gst::Message> & message);

	private:
		Glib::RefPtr<Glib::MainLoop> _mainloop;
		Glib::RefPtr<Gst::PlayBin> _playbin;
};
