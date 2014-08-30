# Registration system data handling for matholymp package.

# Copyright 2014 Joseph Samuel Myers.

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

from matholymp.urlutil import url_unquote

__all__ = ['file_url_to_local']

def file_url_to_local(url, local_dir, type):
    """
    Convert a registration system download URL for a file to a local path.
    """
    url = re.sub('^.*?/file', '', url)
    matches = re.match("^([0-9]+)/(.*)", url)
    file_id = matches.group(1)
    file_name = matches.group(2)
    file_name = url_unquote(file_name)
    file_name = re.sub('[^a-zA-Z0-9_.]', '_', file_name)
    file_name = re.sub('^.*\\.', type + '.', file_name)
    file_name = re.sub('^[^.]*$', type, file_name)
    return os.path.join(local_dir, type + file_id, file_name)
