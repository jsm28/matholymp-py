Contributing to matholymp
=========================

Although matholymp is intended to be configurable for the most common
requirements of mathematical olympiads, it is likely you will find
some features missing that would be useful for your event; I have a
long list of possible future enhancements (and welcome suggestions for
such features if you don't plan to implement them yourself).  If you
do implement new features for matholymp, please try to contribute them
back to me (even if only useful for some events, it is likely your own
event is not the only one that could use a particular feature).

If you wish to contribute changes to matholymp, you should be working
with the current Git version.  You can then send me diffs generated
with :command:`git diff` or :command:`git format-patch`, either using
:command:`git send-email` or with your normal email client (if sending
with your normal email client, patches should be attached, unless you
are sure your email client does not change whitespace when including
something inline).  You can also send Git pull requests if you prefer.

Please keep patches following the existing coding style (which
generally tries to follow :pep:`8`).  The code is designed so that
configuration for a particular event can be done in configuration
files and HTML and LaTeX templates, so if a feature is only
appropriate for some events please ensure it is appropriately
configurable rather than always enabled.
