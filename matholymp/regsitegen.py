# RegSiteGenerator class for matholymp package.

# Copyright 2014-2019 Joseph Samuel Myers.

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

import collections
import html
import io
import os
import zipfile

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

    def countries_csv_bytes(self, private_data):
        """Return the byte contents of the CSV of countries."""
        data = self.one_event_countries_csv_content(self.event,
                                                    reg_system=True,
                                                    private_data=private_data)
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

    def medal_boundaries_csv_bytes(self):
        """Return the byte contents of the CSV of medal boundaries."""
        csv_out = {}
        e = self.event
        csv_out['Gold Boundary'] = \
            str(e.gold_boundary) if e.gold_boundary is not None else ''
        csv_out['Silver Boundary'] = \
            str(e.silver_boundary) if e.silver_boundary is not None else ''
        csv_out['Bronze Boundary'] = \
            str(e.bronze_boundary) if e.bronze_boundary is not None else ''
        columns = ['Gold Boundary', 'Silver Boundary', 'Bronze Boundary']
        return write_utf8_csv_bytes([csv_out], columns)

    def flags_zip_bytes(self):
        """Return the byte contents of the ZIP of flags."""
        output = io.BytesIO()
        zip_file = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
        zip_file.writestr('flags/README.txt',
                          'The flags in this file are arranged by internal'
                          ' database identifier\nfor the country.\n')

        e = self.event
        country_list = sorted(e.country_list, key=lambda x: x.sort_key)
        for c in country_list:
            url = c.flag_url
            if url is not None:
                ext = file_extension(url)
                filename = c.flag_filename
                zip_filename = 'flags/country%d/flag.%s' % (c.country.id, ext)
                zip_file.write(filename, zip_filename)

        zip_file.close()
        zip_bytes = output.getvalue()
        output.close()
        return zip_bytes

    def photos_zip_bytes(self, for_badges):
        """Return the byte contents of the ZIP of photos."""
        output = io.BytesIO()
        zip_file = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
        zip_file.writestr('photos/README.txt',
                          'The photos in this file are arranged by internal'
                          ' database identifier\nfor the person.\n')

        e = self.event
        person_list = sorted(e.person_list, key=lambda x: x.sort_key)
        for p in person_list:
            url = p.badge_photo_url if for_badges else p.photo_url
            if url is not None:
                ext = file_extension(url)
                filename = (p.badge_photo_filename
                            if for_badges
                            else p.photo_filename)
                zip_filename = 'photos/person%d/photo.%s' % (p.person.id, ext)
                zip_file.write(filename, zip_filename)

        zip_file.close()
        zip_bytes = output.getvalue()
        output.close()
        return zip_bytes

    def consent_forms_zip_bytes(self):
        """Return the byte contents of the ZIP of consent_forms."""
        output = io.BytesIO()
        zip_file = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
        zip_file.writestr('consent-forms/README.txt',
                          'The consent forms in this file are arranged by'
                          ' internal database identifier\nfor the person.\n')

        e = self.event
        person_list = sorted(e.person_list, key=lambda x: x.sort_key)
        for p in person_list:
            url = p.consent_form_url
            if url is not None:
                ext = file_extension(url)
                filename = p.consent_form_filename
                zip_filename = ('consent-forms/person%d/consent-form.%s'
                                % (p.person.id, ext))
                zip_file.write(filename, zip_filename)

        zip_file.close()
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
                           key=lambda x: x.sort_key)
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
                                     key=lambda x: x.sort_key)
                body_row_list = []
                for p in contestants:
                    body_row_list.append(
                        self.person_scoreboard_row(p,
                                                   show_rank=False,
                                                   show_name=False,
                                                   show_range=False,
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
                     ' Bronze %d.</p>\n'
                     % (e.gold_boundary, e.silver_boundary, e.bronze_boundary))
        return text

    def missing_person_details(self, p, consent_forms_date):
        """Return a description of missing details for a person."""

        missing_list = []

        if p.basic_data_missing:
            missing_list.append('basic data')

        if consent_forms_date is not None and p.consent_form_url is None:
            if p.date_of_birth is not None:
                if p.date_of_birth >= consent_forms_date:
                    missing_list.append('consent form')

        if p.badge_photo_url is None:
            missing_list.append('photo')

        have_travel_details = True
        if (p.arrival_place is None
            or p.arrival_date is None
            or p.arrival_time is None):
            have_travel_details = False
        elif (p.departure_place is None
              or p.departure_date is None
              or p.departure_time is None):
            have_travel_details = False
        else:
            if p.arrival_is_airport:
                if p.arrival_flight is None:
                    have_travel_details = False
            if p.departure_is_airport:
                if p.departure_flight is None:
                    have_travel_details = False
        if not have_travel_details:
            missing_list.append('travel details')

        if p.guide_for and p.phone_number is None:
            missing_list.append('phone number')

        return missing_list

    def missing_roles_text(self, c):
        """Return a description of people not registered for a country."""
        if c.expected_numbers_confirmed:
            ret_text = ''
        else:
            ret_text = ('<p>Expected numbers of participants and single '
                        'room requests not yet confirmed for '
                        '<strong>%s</strong>.</p>\n'
                        % html.escape(c.name_with_code))
        expected_roles = c.expected_roles
        person_list = c.person_list
        if not person_list:
            ret_text += ('<p>No participants registered from'
                         ' <strong>%s</strong>.</p>\n'
                         % html.escape(c.name_with_code))
        else:
            have_roles = collections.defaultdict(int)
            for p in person_list:
                have_roles[p.primary_role] += 1
            missing_roles = []
            for role in sorted(expected_roles.keys()):
                missing = expected_roles[role] - have_roles[role]
                if missing > 0:
                    if missing > 1:
                        missing_roles.append('%s (x%d)' % (role, missing))
                    else:
                        missing_roles.append(role)
            if missing_roles:
                ret_text += ('<p>Not registered from <strong>%s</strong>:'
                             ' %s.</p>\n'
                             % (html.escape(c.name_with_code),
                                html.escape(', '.join(missing_roles))))
        return ret_text

    def missing_person_details_text(self, people, consent_forms_date,
                                    have_consent_ui, show_country):
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
                    row = [html.escape(p.country.name_with_code)]
                else:
                    row = []
                row.extend([self.link_for_person(p.person,
                                                 html.escape(p.name)),
                            ', '.join(p_needed)])
                body_row_list.append(self.html_tr_td_list(row))
        if body_row_list:
            text += self.html_table_thead_tbody_list(head_row_list,
                                                     body_row_list) + '\n'
        if missing_photo:
            text += ('<p>Photos are optional but recommended; they appear'
                     ' on the website%s and may appear on name badges.</p>\n'
                     % (', if permission is given for that use,'
                        if have_consent_ui else ''))
        if missing_phone:
            text += ('<p>Phone numbers (for Guides) need only be entered'
                     ' if they will appear on name badges or will be'
                     ' used for some other purpose.  Only Guides are listed'
                     ' as missing phone numbers, not other staff.</p>\n')
        return text

    def photo_scale_form(self, person, nonce):
        """Return a form to scale down a person's photo."""
        raise NotImplementedError

    def registration_status_text(self, consent_forms_date, have_consent_ui,
                                 max_photo_size, nonce):
        """Return the text of the registration status page."""
        e = self.event
        normal_countries = sorted(e.normal_country_list,
                                  key=lambda x: x.sort_key)
        people = sorted(e.person_list, key=lambda x: x.sort_key)
        normal_people = sorted(e.normal_person_list, key=lambda x: x.sort_key)
        staff = sorted(e.staff_list, key=lambda x: x.sort_key)
        text = ''

        text += '<h2>Action needed by participating countries</h2>\n'

        for c in normal_countries:
            text += self.missing_roles_text(c)

        text += self.missing_person_details_text(normal_people,
                                                 consent_forms_date,
                                                 have_consent_ui, True)

        text += '<h2>Action needed by the organisers</h2>\n'

        for c in normal_countries:
            if not c.guide_list:
                text += ('<p>No guide registered for'
                         ' <strong>%s</strong>.</p>\n'
                         % html.escape(c.name_with_code))
        text += ('<p>The system cannot tell automatically if not all'
                 ' staff have been registered.</p>\n')

        text += self.missing_person_details_text(staff, consent_forms_date,
                                                 have_consent_ui, False)

        head_row_list = [self.html_tr_th_list(['Country', 'Person', 'Role'])]
        body_row_list = []
        for p in people:
            if p.room_number is None:
                row = [html.escape(p.country.name_with_code),
                       self.link_for_person(p.person, html.escape(p.name)),
                       html.escape(p.primary_role)]
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

        head_row_list = [self.html_tr_th_list(['Country', 'Person',
                                               'File size', 'Scale down'])]
        body_row_list = []
        for p in people:
            filename = p.badge_photo_filename
            if filename is not None:
                photo_size = os.stat(filename).st_size
                if photo_size > max_photo_size:
                    row = [html.escape(p.country.name_with_code),
                           self.link_for_person(p.person, html.escape(p.name)),
                           str(photo_size),
                           self.photo_scale_form(p.person, nonce)]
                    body_row_list.append(self.html_tr_td_list(row))
        if body_row_list:
            text += '<h2>Photos with large file size</h2>\n'
            text += ('<p>These participants have photos that are over '
                     '%d bytes in size.  Although not strictly required, '
                     'scaling them down will make the site quicker for users '
                     'and may also speed up printing name badges.</p>\n'
                     % max_photo_size)
            text += self.html_table_thead_tbody_list(head_row_list,
                                                     body_row_list) + '\n'

        flags_needed = ''
        for c in normal_countries:
            if not c.flag_url:
                flags_needed += ('<p>No flag for <strong>%s</strong>.</p>\n'
                                 % html.escape(c.name_with_code))
        if flags_needed:
            text += ('<h2>Action needed by registration system'
                     ' maintainers</h2>\n')
            text += flags_needed

        return text

    def registration_status_country_text(self, country, consent_forms_date,
                                         have_consent_ui):
        """Return the text of the registration status page for one country."""
        people = sorted(country.person_list, key=lambda x: x.sort_key)
        text = ''
        text += self.missing_roles_text(country)

        text += self.missing_person_details_text(people, consent_forms_date,
                                                 have_consent_ui, False)

        return text

    def room_edit_field(self, p):
        """Return a form field to edit a person's room number."""
        raise NotImplementedError

    def edit_rooms_text(self):
        """Return the text of the page for editing room numbers."""
        e = self.event
        people_by_room = e.people_by_room
        rooms = sorted(people_by_room.keys())
        rlist = []
        for r in rooms:
            if r == '':
                rdesc = 'No room allocated'
            else:
                rdesc = 'Room: %s' % r
            rtext = '<h2>%s</h2>\n' % html.escape(rdesc)
            head_row_list = [self.html_tr_th_list(['Country', 'Person', 'Role',
                                                   'Gender', 'Room Type',
                                                   'Share With', 'Room'])]
            body_row_list = []
            for p in sorted(people_by_room[r], key=lambda x: x.sort_key):
                row = [html.escape(p.country.name_with_code),
                       self.link_for_person(p.person, html.escape(p.name)),
                       html.escape(p.primary_role),
                       html.escape(p.gender or ''),
                       html.escape(p.room_type or ''),
                       html.escape(p.room_share_with or ''),
                       self.room_edit_field(p)]
                body_row_list.append(self.html_tr_td_list(row))
            rtext += self.html_table_thead_tbody_list(head_row_list,
                                                      body_row_list) + '\n'
            rlist.append(rtext)
        return ''.join(rlist)
