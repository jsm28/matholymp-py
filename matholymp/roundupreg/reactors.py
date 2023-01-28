# Reactors for Roundup registration system for matholymp package.

# Copyright 2014-2023 Joseph Samuel Myers.

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

"""This module provides reactors for the Roundup registration system."""

__all__ = ['country_react', 'person_react', 'scoreboard_react',
           'register_reactors']

import os.path

import roundup.password

from matholymp.fileutil import read_text_from_file
from matholymp.roundupreg.cache import invalidate_cache
from matholymp.roundupreg.config import have_consent_forms, have_id_scans, get_short_name_year
from matholymp.roundupreg.roundupemail import send_email


def country_react(db, cl, nodeid, oldvalues):
    """
    Mark the cached scoreboard invalid, and create an account for a
    country if required, and set the country for the flag if required.
    """
    scoreboard_react(db, cl, nodeid, oldvalues)
    if db.country.is_retired(nodeid):
        return
    flag_id = db.country.get(nodeid, 'flag')
    if flag_id:
        flag_country = db.flag.get(flag_id, 'country')
        if nodeid != flag_country:
            db.flag.set(flag_id, country=nodeid)
    email_addr = db.country.get(nodeid, 'contact_email')
    if not email_addr:
        return
    email_extra = db.country.get(nodeid, 'contact_extra')
    if email_extra:
        email_extra = [val.strip()
                       for val in email_extra.split('\n')]
        email_extra = [val for val in email_extra if val]
    else:
        email_extra = []
    country_code = db.country.get(nodeid, 'code')
    username = country_code + '_reg'
    if db.user.stringFind(username=username):
        return
    country_name = db.country.get(nodeid, 'name')
    realname = country_name + ' registration'
    if db.user.stringFind(realname=realname):
        return
    pw = roundup.password.generatePassword()
    db.user.create(username=username, realname=realname,
                   password=roundup.password.Password(pw),
                   address=email_addr, country=nodeid,
                   roles='User,Register')
    template_path = os.path.join(db.config.TRACKER_HOME, 'extensions',
                                 'email-template-new-user')
    template_text = read_text_from_file(template_path)
    email_text = template_text % {'country': country_name,
                                  'username': username,
                                  'password': pw}
    short_name_year = get_short_name_year(db)
    subject = '%s registration (%s)' % (short_name_year, country_name)
    send_email(db, [email_addr] + email_extra, subject, email_text,
               country_code)


def person_react(db, cl, nodeid, oldvalues):
    """
    Mark the cached scoreboard invalid, and set the person for a
    person's photo, ID scan and consent form if required.
    """
    scoreboard_react(db, cl, nodeid, oldvalues)
    if db.person.is_retired(nodeid):
        return
    photo_id = db.person.get(nodeid, 'photo')
    if photo_id:
        photo_person = db.photo.get(photo_id, 'person')
        if nodeid != photo_person:
            db.photo.set(photo_id, person=nodeid)
    if have_consent_forms(db):
        cf_id = db.person.get(nodeid, 'consent_form')
        if cf_id:
            cf_person = db.consent_form.get(cf_id, 'person')
            if nodeid != cf_person:
                db.consent_form.set(cf_id, person=nodeid)
    if have_id_scans(db):
        sc_id = db.person.get(nodeid, 'id_scan')
        if sc_id:
            sc_person = db.id_scan.get(sc_id, 'person')
            if nodeid != sc_person:
                db.id_scan.set(sc_id, person=nodeid)


def scoreboard_react(db, cl, nodeid, oldvalues):
    """Mark the cached scoreboard invalid."""
    invalidate_cache(db, 'scoreboard')


def register_reactors(db):
    """Register the matholymp reactors with Roundup."""
    db.country.react('set', country_react)
    db.country.react('create', country_react)
    db.country.react('retire', country_react)
    db.country.react('restore', country_react)
    db.person.react('set', person_react)
    db.person.react('create', person_react)
    db.person.react('retire', person_react)
    db.person.react('restore', person_react)
    db.event.react('set', scoreboard_react)
    db.event.react('create', scoreboard_react)
    db.event.react('retire', scoreboard_react)
    db.event.react('restore', scoreboard_react)
    db.matholymprole.react('set', scoreboard_react)
    db.matholymprole.react('create', scoreboard_react)
    db.matholymprole.react('retire', scoreboard_react)
    db.matholymprole.react('restore', scoreboard_react)
