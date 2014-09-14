# CSVDataSource class for matholymp package.

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
This module provides the CSVDataSource class that uses CSV files to
provide the source data about events and the people and countries
involved in them from which other data is derived.
"""

from matholymp.data import Paper
from matholymp.datasource import DataSource

__all__ = ['CSVDataSource']

class CSVDataSource(DataSource):

    """Subclass of DataSource providing information from CSV files."""

    def __init__(self, cfg, events, papers, countries, people):
        """
        Initialise a CSVDataSource from the given configuration
        information and arrays of dicts from CSV files.
        """
        self._cfg = cfg
        self._events = {}
        self._papers = {}
        self._countries = {}
        self._people = {}
        if events is None:
            # Data direct from registration system used for generating
            # documents; no CSV file of event data.
            eid = cfg['event_number']
            e = {}
            e['Year'] = cfg['year']
            e['Number of Exams'] = str(cfg['num_exams'])
            e['Number of Problems'] = str(cfg['num_problems'])
            e['Gold Boundary'] = (cfg['gold_boundary'] is not None and
                                  str(cfg['gold_boundary']) or '')
            e['Silver Boundary'] = (cfg['silver_boundary'] is not None and
                                    str(cfg['silver_boundary']) or '')
            e['Bronze Boundary'] = (cfg['bronze_boundary'] is not None and
                                    str(cfg['bronze_boundary']) or '')
            marks_per_problem = cfg['marks_per_problem'].split()
            for i in range(int(cfg['num_problems'])):
                e['P%d Max' % (i + 1)] = marks_per_problem[i]
            self._events[eid] = e
            self._papers[eid] = []
            self._countries[eid] = {}
            self._people[eid] = {}
        else:
            for e in events:
                eid = int(e['Number'])
                if eid in self._events:
                    raise ValueError('duplicate event %d' % eid)
                self._events[eid] = e
                self._papers[eid] = []
                self._countries[eid] = {}
                self._people[eid] = {}
        for p in papers:
            eid = int(p[cfg['num_key']])
            self._papers[eid].append(Paper(int(p['Day']), p['Language'],
                                           p['Description'], p['URL']))
        self._country_ids = set()
        for c in countries:
            eid = int(c[cfg['num_key']])
            cid = int(c['Country Number'])
            self._country_ids.add(cid)
            if cid in self._countries[eid]:
                raise ValueError('duplicate event %d country %d' % (eid, cid))
            self._countries[eid][cid] = c
        self._person_ids = set()
        for p in people:
            eid = int(p[cfg['num_key']])
            pid = int(p['Person Number'])
            self._person_ids.add(pid)
            if pid in self._people[eid]:
                raise ValueError('duplicate event %d person %d' % (eid, pid))
            self._people[eid][pid] = p

    def event_group_get_attr(self, name):
        if name in ('short_name', 'short_name_plural', 'long_name',
                    'distinguish_official', 'rank_top_n'):
            return self._cfg[name]
        if name == '_event_ids':
            return list(self._events.keys())
        if name == '_person_ids':
            return list(self._person_ids)
        if name == '_country_ids':
            return list(self._country_ids)
        raise KeyError(name)

    def event_exists(self, id):
        return id in self._events

    def person_exists(self, id):
        return id in self._person_ids

    def country_exists(self, id):
        return id in self._country_ids

    def person_event_exists(self, person_id, event_id):
        return person_id in self._people[event_id]

    def country_event_exists(self, country_id, event_id):
        return country_id in self._countries[event_id]

    _event_attr_map_str = { 'year': 'Year',
                            'host_country_name': 'Country',
                            'host_city': 'City',
                            'start_date': 'Start Date',
                            'end_date': 'End Date',
                            'home_page_url': 'Home Page URL',
                            'contact_name': 'Contact Name',
                            'contact_email': 'Contact Email' }

    _event_attr_map_int = { '_host_country_id': 'Country Number',
                            'num_exams': 'Number of Exams',
                            'num_problems': 'Number of Problems',
                            'gold_boundary': 'Gold Boundary',
                            'silver_boundary': 'Silver Boundary',
                            'bronze_boundary': 'Bronze Boundary' }

    def event_get_attr(self, id, name):
        if name in CSVDataSource._event_attr_map_str:
            s = self._events[id][CSVDataSource._event_attr_map_str[name]]
            if s == '':
                s = None
            return s
        if name in CSVDataSource._event_attr_map_int:
            s = self._events[id][CSVDataSource._event_attr_map_int[name]]
            if s == '':
                return None
            else:
                return int(s)
        if name == 'marks_per_problem':
            np = int(self._events[id]['Number of Problems'])
            return [int(self._events[id]['P%d Max' % (n + 1)])
                    for n in range(np)]
        if name == 'registration_active':
            return id == self._cfg['event_active_number']
        if name == 'paper_list':
            return self._papers[id]
        if name == '_person_ids':
            return list(self._people[id].keys())
        if name == '_country_ids':
            return list(self._countries[id].keys())
        raise KeyError(name)

    _person_event_attr_map_str = { 'annual_url': 'Annual URL',
                                   'primary_role': 'Primary Role',
                                   'given_name': 'Given Name',
                                   'family_name': 'Family Name',
                                   'award': 'Award',
                                   'photo_url': 'Photo URL',
                                   'first_language': 'First Language',
                                   'second_language': 'Second Language',
                                   'diet': 'Dietary Requirements',
                                   'room_number': 'Room Number',
                                   'phone_number': 'Phone Number',
                                   'gender': 'Gender',
                                   'date_of_birth': 'Date of Birth',
                                   'tshirt': 'T-Shirt Size',
                                   'arrival_place': 'Arrival Place',
                                   'arrival_time': 'Arrival Time',
                                   'arrival_flight': 'Arrival FLight',
                                   'departure_place': 'Departure Place',
                                   'departure_time': 'Departure Time',
                                   'departure_flight': 'Departure FLight' }

    _person_event_attr_map_int = { '_country_id': 'Country Number',
                                   'contestant_age': 'Contestant Age',
                                   'total_score': 'Total',
                                   'generic_id': 'Generic Number' }

    def person_event_get_attr(self, person_id, event_id, name):
        if name in CSVDataSource._person_event_attr_map_str:
            k = CSVDataSource._person_event_attr_map_str[name]
            s = self._people[event_id][person_id][k]
            if s == '':
                s = None
            return s
        if name in CSVDataSource._person_event_attr_map_int:
            k = CSVDataSource._person_event_attr_map_int[name]
            s = self._people[event_id][person_id][k]
            if s == '':
                return None
            else:
                return int(s)
        if name == 'other_roles':
            s = self._people[event_id][person_id]['Other Roles']
            if s == '':
                return []
            return s.split(',')
        if name == '_guide_for_ids':
            s = self._people[event_id][person_id]['Guide For']
            if s == '':
                return []
            cnames = s.split(',')
            r = []
            ce = self._countries[event_id].values()
            for cn in cnames:
                cl = [int(c['Country Number']) for c in ce if c['Name'] == cn]
                if len(cl) != 1:
                    raise ValueError('bad number of countries called %s' % cn)
                r.extend(cl)
            return r
        if name == 'problem_scores':
            r = []
            for n in range(int(self._events[event_id]['Number of Problems'])):
                s = self._people[event_id][person_id]['P%d' % (n+1)]
                if s == '':
                    s = None
                else:
                    s = int(s)
                r.append(s)
            return r
        raise KeyError(name)

    def person_event_have_attr(self, person_id, event_id, name):
        return True

    _country_event_attr_map_str = { 'annual_url': 'Annual URL',
                                    'code': 'Code',
                                    'name': 'Name',
                                    'flag_url': 'Flag URL' }

    _country_event_attr_map_int = { 'generic_id': 'Generic Number' }

    def country_event_get_attr(self, country_id, event_id, name):
        if name in CSVDataSource._country_event_attr_map_str:
            k = CSVDataSource._country_event_attr_map_str[name]
            s = self._countries[event_id][country_id][k]
            if s == '':
                s = None
            return s
        if name in CSVDataSource._country_event_attr_map_int:
            k = CSVDataSource._country_event_attr_map_int[name]
            s = self._countries[event_id][country_id][k]
            if s == '':
                return None
            else:
                return int(s)
        if name == 'is_official':
            k = self._cfg['official_desc']
            s = self._countries[event_id][country_id][k]
            if s == 'Yes':
                return True
            if s == 'No':
                return False
            raise ValueError('unexpected official setting %s', s)
        raise KeyError(name)
