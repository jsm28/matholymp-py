# Utility functions for Roundup registration system for matholymp package.

# Copyright 2014-2019 Joseph Samuel Myers.

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
import cgi
import csv
import datetime
import re
import time

from matholymp.datetimeutil import date_from_ymd_str, date_from_ymd_iso, \
    age_on_date
from matholymp.fileutil import read_utf8_csv_bytes, boolean_states, \
    file_format_contents, file_extension

__all__ = ['distinguish_official', 'get_consent_forms_date_str',
           'get_consent_forms_date', 'have_consent_forms', 'have_consent_ui',
           'have_passport_numbers', 'have_nationality', 'require_diet',
           'require_dob', 'get_num_problems', 'get_marks_per_problem',
           'scores_from_str', 'get_num_languages', 'get_language_numbers',
           'get_earliest_date_of_birth', 'get_sanity_date_of_birth',
           'get_earliest_date_of_birth_contestant', 'person_date_of_birth',
           'contestant_age', 'get_arrdep_bounds', 'get_staff_country_name',
           'person_is_contestant', 'contestant_code', 'pn_score',
           'scores_final', 'any_scores_missing', 'country_has_contestants',
           'valid_country_problem', 'valid_int_str', 'create_rss',
           'db_file_format_contents', 'db_file_extension', 'db_file_url',
           'bulk_csv_data', 'bulk_csv_contact_emails',
           'bulk_csv_country_number_url']


def distinguish_official(db):
    """Return whether this event distinguishes official countries."""
    dist_off = db.config.ext['MATHOLYMP_DISTINGUISH_OFFICIAL']
    return boolean_states[dist_off.lower()]


def get_consent_forms_date_str(db):
    """
    Return the earliest date of birth for which participants require
    consent forms, as a string, or the empty string if not required.
    """
    return db.config.ext['MATHOLYMP_CONSENT_FORMS_DATE']


def get_consent_forms_date(db):
    """
    Return the earliest date of birth for which participants require
    consent forms, as a datetime.date object, or None if not required.
    """
    s = get_consent_forms_date_str(db)
    if s == '':
        return None
    else:
        return date_from_ymd_iso('consent forms date', s)


def have_consent_forms(db):
    """Return whether this event has consent forms."""
    return get_consent_forms_date_str(db) != ''


def have_consent_ui(db):
    """Return whether this event collects additional consent information."""
    consent_ui = db.config.ext['MATHOLYMP_CONSENT_UI']
    return boolean_states[consent_ui.lower()]


def have_passport_numbers(db):
    """
    Return whether passport or identity card numbers are collected for
    this event.
    """
    req_passport = db.config.ext['MATHOLYMP_REQUIRE_PASSPORT_NUMBER']
    return boolean_states[req_passport.lower()]


def have_nationality(db):
    """Return whether nationalities are collected for this event."""
    req_nationality = db.config.ext['MATHOLYMP_REQUIRE_NATIONALITY']
    return boolean_states[req_nationality.lower()]


def require_diet(db):
    """
    Return whether dietary requirements information is required for
    all participants.
    """
    req_diet = db.config.ext['MATHOLYMP_REQUIRE_DIET']
    return boolean_states[req_diet.lower()]


def require_dob(db):
    """Return whether date of birth is required for all participants."""
    req_dob = db.config.ext['MATHOLYMP_REQUIRE_DATE_OF_BIRTH']
    return boolean_states[req_dob.lower()]


def get_num_problems(db):
    """Return the number of problems at this event."""
    return int(db.config.ext['MATHOLYMP_NUM_PROBLEMS'])


def get_marks_per_problem(db):
    """Return the number of marks for each problem at this event."""
    marks_per_problem = db.config.ext['MATHOLYMP_MARKS_PER_PROBLEM']
    marks_per_problem = marks_per_problem.split()
    return [int(m) for m in marks_per_problem]


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


def get_num_languages(db):
    """Return the maximum number of languages for a person at this event."""
    return int(db.config.ext['MATHOLYMP_NUM_LANGUAGES'])


def get_language_numbers(db):
    """Return the numbers of language database properties for a person."""
    return range(1, get_num_languages(db) + 1)


def get_earliest_date_of_birth(db):
    """Return the earliest date of birth allowed for any participant."""
    # Avoid problems with strftime by disallowing dates before 1902.
    return datetime.date(1902, 1, 1)


def get_sanity_date_of_birth(db):
    """
    Return a date of birth such that participants may not be born on
    or after that date.
    """
    return date_from_ymd_iso('sanity date of birth',
                             db.config.ext['MATHOLYMP_SANITY_DATE_OF_BIRTH'])


def get_earliest_date_of_birth_contestant(db):
    """Return the earliest date of birth allowed for contestants."""
    return date_from_ymd_iso('earliest date of birth for contestants',
                             db.config.ext['MATHOLYMP_EARLIEST_DATE_OF_BIRTH'])


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
    date2 = date_from_ymd_iso('age day date',
                              db.config.ext['MATHOLYMP_AGE_DAY_DATE'])
    return age_on_date(date1, date2)


_early_vars = {'arrival': 'MATHOLYMP_EARLIEST_ARRIVAL_DATE',
               'departure': 'MATHOLYMP_EARLIEST_DEPARTURE_DATE'}
_late_vars = {'arrival': 'MATHOLYMP_LATEST_ARRIVAL_DATE',
              'departure': 'MATHOLYMP_LATEST_DEPARTURE_DATE'}


def get_arrdep_bounds(db, kind):
    """Return the bounds on arrival or departure dates."""
    early_var = _early_vars[kind]
    late_var = _late_vars[kind]
    early_date = date_from_ymd_iso('earliest %s date' % kind,
                                   db.config.ext[early_var])
    late_date = date_from_ymd_iso('latest %s date' % kind,
                                  db.config.ext[late_var])
    return (early_date, late_date)


def get_staff_country_name(db):
    """Return the name of the special staff country."""
    short_name = db.config.ext['MATHOLYMP_SHORT_NAME']
    year = db.config.ext['MATHOLYMP_YEAR']
    return short_name + ' ' + year + ' Staff'


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
    if not re.match('^[1-9][0-9]*\\Z', problem):
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
    if int_str != '0' and not re.match('^[1-9][0-9]*\\Z', int_str):
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
                '</item>' % (cgi.escape(title), cgi.escape(description),
                             cgi.escape(date_text), cgi.escape(rss_url)))
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


def bulk_csv_data(form):
    """
    Return the rows of an uploaded CSV file, in a tuple with a boolean
    for whether just to check the results or act on them, or a string
    error message.
    """
    # A csv_file form input means data has been uploaded for initial
    # checking.  A csv_contents form input means the previously
    # checked data has been submitted for actual bulk registration
    # (but should still be rechecked rather than trusting the client).
    if 'csv_file' in form:
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
    try:
        file_data = read_utf8_csv_bytes(file_bytes)
    except (UnicodeError, csv.Error) as exc:
        return str(exc)
    # For user convenience, strip leading and trailing whitespace
    # from CSV file fields.  Remove empty fields.
    for row in file_data:
        for key in list(row.keys()):
            row[key] = row[key].strip()
            if row[key] == '':
                del row[key]
    return (file_data, check_only)


def bulk_csv_contact_emails(row):
    """Return main and extra contact emails from an uploaded countries CSV."""
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
