# Implement mo-static-upgrade script.

# Copyright 2015-2017 Joseph Samuel Myers.

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
from matholymp.sitegen import read_sitegen_config, sitegen_people_csv

__all__ = ['main']

def _convert_comma_separated(s):
    if s == '':
        return s
    return comma_join(s.split(','))

def main():
    """Main program for mo-static-upgrade."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s '+matholymp.__version__)
    args = vars(parser.parse_args())

    top_directory = os.getcwd()

    cfg_data = read_sitegen_config(top_directory)
    people_csv = sitegen_people_csv(top_directory, cfg_data)

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
