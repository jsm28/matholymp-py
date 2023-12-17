# Utility functions for Roundup registration system for matholymp package.

# Copyright 2014-2023 Joseph Samuel Myers.

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

import html
import re
import time

from matholymp.datetimeutil import date_from_ymd_str, age_on_date
from matholymp.fileutil import file_format_contents, file_extension
from matholymp.roundupreg.config import get_num_problems, get_age_day_date, \
    event_type

__all__ = ['scores_from_str', 'person_date_of_birth', 'contestant_age',
           'person_is_contestant', 'contestant_code', 'pn_score',
           'scores_final', 'any_scores_missing', 'country_has_contestants',
           'valid_country_problem', 'valid_int_str', 'create_rss',
           'db_file_format_contents', 'db_file_extension', 'db_file_url',
           'country_from_code', 'person_is_remote', 'registration_enabled',
           'show_scores']


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


def country_from_code(db, code):
    """Return the country with a given code, where there must be one."""
    countries_with_code = db.country.filter(
        None, {}, exact_match_spec={'code': code})
    if len(countries_with_code) == 1:
        return countries_with_code[0]
    else:
        raise ValueError('country %s not registered' % code)


def person_is_remote(db, person, override=None):
    """Determine whether a person is a remote participant."""
    this_event_type = event_type(db)
    if this_event_type == 'in-person':
        return False
    elif this_event_type == 'virtual':
        return True
    if override is None:
        override = {}
    if 'participation_type' in override:
        val = override['participation_type']
    elif person is None:
        val = None
    else:
        val = db.person.get(person, 'participation_type')
    if val == 'in-person':
        return False
    elif val == 'virtual':
        return True
    else:
        return None


def registration_enabled(db, userid):
    """
    Determine whether registration is enabled for a given user.  The
    result is only of significance for a user with some kind of
    registration permissions.
    """
    return (db.security.hasPermission('RegisterAnyTime', userid)
            or db.event.get('1', 'registration_enabled'))


def show_scores(db, userid):
    """Determine whether scores are displayed."""
    return (db.security.hasPermission('ViewScores', userid)
            or not db.event.get('1', 'hide_scores_message')
            or scores_final(db))
