# RoundupDataSource class for matholymp package.

# Copyright 2014-2017 Joseph Samuel Myers.

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
This module provides the RoundupSource class that uses Roundup
interfaces to provide the source data about events and the people and
countries involved in them from which other data is derived.
"""

from matholymp.datasource import DataSource
from matholymp.datetimeutil import date_from_ymd_iso, time_from_hhmm_str
from matholymp.fileutil import comma_split, boolean_states
from matholymp.roundupreg.rounduputil import distinguish_official, \
    have_consent_forms, have_passport_numbers, have_nationality, \
    get_num_problems, get_marks_per_problem, scores_from_str, \
    person_date_of_birth, contestant_age, db_file_extension, \
    db_private_file_extension

__all__ = ['RoundupDataSource']

class RoundupDataSource(DataSource):

    """Subclass of DataSource providing information from Roundup."""

    def __init__(self, db):
        """
        Initialise a RoundupDataSource given the db object for that
        Roundup instance (db._db, when accessed within page
        templates).
        """
        self._db = db

    def event_group_get_attr(self, name):
        if name == 'short_name':
            return self._db.config.ext['MATHOLYMP_SHORT_NAME']
        elif name == 'distinguish_official':
            return distinguish_official(self._db)
        elif name == 'rank_top_n':
            s = self._db.config.ext['MATHOLYMP_RANK_TOP_N']
            if s:
                return int(s)
            else:
                return None
        elif name == 'honourable_mentions_available':
            hm_avail = self._db.config.ext['MATHOLYMP_HONOURABLE_'
                                           'MENTIONS_AVAILABLE']
            return boolean_states[hm_avail.lower()]
        elif name == '_event_ids':
            return [int(self._db.config.ext['MATHOLYMP_EVENT_NUMBER'])]
        elif name == '_person_ids':
            return [int(p) for p in self._db.person.list()]
        elif name == '_country_ids':
            return [int(c) for c in self._db.country.list()
                    if self._db.country.get(c, 'participants_ok')]
        raise KeyError(name)

    def event_exists(self, id):
        return self._db.config.ext['MATHOLYMP_EVENT_NUMBER'] == str(id)

    def person_exists(self, id):
        id = str(id)
        return (self._db.person.hasnode(id) and
                not self._db.person.is_retired(id))

    def country_exists(self, id):
        id = str(id)
        return (self._db.country.hasnode(id) and
                not self._db.country.is_retired(id) and
                self._db.country.get(id, 'participants_ok'))

    def person_event_exists(self, person_id, event_id):
        return self.person_exists(person_id)

    def country_event_exists(self, country_id, event_id):
        return self.country_exists(country_id)

    def event_get_attr(self, id, name):
        if name == 'num_problems':
            return get_num_problems(self._db)
        elif name == 'marks_per_problem':
            return get_marks_per_problem(self._db)
        elif name == 'gold_boundary':
            gold = self._db.event.get('1', 'gold')
            if gold is None or gold == '':
                return None
            return int(gold)
        elif name == 'silver_boundary':
            silver = self._db.event.get('1', 'silver')
            if silver is None or silver == '':
                return None
            return int(silver)
        elif name == 'bronze_boundary':
            bronze = self._db.event.get('1', 'bronze')
            if bronze is None or bronze == '':
                return None
            return int(bronze)
        elif name == '_person_ids':
            return [int(p) for p in self._db.person.list()]
        elif name == '_country_ids':
            return [int(c) for c in self._db.country.list()
                    if self._db.country.get(c, 'participants_ok')]
        raise KeyError(name)

    def person_event_get_attr(self, person_id, country_id, event_id, name):
        id = str(person_id)
        if name == '_country_ids':
            assert country_id is None
            return [int(self._db.person.get(id, 'country'))]
        assert country_id is not None
        if name == 'annual_url':
            return self._db.config.TRACKER_WEB + 'person' + id
        elif name == 'primary_role':
            primary_role = self._db.person.get(id, 'primary_role')
            return self._db.matholymprole.get(primary_role, 'name')
        elif name == 'other_roles':
            other_roles = self._db.person.get(id, 'other_roles')
            if other_roles is None:
                other_roles = []
            primary_role = self._db.person.get(id, 'primary_role')
            other_roles = [i for i in other_roles if i != primary_role]
            return [self._db.matholymprole.get(i, 'name') for i in other_roles]
        elif name == '_guide_for_ids':
            guide_for = self._db.person.get(id, 'guide_for')
            if guide_for is None:
                guide_for = []
            return [int(c) for c in guide_for]
        elif name == 'contestant_age':
            return contestant_age(self._db, id)
        elif name == 'given_name':
            return self._db.person.get(id, 'given_name')
        elif name == 'family_name':
            return self._db.person.get(id, 'family_name')
        elif name == 'problem_scores':
            score_str = self._db.person.get(id, 'scores')
            scores = scores_from_str(self._db, score_str)
            r = []
            for s in scores:
                if s == '':
                    s = None
                else:
                    s = int(s)
                r.append(s)
            return r
        elif name == 'extra_awards':
            extra_awards_str = self._db.person.get(id, 'extra_awards')
            if extra_awards_str is None:
                return []
            return comma_split(extra_awards_str)
        elif name == 'photo_url':
            photo_id = self._db.person.get(id, 'files')
            photo_url = None
            if photo_id is not None:
                photo_ext = db_file_extension(self._db, photo_id)
                if photo_ext is not None:
                    photo_url = (self._db.config.TRACKER_WEB + 'file' +
                                 photo_id + '/photo.' + photo_ext)
            return photo_url
        elif name == 'photo_filename':
            photo_id = self._db.person.get(id, 'files')
            photo_filename = None
            if photo_id is not None:
                photo_filename = self._db.filename('file', photo_id)
            return photo_filename
        elif name == 'consent_form_url':
            if not have_consent_forms(self._db):
                return None
            consent_form_id = self._db.person.get(id, 'consent_form')
            consent_form_url = None
            if consent_form_id is not None:
                consent_form_ext = db_private_file_extension(self._db,
                                                             consent_form_id)
                if consent_form_ext is not None:
                    consent_form_url = (self._db.config.TRACKER_WEB +
                                        'private_file' + consent_form_id +
                                        '/consent-form.' + consent_form_ext)
            return consent_form_url
        elif name == 'consent_form_filename':
            if not have_consent_forms(self._db):
                return None
            consent_form_id = self._db.person.get(id, 'consent_form')
            consent_form_filename = None
            if consent_form_id is not None:
                consent_form_filename = self._db.filename('private_file',
                                                          consent_form_id)
            return consent_form_filename
        elif name == 'languages':
            first_language = self._db.person.get(id, 'first_language')
            first_language_name = self._db.language.get(first_language, 'name')
            second_language = self._db.person.get(id, 'second_language')
            if second_language is None or second_language == first_language:
                return [first_language_name]
            return [first_language_name,
                    self._db.language.get(second_language, 'name')]
        elif name == 'diet':
            return self._db.person.get(id, 'diet') or None
        elif name == 'room_number':
            return self._db.person.get(id, 'room_number') or None
        elif name == 'phone_number':
            return self._db.person.get(id, 'phone_number') or None
        elif name == 'generic_id':
            generic_url = self._db.person.get(id, 'generic_url')
            gubase = (self._db.config.ext['MATHOLYMP_GENERIC_URL_BASE'] +
                      'people/person')
            if (generic_url is None or not generic_url.startswith(gubase) or
                not generic_url.endswith('/')):
                generic_id = None
            else:
                generic_id = int(generic_url[len(gubase):-1])
            return generic_id
        elif name == 'gender':
            gender = self._db.person.get(id, 'gender')
            return self._db.gender.get(gender, 'name')
        elif name == 'date_of_birth':
            return person_date_of_birth(self._db, id)
        elif name == 'passport_number':
            if not have_passport_numbers(self._db):
                return None
            return self._db.person.get(id, 'passport_number') or None
        elif name == 'nationality':
            if not have_nationality(self._db):
                return None
            return self._db.person.get(id, 'nationality') or None
        elif name == 'tshirt':
            tshirt = self._db.person.get(id, 'tshirt')
            return self._db.tshirt.get(tshirt, 'name')
        elif name == 'arrival_place':
            arrival_place = self._db.person.get(id, 'arrival_place')
            if arrival_place is None:
                return None
            else:
                return self._db.arrival.get(arrival_place, 'name')
        elif name == 'arrival_date':
            date = self._db.person.get(id, 'arrival_date')
            if date is None:
                return None
            else:
                return date_from_ymd_iso('arrival date', date)
        elif name == 'arrival_time':
            hour = self._db.person.get(id, 'arrival_time_hour')
            minute = self._db.person.get(id, 'arrival_time_minute')
            if hour is None or minute is None:
                return None
            else:
                return time_from_hhmm_str('arrival time', hour, minute)
        elif name == 'arrival_flight':
            return self._db.person.get(id, 'arrival_flight') or None
        elif name == 'departure_place':
            departure_place = self._db.person.get(id, 'departure_place')
            if departure_place is None:
                return None
            else:
                return self._db.arrival.get(departure_place, 'name')
        elif name == 'departure_date':
            date = self._db.person.get(id, 'departure_date')
            if date is None:
                return None
            else:
                return date_from_ymd_iso('departure date', date)
        elif name == 'departure_time':
            hour = self._db.person.get(id, 'departure_time_hour')
            minute = self._db.person.get(id, 'departure_time_minute')
            if hour is None or minute is None:
                return None
            else:
                return time_from_hhmm_str('departure time', hour, minute)
        elif name == 'departure_flight':
            return self._db.person.get(id, 'departure_flight') or None
        raise KeyError(name)

    def country_event_get_attr(self, country_id, event_id, name):
        id = str(country_id)
        if name == 'annual_url':
            return self._db.config.TRACKER_WEB + 'country' + id
        elif name == 'code':
            return self._db.country.get(id, 'code')
        elif name == 'name':
            return self._db.country.get(id, 'name')
        elif name == 'flag_url':
            flag_id = self._db.country.get(id, 'files')
            flag_url = None
            if flag_id is not None:
                flag_ext = db_file_extension(self._db, flag_id)
                if flag_ext is not None:
                    flag_url = (self._db.config.TRACKER_WEB + 'file' +
                                flag_id + '/flag.' + flag_ext)
            return flag_url
        elif name == 'flag_filename':
            flag_id = self._db.country.get(id, 'files')
            flag_filename = None
            if flag_id is not None:
                flag_filename = self._db.filename('file', flag_id)
            return flag_filename
        elif name == 'is_official':
            return self._db.country.get(id, 'official')
        elif name == 'is_normal':
            return self._db.country.get(id, 'is_normal')
        elif name == '_person_ids':
            person_list = self._db.person.filter(None, {'country': id})
            return [int(p) for p in person_list]
        elif name == '_guide_ids':
            guide_list = self._db.person.filter(None, {'guide_for': id})
            return [int(p) for p in guide_list]
        elif name == 'generic_id':
            generic_url = self._db.country.get(id, 'generic_url')
            gubase = (self._db.config.ext['MATHOLYMP_GENERIC_URL_BASE'] +
                      'countries/country')
            if (generic_url is None or not generic_url.startswith(gubase) or
                not generic_url.endswith('/')):
                generic_id = None
            else:
                generic_id = int(generic_url[len(gubase):-1])
            return generic_id
        raise KeyError(name)

    def country_event_have_attr(self, country_id, event_id, name):
        return True
