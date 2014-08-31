# File access utilities for matholymp package.

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
This module provides file access support for matholymp use.
"""

import sys
_py3 = sys.version_info.major >= 3
import codecs
if _py3:
    import configparser
else:
    import ConfigParser as configparser
import csv
import io
import os
import os.path

__all__ = ['read_utf8_csv', 'write_utf8_csv_bytes', 'write_utf8_csv',
           'make_dirs_for_file', 'write_text_to_file', 'read_text_from_file',
           'read_config', 'boolean_states', 'remove_if_exists']

if _py3:
    _text_open_args = { 'encoding': 'utf-8' }
else:
    _text_open_args = {}

def read_utf8_csv(csv_file_name):
    """
    Read the contents of a UTF-8 CSV file (with BOM) into an array of
    dictionaries.
    """
    if _py3:
        open_mode = 'r'
        open_args = { 'encoding': 'utf-8-sig', 'newline': '' }
    else:
        open_mode = 'rb'
        open_args = {}
    with open(csv_file_name, open_mode, **open_args) as csv_file:
        if not _py3:
            should_be_bom = csv_file.read(len(codecs.BOM_UTF8))
            if should_be_bom != codecs.BOM_UTF8:
                raise ValueError('CSV file %s does not have BOM' %
                                 csv_file_name)
        csv_reader = csv.DictReader(csv_file)
        rows = [row for row in csv_reader]
        return rows

def write_utf8_csv_bytes(rows, keys):
    """
    Return the byte contents of a UTF-8 CSV file (with BOM) from an
    array of dictionaries.
    """
    csv_bytes_file_b = io.BytesIO()
    if _py3:
        csv_bytes_file = io.TextIOWrapper(csv_bytes_file_b,
                                          encoding='utf-8-sig',
                                          newline='')
    else:
        csv_bytes_file_b.write(codecs.BOM_UTF8)
        csv_bytes_file = csv_bytes_file_b
    csv_file_writer = csv.DictWriter(csv_bytes_file, keys,
                                     extrasaction='raise', dialect='excel')
    csv_file_writer.writeheader()
    csv_file_writer.writerows(rows)
    csv_bytes_file.flush()
    csv_bytes = csv_bytes_file_b.getvalue()
    csv_bytes_file_b.close()
    return csv_bytes

def write_utf8_csv(csv_file_name, rows, keys):
    """Write a UTF-8 CSV file (with BOM) from an array of dictionaries."""
    with open(csv_file_name, 'wb') as csv_file:
        csv_file.write(write_utf8_csv_bytes(rows, keys))

def make_dirs_for_file(file_name):
    """Create directories needed to create a file."""
    dir = os.path.dirname(file_name)
    if not os.access(dir, os.F_OK):
        os.makedirs(dir)

def write_text_to_file(out_text, out_file_name):
    """Write some UTF-8 text to a file (without BOM)."""
    make_dirs_for_file(out_file_name)
    with open(out_file_name, 'w', **_text_open_args) as out_file:
        out_file.write(out_text)

def read_text_from_file(file_name):
    """Read the UTF-8 (no BOM) text contents of a file."""
    with open(file_name, 'r', **_text_open_args) as in_file:
        text = in_file.read()
    return text

def read_config(file_name, section, str_keys, int_keys, int_none_keys,
                bool_keys):
    """
    Read a (UTF-8, no BOM) configuration file and return a dict of the
    configuration values from the given section, with the given keys
    indicating strings, integers, integers where None should be
    returned for an empty string, and booleans.
    """
    cfg = configparser.RawConfigParser()
    with open(file_name, 'r', **_text_open_args) as cfg_file:
        cfg.readfp(cfg_file)
    ret = {}
    for k in str_keys:
        ret[k] = cfg.get(section, k)
    for k in int_keys:
        ret[k] = cfg.getint(section, k)
    for k in int_none_keys:
        v = cfg.get(section, k)
        if v == '':
            ret[k] = None
        else:
            ret[k] = int(v)
    for k in bool_keys:
        ret[k] = cfg.getboolean(section, k)
    return ret

if _py3:
    # Exported by the standard library from 3.2 onwards.
    _boolean_states = configparser.BOOLEAN_STATES
else:
    _boolean_states = { '1': True, 'yes': True, 'true': True, 'on': True,
                        '0': False, 'no': False, 'false': False, 'off': False }
boolean_states = _boolean_states
"""Mapping of boolean states to values in configuration files."""

def remove_if_exists(file_name):
    """Remove a file if it exists."""
    if os.access(file_name, os.F_OK):
        os.remove(file_name)
