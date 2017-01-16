.. Matholymp todo list.
   Copyright 2017 Joseph Samuel Myers.

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

.. _todo:

Matholymp todo list
===================

The following lists ideas for possible changes and improvements to
matholymp, both internal and user-visible.  Many of these ideas are
speculative, I may have further ideas not written here about how a
change should be implemented and I may not always be sure that a
change would be desirable, so it would be a good idea to discuss
possible changes with me first before implementing ideas listed here.
If you are reading the version of this list in the online
documentation for a release, you should also check the current Git
version for any changes to the list.  See also :ref:`contributing`.

Changes are likely to be a higher priority if they are known to be of
use for a specific event that is using or planning to use matholymp.
Some entries in this list reflect known areas of variation between
different events (so would be necessary or useful if events with that
form of variation from what matholymp currently does were to choose to
adopt it).

General and global changes
--------------------------

* Support coordination timetabling (displaying a timetable showing
  active and pending coordinations; also generating a timetable if
  desired).

* Implement better sorting of roles / contestant codes (numerical
  rather than simply alphabetic) if 10 or more contestants.  (Applies
  to registration system sorting as well as to main
  :py:mod:`matholymp.data` sorting.)

* Handle restricted subsets of possible scores on a problem, where the
  rules of a competition do not allow all scores from 0 to the
  maximum.

* Support awards not algorithmically derived from scores and
  annotations relating to awards.

* Support disqualifications (explicitly showing that there was one
  rather than just removing people and countries).

* Don't hardcode that people have at most two languages (even if
  hardcoded in the registration system, make the underlying data model
  and CSV files use a list of languages instead).

* Support name orders other than given-family.

* Support mononymous people.

* Support multilingual output support rather than just English.

* Avoid Y10K problems (throughout, allow more-than-4-digit years).

* Make all static site and registration system text generated from
  Python code rather than templates more customisable.

* For the static site and registration system, make configurable
  whether to use "the" with country names in prose to avoid generating
  text such as "in United Kingdom".

* Add graphical statistics of results and individual and country
  performance over time.

* Support gender as optionally public information (generally or for
  contestants).

* Allow SVG images of flags and generate PNG automatically for LaTeX
  inclusion.

* Allow for a global configuration file rather than separate files for
  each part of the system; also allow scripts to read multiple
  configuration files (shared and non-shared).

* Add web interfaces for more things currently done on command line.

* Flag staff countries, or non-normal countries (in registration
  system and CSV files) explicitly to avoid hardcoded use of country
  names (in registration system and document generation) other than
  for initial creation.  Likewise flag "None" country (in registration
  system only), or have tristate country type there.

* Don't hardcode ``en_GB`` as locale for collation.

* Add Python 3 support in Sphinx document generation (may work, not
  tested).

* Include Python API documentation in generated documentation.

* Add automated testing for error cases in scripts.

* Consistently pass ids to :py:func:`file_url_to_local` as integers,
  not sometimes integers (document generation) and sometimes strings
  (:command:`mo-static-import`).

* Make capitalization of exception messages consistent.

* Take advantage of missing CSV entries being output as ``''`` by
  Python by default to simplify code.

* Use more specific exception classes rather than :py:exc:`ValueError`
  etc. everywhere.

Static site
-----------

* Allow CSV files to specify event short and long names, and the
  number of contestants for ranking, so those can vary from year to
  year.

* Support not showing the host country / city if always the same.

* Support (in matholymp rather than through hardcoding redirects in
  web server configuration) merging people; removing people (if later
  determined not to have been there, etc.); incomplete scores or names
  information for old events.  E.g., add a ``Redirect Person Numbers``
  column in :file:`people.csv` plus allowing ``Annual URL`` to be a
  comma-separated list, together with :command:`mo-static-upgrade`
  support, tests and documentation.

* Add a general index of all problem papers for all years.

* Support a host country that did not previously take part (e.g., when
  a planned host splits up, or for a completely new event), and
  generally ensure the site looks sensible when there are no past
  events.

* Make :command:`mo-static-import` ignore excess data (e.g., from
  having the full version of :file:`people.csv` instead of the public
  version) rather than giving errors for it.

* Make :command:`mo-static-import` support downloading all data itself
  (including medal boundaries, via xmlrpc or new action), and setting
  medal boundaries and removing ``event_active_number`` from
  :file:`staticsite.cfg`, so just running :command:`mo-static-import`
  with no arguments does everything needed after an event to transfer
  data to the static site.

Registration system
-------------------

* Update the example :file:`config.ini` based on that generated by
  Roundup 1.5.1.

* Support bulk emails (announcements) to registration contacts.

* Add downloadable (given administrative access) full version of
  country list including contact details.

* Extend automatic checks / warnings for all-uppercase names: also
  warn on the registration status page.

* Possibly make :file:`person.item.html` advise people of the
  recommended maximum file size for photos (in human-friendly form
  rather than a raw number of bytes).  File extension and contents
  should also be checked to agree with MIME type.  Apply checks also
  to flags and photos reused from previous years, but quietly don't
  reuse in that case if format and extension mismatch.

* Add more automation for rotating photos server-side.

* Support (staff only?) uploading a photo that appears on name badges
  but not public on the site.

* Add user interface for removing a language, replacing all requests
  for it by requests for a given other language.

* In the registration system, show more past participation information
  rather than just a link.

* Generate automatic suggestions of possible past participation links
  where same name and same country or staff.

* Support for registration contact to view room allocations for their
  country and people sharing rooms with them.

* Support entering accommodation preferences / requests.

* Support other registration information (e.g., passport scan) where
  useful.

* Support for registration contacts to view subset of Registration
  Status information applicable to their countries.

* Use database to describe maximum / expected number of people in a
  given role from a country rather than hardcoding.

* Use database to describe other role properties rather than
  hardcoding based on names (also applies to some other things,
  e.g., document generation).  This includes at least contestant
  number, whether should have phone number, which badge background to
  use.  (Need to pass some information through to CSV files so
  registration status generation can work from those.)

* Use database to describe which arrival points are airports rather
  than hardcoding reference to ``Airport`` text.  (Need to pass
  information through to CSV files so registration status generation
  can work from those.)

* Support for sending emails to registration contacts with reminders
  about missing data, and summaries of present data.

* Add automation for bulk creation of countries in registration system
  from command line.

* Support bulk upload of other registration details.

* Support self-registration accounts (that can register a single
  person in a particular role only, for both staff and normal
  countries, so people can enter some of their own data).

* Ensure all tables in the registration system use ``thead`` and
  ``tbody`` to facilitate uses involving sortable tables.

* Support for not publishing scores until the results are final, or
  for hiding some scores until all are entered or until the results
  are final, for events wanting such restrictions.

* Add more registration system sanity checks against mistakes by
  administrative users (open-ended issue).

* Make all registration system actions verify they are applied only to
  the intended class.

* Verify that arrival date/time are not after departure date/time.

* Support multiple new people being the same person on the static site
  (e.g., same new person as deputy for multiple countries, such as
  host country main and B teams).

* Make more registration system code use the general
  :py:mod:`matholymp.data` interface rather than depending on Roundup
  interfaces, and move to general site generation code
  (:py:mod:`matholymp.regsitegen` module) (facilitates code sharing
  between multiple registration back ends).  Specifically, the
  registration status page.

* Use common :py:func:`file_extension` in
  :py:mod:`matholymp.roundupreg.staticsite` instead of local code for
  filename extensions.

The following ideas are more speculative.

* Make :file:`person.item.html` explicitly say that ``yyyy-mm-dd``
  should be used for dates of birth if not using the calendar widget.

* Reduce the differences between static site and registration system
  CSV files (generally, include more data in registration system
  files, at least once results complete).

* Add more sanity checks for past participation information (not
  allowing multiple countries pointing to same past country, or
  pointing to past staff countries).

* Support Unicode sorting of names in the registration system in more
  cases.  The main ones are done, but this theoretically applies to
  lists of members of many classes that don't go through matholymp
  code.  Also e.g. "plain" versions of ``other_roles`` and
  ``guide_for`` may not have the desired sorting.

* Add RSS feeds of new registered participants and changes to public
  participant details (old versions of changed data maybe shouldn't be
  public, but could still indicate that something has changed or is
  new).

* Add automated testing for registration system code.

* Add Python 3 support in registration system code (not very useful
  until Roundup supports Python 3, and may already be ready for Python
  3 apart from that).

* Make registration system code avoid time-of-check / time-of-use race
  conditions (registering multiple people with the same role from the
  same country at the same time; creating / editing countries to
  duplicate country codes at the same time; entering scores for
  multiple problems for the same country at the same time; conceivably
  others).

* Support having multiple staff countries.

* Support logical role ordering within countries rather than only
  alphabetical.

* Add a public list of country contacts.  Or a private list for future
  hosts, or both with support for different contacts on the two lists.
  Add support for editing contacts that affects future years as well.
  (More generally, add automation for keeping user account passwords
  from year to year.)

* Support separate date/time entry for arrival/departure rather than
  requiring people to put both in the same field in a specified form.

Document generation
-------------------

* Don't hardcode English as a language to give to all leaders.

* Make draft papers say somewhere which draft version they are.

* Add more thorough testing for :command:`mo-document-generate`
  (background and logo PDFs, flags, photos, inclusion of room / phone
  numbers on badges, actual contents of LaTeX files, escaping of names
  and accented characters in documents).

* Add borders round flags on name badges (and website?).
