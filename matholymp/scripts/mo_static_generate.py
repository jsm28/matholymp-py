# Implement mo-static-generate script.

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
The mo-static-generate script processes CSV input files to generate a
static website for mathematical olympiads.  It expects to be run with
a working directory that also contains files staticsite.cfg and
page-template.  The website is generated in that directory.  Files
data/countries.csv, data/<event>s.csv, data/papers.csv and
data/people.csv are used as inputs.  The script does not generate an
overall front page to the site; such a page must be created manually.
The page template, or a manually created page, should contain links to
the overall countries/, <event>s/ and people/ pages.
"""

import os
import os.path
import sys

from matholymp.data import EventGroup
from matholymp.csvsource import CSVDataSource
from matholymp.fileutil import read_utf8_csv, read_text_from_file, read_config
from matholymp.sitegen import SiteGenerator

__all__ = ['main']

def main():
    """Main program for mo-static-generate."""

    top_directory = os.getcwd()

    cfg_file_name = os.path.join(top_directory, 'staticsite.cfg')
    cfg_str_keys = ['long_name', 'short_name', 'short_name_plural',
                    'num_key', 'scores_css', 'list_css', 'photo_css',
                    'page_suffix', 'page_include_extra', 'url_base',
                    'short_name_url', 'short_name_url_plural',
                    'official_desc', 'official_desc_lc', 'official_adj',
                    'age_day_desc']
    cfg_int_keys = []
    cfg_int_none_keys = ['event_active_number']
    cfg_bool_keys = ['use_xhtml']
    cfg_data = read_config(cfg_file_name, 'matholymp.staticsite',
                           cfg_str_keys, cfg_int_keys, cfg_int_none_keys,
                           cfg_bool_keys)

    template_file_name = os.path.join(top_directory, 'page-template')
    cfg_data['page_template'] = read_text_from_file(template_file_name)

    data_directory = os.path.join(top_directory, 'data')

    events_csv = os.path.join(data_directory,
                              cfg_data['short_name_url_plural'] + '.csv')
    countries_csv = os.path.join(data_directory, 'countries.csv')
    people_csv = os.path.join(data_directory, 'people.csv')
    papers_csv = os.path.join(data_directory, 'papers.csv')

    events_data = read_utf8_csv(events_csv)
    countries_data = read_utf8_csv(countries_csv)
    people_data = read_utf8_csv(people_csv)
    papers_data = read_utf8_csv(papers_csv)

    all_data = EventGroup(CSVDataSource(cfg_data, events_data, papers_data,
                                        countries_data, people_data))

    sitegen = SiteGenerator(cfg_data, all_data, top_directory)
    sitegen.generate_site()
