# RoundupSiteGenerator class for matholymp package.

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
This module provides the RoundupSiteGenerator class that generates web
content from within the Roundup-based registration system.
"""

__all__ = ['RoundupSiteGenerator']

from matholymp.data import EventGroup
from matholymp.roundupreg.roundupsource import RoundupDataSource
from matholymp.regsitegen import RegSiteGenerator

class RoundupSiteGenerator(RegSiteGenerator):

    """
    A RoundupSiteGenerator supports web content generation from within
    the Roundup-based registration system.
    """

    def __init__(self, db):
        """
        Initialise a RoundupSiteGenerator from the given db object for
        that Roundup instance.
        """
        html_ver_map = { 'html4': False,
                         'xhtml': True }
        use_xhtml = html_ver_map[db.config.HTML_VERSION]
        cfg = { 'num_key': db.config.ext['MATHOLYMP_SHORT_NAME'] + ' Number',
                'scores_css': db.config.ext['MATHOLYMP_SCORES_CLASS'],
                'list_css': db.config.ext['MATHOLYMP_LIST_CLASS'],
                'use_xhtml': use_xhtml,
                'official_desc': db.config.ext['MATHOLYMP_OFFICIAL_DESC'],
                'official_desc_lc':
                    db.config.ext['MATHOLYMP_OFFICIAL_DESC_LC'],
                'url_base': db.config.ext['MATHOLYMP_GENERIC_URL_BASE'],
                'outer_scores_css':
                    db.config.ext['MATHOLYMP_OUTER_SCORES_CLASS'] }
        event_group = EventGroup(RoundupDataSource(db))
        super(RoundupSiteGenerator, self).__init__(cfg, event_group)

    def link_for_country_at_event(self, country, link_body):
        return self.html_a(link_body, 'country' + str(country.country.id))

    def link_for_person(self, person, link_body):
        return self.html_a(link_body, 'person' + str(person.id))
