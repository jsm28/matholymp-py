# Test mo-static-upgrade script.

# Copyright 2015-2022 Joseph Samuel Myers.

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
Tests for mo-static-upgrade script.
"""

from matholymp.test.testutil import MoScriptTestCase, load_script_tests

__all__ = ['load_tests', 'MoStaticUpgradeTestCase']


class MoStaticUpgradeTestCase(MoScriptTestCase):

    """
    A MoStaticUpgradeTestCase object verifies the results of
    mo-static-upgrade for given inputs.
    """

    def __init__(self, method_name='runTest', script_dir=None, script=None,
                 top_dir=None, this_dir=None, coverage=False):
        """Initialise a MoStaticUpgradeTestCase."""
        super().__init__(method_name, script_dir, script, top_dir, this_dir,
                         coverage)
        if this_dir is not None:
            assert self.check_dir


def load_tests(loader, standard_tests, pattern):
    """Return a TestSuite for all the mo-static-upgrade tests."""
    return load_script_tests('mo-static-upgrade', MoStaticUpgradeTestCase,
                             loader.coverage)
