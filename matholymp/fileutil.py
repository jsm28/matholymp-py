# File access utilities for matholymp package.

# Copyright 2014-2020 Joseph Samuel Myers.

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

import configparser
import csv
import imghdr
import io
import os
import os.path
import re
import string

__all__ = ['read_utf8_csv', 'read_utf8_csv_bytes', 'write_utf8_csv_bytes',
           'write_utf8_csv', 'comma_join', 'comma_split', 'make_dirs_for_file',
           'write_bytes_to_file', 'write_text_to_file', 'read_text_from_file',
           'replace_text_in_file', 'read_config_raw', 'read_config',
           'write_config_raw', 'boolean_states', 'remove_if_exists',
           'file_format_contents', 'file_extension', 'mime_type_map']


def read_utf8_csv(csv_file_name):
    """
    Read the contents of a UTF-8 CSV file (with BOM) into an array of
    dictionaries.
    """
    with open(csv_file_name, 'r', encoding='utf-8-sig',
              newline='') as csv_file:
        csv_reader = csv.DictReader(csv_file, restval='')
        rows = [row for row in csv_reader]
        return rows


def read_utf8_csv_bytes(csv_file_bytes, delimiter=','):
    """
    Read the contents of a UTF-8 CSV file (with BOM), given as byte
    contents, into an array of dictionaries.
    """
    csv_bytes_file_b = io.BytesIO(csv_file_bytes)
    csv_bytes_file = io.TextIOWrapper(csv_bytes_file_b,
                                      encoding='utf-8-sig',
                                      newline='')
    csv_reader = csv.DictReader(csv_bytes_file, restval='',
                                delimiter=delimiter)
    rows = [row for row in csv_reader]
    return rows


def write_utf8_csv_bytes(rows, keys, delimiter=','):
    """
    Return the byte contents of a UTF-8 CSV file (with BOM) from an
    array of dictionaries.
    """
    csv_bytes_file_b = io.BytesIO()
    csv_bytes_file = io.TextIOWrapper(csv_bytes_file_b,
                                      encoding='utf-8-sig',
                                      newline='')
    csv_file_writer = csv.DictWriter(csv_bytes_file, keys,
                                     extrasaction='raise', dialect='excel',
                                     delimiter=delimiter)
    csv_file_writer.writeheader()
    csv_file_writer.writerows(rows)
    csv_bytes_file.flush()
    csv_bytes = csv_bytes_file_b.getvalue()
    csv_bytes_file_b.close()
    return csv_bytes


def write_utf8_csv(csv_file_name, rows, keys, delimiter=','):
    """Write a UTF-8 CSV file (with BOM) from an array of dictionaries."""
    write_bytes_to_file(write_utf8_csv_bytes(rows, keys, delimiter=delimiter),
                        csv_file_name)


def comma_join(val_list):
    """
    Join the given strings together, quoted as needed, in an
    unambiguous way, as if they formed the row of a single-row CSV
    file."""
    if len(val_list) == 0:
        return ''
    if len(val_list) == 1 and val_list[0] == '':
        return '""'
    csv_text_file = io.StringIO(newline='')
    csv_file_writer = csv.writer(csv_text_file, dialect='excel')
    csv_file_writer.writerow(val_list)
    csv_text = csv_text_file.getvalue()
    csv_text_file.close()
    if csv_text[-1] == '\n':
        csv_text = csv_text[:-1]
    if csv_text[-1] == '\r':
        csv_text = csv_text[:-1]
    return csv_text


def comma_split(val_text):
    """
    Split the given comma-separated string as if it formed the row of
    a single-row CSV file.
    """
    if val_text == '':
        return []
    csv_text_file = io.StringIO(initial_value=val_text, newline='')
    csv_file_reader = csv.reader(csv_text_file, dialect='excel')
    val_row = None
    for row in csv_file_reader:
        if val_row is not None:
            raise ValueError('Multiple rows in comma-separated string')
        val_row = row
    if val_row is None:
        raise ValueError('No rows in comma-separated string')
    csv_text_file.close()
    return val_row


def make_dirs_for_file(file_name):
    """Create directories needed to create a file."""
    dir_name = os.path.dirname(file_name)
    if not os.access(dir_name, os.F_OK):
        os.makedirs(dir_name)


def write_bytes_to_file(out_bytes, out_file_name):
    """Write some bytes to a file, but not if it would be unchanged."""
    make_dirs_for_file(out_file_name)
    if os.access(out_file_name, os.F_OK):
        with open(out_file_name, 'rb') as in_file:
            content = in_file.read()
        if content == out_bytes:
            return
    with open(out_file_name, 'wb') as out_file:
        out_file.write(out_bytes)


def write_text_to_file(out_text, out_file_name):
    """Write some UTF-8 text to a file (without BOM)."""
    out_bytes = out_text.encode(encoding='utf-8')
    write_bytes_to_file(out_bytes, out_file_name)


def read_text_from_file(file_name):
    """Read the UTF-8 (no BOM) text contents of a file."""
    with open(file_name, 'r', encoding='utf-8') as in_file:
        text = in_file.read()
    return text


def replace_text_in_file(file_name, old, new):
    """Replace some text in a UTF-8 file."""
    text = read_text_from_file(file_name)
    write_text_to_file(text.replace(old, new), file_name)


def read_config_raw(file_name):
    """
    Read a (UTF-8, no BOM) configuration file and return the
    RawConfigParser object.
    """
    cfg = configparser.RawConfigParser()
    with open(file_name, 'r', encoding='utf-8') as cfg_file:
        cfg.read_file(cfg_file)
    return cfg


def read_config(file_name, section, str_keys, int_keys, int_none_keys,
                bool_keys):
    """
    Read a (UTF-8, no BOM) configuration file and return a dict of the
    configuration values from the given section, with the given keys
    indicating strings, integers, integers where None should be
    returned for an empty string, and booleans.
    """
    cfg = read_config_raw(file_name)
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


def write_config_raw(cfg, file_name):
    """Write a RawConfigParser to a file."""
    with open(file_name, 'w', encoding='utf-8') as cfg_file:
        cfg.write(cfg_file)


boolean_states = configparser.RawConfigParser.BOOLEAN_STATES
"""Mapping of boolean states to values in configuration files."""


def remove_if_exists(file_name):
    """Remove a file if it exists."""
    if os.access(file_name, os.F_OK):
        os.remove(file_name)


# Map file format names from imghdr to canonical extensions.
_file_format_ext_map = {'jpeg': 'jpg',
                        'png': 'png'}


def file_format_contents(filename, contents=None):
    """
    Return the format of a file (in the form of a canonical filename
    extension) based on its contents, or None if not a known format
    that might be valid for some matholymp uses.
    """
    fmt = imghdr.what(filename, contents)
    if fmt in _file_format_ext_map:
        return _file_format_ext_map[fmt]
    else:
        if contents is not None:
            h = contents[:5]
        else:
            with open(filename, 'rb') as f:
                h = f.read(5)
        if h == b'%PDF-':
            return 'pdf'
        return None


_ascii_tolower = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)

# Map extensions to their canonical forms.
_file_ext_map = {'jpg': 'jpg',
                 'jpeg': 'jpg',
                 'png': 'png',
                 'pdf': 'pdf'}


def file_extension(name):
    """
    Given a filename or URL, return the canonical form of its filename
    extension, or None if not a known extension that might be valid
    for some matholymp uses.
    """
    if '.' not in name:
        return None
    name = re.sub('[^a-zA-Z0-9_.]', '_', name)
    name = re.sub('^.*\\.', '', name)
    name = name.translate(_ascii_tolower)
    if name in _file_ext_map:
        return _file_ext_map[name]
    else:
        return None


mime_type_map = {'png': 'image/png', 'jpg': 'image/jpeg'}
"""Mapping of file extensions to corresponding MIME types."""
