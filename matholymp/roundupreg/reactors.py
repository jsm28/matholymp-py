# Reactors for Roundup registration system for matholymp package.

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

"""This module provides reactors for the Roundup registration system."""

__all__ = ['country_react', 'person_react', 'scoreboard_react',
           'register_reactors']

import email
import os.path

import roundup.mailer
import roundup.password

from matholymp.fileutil import read_text_from_file
from matholymp.roundupreg.cache import invalidate_cache
from matholymp.roundupreg.rounduputil import have_consent_forms

def country_react(db, cl, nodeid, oldvalues):
    """
    Mark the cached scoreboard invalid, and create an account for a
    country if required.
    """
    scoreboard_react(db, cl, nodeid, oldvalues)
    if db.country.is_retired(nodeid):
        return
    email_addr = db.country.get(nodeid, 'contact_email')
    if not email_addr:
        return
    country_code = db.country.get(nodeid, 'code')
    username = country_code + '_reg'
    if db.user.stringFind(username=username):
        return
    country_name = db.country.get(nodeid, 'name')
    realname = country_name + ' registration'
    if db.user.stringFind(realname=realname):
        return
    pw = roundup.password.generatePassword()
    user_id = db.user.create(username=username, realname=realname,
                             password=roundup.password.Password(pw),
                             address=email_addr, country=nodeid,
                             roles='User,Register')
    template_path = os.path.join(db.config.TRACKER_HOME, 'extensions',
                                 'email-template-new-user')
    template_text = read_text_from_file(template_path)
    email_text = template_text % { 'country': country_name,
                                   'username': username,
                                   'password': pw }
    short_name = db.config.ext['MATHOLYMP_SHORT_NAME']
    year = db.config.ext['MATHOLYMP_YEAR']
    subject = '%s %s registration (%s)' % (short_name, year, country_name)
    author_name = '%s %s registration' % (short_name, year)
    mailer = roundup.mailer.Mailer(db.config)
    # Roundup's standard_message function does not set a Message-ID,
    # so go through the steps it takes but with one added.
    msg = mailer.get_standard_message()
    msg['Message-Id'] = email.utils.make_msgid('matholymp.' + country_code)
    email_to = [email_addr, db.config.ADMIN_EMAIL]
    mailer.set_message_attributes(msg,
                                  email_to,
                                  subject,
                                  (author_name, db.config.ADMIN_EMAIL))
    msg.set_payload(email_text)
    roundup.mailer.encode_quopri(msg)
    try:
        mailer.smtp_send(email_to, msg.as_string())
    except roundup.mailer.MessageSendError:
        pass

def person_react(db, cl, nodeid, oldvalues):
    """
    Mark the cached scoreboard invalid, and set the country for a
    person's consent form if required.
    """
    scoreboard_react(db, cl, nodeid, oldvalues)
    if db.person.is_retired(nodeid):
        return
    if not have_consent_forms(db):
        return
    cf = db.person.get(nodeid, 'consent_form')
    if not cf:
        return
    person_country = db.person.get(nodeid, 'country')
    file_country = db.private_file.get(cf, 'country')
    if file_country != person_country:
        db.private_file.set(cf, country=person_country)

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
