# Data classes for matholymp package.

# Copyright 2014-2022 Joseph Samuel Myers.

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
This module provides classes that describe events and the people and
countries involved in them, with data provided by a subclass of
DataSource.
"""

import collections.abc

from matholymp.collate import coll_get_sort_key
from matholymp.stats import mean_std_dev, corr_coeff

__all__ = ['EventGroup', 'Event', 'Paper', 'Person', 'PersonEvent',
           'Country', 'CountryEvent']

_award_types = ['Gold Medal', 'Silver Medal', 'Bronze Medal',
                'Honourable Mention']

_award_types_no_hm = ['Gold Medal', 'Silver Medal', 'Bronze Medal']


class _LazyMap(collections.abc.Mapping):

    """A mapping where values are created dynamically."""

    def __init__(self, test_func, get_func, list_func):
        self._dict = {}
        self._test_func = test_func
        self._get_func = get_func
        self._list_func = list_func
        self._not_keys = set()
        self._have_all_keys = False

    def __getitem__(self, key):
        if self._have_all_keys or key in self._dict:
            return self._dict[key]
        if key in self._not_keys:
            raise KeyError(key)
        if self._test_func(key):
            self._dict[key] = self._get_func(key)
            return self._dict[key]
        else:
            self._not_keys.add(key)
            raise KeyError(key)

    def __iter__(self):
        self._ensure_all_keys()
        return self._dict.__iter__()

    def __len__(self):
        self._ensure_all_keys()
        return len(self._dict)

    def _ensure_all_keys(self):
        if not self._have_all_keys:
            for key in self._list_func():
                if key not in self._dict:
                    self._dict[key] = self._get_func(key)
            self._have_all_keys = True


class _PropertyCached(property):

    """
    Common base class for attributes that are cached, and computed if
    not in the cache.
    """

    def __init__(self, name, getter, doc):
        def get_cached(obj):
            if name in obj._cache:
                return obj._cache[name]
            obj._cache[name] = getter(obj)
            return obj._cache[name]
        super().__init__(get_cached, None, None, doc)
        self.__doc__ = doc


class _EventGroupPropertyDS(_PropertyCached):

    """Class for EventGroup attributes that are computed by a DataSource."""

    def __init__(self, name, doc):
        def ds_get(obj):
            return obj._ds.event_group_get_attr(name)
        super().__init__(name, ds_get, doc)


class EventGroup:

    """
    An EventGroup represents a group of related events (instances of
    the same competition in different years), constituting the
    universe on which the matholymp package operates.  The EventGroup,
    and the related Event, Paper, Person, PersonEvent, Country and
    CountryEvent classes, are conceptually read-only after
    initialisation, representing a single state of the universe, and
    new instances are expected to be created if that state changes.
    """

    def __init__(self, datasource):
        """Initialise an EventGroup from the given DataSource."""
        self._ds = datasource
        self._cache = {}
        self.event_map = _LazyMap(self._event_id_test,
                                  self._event_id_get, self._event_id_list)
        """A mapping from the id of an event to the Event object."""
        self.person_map = _LazyMap(self._person_id_test,
                                   self._person_id_get, self._person_id_list)
        """A mapping from the id of a person to the Person object."""
        self.country_map = _LazyMap(self._country_id_test,
                                    self._country_id_get,
                                    self._country_id_list)
        """A mapping from the id of a country to the Country object."""

    short_name = _EventGroupPropertyDS(
        'short_name',
        """
        The abbreviated name (typically all upper-case) for this kind of event.
        """)

    short_name_plural = _EventGroupPropertyDS(
        'short_name_plural',
        """The plural form of the abbreviated name for this kind of event.""")

    long_name = _EventGroupPropertyDS(
        'long_name',
        """The full name for this kind of event.""")

    distinguish_official = _EventGroupPropertyDS(
        'distinguish_official',
        """
        Whether official countries are distinguished at at least some
        of this kind of event.
        """)

    def _get_distinguish_official_varies(self):
        s = {e.distinguish_official for e in self.event_list}
        return len(s) > 1

    distinguish_official_varies = _PropertyCached(
        'distinguish_official_varies', _get_distinguish_official_varies,
        """
        Whether it varies from event to event whether official
        countries are distinguished.
        """)

    rank_top_n = _EventGroupPropertyDS(
        'rank_top_n',
        """
        The number of contestants considered in determining a
        country's rank, or None if all contestants considered.
        """)

    honourable_mentions_available = _EventGroupPropertyDS(
        'honourable_mentions_available',
        """
        Whether the rules of at least some of this kind of event
        include awarding Honourable Mentions to contestants not
        receiving a medal but with a perfect score on at least one
        problem.
        """)

    def _get_honourable_mentions_available_varies(self):
        s = {e.honourable_mentions_available for e in self.event_list}
        return len(s) > 1

    honourable_mentions_available_varies = _PropertyCached(
        'honourable_mentions_available_varies',
        _get_honourable_mentions_available_varies,
        """
        Whether the rules of this kind of event vary from event to
        event as to whether Honourable Mentions can be awarded.
        """)

    def _get_age_day_desc_varies(self):
        s = {e.age_day_desc for e in self.event_list}
        return len(s) > 1

    age_day_desc_varies = _PropertyCached(
        'age_day_desc_varies',
        _get_age_day_desc_varies,
        """
        Whether the description of the day for which contestant ages
        are given varies from event to event.
        """)

    def _get_award_types(self):
        if self.honourable_mentions_available:
            return _award_types
        else:
            return _award_types_no_hm

    _award_types = _PropertyCached(
        '_award_types', _get_award_types,
        """A list of types of award available at this kind of event.""")

    _event_ids = _EventGroupPropertyDS(
        '_event_ids',
        """A list of ids for all events.""")

    def _get_event_list(self):
        return sorted(self.event_map.values(), key=lambda e: e.sort_key)

    event_list = _PropertyCached(
        'event_list', _get_event_list,
        """A list of all events (Event objects), in chronological order.""")

    def _event_id_test(self, event_id):
        return self._ds.event_exists(event_id)

    def _event_id_get(self, event_id):
        return Event(self, event_id)

    def _event_id_list(self):
        return self._event_ids

    _person_ids = _EventGroupPropertyDS(
        '_person_ids',
        """A list of ids for all people.""")

    def _get_person_list(self):
        return list(self.person_map.values())

    person_list = _PropertyCached(
        'person_list', _get_person_list,
        """A list of all people (Person objects).""")

    def _person_id_test(self, person_id):
        return self._ds.person_exists(person_id)

    def _person_id_get(self, person_id):
        return Person(self, person_id)

    def _person_id_list(self):
        return self._person_ids

    def _get_contestant_list(self):
        return [p for p in self.person_list if p.num_participations]

    contestant_list = _PropertyCached(
        'contestant_list', _get_contestant_list,
        """
        A list of all people (Person objects) who were contestants at
        any event.
        """)

    def _get_person_event_list(self):
        r = []
        for e in self.event_list:
            r.extend(e.person_list)
        return r

    person_event_list = _PropertyCached(
        'person_event_list', _get_person_event_list,
        """
        A list of all participations by all people (PersonEvent objects).
        """)

    _country_ids = _EventGroupPropertyDS(
        '_country_ids',
        """A list of ids for all countries.""")

    def _get_country_list(self):
        return list(self.country_map.values())

    country_list = _PropertyCached(
        'country_list', _get_country_list,
        """A list of all countries (Country objects).""")

    def _country_id_test(self, country_id):
        return self._ds.country_exists(country_id)

    def _country_id_get(self, country_id):
        return Country(self, country_id)

    def _country_id_list(self):
        return self._country_ids

    def _get_country_event_list(self):
        r = []
        for e in self.event_list:
            r.extend(e.country_list)
        return r

    country_event_list = _PropertyCached(
        'country_event_list', _get_country_event_list,
        """
        A list of all participations by all countries (CountryEvent objects).
        """)

    def _get_max_num_problems(self):
        return max([e.num_problems for e in self.event_list
                    if e.num_problems is not None])

    max_num_problems = _PropertyCached(
        'max_num_problems', _get_max_num_problems,
        """The maximum number of problems at any event.""")


class _EventPropertyDS(_PropertyCached):

    """Class for Event attributes that are computed by a DataSource."""

    def __init__(self, name, doc):
        def ds_get(obj):
            return obj.event_group._ds.event_get_attr(obj.id, name)
        super().__init__(name, ds_get, doc)


class Event:

    """
    An Event represents a single competition.  Attributes where the
    source can provide the information, but it is not yet known for
    this particular event, are None.
    """

    def __init__(self, event_group, event_id):
        """
        Initialise an Event from the given EventGroup.  Normally users
        should access EventGroup attributes that implicitly create
        Event objects rather than constructing Event objects directly.
        """
        self.event_group = event_group
        """The EventGroup object for this event."""
        self.id = event_id
        """The id of this event."""
        self._cache = {}
        self.person_map = _LazyMap(self._person_id_test,
                                   self._person_id_get, self._person_id_list)
        """
        A mapping from the id of a person to a list of PersonEvent objects.
        """
        self.country_map = _LazyMap(self._country_id_test,
                                    self._country_id_get,
                                    self._country_id_list)
        """A mapping from the id of a country to the CountryEvent object."""

    def _get_short_name(self):
        if self.event_group._ds.event_have_attr(self.id, 'short_name'):
            return self.event_group._ds.event_get_attr(self.id, 'short_name')
        else:
            return self.event_group.short_name

    short_name = _PropertyCached(
        'short_name', _get_short_name,
        """The abbreviated name (typically all upper-case) for this event.""")

    def _get_long_name(self):
        if self.event_group._ds.event_have_attr(self.id, 'long_name'):
            return self.event_group._ds.event_get_attr(self.id, 'long_name')
        else:
            return self.event_group.long_name

    long_name = _PropertyCached(
        'long_name', _get_long_name,
        """The full name for this event.""")

    year = _EventPropertyDS(
        'year',
        """The year of this event.""")

    def _get_short_name_with_year(self):
        return self.short_name + ' ' + self.year

    short_name_with_year = _PropertyCached(
        'short_name_with_year', _get_short_name_with_year,
        """The abbreviated name for this event, including the year.""")

    _host_country_id = _EventPropertyDS(
        '_host_country_id',
        """The id of the host country of this event.""")

    def _get_host_country(self):
        return self.event_group.country_map[self._host_country_id]

    host_country = _PropertyCached(
        'host_country', _get_host_country,
        """The host country (a Country object) of this event.""")

    host_country_name = _EventPropertyDS(
        'host_country_name',
        """The name of the host country of this event.""")

    host_country_name_in = _EventPropertyDS(
        'host_country_name_in',
        """
        The name of the host country of this event, in the form to use
        after 'in'.
        """)

    def _get_short_name_with_year_and_country(self):
        return (self.short_name_with_year + self.host_assoc
                + self.host_country_name_in)

    short_name_with_year_and_country = _PropertyCached(
        'short_name_with_year_and_country',
        _get_short_name_with_year_and_country,
        """A description of this event, in the form 'XMO 2345 in Country'.""")

    host_city = _EventPropertyDS(
        'host_city',
        """The name of the host city of this event.""")

    host_type = _EventPropertyDS(
        'host_type',
        """The type of event ('in-person', 'hybrid' or 'virtual').""")

    def _get_host_virtual(self):
        return self.host_type == 'virtual'

    host_virtual = _PropertyCached(
        'host_virtual',
        _get_host_virtual,
        """Whether this is a virtual event.""")

    def _get_host_hybrid(self):
        return self.host_type == 'hybrid'

    host_hybrid = _PropertyCached(
        'host_hybrid',
        _get_host_hybrid,
        """Whether this is a hybrid event.""")

    def _get_host_city_virtual(self):
        loc = self.host_city
        if loc is None:
            loc = ''
        if self.host_virtual:
            loc = '%s (virtual)' % loc
            loc = loc.strip()
        elif self.host_hybrid:
            loc = '%s (hybrid)' % loc
            loc = loc.strip()
        return loc

    host_city_virtual = _PropertyCached(
        'host_city_virtual', _get_host_city_virtual,
        """The host city of this event, marked if virtual or hybrid.""")

    def _get_host_location(self):
        if self.host_city is None:
            loc = self.host_country_name
        else:
            loc = self.host_city + ', ' + self.host_country_name
        if self.host_virtual:
            return '%s (virtual)' % loc
        elif self.host_hybrid:
            return '%s (hybrid)' % loc
        else:
            return loc

    host_location = _PropertyCached(
        'host_location', _get_host_location,
        """The name (city and country) of the host location of this event.""")

    def _get_host_assoc(self):
        return ' organised by ' if self.host_virtual else ' in '

    host_assoc = _PropertyCached(
        'host_assoc',
        _get_host_assoc,
        """How the host country is associated with the event, e.g. ' in '.""")

    start_date = _EventPropertyDS(
        'start_date',
        """The start date (datetime.date object) of this event.""")

    end_date = _EventPropertyDS(
        'end_date',
        """The end date (datetime.date object) of this event.""")

    home_page_url = _EventPropertyDS(
        'home_page_url',
        """The URL of this event's home page.""")

    contact_name = _EventPropertyDS(
        'contact_name',
        """The name of a contact for this event.""")

    contact_email = _EventPropertyDS(
        'contact_email',
        """The email address of a contact for this event.""")

    def _get_contact(self):
        if self.contact_name is not None:
            if self.contact_email is not None:
                return '%s (%s)' % (self.contact_name, self.contact_email)
            else:
                return self.contact_name
        else:
            return self.contact_email

    contact = _PropertyCached(
        'contact', _get_contact,
        """Contact details (name, email or both) for this event.""")

    num_exams = _EventPropertyDS(
        'num_exams',
        """The number of exams at this event.""")

    num_problems = _EventPropertyDS(
        'num_problems',
        """The number of problems at this event.""")

    marks_per_problem = _EventPropertyDS(
        'marks_per_problem',
        """A list of the number of marks for each problem at this event.""")

    def _get_max_marks_per_problem(self):
        return max(self.marks_per_problem)

    max_marks_per_problem = _PropertyCached(
        'max_marks_per_problem', _get_max_marks_per_problem,
        """
        The maximum number of marks available for any problem at this event.
        """)

    def _get_marks_total(self):
        return sum(self.marks_per_problem)

    marks_total = _PropertyCached(
        'marks_total', _get_marks_total,
        """The maximum number of marks available in total at this event.""")

    def _get_problem_stats(self):
        r = [[0 for s in range(self.marks_per_problem[n] + 1)]
             for n in range(self.num_problems)]
        for p in self.contestant_list:
            for n in range(self.num_problems):
                if p.problem_scores[n] is not None:
                    r[n][p.problem_scores[n]] += 1
        return r

    problem_stats = _PropertyCached(
        'problem_stats', _get_problem_stats,
        """
        A list giving, for each problem, the number of contestants
        (with known score on that problem) receiving each score on
        that problem.  problem_stats[n-1][s] gives this number for
        problem n, score s.
        """)

    def _get_problem_mean_std_dev(self):
        return [mean_std_dev([p.problem_scores[n]
                              for p in self.contestant_list])
                for n in range(self.num_problems)]

    problem_mean_std_dev = _PropertyCached(
        'problem_mean_std_dev', _get_problem_mean_std_dev,
        """
        A list giving, for each problem, the mean and standard
        deviation of known scores on that problem.
        """)

    def _get_problem_mean(self):
        return [(None
                 if self.problem_mean_std_dev[n] is None
                 else self.problem_mean_std_dev[n][0])
                for n in range(self.num_problems)]

    problem_mean = _PropertyCached(
        'problem_mean', _get_problem_mean,
        """
        A list giving, for each problem, the mean of known scores on
        that problem.
        """)

    def _get_problem_std_dev(self):
        return [(None
                 if self.problem_mean_std_dev[n] is None
                 else self.problem_mean_std_dev[n][1])
                for n in range(self.num_problems)]

    problem_std_dev = _PropertyCached(
        'problem_std_dev', _get_problem_std_dev,
        """
        A list giving, for each problem, the standard deviation of
        known scores on that problem.
        """)

    def _get_problem_corr_with_total(self):
        return [corr_coeff([(p.problem_scores[n], p.total_score)
                            for p in self.contestant_list])
                for n in range(self.num_problems)]

    problem_corr_with_total = _PropertyCached(
        'problem_corr_with_total', _get_problem_corr_with_total,
        """
        A list giving, for each problem, the correlation coefficient
        of a contestant's score on that problem (for contestants with
        known score on that problem) with their total score.
        """)

    def _get_problem_corr(self):
        return [[corr_coeff([(p.problem_scores[n1], p.problem_scores[n2])
                             for p in self.contestant_list])
                 for n2 in range(self.num_problems)]
                for n1 in range(self.num_problems)]

    problem_corr = _PropertyCached(
        'problem_corr', _get_problem_corr,
        """
        A list of lists giving, for each pair of problems, the
        correlation coefficient of contestants' scores on those two
        problems (for contestants with known scores on both problems).
        """)

    def _get_total_stats_cond(self, cond):
        r = [0 for s in range(self.marks_total + 1)]
        for p in self.contestant_list:
            if cond(p):
                r[p.total_score] += 1
        return r

    def _get_total_stats(self):
        return self._get_total_stats_cond(lambda p: True)

    total_stats = _PropertyCached(
        'total_stats', _get_total_stats,
        """
        A list giving, for each possible total score, the number of
        contestants receiving that total score.
        """)

    def _get_total_stats_official(self):
        return self._get_total_stats_cond(lambda p: p.country.is_official)

    total_stats_official = _PropertyCached(
        'total_stats_official', _get_total_stats_official,
        """
        A list giving, for each possible total score, the number of
        contestants from official countries receiving that total
        score.
        """)

    def _get_max_total_stats_cond(self, cond):
        r = [0 for s in range(self.marks_total + 1)]
        for p in self.contestant_list:
            if cond(p):
                r[p.max_total_score] += 1
        return r

    def _get_max_total_stats(self):
        return self._get_max_total_stats_cond(lambda p: True)

    max_total_stats = _PropertyCached(
        'max_total_stats', _get_max_total_stats,
        """
        A list giving, for each possible total score, the number of
        contestants that would receive that total score given the
        maximum score on each problem without a score entered.
        """)

    def _get_max_total_stats_official(self):
        return self._get_max_total_stats_cond(lambda p: p.country.is_official)

    max_total_stats_official = _PropertyCached(
        'max_total_stats_official', _get_max_total_stats_official,
        """
        A list giving, for each possible total score, the number of
        contestants from official countries that would receive that
        total score given the maximum score on each problem without a
        score entered.
        """)

    def _get_total_mean_std_dev(self):
        return mean_std_dev([p.total_score for p in self.contestant_list])

    total_mean_std_dev = _PropertyCached(
        'total_mean_std_dev', _get_total_mean_std_dev,
        """The mean and standard deviation of total scores of contestants.""")

    def _get_total_mean(self):
        ms = self.total_mean_std_dev
        if ms is None:
            return None
        else:
            return ms[0]

    total_mean = _PropertyCached(
        'total_mean', _get_total_mean,
        """The mean of total scores of contestants.""")

    def _get_total_std_dev(self):
        ms = self.total_mean_std_dev
        if ms is None:
            return None
        else:
            return ms[1]

    total_std_dev = _PropertyCached(
        'total_std_dev', _get_total_std_dev,
        """The standard deviation of total scores of contestants.""")

    registration_active = _EventPropertyDS(
        'registration_active',
        """Whether the registration system is active for this event.""")

    gold_boundary = _EventPropertyDS(
        'gold_boundary',
        """Gold medal boundary.""")

    silver_boundary = _EventPropertyDS(
        'silver_boundary',
        """Silver medal boundary.""")

    bronze_boundary = _EventPropertyDS(
        'bronze_boundary',
        """Bronze medal boundary.""")

    def _scores_final(self):
        return self.gold_boundary is not None

    scores_final = _PropertyCached(
        'scores_final', _scores_final,
        """Whether the scores for this event are final.""")

    paper_list = _EventPropertyDS(
        'paper_list',
        """List of Paper objects for papers at this event.""")

    _person_ids = _EventPropertyDS(
        '_person_ids',
        """A list of ids for all people at this event.""")

    def _get_person_list(self):
        return [pe for pl in self.person_map.values() for pe in pl]

    person_list = _PropertyCached(
        'person_list', _get_person_list,
        """A list of all people (PersonEvent objects) at this event.""")

    def _person_id_test(self, person_id):
        return self.event_group._ds.person_event_exists(person_id, self.id)

    def _person_id_get(self, person_id):
        ds = self.event_group._ds
        return [PersonEvent(self.event_group.person_map[person_id],
                            self.country_map[cid], self)
                for cid in ds.person_event_get_attr(person_id, None, self.id,
                                                    '_country_ids')]

    def _person_id_list(self):
        return self._person_ids

    def _get_people_by_room(self):
        r = {}
        for p in self.person_list:
            if not p.remote_participant:
                room = p.room_number
                if room is None:
                    room = ''
                if room not in r:
                    r[room] = []
                r[room].append(p)
        return r

    people_by_room = _PropertyCached(
        'people_by_room', _get_people_by_room,
        """A mapping from room number to a list of people in that room.""")

    def _get_normal_person_list(self):
        return [p for p in self.person_list if p.country.is_normal]

    normal_person_list = _PropertyCached(
        'normal_person_list', _get_normal_person_list,
        """
        A list of all normal (non-staff) people (PersonEvent objects)
        at this event.
        """)

    def _get_staff_list(self):
        return [p for p in self.person_list if not p.country.is_normal]

    staff_list = _PropertyCached(
        'staff_list', _get_staff_list,
        """A list of all staff (PersonEvent objects) at this event.""")

    def _get_contestant_list(self):
        return [p for p in self.person_list if p.is_contestant]

    contestant_list = _PropertyCached(
        'contestant_list', _get_contestant_list,
        """A list of all contestants (PersonEvent objects) at this event.""")

    def _get_num_contestants(self):
        return len(self.contestant_list)

    num_contestants = _PropertyCached(
        'num_contestants', _get_num_contestants,
        """The number of contestants at this event.""")

    def _get_contestant_list_official(self):
        return [p for p in self.contestant_list if p.country.is_official]

    contestant_list_official = _PropertyCached(
        'contestant_list_official', _get_contestant_list_official,
        """
        A list of all contestants (PersonEvent objects) from official
        countries at this event.
        """)

    def _get_num_contestants_official(self):
        return len(self.contestant_list_official)

    num_contestants_official = _PropertyCached(
        'num_contestants_official', _get_num_contestants_official,
        """The number of contestants from official countries at this event.""")

    def _get_contestant_map(self):
        r = {}
        for p in self.contestant_list:
            if p.contestant_code in r:
                raise ValueError('duplicate contestant code %s'
                                 % p.contestant_code)
            r[p.contestant_code] = p
        return r

    contestant_map = _PropertyCached(
        'contestant_map', _get_contestant_map,
        """
        A mapping from contestant codes to PersonEvent objects for
        contestants at this event.
        """)

    def _get_language_list(self):
        langs = set()
        for p in self.contestant_list:
            for lang in p.languages:
                langs.add(lang)
        return list(langs)

    language_list = _PropertyCached(
        'language_list', _get_language_list,
        """
        A list of all languages for which some contestant at this
        event requested a paper.
        """)

    def _get_award_types(self):
        if self.honourable_mentions_available:
            return _award_types
        else:
            return _award_types_no_hm

    _award_types = _PropertyCached(
        '_award_types', _get_award_types,
        """A list of types of award available at this event.""")

    def _get_num_awards_cond(self, cond):
        if self.scores_final:
            ival = 0
        else:
            ival = None
        d = {}
        for k in self._award_types:
            d[k] = ival
        if self.scores_final:
            for c in self.country_list:
                if cond(c):
                    for k in self._award_types:
                        d[k] += c.num_awards[k]
        return d

    def _get_num_awards(self):
        return self._get_num_awards_cond(lambda c: True)

    num_awards = _PropertyCached(
        'num_awards', _get_num_awards,
        """The number of each award at this event.""")

    def _get_num_awards_official(self):
        return self._get_num_awards_cond(lambda c: c.is_official)

    num_awards_official = _PropertyCached(
        'num_awards_official', _get_num_awards_official,
        """
        The number of each award for contestants from official
        countries at this event.
        """)

    _country_ids = _EventPropertyDS(
        '_country_ids',
        """A list of ids for all countries at this event.""")

    def _get_country_list(self):
        return list(self.country_map.values())

    country_list = _PropertyCached(
        'country_list', _get_country_list,
        """A list of all countries (CountryEvent objects) at this event.""")

    def _country_id_test(self, country_id):
        return self.event_group._ds.country_event_exists(country_id, self.id)

    def _country_id_get(self, country_id):
        return CountryEvent(self.event_group.country_map[country_id], self)

    def _country_id_list(self):
        return self._country_ids

    def _get_normal_country_list(self):
        return [c for c in self.country_list if c.is_normal]

    normal_country_list = _PropertyCached(
        'normal_country_list', _get_normal_country_list,
        """A list of all normal countries at this event.""")

    def _get_staff_country_list(self):
        return [c for c in self.country_list if not c.is_normal]

    staff_country_list = _PropertyCached(
        'staff_country_list', _get_staff_country_list,
        """A list of all staff countries at this event.""")

    def _get_country_with_contestants_list(self):
        return [c for c in self.country_list if c.num_contestants]

    country_with_contestants_list = _PropertyCached(
        'country_with_contestants_list', _get_country_with_contestants_list,
        """A list of all countries with contestants at this event.""")

    def _get_num_countries(self):
        return len(self.country_with_contestants_list)

    num_countries = _PropertyCached(
        'num_countries', _get_num_countries,
        """The number of countries with contestants at this event.""")

    def _get_country_with_contestants_list_official(self):
        return [c for c in self.country_with_contestants_list if c.is_official]

    country_with_contestants_list_official = _PropertyCached(
        'country_with_contestants_list_official',
        _get_country_with_contestants_list_official,
        """A list of all official countries with contestants at this event.""")

    def _get_num_countries_official(self):
        return len(self.country_with_contestants_list_official)

    num_countries_official = _PropertyCached(
        'num_countries_official', _get_num_countries_official,
        """The number of official countries with contestants at this event.""")

    def _get_distinguish_official(self):
        if self.event_group._ds.event_have_attr(self.id,
                                                'distinguish_official'):
            return self.event_group._ds.event_get_attr(self.id,
                                                       'distinguish_official')
        else:
            return self.event_group.distinguish_official

    distinguish_official = _PropertyCached(
        'distinguish_official', _get_distinguish_official,
        """
        Whether official and unofficial countries are distinguished at
        this event.
        """)

    def _get_rank_top_n(self):
        if self.event_group._ds.event_have_attr(self.id, 'rank_top_n'):
            return self.event_group._ds.event_get_attr(self.id, 'rank_top_n')
        else:
            return self.event_group.rank_top_n

    rank_top_n = _PropertyCached(
        'rank_top_n', _get_rank_top_n,
        """
        The number of contestants considered in determining a
        country's rank, or None if all contestants considered.
        """)

    def _get_rank_top_n_matters(self):
        count = self.rank_top_n
        if count is None:
            return False
        for c in self.country_with_contestants_list:
            if c.num_contestants > count:
                return True
        return False

    rank_top_n_matters = _PropertyCached(
        'rank_top_n_matters', _get_rank_top_n_matters,
        """
        Whether country ranks are determined by the total of the
        scores of a number of contestants that at least sometimes is
        fewer than all the contestants from that country.
        """)

    def _get_rank_top_n_if_matters(self):
        if self.rank_top_n_matters:
            return self.rank_top_n
        else:
            return None

    rank_top_n_if_matters = _PropertyCached(
        'rank_top_n_if_matters', _get_rank_top_n_if_matters,
        """
        The number of contestants considered in determining a
        country's rank, or None if all contestants considered or this
        number is in fact at least as big as the number of contestants
        from each country.
        """)

    def _get_honourable_mentions_available(self):
        if self.event_group._ds.event_have_attr(
                self.id,
                'honourable_mentions_available'):
            return self.event_group._ds.event_get_attr(
                self.id,
                'honourable_mentions_available')
        else:
            return self.event_group.honourable_mentions_available

    honourable_mentions_available = _PropertyCached(
        'honourable_mentions_available', _get_honourable_mentions_available,
        """
        Whether the rules of this event include awarding Honourable
        Mentions to contestants not receiving a medal but with a
        perfect score on at least one problem.
        """)

    age_day_desc = _EventPropertyDS(
        'age_day_desc',
        """Description of the day for which contestant ages are given.""")

    def _get_sort_key(self):
        return self.id

    sort_key = _PropertyCached(
        'sort_key', _get_sort_key,
        """General-purpose sort key.""")


class Paper:

    """A paper represents one version of one paper at one Event."""

    # Papers are not treated as objects with numeric ids, and so are
    # constructed somewhat differently from the other classes here.
    def __init__(self, day, language, description, url):
        """
        Initialise a Paper.  Normally users should access Event
        attributes that implicitly create Paper objects rather than
        constructing Paper objects directly.
        """
        self.day = day
        """The day (1, 2, etc.) of this paper."""
        self.language = language
        """The language of this paper."""
        self.description = description
        """Any additional description of this paper."""
        self.url = url
        """The URL of this paper."""


class Person:

    """
    A Person represents an individual involved in one or more Events
    within an EventGroup.
    """

    def __init__(self, event_group, person_id):
        """
        Initialise a Person from the given EventGroup.  Normally users
        should access EventGroup attributes that implicitly create
        Person objects rather than constructing Person objects
        directly.
        """
        self.event_group = event_group
        """The EventGroup object for this person."""
        self.id = person_id
        """The id of this person."""
        self._cache = {}

    def _get_participation_list(self):
        partl = [e.person_map[self.id] for e in self.event_group.event_list
                 if self.id in e.person_map]
        partl = [p for pl in partl for p in pl]
        partl = sorted(partl, key=lambda p: p.sort_key)
        return partl

    participation_list = _PropertyCached(
        'participation_list', _get_participation_list,
        """
        A list of PersonEvent objects for this person, in
        chronological order; sorted by the sort key for the
        PersonEvent, for multiple objects at the same Event.
        """)

    def _get_contestant_list(self):
        return [p for p in self.participation_list if p.is_contestant]

    contestant_list = _PropertyCached(
        'contestant_list', _get_contestant_list,
        """
        A list of PersonEvent objects for this person when
        participating as a contestant, in chronological order.
        """)

    def _get_num_participations(self):
        return len(self.contestant_list)

    num_participations = _PropertyCached(
        'num_participations', _get_num_participations,
        """The number of times this person participated as a contestant.""")

    def _get_num_awards(self):
        d = {}
        for k in self.event_group._award_types:
            d[k] = 0
        for p in self.contestant_list:
            if p.award is not None:
                d[p.award] += 1
        return d

    num_awards = _PropertyCached(
        'num_awards', _get_num_awards,
        """The number of each award received by this person.""")

    def _get_country_list(self):
        seen = set()
        r = []
        for p in self.contestant_list:
            if p.country.country.id not in seen:
                seen.add(p.country.country.id)
                r.append(p.country.country)
        return r

    country_list = _PropertyCached(
        'country_list', _get_country_list,
        """
        A list of the distinct countries (Country objects) for which
        this person participated as a contestant, in chronological
        order of first participation.
        """)

    def _get_given_name(self):
        return self.participation_list[-1].given_name

    given_name = _PropertyCached(
        'given_name', _get_given_name,
        """The given name of this person.""")

    def _get_family_name(self):
        return self.participation_list[-1].family_name

    family_name = _PropertyCached(
        'family_name', _get_family_name,
        """The family name of this person.""")

    def _get_name(self):
        return self.participation_list[-1].name

    name = _PropertyCached(
        'name', _get_name,
        """The name of this person.""")

    def _get_photo_url(self):
        return self.participation_list[-1].photo_url

    photo_url = _PropertyCached(
        'photo_url', _get_photo_url,
        """The photo URL of this person at their last participation.""")

    def _get_photo_thumb_url(self):
        return self.participation_list[-1].photo_thumb_url

    photo_thumb_url = _PropertyCached(
        'photo_thumb_url', _get_photo_thumb_url,
        """
        The photo thumbnail URL of this person at their last
        participation, containing '%(width)d'.
        """)

    def _get_sort_key_alpha(self):
        return (coll_get_sort_key(self.family_name),
                coll_get_sort_key(self.given_name),
                self.id)

    sort_key_alpha = _PropertyCached(
        'sort_key_alpha', _get_sort_key_alpha,
        """Alphabetical sort key.""")

    def _get_sort_key_hall_of_fame(self):
        if self.event_group.honourable_mentions_available:
            hm_count = self.num_awards['Honourable Mention']
        else:
            hm_count = 0
        return (-self.num_awards['Gold Medal'],
                -self.num_awards['Silver Medal'],
                -self.num_awards['Bronze Medal'],
                -hm_count,
                coll_get_sort_key(self.family_name),
                coll_get_sort_key(self.given_name),
                self.id)

    sort_key_hall_of_fame = _PropertyCached(
        'sort_key_hall_of_fame', _get_sort_key_hall_of_fame,
        """Sort key for the Hall of Fame by medal count.""")


class _PersonEventPropertyDS(_PropertyCached):

    """Class for PersonEvent attributes that are computed by a DataSource."""

    def __init__(self, name, doc):
        def ds_get(obj):
            ds = obj.person.event_group._ds
            return ds.person_event_get_attr(obj.person.id,
                                            obj.country.country.id,
                                            obj.event.id,
                                            name)
        super().__init__(name, ds_get, doc)


class PersonEvent:

    """
    A PersonEvent represents the participation of a Person in a
    particular Event for a particular Country.  Normally, a Person
    participates in an Event for only one Country; if they have staff
    and non-staff roles (e.g. being a Leader and also being on the
    organising committee), the staff roles are listed as other roles
    for the person under the non-staff country.  However, if someone
    has no staff roles but non-staff roles (Leader, Deputy Leader or
    Observer) for more than one Country (e.g., A and B teams from the
    same country), they have multiple PersonEvents at the same Event.
    """

    def __init__(self, person, country, event):
        """
        Initialise a PersonEvent from the given Person, CountryEvent
        and Event.  Normally users should access attributes that
        implicitly create PersonEvent objects rather than constructing
        PersonEvent objects directly.
        """
        self.person = person
        """The Person object for this PersonEvent."""
        self.country = country
        """The CountryEvent object for this PersonEvent."""
        self.event = event
        """The Event object for this PersonEvent."""
        assert person.event_group is event.event_group
        self._cache = {}

    annual_url = _PersonEventPropertyDS(
        'annual_url',
        """The URL for this person in this event's registration system.""")

    primary_role = _PersonEventPropertyDS(
        'primary_role',
        """The primary role of this person at this event.""")

    other_roles = _PersonEventPropertyDS(
        'other_roles',
        """
        A list of roles of this person at this event, other than their
        primary role.
        """)

    _guide_for_ids = _PersonEventPropertyDS(
        '_guide_for_ids',
        """
        A list of the ids of countries for which this person was a
        Guide at this event.
        """)

    def _get_guide_for(self):
        return [self.event.country_map[cid] for cid in self._guide_for_ids]

    guide_for = _PropertyCached(
        'guide_for', _get_guide_for,
        """
        A list of the countries (CountryEvent objects) for which this
        person was a Guide at this event.
        """)

    def _get_is_contestant(self):
        return self.primary_role.startswith('Contestant ')

    is_contestant = _PropertyCached(
        'is_contestant', _get_is_contestant,
        """Whether this person was a contestant at this event.""")

    def _get_contestant_code(self):
        assert self.is_contestant
        return self.country.code + self.primary_role[len('Contestant '):]

    contestant_code = _PropertyCached(
        'contestant_code', _get_contestant_code,
        """The contestant code for this contestant at this event.""")

    contestant_age = _PersonEventPropertyDS(
        'contestant_age',
        """The age of this contestant at this event.""")

    given_name = _PersonEventPropertyDS(
        'given_name',
        """The given name of this person at this event.""")

    family_name = _PersonEventPropertyDS(
        'family_name',
        """The family name of this person at this event.""")

    def _get_name(self):
        return self.given_name + ' ' + self.family_name

    name = _PropertyCached(
        'name', _get_name,
        """The name of this person at this event.""")

    problem_scores = _PersonEventPropertyDS(
        'problem_scores',
        """
        A list of the scores this contestant on each problem at this event.
        """)

    def _get_have_any_scores(self):
        assert self.is_contestant
        for s in self.problem_scores:
            if s is not None:
                return True
        return False

    have_any_scores = _PropertyCached(
        'have_any_scores', _get_have_any_scores,
        """Whether any scores are known for this contestant at this event.""")

    def _get_total_score(self):
        assert self.is_contestant
        t = sum([s for s in self.problem_scores if s is not None])
        ds = self.person.event_group._ds
        if ds.person_event_have_attr(self.person.id, self.country.country.id,
                                     self.event.id, 'total_score'):
            expt = ds.person_event_get_attr(self.person.id,
                                            self.country.country.id,
                                            self.event.id,
                                            'total_score')
            if t != expt:
                raise ValueError('total score not as expected')
        return t

    total_score = _PropertyCached(
        'total_score', _get_total_score,
        """The total score of this contestant at this event.""")

    def _get_max_total_score(self):
        assert self.is_contestant
        t = 0
        for n in range(self.event.num_problems):
            if self.problem_scores[n] is None:
                t += self.event.marks_per_problem[n]
            else:
                t += self.problem_scores[n]
        return t

    max_total_score = _PropertyCached(
        'max_total_score', _get_max_total_score,
        """
        The maximum possible total score of this contestant at this
        event.
        """)

    def _get_award(self):
        assert self.is_contestant
        if not self.event.scores_final:
            return None
        if self.total_score >= self.event.gold_boundary:
            a = 'Gold Medal'
        elif self.total_score >= self.event.silver_boundary:
            a = 'Silver Medal'
        elif self.total_score >= self.event.bronze_boundary:
            a = 'Bronze Medal'
        elif self.event.honourable_mentions_available:
            a = None
            for n in range(self.event.num_problems):
                if self.problem_scores[n] == self.event.marks_per_problem[n]:
                    a = 'Honourable Mention'
        else:
            a = None
        ds = self.person.event_group._ds
        if ds.person_event_have_attr(self.person.id, self.country.country.id,
                                     self.event.id, 'award'):
            expa = ds.person_event_get_attr(self.person.id,
                                            self.country.country.id,
                                            self.event.id,
                                            'award')
            if a != expa:
                raise ValueError('award not as expected')
        return a

    award = _PropertyCached(
        'award', _get_award,
        """The award given to this contestant at this event.""")

    extra_awards = _PersonEventPropertyDS(
        'extra_awards',
        """A list of extra awards for this person at this event.""")

    def _get_awards_str(self):
        assert self.is_contestant
        if not self.event.scores_final:
            return ''
        base_award = self.award
        if base_award is not None:
            award_list = [base_award]
        else:
            award_list = []
        award_list.extend(self.extra_awards)
        return ', '.join(award_list)

    awards_str = _PropertyCached(
        'awards_str', _get_awards_str,
        """A string listing awards for this person at this event.""")

    def _get_rank(self):
        assert self.is_contestant
        rank = 0
        nrank = 0
        last_score = -1
        for p in sorted(self.event.contestant_list,
                        key=lambda x: x.total_score, reverse=True):
            nrank += 1
            if p.total_score != last_score:
                rank = nrank
                last_score = p.total_score
            p._cache['rank'] = rank
        return self._cache['rank']

    rank = _PropertyCached(
        'rank', _get_rank,
        """The rank of this person at this event.""")

    def _get_rank_official(self):
        assert self.is_contestant
        if not self.country.is_official:
            return None
        rank = 0
        nrank = 0
        last_score = -1
        for p in sorted(self.event.contestant_list_official,
                        key=lambda x: x.total_score, reverse=True):
            nrank += 1
            if p.total_score != last_score:
                rank = nrank
                last_score = p.total_score
            p._cache['rank_official'] = rank
        return self._cache['rank_official']

    rank_official = _PropertyCached(
        'rank_official', _get_rank_official,
        """
        The rank of this person among official contestants at this event.
        """)

    photo_url = _PersonEventPropertyDS(
        'photo_url',
        """
        The URL of the registration photo of this person (for the
        website) at this event.
        """)

    photo_thumb_url = _PersonEventPropertyDS(
        'photo_thumb_url',
        """
        The URL of the registration photo thumbnail of this person
        (for the website) at this event, containing '%(width)d'.
        """)

    photo_filename = _PersonEventPropertyDS(
        'photo_filename',
        """
        The local filename of the registration photo of this person
        (for the website) at this event.
        """)

    photo_thumb_filename = _PersonEventPropertyDS(
        'photo_thumb_filename',
        """
        The local filename of the registration photo thumbnail of this
        person (for the website) at this event, containing
        '%(width)d'.
        """)

    badge_photo_url = _PersonEventPropertyDS(
        'badge_photo_url',
        """
        The URL of the registration photo of this person (for the name
        badge) at this event.
        """)

    badge_photo_filename = _PersonEventPropertyDS(
        'badge_photo_filename',
        """
        The local filename of the registration photo of this person
        (for the name badge) at this event.
        """)

    badge_background = _PersonEventPropertyDS(
        'badge_background',
        """
        The background name for the name badge of this person at this
        event.
        """)

    badge_colour_outer = _PersonEventPropertyDS(
        'badge_colour_outer',
        """
        The outer colour for the name badge of this person at this
        event.
        """)

    badge_colour_inner = _PersonEventPropertyDS(
        'badge_colour_inner',
        """
        The inner colour for the name badge of this person at this
        event.
        """)

    badge_colour_text = _PersonEventPropertyDS(
        'badge_colour_text',
        """
        The text colour for the name badge of this person at this
        event.
        """)

    consent_form_url = _PersonEventPropertyDS(
        'consent_form_url',
        """The URL of the consent form of this person at this event.""")

    consent_form_filename = _PersonEventPropertyDS(
        'consent_form_filename',
        """
        The local filename of the consent form of this person at this
        event.
        """)

    languages = _PersonEventPropertyDS(
        'languages',
        """The languages of this person at this event.""")

    diet = _PersonEventPropertyDS(
        'diet',
        """
        The allergies and dietary requirements of this person at this
        event.
        """)

    sars_cov2_cert = _PersonEventPropertyDS(
        'sars_cov2_cert',
        """
        Whether this person has a SARS-CoV-2 vaccine certificate of
        the appropriate form for this event.
        """)

    sars_cov2_doses = _PersonEventPropertyDS(
        'sars_cov2_doses',
        """
        The number of doses of SARS-CoV-2 vaccine this person has had
        for this event.
        """)

    sars_cov2_after = _PersonEventPropertyDS(
        'sars_cov2_after',
        """
        Whether this person has had a SARS-CoV-2 vaccine dose after
        the threshold date for this event.
        """)

    room_type = _PersonEventPropertyDS(
        'room_type',
        """The requested room type of this person at this event.""")

    room_share_with = _PersonEventPropertyDS(
        'room_share_with',
        """
        The person (name and country) this person requests to share a
        room with at this event.
        """)

    room_number = _PersonEventPropertyDS(
        'room_number',
        """The room number of this person at this event.""")

    phone_number = _PersonEventPropertyDS(
        'phone_number',
        """The phone number of this person at this event.""")

    generic_id = _PersonEventPropertyDS(
        'generic_id',
        """
        The generic id for this person at this event (when ids used in
        this EventGroup are those from the registration system rather
        than permanent generic ids).
        """)

    gender = _PersonEventPropertyDS(
        'gender',
        """The gender of this person at this event.""")

    date_of_birth = _PersonEventPropertyDS(
        'date_of_birth',
        """The date of birth of this person at this event.""")

    passport_number = _PersonEventPropertyDS(
        'passport_number',
        """
        The passport or identity card number of this person at this
        event.
        """)

    nationality = _PersonEventPropertyDS(
        'nationality',
        """The nationality of this person at this event.""")

    passport_given_name = _PersonEventPropertyDS(
        'passport_given_name',
        """
        The given name of this person in their passport at this event,
        if relevant, or the same as given_name otherwise.
        """)

    passport_family_name = _PersonEventPropertyDS(
        'passport_family_name',
        """
        The family name of this person in their passport at this
        event, if relevant, or the same as family_name otherwise.
        """)

    tshirt = _PersonEventPropertyDS(
        'tshirt',
        """The T-shirt size of this person at this event.""")

    arrival_place = _PersonEventPropertyDS(
        'arrival_place',
        """The arrival place of this person at this event.""")

    arrival_is_airport = _PersonEventPropertyDS(
        'arrival_is_airport',
        """Whether this person is arriving at an airport at this event.""")

    arrival_date = _PersonEventPropertyDS(
        'arrival_date',
        """The arrival date of this person at this event.""")

    arrival_time = _PersonEventPropertyDS(
        'arrival_time',
        """The arrival time of this person at this event.""")

    arrival_flight = _PersonEventPropertyDS(
        'arrival_flight',
        """The arrival flight of this person at this event.""")

    departure_place = _PersonEventPropertyDS(
        'departure_place',
        """The departure place of this person at this event.""")

    departure_is_airport = _PersonEventPropertyDS(
        'departure_is_airport',
        """Whether this person is departing from an airport at this event.""")

    departure_date = _PersonEventPropertyDS(
        'departure_date',
        """The departure date of this person at this event.""")

    departure_time = _PersonEventPropertyDS(
        'departure_time',
        """The departure time of this person at this event.""")

    departure_flight = _PersonEventPropertyDS(
        'departure_flight',
        """The departure flight of this person at this event.""")

    event_photos_consent = _PersonEventPropertyDS(
        'event_photos_consent',
        """
        Whether permission has been given for publication of photos of
        this person taken at this event.  None if that information is
        not collected.
        """)

    remote_participant = _PersonEventPropertyDS(
        'remote_participant',
        """Whether this person is taking part remotely at this event.""")

    basic_data_missing = _PersonEventPropertyDS(
        'basic_data_missing',
        """
        Whether basic, normally required, data may be missing for this
        person at this event (where an incomplete registration of the
        person has been done to be completed by self-registration).
        """)

    def _get_sort_key(self):
        return (self.event.id,
                coll_get_sort_key(self.country.code),
                coll_get_sort_key(self.primary_role),
                coll_get_sort_key(self.family_name),
                coll_get_sort_key(self.given_name),
                self.country.country.id,
                self.person.id)

    sort_key = _PropertyCached(
        'sort_key', _get_sort_key,
        """General-purpose sort key.""")

    def _get_sort_key_exams(self):
        return (self.event.id,
                coll_get_sort_key(self.primary_role),
                coll_get_sort_key(self.country.code),
                self.person.id)

    sort_key_exams = _PropertyCached(
        'sort_key_exams', _get_sort_key_exams,
        """Sort key by contestant number for exams.""")


class Country:

    """
    A Country represents a group of people involved together in one or
    more Events within an EventGroup (possibly a conventional national
    team for a country or territory, possibly a B team, possibly a
    container for staff at an event instead of a normal country at
    all).
    """

    def __init__(self, event_group, country_id):
        """
        Initialise a Country from the given EventGroup.  Normally
        users should access EventGroup attributes that implicitly
        create Country objects rather than constructing Country
        objects directly.
        """
        self.event_group = event_group
        """The EventGroup object for this country."""
        self.id = country_id
        """The id of this country."""
        self._cache = {}

    def _get_participation_list(self):
        return [e.country_map[self.id] for e in self.event_group.event_list
                if self.id in e.country_map]

    participation_list = _PropertyCached(
        'participation_list', _get_participation_list,
        """
        A list of CountryEvent objects for this country, in
        chronological order.
        """)

    def _get_num_participations(self):
        return len(self.participation_list)

    num_participations = _PropertyCached(
        'num_participations', _get_num_participations,
        """The number of events this country participated at.""")

    def _get_max_num_problems(self):
        nplist = [ce.event.num_problems for ce in self.participation_list
                  if ce.num_contestants]
        if nplist:
            return max(nplist)
        else:
            return None

    max_num_problems = _PropertyCached(
        'max_num_problems', _get_max_num_problems,
        """
        The maximum number of problems at any event at which this
        country had contestants, or None if no such events.
        """)

    def _get_honourable_mentions_available(self):
        for ce in self.participation_list:
            if ce.num_contestants and ce.event.honourable_mentions_available:
                return True
        return False

    honourable_mentions_available = _PropertyCached(
        'honourable_mentions_available', _get_honourable_mentions_available,
        """
        Whether Honourable Mentions were available at at least one
        event at which this country had contestants.
        """)

    def _get_host_list(self):
        return [e for e in self.event_group.event_list
                if self is e.host_country]

    host_list = _PropertyCached(
        'host_list', _get_host_list,
        """
        A list of Event objects for events at which this country was host.
        """)

    def _get_code(self):
        return self.participation_list[-1].code

    code = _PropertyCached(
        'code', _get_code,
        """The country code of this country.""")

    def _get_name(self):
        return self.participation_list[-1].name

    name = _PropertyCached(
        'name', _get_name,
        """The name of this country.""")

    def _get_name_with_code(self):
        return '%s (%s)' % (self.name, self.code)

    name_with_code = _PropertyCached(
        'name_with_code', _get_name_with_code,
        """A description of this country, in the form 'Name (Code)'.""")

    def _get_flag_url(self):
        return self.participation_list[-1].flag_url

    flag_url = _PropertyCached(
        'flag_url', _get_flag_url,
        """The flag URL of this country.""")

    def _get_flag_thumb_url(self):
        return self.participation_list[-1].flag_thumb_url

    flag_thumb_url = _PropertyCached(
        'flag_thumb_url', _get_flag_thumb_url,
        """The flag thumbnail URL of this country, containing '%(width)d'.""")

    def _get_is_official(self):
        most_recent = self.participation_list[-1]
        if most_recent.event.distinguish_official:
            return most_recent.is_official
        else:
            return None

    is_official = _PropertyCached(
        'is_official', _get_is_official,
        """
        Whether this country is an official country at its most recent
        event; None if official countries are not distinguished at
        that event.
        """)

    def _get_sort_key(self):
        return (coll_get_sort_key(self.code),
                coll_get_sort_key(self.name),
                self.id)

    sort_key = _PropertyCached(
        'sort_key', _get_sort_key,
        """General-purpose sort key.""")


class _CountryEventPropertyDS(_PropertyCached):

    """Class for CountryEvent attributes that are computed by a DataSource."""

    def __init__(self, name, doc):
        def ds_get(obj):
            ds = obj.country.event_group._ds
            return ds.country_event_get_attr(obj.country.id, obj.event.id,
                                             name)
        super().__init__(name, ds_get, doc)


class CountryEvent:

    """
    A CountryEvent represents the participation of a Country in a
    particular Event.
    """

    def __init__(self, country, event):
        """
        Initialise a CountryEvent from the given Country and Event.
        Normally users should access attributes that implicitly create
        CountryEvent objects rather than constructing CountryEvent
        objects directly.
        """
        self.country = country
        """The Country object for this CountryEvent."""
        self.event = event
        """The Event object for this CountryEvent."""
        assert country.event_group is event.event_group
        self._cache = {}

    annual_url = _CountryEventPropertyDS(
        'annual_url',
        """The URL for this country in this event's registration system.""")

    code = _CountryEventPropertyDS(
        'code',
        """The country code of this country at this event.""")

    name = _CountryEventPropertyDS(
        'name',
        """The name of this country at this event.""")

    def _get_name_with_code(self):
        return '%s (%s)' % (self.name, self.code)

    name_with_code = _PropertyCached(
        'name_with_code', _get_name_with_code,
        """A description of this country, in the form 'Name (Code)'.""")

    flag_url = _CountryEventPropertyDS(
        'flag_url',
        """The flag URL of this country at this event.""")

    flag_thumb_url = _CountryEventPropertyDS(
        'flag_thumb_url',
        """
        The flag thumbnail URL of this country at this event,
        containing '%(width)d'.
        """)

    flag_filename = _CountryEventPropertyDS(
        'flag_filename',
        """The local filename for the flag of this country at this event.""")

    flag_thumb_filename = _CountryEventPropertyDS(
        'flag_thumb_filename',
        """
        The local filename for the flag thumbnail of this country at
        this event, containing '%(width)d'.
        """)

    def _get_is_official(self):
        if self.event.distinguish_official:
            ds = self.country.event_group._ds
            return ds.country_event_get_attr(self.country.id, self.event.id,
                                             'is_official')
        else:
            return True

    is_official = _PropertyCached(
        'is_official', _get_is_official,
        """Whether this country is an official country at this event.""")

    is_normal = _CountryEventPropertyDS(
        'is_normal',
        """
        Whether this country is a normal country (one that may have
        non-staff participants) at this event.
        """)

    contact_emails = _CountryEventPropertyDS(
        'contact_emails',
        """
        The list of contact email addresses for this country at this
        event.
        """)

    expected_leaders = _CountryEventPropertyDS(
        'expected_leaders',
        """
        The expected number of Leaders for this country at this event.
        """)

    expected_deputies = _CountryEventPropertyDS(
        'expected_deputies',
        """
        The expected number of Deputy Leaders for this country at this event.
        """)

    expected_contestants = _CountryEventPropertyDS(
        'expected_contestants',
        """
        The expected number of Contestants for this country at this event.
        """)

    expected_observers_a = _CountryEventPropertyDS(
        'expected_observers_a',
        """
        The expected number of Observers with Leader for this country
        at this event.
        """)

    expected_observers_b = _CountryEventPropertyDS(
        'expected_observers_b',
        """
        The expected number of Observers with Deputy for this country
        at this event.
        """)

    expected_observers_c = _CountryEventPropertyDS(
        'expected_observers_c',
        """
        The expected number of Observers with Contestants for this
        country at this event.
        """)

    expected_single_rooms = _CountryEventPropertyDS(
        'expected_single_rooms',
        """
        The expected number of single rooms for this country at this event.
        """)

    expected_numbers_confirmed = _CountryEventPropertyDS(
        'expected_numbers_confirmed',
        """
        Whether the expected numbers of participants and single rooms
        have been confirmed (rather than just being defaults).
        """)

    def _get_expected_roles(self):
        exp_nums = {'Leader': self.expected_leaders,
                    'Deputy Leader': self.expected_deputies,
                    'Observer with Leader': self.expected_observers_a,
                    'Observer with Deputy': self.expected_observers_b,
                    'Observer with Contestants': self.expected_observers_c}
        for i in range(self.expected_contestants):
            exp_nums['Contestant %d' % (i + 1)] = 1
        return exp_nums

    expected_roles = _PropertyCached(
        'expected_roles', _get_expected_roles,
        """
        A mapping from roles to the expected number of people in each
        role for this country at this event.
        """)

    leader_email = _CountryEventPropertyDS(
        'leader_email',
        """The email address for the leader of this country at this event.""")

    physical_address = _CountryEventPropertyDS(
        'physical_address',
        """The physical address for this country at this event.""")

    participation_type = _CountryEventPropertyDS(
        'participation_type',
        """
        The type of participation for this country at this event
        ('in-person', 'hybrid', 'virtual' or None if unknown).
        """)

    def _get_person_list(self):
        ds = self.country.event_group._ds
        if ds.country_event_have_attr(self.country.id, self.event.id,
                                      '_person_ids'):
            ids = ds.country_event_get_attr(self.country.id, self.event.id,
                                            '_person_ids')
            return [p for pid in ids for p in self.event.person_map[pid]
                    if p.country.country.id == self.country.id]
        else:
            return [p for p in self.event.person_list if self is p.country]

    person_list = _PropertyCached(
        'person_list', _get_person_list,
        """
        A list of all people (PersonEvent objects) from this country
        at this event.
        """)

    def _get_contestant_list(self):
        return [p for p in self.person_list if p.is_contestant]

    contestant_list = _PropertyCached(
        'contestant_list', _get_contestant_list,
        """
        A list of all contestants (PersonEvent objects) from this
        country at this event.
        """)

    def _get_num_contestants(self):
        return len(self.contestant_list)

    num_contestants = _PropertyCached(
        'num_contestants', _get_num_contestants,
        """The number of contestants from this country at this event.""")

    def _get_guide_list(self):
        ds = self.country.event_group._ds
        if ds.country_event_have_attr(self.country.id, self.event.id,
                                      '_guide_ids'):
            ids = ds.country_event_get_attr(self.country.id, self.event.id,
                                            '_guide_ids')
            gl = [self.event.person_map[pid] for pid in ids]
            for pl in gl:
                if len(pl) != 1:
                    raise ValueError('Guide present more than once at Event')
            return [p for pl in gl for p in pl]
        else:
            return [p for p in self.event.person_list if self in p.guide_for]

    guide_list = _PropertyCached(
        'guide_list', _get_guide_list,
        """
        A list of all guides (PersonEvent objects) for this country at
        this event.
        """)

    def _get_num_awards(self):
        d = {}
        if self.event.scores_final:
            ival = 0
        else:
            ival = None
        for k in self.event._award_types:
            d[k] = ival
        if self.event.scores_final:
            for p in self.contestant_list:
                if p.award is not None:
                    d[p.award] += 1
        return d

    num_awards = _PropertyCached(
        'num_awards', _get_num_awards,
        """
        The number of each award for contestants from this country at
        this event.
        """)

    def _get_have_any_scores(self):
        for p in self.contestant_list:
            if p.have_any_scores:
                return True
        return False

    have_any_scores = _PropertyCached(
        'have_any_scores', _get_have_any_scores,
        """Whether any scores are known for this country at this event.""")

    def _get_total_score(self):
        return sum([p.total_score for p in self.contestant_list])

    total_score = _PropertyCached(
        'total_score', _get_total_score,
        """The total score for contestants from this country at this event.""")

    def _get_max_total_score(self):
        return sum([p.max_total_score for p in self.contestant_list])

    max_total_score = _PropertyCached(
        'max_total_score', _get_max_total_score,
        """
        The maximum possible total score for contestants from this
        country at this event.
        """)

    def _get_total_score_for_rank(self):
        scores = sorted([p.total_score for p in self.contestant_list],
                        reverse=True)
        count = self.event.rank_top_n
        if count is not None and count < len(scores):
            scores = scores[0:count]
        return sum(scores)

    total_score_for_rank = _PropertyCached(
        'total_score_for_rank', _get_total_score_for_rank,
        """
        The total score for ranking purposes for this country at this event.
        """)

    def _get_max_total_score_for_rank(self):
        scores = sorted([p.max_total_score for p in self.contestant_list],
                        reverse=True)
        count = self.event.rank_top_n
        if count is not None and count < len(scores):
            scores = scores[0:count]
        return sum(scores)

    max_total_score_for_rank = _PropertyCached(
        'max_total_score_for_rank', _get_max_total_score_for_rank,
        """
        The maximum possible total score for ranking purposes for this
        country at this event.
        """)

    def _get_have_any_problem_scores(self):
        r = []
        for n in range(self.event.num_problems):
            have_any = False
            for p in self.contestant_list:
                if p.problem_scores[n] is not None:
                    have_any = True
                    break
            r.append(have_any)
        return r

    have_any_problem_scores = _PropertyCached(
        'have_any_problem_scores', _get_have_any_problem_scores,
        """
        A list of whether any scores are known for each problem for
        contestants from this country at this event.
        """)

    def _get_problem_totals(self):
        r = []
        for n in range(self.event.num_problems):
            r.append(sum([p.problem_scores[n] for p in self.contestant_list
                          if p.problem_scores[n] is not None]))
        return r

    problem_totals = _PropertyCached(
        'problem_totals', _get_problem_totals,
        """
        A list of the total score on each problem for contestants from
        this country at this event.
        """)

    def _get_max_problem_totals(self):
        r = []
        for n in range(self.event.num_problems):
            t = 0
            for p in self.contestant_list:
                if p.problem_scores[n] is None:
                    t += self.event.marks_per_problem[n]
                else:
                    t += p.problem_scores[n]
            r.append(t)
        return r

    max_problem_totals = _PropertyCached(
        'max_problem_totals', _get_max_problem_totals,
        """
        A list of the maximum possible total score on each problem for
        contestants from this country at this event.
        """)

    def _get_rank(self):
        assert self.num_contestants
        rank = 0
        nrank = 0
        last_score = -1
        for c in sorted(self.event.country_with_contestants_list,
                        key=lambda x: x.total_score_for_rank, reverse=True):
            nrank += 1
            if c.total_score_for_rank != last_score:
                rank = nrank
                last_score = c.total_score_for_rank
            c._cache['rank'] = rank
        return self._cache['rank']

    rank = _PropertyCached(
        'rank', _get_rank,
        """The rank of this country at this event.""")

    def _get_rank_official(self):
        assert self.num_contestants
        if not self.is_official:
            return None
        rank = 0
        nrank = 0
        last_score = -1
        for c in sorted(self.event.country_with_contestants_list_official,
                        key=lambda x: x.total_score_for_rank, reverse=True):
            nrank += 1
            if c.total_score_for_rank != last_score:
                rank = nrank
                last_score = c.total_score_for_rank
            c._cache['rank_official'] = rank
        return self._cache['rank_official']

    rank_official = _PropertyCached(
        'rank_official', _get_rank_official,
        """The rank of this country among official countries at this event.""")

    generic_id = _CountryEventPropertyDS(
        'generic_id',
        """
        The generic id for this country at this event (when ids used
        in this EventGroup are those from the registration system
        rather than permanent generic ids).
        """)

    def _get_sort_key(self):
        return (self.event.id,
                coll_get_sort_key(self.code),
                coll_get_sort_key(self.name),
                self.country.id)

    sort_key = _PropertyCached(
        'sort_key', _get_sort_key,
        """General-purpose sort key.""")
