jeff
====

JEFF Emits Fabulous Frequencies

Jason Lynch <jason@calindora.com>

Jeff is a music player written in Python and based on GTK+ and GStreamer
designed to help you semi-automatically rank your music. It's not completely
automatic, but it also doesn't require you to manually rate tracks on some
arbitrary scale.

Fundamentally, Jeff presents you a series of pairs of tracks for you to compare
and enqueue. The enqueued track (when played) registers a victory over the
losing track. By assembling these victories over time, Jeff is eventually able
to generate a ranked listing of tracks. Note, however, that the number of
comparisons necessary to fully rank a set of tracks is not small, especially for
larger collections.

I fully expect that no one in the world will be interested in this software
other than me. I primarily use it to sort tracks so that a smaller, more liked
collection of tracks can be transferred to my mobile phone for use while on the
road. I have trouble imagining many other use cases, especially since Jeff does
not currently use the ranking information itself in any way.

A script is provided to help export the ranking data, but it wasn't really
designed for release, so it may or may not work in your environment.
