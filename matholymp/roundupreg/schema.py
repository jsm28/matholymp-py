# Schema for Roundup registration system for matholymp package.

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

# Parts relating to the user class based on schema.py from Roundup, to
# which the following applies:

# Copyright (c) 2003-2009 Richard Jones (richard@mechanicalcat.net)
# Copyright (c) 2002 eKit.com Inc (http://www.ekit.com/)
# Copyright (c) 2001 Bizar Software Pty Ltd (http://www.bizarsoftware.com.au/)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""This module provides the Roundup registration schema."""

from matholymp.roundupreg.config import distinguish_official, \
    have_consent_forms, have_consent_ui, have_passport_numbers, \
    have_nationality, get_language_numbers, invitation_letter_register, \
    is_virtual_event, have_remote_participation, allow_hybrid_countries, \
    get_sars_cov2_cert_bool, get_sars_cov2_doses_bool, \
    get_sars_cov2_after_bool, have_vaccine_status

__all__ = ['init_schema']


def init_schema(env):
    """
    Initialise the Roundup schema for the registration system.  The
    argument is the environment passed by Roundup when executing the
    instance's schema.py.
    """

    Class = env['Class']
    FileClass = env['FileClass']
    String = env['String']
    Password = env['Password']
    Link = env['Link']
    Multilink = env['Multilink']
    Boolean = env['Boolean']
    Number = env['Number']
    db = env['db']

    # Create classes:

    # The 'event' class has only one instance, to store global information.
    event_extra = {}
    if is_virtual_event(db):
        event_extra['self_scoring_enabled'] = Boolean()
    Class(db, 'event',
          registration_enabled=Boolean(),
          preregistration_enabled=Boolean(),
          gold=String(),
          silver=String(),
          bronze=String(),
          **event_extra)

    country_extra = {}
    if distinguish_official(db):
        country_extra['official'] = Boolean()
    if have_remote_participation(db):
        # participation_type is only relevant for hybrid events, but
        # include in the schema for virtual events as well, given the
        # possibility of a hybrid event turning into a virtual one.
        country_extra['participation_type'] = String()
        country_extra['leader_email'] = String()
        country_extra['physical_address'] = String()
    country = Class(db, 'country',
                    code=String(),
                    name=String(),
                    contact_email=String(),
                    contact_extra=String(),
                    generic_url=String(),
                    reuse_flag=Boolean(),
                    flag=Link('flag'),
                    is_normal=Boolean(),
                    participants_ok=Boolean(),
                    expected_leaders=String(),
                    expected_deputies=String(),
                    expected_contestants=String(),
                    expected_observers_a=String(),
                    expected_observers_b=String(),
                    expected_observers_c=String(),
                    expected_single_rooms=String(),
                    expected_numbers_confirmed=Boolean(),
                    **country_extra)
    country.setkey('name')
    country.setorderprop('code')

    room_type = Class(db, 'room_type',
                      name=String())
    room_type.setkey('name')

    badge_type = Class(db, 'badge_type',
                       name=String(),
                       background_name=String(),
                       colour_outer=String(),
                       colour_inner=String(),
                       colour_text=String())
    badge_type.setkey('name')

    matholymprole = Class(db, 'matholymprole',
                          name=String(),
                          isadmin=Boolean(),
                          secondaryok=Boolean(),
                          canguide=Boolean(),
                          room_types=Multilink('room_type'),
                          default_room_type=Link('room_type'),
                          badge_type=Link('badge_type'))
    matholymprole.setkey('name')

    gender = Class(db, 'gender',
                   name=String())
    gender.setkey('name')

    tshirt = Class(db, 'tshirt',
                   name=String(),
                   order=Number())
    tshirt.setkey('name')
    tshirt.setorderprop('order')

    language = Class(db, 'language',
                     name=String())
    language.setkey('name')

    arrival = Class(db, 'arrival',
                    name=String(),
                    isairport=Boolean())
    arrival.setkey('name')

    person_extra = {}
    if have_consent_forms(db):
        person_extra['consent_form'] = Link('consent_form')
    if have_consent_ui(db):
        person_extra['event_photos_consent'] = Boolean()
        # not_applicable, no, badge_only, yes.
        person_extra['photo_consent'] = String()
        person_extra['diet_consent'] = Boolean()
        if have_vaccine_status(db):
            person_extra['vaccine_consent'] = Boolean()
    if have_passport_numbers(db):
        person_extra['passport_number'] = String()
    if have_nationality(db):
        person_extra['nationality'] = String()
    if have_passport_numbers(db) and have_nationality(db):
        person_extra['passport_given_name'] = String()
        person_extra['passport_family_name'] = String()
    if have_remote_participation(db):
        # participation_type is only relevant for hybrid events, but
        # include in the schema for virtual events as well, given the
        # possibility of a hybrid event turning into a virtual one.
        person_extra['participation_type'] = String()
    if get_sars_cov2_cert_bool(db):
        # yes, no, or empty string if unknown.
        person_extra['sars_cov2_cert'] = String()
    if get_sars_cov2_doses_bool(db):
        # Free text, but typically a number.
        person_extra['sars_cov2_doses'] = String()
    if get_sars_cov2_after_bool(db):
        # yes, no, or empty string if unknown.
        person_extra['sars_cov2_after'] = String()
    for i in get_language_numbers(db):
        person_extra['language_%d' % i] = Link('language')
    person = Class(db, 'person',
                   country=Link('country'),
                   given_name=String(),
                   family_name=String(),
                   gender=Link('gender'),
                   date_of_birth_year=String(),
                   date_of_birth_month=String(),
                   date_of_birth_day=String(),
                   primary_role=Link('matholymprole'),
                   other_roles=Multilink('matholymprole'),
                   guide_for=Multilink('country'),
                   diet=String(),
                   tshirt=Link('tshirt'),
                   arrival_place=Link('arrival'),
                   arrival_date=String(),
                   arrival_time_hour=String(),
                   arrival_time_minute=String(),
                   arrival_flight=String(),
                   departure_place=Link('arrival'),
                   departure_date=String(),
                   departure_time_hour=String(),
                   departure_time_minute=String(),
                   departure_flight=String(),
                   room_type=Link('room_type'),
                   room_share_with=String(),
                   room_number=String(),
                   phone_number=String(),
                   generic_url=String(),
                   reuse_photo=Boolean(),
                   photo=Link('photo'),
                   incomplete=Boolean(),
                   invitation_letter_generated=Boolean(),
                   # Comma-separated scores on each problem.
                   scores=String(),
                   extra_awards=String(),
                   **person_extra)
    person.setorderprop('primary_role')

    # The 'rss' class is used internally to store items in the RSS news
    # feeds for scores.
    Class(db, 'rss',
          country=Link('country'),
          text=String())

    user = Class(db, 'user',
                 username=String(),
                 password=Password(),
                 country=Link('country'),
                 person=Link('person'),
                 address=String(),
                 realname=String(),
                 # Comma-separated string of Role names.
                 roles=String())
    user.setkey('username')

    FileClass(db, 'flag',
              content=String(indexme='no'),
              name=String(), country=Link('country'))

    FileClass(db, 'photo',
              content=String(indexme='no'),
              name=String(), person=Link('person'))

    FileClass(db, 'consent_form',
              content=String(indexme='no'),
              name=String(), person=Link('person'))

    # Set up permissions:

    db.security.addPermission(
        name='Register', klass='user',
        description='User is allowed to register new user')

    db.security.addPermissionToRole('User', 'Web Access')
    db.security.addPermissionToRole('Anonymous', 'Web Access')

    for cl in ('matholymprole',):
        db.security.addPermissionToRole('User', 'View', cl)
        db.security.addPermissionToRole('Anonymous', 'View', cl)

    # Users should be able to edit their own details; this permission
    # is limited to only the situation where the Viewed or Edited item
    # is their own.
    def own_record(db, userid, itemid):
        """Determine whether the userid matches the item being accessed."""
        return userid == itemid
    p = db.security.addPermission(
        name='View', klass='user', check=own_record,
        description='User is allowed to view their own user details')
    db.security.addPermissionToRole('User', p)
    p = db.security.addPermission(
        name='Edit', klass='user', check=own_record,
        properties=('password', 'address', 'realname'),
        description='User is allowed to edit their own user details')
    db.security.addPermissionToRole('User', p)

    # Users can view any normal or admin country, but not 'None' or
    # retired countries.
    def can_view_country(db, userid, itemid):
        """Determine whether a normal user can view this country."""
        return (db.country.get(itemid, 'participants_ok')
                and not db.country.is_retired(itemid))
    country_public_props = ['code', 'name', 'generic_url', 'flag',
                            'is_normal']
    if distinguish_official(db):
        country_public_props.append('official')
    p = db.security.addPermission(
        name='View', klass='country',
        check=can_view_country,
        properties=country_public_props,
        description='User is allowed to view most country details')
    db.security.addPermissionToRole('User', p)
    db.security.addPermissionToRole('Anonymous', p)
    p = db.security.addPermission(
        name='Search', klass='country', properties=country_public_props,
        description='User is allowed to search country details')
    db.security.addPermissionToRole('User', p)
    db.security.addPermissionToRole('Anonymous', p)

    # Only current flags are public.
    def can_view_flag(db, userid, itemid):
        """Determine whether a normal user can view this flag."""
        flag_country = db.flag.get(itemid, 'country')
        if flag_country is None:
            return False
        if not can_view_country(db, userid, flag_country):
            return False
        country_flag = db.country.get(flag_country, 'flag')
        return country_flag == itemid

    p = db.security.addPermission(name='View', klass='flag',
                                  check=can_view_flag)
    db.security.addPermissionToRole('User', p)
    db.security.addPermissionToRole('Anonymous', p)

    # Registering users can view, edit and create person records if
    # the person is from their own country.  Staff records are
    # expected to be edited by adminstrative users so not all relevant
    # fields are accessible here.  All users can view certain person
    # details, but not for retired people.
    db.security.addRole(name='Register', description='Registering people')

    # Self-registering users can view and edit their own person record
    # (which must be from their own country), but cannot create person
    # records and have no special privileges regarding records of
    # other people.
    db.security.addRole(name='SelfRegister', description='Registering self')

    for cl in ('gender', 'tshirt', 'language', 'arrival', 'room_type'):
        db.security.addPermissionToRole('Register', 'View', cl)
        db.security.addPermissionToRole('SelfRegister', 'View', cl)

    def own_country_person(db, userid, itemid):
        """Determine whether the userid matches the country of the person
        being accessed."""
        return (db.user.get(userid, 'country')
                == db.person.get(itemid, 'country'))

    def own_person(db, userid, itemid):
        """Determine whether the userid matches the person being accessed."""
        return db.user.get(userid, 'person') == itemid

    p = db.security.addPermission(name='View', klass='person',
                                  check=own_country_person)
    db.security.addPermissionToRole('Register', p)
    p = db.security.addPermission(name='View', klass='person',
                                  check=own_person)
    db.security.addPermissionToRole('SelfRegister', p)
    person_common_reg_props = ['given_name', 'family_name', 'gender',
                               'date_of_birth_year', 'date_of_birth_month',
                               'date_of_birth_day',
                               'diet', 'tshirt', 'arrival_place',
                               'arrival_date', 'arrival_time_hour',
                               'arrival_time_minute', 'arrival_flight',
                               'departure_place', 'departure_date',
                               'departure_time_hour', 'departure_time_minute',
                               'departure_flight', 'room_type',
                               'room_share_with', 'generic_url', 'reuse_photo',
                               'photo', 'incomplete']
    if have_consent_forms(db):
        person_common_reg_props.append('consent_form')
    if have_consent_ui(db):
        person_common_reg_props.append('event_photos_consent')
        person_common_reg_props.append('photo_consent')
        person_common_reg_props.append('diet_consent')
        if have_vaccine_status(db):
            person_common_reg_props.append('vaccine_consent')
    if have_passport_numbers(db):
        person_common_reg_props.append('passport_number')
    if have_nationality(db):
        person_common_reg_props.append('nationality')
    if have_passport_numbers(db) and have_nationality(db):
        person_common_reg_props.append('passport_given_name')
        person_common_reg_props.append('passport_family_name')
    if have_remote_participation(db):
        person_common_reg_props.append('participation_type')
    if get_sars_cov2_cert_bool(db):
        person_common_reg_props.append('sars_cov2_cert')
    if get_sars_cov2_doses_bool(db):
        person_common_reg_props.append('sars_cov2_doses')
    if get_sars_cov2_after_bool(db):
        person_common_reg_props.append('sars_cov2_after')
    for i in get_language_numbers(db):
        person_common_reg_props.append('language_%d' % i)
    person_reg_props = person_common_reg_props.copy()
    person_reg_props.append('country')
    person_reg_props.append('primary_role')
    person_selfreg_props = person_common_reg_props.copy()
    person_selfreg_props.append('phone_number')
    p = db.security.addPermission(name='Edit', klass='person',
                                  check=own_country_person,
                                  properties=person_reg_props)
    db.security.addPermissionToRole('Register', p)
    p = db.security.addPermission(name='Edit', klass='person',
                                  check=own_person,
                                  properties=person_selfreg_props)
    db.security.addPermissionToRole('SelfRegister', p)
    p = db.security.addPermission(name='Create', klass='person',
                                  properties=person_reg_props)
    db.security.addPermissionToRole('Register', p)

    def normal_can_view_person(db, userid, itemid):
        """Determine whether a normal user can view this person."""
        return not db.person.is_retired(itemid)

    # Only current photos are public.
    def normal_can_view_photo(db, userid, itemid):
        """Determine whether a normal user can view this photo."""
        photo_person = db.photo.get(itemid, 'person')
        if photo_person is None:
            return False
        if not normal_can_view_person(db, userid, photo_person):
            return False
        if have_consent_ui(db):
            if db.person.get(photo_person, 'photo_consent') != 'yes':
                return False
        person_photo = db.person.get(photo_person, 'photo')
        return person_photo == itemid

    p = db.security.addPermission(name='View', klass='person',
                                  check=normal_can_view_person,
                                  properties=('country', 'given_name',
                                              'family_name', 'primary_role',
                                              'other_roles', 'guide_for',
                                              'photo', 'scores',
                                              'extra_awards', 'generic_url'))
    db.security.addPermissionToRole('User', p)
    db.security.addPermissionToRole('Anonymous', p)
    p = db.security.addPermission(name='View', klass='photo',
                                  check=normal_can_view_photo)
    db.security.addPermissionToRole('User', p)
    db.security.addPermissionToRole('Anonymous', p)

    # Registering users can create photos, and can view the photos
    # they just uploaded and ones for people from their country (even
    # the old ones).
    db.security.addPermissionToRole('Register', 'Create', 'photo')
    # Self-registering users can create and see their own photos.
    db.security.addPermissionToRole('SelfRegister', 'Create', 'photo')

    def own_country_photo(db, userid, itemid):
        """Determine whether the userid matches the country of the photo being
        accessed."""
        user_country = db.user.get(userid, 'country')
        file_person = db.photo.get(itemid, 'person')
        file_country = None
        if file_person:
            file_country = db.person.get(file_person, 'country')
        file_creator = db.photo.get(itemid, 'creator')
        return (user_country == file_country
                or (file_country is None and userid == file_creator))

    def own_person_photo(db, userid, itemid):
        """Determine whether the userid matches the person of the photo being
        accessed."""
        user_person = db.user.get(userid, 'person')
        file_person = db.photo.get(itemid, 'person')
        file_creator = db.photo.get(itemid, 'creator')
        return (user_person == file_person
                or (file_person is None and userid == file_creator))

    p = db.security.addPermission(name='View', klass='photo',
                                  check=own_country_photo)
    db.security.addPermissionToRole('Register', p)
    p = db.security.addPermission(name='View', klass='photo',
                                  check=own_person_photo)
    db.security.addPermissionToRole('SelfRegister', p)

    # Registering users can create consent forms, and view them only
    # when from their own country or created by that user (the latter
    # as a case for access before the person is set).
    db.security.addPermissionToRole('Register', 'Create', 'consent_form')
    # Self-registering users can create and see their own consent
    # forms.
    db.security.addPermissionToRole('SelfRegister', 'Create', 'consent_form')

    def own_country_consent_form(db, userid, itemid):
        """Determine whether the userid matches the country of the consent
        form being accessed."""
        user_country = db.user.get(userid, 'country')
        file_person = db.consent_form.get(itemid, 'person')
        file_country = None
        if file_person:
            file_country = db.person.get(file_person, 'country')
        file_creator = db.consent_form.get(itemid, 'creator')
        return (user_country == file_country
                or (file_country is None and userid == file_creator))

    def own_person_consent_form(db, userid, itemid):
        """Determine whether the userid matches the person of the consent
        form being accessed."""
        user_person = db.user.get(userid, 'person')
        file_person = db.consent_form.get(itemid, 'person')
        file_creator = db.consent_form.get(itemid, 'creator')
        return (user_person == file_person
                or (file_person is None and userid == file_creator))

    p = db.security.addPermission(name='View', klass='consent_form',
                                  check=own_country_consent_form)
    db.security.addPermissionToRole('Register', p)
    p = db.security.addPermission(name='View', klass='consent_form',
                                  check=own_person_consent_form)
    db.security.addPermissionToRole('SelfRegister', p)

    def own_country(db, userid, itemid):
        """Determine whether the userid matches the country being accessed."""
        return db.user.get(userid, 'country') == itemid

    # Registering users can view and edit the preregistration data for
    # their own country.
    prereg_props = ['expected_leaders', 'expected_deputies',
                    'expected_contestants', 'expected_observers_a',
                    'expected_observers_b', 'expected_observers_c',
                    'expected_single_rooms', 'expected_numbers_confirmed']
    if have_remote_participation(db):
        prereg_props.append('participation_type')
        prereg_props.append('leader_email')
        prereg_props.append('physical_address')
    p = db.security.addPermission(name='View', klass='country',
                                  check=own_country, properties=prereg_props)
    db.security.addPermissionToRole('Register', p)
    p = db.security.addPermission(name='Edit', klass='country',
                                  check=own_country, properties=prereg_props)
    db.security.addPermissionToRole('Register', p)

    # Entering scores has its own Permission and Role.  For the menu
    # of countries for entering scores, there is a separate Permission
    # for whether all countries are shown in that list rather than
    # just the user's own country.  A third Permission is used to
    # check if scores can be entered for a given country.
    p = db.security.addPermission(name='Score')
    p2 = db.security.addPermission(name='ScoreAllCountries')
    p3 = db.security.addPermission(name='ScoreForCountry')
    db.security.addPermissionToRole('Admin', p)
    db.security.addPermissionToRole('Admin', p2)
    db.security.addPermissionToRole('Admin', p3)
    db.security.addRole(name='Score', description='Entering scores')
    db.security.addPermissionToRole('Score', p)
    db.security.addPermissionToRole('Score', p2)
    db.security.addPermissionToRole('Score', p3)

    def reg_can_enter_scores(db, userid, itemid):
        """Determine whether the registering user can enter scores."""
        return (db.event.get('1', 'self_scoring_enabled')
                and own_country(db, userid, itemid))

    if is_virtual_event(db):
        p = db.security.addPermission(name='Score')
        p2 = db.security.addPermission(name='ScoreForCountry', klass='country',
                                       check=reg_can_enter_scores)
        db.security.addPermissionToRole('Register', p)
        db.security.addPermissionToRole('Register', p2)

    # Permission for registering people from all countries, as opposed
    # to only from one's own country.
    p = db.security.addPermission(name='RegisterAllCountries')
    db.security.addPermissionToRole('Admin', p)

    # Permission for registering people and changing registration
    # details when registration is otherwise closed.
    p = db.security.addPermission(name='RegisterAnyTime')
    db.security.addPermissionToRole('Admin', p)

    # Likewise, for preregistration data.
    p = db.security.addPermission(name='PreRegisterAnyTime')
    db.security.addPermissionToRole('Admin', p)

    # Online manipulation of participant photos has its own
    # Permission.
    p = db.security.addPermission(name='EditPhotos')
    db.security.addPermissionToRole('Admin', p)

    # Permission for registering people with all roles (both primary
    # and other roles) rather than just non-administrative roles.
    # This is only used to control the menu of roles shown for
    # registering or editing a person, and the menu of countries for
    # guide_for since being able to register all roles implies being
    # able to register guides, not otherwise to check whether a given
    # edit is permitted.
    p = db.security.addPermission(name='RegisterAllRoles')
    db.security.addPermissionToRole('Admin', p)

    # Permission to edit phone numbers in at least some cases.  This
    # is only used to control whether the interface is shown to edit
    # phone numbers, not for actual checks of whether a given edit is
    # permitted.
    p = db.security.addPermission(name='RegisterPhone')
    db.security.addPermissionToRole('Admin', p)
    db.security.addPermissionToRole('SelfRegister', p)

    # Permission to register room types not otherwise allowed (e.g.,
    # to request a single room for a contestant if that is not
    # normally permitted).
    p = db.security.addPermission(name='RegisterAnyRoomType')
    db.security.addPermissionToRole('Admin', p)

    # Permission to register someone or edit their registration
    # without providing all the normally required data.
    p = db.security.addPermission(name='RegisterIncomplete')
    db.security.addPermissionToRole('Admin', p)

    # Permission to generate name badges online.
    p = db.security.addPermission(name='GenerateNameBadges')
    db.security.addPermissionToRole('Admin', p)

    # Permission to generate invitation letters online.
    p = db.security.addPermission(name='GenerateInvitationLetters')
    db.security.addPermissionToRole('Admin', p)
    p = db.security.addPermission(name='GenerateInvitationLettersZip')
    db.security.addPermissionToRole('Admin', p)

    if invitation_letter_register(db):
        p = db.security.addPermission(name='GenerateInvitationLetters',
                                      klass='person', check=own_country_person)
        db.security.addPermissionToRole('Register', p)

    # Permission to edit countries in general, rather than just a
    # limited subset of properties.  This is only used to control
    # whether the interface is shown to edit various fields, not for
    # actual checks of whether a given edit is permitted.
    p = db.security.addPermission(name='EditCountry')
    db.security.addPermissionToRole('Admin', p)

    # Permission to register countries by bulk CSV upload.
    p = db.security.addPermission(name='BulkRegisterCountry')
    db.security.addPermissionToRole('Admin', p)

    # Permission to register participants by bulk CSV upload.
    p = db.security.addPermission(name='BulkRegisterPerson')
    db.security.addPermissionToRole('Admin', p)

    # Viewing registration status pages (whether for everyone, or just
    # for one's own country) has its own permission.
    p = db.security.addPermission(name='RegistrationStatus')
    db.security.addPermissionToRole('Admin', p)
    db.security.addPermissionToRole('Register', p)

    # Viewing and editing the global set of room allocations has its
    # own permission.
    p = db.security.addPermission(name='EditRooms')
    db.security.addPermissionToRole('Admin', p)

    # Permission to register an individual country for hybrid
    # participation.
    p = db.security.addPermission(name='RegisterHybridCountry')
    db.security.addPermissionToRole('Admin', p)
    if allow_hybrid_countries(db):
        db.security.addPermissionToRole('Register', p)

    # Downloading full person data has its own Permission.
    p = db.security.addPermission(name='Omnivident')
    db.security.addPermissionToRole('Admin', p)
