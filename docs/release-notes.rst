Release notes
=============

These release notes do not cover changes to the Python API of
matholymp, which is considered unstable.  If making use of matholymp
at the Python API level (such as by writing your own scripts importing
matholymp modules, or making substantial changes to the example HTML
templates for the online registration system that involve calls to
matholymp APIs not in the provided examples), you should examine the
source code changes to determine if any API changes require changes to
your code.

Next version (unreleased)
-------------------------

* The registration system can detect some more cases of invalid URLs
  specified for previous participation.

* A new configuration variable ``matholymp_static_site_directory``
  must be specified in :file:`extensions/config.ini` for the
  registration system.  If this is empty, there is no change in
  functionality from previous versions.  If not empty, it is a
  filesystem path to the static site (directory with
  :file:`staticsite.cfg`), either absolute or relative to the Roundup
  instance directory, on the system running the registration system;
  this directory must be readably by the registration system, but need
  not be writable.  This is used by the registration system to access
  information from the static site (specifically, to check whether
  URLs for previous participation specified at registration time do
  relate to some country or person that previously participated).

Version 2014.09.0 (28 September 2014)
-------------------------------------

* First public release.
