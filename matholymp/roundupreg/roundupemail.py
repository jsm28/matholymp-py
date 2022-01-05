# Email sending for Roundup registration system for matholymp package.

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

"""This module provides email support for the Roundup registration system."""

__all__ = ['send_email']

import email

import roundup.mailer

from matholymp.roundupreg.config import get_short_name_year


def send_email(db, email_to, subject, body, msgid_frag):
    """Send an email, ignoring errors."""
    short_name_year = get_short_name_year(db)
    author_name = '%s registration' % (short_name_year)
    mailer = roundup.mailer.Mailer(db.config)
    # Roundup's standard_message function does not set a Message-ID,
    # so go through the steps it takes but with one added.
    msg = mailer.get_standard_message()
    msg['Message-Id'] = email.utils.make_msgid('matholymp.' + msgid_frag)
    email_to = email_to + [db.config.ADMIN_EMAIL]
    mailer.set_message_attributes(msg,
                                  email_to,
                                  subject,
                                  (author_name, db.config.ADMIN_EMAIL))
    msg.set_payload(body, charset='utf-8')
    try:
        mailer.smtp_send(email_to, msg.as_string())
    except roundup.mailer.MessageSendError:
        pass
