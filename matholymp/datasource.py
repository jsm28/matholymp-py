# DataSource class for matholymp package.

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
This module provides the DataSource base class that provides the
source data about events and the people and countries involved in them
from which other data is derived.
"""

__all__ = ['DataSource']

class DataSource(object):

    """
    A DataSource represents the underlying source (such as files or a
    database) for information about events and the people and
    countries involved in them.  DataSource is a base class for
    classes corresponding to the different supported sources of data.
    """

    def event_group_get_attr(self, name):
        """
        Return the value of an attribute for an EventGroup.  Possible
        names are: short_name, short_name_plural, long_name,
        distinguish_official, rank_top_n,
        honourable_mentions_available, _event_ids, _person_ids,
        _country_ids.
        """
        raise NotImplementedError

    def event_exists(self, id):
        """Return whether an event exists with the given id."""
        raise NotImplementedError

    def person_exists(self, id):
        """Return whether a person exists with the given id."""
        raise NotImplementedError

    def country_exists(self, id):
        """Return whether a country exists with the given id."""
        raise NotImplementedError

    def person_event_exists(self, person_id, event_id):
        """
        Return whether a person exists with the given id at the event
        with the given id.
        """
        raise NotImplementedError

    def country_event_exists(self, country_id, event_id):
        """
        Return whether a country exists with the given id at the event
        with the given id.
        """
        raise NotImplementedError

    def event_get_attr(self, id, name):
        """
        Return the value of an attribute for an Event.  Possible names
        are: short_name, long_name, year, _host_country_id,
        host_country_name, host_city, start_date, end_date,
        home_page_url, contact_name, contact_email, num_exams,
        num_problems, marks_per_problem, registration_active,
        gold_boundary, silver_boundary, bronze_boundary, paper_list,
        _person_ids, _country_ids, distinguish_official, rank_top_n,
        honourable_mentions_available.
        """
        raise NotImplementedError

    def event_have_attr(self, id, name):
        """
        Return whether this DataSource provides a value of an
        attribute for an Event, or whether it should be inherited from
        the EventGroup.  Possible names are: short_name, long_name,
        distinguish_official, rank_top_n,
        honourable_mentions_available.
        """
        return False

    def person_event_get_attr(self, person_id, event_id, name):
        """
        Return the value of an attribute for a PersonEvent.  Possible
        names are: _country_id, annual_url, primary_role, other_roles,
        _guide_for_ids, contestant_age, given_name, family_name,
        problem_scores, total_score, award, photo_url, first_language,
        second_language, diet, room_number, phone_number, generic_id,
        gender, date_of_birth, tshirt, arrival_place, arrival_time,
        arrival_flight, departure_place, departure_time,
        departure_flight.
        """
        raise NotImplementedError

    def person_event_have_attr(self, person_id, event_id, name):
        """
        Return whether this DataSource provides a value of an
        attribute for a PersonEvent, or whether it should be computed
        without cross-checking against a value from the DataSource.
        Possible names are: total_score, award.
        """
        return False

    def country_event_get_attr(self, country_id, event_id, name):
        """
        Return the value of an attribute for a CountryEvent.  Possible
        names are: annual_url, code, name, flag_url, is_official,
        _person_ids, _guide_ids, generic_id.
        """
        raise NotImplementedError

    def country_event_have_attr(self, country_id, event_id, name):
        """
        Return whether this DataSource provides a value of an
        attribute for a CountryEvent, or whether it should be computed
        from other attributes provided (in a way that may be less
        efficient if the DataSource is querying a database).  Possible
        names are: _person_ids, _guide_ids.
        """
        return False
