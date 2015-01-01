# User auditor for Roundup registration system for matholymp package.

# Copyright 2014-2015 Joseph Samuel Myers.

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

# Based on userauditor.py from Roundup, to which the following applies:

# Copyright (c) 2003 Richard Jones (richard@mechanicalcat.net)
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

"""
This module provides the user auditor for the Roundup registration system.
"""

__all__ = ['audit_user_fields']

import re

from matholymp.roundupreg.auditorutil import require_value

# regular expression thanks to: http://www.regular-expressions.info/email.html
# this is the "99.99% solution for syntax only".
_email_regexp = (r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*", r"(localhost|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9]))")
_email_rfc = re.compile('^' + _email_regexp[0] + '@' + _email_regexp[1] + '$', re.IGNORECASE)

def _valid_address(address):
    """Check validity of an email address."""
    return _email_rfc.match(address)

def audit_user_fields(db, cl, nodeid, newvalues):
    """ Make sure user properties are valid.

        - email address is syntactically valid
        - email address is unique
        - roles specified exist
        - country is specified
    """

    if 'address' in newvalues:
        address = newvalues['address']
        if not _valid_address(address):
            raise ValueError('Email address syntax is invalid')

        if db.user.stringFind(address=address):
            raise ValueError('Email address %s already in use' % address)

    for rolename in [r.lower().strip()
                     for r in newvalues.get('roles', '').split(',')]:
        if rolename and not db.security.role.has_key(rolename):
            raise ValueError('Role "%s" does not exist' % rolename)

    require_value(db, cl, nodeid, newvalues, 'country', 'No country specified')
