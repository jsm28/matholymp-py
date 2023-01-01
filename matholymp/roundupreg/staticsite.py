# Static site access for Roundup registration system for matholymp package.

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

"""
This module provides access to the static site from the Roundup
registration system.
"""

import os.path

from matholymp.fileutil import file_extension, mime_type_map
from matholymp.roundupreg.config import get_static_site_path
from matholymp.sitegen import read_sitegen_config, sitegen_event_group

__all__ = ['static_site_event_group', 'static_site_file_data']


def static_site_event_group(db):
    """
    Return an EventGroup for the static site, or None if static site
    access is not available.
    """
    static_site_path = get_static_site_path(db)
    if not static_site_path:
        return None
    cfg_data = read_sitegen_config(static_site_path)
    return sitegen_event_group(static_site_path, cfg_data)


def static_site_file_data(db, url):
    """
    Return file name, content and MIME type for a file from the static
    site, or None if not available.
    """
    if not url:
        return None
    gubase = db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
    if not url.startswith(gubase):
        return None
    url_path = url[len(gubase):]
    url_dirs = url_path.split('/')
    static_site_path = get_static_site_path(db)
    if not static_site_path:
        return None
    file_path = os.path.join(static_site_path, *url_dirs)
    file_ext = file_extension(file_path)
    if file_ext not in mime_type_map:
        return None
    with open(file_path, 'rb') as in_file:
        content = in_file.read()
    return {'name': url_dirs[-1],
            'type': mime_type_map[file_ext],
            'content': content}
