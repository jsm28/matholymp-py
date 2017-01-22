# Auditors for Roundup registration system for matholymp package.

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

"""This module provides auditors for the Roundup registration system."""

__all__ = ['audit_event_fields', 'audit_country_fields', 'audit_person_fields',
           'register_auditors']

import re

from roundup.date import Date

from matholymp.fileutil import boolean_states
from matholymp.roundupreg.auditorutil import get_new_value, require_value
from matholymp.roundupreg.rounduputil import have_consent_forms, \
    have_passport_numbers, have_nationality, require_dob, get_num_problems, \
    get_marks_per_problem, get_none_country, get_staff_country, \
    any_scores_missing, valid_score, create_rss, db_file_format_contents, \
    db_file_extension, db_private_file_format_contents, \
    db_private_file_extension
from matholymp.roundupreg.staticsite import static_site_event_group, \
    static_site_file_data
from matholymp.roundupreg.userauditor import audit_user_fields

def audit_event_fields(db, cl, nodeid, newvalues):
    """Verify medal boundaries can be set and create RSS item for them."""
    gold = get_new_value(db, cl, nodeid, newvalues, 'gold')
    silver = get_new_value(db, cl, nodeid, newvalues, 'silver')
    bronze = get_new_value(db, cl, nodeid, newvalues, 'bronze')
    if gold or silver or bronze:
        if any_scores_missing(db):
            raise ValueError('Scores not all entered')
        if not gold or not silver or not bronze:
            raise ValueError('Must set all medal boundaries at once')
        marks_per_problem = get_marks_per_problem(db)
        # A gold medal boundary of max + 1 means no gold medals.
        max_medal_boundary = sum(marks_per_problem) + 1
        if not valid_score(gold, max_medal_boundary):
            raise ValueError('Invalid gold medal boundary')
        if not valid_score(silver, max_medal_boundary):
            raise ValueError('Invalid silver medal boundary')
        if not valid_score(bronze, max_medal_boundary):
            raise ValueError('Invalid bronze medal boundary')
        if int(silver) > int(gold) or int(bronze) > int(silver):
            raise ValueError('Medal boundaries in wrong order')
    medal_items = []
    if newvalues.get('gold', None) is not None:
        medal_items.append('Gold ' + gold)
    if newvalues.get('silver', None) is not None:
        medal_items.append('Silver ' + silver)
    if newvalues.get('bronze', None) is not None:
        medal_items.append('Bronze ' + bronze)
    if medal_items:
        medal_text = 'Medal boundaries: ' + ', '.join(medal_items)
        create_rss(db, 'Medal boundaries', medal_text)

def audit_country_fields(db, cl, nodeid, newvalues):
    """Make sure country properties are valid."""
    code = require_value(db, cl, nodeid, newvalues, 'code',
                         'No country code specified')
    if not re.match('^[A-Z]+\\Z', code):
        raise ValueError('Country codes must be all capital letters')
    countries_with_code = db.country.filter(None, {'code': code})
    for c in countries_with_code:
        if c != nodeid:
            raise ValueError('A country with code %s already exists' % code)

    name = require_value(db, cl, nodeid, newvalues, 'name',
                         'No country name specified')
    if nodeid is not None:
        if nodeid == get_staff_country(db) or nodeid == get_none_country(db):
            if name != db.country.get(nodeid, 'name'):
                raise ValueError('Cannot rename special countries')

    if 'files' in newvalues:
        file_id = newvalues['files']
        if file_id is not None:
            format_contents = db_file_format_contents(db, file_id)
            format_ext = db_file_extension(db, file_id)
            if format_contents != 'png':
                raise ValueError('Flags must be in PNG format')
            if format_ext != format_contents:
                raise ValueError('Filename extension for flag must match '
                                 'contents (%s)' % format_contents)

    generic_url = get_new_value(db, cl, nodeid, newvalues, 'generic_url')
    if generic_url is not None and generic_url != '':
        gudesc = db.config.ext['MATHOLYMP_GENERIC_URL_DESC_PLURAL']
        gudesc_sing = db.config.ext['MATHOLYMP_GENERIC_URL_DESC']
        gubase = (db.config.ext['MATHOLYMP_GENERIC_URL_BASE'] +
                  'countries/country')
        guok = False
        if generic_url.startswith(gubase):
            generic_url = generic_url[len(gubase):]
            m = re.match('^([1-9][0-9]*)/\Z', generic_url)
            if m:
                guok = True
                sdata = static_site_event_group(db)
                if sdata:
                    cno = int(m.group(1))
                    if cno not in sdata.country_map:
                        raise ValueError(gudesc_sing + ' for previous'
                                         ' participation not valid')
                    if (get_new_value(db, cl, nodeid, newvalues,
                                      'reuse_flag') and
                        not get_new_value(db, cl, nodeid, newvalues, 'files')):
                        flag_url = sdata.country_map[cno].flag_url
                        flag_data = static_site_file_data(db, flag_url)
                        if flag_data:
                            newvalues['files'] = db.file.create(**flag_data)
        if not guok:
            raise ValueError(gudesc + ' for previous participation must'
                             ' be in the form ' + gubase + 'N/')

def audit_person_fields(db, cl, nodeid, newvalues):
    """Make sure person properties are valid, both individually and
    together with other person entries in the database."""

    userid = db.getuid()
    none_country = get_none_country(db)
    staff_country = get_staff_country(db)

    # A country must be specified and ordinary users cannot create or
    # modify records for other countries.
    country = require_value(db, cl, nodeid, newvalues, 'country',
                            'No country specified')
    user_country = db.user.get(userid, 'country')
    if (user_country != none_country
        and user_country != staff_country
        and user_country != country):
        raise ValueError('Person must be from your country')

    if (user_country != staff_country
        and not db.event.get('1', 'registration_enabled')):
        raise ValueError('Registration is now disabled, please contact'
                         ' the event organisers to change details of'
                         ' registered participants')

    # Given and family names must be specified.
    require_value(db, cl, nodeid, newvalues, 'given_name',
                  'No given name specified')
    require_value(db, cl, nodeid, newvalues, 'family_name',
                  'No family name specified')

    # A gender must be specified.
    gender = require_value(db, cl, nodeid, newvalues, 'gender',
                           'No gender specified')

    # A primary role must be specified.
    primary_role = require_value(db, cl, nodeid, newvalues, 'primary_role',
                                 'No primary role specified')

    # A first language must be specified.
    require_value(db, cl, nodeid, newvalues, 'first_language',
                  'No first language specified')

    # A T-shirt size must be specified.
    require_value(db, cl, nodeid, newvalues, 'tshirt',
                  'No T-shirt size specified')

    if db.matholymprole.get(primary_role, 'name').startswith('Contestant '):
        is_contestant = True
    else:
        is_contestant = False

    # Contestants must have one of the permitted genders.
    if is_contestant:
        req_genders = db.config.ext['MATHOLYMP_CONTESTANT_GENDERS'].split(',')
        req_genders = [g.strip() for g in req_genders]
        req_genders = [g for g in req_genders if g != '']
        if req_genders:
            gender_name = db.gender.get(gender, 'name')
            if gender_name not in req_genders:
                raise ValueError('Contestant gender must be %s' %
                                 (' or '.join(req_genders)))

    # Contestants must have been born on or after the date specified
    # in the regulations.  To avoid problems generating CSV files,
    # dates of birth, if specified for other people, must not be too
    # old for python's strftime.
    dob_required = is_contestant or require_dob(db)
    date_of_birth = get_new_value(db, cl, nodeid, newvalues, 'date_of_birth')
    if dob_required:
        date_of_birth = require_value(db, cl, nodeid, newvalues,
                                      'date_of_birth',
                                      'No date of birth specified')
    if date_of_birth is not None:
        if date_of_birth < Date('1902-01-01'):
            raise ValueError('Participant implausibly old')
        # As a sanity check against users entering e.g. today's date
        # by mistake, require participants to be born before a sanity
        # check date.
        sanity_dob = Date(db.config.ext['MATHOLYMP_SANITY_DATE_OF_BIRTH'])
        if date_of_birth >= sanity_dob:
            raise ValueError('Participant implausibly young')
    if is_contestant:
        earliest_dob = Date(db.config.ext['MATHOLYMP_EARLIEST_DATE_OF_BIRTH'])
        if date_of_birth < earliest_dob:
            raise ValueError('Contestant too old')

    # If passport numbers are collected, they are required.
    if have_passport_numbers(db):
        require_value(db, cl, nodeid, newvalues, 'passport_number',
                      'No passport or identity card number specified')

    # If nationalities are collected, they are required.
    if have_nationality(db):
        require_value(db, cl, nodeid, newvalues, 'nationality',
                      'No nationality specified')

    # Start with blank scores for contestants - and for other people
    # in case someone is first registered with another role then
    # changed to a contestant.
    if nodeid is None:
        num_problems = get_num_problems(db)
        scores_list = ['' for i in range(num_problems)]
        newvalues['scores'] = ','.join(scores_list)

    # Sanity check arrival and departure times.
    arrival_time = newvalues.get('arrival_time', None)
    if arrival_time is not None:
        earliest_arr = Date(db.config.ext['MATHOLYMP_EARLIEST_ARRIVAL_DATE'])
        if arrival_time < earliest_arr:
            raise ValueError('Arrival date too early')
        latest_arr = Date(db.config.ext['MATHOLYMP_LATEST_ARRIVAL_DATE'])
        if arrival_time > latest_arr:
            raise ValueError('Arrival date too late')
    departure_time = newvalues.get('departure_time', None)
    if departure_time is not None:
        earliest_dep = Date(db.config.ext['MATHOLYMP_EARLIEST_DEPARTURE_DATE'])
        if departure_time < earliest_dep:
            raise ValueError('Departure date too early')
        latest_dep = Date(db.config.ext['MATHOLYMP_LATEST_DEPARTURE_DATE'])
        if departure_time > latest_dep:
            raise ValueError('Departure date too late')

    if 'files' in newvalues:
        file_id = newvalues['files']
        if file_id is not None:
            format_contents = db_file_format_contents(db, file_id)
            format_ext = db_file_extension(db, file_id)
            if format_contents not in ('jpg', 'png'):
                raise ValueError('Photos must be in JPEG or PNG format')
            if format_ext != format_contents:
                raise ValueError('Filename extension for photo must match '
                                 'contents (%s)' % format_contents)

    if have_consent_forms(db) and 'consent_form' in newvalues:
        file_id = newvalues['consent_form']
        if file_id is not None:
            format_contents = db_private_file_format_contents(db, file_id)
            format_ext = db_private_file_extension(db, file_id)
            if format_contents != 'pdf':
                raise ValueError('Consent forms must be in PDF format')
            if format_ext != format_contents:
                raise ValueError('Filename extension for consent form must '
                                 'match contents (%s)' % format_contents)
            if user_country != staff_country:
                file_country = db.private_file.get(file_id, 'country')
                if file_country is not None and file_country != user_country:
                    raise ValueError('Consent form from another country')

    generic_url = get_new_value(db, cl, nodeid, newvalues, 'generic_url')
    if generic_url is not None and generic_url != '':
        gudesc = db.config.ext['MATHOLYMP_GENERIC_URL_DESC_PLURAL']
        gudesc_sing = db.config.ext['MATHOLYMP_GENERIC_URL_DESC']
        gubase = (db.config.ext['MATHOLYMP_GENERIC_URL_BASE'] +
                  'people/person')
        guok = False
        if generic_url.startswith(gubase):
            generic_url = generic_url[len(gubase):]
            m = re.match('^([1-9][0-9]*)/\Z', generic_url)
            if m:
                guok = True
                sdata = static_site_event_group(db)
                if sdata:
                    pno = int(m.group(1))
                    if pno not in sdata.person_map:
                        raise ValueError(gudesc_sing + ' for previous'
                                         ' participation not valid')
                    if (get_new_value(db, cl, nodeid, newvalues,
                                      'reuse_photo') and
                        not get_new_value(db, cl, nodeid, newvalues, 'files')):
                        photo_url = sdata.person_map[pno].photo_url
                        photo_data = static_site_file_data(db, photo_url)
                        if photo_data:
                            newvalues['files'] = db.file.create(**photo_data)
        if not guok:
            raise ValueError(gudesc + ' for previous participation'
                             ' must be in the form ' + gubase + 'N/')

    # For a normal country, the primary role must be normal and there
    # must be no secondary roles, other than committee membership.
    # For an administrative country, the roles must all be
    # administrative.
    if country == none_country:
        raise ValueError('Invalid country')

    other_roles = get_new_value(db, cl, nodeid, newvalues, 'other_roles')
    if other_roles is None:
        other_roles = []
    if country == staff_country:
        if not db.matholymprole.get(primary_role, 'isadmin'):
            raise ValueError('Staff must have administrative roles')
        for role in other_roles:
            if not db.matholymprole.get(role, 'isadmin'):
                raise ValueError('Staff must have administrative roles')
    else:
        # Normal participants.
        if db.matholymprole.get(primary_role, 'isadmin'):
            raise ValueError('Invalid role for participant')
        for role in other_roles:
            if not db.matholymprole.get(role, 'secondaryok'):
                raise ValueError('Non-staff may not have secondary roles')

        # Non-observer roles for normal countries are uniquely named:
        # there must be no more than one Leader, Contestant 2 etc.
        primary_role_name = db.matholymprole.get(primary_role, 'name')
        if not primary_role_name.startswith('Observer '):
            people = db.person.filter(None,
                                      {'primary_role': primary_role,
                                       'country': country})
            for person in people:
                if person != nodeid:
                    raise ValueError('A person with this role already exists')

    # guide_for must only be specified for ordinary guides.
    guide_for = get_new_value(db, cl, nodeid, newvalues, 'guide_for')
    if guide_for is None:
        guide_for = []
    guide = db.matholymprole.lookup('Guide')
    for c in guide_for:
        if primary_role != guide:
            raise ValueError('Only normal Guides may guide a country')
        if c == staff_country or c == none_country:
            raise ValueError('May only guide normal countries')

    # Likewise phone_number.
    phone_number = get_new_value(db, cl, nodeid, newvalues, 'phone_number')
    if phone_number is None:
        phone_number = ''
    if phone_number != '':
        if primary_role != guide:
            raise ValueError('Phone numbers may only be entered for'
                             ' normal Guides')

def register_auditors(db):
    """Register the matholymp auditors with Roundup."""
    db.event.audit('set', audit_event_fields)
    db.event.audit('create', audit_event_fields)
    db.country.audit('set', audit_country_fields)
    db.country.audit('create', audit_country_fields)
    db.person.audit('set', audit_person_fields)
    db.person.audit('create', audit_person_fields)
    db.user.audit('set', audit_user_fields)
    db.user.audit('create', audit_user_fields)
