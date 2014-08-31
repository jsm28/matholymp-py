# Implement mo-document-generate script.

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
The mo-document-generate script processes data downloaded from the
registration system to generate various documents such as papers and
name badges.  It expects to be run in a directory where the data/
subdirectory contains the downloaded people.csv (full file, downloaded
when logged in administratively), countries.csv and flags/ and photos/
directories from unpacking the corresponding .zip files, and generates
output in an out/ subdirectory, unless options are used to select
other directories.  The known types of document are 'badge',
'desk-label', 'award-certificate', 'participation-certificate',
'paper', 'language-list', 'coord-form' and 'scores-commands'.  The
identifiers passed along with document types vary; any identifier may
be used for document types that do not depend on such an identifier,
and 'all' is suitable for most cases.
"""

import argparse
import os
import os.path

from matholymp.data import EventGroup
from matholymp.docgen import DocumentGenerator
from matholymp.csvsource import CSVDataSource
from matholymp.fileutil import read_utf8_csv, read_config

__all__ = ['main']

def main():
    """Main program for mo-document-generate."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--background', action='store_true',
                        help='include background in output')
    parser.add_argument('--input-directory',
                        help='directory with CSV files and unpacked'
                        ' ZIP contents')
    parser.add_argument('--output-directory',
                        help='directory for output files')
    parser.add_argument('--problems-directory', help='directory for problems')
    parser.add_argument('--day', help='day for papers')
    parser.add_argument('type', help='type of document to output')
    parser.add_argument('id', help='object for which to output the document,'
                        ' or \'all\'')
    cmdline_data = vars(parser.parse_args())
    top_directory = os.getcwd()
    templates_dir = os.path.join(top_directory, 'templates')
    config_file_name = os.path.join(top_directory, 'documentgen.cfg')
    cfg_str_keys = ['year', 'short_name', 'long_name', 'num_key',
                    'marks_per_problem', 'badge_phone_desc',
                    'badge_event_phone', 'badge_emergency_phone',
                    'badge_event_ordinal', 'badge_event_venue',
                    'badge_event_dates']
    cfg_int_keys = ['event_number', 'num_exams', 'num_problems',
                    'num_contestants_per_team']
    cfg_int_none_keys = ['gold_boundary', 'silver_boundary', 'bronze_boundary']
    cfg_bool_keys = ['show_countries_for_guides', 'show_rooms_for_guides',
                     'paper_print_logo', 'paper_text_left']
    config_data = read_config(config_file_name, 'matholymp.documentgen',
                              cfg_str_keys, cfg_int_keys,
                              cfg_int_none_keys, cfg_bool_keys)
    config_data['staff_country'] = (config_data['short_name'] + ' ' +
                                    config_data['year'] + ' Staff')
    if not cmdline_data['input_directory']:
        cmdline_data['input_directory'] = os.path.join(top_directory, 'data')
    if not cmdline_data['output_directory']:
        cmdline_data['output_directory'] = os.path.join(top_directory, 'out')
    if not cmdline_data['problems_directory']:
        cmdline_data['problems_directory'] = os.path.join(top_directory,
                                                          'papers',
                                                          config_data['year'])

    people_data = read_utf8_csv(os.path.join(cmdline_data['input_directory'],
                                             'people.csv'))
    country_data = read_utf8_csv(os.path.join(cmdline_data['input_directory'],
                                              'countries.csv'))

    all_data = EventGroup(CSVDataSource(config_data, None, [], country_data,
                                        people_data))
    event_data = all_data.event_map[config_data['event_number']]
    docgen = DocumentGenerator(config_data, event_data, templates_dir,
                               cmdline_data['problems_directory'],
                               cmdline_data['input_directory'],
                               cmdline_data['output_directory'])

    id = cmdline_data['id']
    bg = cmdline_data['background']
    if cmdline_data['type'] == 'badge':
        docgen.generate_badges(id, bg)
    elif cmdline_data['type'] == 'desk-label':
        docgen.generate_desk_labels(id)
    elif cmdline_data['type'] == 'award-certificate':
        docgen.generate_award_certs(id, bg)
    elif cmdline_data['type'] == 'participation-certificate':
        docgen.generate_part_certs(id, bg)
    elif cmdline_data['type'] == 'paper':
        docgen.generate_papers(id, cmdline_data['day'], bg)
    elif cmdline_data['type'] == 'language-list':
        docgen.generate_language_list()
    elif cmdline_data['type'] == 'coord-form':
        docgen.generate_coord_forms()
    elif cmdline_data['type'] == 'scores-commands':
        docgen.generate_scores_commands()
    else:
        raise ValueError('Unknown type %s' % cmdline_data['type'])