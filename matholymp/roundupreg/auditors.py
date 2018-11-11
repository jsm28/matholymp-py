# Auditors for Roundup registration system for matholymp package.

# Copyright 2014-2018 Joseph Samuel Myers.

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

__all__ = ['audit_event_fields', 'audit_file_format', 'audit_country_fields',
           'audit_person_arrdep', 'audit_person_fields', 'register_auditors']

import re

from matholymp.datetimeutil import date_from_ymd_str, date_from_ymd_iso, \
    time_from_hhmm_str
from matholymp.roundupreg.auditorutil import get_new_value, require_value
from matholymp.roundupreg.rounduputil import have_consent_forms, \
    have_consent_ui, have_passport_numbers, have_nationality, require_diet, \
    require_dob, get_num_problems, get_marks_per_problem, \
    get_earliest_date_of_birth, get_sanity_date_of_birth, \
    get_earliest_date_of_birth_contestant, get_arrdep_bounds, \
    any_scores_missing, valid_score, create_rss, db_file_format_contents, \
    db_file_extension
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


def audit_file_format(db, cls, file_id, desc1, desc2, fmts, fmtdesc):
    """Check for format of an uploaded file."""
    format_contents = db_file_format_contents(db, cls, file_id)
    format_ext = db_file_extension(db, cls, file_id)
    if format_contents not in fmts:
        raise ValueError('%s must be in %s format' % (desc1, fmtdesc))
    if format_ext != format_contents:
        raise ValueError('Filename extension for %s must match '
                         'contents (%s)' % (desc2, format_contents))


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

    require_value(db, cl, nodeid, newvalues, 'name',
                  'No country name specified')
    if nodeid is not None:
        if ('is_normal' in newvalues
            and newvalues['is_normal'] != db.country.get(nodeid, 'is_normal')):
            raise ValueError('Cannot change whether a country is normal')
        if ('participants_ok' in newvalues
            and (newvalues['participants_ok']
                 != db.country.get(nodeid, 'participants_ok'))):
            raise ValueError('Cannot change whether a country '
                             'can have participants')

    if 'flag' in newvalues:
        file_id = newvalues['flag']
        if file_id is not None:
            audit_file_format(db, 'flag', file_id, 'Flags', 'flag',
                              ('png',), 'PNG')

    generic_url = get_new_value(db, cl, nodeid, newvalues, 'generic_url')
    if generic_url is not None and generic_url != '':
        gudesc = db.config.ext['MATHOLYMP_GENERIC_URL_DESC_PLURAL']
        gudesc_sing = db.config.ext['MATHOLYMP_GENERIC_URL_DESC']
        gubase = (db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
                  + 'countries/country')
        guok = False
        if generic_url.startswith(gubase):
            generic_url = generic_url[len(gubase):]
            m = re.match('^([1-9][0-9]*)/\\Z', generic_url)
            if m:
                guok = True
                sdata = static_site_event_group(db)
                if sdata:
                    cno = int(m.group(1))
                    if cno not in sdata.country_map:
                        raise ValueError(gudesc_sing + ' for previous'
                                         ' participation not valid')
                    if (get_new_value(db, cl, nodeid, newvalues, 'reuse_flag')
                        and not get_new_value(db, cl, nodeid, newvalues,
                                              'flag')):
                        flag_url = sdata.country_map[cno].flag_url
                        flag_data = static_site_file_data(db, flag_url)
                        if flag_data:
                            newvalues['flag'] = db.flag.create(**flag_data)
        if not guok:
            raise ValueError(gudesc + ' for previous participation must'
                             ' be in the form ' + gubase + 'N/')


def audit_person_arrdep(db, cl, nodeid, newvalues, kind):
    """
    Check arrival or departure details for a person.  Return the date
    and time specified.
    """
    date = get_new_value(db, cl, nodeid, newvalues, '%s_date' % kind)
    hour = get_new_value(db, cl, nodeid, newvalues, '%s_time_hour' % kind)
    minute = get_new_value(db, cl, nodeid, newvalues, '%s_time_minute' % kind)
    if date is None:
        if hour is not None:
            hour = None
            newvalues['%s_time_hour' % kind] = None
            # On node creation, unset string fields are omitted from
            # newvalues by the form parsing code, and must be omitted
            # in newvalues in the form in which it is passed to the
            # database back end or internal errors will occur.  On
            # node edit, such a field being changed to unset is
            # represented as None by the form parsing code so it is
            # appropriate for the auditor to represent it that way as
            # well.
            if nodeid is None:
                del newvalues['%s_time_hour' % kind]
    else:
        date = date_from_ymd_iso('%s date' % kind, date)
    if hour is None:
        if minute is not None:
            minute = None
            newvalues['%s_time_minute' % kind] = None
            if nodeid is None:
                del newvalues['%s_time_minute' % kind]
        time = None
    else:
        if minute is None:
            # Default minute to 00 if only hour specified.
            minute = '00'
            newvalues['%s_time_minute' % kind] = '00'
        time = time_from_hhmm_str('%s time' % kind, hour, minute)
    if date is not None:
        earliest, latest = get_arrdep_bounds(db, kind)
        if date < earliest:
            raise ValueError('%s date too early' % kind)
        if date > latest:
            raise ValueError('%s date too late' % kind)
    return date, time


def audit_person_fields(db, cl, nodeid, newvalues):
    """Make sure person properties are valid, both individually and
    together with other person entries in the database."""

    userid = db.getuid()

    # A country must be specified and ordinary users cannot create or
    # modify records for other countries.
    country = require_value(db, cl, nodeid, newvalues, 'country',
                            'No country specified')
    user_country = db.user.get(userid, 'country')
    user_country_normal = db.country.get(user_country, 'is_normal')
    if (user_country_normal
        and user_country != country):
        raise ValueError('Person must be from your country')

    if (user_country_normal
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
    require_value(db, cl, nodeid, newvalues, 'language_1',
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
                raise ValueError('Contestant gender must be %s'
                                 % (' or '.join(req_genders)))

    # Contestants must have been born on or after the date specified
    # in the regulations.  To avoid problems generating CSV files,
    # dates of birth, if specified for other people, must not be too
    # old for python's strftime.
    dob_required = is_contestant or require_dob(db)
    dob_year = get_new_value(db, cl, nodeid, newvalues, 'date_of_birth_year')
    dob_month = get_new_value(db, cl, nodeid, newvalues, 'date_of_birth_month')
    dob_day = get_new_value(db, cl, nodeid, newvalues, 'date_of_birth_day')
    if dob_required:
        dob_year = require_value(db, cl, nodeid, newvalues,
                                 'date_of_birth_year',
                                 'No year of birth specified')
        dob_month = require_value(db, cl, nodeid, newvalues,
                                  'date_of_birth_month',
                                  'No month of birth specified')
        dob_day = require_value(db, cl, nodeid, newvalues,
                                'date_of_birth_day',
                                'No day of birth specified')
    # Do not allow partially specified dates of birth.
    if dob_year is None or dob_month is None or dob_day is None:
        if dob_year is not None:
            dob_year = None
            newvalues['date_of_birth_year'] = None
        if dob_month is not None:
            dob_month = None
            newvalues['date_of_birth_month'] = None
        if dob_day is not None:
            dob_day = None
            newvalues['date_of_birth_day'] = None
        date_of_birth = None
    else:
        date_of_birth = date_from_ymd_str('date of birth', dob_year, dob_month,
                                          dob_day)
    if date_of_birth is not None:
        if date_of_birth < get_earliest_date_of_birth(db):
            raise ValueError('Participant implausibly old')
        # As a sanity check against users entering e.g. today's date
        # by mistake, require participants to be born before a sanity
        # check date.
        if date_of_birth >= get_sanity_date_of_birth(db):
            raise ValueError('Participant implausibly young')
    if is_contestant:
        if date_of_birth < get_earliest_date_of_birth_contestant(db):
            raise ValueError('Contestant too old')

    # If consent information is collected, it is required.
    if have_consent_ui(db):
        event_photos_consent = get_new_value(db, cl, nodeid, newvalues,
                                             'event_photos_consent')
        if event_photos_consent is None:
            raise ValueError('No choice of consent for photos specified')
        diet_consent = get_new_value(db, cl, nodeid, newvalues,
                                     'diet_consent')
        if diet_consent is None:
            raise ValueError('No choice of consent for allergies and dietary '
                             'requirements information specified')
        if not diet_consent:
            # Remove any dietary requirements information specified,
            # now or previously.
            newvalues['diet'] = 'Unknown'

    # If passport numbers are collected, they are required.
    if have_passport_numbers(db):
        require_value(db, cl, nodeid, newvalues, 'passport_number',
                      'No passport or identity card number specified')

    # If nationalities are collected, they are required.
    if have_nationality(db):
        require_value(db, cl, nodeid, newvalues, 'nationality',
                      'No nationality specified')

    # Dietary requirements may be required.
    if require_diet(db):
        require_value(db, cl, nodeid, newvalues, 'diet',
                      'Allergies and dietary requirements not specified')

    # Start with blank scores for contestants - and for other people
    # in case someone is first registered with another role then
    # changed to a contestant.
    if nodeid is None:
        num_problems = get_num_problems(db)
        scores_list = ['' for i in range(num_problems)]
        newvalues['scores'] = ','.join(scores_list)

    # Sanity check arrival and departure dates and times.
    arr_date, arr_time = audit_person_arrdep(db, cl, nodeid, newvalues,
                                             'arrival')
    dep_date, dep_time = audit_person_arrdep(db, cl, nodeid, newvalues,
                                             'departure')
    if arr_date is not None and dep_date is not None:
        if dep_date < arr_date:
            raise ValueError('Departure date before arrival date')
        elif dep_date == arr_date:
            if arr_time is not None and dep_time is not None:
                if dep_time < arr_time:
                    raise ValueError('Departure time before arrival time')

    if 'photo' in newvalues:
        file_id = newvalues['photo']
        if file_id is not None:
            audit_file_format(db, 'photo', file_id, 'Photos', 'photo',
                              ('jpg', 'png'), 'JPEG or PNG')
            if user_country_normal:
                file_person = db.photo.get(file_id, 'person')
                if file_person is not None and file_person != nodeid:
                    raise ValueError('Photo from another person')
                if file_person is None:
                    # Ensure a race cannot occur linking to a photo
                    # uploaded by another user before the person
                    # reactor runs to set the person for that photo.
                    file_creator = db.photo.get(file_id, 'creator')
                    if file_creator != userid:
                        raise ValueError('Photo from another user')

    if have_consent_forms(db) and 'consent_form' in newvalues:
        file_id = newvalues['consent_form']
        if file_id is not None:
            audit_file_format(db, 'consent_form', file_id, 'Consent forms',
                              'consent form', ('pdf',), 'PDF')
            if user_country_normal:
                file_person = db.consent_form.get(file_id, 'person')
                if file_person is not None and file_person != nodeid:
                    raise ValueError('Consent form from another person')
                if file_person is None:
                    # Ensure a race cannot occur linking to a consent
                    # form uploaded by another user before the person
                    # reactor runs to set the person for that consent
                    # form.
                    file_creator = db.consent_form.get(file_id, 'creator')
                    if file_creator != userid:
                        raise ValueError('Consent form from another user')

    generic_url = get_new_value(db, cl, nodeid, newvalues, 'generic_url')
    if generic_url is not None and generic_url != '':
        gudesc = db.config.ext['MATHOLYMP_GENERIC_URL_DESC_PLURAL']
        gudesc_sing = db.config.ext['MATHOLYMP_GENERIC_URL_DESC']
        gubase = (db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
                  + 'people/person')
        guok = False
        if generic_url.startswith(gubase):
            generic_url = generic_url[len(gubase):]
            m = re.match('^([1-9][0-9]*)/\\Z', generic_url)
            if m:
                guok = True
                sdata = static_site_event_group(db)
                if sdata:
                    pno = int(m.group(1))
                    if pno not in sdata.person_map:
                        raise ValueError(gudesc_sing + ' for previous'
                                         ' participation not valid')
                    if (get_new_value(db, cl, nodeid, newvalues, 'reuse_photo')
                        and not get_new_value(db, cl, nodeid, newvalues,
                                              'photo')):
                        photo_url = sdata.person_map[pno].photo_url
                        photo_data = static_site_file_data(db, photo_url)
                        if photo_data:
                            newvalues['photo'] = db.photo.create(**photo_data)
        if not guok:
            raise ValueError(gudesc + ' for previous participation'
                             ' must be in the form ' + gubase + 'N/')

    # For a normal country, the primary role must be normal and there
    # must be no secondary roles, other than committee membership.
    # For an administrative country, the roles must all be
    # administrative.
    if not db.country.get(country, 'participants_ok'):
        raise ValueError('Invalid country')

    other_roles = get_new_value(db, cl, nodeid, newvalues, 'other_roles')
    if other_roles is None:
        other_roles = []
    is_normal = db.country.get(country, 'is_normal')
    if not is_normal:
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
    can_guide = db.matholymprole.get(primary_role, 'canguide')
    for c in guide_for:
        if not can_guide:
            raise ValueError('People with this role may not guide a country')
        if not db.country.get(c, 'is_normal'):
            raise ValueError('May only guide normal countries')

    # Phone numbers may only be specified for staff.
    phone_number = get_new_value(db, cl, nodeid, newvalues, 'phone_number')
    if phone_number is None:
        phone_number = ''
    if phone_number != '' and is_normal:
        raise ValueError('Phone numbers may only be entered for staff')


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
