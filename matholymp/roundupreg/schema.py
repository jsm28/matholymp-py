# Schema for Roundup registration system for matholymp package.

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

# Parts relating to user and file classes based on schema.py from
# Roundup, to which the following applies:

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

from matholymp.roundupreg.rounduputil import distinguish_official, \
    have_consent_forms, have_passport_numbers, have_nationality, \
    get_none_country

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
    Date = env['Date']
    Link = env['Link']
    Multilink = env['Multilink']
    Boolean = env['Boolean']
    Number = env['Number']
    db = env['db']

    # Create classes:

    # The 'event' class has only one instance, to store global information.
    event = Class(db, 'event',
                  year=String(),
                  registration_enabled=Boolean(),
                  gold=String(),
                  silver=String(),
                  bronze=String())

    if distinguish_official(db):
        country_extra = { 'official': Boolean() }
    else:
        country_extra = {}
    country = Class(db, 'country',
                    code=String(),
                    name=String(),
                    contact_email=String(),
                    generic_url=String(),
                    reuse_flag=Boolean(),
                    files=Link('file'),
                    **country_extra)
    country.setkey('name')
    country.setorderprop('code')

    matholymprole = Class(db, 'matholymprole',
                          name=String(),
                          isadmin=Boolean(),
                          secondaryok=Boolean())
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
                    name=String())
    arrival.setkey('name')

    person_extra = {}
    if have_consent_forms(db):
        person_extra['consent_form'] = Link('private_file')
    if have_passport_numbers(db):
        person_extra['passport_number'] = String()
    if have_nationality(db):
        person_extra['nationality'] = String()
    person=Class(db, 'person',
                 country=Link('country'),
                 given_name=String(),
                 family_name=String(),
                 gender=Link('gender'),
                 date_of_birth=Date(),
                 primary_role=Link('matholymprole'),
                 other_roles=Multilink('matholymprole'),
                 guide_for=Multilink('country'),
                 first_language=Link('language'),
                 second_language=Link('language'),
                 diet=String(),
                 tshirt=Link('tshirt'),
                 arrival_place=Link('arrival'),
                 arrival_time=Date(),
                 arrival_flight=String(),
                 departure_place=Link('arrival'),
                 departure_time=Date(),
                 departure_flight=String(),
                 room_number=String(),
                 phone_number=String(),
                 generic_url=String(),
                 reuse_photo=Boolean(),
                 files=Link('file'),
                 scores=String(), # comma-separated scores on each problem
                 extra_awards=String(),
                 **person_extra
    )
    person.setorderprop('primary_role')

    # The 'rss' class is used internally to store items in the RSS news
    # feeds for scores.
    rss = Class(db, 'rss',
                country=Link('country'),
                text=String())

    user = Class(db, 'user',
                 username=String(),
                 password=Password(),
                 country=Link('country'),
                 address=String(),
                 realname=String(),
                 roles=String()     # comma-separated string of Role names
    )
    user.setkey('username')

    file = FileClass(db, 'file',
                    name=String())

    private_file = FileClass(db, 'private_file',
                             name=String(), country=Link('country'))

    # Set up permissions:

    db.security.addPermission(
        name='Register', klass='user',
        description='User is allowed to register new user')

    db.security.addPermissionToRole('User', 'Web Access')
    db.security.addPermissionToRole('Anonymous', 'Web Access')

    for cl in 'file',:
        db.security.addPermissionToRole('User', 'View', cl)
        db.security.addPermissionToRole('User', 'Create', cl)
    for cl in 'matholymprole', 'gender', 'tshirt', 'language', 'arrival':
        db.security.addPermissionToRole('User', 'View', cl)
    for cl in 'file', 'matholymprole':
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
        properties=('username', 'password', 'address', 'realname'),
        description='User is allowed to edit their own user details')
    db.security.addPermissionToRole('User', p)

    # Users can view any normal or admin country, but not 'None' or
    # retired countries.
    def can_view_country(db, userid, itemid):
        """Determine whether a normal user can view this country."""
        return (itemid != get_none_country(db) and
                not db.country.is_retired(itemid))
    country_public_props = ['code', 'name', 'generic_url', 'files']
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

    # Registering users can view and edit person records if the person is
    # from their own country.  Staff records are expected to be edited by
    # adminstrative users so not all relevant fields are accessible here.
    # All users can view certain person details, but not for retired people.
    db.security.addRole(name='Register', description='Registering people')
    def own_country_person(db, userid, itemid):
        """Determine whether the userid matches the country of the person
        being accessed."""
        return (db.user.get(userid, 'country') ==
                db.person.get(itemid, 'country'))
    p = db.security.addPermission(name='View', klass='person',
                                  check=own_country_person)
    db.security.addPermissionToRole('Register', p)
    person_reg_props = ['country', 'given_name', 'family_name', 'gender',
                        'date_of_birth', 'primary_role', 'first_language',
                        'second_language', 'diet', 'tshirt', 'arrival_place',
                        'arrival_time', 'arrival_flight', 'departure_place',
                        'departure_time', 'departure_flight', 'generic_url',
                        'reuse_photo', 'files']
    if have_consent_forms(db):
        person_reg_props.append('consent_form')
    if have_passport_numbers(db):
        person_reg_props.append('passport_number')
    if have_nationality(db):
        person_reg_props.append('nationality')
    p = db.security.addPermission(name='Edit', klass='person',
                                  check=own_country_person,
                                  properties=person_reg_props)
    db.security.addPermissionToRole('Register', p)
    p = db.security.addPermission(name='Create', klass='person',
                                  properties=person_reg_props)
    db.security.addPermissionToRole('Register', p)
    def normal_can_view_person(db, userid, itemid):
        """Determine whether a normal user can view this person."""
        return not db.person.is_retired(itemid)
    p = db.security.addPermission(name='View', klass='person',
                                  check=normal_can_view_person,
                                  properties=('country', 'given_name',
                                              'family_name', 'primary_role',
                                              'other_roles', 'guide_for',
                                              'files', 'scores',
                                              'extra_awards', 'generic_url'))
    db.security.addPermissionToRole('User', p)
    db.security.addPermissionToRole('Anonymous', p)

    # Registering users can create private files, and view them only
    # when from their own country or created by that user (the latter
    # as a case for access before the country is set).
    db.security.addPermissionToRole('Register', 'Create', 'private_file')
    def own_country_file(db, userid, itemid):
        """Determine whether the userid matches the country of the private
        file being accessed."""
        user_country = db.user.get(userid, 'country')
        file_country = db.private_file.get(itemid, 'country')
        file_creator = db.private_file.get(itemid, 'creator')
        return (user_country == file_country or
                (file_country is None and userid == file_creator))
    p = db.security.addPermission(name='View', klass='private_file',
                                  check=own_country_file)
    db.security.addPermissionToRole('Register', p)

    # Entering scores has its own Permission and Role.
    p = db.security.addPermission(name='Score')
    db.security.addPermissionToRole('Admin', p)
    db.security.addRole(name='Score', description='Entering scores')
    db.security.addPermissionToRole('Score', p)
    # This is needed for the menu of countries to appear for entering
    # scores (but does not actually enable scoring accounts to register
    # new participants).
    p = db.security.addPermission(name='Create', klass='person',
                                  properties=('country',))
    db.security.addPermissionToRole('Score', p)
    # So that scoring users do not see the user interface for
    # registering people:
    p = db.security.addPermission(name='RegisterAllCountries')
    db.security.addPermissionToRole('Admin', p)

    # Online manipulation of participant photos has its own
    # Permission.
    p = db.security.addPermission(name='EditPhotos')
    db.security.addPermissionToRole('Admin', p)

    # Downloading full person data has its own Permission.
    p = db.security.addPermission(name='Omnivident')
    db.security.addPermissionToRole('Admin', p)
