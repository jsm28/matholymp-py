# Utility functions for Roundup registration system for matholymp package.

# Copyright 2014-2020 Joseph Samuel Myers.

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
This module provides various utility functions for the Roundup
registration system.
"""

import base64
import binascii
import csv
import hashlib
import html
import os
import os.path
import re
import time
import zipfile

from matholymp.datetimeutil import date_from_ymd_str, age_on_date
from matholymp.fileutil import read_utf8_csv_bytes, comma_split, \
    file_format_contents, file_extension
from matholymp.roundupreg.config import get_num_problems, get_age_day_date

__all__ = ['scores_from_str', 'person_date_of_birth', 'contestant_age',
           'person_is_contestant', 'contestant_code', 'pn_score',
           'scores_final', 'any_scores_missing', 'country_has_contestants',
           'valid_country_problem', 'valid_int_str', 'create_rss',
           'db_file_format_contents', 'db_file_extension', 'db_file_url',
           'bulk_csv_delimiter', 'bulk_csv_data', 'bulk_csv_contact_emails',
           'bulk_csv_country_number_url', 'bulk_csv_person_number_url',
           'upload_path_from_hash', 'bulk_zip_data', 'country_from_code']


def scores_from_str(db, score_str):
    """
    Return a list of the scores (strings) for a contestant, given the
    string for their scores stored in the database.
    """
    num_problems = get_num_problems(db)
    scores = score_str.split(',')
    # Allow for the number of problems changing after registration started.
    if len(scores) < num_problems:
        scores.extend(['' for i in range(num_problems - len(scores))])
    elif len(scores) > num_problems:
        for i in range(num_problems, len(scores)):
            if scores[i] != '':
                raise ValueError('number of problems reduced after'
                                 ' scores entered: %s' % scores[i])
        scores = scores[0:num_problems]
    return scores


def person_date_of_birth(db, person):
    """Return the date of birth for a registered participant, or None."""
    dob_year = db.person.get(person, 'date_of_birth_year')
    dob_month = db.person.get(person, 'date_of_birth_month')
    dob_day = db.person.get(person, 'date_of_birth_day')
    if dob_year is None or dob_month is None or dob_day is None:
        return None
    return date_from_ymd_str('date of birth', dob_year, dob_month, dob_day)


def contestant_age(db, person):
    """Return the age of a contestant on the configured day."""
    date1 = person_date_of_birth(db, person)
    if date1 is None:
        return None
    date2 = get_age_day_date(db)
    return age_on_date(date1, date2)


def person_is_contestant(db, person):
    """Determine whether a person is a contestant."""
    role = db.person.get(person, 'primary_role')
    return db.matholymprole.get(role, 'name').startswith('Contestant ')


def contestant_code(db, person):
    """Determine a contestant's contestant code."""
    role = db.person.get(person, 'primary_role')
    country = db.person.get(person, 'country')
    number = db.matholymprole.get(role, 'name')[len('Contestant '):]
    return db.country.get(country, 'code') + number


def pn_score(db, person, n):
    """Determine the score of a contestant on a given problem."""
    score_str = db.person.get(person, 'scores')
    scores = scores_from_str(db, score_str)
    return scores[n - 1]


def scores_final(db):
    """Determine whether the scores are final."""
    gold = db.event.get('1', 'gold')
    if gold is None or gold == '':
        return False
    else:
        return True


def any_scores_missing(db):
    """Determine whether any scores have yet to be entered."""
    person_list = db.person.list()
    num_problems = get_num_problems(db)
    for person in person_list:
        if person_is_contestant(db, person):
            score_str = db.person.get(person, 'scores')
            scores = scores_from_str(db, score_str)
            for i in range(num_problems):
                if scores[i] == '':
                    return True
    return False


def country_has_contestants(db, country):
    """Determine whether a country has any contestants registered."""
    people = db.person.filter(None, {'country': country})
    for person in people:
        if person_is_contestant(db, person):
            return True
    return False


def valid_country_problem(db, form):
    """Determine whether the country and problem are valid to enter scores."""
    if 'country' not in form or 'problem' not in form:
        return False
    num_problems = get_num_problems(db)
    country = form['country'].value
    problem = form['problem'].value
    if not re.fullmatch('[1-9][0-9]*', problem):
        return False
    if int(problem) > num_problems:
        return False
    return country_has_contestants(db, country)


def valid_int_str(int_str, max_val):
    """
    Determine whether the given string (for something required to be
    an integer, such as a score) is an integer in the range from 0 to
    max_val inclusive.  If max_val is None, there is no upper bound on
    allowed values.
    """
    if int_str != '0' and not re.fullmatch('[1-9][0-9]*', int_str):
        return False
    if max_val is None:
        return True
    if len(int_str) > len(str(max_val)):
        return False
    if int(int_str) > max_val:
        return False
    return True


def create_rss(db, title, description, **args):
    """Create an RSS item."""
    date_text = time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime())
    rss_id = db.rss.create(**args)
    rss_url = db.config.TRACKER_WEB + 'rss' + rss_id
    rss_text = ('<item>'
                '<title>%s</title>'
                '<description>%s</description>'
                '<pubDate>%s</pubDate>'
                '<guid isPermaLink="false">%s</guid>'
                '</item>' % (html.escape(title), html.escape(description),
                             html.escape(date_text), html.escape(rss_url)))
    db.rss.set(rss_id, text=rss_text)


def db_file_format_contents(db, cls, file_id):
    """
    Return the format (canonical filename extension) of an uploaded
    file based on its contents, or None if not a known format that
    might be valid for some uploads.
    """
    filename = db.filename(cls, file_id)
    return file_format_contents(filename)


def db_file_extension(db, cls, file_id):
    """
    Return the format (canonical filename extension) of an uploaded
    file based on its filename extension, or None if not a known
    format that might be valid for some uploads.
    """
    name = db.getclass(cls).get(file_id, 'name')
    # If a file somehow has an empty filename, that will be returned
    # as None, but file_extension expects a string.
    if name is None:
        return None
    return file_extension(name)


def db_file_url(db, cls, kind, file_id):
    """
    Return a download URL of an uploaded file.  If the specified id is
    None, return None.
    """
    url = None
    if file_id is not None:
        ext = db_file_extension(db, cls, file_id)
        if ext is not None:
            url = '%s%s%s/%s.%s' % (db.config.TRACKER_WEB, cls, file_id, kind,
                                    ext)
    return url


def bulk_csv_delimiter(form):
    """Return the delimiter of a previously uploaded CSV file."""
    if 'csv_delimiter' in form:
        delimiter = form['csv_delimiter'].value
        if delimiter in (',', ';'):
            return delimiter
    return ','


def bulk_csv_data(form, comma_sep_fields=()):
    """
    Return the rows of an uploaded CSV file, in a tuple with a boolean
    for whether just to check the results or act on them, or a string
    error message.
    """
    # A csv_file form input with nonempty filename means data has been
    # uploaded for initial checking.  A csv_contents form input means
    # the previously checked data has been submitted for actual bulk
    # registration (but should still be rechecked rather than trusting
    # the client).
    if 'csv_file' in form and form['csv_file'].filename != '':
        check_only = True
        file_bytes = form['csv_file'].value
        if not isinstance(file_bytes, bytes):
            return 'csv_file not an uploaded file'
    elif 'csv_contents' in form:
        check_only = False
        file_base64_str = form['csv_contents'].value
        if not isinstance(file_base64_str, str):
            return 'csv_contents an uploaded file'
        try:
            file_bytes = base64.b64decode(file_base64_str, validate=True)
        except (ValueError, binascii.Error) as exc:
            return str(exc)
    else:
        return 'no CSV file uploaded'
    delimiter = bulk_csv_delimiter(form)
    try:
        file_data = read_utf8_csv_bytes(file_bytes, delimiter=delimiter)
    except (UnicodeError, csv.Error) as exc:
        return str(exc)
    # For user convenience, strip leading and trailing whitespace
    # from CSV file fields.  Remove empty fields.
    for row in file_data:
        for key in list(row.keys()):
            row[key] = row[key].strip()
            if row[key] == '':
                del row[key]
            elif key in comma_sep_fields:
                # Convert comma-separated fields into lists.  Entries
                # in such lists must be unique.
                try:
                    sub_row = comma_split(row[key])
                except (ValueError, csv.Error) as exc:
                    return str(exc)
                row[key] = [val.strip() for val in sub_row]
                if len(row[key]) != len(set(row[key])):
                    return 'duplicate entries in %s' % key
    return (file_data, check_only)


def bulk_csv_contact_emails(row):
    """Return main and extra contact emails from an uploaded CSV."""
    contact_email = row.get('Contact Email 1', '')
    if contact_email:
        contact_list = [contact_email]
        n = 2
        while ('Contact Email %d' % n) in row:
            contact_list.append(row['Contact Email %d' % n])
            n += 1
        return contact_list
    else:
        return []


def bulk_csv_country_number_url(db, row):
    """
    Return the country number and previous participation URL for a
    bulk-registered country.
    """
    country_number = row.get('Country Number', '')
    if country_number and valid_int_str(country_number, None):
        gubase = db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
        return (int(country_number),
                '%scountries/country%s/' % (gubase, country_number))
    else:
        return None, None


def bulk_csv_person_number_url(db, row):
    """
    Return the person number and previous participation URL for a
    bulk-registered person.
    """
    person_number = row.get('Person Number', '')
    if person_number and valid_int_str(person_number, None):
        gubase = db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
        return (int(person_number),
                '%speople/person%s/' % (gubase, person_number))
    else:
        return None, None


def upload_path_from_hash(db, hashstr):
    """
    Return the path to use for an uploaded file, creating any required
    directories.  This is used to stash uploaded ZIP files between the
    first and second stages of bulk registration.  At present, such
    uploaded files are never deleted once created.
    """
    db_path = db.config.DATABASE
    upload_path = os.path.join(db_path, 'upload')
    os.makedirs(upload_path, exist_ok=True)
    return os.path.join(upload_path, hashstr)


def bulk_zip_data(db, form):
    """
    Return a ZipFile object for an uploaded ZIP file, or None if no
    such file was uploaded, or a string on error.
    """
    # A zip_file form input with nonempty filename means a ZIP file
    # has been uploaded now.  A nonempty zip_ref form input refers to
    # such a file previously uploaded.
    if 'zip_file' in form and form['zip_file'].filename != '':
        file_bytes = form['zip_file'].value
        if not isinstance(file_bytes, bytes):
            return 'zip_file not an uploaded file'
        hashstr = hashlib.sha256(file_bytes).hexdigest()
        file_path = upload_path_from_hash(db, hashstr)
        if not os.access(file_path, os.F_OK):
            with open(file_path, 'wb') as file:
                file.write(file_bytes)
        try:
            return zipfile.ZipFile(file_path)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError,
                ValueError, NotImplementedError, EOFError) as exc:
            return str(exc)
    elif 'zip_ref' in form and form['zip_ref'].value != '':
        hashstr = form['zip_ref'].value
        if not isinstance(hashstr, str):
            return 'zip_ref an uploaded file'
        if not re.fullmatch('[0-9a-f]{64}', hashstr):
            return 'zip_ref not a valid hash'
        file_path = upload_path_from_hash(db, hashstr)
        if not os.access(file_path, os.F_OK):
            return 'zip_ref not a known hash'
        try:
            return zipfile.ZipFile(file_path)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError,
                ValueError, NotImplementedError, EOFError) as exc:
            return str(exc)
    else:
        return None


def country_from_code(db, code):
    """Return the country with a given code, where there must be one."""
    countries_with_code = db.country.filter(
        None, {}, exact_match_spec={'code': code})
    if len(countries_with_code) == 1:
        return countries_with_code[0]
    else:
        raise ValueError('country %s not registered' % code)
