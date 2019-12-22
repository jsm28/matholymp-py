# Templating support for Roundup registration system for matholymp package.

# Copyright 2014-2019 Joseph Samuel Myers.

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
           'person_case_warning', 'registration_status',
           'registration_status_country', 'edit_rooms', 'show_consent_form_ui',
           'has_consent_for_photo', 'string_select', 'date_of_birth_select',
           'arrdep_date_select', 'arrdep_time_select', 'photo_consent_select',
           'score_country_select', 'show_incomplete', 'required_person_fields',
           'register_templating_utils', 'show_prereg_sidebar',
           'show_prereg_reminder', 'bulk_csv_contents',
           'show_bulk_csv_country', 'show_bulk_csv_country_link_from_code',
           'show_bulk_csv_person', 'required_user_fields']

import base64
import datetime
import html
import json

from roundup.cgi.templating import HTMLItem

from matholymp.caseconv import all_uppercase
from matholymp.collate import coll_get_sort_key
from matholymp.datetimeutil import month_name, date_to_ymd_iso, date_to_name
from matholymp.roundupreg.cache import cached_text
from matholymp.roundupreg.roundupsitegen import RoundupSiteGenerator
from matholymp.roundupreg.rounduputil import distinguish_official, \
    get_consent_forms_date, have_consent_forms, have_consent_ui, \
    have_passport_numbers, have_nationality, require_diet, require_dob, \
    get_language_numbers, get_earliest_date_of_birth, \
    get_sanity_date_of_birth, person_date_of_birth, contestant_age, \
    get_arrdep_bounds, person_is_contestant, contestant_code, pn_score, \
    scores_final, any_scores_missing, country_has_contestants, \
    valid_country_problem, bulk_csv_delimiter, bulk_csv_data, \
    bulk_csv_contact_emails, bulk_csv_country_number_url, \
    bulk_csv_person_number_url
from matholymp.roundupreg.staticsite import static_site_event_group


def people_from_country_internal(db, country):
    """
    Return a list of people from a given country, sorted first by role
    then by family name then by given name.
    """
    person_list = db.person.filter(None, {'country': country})
    sorted_list = sorted(
        person_list,
        key=lambda x: coll_get_sort_key(db.person.get(x, 'given_name')))
    sorted_list = sorted(
        sorted_list,
        key=lambda x: coll_get_sort_key(db.person.get(x, 'family_name')))
    sorted_list = sorted(
        sorted_list,
        key=lambda x: coll_get_sort_key(
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
    return (db.country.get(country, 'participants_ok')
            and not db.country.is_retired(country))


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
    return (db.person.get(person, 'arrival_place') is not None
            or db.person.get(person, 'arrival_date') is not None
            or db.person.get(person, 'arrival_time_hour') is not None
            or db.person.get(person, 'arrival_time_minute') is not None
            or db.person.get(person, 'arrival_flight') is not None
            or db.person.get(person, 'departure_place') is not None
            or db.person.get(person, 'departure_date') is not None
            or db.person.get(person, 'departure_time_hour') is not None
            or db.person.get(person, 'departure_time_minute') is not None
            or db.person.get(person, 'departure_flight') is not None)


def show_travel_copy_options(db, userid, person):
    """Return whether to give options to copy travel details."""
    if person:
        country = db.person.get(person, 'country')
    else:
        if db.security.hasPermission('RegisterAllCountries', userid):
            return False
        country = db.user.get(userid, 'country')
    return db.country.get(country, 'is_normal')


def country_travel_copy_options(db, country, person_to):
    """
    Produce text giving the option to copy travel details from any
    other person from this country with nonempty travel details.
    """
    person_list = people_from_country_internal(db, country)
    person_list = [i for i in person_list
                   if i != person_to and has_nonempty_travel(db, i)]
    travel_list = []
    for person in person_list:
        prop_js_list = []
        text_props = ('arrival_flight', 'departure_flight')
        for prop in text_props:
            val = db.person.get(person, prop)
            if val is None:
                val = ''
            prop_js_list.append('this.form.elements["%s"].value = %s'
                                % (prop, json.dumps(str(val))))
        sel_props = (('arrival_place', '-1'),
                     ('arrival_date', ''),
                     ('arrival_time_hour', ''),
                     ('arrival_time_minute', ''),
                     ('departure_place', '-1'),
                     ('departure_date', ''),
                     ('departure_time_hour', ''),
                     ('departure_time_minute', ''))
        for prop_t in sel_props:
            prop = prop_t[0]
            no_sel_val = prop_t[1]
            val = db.person.get(person, prop)
            if val is None:
                val = no_sel_val
                prop_js_list.append('this.form.elements["%s"].selectedIndex'
                                    ' = -1' % prop)
            prop_js_list.append(
                'for (var i = 0; i < this.form.elements["%s"].length; i++) '
                '{ if (this.form.elements["%s"].options[i].value == "%s") '
                'this.form.elements["%s"].selectedIndex = i; }'
                % (prop, prop, val, prop))
        prop_js = ';'.join(prop_js_list)
        prop_js_esc = html.escape(prop_js)
        prop_js_submit = ('<input type="button"'
                          ' value="Copy travel details from %s %s"'
                          ' onclick="%s">'
                          % (html.escape(db.person.get(person, 'given_name')),
                             html.escape(db.person.get(person, 'family_name')),
                             prop_js_esc))
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


def registration_status(db, nonce):
    """Produce registration status page contents for all countries."""
    sitegen = RoundupSiteGenerator(db)
    consent_forms_date = get_consent_forms_date(db)
    max_photo_size = int(db.config.ext['MATHOLYMP_PHOTO_MAX_SIZE'])
    return sitegen.registration_status_text(consent_forms_date,
                                            have_consent_ui(db),
                                            max_photo_size, nonce)


def registration_status_country(db, country):
    """Produce registration status page contents for one country."""
    if not db.country.get(country, 'is_normal'):
        return '<p>Cannot produce registration status for this user.</p>\n'
    sitegen = RoundupSiteGenerator(db)
    consent_forms_date = get_consent_forms_date(db)
    c = sitegen.event.country_map[int(country)]
    return sitegen.registration_status_country_text(c, consent_forms_date,
                                                    have_consent_ui(db))


def edit_rooms(db):
    """Produce contents of page for viewing and editing room numbers."""
    sitegen = RoundupSiteGenerator(db)
    return sitegen.edit_rooms_text()


def show_consent_form_ui(db, person):
    """Return whether to show the interface to upload a consent form."""
    if not have_consent_forms(db):
        return False
    if db.person.get(person, 'consent_form'):
        # Always show the interface if a form has been uploaded, even
        # if the date of birth shows the form was unnecessary.
        return True
    date_of_birth = person_date_of_birth(db, person)
    if date_of_birth is None:
        return True
    consent_forms_date = get_consent_forms_date(db)
    return date_of_birth >= consent_forms_date


def string_select(name, default_label, entry_list, selected):
    """Return form content for selecting from a list of string choices."""
    option_list = []
    found_sel = False
    for e in entry_list:
        e_value = e[0]
        e_label = e[1]
        sel = ''
        if e_value == selected:
            sel = 'selected="selected" '
            found_sel = True
        option_list.append('<option %svalue="%s">%s</option>'
                           % (sel, html.escape(e_value),
                              html.escape(e_label)))
    if default_label:
        d_sel = ''
        if not found_sel:
            d_sel = 'selected="selected" '
        option_list.insert(0, ('<option %svalue="">%s</option>'
                               % (d_sel, html.escape(default_label))))
    return ('<select id="%s" name="%s">%s</select>'
            % (name, name, '\n'.join(option_list)))


def date_of_birth_select(db, year, month, day):
    """Return form content for selecting a date of birth."""
    earliest_dob = get_earliest_date_of_birth(db)
    sanity_dob = get_sanity_date_of_birth(db)
    latest_dob = sanity_dob - datetime.timedelta(1)
    earliest_year = earliest_dob.year
    latest_year = latest_dob.year
    year_range = range(latest_year, earliest_year - 1, -1)
    year_list = [(str(y), str(y)) for y in year_range]
    year_select = string_select('date_of_birth_year', '(year)', year_list,
                                year)
    month_range = range(1, 13)
    month_list = [('%02d' % m, month_name(m)) for m in month_range]
    month_select = string_select('date_of_birth_month', '(month)', month_list,
                                 month)
    day_range = range(1, 32)
    day_list = [('%02d' % d, str(d)) for d in day_range]
    day_select = string_select('date_of_birth_day', '(day)', day_list, day)
    return '%s\n%s\n%s' % (day_select, month_select, year_select)


def arrdep_date_select(db, kind, date):
    """Return form content for selecting an arrival or departure date."""
    earliest, latest = get_arrdep_bounds(db, kind)
    date_list = []
    d = earliest
    while d <= latest:
        d_iso = date_to_ymd_iso(d)
        d_label = date_to_name(d)
        date_list.append((d_iso, d_label))
        d = d + datetime.timedelta(1)
    return string_select('%s_date' % kind, '(date)', date_list, date)


def arrdep_time_select(db, kind, hour, minute):
    """Return form content for selecting an arrival or departure time."""
    hour_range = range(0, 24)
    hour_list = [('%02d' % h, '%02d' % h) for h in hour_range]
    hour_select = string_select('%s_time_hour' % kind, '(hour)', hour_list,
                                hour)
    minute_range = range(0, 60)
    minute_list = [('%02d' % h, '%02d' % h) for h in minute_range]
    minute_select = string_select('%s_time_minute' % kind, '(minute)',
                                  minute_list, minute)
    return '%s : %s' % (hour_select, minute_select)


def photo_consent_select(selected):
    """Return form content for selecting consent for uploaded photos."""
    return string_select('photo_consent', None,
                         (('not_applicable',
                           'Not applicable, no photo uploaded'),
                          ('yes', 'Yes, for website and name badge'),
                          ('badge_only', 'Yes, for name badge only'),
                          ('no', 'No')), selected)


def score_country_select(db):
    """Return form content for selecting a country for entering scores."""
    countries = db.country.filter(None, {'is_normal': True}, [('+', 'code')])
    country_list = [(c, db.country.get(c, 'name')) for c in countries]
    return string_select('country', None, country_list, None)


def has_consent_for_photo(db, person):
    """
    Return whether there is consent (if needed) to show this person's
    photo on the website.
    """
    if not have_consent_ui(db):
        return True
    return db.person.get(person, 'photo_consent') == 'yes'


def show_incomplete(db, person):
    """
    Return whether to show the interface for editing an incomplete
    registration.
    """
    # Incomplete registrations should only be created through bulk
    # registration.  However, once one has been created, it may be
    # useful for administrative users to make further edits to it
    # while it remains incomplete, before self-registration has been
    # done for that person.
    if person is None:
        return False
    if not db.security.hasPermission('RegisterIncomplete', db.getuid()):
        return False
    return db.person.get(person, 'incomplete')


def required_person_fields(db, person):
    """Return the list of fields required for registered people."""
    incomplete = show_incomplete(db, person)
    req = ['given_name', 'family_name']
    # Accounts that cannot create people but can edit them get forms
    # without editable country or primary_name.
    if db.security.hasPermission('Create', db.getuid(), classname='person'):
        req.append('country')
        req.append('primary_role')
    if not incomplete:
        req.append('gender')
        req.append('language_1')
        req.append('tshirt')
        if require_dob(db):
            req.append('date_of_birth_year')
            req.append('date_of_birth_month')
            req.append('date_of_birth_day')
        if have_consent_ui(db):
            # event_photos_consent and diet_consent not listed here
            # because the JavaScript support for checking required
            # fields are set (taken unmodified from Roundup) does not
            # support radio-button fields (it requires a single
            # <input> with an appropriate id, which must have a
            # value).
            req.append('photo_consent')
        if have_passport_numbers(db):
            req.append('passport_number')
        if have_nationality(db):
            req.append('nationality')
        if require_diet(db):
            req.append('diet')
    return req


def show_prereg_sidebar(db, userid):
    """Return whether to show the preregistration link in the sidebar."""
    # The preregistration link is always for one's own country.
    # Administrative users can edit the data via the general country
    # edit page.
    country = db.user.get(userid, 'country')
    # The data collected in preregistration is mostly only relevant
    # for normal countries (mainly numbers of participants in
    # non-staff roles).
    if not db.country.get(country, 'is_normal'):
        return False
    return db.security.hasPermission('Edit', userid, 'country',
                                     'expected_numbers_confirmed', country)


def show_prereg_reminder(db, userid):
    """Return whether to show the preregistration reminder on all pages."""
    if not show_prereg_sidebar(db, userid):
        return False
    if (not db.security.hasPermission('PreRegisterAnyTime', userid)
        and not db.event.get('1', 'preregistration_enabled')):
        return False
    country = db.user.get(userid, 'country')
    return not db.country.get(country, 'expected_numbers_confirmed')


def bulk_csv_contents(form):
    """Return base64-encoded contents of a previously uploaded CSV file."""
    # In valid uses, csv_file is present as an uploaded file.  To
    # avoid errors to the registration system admin when the template
    # using this function is accessed directly without such an upload,
    # silently return an empty string in such a case.
    if 'csv_file' not in form or not isinstance(form['csv_file'].value, bytes):
        return ''
    return base64.b64encode(form['csv_file'].value).decode('ascii')


def show_bulk_csv_country(db, form):
    """Return HTML text of bulk-country-registration CSV contents."""
    csv_data = bulk_csv_data(form)
    if isinstance(csv_data, str):
        return '<p class="error-message">%s</p>' % html.escape(csv_data)
    file_data = csv_data[0]
    sitegen = RoundupSiteGenerator(db)
    sdata = static_site_event_group(db)
    columns = ['Code', 'Name', 'Previous Participation']
    dist_official = distinguish_official(db)
    if dist_official:
        official_desc = db.config.ext['MATHOLYMP_OFFICIAL_DESC']
        columns.append(official_desc)
    columns.append('Contact Emails')
    head_row_list = [sitegen.html_tr_th_list(columns)]
    body_row_list = []
    for csv_row in file_data:
        out_row = []
        out_row.append(html.escape(csv_row.get('Code', '')))
        out_row.append(html.escape(csv_row.get('Name', '')))
        country_number, generic_url = bulk_csv_country_number_url(db, csv_row)
        country_link = ''
        if country_number is not None:
            if sdata and country_number in sdata.country_map:
                country_link = sitegen.html_a(html.escape(
                    sdata.country_map[country_number].name), generic_url)
            else:
                # Either invalid country number (would normally have
                # been detected by auditor) or no static site data
                # available.
                country_link = str(country_number)
        out_row.append(country_link)
        if dist_official:
            out_row.append(html.escape(csv_row.get(official_desc, '')))
        contact_emails = bulk_csv_contact_emails(csv_row)
        out_row.append(html.escape(', '.join(contact_emails)))
        body_row_list.append(sitegen.html_tr_td_list(out_row))
    return sitegen.html_table_thead_tbody_list(head_row_list, body_row_list)


def show_bulk_csv_country_link_from_code(db, sitegen, code):
    """
    Return HTML text of a link to a country, given its code from
    bulk-person-registration CSV contents.
    """
    countries_with_code = db.country.filter(
        None, {}, exact_match_spec={'code': code})
    if len(countries_with_code) == 1:
        country_id = countries_with_code[0]
        country_name = html.escape(db.country.get(country_id, 'name'))
        return sitegen.link_for_country_at_event(
            sitegen.event.country_map[int(country_id)], country_name)
    else:
        return html.escape(code)


def show_bulk_csv_person(db, form):
    """Return HTML text of bulk-person-registration CSV contents."""
    csv_data = bulk_csv_data(form, ('Other Roles', 'Guide For Codes'))
    if isinstance(csv_data, str):
        return '<p class="error-message">%s</p>' % html.escape(csv_data)
    file_data = csv_data[0]
    sitegen = RoundupSiteGenerator(db)
    sdata = static_site_event_group(db)
    columns = ['Given Name', 'Family Name', 'Country', 'Primary Role',
               'Other Roles', 'Guide For', 'Previous Participation']
    columns.append('Contact Emails')
    head_row_list = [sitegen.html_tr_th_list(columns)]
    body_row_list = []
    for csv_row in file_data:
        out_row = []
        out_row.append(html.escape(csv_row.get('Given Name', '')))
        out_row.append(html.escape(csv_row.get('Family Name', '')))
        country_code = csv_row.get('Country Code', '')
        out_row.append(show_bulk_csv_country_link_from_code(db, sitegen,
                                                            country_code))
        out_row.append(html.escape(csv_row.get('Primary Role', '')))
        out_row.append(html.escape(', '.join(csv_row.get('Other Roles', []))))
        guide_for_codes = csv_row.get('Guide For Codes', [])
        out_row.append(', '.join(show_bulk_csv_country_link_from_code(
            db, sitegen, country_code) for country_code in guide_for_codes))
        person_number, generic_url = bulk_csv_person_number_url(db, csv_row)
        person_link = ''
        if person_number is not None:
            if sdata and person_number in sdata.person_map:
                person_link = sitegen.html_a(html.escape(
                    sdata.person_map[person_number].name), generic_url)
            else:
                # Either invalid person number (would normally have
                # been detected by auditor) or no static site data
                # available.
                person_link = str(person_number)
        out_row.append(person_link)
        contact_emails = bulk_csv_contact_emails(csv_row)
        out_row.append(html.escape(', '.join(contact_emails)))
        body_row_list.append(sitegen.html_tr_td_list(out_row))
    return sitegen.html_table_thead_tbody_list(head_row_list, body_row_list)


def required_user_fields(db):
    """Return the list of fields required for registered users."""
    req = ['address']
    # Accounts that cannot create users but can edit their own user
    # get forms without editable country or username.
    if db.security.hasPermission('Create', db.getuid(), classname='user'):
        req.append('country')
        req.append('username')
    return req


def register_templating_utils(instance):
    """Register functions for use from page templates with Roundup."""
    instance.registerUtil('distinguish_official', distinguish_official)
    instance.registerUtil('have_consent_forms', have_consent_forms)
    instance.registerUtil('have_consent_ui', have_consent_ui)
    instance.registerUtil('have_passport_numbers', have_passport_numbers)
    instance.registerUtil('have_nationality', have_nationality)
    instance.registerUtil('require_diet', require_diet)
    instance.registerUtil('require_dob', require_dob)
    instance.registerUtil('get_language_numbers', get_language_numbers)
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
    instance.registerUtil('edit_rooms', edit_rooms)
    instance.registerUtil('show_consent_form_ui', show_consent_form_ui)
    instance.registerUtil('has_consent_for_photo', has_consent_for_photo)
    instance.registerUtil('date_of_birth_select', date_of_birth_select)
    instance.registerUtil('arrdep_date_select', arrdep_date_select)
    instance.registerUtil('arrdep_time_select', arrdep_time_select)
    instance.registerUtil('photo_consent_select', photo_consent_select)
    instance.registerUtil('score_country_select', score_country_select)
    instance.registerUtil('show_incomplete', show_incomplete)
    instance.registerUtil('required_person_fields', required_person_fields)
    instance.registerUtil('show_prereg_sidebar', show_prereg_sidebar)
    instance.registerUtil('show_prereg_reminder', show_prereg_reminder)
    instance.registerUtil('bulk_csv_contents', bulk_csv_contents)
    instance.registerUtil('bulk_csv_delimiter', bulk_csv_delimiter)
    instance.registerUtil('show_bulk_csv_country', show_bulk_csv_country)
    instance.registerUtil('show_bulk_csv_person', show_bulk_csv_person)
    instance.registerUtil('required_user_fields', required_user_fields)
