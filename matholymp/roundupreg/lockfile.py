# Lock file support for Roundup registration system for matholymp package.

# Copyright 2017-2021 Joseph Samuel Myers.

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
This module provides lock file support for the Roundup registration
system.
"""

__all__ = ['can_lock', 'with_lock_file']

import contextlib

# This locking implementation depends on a Unix-like operating system.
# (a) It uses fcntl.  (b) fcntl semantics mean the lock is lost as
# soon as any file descriptor for the file is closed, which works when
# each query is served in a forked subprocess but may not work on an
# operating system where threads are used.
try:
    import fcntl
    can_lock = True
except ImportError:
    can_lock = False


@contextlib.contextmanager
def with_lock_file(file):
    """Run code with a lock file active.

    If locking is not supported, runs without a lock; if this is not
    OK, the caller must check for whether locking is supported."""
    if can_lock:
        with open(file, 'w') as lock_file:
            fcntl.lockf(lock_file, fcntl.LOCK_EX)
            yield
    else:
        yield
