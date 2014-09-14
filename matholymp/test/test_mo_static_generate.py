# Test mo-static-generate script.

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
Tests for mo-static-generate script.
"""

import os.path
import shutil
import subprocess
import sys
import tempfile
import unittest

from matholymp.test.testutil import MoScriptTestCase, load_script_tests

__all__ = ['load_tests', 'MoStaticGenerateTestCase']

class MoStaticGenerateTestCase(MoScriptTestCase):

    """
    A MoStaticGenerateTestCase object verifies the results of
    mo-static-generate for given inputs.
    """

    def __init__(self, method_name='runTest', script_dir=None, script=None,
                 top_dir=None, dir=None):
        """Initialise a MoStaticGenerateTestCase."""
        self.script = script
        if script_dir is not None:
            self.script_path = os.path.join(script_dir, script)
        self.dir = dir
        if dir is not None:
            full_dir = os.path.join(top_dir, dir)
            self.in_dir = os.path.join(full_dir, 'in')
            self.expected_out_dir = os.path.join(full_dir, 'out')
        super(MoStaticGenerateTestCase, self).__init__(method_name)

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.out_dir = os.path.join(self.temp_dir, 'out')
        shutil.copytree(self.in_dir, self.out_dir)

    def runTest(self):
        returncode = 0
        try:
            output = subprocess.check_output([sys.executable,
                                              self.script_path],
                                             cwd=self.out_dir,
                                             stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            returncode = e.returncode
            output = e.output
        self.assertFalse(output)
        self.assertEqual(returncode, 0)
        self.assert_dirs_equal(self.expected_out_dir, self.out_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

def load_tests(loader, standard_tests, pattern):
    """Return a TestSuite for all the mo-static-generate tests."""
    return load_script_tests('mo-static-generate', MoStaticGenerateTestCase)
