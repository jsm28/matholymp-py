# Initial data setup for Roundup registration system for matholymp package.

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

# Parts relating to user account setup based on initial_data.py from
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

"""This module provides the Roundup initial data setup."""

from matholymp.roundupreg.rounduputil import distinguish_official, \
    get_staff_country_name
from matholymp.roundupreg.staticsite import static_site_event_group

__all__ = ['init_data']


def init_data(env):
    """
    Initialise the Roundup database contents for the registration
    system.  The argument is the environment passed by Roundup when
    executing the instance's initial_data.py.  This is used only when
    the instance is first set up.
    """

    db = env['db']
    adminpw = env['adminpw']
    admin_email = env['admin_email']

    staff_country_name = get_staff_country_name(db)

    # The year, from the configuration file.
    year = db.config.ext['MATHOLYMP_YEAR']

    # Extra roles from the configuration file.
    extra_admin_roles_secondaryok = \
        db.config.ext['MATHOLYMP_EXTRA_ADMIN_ROLES_SECONDARYOK'].split(',')
    extra_admin_roles_secondaryok = [r.strip()
                                     for r in extra_admin_roles_secondaryok]
    extra_admin_roles_secondaryok = [r for r in extra_admin_roles_secondaryok
                                     if r != '']

    # Create a record for this event.
    event = db.getclass('event')
    event.create(year=year,
                 registration_enabled=True,
                 preregistration_enabled=True)

    # Create country records for administration and special-case users.
    country = db.getclass('country')
    country_extra = {'expected_leaders': '0',
                     'expected_deputies': '0',
                     'expected_contestants': '0',
                     'expected_observers_a': '0',
                     'expected_observers_b': '0',
                     'expected_observers_c': '0',
                     'expected_single_rooms': '0',
                     'expected_numbers_confirmed': True}
    if distinguish_official(db):
        country_extra['official'] = False
    staff_country = country.create(code='ZZA', name=staff_country_name,
                                   is_normal=False, participants_ok=True,
                                   **country_extra)
    none_country = country.create(code='ZZN', name='None',
                                  is_normal=False, participants_ok=False,
                                  **country_extra)

    # Create room types.
    room_type_cl = db.getclass('room_type')
    initial_room_types = db.config.ext['MATHOLYMP_INITIAL_'
                                       'ROOM_TYPES'].split(',')
    for room_type in initial_room_types:
        room_type = room_type.strip()
        if room_type != '':
            room_type_cl.create(name=room_type)
    room_types_nc = db.config.ext['MATHOLYMP_INITIAL_'
                                  'ROOM_TYPES_NON_CONTESTANT'].split(',')
    room_types_nc = [t.strip() for t in room_types_nc]
    room_types_nc = [db.room_type.lookup(t) for t in room_types_nc if t != '']
    room_type_nc_def = db.room_type.lookup(
        db.config.ext['MATHOLYMP_INITIAL_DEFAULT_ROOM_TYPE_NON_CONTESTANT'])
    rt_props_nc = {'room_types': room_types_nc,
                   'default_room_type': room_type_nc_def}
    room_types_c = db.config.ext['MATHOLYMP_INITIAL_'
                                 'ROOM_TYPES_CONTESTANT'].split(',')
    room_types_c = [t.strip() for t in room_types_c]
    room_types_c = [db.room_type.lookup(t) for t in room_types_c if t != '']
    room_type_c_def = db.room_type.lookup(
        db.config.ext['MATHOLYMP_INITIAL_DEFAULT_ROOM_TYPE_CONTESTANT'])
    rt_props_c = {'room_types': room_types_c,
                  'default_room_type': room_type_c_def}

    # Create standard roles for olympiad participants.
    props_most_admin = rt_props_nc.copy()
    props_most_admin['isadmin'] = True
    props_most_admin['secondaryok'] = False
    props_most_admin['canguide'] = False
    matholymprole = db.getclass('matholymprole')
    for i in range(int(db.config.ext['MATHOLYMP_NUM_CONTESTANTS_PER_TEAM'])):
        rolename = 'Contestant %d' % (i + 1)
        matholymprole.create(name=rolename, isadmin=False, secondaryok=False,
                             canguide=False, **rt_props_c)
    matholymprole.create(name='Leader', isadmin=False, secondaryok=False,
                         canguide=False, **rt_props_nc)
    matholymprole.create(name='Deputy Leader', isadmin=False,
                         secondaryok=False, canguide=False, **rt_props_nc)
    matholymprole.create(name='Observer with Contestants', isadmin=False,
                         secondaryok=False, canguide=False, **rt_props_nc)
    matholymprole.create(name='Observer with Leader', isadmin=False,
                         secondaryok=False, canguide=False, **rt_props_nc)
    matholymprole.create(name='Observer with Deputy', isadmin=False,
                         secondaryok=False, canguide=False, **rt_props_nc)
    matholymprole.create(name='Staff', **props_most_admin)
    matholymprole.create(name='Jury Chair', **props_most_admin)
    matholymprole.create(name='Chief Coordinator', **props_most_admin)
    matholymprole.create(name='Coordinator', **props_most_admin)
    matholymprole.create(name='Chief Guide', **props_most_admin)
    matholymprole.create(name='Deputy Chief Guide', **props_most_admin)
    matholymprole.create(name='Guide', isadmin=True, secondaryok=False,
                         canguide=True, **rt_props_nc)
    matholymprole.create(name='Treasurer', **props_most_admin)
    matholymprole.create(name='IT', **props_most_admin)
    matholymprole.create(name='Transport', **props_most_admin)
    matholymprole.create(name='Entertainment', **props_most_admin)
    matholymprole.create(name='Logistics', **props_most_admin)
    matholymprole.create(name='Problem Selection Chair', **props_most_admin)
    matholymprole.create(name='Problem Selection', **props_most_admin)
    matholymprole.create(name='Chief Invigilator', **props_most_admin)
    matholymprole.create(name='Invigilator', **props_most_admin)
    matholymprole.create(name='Crew', **props_most_admin)
    matholymprole.create(name='Guest', **props_most_admin)
    matholymprole.create(name='Press', **props_most_admin)
    matholymprole.create(name='VIP', **props_most_admin)
    for r in extra_admin_roles_secondaryok:
        matholymprole.create(name=r, isadmin=True, secondaryok=True,
                             canguide=False, **rt_props_nc)

    # Create three genders.
    gender = db.getclass('gender')
    gender.create(name='Female')
    gender.create(name='Male')
    gender.create(name='Non-binary')

    # Create T-shirt sizes.
    tshirt = db.getclass('tshirt')
    tshirt.create(name='S', order=1)
    tshirt.create(name='M', order=2)
    tshirt.create(name='L', order=3)
    tshirt.create(name='XL', order=4)
    tshirt.create(name='XXL', order=5)
    tshirt.create(name='XXXL', order=6)

    # Create languages previously used.
    initial_languages = db.config.ext['MATHOLYMP_INITIAL_LANGUAGES'].split(',')
    lang_set = set()
    for lang in initial_languages:
        lang = lang.strip()
        if lang == '':
            pass
        elif lang.startswith('-'):
            lang_set.remove(lang[1:])
        elif lang == 'PREVIOUS':
            sdata = static_site_event_group(db)
            if not sdata:
                raise ValueError('PREVIOUS languages specified without'
                                 ' static site data')
            for e in sdata.event_list:
                for p in e.paper_list:
                    lang_set.add(p.language)
        else:
            lang_set.add(lang)
    language = db.getclass('language')
    for lang in sorted(lang_set):
        language.create(name=lang)

    # Arrival/departure points must be created using the web interface.

    # Create the two default users.
    user = db.getclass('user')
    user.create(username='admin', password=adminpw,
                address=admin_email, roles='Admin',
                country=staff_country)
    user.create(username='anonymous', roles='Anonymous',
                country=none_country)
