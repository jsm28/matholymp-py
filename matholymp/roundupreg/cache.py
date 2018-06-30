# Cache support for Roundup registration system for matholymp package.

# Copyright 2017-2018 Joseph Samuel Myers.

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
This module provides cache support for the Roundup registration
system.
"""

__all__ = ['cached_text', 'invalidate_cache']

import os
import os.path

# This caching implementation depends on a Unix-like operating system.
# (a) It uses fcntl.  (b) It may remove the file marking the cache
# invalid while another process has it open, which may not work on
# some operating systems.  (c) fcntl semantics mean the lock is lost
# as soon as any file descriptor for the file is closed, which works
# when each query is served in a forked subprocess but may not work on
# an operating system where threads are used.
_can_cache = True
try:
    import fcntl
except ImportError:
    _can_cache = False

from matholymp.fileutil import write_text_to_file, read_text_from_file


def _cache_path(db, name, suffix):
    """Return the path for a file used in implementing the cache."""
    db_path = db.config.DATABASE
    return os.path.join(db_path, 'cache-%s.%s' % (name, suffix))


def _invalid_path(db, name):
    """Return the path for the file to mark the cache invalid."""
    return _cache_path(db, name, 'invalid')


def cached_text(db, name, force_regen, gen_func):
    """Return text that can be cached, generating it if necessary."""
    if not _can_cache:
        return gen_func(db)
    file_path = _cache_path(db, name, 'current')
    tmp_path = _cache_path(db, name, 'tmp')
    invalid_path = _invalid_path(db, name)
    lock_path = _cache_path(db, name, 'lock')
    with open(lock_path, 'w') as lock_file:
        fcntl.lockf(lock_file, fcntl.LOCK_EX)
        invalid_exists = os.access(invalid_path, os.F_OK)
        if invalid_exists:
            force_regen = True
        cache_exists = os.access(file_path, os.F_OK)
        if not cache_exists:
            force_regen = True
        if not force_regen:
            return read_text_from_file(file_path)
        if cache_exists:
            os.remove(file_path)
        if invalid_exists:
            os.remove(invalid_path)
        new_text = gen_func(db)
        write_text_to_file(new_text, tmp_path)
        os.rename(tmp_path, file_path)
        return new_text


def invalidate_cache(db, name):
    """Mark cached text invalid so it needs regenerating."""
    invalid_path = _invalid_path(db, name)
    write_text_to_file('', invalid_path)
