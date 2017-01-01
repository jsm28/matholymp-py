# Registration system data handling for matholymp package.

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

"""
This module handles input data downloaded from the registration system.
"""

import os.path
import re

from matholymp.fileutil import file_extension

__all__ = ['file_url_to_local', 'lang_to_filename']

_type_to_entity_type = { 'flag': 'country',
                         'photo': 'person',
                         'consent-form': 'person' }

def file_url_to_local(url, local_dir, type, id):
    """
    Convert a registration system download URL for a file to a local path.
    """
    ext = file_extension(url)
    entity_type = _type_to_entity_type[type]
    return os.path.join(local_dir, entity_type + str(id), type + '.' + ext)

def lang_to_filename(lang):
    """Convert a language name to the form used in a filename."""
    return re.sub('[^a-zA-Z]', '', lang)
