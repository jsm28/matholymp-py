.. Documentation of Roundup patches for matholymp.
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

.. _roundup-patches:

Roundup patches
===============

Matholymp comes with some patches to `Roundup
<http://roundup-tracker.org/>`_ that have been found useful when using
the matholymp's online registration functionality based on Roundup.
It may be useful to apply these patches to the Roundup sources before
installing Roundup.  All these patches can be applied with
:command:`patch -p1 -N -E` from within the Roundup source directory.

These are located in the :file:`roundup-patches/` directory of the
source distribution, and are relative to Roundup version 2.5.0 (so may
require changes to apply cleanly to later versions).  Details of the
individual patches are:

* :download:`issue2550750-no-timeout-mail.patch
  <../roundup-patches/issue2550750-no-timeout-mail.patch>` is a patch
  for `Roundup issue 2550750
  <https://issues.roundup-tracker.org/issue2550750>`_ that avoids
  socket timeouts (when large images are served through Roundup, for
  example) generating emails to the person running the registration
  system.

* :download:`increase-socket-timeout.patch
  <../roundup-patches/increase-socket-timeout.patch>` is a patch that
  increases the socket timeout to reduce the number of such timeouts
  (there may however not be a great need for this when the previous
  patch is applied).
