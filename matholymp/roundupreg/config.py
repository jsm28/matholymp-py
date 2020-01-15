# Configuration for Roundup registration system for matholymp package.

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
This module provides access to configuration settings for the Roundup
registration system.
"""

import datetime

from matholymp.datetimeutil import date_from_ymd_iso
from matholymp.fileutil import boolean_states

__all__ = ['distinguish_official', 'get_consent_forms_date_str',
           'get_consent_forms_date', 'have_consent_forms', 'have_consent_ui',
           'have_passport_numbers', 'have_nationality', 'require_diet',
           'require_dob', 'get_num_problems', 'get_marks_per_problem',
           'get_num_languages', 'get_language_numbers',
           'get_earliest_date_of_birth', 'get_sanity_date_of_birth',
           'get_earliest_date_of_birth_contestant', 'get_arrdep_bounds',
           'get_staff_country_name', 'invitation_letter_register']


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


def invitation_letter_register(db):
    """
    Return whether registering users can generate invitation letters
    for participants from their country.
    """
    inv_letter = db.config.ext['MATHOLYMP_INVITATION_LETTER_REGISTER']
    return boolean_states[inv_letter.lower()]
