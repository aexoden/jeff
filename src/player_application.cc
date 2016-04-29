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

#include <glibmm/miscutils.h>

#include "player_application.hh"
#include "player_window.hh"
#include "version.hh"

Glib::RefPtr<PlayerApplication> PlayerApplication::create(const Glib::RefPtr<Gst::PlayBin> & playbin)
{
	return Glib::RefPtr<PlayerApplication>(new PlayerApplication(playbin));
}

PlayerApplication::PlayerApplication(const Glib::RefPtr<Gst::PlayBin> & playbin) :
	Gtk::Application("com.calindora.jeff"),
	_window(playbin)
{
	Glib::set_application_name("JEFF " JEFF_VERSION);
}

void PlayerApplication::on_startup()
{
	Gtk::Application::on_startup();

	add_window(_window);

	add_action("quit", sigc::mem_fun(*this, &PlayerApplication::_on_action_quit));

	auto builder = Gtk::Builder::create();

	builder->add_from_string(
		"<interface>"
		"	<menu id='app-menu'>"
		"		<section>"
		"			<item>"
		"				<attribute name='label' translatable='yes'>_Quit</attribute>"
		"				<attribute name='action'>app.quit</attribute>"
		"				<attribute name='accel'>&lt;Primary&gt;q</attribute>"
		"			</item>"
		"		</section>"
		"	</menu>"
		"</interface>"
	);

	set_app_menu(Glib::RefPtr<Gio::Menu>::cast_dynamic(builder->get_object("app-menu")));
}

void PlayerApplication::on_activate()
{
	_window.show_all();
}

void PlayerApplication::_on_action_quit()
{
	quit();
}
