# RoundupDataSource class for matholymp package.

# Copyright 2014-2015 Joseph Samuel Myers.

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
from matholymp.fileutil import boolean_states
from matholymp.roundupreg.rounduputil import distinguish_official, \
    get_num_problems, get_marks_per_problem, scores_from_str, contestant_age, \
    get_none_country
from matholymp.urlutil import url_quote

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
        # The special country "None" exists to be the country of the
        # anonymous user, but should be ignored for the purposes of
        # the general data model used here.
        self._none_country = None

    def _get_none_country(self):
        if self._none_country is None:
            self._none_country = get_none_country(self._db)

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
            self._get_none_country()
            return [int(c) for c in self._db.country.list()
                    if c != self._none_country]
        raise KeyError(name)

    def event_exists(self, id):
        return self._db.config.ext['MATHOLYMP_EVENT_NUMBER'] == str(id)

    def person_exists(self, id):
        id = str(id)
        return (self._db.person.hasnode(id) and
                not self._db.person.is_retired(id))

    def country_exists(self, id):
        id = str(id)
        self._get_none_country()
        return (id != self._none_country and
                self._db.country.hasnode(id) and
                not self._db.country.is_retired(id))

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
            self._get_none_country()
            return [int(c) for c in self._db.country.list()
                    if c != self._none_country]
        raise KeyError(name)

    def person_event_get_attr(self, person_id, event_id, name):
        id = str(person_id)
        if name == '_country_id':
            return int(self._db.person.get(id, 'country'))
        elif name == 'annual_url':
            return self._db.config.TRACKER_WEB + 'person' + id
        elif name == 'primary_role':
            primary_role = self._db.person.get(id, 'primary_role')
            return self._db.matholymprole.get(primary_role, 'name')
        elif name == 'other_roles':
            other_roles = self._db.person.get(id, 'other_roles')
            if other_roles is None:
                other_roles = []
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
        elif name == 'photo_url':
            photo_id = self._db.person.get(id, 'files')
            if photo_id is None:
                photo_url = None
            else:
                photo_name = self._db.file.get(photo_id, 'name')
                photo_url = (self._db.config.TRACKER_WEB + 'file' + photo_id +
                             '/' + url_quote(photo_name))
            return photo_url
        elif name == 'first_language':
            first_language = self._db.person.get(id, 'first_language')
            return self._db.language.get(first_language, 'name')
        elif name == 'second_language':
            first_language = self._db.person.get(id, 'first_language')
            second_language = self._db.person.get(id, 'second_language')
            if second_language is None or second_language == first_language:
                return None
            return self._db.language.get(second_language, 'name')
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
            date_of_birth = self._db.person.get(id, 'date_of_birth')
            if date_of_birth is None:
                return None
            else:
                return date_of_birth.pretty('%Y-%m-%d')
        elif name == 'tshirt':
            tshirt = self._db.person.get(id, 'tshirt')
            return self._db.tshirt.get(tshirt, 'name')
        elif name == 'arrival_place':
            arrival_place = self._db.person.get(id, 'arrival_place')
            if arrival_place is None:
                return None
            else:
                return self._db.arrival.get(arrival_place, 'name')
        elif name == 'arrival_time':
            arrival_time = self._db.person.get(id, 'arrival_time')
            if arrival_time is None:
                return None
            else:
                return arrival_time.pretty('%Y-%m-%d.%H:%M')
        elif name == 'arrival_flight':
            return self._db.person.get(id, 'arrival_flight') or None
        elif name == 'departure_place':
            departure_place = self._db.person.get(id, 'departure_place')
            if departure_place is None:
                return None
            else:
                return self._db.arrival.get(departure_place, 'name')
        elif name == 'departure_time':
            departure_time = self._db.person.get(id, 'departure_time')
            if departure_time is None:
                return None
            else:
                return departure_time.pretty('%Y-%m-%d.%H:%M')
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
            if flag_id is None:
                flag_url = None
            else:
                flag_name = self._db.file.get(flag_id, 'name')
                flag_url = (self._db.config.TRACKER_WEB + 'file' + flag_id +
                            '/' + url_quote(flag_name))
            return flag_url
        elif name == 'is_official':
            return self._db.country.get(id, 'official')
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
