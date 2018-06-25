# Implement mo-static-papers-import script.

# Copyright 2014-2018 Joseph Samuel Myers.

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
The mo-static-papers-import script imports exam papers to the static
site, after those exams have been sat.  mo-static-papers-import should
be run with the toplevel directory for the website, containing the
file staticsite.cfg, as its working directory.  It takes options
--day, to specify the day for which papers are to be imported (if not
specified, papers for all days are imported), and --background,
specifying that papers were printed on paper with a pre-printed
background and so both versions with and without that background
included should be imported (otherwise, only one version for each
language is imported).  The non-option argument is the name of the
toplevel directory for mo-document-generate, containing
documentgen.cfg, a subdirectory data/ with files from the registration
system (with the full version of people.csv downloaded when logged in
administratively, as well as countries.csv), and a subdirectory out/
containing the output from 'mo-document-generate paper all-languages'
and, if pre-printed backgrounds were used, 'mo-document-generate
--background paper all-languages'.  After running
mo-static-papers-import, mo-static-generate needs to be run to update
the site to reflect the newly imported data.
"""

import argparse
import os
import os.path
import shutil

import matholymp
from matholymp.collate import coll_get_sort_key
from matholymp.data import EventGroup
from matholymp.docgen import read_docgen_config
from matholymp.csvsource import CSVDataSource
from matholymp.fileutil import read_utf8_csv, write_utf8_csv, \
    make_dirs_for_file
from matholymp.regdata import lang_to_filename
from matholymp.sitegen import read_sitegen_config, sitegen_papers_csv

__all__ = ['main']


def _import_paper(papers_data, cfg_data, docgen_config_data, top_directory,
                  input_papers_directory, day, language, description,
                  filename):
    paper_dst_list = [cfg_data['short_name_url_plural'],
                      (cfg_data['short_name_url']
                       + str(docgen_config_data['event_number'])),
                      filename]
    p = {cfg_data['num_key']: str(docgen_config_data['event_number']),
         'Day': day or '1',
         'Language': language,
         'Description': description,
         'URL': cfg_data['url_base'] + '/'.join(paper_dst_list)}
    paper_dst_filename = os.path.join(top_directory, *paper_dst_list)
    make_dirs_for_file(paper_dst_filename)
    shutil.copyfile(os.path.join(input_papers_directory, filename),
                    paper_dst_filename)
    papers_data.append(p)


def main():
    """Main program for mo-static-papers-import."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s '+matholymp.__version__)
    parser.add_argument('--background', action='store_true',
                        help='papers use preprinted backgrounds')
    parser.add_argument('--day', help='day for papers')
    parser.add_argument('input_directory', help='directory with input data')
    args = vars(parser.parse_args())

    top_directory = os.getcwd()
    input_directory = args['input_directory']

    input_countries_csv = os.path.join(input_directory, 'data',
                                       'countries.csv')
    input_people_csv = os.path.join(input_directory, 'data', 'people.csv')
    input_papers_directory = os.path.join(input_directory, 'out')

    cfg_data = read_sitegen_config(top_directory)
    papers_csv = sitegen_papers_csv(top_directory, cfg_data)

    papers_data = read_utf8_csv(papers_csv)

    docgen_config_data = read_docgen_config(input_directory)
    new_countries_data = read_utf8_csv(input_countries_csv)
    new_people_data = read_utf8_csv(input_people_csv)
    all_new_data = EventGroup(CSVDataSource(docgen_config_data, None, [],
                                            new_countries_data,
                                            new_people_data, input_directory))
    event_data = all_new_data.event_map[docgen_config_data['event_number']]

    if args['day']:
        days = [args['day']]
    elif event_data.num_exams == 1:
        days = ['']
    else:
        days = [str(i + 1) for i in range(event_data.num_exams)]

    all_languages = sorted(event_data.language_list, key=coll_get_sort_key)
    for d in days:
        if d:
            day_text = '-day' + d
        else:
            day_text = ''
        for lang in all_languages:
            before_text = 'paper' + day_text
            after_text = '-' + lang_to_filename(lang) + '.pdf'
            if args['background']:
                filename = before_text + '-bg' + after_text
                _import_paper(papers_data, cfg_data, docgen_config_data,
                              top_directory, input_papers_directory, d, lang,
                              '', filename)
                filename = before_text + after_text
                _import_paper(papers_data, cfg_data, docgen_config_data,
                              top_directory, input_papers_directory, d, lang,
                              'without background design', filename)
            else:
                filename = before_text + after_text
                _import_paper(papers_data, cfg_data, docgen_config_data,
                              top_directory, input_papers_directory, d, lang,
                              '', filename)

    write_utf8_csv(papers_csv, papers_data,
                   [cfg_data['num_key'], 'Day', 'Language', 'Description',
                    'URL'])
