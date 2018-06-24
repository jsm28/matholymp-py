.. Matholymp release notes.
   Copyright 2014-2018 Joseph Samuel Myers.

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

Because of changes to how data is represented in the registration
system, upgrades to this version can only be made between events when
the registration system is not active.

* A bug has been fixed in :command:`mo-static-import` where it would
  download an incorrect file as the RSS feed of scores when
  downloading files automatically from the registration system.

* A bug has been fixed that caused the static site to have incorrect
  descriptions of the dates as of which ages are given for contestants
  who competed in years all of which had the same such description but
  for which that description was not the one in
  :file:`staticsite.cfg`.

* Changes have been made to how uploaded flags and photos are handled
  in the registration system, which involve updates to
  :file:`country.item.html` and :file:`person.item.html`.  New files
  :file:`consent_form.index.html`, :file:`consent_form.item.html`,
  :file:`flag.index.html`, :file:`flag.item.html`,
  :file:`photo.index.html` and :file:`photo.item.html` are added, and
  :file:`file.index.html`, :file:`file.item.html`,
  :file:`private_file.index.html` and :file:`private_file.item.html`
  are removed.

* As part of cleanups to Python coding style, the example Python files
  for the registration system have been changed.

Version 2018.02.0 (11 February 2018)
------------------------------------

Because of changes to how data is represented in the registration
system, upgrades to this version can only be made between events when
the registration system is not active.

* Static site generation now supports different events having
  different descriptions of the day for which contestant ages are
  given.  If the CSV file of events has a column ``Age Day
  Description``, the text from that column will be used instead of
  ``age_day_desc`` from :file:`staticsite.cfg`.

* :command:`mo-static-import` can now work directly with the ZIP files
  of flags and photos from the registration system, instead of
  requiring you to unpack them manually, and can automatically
  download from the registration system any files not present in the
  directory specified.

* :command:`mo-static-import` now sets ``event_active_number`` to
  empty in :file:`staticsite.cfg` if it was previously set to the
  number of the event for which data is being imported.

* The registration system now allows entering phone numbers for all
  staff, not just Guides.  Document generation will only use this
  information in the case of Guides, but it may sometimes be useful
  for other staff for other administrative purposes.
  :file:`person.item.html` is updated accordingly.

* The registration system now supports requiring allergies and dietary
  requirements information to be specified explicitly, possibly as
  ``None``, rather than left blank.  The new configuration variable
  ``matholymp_require_diet`` must be specified in
  :file:`extensions/config.ini` for the registration system.  If
  ``Yes``, this information is required for all people at
  registration.  If ``No``, that field can be left blank at
  registration, as before.  :file:`person.item.html` is updated
  accordingly.

* The registration system now supports editing rooms for many people
  from a single page.  The example :file:`page.html` is updated
  accordingly, and a new :file:`person.rooms.html` is added.

* :command:`mo-static-generate` no longer writes output files if their
  contents would be unchanged, to support dependency-based
  postprocessing of its output.

* The registration system now supports a configurable number of
  languages being registered for each participant, rather than the
  previous hardcoded two languages.  The new configuration variable
  ``matholymp_num_languages`` must be specified in
  :file:`extensions/config.ini` for the registration system.
  :file:`person.item.html` is updated accordingly.  The first language
  must be specified; the others are optional.  Labels for contestant
  desks only list at most two languages.

* Information about which arrival / departure points are airports (and
  so should have flight numbers entered when registering participants)
  is now entered and stored explicitly in the registration system,
  rather than being based on whether the name contains ``Airport``.
  :file:`arrival.index.html` and :file:`arrival.item.html` are updated
  accordingly.

* Which staff roles are allowed to be Guides for countries is now
  configured through the registration system database, rather than
  being hardcoded as only the ``Guide`` role.  The default is only the
  ``Guide`` role, but other roles may be edited to allow them to guide
  countries (if, for example, a Deputy Chief Guide is also guiding a
  country).  :file:`matholymprole.index.html` and
  :file:`matholymprole.item.html` are updated accordingly.

* The example :file:`country.index.html` and :file:`person.index.html`
  for the registration system no longer link to ZIP files of flags and
  photos, so matching the lists in the static site which does not have
  such ZIP files, unless logged in administratively.

Version 2017.05.0 (1 May 2017)
------------------------------

Because of changes to how data is represented in the registration
system, upgrades to this version can only be made between events when
the registration system is not active.

* The registration system now supports collecting nationality
  information for participants.  The new configuration variable
  ``matholymp_require_nationality`` must be specified in
  :file:`extensions/config.ini` for the registration system.  If
  ``Yes``, this information is collected and is required for all
  participants.  If ``No``, this information is not collected.
  :file:`person.item.html` is updated accordingly.

* The registration system now caches the generated scoreboard to avoid
  high system load when many people are accessing it simultaneously
  while coordination is going on.  The templates
  :file:`person.scoreboard.html` and :file:`person.scoredisplay.html`
  are updated accordingly.  This functionality only works on a
  Unix-like operating system; on other systems, the online scoreboard
  will still be regenerated every time it is accessed.

* The registration system now supports scaling down excessively large
  photos uploaded when registering participants.  To support this
  feature, matholymp now requires the `Pillow
  <https://python-pillow.org/>`_ library if the registration system is
  used.  The new configuration variables ``matholymp_photo_max_size``
  and ``matholymp_photo_min_dimen`` must be specified in
  :file:`extensions/config.ini` for the registration system.  The
  registration status page shows a list of people with large photos
  and provides the option to scale down those photos.

* The registration system now applies the sanity check that dates of
  birth are not too recent to all participants with a date of birth
  registered rather than just to contestants.  The example
  :file:`extensions/config.ini` is updated accordingly (change to the
  comment on ``matholymp_sanity_date_of_birth`` only).

* The registration system configuration variable
  ``matholymp_require_contestants_female`` is replaced by a variable
  ``matholymp_contestant_genders`` with a comma-separated list of
  genders allowed for contestants.  If empty, all genders are allowed,
  which is equivalent to a value of ``Female, Male, Non-binary`` with
  the default set of genders.

* The registration system now detects and gives errors for more cases
  of accessing invalid URLs instead of treating them as equivalent to
  other valid URLs.

* The full version of the CSV file of person details now lists
  languages in a single ``Languages`` column (which contains a
  comma-separated list interpreted as if it were the single row of a
  CSV file) instead of separate columns for first and second
  languages.  At most two languages can be requested at registration,
  but this change allows papers in more than two languages to be
  generated for a contestant in special circumstances by editing the
  CSV file before generating the papers.  Labels for contestant desks
  only list at most two languages.

* Registration system users with ordinary accounts for registering
  participants from their own country can now see a registration
  status page with information about missing registration information
  from their country.  The example :file:`page.html` and
  :file:`person.status.html` are updated accordingly.

* The example :file:`badge-template.tex` is updated to reflect that
  allergies information is collected together with dietary
  requirements.

* Static site generation now supports having a different form of a
  host country's name that appears after "in", for names requiring
  "the" in that context.  A ``Country Name In`` column is added to the
  CSV file of events for that purpose.

* It is now possible to have multiple staff countries in the
  registration system (e.g., to separate different kinds of staff),
  although exactly one staff country is created automatically.  The
  example :file:`country.item.html` is updated for this change.  CSV
  files listing countries now explicitly track whether a country is a
  normal or staff country.

* The online scoreboard now indicates the maximum score a contestant
  or country could achieve when only partial scores for that
  contestant or country have been entered, and shows a contestant's or
  country's total score, or a country's total score on a problem, as a
  blank rather than zero if no scores for that contestant or country,
  or for that country on that problem, have been entered.

* In the registration system, dates of birth now use separate
  drop-down menus for day, month and year, instead of needing to be
  entered as text in a particular format or using a pop-up not
  designed for dates far in the past.  :file:`person.item.html` is
  updated accordingly.

* In the registration system, arrival and departure times now use
  separate drop-down menus for date (restricted to dates within the
  permitted range), hour and minute, instead of needing to be entered
  as text in a particular format or using a pop-up calendar.
  :file:`person.item.html` is updated accordingly.  The full version
  of the CSV file of person details now lists the arrival and
  departure dates separately from the arrival and departure times.
  Arrivals and departures after midnight at the start of the
  configured latest arrival and departure dates are now allowed as
  intended.  The :file:`extensions/config.ini` configuration variable
  ``matholymp_date_template`` is no longer used and is removed from
  the example file.

* The registration system now gives an error if a person is registered
  as departing before they arrive.

Version 2017.01.0 (8 January 2017)
----------------------------------

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
  to be uploaded.  If this feature is used, the configuration variable
  ``matholymp_consent_forms_url`` must also be set, to the URL of the
  blank consent form.  :file:`person.item.html` and
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

* The registration system now supports collecting passport or identity
  card numbers for participants.  The new configuration variable
  ``matholymp_require_passport_number`` must be specified in
  :file:`extensions/config.ini` for the registration system.  If
  ``Yes``, this information is collected and is required for all
  participants.  If ``No``, this information is not collected.
  :file:`person.item.html` is updated accordingly.

* My list of ideas for possible future improvements to matholymp is
  now included in the documentation.  See :ref:`todo`.

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
