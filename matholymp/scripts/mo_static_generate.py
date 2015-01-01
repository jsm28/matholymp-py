# Implement mo-static-generate script.

# Copyright 2014-2015 Joseph Samuel Myers.

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
The mo-static-generate script processes CSV input files to generate a
static website for mathematical olympiads.  It expects to be run with
a working directory that also contains files staticsite.cfg and
page-template.  The website is generated in that directory.  Files
data/countries.csv, data/<event>s.csv, data/papers.csv and
data/people.csv are used as inputs.  The script does not generate an
overall front page to the site; such a page must be created manually.
The page template, or a manually created page, should contain links to
the overall countries/, <event>s/ and people/ pages.
"""

import argparse
import os

import matholymp
from matholymp.sitegen import read_sitegen_config, sitegen_event_group, \
    SiteGenerator

__all__ = ['main']

def main():
    """Main program for mo-static-generate."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version',
                        version='%(prog)s '+matholymp.__version__)
    parser.parse_args()

    top_directory = os.getcwd()

    cfg_data = read_sitegen_config(top_directory)
    all_data = sitegen_event_group(top_directory, cfg_data)

    sitegen = SiteGenerator(cfg_data, all_data, top_directory)
    sitegen.generate_site()
