# Implement mo-run-tests script.

# Copyright 2014-2019 Joseph Samuel Myers.

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
The mo-run-tests script runs the matholymp testsuite.
"""

import argparse
import unittest
import sys

import matholymp
from matholymp.test.testutil import MoTestLoader

__all__ = ['main']


def main():
    """Main program for mo-run-tests."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + matholymp.__version__)
    parser.add_argument('--coverage', action='store_true',
                        help='measure code coverage of tests')
    parser.add_argument('--pattern', default='test*.py',
                        help='pattern for test modules to use '
                        '(default test*.py)')
    args = parser.parse_args()
    loader = MoTestLoader(args.coverage)
    suite = loader.discover('matholymp.test',
                            pattern=args.pattern,
                            top_level_dir=sys.path[0])
    unittest.TextTestRunner(verbosity=2).run(suite)
