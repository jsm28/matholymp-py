# Auditor utility functions for Roundup registration system for
# matholymp package.

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

"""
This module provides utility functions for writing auditors for the
Roundup registration system.
"""

__all__ = ['get_new_value', 'require_value']

def get_new_value(db, cl, nodeid, newvalues, prop):
    """
    Return the new value of a property if one was specified, or the
    continuing old value if not, or None if this is a new node and no
    value was specified.
    """
    if prop in newvalues:
        return newvalues[prop]
    if nodeid is None:
        return None
    return cl.get(nodeid, prop)

def require_value(db, cl, nodeid, newvalues, prop, error):
    """
    Require a property to have a nonempty value, restoring a previous
    value from the database if an attempt is made to empty it; return
    that value.
    """
    value = get_new_value(db, cl, nodeid, newvalues, prop)
    if value:
        return value
    if nodeid is None:
        raise ValueError(error)
    value = cl.get(nodeid, prop)
    if not value:
        raise ValueError(error)
    newvalues[prop] = value
    return value
