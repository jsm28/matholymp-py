# Utility functions for Roundup registration system for matholymp package.

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
This module provides various utility functions for the Roundup
registration system.
"""

import cgi
import re
import time

from roundup.date import Date

from matholymp.fileutil import boolean_states, file_format_contents, \
    file_extension

__all__ = ['distinguish_official', 'get_num_problems', 'get_marks_per_problem',
           'scores_from_str', 'contestant_age', 'get_none_country_name',
           'get_none_country', 'get_staff_country_name', 'get_staff_country',
           'normal_country_person', 'person_is_contestant', 'contestant_code',
           'pn_score', 'scores_final', 'any_scores_missing',
           'country_has_contestants', 'valid_country_problem', 'valid_score',
           'create_rss', 'db_file_format_contents', 'db_file_extension']

def distinguish_official(db):
    """Return whether this event distinguishes official countries."""
    dist_off = db.config.ext['MATHOLYMP_DISTINGUISH_OFFICIAL']
    return boolean_states[dist_off.lower()]

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

def contestant_age(db, person):
    """Return the age of a contestant on the configured day."""
    date1 = db.person.get(person, 'date_of_birth')
    date2 = Date(db.config.ext['MATHOLYMP_AGE_DAY_DATE'])
    date1t = date1.get_tuple()
    date2t = date2.get_tuple()
    diff = date2t[0] - date1t[0]
    if (date2t[1] < date1t[1]) or (date2t[1] == date1t[1] and
                                   date2t[2] < date1t[2]):
        diff -= 1
    return diff

def get_none_country_name(db):
    """Return the name of the special 'None' country."""
    return 'None'

def get_none_country(db):
    """Return the id of the special 'None' country."""
    return db.country.lookup(get_none_country_name(db))

def get_staff_country_name(db):
    """Return the name of the special staff country."""
    short_name = db.config.ext['MATHOLYMP_SHORT_NAME']
    year = db.config.ext['MATHOLYMP_YEAR']
    return short_name + ' ' + year + ' Staff'

def get_staff_country(db):
    """Return the id of the special staff country."""
    return db.country.lookup(get_staff_country_name(db))

def normal_country_person(db, userid):
    """Determine whether the user is from a normal country."""
    user_country = db.user.get(userid, 'country')
    return (user_country != get_none_country(db) and
            user_country != get_staff_country(db))

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
    return scores[n-1]

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

def valid_score(score_str, max_score):
    """
    Determine whether the score string (for an individual problem or a
    medal boundary) is an integer in the range from 0 to max_score
    inclusive.
    """
    if score_str != '0' and not re.match('^[1-9][0-9]*\\Z', score_str):
        return False
    if len(score_str) > len(str(max_score)):
        return False
    if int(score_str) > max_score:
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

def db_file_format_contents(db, id):
    """
    Return the format (canonical filename extension) of an uploaded
    file based on its contents, or None if not a known format that
    might be valid for some uploads.
    """
    filename = db.filename('file', id)
    return file_format_contents(filename)

def db_file_extension(db, id):
    """
    Return the format (canonical filename extension) of an uploaded
    file based on its filename extension, or None if not a known
    format that might be valid for some uploads.
    """
    name = db.file.get(id, 'name')
    return file_extension(name)
