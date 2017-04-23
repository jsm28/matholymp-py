# Templating support for Roundup registration system for matholymp package.

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
This module provides templating support for the Roundup registration
system.
"""

__all__ = ['people_from_country_internal', 'people_from_country',
           'show_country_people', 'country_people_table', 'all_people_table',
           'person_scores_table', 'country_scores_table', 'scoreboard_gen',
           'scoreboard', 'display_scoreboard', 'has_nonempty_travel',
           'show_travel_copy_options', 'country_travel_copy_options',
           'person_case_warning', 'list_expected_roles', 'registration_status',
           'registration_status_country', 'show_consent_form_ui',
           'required_person_fields', 'register_templating_utils']

import cgi
import json
import os
import re

from roundup.cgi.templating import HTMLItem
from roundup.date import Date

from matholymp.caseconv import all_uppercase
from matholymp.collate import coll_get_sort_key
from matholymp.roundupreg.cache import cached_text
from matholymp.roundupreg.roundupsitegen import RoundupSiteGenerator
from matholymp.roundupreg.rounduputil import distinguish_official, \
    have_consent_forms, have_passport_numbers, have_nationality, require_dob, \
    contestant_age, normal_country_person, person_is_contestant, \
    contestant_code, pn_score, scores_final, any_scores_missing, \
    country_has_contestants, valid_country_problem

def people_from_country_internal(db, country):
    """
    Return a list of people from a given country, sorted first by role
    then by family name then by given name.
    """
    person_list = db.person.filter(None, {'country': country})
    sorted_list = sorted(
        person_list,
        key=lambda x:coll_get_sort_key(db.person.get(x, 'given_name')))
    sorted_list = sorted(
        sorted_list,
        key=lambda x:coll_get_sort_key(db.person.get(x, 'family_name')))
    sorted_list = sorted(
        sorted_list,
        key=lambda x:coll_get_sort_key(
            db.matholymprole.get(db.person.get(x, 'primary_role'), 'name')))
    return sorted_list

def people_from_country(db, country):
    """
    Return a list of people from a given country, sorted first by role
    then by family name then by given name, for templating use.
    """
    sorted_list = people_from_country_internal(db._db, country)
    return [HTMLItem(db._client, 'person', i) for i in sorted_list]

def show_country_people(db, country):
    """Return whether to show a table of people on a country's page."""
    return (db.country.get(country, 'participants_ok') and
            not db.country.is_retired(country))

def country_people_table(db, country):
    """Show the table of people from a country on that country's page."""
    sitegen = RoundupSiteGenerator(db)
    c = sitegen.event.country_map[int(country)]
    return sitegen.country_event_people_table(c, True)

def all_people_table(db):
    """Show the table of all people."""
    sitegen = RoundupSiteGenerator(db)
    event = sitegen.event
    return sitegen.event_people_table(event)

def person_scores_table(db, person):
    """Show the table of scores for a person on that person's page."""
    sitegen = RoundupSiteGenerator(db)
    p = sitegen.event.person_map[int(person)]
    assert len(p) == 1
    p = p[0]
    return sitegen.person_event_scores_table(p, show_rank=False,
                                             show_code=False, show_name=False)

def country_scores_table(db, country):
    """Show the table of scores for a country on that country's page."""
    sitegen = RoundupSiteGenerator(db)
    c = sitegen.event.country_map[int(country)]
    return sitegen.country_event_scores_table(c, show_rank=False)

def scoreboard_gen(db):
    """Produce scoreboard page contents from the database."""
    sitegen = RoundupSiteGenerator(db)
    return sitegen.scoreboard_text(sitegen.event)

def scoreboard(db, force_regen):
    """Produce scoreboard page contents, possibly cached."""
    return cached_text(db, 'scoreboard', force_regen, scoreboard_gen)

def display_scoreboard(db, display_start):
    """Produce display scoreboard page contents."""
    sitegen = RoundupSiteGenerator(db)
    return sitegen.display_scoreboard_text(sitegen.event, display_start)

def has_nonempty_travel(db, person):
    """Return whether a person has nonempty travel details."""
    return (db.person.get(person, 'arrival_place') is not None or
            db.person.get(person, 'arrival_time') is not None or
            db.person.get(person, 'arrival_flight') is not None or
            db.person.get(person, 'departure_place') is not None or
            db.person.get(person, 'departure_time') is not None or
            db.person.get(person, 'departure_flight') is not None)

def show_travel_copy_options(db, userid, person):
    """Return whether to give options to copy travel details."""
    if normal_country_person(db, userid):
        return True
    if not person:
        return False
    country = db.person.get(person, 'country')
    return db.country.get(country, 'is_normal')

def country_travel_copy_options(db, country, person):
    """
    Produce text giving the option to copy travel details from any
    other person from this country with nonempty travel details.
    """
    person_list = people_from_country_internal(db, country)
    person_list = [i for i in person_list
                   if i != person and has_nonempty_travel(db, i)]
    travel_list = []
    for person in person_list:
        prop_js_list = []
        text_props = ['arrival_flight', 'arrival_time',
                      'departure_flight', 'departure_time']
        for prop in text_props:
            val = db.person.get(person, prop)
            if val is None:
                val = ''
            prop_js_list.append('this.form.elements["%s"].value = %s' %
                                (prop, json.dumps(str(val))))
        for prop in 'arrival_place', 'departure_place':
            val = db.person.get(person, prop)
            if val is None:
                val = '-1'
                prop_js_list.append('this.form.elements["%s"].selectedIndex'
                                    ' = -1' % prop)
            prop_js_list.append(
                'for (var i = 0; i < this.form.elements["%s"].length; i++) '
                '{ if (this.form.elements["%s"].options[i].value == "%s") '
                'this.form.elements["%s"].selectedIndex = i; }' %
                (prop, prop, val, prop))
        prop_js = ';'.join(prop_js_list)
        prop_js_esc = cgi.escape(prop_js, quote=True)
        prop_js_submit = ('<input type="button"'
                          ' value="Copy travel details from %s %s"'
                          ' onclick="%s">' %
                          (cgi.escape(db.person.get(person, 'given_name'),
                                      quote=True),
                           cgi.escape(db.person.get(person, 'family_name'),
                                      quote=True), prop_js_esc))
        travel_list.append(prop_js_submit)
    return '\n'.join(travel_list)

def person_case_warning(db, person):
    """Return an HTML warning about all-upper-case parts of a person's name."""
    given_name = db.person.get(person, 'given_name')
    family_name = db.person.get(person, 'family_name')
    given_all_uc = all_uppercase(given_name)
    family_all_uc = all_uppercase(family_name)
    warn_text = ''
    if given_all_uc and family_all_uc:
        warn_text = 'Warning: name has been entered in all upper case.'
    elif family_all_uc:
        warn_text = 'Warning: family name has been entered in all upper case.'
    elif given_all_uc:
        warn_text = 'Warning: given name has been entered in all upper case.'
    if warn_text:
        warn_text = '<strong>%s</strong>' % warn_text
    return warn_text

def list_expected_roles(db):
    """List the roles expected to be present for a normal country."""
    main_role_list = ['Leader', 'Deputy Leader']
    cont_per_team = int(db.config.ext['MATHOLYMP_NUM_CONTESTANTS_PER_TEAM'])
    main_role_list.extend([('Contestant %d' % (i + 1))
                           for i in range(cont_per_team)])
    return main_role_list

def registration_status(db):
    """Produce registration status page contents for all countries."""
    sitegen = RoundupSiteGenerator(db)
    main_role_list = list_expected_roles(db)
    consent_forms_date = db.config.ext['MATHOLYMP_CONSENT_FORMS_DATE']
    if consent_forms_date == '':
        consent_forms_date = None
    max_photo_size = int(db.config.ext['MATHOLYMP_PHOTO_MAX_SIZE'])
    return sitegen.registration_status_text(main_role_list, consent_forms_date,
                                            max_photo_size)

def registration_status_country(db, userid):
    """Produce registration status page contents for one country."""
    if not normal_country_person(db, userid):
        return '<p>Cannot produce registration status for this user.</p>\n'
    sitegen = RoundupSiteGenerator(db)
    main_role_list = list_expected_roles(db)
    consent_forms_date = db.config.ext['MATHOLYMP_CONSENT_FORMS_DATE']
    if consent_forms_date == '':
        consent_forms_date = None
    user_country = db.user.get(userid, 'country')
    c = sitegen.event.country_map[int(user_country)]
    return sitegen.registration_status_country_text(c, main_role_list,
                                                    consent_forms_date)

def show_consent_form_ui(db, person):
    """Return whether to show the interface to upload a consent form."""
    if not have_consent_forms(db):
        return False
    if db.person.get(person, 'consent_form'):
        # Always show the interface if a form has been uploaded, even
        # if the date of birth shows the form was unnecessary.
        return True
    date_of_birth = db.person.get(person, 'date_of_birth')
    if date_of_birth is None:
        return True
    consent_forms_date = db.config.ext['MATHOLYMP_CONSENT_FORMS_DATE']
    return date_of_birth >= Date(consent_forms_date)

def required_person_fields(db):
    """Return the list of fields required for registered people."""
    req = ['country', 'given_name', 'family_name', 'gender', 'primary_role',
           'first_language', 'tshirt']
    if require_dob(db):
        req.append('date_of_birth')
    if have_passport_numbers(db):
        req.append('passport_number')
    if have_nationality(db):
        req.append('nationality')
    return req

def register_templating_utils(instance):
    """Register functions for use from page templates with Roundup."""
    instance.registerUtil('distinguish_official', distinguish_official)
    instance.registerUtil('have_consent_forms', have_consent_forms)
    instance.registerUtil('have_passport_numbers', have_passport_numbers)
    instance.registerUtil('have_nationality', have_nationality)
    instance.registerUtil('require_dob', require_dob)
    instance.registerUtil('normal_country_person', normal_country_person)
    instance.registerUtil('person_is_contestant', person_is_contestant)
    instance.registerUtil('people_from_country', people_from_country)
    instance.registerUtil('show_country_people', show_country_people)
    instance.registerUtil('country_people_table', country_people_table)
    instance.registerUtil('all_people_table', all_people_table)
    instance.registerUtil('contestant_code', contestant_code)
    instance.registerUtil('contestant_age', contestant_age)
    instance.registerUtil('pn_score', pn_score)
    instance.registerUtil('scores_final', scores_final)
    instance.registerUtil('person_scores_table', person_scores_table)
    instance.registerUtil('country_scores_table', country_scores_table)
    instance.registerUtil('scoreboard', scoreboard)
    instance.registerUtil('display_scoreboard', display_scoreboard)
    instance.registerUtil('any_scores_missing', any_scores_missing)
    instance.registerUtil('country_has_contestants', country_has_contestants)
    instance.registerUtil('valid_country_problem', valid_country_problem)
    instance.registerUtil('show_travel_copy_options', show_travel_copy_options)
    instance.registerUtil('country_travel_copy_options',
                          country_travel_copy_options)
    instance.registerUtil('person_case_warning', person_case_warning)
    instance.registerUtil('registration_status', registration_status)
    instance.registerUtil('registration_status_country',
                          registration_status_country)
    instance.registerUtil('show_consent_form_ui', show_consent_form_ui)
    instance.registerUtil('required_person_fields', required_person_fields)
