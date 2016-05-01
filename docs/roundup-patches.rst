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
source distribution, and are relative to Roundup version 1.5.1 (so may
require changes to apply cleanly to later versions).  Details of the
individual patches are:

* :download:`issue2086536-back_postgresql.patch
  <../roundup-patches/issue2086536-back_postgresql.patch>` is an
  updated version of a patch originally provided by someone else in
  `Roundup issue 2086536
  <http://issues.roundup-tracker.org/issue2086536>`_ for issues with
  the PostgreSQL back end.

* :download:`back_postgresql-retry-more.patch
  <../roundup-patches/back_postgresql-retry-more.patch>` is a patch
  that works around some problems with simultaneous accesses to the
  database by increasing the number of retries.  The `underlying
  problem
  <http://article.gmane.org/gmane.comp.bug-tracking.roundup.devel/4812>`_
  being worked around by this patch, and possibly to some extent by
  the previous patch, is that database updates for session cookies
  (where concurrent updates are extremely likely, if someone accesses
  a page on which multiple images, scripts or other files are served
  through Roundup, and each access updates the session information)
  use the same database cursor as for database content (where
  concurrent updates are extremely unlikely and not a significant
  concern in the matholymp context).

* :download:`issue2550750-no-timeout-mail.patch
  <../roundup-patches/issue2550750-no-timeout-mail.patch>` is a patch
  for `Roundup issue 2550750
  <http://issues.roundup-tracker.org/issue2550750>`_ that avoids
  socket timeouts (when large images are served through Roundup, for
  example) generating emails to the person running the registration
  system.

* :download:`increase-socket-timeout.patch
  <../roundup-patches/increase-socket-timeout.patch>` is a patch that
  increases the socket timeout to reduce the number of such timeouts
  (there may however not be a great need for this when the previous
  patch is applied).

* :download:`issue2550722-multilink.patch
  <../roundup-patches/issue2550722-multilink.patch>` is a patch for
  `Roundup issue 2550722
  <http://issues.roundup-tracker.org/issue2550722>`_ that avoids
  internal errors in Roundup in certain cases of incorrect settings of
  Multilink fields in the web interface.  (For matholymp, the relevant
  fields are "Other roles" and "Guide for", so those internal errors
  can only be triggered by administrative users and cannot arise for
  registration of ordinary participants.  However, when they do arise,
  it may be necessary to restart the process of registering the person
  for which the mistake was made.)
