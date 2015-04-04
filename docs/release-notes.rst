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

* Country and role names can now contain commas without this causing
  ambiguity in interpretation of the CSV fields ``Other Roles`` and
  ``Guide For``.  Those fields now contain values interpreted as if
  they were the single row of a CSV file, instead of as simple
  comma-separated strings.

* The registration system now detects and warns users if given or
  family names are entered all in uppercase.  (This is a warning
  rather than a hard error because of the possibility that in some
  cases the correct orthography is all-uppercase; for example, for a
  single-character name.)  :file:`person.item.html` needs updating to
  make use of this feature.

* The example document-generation template
  :file:`coord-form-template.tex` now handles longer country names.

* New configuration variables ``coord_form_print_logo`` and
  ``coord_form_text_left`` must be specified in
  :file:`documentgen.cfg`.  These can be used to configure the
  template for coordination forms; the example
  :file:`coord-form-template.tex` has been updated to use them
  (settings of ``Yes`` make the template behave the same as in
  previous versions).  In addition, the ``--background`` option to
  :command:`mo-document-generate` can be used to include a background
  design from :file:`coord-form-background.pdf` when generating
  coordination forms; again, the example template has been updated for
  this.

* :file:`person.item.html` has had clarification added that the
  languages to enter for contestants are those in which papers are
  requested.

* Scoreboards now properly use singular rather than plural when
  referring to a single contestant having received a particular award,
  or to a single contestant being registered.

Version 2015.01.0 (4 January 2015)
----------------------------------

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
  relate to some country or person that previously participated, and
  to support automatic reuse of flags and photos from previous years).

* When registering a country, you can specify to reuse a flag from a
  previous year (without needing to download and reupload it
  manually); this reuse is the default option.  This depends on
  ``matholymp_static_site_directory`` pointing to the static site
  data.  The HTML site template :file:`country.item.html` also needs
  updating from the provided examples to make use of this feature.
  Similarly, photos from previous years are reused by default when a
  person is registered (if a URL for previous participation is
  specified), with the same configuration requirement;
  :file:`person.item.html` needs updating to make use of this feature.

* The registration system makes further sanity checks on things done
  by administrative users.

* A bug has been fixed that produced errors when downloading a CSV
  file of scores from the registration system.

* Previously, when a person or country was removed from the
  registration system, although they no longer appeared in the lists
  of registered people or countries, accessing the page for that
  person or country directly via its URL (e.g., if it had been indexed
  by a search engine before the removal) would still show their
  details, with no indication (unless logged in with edit access) that
  the person or country was no longer registered.  Now, accessing the
  page for a removed person or country will give an error instead of
  showing any details for that person or country, unless logged in
  with access to edit that person or country's details.

* When a contact email address was given for a country at registration
  time so that a registration system account could be created
  automatically, that address did not appear in public on the
  registration system page for that country but was unintentionally
  available to the public through the XML-RPC interface to the
  registration system.  Now the registration system properly denies
  access to the contact email address through the XML-RPC interface as
  well as the main web interface.

* The same contact email address can now be specified for multiple
  user accounts (this can be useful, for example, if the person
  registering participants from the host country also has an
  administrative account, or the same person registers participants
  for both a country's main team and its B team).  You may wish to
  update :file:`user.forgotten.html` from the provided examples as the
  example file has been updated to reflect this change.

* Scoreboards now show additional statistical information about
  scores.

Version 2014.09.0 (28 September 2014)
-------------------------------------

* First public release.
