# Case conversion support for matholymp package.

# Copyright 2015-2019 Joseph Samuel Myers.

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

"""
This module provides case conversion support for matholymp use.
"""

import icu

__all__ = ['tolower', 'toupper', 'all_uppercase']


def tolower(text):
    """Return the argument string converted to lowercase."""
    usret = icu.UnicodeString(text).toLower(icu.Locale('en_GB'))
    return str(usret)


def toupper(text):
    """Return the argument string converted to uppercase."""
    usret = icu.UnicodeString(text).toUpper(icu.Locale('en_GB'))
    return str(usret)


def all_uppercase(text):
    """Return whether the argument string is all uppercase."""
    return text == toupper(text) and text != tolower(text)
