# RegSiteGenerator class for matholymp package.

# Copyright 2014-2017 Joseph Samuel Myers.

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see
# <https://www.gnu.org/licenses/>.

# Additional permission under GNU GPL version 3 section 7:

# If you modify this program, or any covered work, by linking or
# combining it with the OpenSSL project's OpenSSL library (or a
# modified version of that library), containing parts covered by the
# terms of the OpenSSL or SSLeay licenses, the licensors of this
# program grant you additional permission to convey the resulting
# work.  Corresponding Source for a non-source form of such a
# combination shall include the source code for the parts of OpenSSL
# used as well as that of the covered work.

"""
This module provides the RegSiteGenerator class that generates web
content from within the registration system.
"""

__all__ = ['RegSiteGenerator']

import cgi
import io
import os
import zipfile

from matholymp.data import EventGroup
from matholymp.fileutil import write_utf8_csv_bytes, file_extension
from matholymp.sitegen import SiteGenerator

class RegSiteGenerator(SiteGenerator):

    """
    A RegSiteGenerator supports web content generation from within the
    registration system.
    """

    def __init__(self, cfg, event_group):
        """
        Initialise a RegSiteGenerator from the given configuration and
        EventGroup object.
        """
        self.event = event_group.event_list[0]
        """The unique event described by the registration system instance."""
        super(RegSiteGenerator, self).__init__(cfg, event_group)

    def countries_csv_bytes(self):
        """Return the byte contents of the CSV of countries."""
        data = self.one_event_countries_csv_content(self.event,
                                                    reg_system=True)
        return write_utf8_csv_bytes(data[0], data[1])

    def scores_csv_bytes(self):
        """Return the byte contents of the CSV of scores."""
        data = self.one_event_scores_csv_content(self.event, reg_system=True)
        return write_utf8_csv_bytes(data[0], data[1])

    def people_csv_bytes(self, private_data):
        """Return the byte contents of the CSV of people."""
        data = self.one_event_people_csv_content(self.event, reg_system=True,
                                                 private_data=private_data)
        return write_utf8_csv_bytes(data[0], data[1])

    def flags_zip_bytes(self):
        """Return the byte contents of the ZIP of flags."""
        output = io.BytesIO()
        zip = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
        zip.writestr('flags/README.txt',
                     'The flags in this file are arranged by internal'
                     ' database identifier\nfor the country.\n')

        e = self.event
        country_list = sorted(e.country_list, key=lambda x:x.sort_key)
        for c in country_list:
            url = c.flag_url
            if url is not None:
                ext = file_extension(url)
                filename = c.flag_filename
                zip_filename = 'flags/country%d/flag.%s' % (c.country.id, ext)
                zip.write(filename, zip_filename)

        zip.close()
        zip_bytes = output.getvalue()
        output.close()
        return zip_bytes

    def photos_zip_bytes(self):
        """Return the byte contents of the ZIP of photos."""
        output = io.BytesIO()
        zip = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
        zip.writestr('photos/README.txt',
                     'The photos in this file are arranged by internal'
                     ' database identifier\nfor the person.\n')

        e = self.event
        person_list = sorted(e.person_list, key=lambda x:x.sort_key)
        for p in person_list:
            url = p.photo_url
            if url is not None:
                ext = file_extension(url)
                filename = p.photo_filename
                zip_filename = 'photos/person%d/photo.%s' % (p.person.id, ext)
                zip.write(filename, zip_filename)

        zip.close()
        zip_bytes = output.getvalue()
        output.close()
        return zip_bytes

    def consent_forms_zip_bytes(self):
        """Return the byte contents of the ZIP of consent_forms."""
        output = io.BytesIO()
        zip = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
        zip.writestr('consent-forms/README.txt',
                     'The consent forms in this file are arranged by internal'
                     ' database identifier\nfor the person.\n')

        e = self.event
        person_list = sorted(e.person_list, key=lambda x:x.sort_key)
        for p in person_list:
            url = p.consent_form_url
            if url is not None:
                ext = file_extension(url)
                filename = p.consent_form_filename
                zip_filename = ('consent-forms/person%d/consent-form.%s' %
                                (p.person.id, ext))
                zip.write(filename, zip_filename)

        zip.close()
        zip_bytes = output.getvalue()
        output.close()
        return zip_bytes

    def display_scoreboard_text(self, e, display_start):
        """
        Return the text of one page of the display scoreboard for one
        event.
        """
        text = ''
        countries = sorted(e.country_with_contestants_list,
                           key=lambda x:x.sort_key)
        rows = self._cfg['display_scoreboard_rows']
        cols = self._cfg['display_scoreboard_columns']
        cell_width = 'width:%d%%' % (100 // cols)
        per_screen = rows * cols
        num_screens = (len(countries) + per_screen - 1) // per_screen
        if num_screens < 1:
            num_screens = 1
        display_start = display_start % num_screens
        start_idx = display_start * per_screen
        end_idx = (display_start + 1) * per_screen
        ctext_list = []
        for i in range(start_idx, end_idx):
            head_row_list = [self.person_scoreboard_header(e, show_rank=False,
                                                           show_name=False,
                                                           show_award=False)]
            ctext = ''
            if i < len(countries):
                contestants = sorted(countries[i].contestant_list,
                                     key=lambda x:x.sort_key)
                body_row_list = []
                for p in contestants:
                    body_row_list.append(
                        self.person_scoreboard_row(p,
                                                   show_rank=False,
                                                   show_name=False,
                                                   show_award=False,
                                                   link=False))
                ctext += self.html_table_thead_tbody_list(head_row_list,
                                                          body_row_list)
            ctext_list.append(ctext)
        row_list = []
        for i in range(rows):
            col_list = []
            for j in range(cols):
                td_text = self.html_td(ctext_list[i * cols + j],
                                       class_=self._cfg['outer_scores_css'],
                                       style=cell_width)
                col_list.append(td_text)
            row_list.append(self.html_tr_list(col_list))
        text += self.html_table('\n'.join(row_list), style='width:100%')
        if e.scores_final:
            text += ('<p>Medal boundaries: Gold %d, Silver %d,'
                     ' Bronze %d.</p>\n' %
                     (e.gold_boundary, e.silver_boundary, e.bronze_boundary))
        return text

    def missing_person_details(self, p, consent_forms_date):
        """Return a description of missing details for a person."""

        missing_list = []

        if consent_forms_date is not None and p.consent_form_url is None:
            if p.date_of_birth is not None:
                if p.date_of_birth >= consent_forms_date:
                    missing_list.append('consent form')

        if p.photo_url is None:
            missing_list.append('photo')

        have_travel_details = True
        if p.arrival_place is None or p.arrival_time is None:
            have_travel_details = False
        elif p.departure_place is None or p.departure_time is None:
            have_travel_details = False
        else:
            if 'Airport' in p.arrival_place:
                if p.arrival_flight is None:
                    have_travel_details = False
            if 'Airport' in p.departure_place:
                if p.departure_flight is None:
                    have_travel_details = False
        if not have_travel_details:
            missing_list.append('travel details')

        if p.primary_role == 'Guide' and p.phone_number is None:
            missing_list.append('phone number')

        return missing_list

    def missing_roles_text(self, c, expected_roles):
        """Return a description of people not registered for a country."""
        person_list = c.person_list
        if not person_list:
            return ('<p>No participants registered from'
                    ' <strong>%s</strong>.</p>\n' %
                    cgi.escape(c.name_with_code))
        else:
            have_roles = [p.primary_role for p in person_list]
            missing_roles = [r for r in expected_roles
                             if not r in have_roles]
            if missing_roles:
                return ('<p>Not registered from <strong>%s</strong>:'
                        ' %s.</p>\n' %
                        (cgi.escape(c.name_with_code),
                         cgi.escape(', '.join(missing_roles))))
            else:
                return ''

    def missing_person_details_text(self, people, consent_forms_date,
                                    show_country):
        """Return a table of missing details for people."""
        text = ''
        if show_country:
            cols = ['Country']
        else:
            cols = []
        cols.extend(['Person', 'Missing data'])
        head_row_list = [self.html_tr_th_list(cols)]
        body_row_list = []
        missing_photo = False
        missing_phone = False
        for p in people:
            p_needed = self.missing_person_details(p, consent_forms_date)
            if p_needed:
                if 'photo' in p_needed:
                    missing_photo = True
                if 'phone number' in p_needed:
                    missing_phone = True
                if show_country:
                    row = [cgi.escape(p.country.name_with_code)]
                else:
                    row = []
                row.extend([self.link_for_person(p.person, cgi.escape(p.name)),
                            ', '.join(p_needed)])
                body_row_list.append(self.html_tr_td_list(row))
        if body_row_list:
            text += self.html_table_thead_tbody_list(head_row_list,
                                                     body_row_list) + '\n'
        if missing_photo:
            text += ('<p>Photos are optional but recommended; they appear'
                     ' on the website and may appear on name badges.</p>\n')
        if missing_phone:
            text += ('<p>Phone numbers (for Guides) need only be entered'
                     ' if they will appear on name badges.</p>\n')
        return text

    def photo_scale_form(self, p):
        """Return a form to scale down a person's photo."""
        raise NotImplementedError

    def registration_status_text(self, expected_roles, consent_forms_date,
                                 max_photo_size):
        """Return the text of the registration status page."""
        e = self.event
        normal_countries = sorted(e.normal_country_list,
                                  key=lambda x:x.sort_key)
        staff_countries = sorted(e.staff_country_list, key=lambda x:x.sort_key)
        people = sorted(e.person_list, key=lambda x:x.sort_key)
        normal_people = sorted(e.normal_person_list, key=lambda x:x.sort_key)
        staff = sorted(e.staff_list, key=lambda x:x.sort_key)
        text = ''

        text += '<h2>Action needed by participating countries</h2>\n'

        for c in normal_countries:
            text += self.missing_roles_text(c, expected_roles)
        text += ('<p>Some countries may intend to send Observers'
                 ' but not have registered them all.</p>\n')

        text += self.missing_person_details_text(normal_people,
                                                 consent_forms_date, True)

        text += '<h2>Action needed by the organisers</h2>\n'

        for c in normal_countries:
            if not c.guide_list:
                text += ('<p>No guide registered for'
                         ' <strong>%s</strong>.</p>\n' %
                         cgi.escape(c.name_with_code))
        text += ('<p>The system cannot tell automatically if not all'
                 ' staff have been registered.</p>\n')

        text += self.missing_person_details_text(staff, consent_forms_date,
                                                 False)

        head_row_list = [self.html_tr_th_list(['Country', 'Person', 'Role'])]
        body_row_list = []
        for p in people:
            if p.room_number is None:
                row = [cgi.escape(p.country.name_with_code),
                       self.link_for_person(p.person, cgi.escape(p.name)),
                       cgi.escape(p.primary_role)]
                body_row_list.append(self.html_tr_td_list(row))
        if body_row_list:
            text += '<h2>Room allocations needed</h2>\n'
            text += ('<p>Room numbers need only be entered if they will'
                     ' appear on name badges, or if the organisers find'
                     ' it useful for other purposes to have that information'
                     ' here.  For staff using their own accommodation,'
                     ' enter &lsquo;Own accommodation&rsquo;,'
                     ' or a more precise location for any Guides'
                     ' (whose room numbers will appear on badges of'
                     ' their team members).</p>\n')
            text += self.html_table_thead_tbody_list(head_row_list,
                                                     body_row_list) + '\n'

        head_row_list = [self.html_tr_th_list(['Country', 'Person', 'File size',
                                               'Scale down'])]
        body_row_list = []
        for p in people:
            filename = p.photo_filename
            if filename is not None:
                photo_size = os.stat(filename).st_size
                if photo_size > max_photo_size:
                    row = [cgi.escape(p.country.name_with_code),
                           self.link_for_person(p.person, cgi.escape(p.name)),
                           str(photo_size),
                           self.photo_scale_form(p.person)]
                    body_row_list.append(self.html_tr_td_list(row))
        if body_row_list:
            text += '<h2>Photos with large file size</h2>\n'
            text += ('<p>These participants have photos that are over '
                     '%d bytes in size.  Although not strictly required, '
                     'scaling them down will make the site quicker for users '
                     'and may also speed up printing name badges.</p>\n' %
                     max_photo_size)
            text += self.html_table_thead_tbody_list(head_row_list,
                                                     body_row_list) + '\n'

        flags_needed = ''
        for c in normal_countries:
            if not c.flag_url:
                flags_needed += ('<p>No flag for <strong>%s</strong>.</p>\n' %
                                 cgi.escape(c.name_with_code))
        if flags_needed:
            text += ('<h2>Action needed by registration system'
                     ' maintainers</h2>\n')
            text += flags_needed

        return text

    def registration_status_country_text(self, country, expected_roles,
                                         consent_forms_date):
        """Return the text of the registration status page for one country."""
        people = sorted(country.person_list, key=lambda x:x.sort_key)
        text = ''
        text += self.missing_roles_text(country, expected_roles)
        text += ('<p>The system cannot tell automatically if there are any'
                 ' Observers you have not yet registered.</p>\n')

        text += self.missing_person_details_text(people, consent_forms_date,
                                                 False)

        return text
