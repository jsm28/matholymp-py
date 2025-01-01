# Implement mo-static-upgrade script.

# Copyright 2015-2025 Joseph Samuel Myers.

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
The mo-static-upgrade script updates CSV files on the static site for
changes to their format required by matholymp upgrades.  As with
mo-static-generate, mo-static-upgrade should be run with the toplevel
directory for the website, containing the file staticsite.cfg, as its
working directory.
"""

import argparse
import os

import matholymp
from matholymp.fileutil import read_utf8_csv, write_utf8_csv, comma_join
from matholymp.sitegen import read_sitegen_config, sitegen_events_csv, \
    sitegen_countries_csv, sitegen_people_csv

__all__ = ['main']


def _convert_comma_separated(s):
    if s == '':
        return s
    return comma_join(s.split(','))


def main():
    """Main program for mo-static-upgrade."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + matholymp.__version__)
    parser.parse_args()

    top_directory = os.getcwd()

    cfg_data = read_sitegen_config(top_directory)
    events_csv = sitegen_events_csv(top_directory, cfg_data)
    countries_csv = sitegen_countries_csv(top_directory, cfg_data)
    people_csv = sitegen_people_csv(top_directory, cfg_data)

    e_max_num_problems = 0
    e_honourable_mentions_available_varies = False
    e_distinguish_official_varies = False
    e_age_day_desc_varies = False
    e_staff_names = {}
    events_data = read_utf8_csv(events_csv)
    for e in events_data:
        e_staff_names[e['Number']] = (cfg_data['short_name'] + ' '
                                      + e['Year'] + ' Staff')
        i = e_max_num_problems + 1
        while ('P%d Max' % i) in e:
            e_max_num_problems = i
            i += 1
        if 'Honourable Mentions Available' in e:
            e_honourable_mentions_available_varies = True
        if 'Distinguish Official Countries' in e:
            e_distinguish_official_varies = True
        if 'Age Day Description' in e:
            e_age_day_desc_varies = True
        if 'Country Name In' not in e:
            # Updating from 2017.01.0 or earlier.
            e['Country Name In'] = e['Country']
        if 'Event Type' not in e:
            # Updating from 2020.07.0 or earlier.
            if 'Virtual Event' in e:
                e['Event Type'] = ('virtual'
                                   if e['Virtual Event'] == 'Yes'
                                   else 'in-person')
                del e['Virtual Event']
            else:
                # Updating from 2018.02.0 or earlier.
                e['Event Type'] = 'in-person'
    events_header = ['Number', 'Year', 'Country Number', 'Country',
                     'Country Name In', 'City', 'Event Type', 'Start Date',
                     'End Date', 'Home Page URL', 'Contact Name',
                     'Contact Email', 'Number of Exams',
                     'Number of Problems']
    events_header.extend(['P%d Max' % (i + 1)
                          for i in range(e_max_num_problems)])
    events_header.extend(['Gold Boundary', 'Silver Boundary',
                          'Bronze Boundary'])
    if e_honourable_mentions_available_varies:
        events_header.extend(['Honourable Mentions Available'])
    if e_distinguish_official_varies:
        events_header.extend(['Distinguish Official Countries'])
    if e_age_day_desc_varies:
        events_header.extend(['Age Day Description'])
    write_utf8_csv(events_csv, events_data, events_header)

    countries_data = read_utf8_csv(countries_csv)
    for c in countries_data:
        if 'Normal' not in c:
            # Updating from 2015.01.0 or earlier.
            e_number = c[cfg_data['num_key']]
            is_normal = c['Name'] != e_staff_names[e_number]
            c['Normal'] = 'Yes' if is_normal else 'No'
    countries_header = [cfg_data['num_key'], 'Country Number', 'Annual URL',
                        'Code', 'Name', 'Flag URL']
    if cfg_data['distinguish_official']:
        countries_header.extend([cfg_data['official_desc']])
    countries_header.extend(['Normal'])
    write_utf8_csv(countries_csv, countries_data, countries_header)

    max_num_problems = 0
    people_data = read_utf8_csv(people_csv)
    for p in people_data:
        i = max_num_problems + 1
        while ('P%d' % i) in p:
            max_num_problems = i
            i += 1
        if 'Extra Awards' not in p:
            # Updating from 2015.01.0 or earlier.
            p['Extra Awards'] = ''
            p['Other Roles'] = _convert_comma_separated(p['Other Roles'])
            p['Guide For'] = _convert_comma_separated(p['Guide For'])

    people_header = [cfg_data['num_key'], 'Country Number', 'Person Number',
                     'Annual URL', 'Country Name', 'Country Code',
                     'Primary Role', 'Other Roles', 'Guide For',
                     'Contestant Code', 'Contestant Age', 'Given Name',
                     'Family Name']
    people_header.extend([('P%d' % (i + 1)) for i in range(max_num_problems)])
    people_header.extend(['Total', 'Award', 'Extra Awards', 'Photo URL'])
    write_utf8_csv(people_csv, people_data, people_header)
