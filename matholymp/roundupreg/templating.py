# Templating support for Roundup registration system for matholymp package.

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
This module provides templating support for the Roundup registration
system.
"""

__all__ = ['people_from_country_internal', 'people_from_country',
           'country_people_table', 'all_people_table', 'person_scores_table',
           'country_scores_table', 'scoreboard', 'has_nonempty_travel',
           'country_travel_copy_options', 'missing_person_details',
           'registration_status', 'register_templating_utils']

import cgi
import json
import re

from roundup.cgi.templating import HTMLItem

from matholymp.collate import coll_get_sort_key
from matholymp.roundupreg.roundupsitegen import RoundupSiteGenerator
from matholymp.roundupreg.rounduputil import contestant_age, \
    get_none_country, get_staff_country, normal_country_person, \
    person_is_contestant, contestant_code, pn_score, scores_final, \
    any_scores_missing, country_has_contestants, valid_country_problem

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
    return sitegen.person_event_scores_table(p, show_rank=False,
                                             show_code=False, show_name=False)

def country_scores_table(db, country):
    """Show the table of scores for a country on that country's page."""
    sitegen = RoundupSiteGenerator(db)
    c = sitegen.event.country_map[int(country)]
    return sitegen.country_event_scores_table(c, show_rank=False)

def scoreboard(db, for_display, display_start):
    """Produce scoreboard page contents."""
    return RoundupSiteGenerator(db).this_event_scoreboard_text(for_display,
                                                               display_start)

def has_nonempty_travel(db, person):
    """Return whether a person has nonempty travel details."""
    return (db.person.get(person, 'arrival_place') is not None or
            db.person.get(person, 'arrival_time') is not None or
            db.person.get(person, 'arrival_flight') is not None or
            db.person.get(person, 'departure_place') is not None or
            db.person.get(person, 'departure_time') is not None or
            db.person.get(person, 'departure_flight') is not None)

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

def missing_person_details(db, person):
    """Return a description of missing details for a person."""

    missing_list = []

    if not db.person.get(person, 'files'):
        missing_list.append('photo')

    have_travel_details = True
    arrival_place = db.person.get(person, 'arrival_place')
    arrival_time = db.person.get(person, 'arrival_time')
    departure_place = db.person.get(person, 'departure_place')
    departure_time = db.person.get(person, 'departure_time')
    if not arrival_place or not arrival_time:
        have_travel_details = False
    elif not departure_place or not departure_time:
        have_travel_details = False
    else:
        arrival_place_name = db.arrival.get(arrival_place, 'name')
        if 'Airport' in arrival_place_name:
            arrival_flight = db.person.get(person, 'arrival_flight')
            if not arrival_flight:
                have_travel_details = False
        departure_place_name = db.arrival.get(departure_place, 'name')
        if 'Airport' in departure_place_name:
            departure_flight = db.person.get(person, 'departure_flight')
            if not departure_flight:
                have_travel_details = False
    if not have_travel_details:
        missing_list.append('travel details')

    role = db.person.get(person, 'primary_role')
    guide = db.matholymprole.lookup('Guide')
    if role == guide and not db.person.get(person, 'phone_number'):
        missing_list.append('phone number')

    return ', '.join(missing_list)

def registration_status(db):
    """Produce registration status page contents."""

    country_list_all = db.country.list()
    none_country = get_none_country(db)
    staff_country = get_staff_country(db)
    country_list_all = [c for c in country_list_all if c != none_country]
    country_codes = {}
    country_names = {}
    for c in country_list_all:
        country_codes[c] = db.country.get(c, 'code')
        country_names[c] = db.country.get(c, 'name')
    country_list_all = sorted(country_list_all, key=lambda x:country_codes[x])
    country_list = [c for c in country_list_all if c != staff_country]
    main_role_list = ['Leader', 'Deputy Leader']
    cont_per_team = int(db.config.ext['MATHOLYMP_NUM_CONTESTANTS_PER_TEAM'])
    main_role_list.extend([('Contestant %d' % (i + 1))
                           for i in range(cont_per_team)])

    text = '<h2>Action needed by participating countries</h2>\n'
    details_needed = ''
    for c in country_list:
        person_list = people_from_country_internal(db, c)
        if not person_list:
            text += ('<p>No participants registered from'
                     ' <strong>%s (%s)</strong>.</p>\n' %
                     (cgi.escape(country_names[c]),
                      cgi.escape(country_codes[c])))
        else:
            have_roles = [
                db.matholymprole.get(db.person.get(p, 'primary_role'), 'name')
                for p in person_list]
            missing_roles = [r for r in main_role_list if not r in have_roles]
            if missing_roles:
                text += ('<p>Not registered from <strong>%s (%s)</strong>:'
                         ' %s.</p>\n' %
                         (cgi.escape(country_names[c]),
                          cgi.escape(country_codes[c]),
                          ', '.join(missing_roles)))
        for p in person_list:
            p_needed = missing_person_details(db, p)
            if p_needed:
                details_needed += ('<tr><td>%s (%s)</td>'
                                   '<td><a href="person%s">%s %s</a></td>'
                                   '<td>%s</td></tr>\n' %
                                   (cgi.escape(country_names[c]),
                                    cgi.escape(country_codes[c]),
                                    p,
                                    cgi.escape(db.person.get(p, 'given_name')),
                                    cgi.escape(db.person.get(p,
                                                             'family_name')),
                                    p_needed))
    text += ('<p>Some countries may intend to send Observers'
             ' but not have registered them all.</p>\n')
    if details_needed:
        text += '<table class="list">\n'
        text += ('<tr><th>Country</th><th>Person</th>'
                 '<th>Missing data</th></tr>\n')
        text += details_needed
        text += '</table>\n'

    text += '<h2>Action needed by the organisers</h2>\n'
    for c in country_list:
        if not db.person.filter(None, {'guide_for': c}):
            text += ('<p>No guide registered for'
                     ' <strong>%s (%s)</strong>.</p>\n' %
                     (cgi.escape(country_names[c]),
                      cgi.escape(country_codes[c])))
    text += ('<p>The system cannot tell automatically if not all'
             ' staff have been registered.</p>\n')
    person_list = people_from_country_internal(db, staff_country)
    s_details_needed = ''
    for p in person_list:
        p_needed = missing_person_details(db, p)
        if p_needed:
            s_details_needed += ('<tr><td><a href="person%s">%s %s</a></td>'
                                 '<td>%s</td></tr>\n' %
                                 (p,
                                  cgi.escape(db.person.get(p, 'given_name')),
                                  cgi.escape(db.person.get(p, 'family_name')),
                                  p_needed))
    if s_details_needed:
        text += '<table class="list">\n'
        text += '<tr><th>Person</th><th>Missing data</th></tr>\n'
        text += s_details_needed
        text += '</table>\n'

    rooms_needed = ''
    for c in country_list_all:
        person_list = people_from_country_internal(db, c)
        for p in person_list:
            if not db.person.get(p, 'room_number'):
                rooms_needed += ('<tr><td>%s (%s)</td>'
                                 '<td><a href="person%s">%s %s</a></td>'
                                 '<td>%s</td></tr>\n' %
                                 (cgi.escape(country_names[c]),
                                  cgi.escape(country_codes[c]),
                                  p,
                                  cgi.escape(db.person.get(p, 'given_name')),
                                  cgi.escape(db.person.get(p, 'family_name')),
                                  cgi.escape(db.matholymprole.get(
                                      db.person.get(p, 'primary_role'),
                                      'name'))))
    if rooms_needed:
        text += '<h2>Room allocations needed</h2>\n'
        text += ('<p>For staff using their own accommodation,'
                 ' enter &lsquo;Own accommodation&rsquo;,'
                 ' or a more precise location for any Guides'
                 ' (whose room numbers will appear on badges of'
                 ' their team members).</p>\n')
        text += '<table class="list">\n'
        text += '<tr><th>Country</th><th>Person</th><th>Role</th></tr>\n'
        text += rooms_needed
        text += '</table>\n'

    flags_needed = ''
    for c in country_list:
        if not db.country.get(c, 'files'):
            flags_needed += ('<p>No flag for <strong>%s (%s)</strong>.</p>\n' %
                             (cgi.escape(country_names[c]),
                              cgi.escape(country_codes[c])))
    if flags_needed:
        text += '<h2>Action needed by registration system maintainers</h2>\n'
        text += flags_needed

    return text

def register_templating_utils(instance):
    """Register functions for use from page templates with Roundup."""
    instance.registerUtil('normal_country_person', normal_country_person)
    instance.registerUtil('person_is_contestant', person_is_contestant)
    instance.registerUtil('people_from_country', people_from_country)
    instance.registerUtil('country_people_table', country_people_table)
    instance.registerUtil('all_people_table', all_people_table)
    instance.registerUtil('contestant_code', contestant_code)
    instance.registerUtil('contestant_age', contestant_age)
    instance.registerUtil('pn_score', pn_score)
    instance.registerUtil('scores_final', scores_final)
    instance.registerUtil('person_scores_table', person_scores_table)
    instance.registerUtil('country_scores_table', country_scores_table)
    instance.registerUtil('scoreboard', scoreboard)
    instance.registerUtil('any_scores_missing', any_scores_missing)
    instance.registerUtil('country_has_contestants', country_has_contestants)
    instance.registerUtil('valid_country_problem', valid_country_problem)
    instance.registerUtil('country_travel_copy_options',
                          country_travel_copy_options)
    instance.registerUtil('registration_status', registration_status)
