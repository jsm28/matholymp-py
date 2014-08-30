# RoundupSiteGenerator class for matholymp package.

# Copyright 2014 Joseph Samuel Myers.

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
This module provides the RoundupSiteGenerator class that generates web
content from within the registration system.
"""

__all__ = ['RoundupSiteGenerator']

from matholymp.data import EventGroup
from matholymp.fileutil import write_utf8_csv_bytes
from matholymp.roundupreg.roundupsource import RoundupDataSource
from matholymp.sitegen import SiteGenerator

class RoundupSiteGenerator(SiteGenerator):

    """
    A RoundupSiteGenerator supports web content generation from within
    the registration system.
    """

    def __init__(self, db):
        """
        Initialise a RoundupSiteGenerator from the given db object for
        that Roundup instance.
        """
        cfg = { 'num_key': db.config.ext['MATHOLYMP_SHORT_NAME'] + ' Number',
                'scores_css': db.config.ext['MATHOLYMP_SCORES_CLASS'],
                'list_css': db.config.ext['MATHOLYMP_LIST_CLASS'],
                'official_desc': db.config.ext['MATHOLYMP_OFFICIAL_DESC'],
                'official_desc_lc':
                    db.config.ext['MATHOLYMP_OFFICIAL_DESC_LC'],
                'url_base': db.config.ext['MATHOLYMP_GENERIC_URL_BASE'],
                'outer_scores_css':
                    db.config.ext['MATHOLYMP_OUTER_SCORES_CLASS'] }
        event_group = EventGroup(RoundupDataSource(db))
        super(RoundupSiteGenerator, self).__init__(cfg, event_group)

    def countries_csv_bytes(self):
        """Return the byte contents of the CSV of countries."""
        e = self._data.event_list[0]
        data = self.one_event_countries_csv_content(e, reg_system=True)
        return write_utf8_csv_bytes(data[0], data[1])

    def scores_csv_bytes(self):
        """Return the byte contents of the CSV of scores."""
        e = self._data.event_list[0]
        data = self.one_event_scores_csv_content(e, reg_system=True)
        return write_utf8_csv_bytes(data[0], data[1])

    def people_csv_bytes(self, private_data):
        """Return the byte contents of the CSV of people."""
        e = self._data.event_list[0]
        data = self.one_event_people_csv_content(e, reg_system=True,
                                                 private_data=private_data)
        return write_utf8_csv_bytes(data[0], data[1])

    def link_for_country_at_event(self, country, link_body):
        return self.html_a(link_body, 'country' + str(country.country.id))

    def link_for_person(self, person, link_body):
        return self.html_a(link_body, 'person' + str(person.id))

    def display_scoreboard_text(self, e, display_start):
        """
        Return the text of one page of the display scoreboard for one
        event.
        """
        text = ''
        countries = sorted(e.country_with_contestants_list,
                           key=lambda x:x.sort_key)
        rows = 2
        cols = 2
        cell_width = '50%'
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
                                       width=cell_width)
                col_list.append(td_text)
            row_list.append(self.html_tr_list(col_list))
        text += self.html_table('\n'.join(row_list), width='100%')
        if e.scores_final:
            text += ('<p>Medal boundaries: Gold %d, Silver %d,'
                     ' Bronze %d.</p>\n' %
                     (e.gold_boundary, e.silver_boundary, e.bronze_boundary))
        return text

    def this_event_scoreboard_text(self, for_display, display_start):
        """Return the text of the scoreboard for the present event."""
        e = self._data.event_list[0]
        if for_display:
            return self.display_scoreboard_text(e, display_start)
        else:
            return self.scoreboard_text(e)
