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

When upgrading matholymp, you should run the
:command:`mo-static-upgrade` script from the directory containing the
static site, to update the CSV data files with details of past events
for any format changes in the new version of matholymp.  After doing
so, run :command:`mo-static-generate`.

Next version (unreleased)
-------------------------

* The ZIP files of flags and photos that can be downloaded from the
  registration system now have their contents arranged by the
  registration system identifier for the country or person, not by
  that for the file itself.

* The registration system now supports uploading consent forms for
  participants, where the host country requires this for participants
  under a certain age. The new configuration variable
  ``matholymp_consent_forms_date`` must be specified in
  :file:`extensions/config.ini` for the registration system.  If
  empty, consent forms are disabled; otherwise, it must be a date such
  that participants born on or after that date require consent forms
  to be uploaded.  :file:`person.item.html` and
  :file:`person.index.html` are updated to support this feature (but
  local changes may be needed to point people to an appropriate blank
  consent form to fill in), and new templates
  :file:`private_file.item.html` and :file:`private_file.index.html`
  are added.

* The registration system templates :file:`user.item.html` and
  :file:`country.item.html` are updated to clarify the effects of
  editing email addresses entered in the registration system.

* The registration system template :file:`person.item.html` now
  collects information "Allergies and dietary requirements" rather
  than simply "Dietary requirements".  The CSV file column is renamed
  accordingly.

* The registration system now supports requiring a date of birth to be
  specified for all participants rather than just for contestants.
  The new configuration variable ``matholymp_require_date_of_birth``
  must be specified in :file:`extensions/config.ini` for the
  registration system (as ``Yes`` or ``No``).
  :file:`person.item.html` is updated accordingly.

Version 2016.05.0 (1 May 2016)
------------------------------

* Static site generation now supports a person with roles for more
  than one country at an event.  (This is only intended for cases
  where someone has a role, such as Leader or Deputy Leader, for more
  than one non-staff country, such as A and B teams for the host
  country.  If someone has both non-staff and staff roles, such as
  being both a Leader and on the organising committee, this should be
  represented by listing other roles under the non-staff
  participation.)  In the registration system, this should be
  represented by separately registered entries for each country, with
  the same URL for past participation listed; it is not currently
  possible to register a new participant this way without multiple
  records being created for them by :command:`mo-static-import`.

* When papers are generated with :command:`mo-document-generate`, the
  directory with papers received from leaders may contain only the
  LaTeX sources of a paper without a corresponding PDF version, in
  which case the PDF version is generated automatically with
  :command:`pdflatex`.  (If both PDF and LaTeX versions are present,
  the PDF version will be used, as before.)

* :command:`mo-document-generate` can now be used with arguments
  ``paper new-drafts`` to generate draft papers to display only for
  translations that are new or modified since the previous call with
  those arguments.  Previously the user needed to keep track of which
  new or revised papers needed drafts generating.

* The registration system code and associated Roundup patches have
  been updated for Roundup 1.5.1.  Because of Roundup API changes, the
  code will no longer work with older Roundup versions.

* The registration system now checks that flags are uploaded in PNG
  format, and that photos are uploaded in JPEG or PNG format, and that
  the filename extension for such uploaded files matches the format of
  the contents of the files.  :file:`country.item.html` and
  :file:`person.item.html` are updated to mention these requirements.
  (These checks are not applied to flags or photos automatically
  reused from previous years.)

* The numbers of rows and columns on each page of the display
  scoreboard are now configurable instead of being hardcoded as 2.
  The new configuration variables
  ``matholymp_display_scoreboard_rows`` and
  ``matholymp_display_scoreboard_columns`` must be specified in
  :file:`extensions/config.ini` for the registration system.

* If a person is registered with "Other roles" including their main
  role, that duplicate entry will be automatically excluded when
  generating the CSV file of person details, and so when the final
  registration data are transferred to the static site.

Version 2016.01.0 (2 January 2016)
----------------------------------

* Generated statistics now refer to the number of participating teams,
  not countries, at an event, reflecting that what is counted is not
  countries in the matholymp sense (including the special staff
  country and any countries sending only observers), nor in the sense
  of common usage (B teams are included, but countries sending only
  observers are excluded), but those sending nonempty teams.  This
  includes changes to the CSV column headers in generated CSV files
  (though not in those that serve as inputs to
  :command:`mo-static-generate`).

* The :command:`mo-static-import` script no longer takes an argument
  specifying the number of the event for which data is to be imported;
  instead, this is determined automatically from the data imported.

* :command:`mo-static-import` has an additional sanity check that data
  is not already present in the static site for countries or people at
  the event for which data is being imported.

* When scores are incomplete, the live scoreboard's cumulative
  statistics on scores show the maximum number of contestants who
  might have at least a given score after their scores are complete,
  as well as the number who have at least that score based on the
  scores entered so far.

* The default set of choices for gender in the registration system now
  includes "Other".

* :file:`country.item.html` no longer refers to accounts being created
  automatically only if the specified email address is not used by any
  other country.  (That restriction was removed in version 2015.01.0.)

* When the registration system is initialised, if
  ``matholymp_initial_languages`` in :file:`extensions/config.ini`
  includes the special language name ``PREVIOUS``, then all languages
  of papers at previous events will automatically be added to the
  registration system; this requires
  ``matholymp_static_site_directory`` to point to the static site data
  for previous events.  To exclude some previous languages while
  including others automatically, languages starting with ``-`` may be
  listed after ``PREVIOUS`` (for example, ``PREVIOUS, -Latin``).

Version 2015.04.0 (5 April 2015)
--------------------------------

* There is a new script :command:`mo-static-upgrade` that should be
  run from the directory containing the static site when upgrading
  matholymp.

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

* Special prizes are now supported.  :file:`person.item.html` needs
  updating to make use of this feature in the registration system.

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
