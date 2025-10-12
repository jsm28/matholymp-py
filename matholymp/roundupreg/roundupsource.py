# RoundupDataSource class for matholymp package.

# Copyright 2014-2025 Joseph Samuel Myers.

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
from matholymp.fileutil import comma_split
from matholymp.roundupreg.config import distinguish_official, \
    have_consent_forms, have_id_scans, have_consent_ui, \
    have_passport_numbers, have_nationality, get_num_problems, get_num_exams, \
    get_marks_per_problem, get_language_numbers, get_short_name, \
    honourable_mentions_available, event_type, have_remote_participation, \
    get_sars_cov2_cert_bool, get_sars_cov2_doses_bool, get_sars_cov2_after_bool
from matholymp.roundupreg.rounduputil import scores_from_str, \
    person_date_of_birth, contestant_age, db_file_url, person_is_remote

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
            return get_short_name(self._db)
        elif name == 'distinguish_official':
            return distinguish_official(self._db)
        elif name == 'rank_top_n':
            s = self._db.config.ext['MATHOLYMP_RANK_TOP_N']
            if s:
                return int(s)
            else:
                return None
        elif name == 'honourable_mentions_available':
            return honourable_mentions_available(self._db)
        elif name == '_event_ids':
            return [int(self._db.config.ext['MATHOLYMP_EVENT_NUMBER'])]
        elif name == '_person_ids':
            return [int(p) for p in self._db.person.list()]
        elif name == '_country_ids':
            return [int(c) for c in self._db.country.list()
                    if self._db.country.get(c, 'participants_ok')]
        raise KeyError(name)

    def event_exists(self, event_id):
        return self._db.config.ext['MATHOLYMP_EVENT_NUMBER'] == str(event_id)

    def person_exists(self, person_id):
        person_id = str(person_id)
        return (self._db.person.hasnode(person_id)
                and not self._db.person.is_retired(person_id))

    def country_exists(self, country_id):
        country_id = str(country_id)
        return (self._db.country.hasnode(country_id)
                and not self._db.country.is_retired(country_id)
                and self._db.country.get(country_id, 'participants_ok'))

    def person_event_exists(self, person_id, event_id):
        return self.person_exists(person_id)

    def country_event_exists(self, country_id, event_id):
        return self.country_exists(country_id)

    def event_get_attr(self, event_id, name):
        if name == 'num_problems':
            return get_num_problems(self._db)
        elif name == 'marks_per_problem':
            return get_marks_per_problem(self._db)
        elif name == 'num_exams':
            return get_num_exams(self._db)
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
        elif name == 'age_day_desc':
            return self._db.config.ext['MATHOLYMP_AGE_DAY_DESC']
        elif name == 'host_type':
            return event_type(self._db)
        raise KeyError(name)

    def person_event_get_attr(self, person_id, country_id, event_id, name):
        person_id = str(person_id)
        if name == '_country_ids':
            assert country_id is None
            return [int(self._db.person.get(person_id, 'country'))]
        assert country_id is not None
        if name == 'annual_url':
            return self._db.config.TRACKER_WEB + 'person' + person_id
        elif name == 'primary_role':
            primary_role = self._db.person.get(person_id, 'primary_role')
            return self._db.matholymprole.get(primary_role, 'name')
        elif name == 'other_roles':
            other_roles = self._db.person.get(person_id, 'other_roles')
            if other_roles is None:
                other_roles = []
            primary_role = self._db.person.get(person_id, 'primary_role')
            other_roles = [i for i in other_roles if i != primary_role]
            return [self._db.matholymprole.get(i, 'name') for i in other_roles]
        elif name == '_guide_for_ids':
            guide_for = self._db.person.get(person_id, 'guide_for')
            if guide_for is None:
                guide_for = []
            return [int(c) for c in guide_for]
        elif name == 'contestant_age':
            return contestant_age(self._db, person_id)
        elif name == 'given_name':
            return self._db.person.get(person_id, 'given_name')
        elif name == 'family_name':
            return self._db.person.get(person_id, 'family_name')
        elif name == 'problem_scores':
            score_str = self._db.person.get(person_id, 'scores')
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
            extra_awards_str = self._db.person.get(person_id, 'extra_awards')
            if extra_awards_str is None:
                return []
            return comma_split(extra_awards_str)
        elif name in ('photo_url', 'photo_thumb_url', 'badge_photo_url'):
            if name != 'badge_photo_url' and have_consent_ui(self._db):
                if self._db.person.get(person_id, 'photo_consent') != 'yes':
                    return None
            photo_id = self._db.person.get(person_id, 'photo')
            if name == 'photo_thumb_url':
                return ('%sphoto%s?@action=photo_thumb&width=%%(width)d'
                        % (self._db.config.TRACKER_WEB, photo_id))
            else:
                return db_file_url(self._db, 'photo', 'photo', photo_id)
        elif name in ('photo_filename', 'badge_photo_filename'):
            if name == 'photo_filename' and have_consent_ui(self._db):
                if self._db.person.get(person_id, 'photo_consent') != 'yes':
                    return None
            photo_id = self._db.person.get(person_id, 'photo')
            photo_filename = None
            if photo_id is not None:
                photo_filename = self._db.filename('photo', photo_id)
            return photo_filename
        elif name == 'consent_form_url':
            if not have_consent_forms(self._db):
                return None
            consent_form_id = self._db.person.get(person_id, 'consent_form')
            return db_file_url(self._db, 'consent_form', 'consent-form',
                               consent_form_id)
        elif name == 'consent_form_filename':
            if not have_consent_forms(self._db):
                return None
            consent_form_id = self._db.person.get(person_id, 'consent_form')
            consent_form_filename = None
            if consent_form_id is not None:
                consent_form_filename = self._db.filename('consent_form',
                                                          consent_form_id)
            return consent_form_filename
        elif name == 'id_scan_url':
            if not have_id_scans(self._db):
                return None
            id_scan_id = self._db.person.get(person_id, 'id_scan')
            return db_file_url(self._db, 'id_scan', 'id-scan',
                               id_scan_id)
        elif name == 'id_scan_filename':
            if not have_id_scans(self._db):
                return None
            id_scan_id = self._db.person.get(person_id, 'id_scan')
            id_scan_filename = None
            if id_scan_id is not None:
                id_scan_filename = self._db.filename('id_scan',
                                                     id_scan_id)
            return id_scan_filename
        elif name in ('script_scan_urls', 'script_scan_filenames'):
            num_problems = get_num_problems(self._db)
            return [None for n in range(num_problems)]
        elif name in ('scratch_scan_urls', 'scratch_scan_filenames'):
            num_exams = get_num_exams(self._db)
            return [None for n in range(num_exams)]
        elif name == 'event_photos_consent':
            if not have_consent_ui(self._db):
                return None
            return self._db.person.get(person_id, 'event_photos_consent')
        elif name == 'remote_participant':
            return person_is_remote(self._db, person_id)
        elif name == 'basic_data_missing':
            return self._db.person.get(person_id, 'incomplete')
        elif name == 'badge_background':
            primary_role = self._db.person.get(person_id, 'primary_role')
            badge_type = self._db.matholymprole.get(primary_role, 'badge_type')
            return self._db.badge_type.get(badge_type, 'background_name')
        elif name == 'badge_colour_outer':
            primary_role = self._db.person.get(person_id, 'primary_role')
            badge_type = self._db.matholymprole.get(primary_role, 'badge_type')
            return self._db.badge_type.get(badge_type, 'colour_outer')
        elif name == 'badge_colour_inner':
            primary_role = self._db.person.get(person_id, 'primary_role')
            badge_type = self._db.matholymprole.get(primary_role, 'badge_type')
            return self._db.badge_type.get(badge_type, 'colour_inner')
        elif name == 'badge_colour_text':
            primary_role = self._db.person.get(person_id, 'primary_role')
            badge_type = self._db.matholymprole.get(primary_role, 'badge_type')
            return self._db.badge_type.get(badge_type, 'colour_text')
        elif name == 'languages':
            ret = []
            langs = set()
            for i in get_language_numbers(self._db):
                lang = self._db.person.get(person_id, 'language_%d' % i)
                if lang is not None and lang not in langs:
                    langs.add(lang)
                    lang_name = self._db.language.get(lang, 'name')
                    ret.append(lang_name)
            return ret
        elif name == 'diet':
            return self._db.person.get(person_id, 'diet') or None
        elif name == 'sars_cov2_cert':
            if not get_sars_cov2_cert_bool(self._db):
                return None
            sars_cov2_cert = self._db.person.get(person_id, 'sars_cov2_cert')
            if not sars_cov2_cert:
                return None
            return sars_cov2_cert == 'yes'
        elif name == 'sars_cov2_doses':
            if not get_sars_cov2_doses_bool(self._db):
                return None
            return self._db.person.get(person_id, 'sars_cov2_doses') or None
        elif name == 'sars_cov2_after':
            if not get_sars_cov2_after_bool(self._db):
                return None
            sars_cov2_after = self._db.person.get(person_id, 'sars_cov2_after')
            if not sars_cov2_after:
                return None
            return sars_cov2_after == 'yes'
        elif name == 'room_type':
            room_type = self._db.person.get(person_id, 'room_type')
            if room_type is None:
                return None
            else:
                return self._db.room_type.get(room_type, 'name')
        elif name == 'room_share_with':
            return self._db.person.get(person_id, 'room_share_with') or None
        elif name == 'room_number':
            return self._db.person.get(person_id, 'room_number') or None
        elif name == 'phone_number':
            return self._db.person.get(person_id, 'phone_number') or None
        elif name == 'generic_id':
            generic_url = self._db.person.get(person_id, 'generic_url')
            gubase = (self._db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
                      + 'people/person')
            if (generic_url is None or not generic_url.startswith(gubase)
                or not generic_url.endswith('/')):
                generic_id = None
            else:
                generic_id = int(generic_url[len(gubase):-1])
            return generic_id
        elif name == 'gender':
            gender = self._db.person.get(person_id, 'gender')
            if gender is None:
                return None
            else:
                return self._db.gender.get(gender, 'name')
        elif name == 'date_of_birth':
            return person_date_of_birth(self._db, person_id)
        elif name == 'passport_number':
            if not have_passport_numbers(self._db):
                return None
            return self._db.person.get(person_id, 'passport_number') or None
        elif name == 'nationality':
            if not have_nationality(self._db):
                return None
            return self._db.person.get(person_id, 'nationality') or None
        elif name == 'passport_given_name':
            if (not have_passport_numbers(self._db)
                or not have_nationality(self._db)):
                return self._db.person.get(person_id, 'given_name')
            return (self._db.person.get(person_id, 'passport_given_name')
                    or self._db.person.get(person_id, 'given_name'))
        elif name == 'passport_family_name':
            if (not have_passport_numbers(self._db)
                or not have_nationality(self._db)):
                return self._db.person.get(person_id, 'family_name')
            return (self._db.person.get(person_id, 'passport_family_name')
                    or self._db.person.get(person_id, 'family_name'))
        elif name == 'tshirt':
            tshirt = self._db.person.get(person_id, 'tshirt')
            if tshirt is None:
                return None
            else:
                return self._db.tshirt.get(tshirt, 'name')
        elif name == 'arrival_place':
            arrival_place = self._db.person.get(person_id, 'arrival_place')
            if arrival_place is None:
                return None
            else:
                return self._db.arrival.get(arrival_place, 'name')
        elif name == 'arrival_is_airport':
            arrival_place = self._db.person.get(person_id, 'arrival_place')
            if arrival_place is None:
                return False
            else:
                return self._db.arrival.get(arrival_place, 'isairport')
        elif name == 'arrival_date':
            date = self._db.person.get(person_id, 'arrival_date')
            if date is None:
                return None
            else:
                return date_from_ymd_iso('arrival date', date)
        elif name == 'arrival_time':
            hour = self._db.person.get(person_id, 'arrival_time_hour')
            minute = self._db.person.get(person_id, 'arrival_time_minute')
            if hour is None or minute is None:
                return None
            else:
                return time_from_hhmm_str('arrival time', hour, minute)
        elif name == 'arrival_flight':
            return self._db.person.get(person_id, 'arrival_flight') or None
        elif name == 'departure_place':
            departure_place = self._db.person.get(person_id, 'departure_place')
            if departure_place is None:
                return None
            else:
                return self._db.arrival.get(departure_place, 'name')
        elif name == 'departure_is_airport':
            departure_place = self._db.person.get(person_id, 'departure_place')
            if departure_place is None:
                return False
            else:
                return self._db.arrival.get(departure_place, 'isairport')
        elif name == 'departure_date':
            date = self._db.person.get(person_id, 'departure_date')
            if date is None:
                return None
            else:
                return date_from_ymd_iso('departure date', date)
        elif name == 'departure_time':
            hour = self._db.person.get(person_id, 'departure_time_hour')
            minute = self._db.person.get(person_id, 'departure_time_minute')
            if hour is None or minute is None:
                return None
            else:
                return time_from_hhmm_str('departure time', hour, minute)
        elif name == 'departure_flight':
            return self._db.person.get(person_id, 'departure_flight') or None
        raise KeyError(name)

    def country_event_get_attr(self, country_id, event_id, name):
        country_id = str(country_id)
        if name == 'annual_url':
            return self._db.config.TRACKER_WEB + 'country' + country_id
        elif name == 'code':
            return self._db.country.get(country_id, 'code')
        elif name == 'name':
            return self._db.country.get(country_id, 'name')
        elif name == 'flag_url':
            flag_id = self._db.country.get(country_id, 'flag')
            return db_file_url(self._db, 'flag', 'flag', flag_id)
        elif name == 'flag_filename':
            flag_id = self._db.country.get(country_id, 'flag')
            flag_filename = None
            if flag_id is not None:
                flag_filename = self._db.filename('flag', flag_id)
            return flag_filename
        elif name == 'is_official':
            return self._db.country.get(country_id, 'official')
        elif name == 'is_normal':
            return self._db.country.get(country_id, 'is_normal')
        elif name == 'contact_emails':
            contact_main = self._db.country.get(country_id, 'contact_email')
            if contact_main is None:
                contact_list = []
            else:
                contact_list = [contact_main]
            contact_extra = self._db.country.get(country_id, 'contact_extra')
            if contact_extra is not None:
                contact_extra_list = [val.strip()
                                      for val in contact_extra.split('\n')]
                contact_extra_list = [val for val in contact_extra_list if val]
                contact_list.extend(contact_extra_list)
            return contact_list
        elif name in ('expected_leaders', 'expected_deputies',
                      'expected_contestants', 'expected_observers_a',
                      'expected_observers_b', 'expected_observers_c',
                      'expected_single_rooms'):
            return int(self._db.country.get(country_id, name))
        elif name == 'expected_numbers_confirmed':
            return self._db.country.get(country_id,
                                        'expected_numbers_confirmed')
        elif name in ('billing_address', 'leader_email'):
            return self._db.country.get(country_id, name)
        elif name == 'physical_address':
            if not have_remote_participation(self._db):
                return None
            return self._db.country.get(country_id, name)
        elif name == 'participation_type':
            this_event_type = event_type(self._db)
            if this_event_type in ('in-person', 'virtual'):
                return this_event_type
            return self._db.country.get(country_id, 'participation_type')
        elif name == '_person_ids':
            person_list = self._db.person.filter(None, {'country': country_id})
            return [int(p) for p in person_list]
        elif name == '_guide_ids':
            guide_list = self._db.person.filter(None,
                                                {'guide_for': country_id})
            return [int(p) for p in guide_list]
        elif name == 'generic_id':
            generic_url = self._db.country.get(country_id, 'generic_url')
            gubase = (self._db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
                      + 'countries/country')
            if (generic_url is None or not generic_url.startswith(gubase)
                or not generic_url.endswith('/')):
                generic_id = None
            else:
                generic_id = int(generic_url[len(gubase):-1])
            return generic_id
        raise KeyError(name)

    def country_event_have_attr(self, country_id, event_id, name):
        return True
