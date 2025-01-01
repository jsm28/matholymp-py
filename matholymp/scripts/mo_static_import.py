# Implement mo-static-import script.

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
The mo-static-import script imports CSV files and images from the
registration system to the static site, after an event has finished.
The argument is the directory with the files to import.  This
directory may contain files countries.csv, people.csv (the file
downloaded when not logged in, so only including public information)
and scores-rss.xml (the final RSS feed of all scores), and either
files flags.zip and photos.zip or subdirectories flags and photos from
unpacking those files from the registration system; where a file or
corresponding directory is not present, it will be downloaded
automatically.  The data/<event>s.csv file needs updating manually to
include all relevant data (in particular, the number of problems, the
maximum marks for each problem and the medal boundaries); this may be
done before or after running mo-static-import.  Once <event>s.csv has
been updated and mo-static-import has been run, mo-static-generate
needs to be run to update the site to reflect the newly imported data.
As with mo-static-generate, mo-static-import should be run with the
toplevel directory for the website, containing the file
staticsite.cfg, as its working directory.
"""

import argparse
import os
import os.path
import re
import shutil
import tempfile
import urllib.request
import zipfile

import matholymp
from matholymp.fileutil import read_utf8_csv, write_utf8_csv, \
    make_dirs_for_file, write_text_to_file, read_text_from_file, file_extension
from matholymp.regdata import file_url_to_local
from matholymp.sitegen import read_sitegen_config, sitegen_events_csv, \
    sitegen_countries_csv, sitegen_people_csv

__all__ = ['main']


def _import_from_dir(top_directory, input_directory, temp_dir):
    cfg_data = read_sitegen_config(top_directory)
    events_csv = sitegen_events_csv(top_directory, cfg_data)
    countries_csv = sitegen_countries_csv(top_directory, cfg_data)
    people_csv = sitegen_people_csv(top_directory, cfg_data)
    event_active_number = cfg_data['event_active_number']
    reg_url = None
    if event_active_number is not None:
        events_data = read_utf8_csv(events_csv)
        for e in events_data:
            eid = int(e['Number'])
            if eid == event_active_number:
                if reg_url is not None:
                    raise ValueError('duplicate event %d' % eid)
                reg_url = '%sregistration/%s/' % (cfg_data['url_base'],
                                                  e['Year'])

    input_countries_csv = os.path.join(input_directory, 'countries.csv')
    if not os.access(input_countries_csv, os.F_OK):
        if reg_url is None:
            raise ValueError('downloading data for unknown event')
        urllib.request.urlretrieve(reg_url + 'country?@action=country_csv',
                                   input_countries_csv)
    input_people_csv = os.path.join(input_directory, 'people.csv')
    if not os.access(input_people_csv, os.F_OK):
        if reg_url is None:
            raise ValueError('downloading data for unknown event')
        urllib.request.urlretrieve(reg_url + 'person?@action=people_csv',
                                   input_people_csv)
    input_flags_dir = os.path.join(input_directory, 'flags')
    if not os.access(input_flags_dir, os.F_OK):
        input_flags_zip = os.path.join(input_directory, 'flags.zip')
        if not os.access(input_flags_zip, os.F_OK):
            if reg_url is None:
                raise ValueError('downloading data for unknown event')
            urllib.request.urlretrieve(reg_url + 'country?@action=flags_zip',
                                       input_flags_zip)
        with zipfile.ZipFile(input_flags_zip, 'r') as z:
            z.extractall(temp_dir)
        input_flags_dir = os.path.join(temp_dir, 'flags')
    input_photos_dir = os.path.join(input_directory, 'photos')
    if not os.access(input_photos_dir, os.F_OK):
        input_photos_zip = os.path.join(input_directory, 'photos.zip')
        if not os.access(input_photos_zip, os.F_OK):
            if reg_url is None:
                raise ValueError('downloading data for unknown event')
            urllib.request.urlretrieve(reg_url + 'person?@action=photos_zip',
                                       input_photos_zip)
        with zipfile.ZipFile(input_photos_zip, 'r') as z:
            z.extractall(temp_dir)
        input_photos_dir = os.path.join(temp_dir, 'photos')
    input_scores_rss = os.path.join(input_directory, 'scores-rss.xml')
    if not os.access(input_scores_rss, os.F_OK):
        if reg_url is None:
            raise ValueError('downloading data for unknown event')
        urllib.request.urlretrieve(reg_url + 'country?@action=scores_rss',
                                   input_scores_rss)

    max_num_problems = 0
    event_number = None

    countries_data = read_utf8_csv(countries_csv)
    max_country_index = 0
    for c in countries_data:
        n = int(c['Country Number'])
        max_country_index = max(max_country_index, n)

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
                                                  'flag', annual_id)
            flag_ext = file_extension(flag_src_filename)
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
    countries_header.extend(['Normal'])
    write_utf8_csv(countries_csv, countries_data, countries_header)

    people_data = read_utf8_csv(people_csv)
    max_person_index = 0
    for p in people_data:
        n = int(p['Person Number'])
        max_person_index = max(max_person_index, n)
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
        annual_id = p['Person Number']
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
                                                   input_photos_dir, 'photo',
                                                   annual_id)
            photo_ext = file_extension(photo_src_filename)
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
            pn = 'P%d' % (i + 1)
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

    if event_active_number == int(event_number):
        static_cfg = os.path.join(top_directory, 'staticsite.cfg')
        cfg_text = read_text_from_file(static_cfg)
        cfg_text = re.sub('^event_active_number *= *[0-9]*$',
                          'event_active_number =', cfg_text,
                          flags=re.MULTILINE)
        write_text_to_file(cfg_text, static_cfg)


def main():
    """Main program for mo-static-import."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + matholymp.__version__)
    parser.add_argument('input_directory', help='directory with input data')
    args = vars(parser.parse_args())

    with tempfile.TemporaryDirectory() as temp_dir:
        _import_from_dir(os.getcwd(), args['input_directory'], temp_dir)
