.. Documentation of contributing to matholymp.
   Copyright 2014-2025 Joseph Samuel Myers.

   This program is free software; you can redistribute it and/or
   modify it under the terms of the GNU General Public License as
   published by the Free Software Foundation; either version 3 of the
   License, or (at your option) any later version.

   This program is distributed in the hope that it will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program.  If not, see
   <https://www.gnu.org/licenses/>.

   Additional permission under GNU GPL version 3 section 7:

   If you modify this program, or any covered work, by linking or
   combining it with the OpenSSL project's OpenSSL library (or a
   modified version of that library), containing parts covered by the
   terms of the OpenSSL or SSLeay licenses, the licensors of this
   program grant you additional permission to convey the resulting
   work.  Corresponding Source for a non-source form of such a
   combination shall include the source code for the parts of OpenSSL
   used as well as that of the covered work.

.. _contributing:

Contributing to matholymp
=========================

Although matholymp is intended to be configurable for the most common
requirements of mathematical olympiads, it is likely you will find
some features missing that would be useful for your event; I have a
long list of possible future enhancements (and welcome suggestions for
such features if you don't plan to implement them yourself); see
:ref:`todo`.  If you do implement new features for matholymp, please
try to contribute them back to me (even if only useful for some
events, it is likely your own event is not the only one that could use
a particular feature).

If you wish to contribute changes to matholymp, you should be working
with the current Git version.  You can then send me diffs generated
with :command:`git diff` or :command:`git format-patch`, either using
:command:`git send-email` or with your normal email client (if sending
with your normal email client, patches should be attached, unless you
are sure your email client does not change whitespace, including UTF-8
BOMs, when including something inline).  You can also send Git pull
requests if you prefer.

Please keep patches following the existing coding style (which
generally tries to follow :pep:`8`).  The code is designed so that
configuration for a particular event can be done in configuration
files and HTML and LaTeX templates, so if a feature is only
appropriate for some events please ensure it is appropriately
configurable rather than always enabled.  If the new features affect
parts of the code covered by the automated testsuite (which can be run
with :command:`mo-run-tests`), please update existing test
expectations if needed, and add new tests if not adequately covered by
the existing tests.
