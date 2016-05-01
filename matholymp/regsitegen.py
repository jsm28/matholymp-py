# RegSiteGenerator class for matholymp package.

# Copyright 2014-2016 Joseph Samuel Myers.

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

from matholymp.data import EventGroup
from matholymp.fileutil import write_utf8_csv_bytes
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
