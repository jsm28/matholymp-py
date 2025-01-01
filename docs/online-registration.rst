.. Documentation of online registration with matholymp.
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

.. _online-registration:

Online registration
===================

Matholymp provides support for an online registration system based on
Roundup.  See the `Roundup installation documentation
<http://roundup-tracker.org/docs/installation.html>`_ for general
information about how to install Roundup (including other Python
packages you may need to install for the database back ends), while
noting that there are some patches (see :ref:`roundup-patches`) it may
be useful to apply before installing Roundup, and that the email
interface is not used.

The online registration system makes limited details of registered
participants public online immediately, and a full online scoreboard
during coordination.  Full details (both public and non-public) of
registered participants can be downloaded when logged in to an
administrative account.

Example files
-------------

Various example files are provided in the
:file:`examples/online-registration/` directory in the matholymp
source distribution.  It is recommended that you copy that directory
to form your Roundup instance directory (the "tracker home"), and then
adapt the files as needed for your event.  Do not use
:command:`roundup-admin install`, since none of the default templates
it can install are being used.

Having copied the examples, you then need to customise the following
files:

* :file:`config.ini` (the comments at the top indicate the settings
  that are most likely to need changing; note in particular the need
  to use :command:`roundup-admin updateconfig` in order to set the
  ``secret_key`` value, followed by merging those comments back into
  the file).

* :file:`extensions/config.ini` (see the comments in the file for
  details of the individual settings; note that some of these settings
  will need updating for each year's event).

* :file:`extensions/email-template-new-user` (a template for emails
  sent automatically to country contacts with details of their
  accounts for registering participants, if a contact email address is
  specified when registering a country; Python formats such as
  ``%(username)s`` in this template are substituted with the relevant
  details of the country and the automatically created account).  The
  example version of this file is written for the case where
  ``matholymp_consent_ui`` is ``Yes``; if it is ``No``, the text about
  collecting information about consent for certain uses of personal
  data should be removed.

* :file:`extensions/email-template-self-reg` (a similar template for
  emails sent automatically to participants registered using the bulk
  registration mechanism, if a contact email address is specified when
  doing so).

* :file:`extensions/email-template-invitation-change` (a similar
  template for emails sent automatically to organisers when personal
  details used in invitation letters are changed after such a letter
  has been generated online).

* :file:`html/page.html` (you may wish to make this file match the
  overall page style used for the static site, although this is not
  required; at least, the stylesheet and shortcut icon URLs will need
  updating, and it should be possible to use the same files for those
  as on the static site).

* :file:`html/dpage.html` (a simplified page style used for a very
  plain version of the scoreboard for projection; this should probably
  not try to match the static site; the `style used for EGMO
  <https://www.egmo.org/egmo-scoredisplay.css>`_ may give useful
  ideas, or indeed be usable more or less as-is.

You may wish to customise other page templates to fine-tune them for
your event (for example, if this is the first event of this kind, to
hide the interface for entering URLs for previous participation by
countries and people), but they should be usable without such changes.

Initialising and running Roundup
--------------------------------

There are many different possible ways to set up and use Roundup
described in the Roundup documentation.  The following approach is
suggested as known to work for matholymp uses, but is not the only
one.

Create a user account and corresponding group for use in running
Roundup (e.g., ``roundup-xmo``).  This user account and group should
own the :file:`db/` directory, but should not own or have write access
to any other files in the Roundup instance.  They should be able to
read all files in the instance.  The ``config.ini`` file should have
its group set to this group, and be group-readable but not
world-readable, because it contains the database password; other files
may be world-readable.

Arrange to run Roundup with the provided :command:`roundup-server`,
running as that user and group, listening on some (fairly arbitrary)
high port on internal interfaces only.  Set up an init script (or
systemd unit file, etc.) to start the server, as the appropriate user
and group, on boot.  This script may usefully call the
:command:`server-ctl` script included in the Roundup source
distribution, or an adapted version thereof.

Set up Apache to provide SSL access (and no unencrypted access, to
avoid issues with logins over unencrypted connections) to the site.
Enable `mod_proxy
<https://httpd.apache.org/docs/current/mod/mod_proxy.html>`_, but only
as a reverse proxy, not as a forward proxy (that is, ``ProxyRequests
Off``).  Set it up to forward requests for appropriate URLs to the
internal server; inside the relevant ``VirtualHost``, put something
like:

.. parsed-literal::

   ProxyPass /registration/*year*/ \http://localhost:*port*/*name*/

where *name* is the instance name passed on the
:command:`roundup-server` command line (:samp:`-p {port}
{name}={instance-directory}`).

Before starting the server for the first time, the database needs to
be initialised.  Ensure the database user named in :file:`config.ini`
exists and has appropriate permissions to create databases.  (You can
remove those permissions after initialisation.)  Then run, as the
Roundup user:

.. parsed-literal::

   roundup-admin -i *instance-directory* initialise

and enter the initial password you wish to use for the ``admin``
user.  Having done this, you can then start the server.

If, after starting the server, you change either of the
:file:`config.ini` files, you need to restart the server for it to
load the new configuration.  This is not needed for changes to the
HTML templates.

Online registration tasks
-------------------------

The following describes how to do various tasks with the online
registration system.  Most can be done with the web interface
(generally requiring to be logged in to an administrative account),
but some require use of :command:`roundup-admin` from the command
line.  All such commands should be run as the user set up for running
Roundup.

Adding and editing miscellaneous items
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can add and edit many kinds of items with an administrative
account (e.g., :guilabel:`Add T-shirt Size`).  In particular, at an
early stage of setup you should use :guilabel:`Add Arrival/Departure
Point` to add details of the places (e.g., airports) where
participants may arrive or depart (one of which is likely to be "Own
travel arrangements" or similar, for local staff not needing airport
transport).  There may also be local roles to add (:guilabel:`Add
Role`).  Initially, both registration of participants and
preregistration (confirming expected numbers of participants and
single room requests) are enabled; if you want to have a period where
only preregistration is possible, you can disable registration before
adding countries and enable it later.
:file:`extensions/email-template-new-user` should be set up to reflect
which of registration and preregistration are enabled.

Extra administrative users can be added, with their roles set to
``Admin``.

Adding countries
^^^^^^^^^^^^^^^^

If it seems likely that participants from the country will want papers
in a language not currently listed in the system, add that language
(:guilabel:`Add Language`).

Countries can be added in bulk, including creating registration system
accounts and sending details of them by email to specified contacts,
by uploading a CSV file (:guilabel:`Bulk register countries`).
Otherwise, countries can be added individually.

Create the country (:guilabel:`Add Country`), including uploading a
(PNG) flag image (if a flag is available from a previous year in the
static site, and ``matholymp_static_site_directory`` in
:file:`extensions/config.ini` points to the static site directory,
that flag will be reused automatically).  If you specify a contact
email address when creating the country, or when subsequently editing
it, a registration system account will be created automatically for
that country and details of it will be sent to that person and the
registration system administrator.  Otherwise, or if more than one
account is needed for a country, you can create a registration system
account manually.  (To do so, create a user account, specifying that
country as its country, choosing a password for that user and
assigning it roles ``User,Register``.  Send details of that user and
password to the appropriate contact for that country; they are only
sent out automatically for users that are created automatically by
specifying a contact email address when creating or editing a
country.)

Once the participating countries have been added, it's appropriate to
link to the registration system from the static site.  Set
``event_active_number`` in :file:`staticsite.cfg`; see
:ref:`static-site` for details.

Registering staff
^^^^^^^^^^^^^^^^^

Staff can be registered, using an administrative account, in the
special country automatically created for them.  This can be done in
bulk, including creating self-registration accounts and sending
details of them by email to specified addresses, by uploading a CSV
file (:guilabel:`Bulk register participants`).  Otherwise, staff can
be registered individually.

Monitoring registration
^^^^^^^^^^^^^^^^^^^^^^^

There is a :guilabel:`Registration Status` link to a page with a
summary of possible issues with the registration data, and it is
useful to keep a watch on this page and to chase up countries that are
late in completing all required information (as well as acting on
points there that do not require information from participating
countries, such as scaling down large photos).

In addition to the points listed on this page, there are some things
you should check manually from time to time.

* If any photos are in the wrong orientation, rotate them and upload
  the rotated version; :command:`jpegtran` can be used to rotate JPEG
  images without uncompressing and recompressing.  (Future versions of
  matholymp may add more automation in this area.)

* If some names are entered with all-uppercase surnames (or entirely
  in uppercase), convert them to mixed case for consistency.  (The
  registration system will show a warning when editing details for a
  person either of whose names is entirely in uppercase.)

* If a person is registered without a link for previous participation,
  check the list of previous participants and add a link if it seems
  that person did in fact participate previously (checking with the
  relevant country if necessary).

* Sometimes a registration for one person may have most of the
  registration details changed so it now refers to another person
  (whether in the same role or a different role).  In such cases, the
  link for previous participation, or its absence, should be checked,
  since it may have been correct for the person previously registered
  but not for the new details.

* If languages chosen seem unlikely for contestants from a given
  country (for example, all contestants from a non-English-speaking
  country requesting only English papers), check the correctness of
  the requested languages with the country in question.

* If there are multiple registrations for the same person in different
  roles for the staff country, add the additional roles to "Other
  roles" for one of those registrations, and remove the other
  registrations.  Likewise, if a person has both staff and non-staff
  roles, all their staff roles should be listed in "Other roles" for
  their non-staff registration; "OK as secondary role for non-staff?"
  needs setting for such roles (which can be edited after finding them
  through :guilabel:`Role List`) if not already set for them.
  
Closing registration
^^^^^^^^^^^^^^^^^^^^

At some point before the event, use :guilabel:`Set medal boundaries or
disable registration` to disable registration (including all changes
by participating countries to registered details of participants), so
that any countries with late changes to participants need to go
through the organisers to ensure the organisers can update logistical
arrangements to handle the changes.  If using preregistration, you can
disable that at some point if desired (and enable registration if
initially disabling it); when disabling registration because late
changes need to go through the organisers, preregistration should be
disabled as well, as the system treats the combination of registration
disabled and preregistration enabled as meaning registration has not
yet started, and displays corresponding messages.  When
preregistration is disabled, countries can still confirm the default
numbers of participants, but not otherwise change the expected
numbers.

Allocating room numbers
^^^^^^^^^^^^^^^^^^^^^^^

If room numbers are entered in the registration system, they can then
go on name badges automatically (including name badges showing the
room number of one's guide and those of other team members).  Room
numbers should be allocated and entered in the registration system
manually (there is no automation for allocating rooms or uploading
room numbers, although if desired the XMLRPC interface to Roundup
could be used for bulk upload of this or other data).  They can be
entered through the :guilabel:`View and edit room allocations` page,
or on the pages for individual people.

Removing people or countries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When logged in administratively, person and country pages have buttons
:guilabel:`Remove this person (requires confirmation)` and
:guilabel:`Remove this country (requires confirmation)`.  Those take
you to a confirmation page; the removal is only effective if you then
click on :guilabel:`Confirm removal of this person` or
:guilabel:`Confirm removal of this country`.

Removing a country this way automatically removes the people from that
country and the registration user from that country, and removes that
country from the "Guide for" list for any guides for that country (but
does not remove the registration of those guides, whether or not they
are also listed as guides for other countries).

If it is necessary to restore a person or country after removal,
:command:`roundup-admin restore` can be used.  When restoring a
country, note the need to restore each person from that country, the
registration user for that country, and any guides for that country,
individually.

Removing a photo
^^^^^^^^^^^^^^^^

If, after a photo is uploaded to the registration system, the person
concerned objects to it being there, it can be removed with:

.. parsed-literal::

   roundup-admin -i *instance-directory* set personN files=

A photo is no longer available over the web to the public when it is
no longer the current photo uploaded for that person.

Scoring
^^^^^^^

Score can be entered (:guilabel:`Enter scores`) with an administrative
account, or one with roles ``User,Score``.  Before scores can be
entered, registration must have been closed by an administrative
account.

An administrative account can enter medal boundaries (:guilabel:`Set
medal boundaries or disable registration`).

During the event
^^^^^^^^^^^^^^^^

At some point during the event you should determine if any registered
people have not turned up.  If so, remove them as described above so
that records for them are not transferred to the static site after the
event.

If someone requests a change to the selected languages for exams,
ensure that the change is made in the registration system and that an
updated version of the data about people is downloaded for use in
generating papers.  If someone indicates that their registered name
should be corrected, again, make that change online so that it is
reflected in the final data transferred to the static site.

At appropriate points during the event, add papers to the static site,
and then add the final results to the static site.  See
:ref:`static-site` for detailed instructions.

After the final results have been added to the static site, when
non-public registration data is no longer needed you can set up the
redirects from registration system URLs to the static site (see
:ref:`static-site`), and shut down the Roundup server.  After an
appropriate lapse of time for safety, if you are satisfied all the
public data is correctly on the static site you can then delete the
database from the database server, and the contents of the :file:`db/`
directory.

Displaying scores
^^^^^^^^^^^^^^^^^

A very plain version of the scoreboard that displays multiple
countries on a page (the number of rows and columns being configurable
in :file:`extensions/config.ini`) and automatically rotates through
all countries is available for showing on screens or projecting at the
olympiad site.  The system driving the display should run a
(full-screen) browser pointed to the page
``person?@template=scoredisplay`` within the registration system.
This browser does not need to be logged in; as with the main
scoreboard, the display version is public (although it is not linked
to from other pages, given the limited use of it).
