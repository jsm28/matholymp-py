# Utilities for matholymp testing.

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
This module provides utility functions for matholymp testing.
"""

import filecmp
import os
import os.path
import unittest

__all__ = ['MoScriptTestCase', 'load_script_tests']

class MoScriptTestCase(unittest.TestCase):

    """
    A MoScriptTestCase provides functionality for testing matholymp scripts.
    """

    def __str__(self):
        return self.script + ' ' + self.dir

    def _assert_dcmp_equal(self, dcmp):
        self.assertFalse(dcmp.left_only)
        self.assertFalse(dcmp.right_only)
        self.assertFalse(dcmp.common_funny)
        self.assertFalse(dcmp.diff_files)
        self.assertFalse(dcmp.funny_files)
        for sub_dcmp in dcmp.subdirs.values():
            self._assert_dcmp_equal(sub_dcmp)

    def assert_dirs_equal(self, dir1, dir2):
        """Assert that the contents of two directories are the same."""
        dcmp = filecmp.dircmp(dir1, dir2, [])
        self._assert_dcmp_equal(dcmp)

def load_script_tests(script, cl):
    """Load the tests for the given script."""
    suite = unittest.TestSuite()
    mod_dir = os.path.dirname(os.path.abspath(__file__))
    top_dir = os.path.dirname(os.path.dirname(mod_dir))
    test_top_dir = os.path.join(top_dir, 'test-data', script)
    for d in sorted(os.listdir(test_top_dir)):
        suite.addTest(cl(script_dir=top_dir, script=script,
                         top_dir=test_top_dir, dir=d))
    return suite
