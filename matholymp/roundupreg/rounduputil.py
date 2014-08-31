# Utility functions for Roundup registration system for matholymp package.

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
This module provides various utility functions for the Roundup
registration system.
"""

import re

from roundup.date import Date

__all__ = ['scores_from_str', 'contestant_age', 'get_none_country',
           'get_staff_country', 'normal_country_person',
           'person_is_contestant', 'contestant_code', 'pn_score',
           'scores_final', 'any_scores_missing', 'country_has_contestants',
           'valid_country_problem']

def scores_from_str(db, score_str):
    """
    Return a list of the scores (strings) for a contestant, given the
    string for their scores stored in the database.
    """
    num_problems = int(db.config.ext['MATHOLYMP_NUM_PROBLEMS'])
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

def get_none_country(db):
    """Return the id of the special 'None' country."""
    return db.country.lookup('None')

def get_staff_country(db):
    """Return the id of the special staff country."""
    short_name = db.config.ext['MATHOLYMP_SHORT_NAME']
    year = db.config.ext['MATHOLYMP_YEAR']
    staff_country_name = short_name + ' ' + year + ' Staff'
    return db.country.lookup(staff_country_name)

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
    num_problems = int(db.config.ext['MATHOLYMP_NUM_PROBLEMS'])
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
    num_problems = int(db.config.ext['MATHOLYMP_NUM_PROBLEMS'])
    country = form['country'].value
    problem = form['problem'].value
    if not re.match('^[1-9][0-9]*\\Z', problem):
        return False
    if int(problem) > num_problems:
        return False
    return country_has_contestants(db, country)
