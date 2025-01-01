# Implement mo-sphinx-build script.

# Copyright 2014-2025 Joseph Samuel Myers.

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
The mo-sphinx-build script generates the formatted HTML documentation
for matholymp.  It is generated in the working directory, and it is
expected that the script is located in the matholymp source directory.
"""

import argparse
import os
import os.path
import sys

import sphinx.cmd.build

import matholymp

__all__ = ['main']


def main():
    """Main program for mo-sphinx-build."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + matholymp.__version__)
    parser.parse_args()
    sys.exit(sphinx.cmd.build.main(['-b', 'dirhtml',
                                    os.path.join(sys.path[0], 'docs'),
                                    os.curdir]))
