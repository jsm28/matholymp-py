# Implement mo-static-import script.

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
The mo-static-import script imports CSV files and images from the
registration system to the static site, after an event has finished.
The argument is the directory with the files to import.  This
directory should contain files countries.csv, people.csv (the file
downloaded when not logged in, so only including public information)
and scores-rss.xml (the final RSS feed of all scores), and
subdirectories flags and photos from unpacking files flags.zip and
photos.zip from the registration system.  The data/<event>s.csv file
needs updating manually to include all relevant data (in particular,
the number of problems, the maximum marks for each problem and the
medal boundaries); this may be done before or after running
mo-static-import.  Once <event>s.csv has been updated and
mo-static-import has been run, mo-static-generate needs to be run to
update the site to reflect the newly imported data.  As with
mo-static-generate, mo-static-import should be run with the toplevel
directory for the website, containing the file staticsite.cfg, as its
working directory.
"""

import argparse
import os
import os.path
import re
import shutil

import matholymp
from matholymp.fileutil import read_utf8_csv, write_utf8_csv, \
    make_dirs_for_file
from matholymp.regdata import file_url_to_local
from matholymp.sitegen import read_sitegen_config, sitegen_countries_csv, \
    sitegen_people_csv

__all__ = ['main']

def main():
    """Main program for mo-static-import."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s '+matholymp.__version__)
    parser.add_argument('input_directory', help='directory with input data')
    args = vars(parser.parse_args())

    top_directory = os.getcwd()
    input_directory = args['input_directory']

    input_countries_csv = os.path.join(input_directory, 'countries.csv')
    input_people_csv = os.path.join(input_directory, 'people.csv')
    input_flags_dir = os.path.join(input_directory, 'flags')
    input_photos_dir = os.path.join(input_directory, 'photos')
    input_scores_rss = os.path.join(input_directory, 'scores-rss.xml')

    cfg_data = read_sitegen_config(top_directory)
    countries_csv = sitegen_countries_csv(top_directory, cfg_data)
    people_csv = sitegen_people_csv(top_directory, cfg_data)

    max_num_problems = 0
    event_number = None

    countries_data = read_utf8_csv(countries_csv)
    max_country_index = 0
    for c in countries_data:
        n = int(c['Country Number'])
        if n > max_country_index:
            max_country_index = n

    new_countries_data = read_utf8_csv(input_countries_csv)
    country_index = {}
    for c in new_countries_data:
        if event_number is None:
            event_number = c[cfg_data['num_key']]
        if c[cfg_data['num_key']] != event_number:
            raise ValueError('country from wrong event')
        annual_id = c['Country Number']
        country_number = c['Generic Number']
        del c['Generic Number']
        if not country_number:
            max_country_index += 1
            country_number = str(max_country_index)
        c['Country Number'] = country_number
        country_index[annual_id] = country_number
        if c['Flag URL']:
            flag_src_filename = file_url_to_local(c['Flag URL'],
                                                  input_flags_dir,
                                                  'flag')
            flag_ext = re.sub('^.*\\.', '', flag_src_filename)
            flag_ext = flag_ext.lower()
            if flag_ext == 'jpeg':
                flag_ext = 'jpg'
            flag_dst = 'flag' + event_number + '.' + flag_ext
            flag_dst_list = ['countries', 'country' + country_number,
                             flag_dst]
            c['Flag URL'] = cfg_data['url_base'] + '/'.join(flag_dst_list)
            flag_dst_filename = os.path.join(top_directory, *flag_dst_list)
            make_dirs_for_file(flag_dst_filename)
            shutil.copyfile(flag_src_filename, flag_dst_filename)
    if event_number is None:
        raise ValueError('no countries in imported data')
    for c in countries_data:
        if c[cfg_data['num_key']] == event_number:
            raise ValueError('data for this event already present')

    countries_data.extend(new_countries_data)
    countries_header = [cfg_data['num_key'], 'Country Number', 'Annual URL',
                        'Code', 'Name', 'Flag URL']
    if cfg_data['distinguish_official']:
        countries_header.extend([cfg_data['official_desc']])
        for c in countries_data:
            if cfg_data['official_desc'] not in c:
                c[cfg_data['official_desc']] = ''
    write_utf8_csv(countries_csv, countries_data, countries_header)

    people_data = read_utf8_csv(people_csv)
    max_person_index = 0
    for p in people_data:
        n = int(p['Person Number'])
        if n > max_person_index:
            max_person_index = n
        i = max_num_problems + 1
        while ('P%d' % i) in p:
            max_num_problems = i
            i += 1

    new_people_data = read_utf8_csv(input_people_csv)
    people_num_photos = {}
    for p in new_people_data:
        if p[cfg_data['num_key']] != event_number:
            raise ValueError('person from wrong event')
        p['Country Number'] = country_index[p['Country Number']]
        person_number = p['Generic Number']
        del p['Generic Number']
        if not person_number:
            max_person_index += 1
            person_number = str(max_person_index)
        p['Person Number'] = person_number
        i = max_num_problems + 1
        while ('P%d' % i) in p:
            max_num_problems = i
            i += 1
        if p['Photo URL']:
            photo_src_filename = file_url_to_local(p['Photo URL'],
                                                   input_photos_dir, 'photo')
            photo_ext = re.sub('^.*\\.', '', photo_src_filename)
            photo_ext = photo_ext.lower()
            if photo_ext == 'jpeg':
                photo_ext = 'jpg'
            photo_extra = ''
            if person_number in people_num_photos:
                people_num_photos[person_number] += 1
                photo_extra = '-%d' % people_num_photos[person_number]
            else:
                people_num_photos[person_number] = 1
            photo_dst = 'photo' + event_number + photo_extra + '.' + photo_ext
            photo_dst_list = ['people', 'person' + person_number,
                              photo_dst]
            p['Photo URL'] = cfg_data['url_base'] + '/'.join(photo_dst_list)
            photo_dst_filename = os.path.join(top_directory, *photo_dst_list)
            make_dirs_for_file(photo_dst_filename)
            shutil.copyfile(photo_src_filename, photo_dst_filename)
    for p in people_data:
        if p[cfg_data['num_key']] == event_number:
            raise ValueError('data for this event already present')

    people_data.extend(new_people_data)
    for p in people_data:
        for i in range(max_num_problems):
            pn = 'P%d' % (i+1)
            if pn not in p:
                p[pn] = ''
    people_header = [cfg_data['num_key'], 'Country Number', 'Person Number',
                     'Annual URL', 'Country Name', 'Country Code',
                     'Primary Role', 'Other Roles', 'Guide For',
                     'Contestant Code', 'Contestant Age', 'Given Name',
                     'Family Name']
    people_header.extend([('P%d' % (i + 1)) for i in range(max_num_problems)])
    people_header.extend(['Total', 'Award', 'Extra Awards', 'Photo URL'])
    write_utf8_csv(people_csv, people_data, people_header)

    rss_dst_filename = os.path.join(top_directory,
                                    cfg_data['short_name_url_plural'],
                                    cfg_data['short_name_url'] + event_number,
                                    'scoreboard', 'rss.xml')
    make_dirs_for_file(rss_dst_filename)
    shutil.copyfile(input_scores_rss, rss_dst_filename)
