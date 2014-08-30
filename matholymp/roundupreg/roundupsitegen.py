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
                'official_desc': db.config.ext['MATHOLYMP_OFFICIAL_DESC'],
                'url_base': db.config.ext['MATHOLYMP_GENERIC_URL_BASE'] }
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
