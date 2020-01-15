# Initial data setup for Roundup registration system for matholymp package.

# Copyright 2014-2020 Joseph Samuel Myers.

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

from matholymp.roundupreg.config import distinguish_official, \
    get_staff_country_name, get_initial_languages, \
    get_extra_admin_roles_secondaryok, get_initial_room_types, \
    get_initial_room_types_non_contestant, get_initial_room_types_contestant
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

    # Extra roles from the configuration file.
    extra_admin_roles_secondaryok = get_extra_admin_roles_secondaryok(db)

    # Create a record for this event.
    event = db.getclass('event')
    event.create(registration_enabled=True,
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
    initial_room_types = get_initial_room_types(db)
    for room_type in initial_room_types:
        room_type_cl.create(name=room_type)
    room_types_nc = get_initial_room_types_non_contestant(db)
    room_types_nc = [db.room_type.lookup(t) for t in room_types_nc]
    room_type_nc_def = db.room_type.lookup(
        db.config.ext['MATHOLYMP_INITIAL_DEFAULT_ROOM_TYPE_NON_CONTESTANT'])
    rt_props_nc = {'room_types': room_types_nc,
                   'default_room_type': room_type_nc_def}
    room_types_c = get_initial_room_types_contestant(db)
    room_types_c = [db.room_type.lookup(t) for t in room_types_c]
    room_type_c_def = db.room_type.lookup(
        db.config.ext['MATHOLYMP_INITIAL_DEFAULT_ROOM_TYPE_CONTESTANT'])
    rt_props_c = {'room_types': room_types_c,
                  'default_room_type': room_type_c_def}

    # Create badge types.
    badge_type = db.getclass('badge_type')
    badge_type_leader = badge_type.create(name='Leader',
                                          background_name='generic',
                                          colour_outer='d22027',
                                          colour_inner='eb9984',
                                          colour_text='000000')
    badge_type_deputy = badge_type.create(name='Deputy Leader',
                                          background_name='generic',
                                          colour_outer='fff200',
                                          colour_inner='fffa99',
                                          colour_text='000000')
    badge_type_contestant = badge_type.create(name='Contestant',
                                              background_name='generic',
                                              colour_outer='7ab558',
                                              colour_inner='c9deb0',
                                              colour_text='000000')
    badge_type_obsa = badge_type.create(name='Observer with Leader',
                                        background_name='generic',
                                        colour_outer='8b0000',
                                        colour_inner='cd5c5c',
                                        colour_text='000000')
    badge_type_obsb = badge_type.create(name='Observer with Deputy',
                                        background_name='generic',
                                        colour_outer='ffd700',
                                        colour_inner='ffef99',
                                        colour_text='000000')
    badge_type_obsc = badge_type.create(name='Observer with Contestants',
                                        background_name='generic',
                                        colour_outer='1d8042',
                                        colour_inner='97c79c',
                                        colour_text='000000')
    badge_type_guide = badge_type.create(name='Guide',
                                         background_name='generic',
                                         colour_outer='2a3e92',
                                         colour_inner='9c95cc',
                                         colour_text='000000')
    badge_type_chiefguide = badge_type.create(name='Chief Guide',
                                              background_name='generic',
                                              colour_outer='2a3e92',
                                              colour_inner='9c95cc',
                                              colour_text='000000')
    badge_type_coordinator = badge_type.create(name='Coordinator',
                                               background_name='generic',
                                               colour_outer='f78b11',
                                               colour_inner='fccc8f',
                                               colour_text='000000')
    badge_type_invigilator = badge_type.create(name='Invigilator',
                                               background_name='generic',
                                               colour_outer='d32395',
                                               colour_inner='eca3d3',
                                               colour_text='000000')
    badge_type_crew = badge_type.create(name='Crew',
                                        background_name='generic',
                                        colour_outer='800080',
                                        colour_inner='dda0dd',
                                        colour_text='000000')
    badge_type_guest = badge_type.create(name='Guest',
                                         background_name='generic',
                                         colour_outer='a9a9a9',
                                         colour_inner='dcdcdc',
                                         colour_text='000000')
    badge_type_organiser = badge_type.create(name='Organiser',
                                             background_name='generic',
                                             colour_outer='231f20',
                                             colour_inner='a7a6a6',
                                             colour_text='000000')

    # Create standard roles for olympiad participants.
    props_most_admin = rt_props_nc.copy()
    props_most_admin['isadmin'] = True
    props_most_admin['secondaryok'] = False
    props_most_admin['canguide'] = False
    matholymprole = db.getclass('matholymprole')
    for i in range(int(db.config.ext['MATHOLYMP_NUM_CONTESTANTS_PER_TEAM'])):
        rolename = 'Contestant %d' % (i + 1)
        matholymprole.create(name=rolename, isadmin=False, secondaryok=False,
                             canguide=False, badge_type=badge_type_contestant,
                             **rt_props_c)
    matholymprole.create(name='Leader', isadmin=False, secondaryok=False,
                         canguide=False, badge_type=badge_type_leader,
                         **rt_props_nc)
    matholymprole.create(name='Deputy Leader', isadmin=False,
                         secondaryok=False, canguide=False,
                         badge_type=badge_type_deputy, **rt_props_nc)
    matholymprole.create(name='Observer with Contestants', isadmin=False,
                         secondaryok=False, canguide=False,
                         badge_type=badge_type_obsc, **rt_props_nc)
    matholymprole.create(name='Observer with Leader', isadmin=False,
                         secondaryok=False, canguide=False,
                         badge_type=badge_type_obsa, **rt_props_nc)
    matholymprole.create(name='Observer with Deputy', isadmin=False,
                         secondaryok=False, canguide=False,
                         badge_type=badge_type_obsb, **rt_props_nc)
    matholymprole.create(name='Staff', badge_type=badge_type_organiser,
                         **props_most_admin)
    matholymprole.create(name='Jury Chair', badge_type=badge_type_organiser,
                         **props_most_admin)
    matholymprole.create(name='Chief Coordinator',
                         badge_type=badge_type_coordinator, **props_most_admin)
    matholymprole.create(name='Coordinator', badge_type=badge_type_coordinator,
                         **props_most_admin)
    matholymprole.create(name='Chief Guide', badge_type=badge_type_chiefguide,
                         **props_most_admin)
    matholymprole.create(name='Deputy Chief Guide',
                         badge_type=badge_type_chiefguide, **props_most_admin)
    matholymprole.create(name='Guide', isadmin=True, secondaryok=False,
                         canguide=True, badge_type=badge_type_guide,
                         **rt_props_nc)
    matholymprole.create(name='Treasurer', badge_type=badge_type_organiser,
                         **props_most_admin)
    matholymprole.create(name='IT', badge_type=badge_type_organiser,
                         **props_most_admin)
    matholymprole.create(name='Transport', badge_type=badge_type_organiser,
                         **props_most_admin)
    matholymprole.create(name='Entertainment', badge_type=badge_type_organiser,
                         **props_most_admin)
    matholymprole.create(name='Logistics', badge_type=badge_type_organiser,
                         **props_most_admin)
    matholymprole.create(name='Problem Selection Chair',
                         badge_type=badge_type_coordinator, **props_most_admin)
    matholymprole.create(name='Problem Selection',
                         badge_type=badge_type_coordinator, **props_most_admin)
    matholymprole.create(name='Chief Invigilator',
                         badge_type=badge_type_invigilator, **props_most_admin)
    matholymprole.create(name='Invigilator', badge_type=badge_type_invigilator,
                         **props_most_admin)
    matholymprole.create(name='Crew', badge_type=badge_type_crew,
                         **props_most_admin)
    matholymprole.create(name='Guest', badge_type=badge_type_guest,
                         **props_most_admin)
    matholymprole.create(name='Press', badge_type=badge_type_organiser,
                         **props_most_admin)
    matholymprole.create(name='VIP', badge_type=badge_type_guest,
                         **props_most_admin)
    for r in extra_admin_roles_secondaryok:
        matholymprole.create(name=r, isadmin=True, secondaryok=True,
                             canguide=False, badge_type=badge_type_organiser,
                             **rt_props_nc)

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
    initial_languages = get_initial_languages(db)
    lang_set = set()
    for lang in initial_languages:
        if lang.startswith('-'):
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
