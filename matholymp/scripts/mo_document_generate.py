# Implement mo-document-generate script.

# Copyright 2014-2025 Joseph Samuel Myers.

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
'invitation-letter', 'desk-label', 'award-certificate',
'participation-certificate', 'paper', 'language-list', 'coord-form'
and 'scores-commands'.  The identifiers passed along with document
types vary; any identifier may be used for document types that do not
depend on such an identifier, and 'all' is suitable for most cases.
"""

import argparse
import os
import os.path

import matholymp
from matholymp.data import EventGroup
from matholymp.docgen import read_docgen_config, DocumentGenerator
from matholymp.csvsource import CSVDataSource
from matholymp.fileutil import read_utf8_csv, read_text_from_file

__all__ = ['main']


def main():
    """Main program for mo-document-generate."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + matholymp.__version__)
    parser.add_argument('--background', action='store_true',
                        help='include background in output')
    parser.add_argument('--input-directory',
                        help='directory with CSV files and unpacked'
                        ' ZIP contents')
    parser.add_argument('--output-directory',
                        help='directory for output files')
    parser.add_argument('--problems-directory', help='directory for problems')
    parser.add_argument('--day', help='day for papers')
    parser.add_argument('--exam-order',
                        help='file with order of contestants for exams')
    parser.add_argument('type', help='type of document to output')
    parser.add_argument('id', help='object for which to output the document,'
                        ' or \'all\'')
    cmdline_data = vars(parser.parse_args())
    top_directory = os.getcwd()
    templates_dir = os.path.join(top_directory, 'templates')
    config_data = read_docgen_config(top_directory)
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
                                        people_data,
                                        cmdline_data['input_directory']))
    event_data = all_data.event_map[config_data['event_number']]
    docgen = DocumentGenerator(config_data, event_data, templates_dir,
                               cmdline_data['problems_directory'],
                               cmdline_data['input_directory'],
                               cmdline_data['output_directory'], True)

    if cmdline_data['exam_order']:
        code_list = read_text_from_file(cmdline_data['exam_order'])
        exam_order = {}
        for idx, code in enumerate(code_list.split()):
            exam_order[code] = idx
    else:
        exam_order = None

    gen_id = cmdline_data['id']
    bg = cmdline_data['background']
    if cmdline_data['type'] == 'badge':
        docgen.generate_badges(gen_id, bg)
    elif cmdline_data['type'] == 'invitation-letter':
        docgen.generate_invitation_letters(gen_id)
    elif cmdline_data['type'] == 'desk-label':
        docgen.generate_desk_labels(gen_id, exam_order)
    elif cmdline_data['type'] == 'award-certificate':
        docgen.generate_award_certs(gen_id, bg)
    elif cmdline_data['type'] == 'participation-certificate':
        docgen.generate_part_certs(gen_id, bg)
    elif cmdline_data['type'] == 'paper':
        docgen.generate_papers(gen_id, cmdline_data['day'], bg, exam_order)
    elif cmdline_data['type'] == 'language-list':
        docgen.generate_language_list()
    elif cmdline_data['type'] == 'coord-form':
        docgen.generate_coord_forms(bg)
    elif cmdline_data['type'] == 'scores-commands':
        docgen.generate_scores_commands()
    else:
        raise ValueError('Unknown type %s' % cmdline_data['type'])
