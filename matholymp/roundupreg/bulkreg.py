# Bulk registration for Roundup registration system for matholymp package.

# Copyright 2019-2025 Joseph Samuel Myers.

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
This module provides bulk registration support functions for the
Roundup registration system.
"""

import base64
import binascii
import csv
import hashlib
import os
import os.path
import re
import zipfile

from matholymp.fileutil import read_utf8_csv_bytes, comma_split
from matholymp.roundupreg.rounduputil import valid_int_str

__all__ = ['bulk_csv_delimiter', 'bulk_csv_data', 'bulk_csv_contact_emails',
           'bulk_csv_country_number_url', 'bulk_csv_person_number_url',
           'upload_path_from_hash', 'bulk_zip_data']


def bulk_csv_delimiter(form):
    """Return the delimiter of a previously uploaded CSV file."""
    if 'csv_delimiter' in form:
        delimiter = form['csv_delimiter'].value
        if delimiter in (',', ';'):
            return delimiter
    return ','


def bulk_csv_data(form, comma_sep_fields=()):
    """
    Return the rows of an uploaded CSV file, in a tuple with a boolean
    for whether just to check the results or act on them, or a string
    error message.
    """
    # A csv_file form input with nonempty filename means data has been
    # uploaded for initial checking.  A csv_contents form input means
    # the previously checked data has been submitted for actual bulk
    # registration (but should still be rechecked rather than trusting
    # the client).
    if 'csv_file' in form and form['csv_file'].filename != '':
        check_only = True
        file_bytes = form['csv_file'].value
        if not isinstance(file_bytes, bytes):
            return 'csv_file not an uploaded file'
    elif 'csv_contents' in form:
        check_only = False
        file_base64_str = form['csv_contents'].value
        if not isinstance(file_base64_str, str):
            return 'csv_contents an uploaded file'
        try:
            file_bytes = base64.b64decode(file_base64_str, validate=True)
        except (ValueError, binascii.Error) as exc:
            return str(exc)
    else:
        return 'no CSV file uploaded'
    delimiter = bulk_csv_delimiter(form)
    try:
        file_data = read_utf8_csv_bytes(file_bytes, delimiter=delimiter)
    except (UnicodeError, csv.Error) as exc:
        return str(exc)
    # For user convenience, strip leading and trailing whitespace
    # from CSV file fields.  Remove empty fields.
    for row in file_data:
        for key in list(row.keys()):
            row[key] = row[key].strip()
            if row[key] == '':
                del row[key]
            elif key in comma_sep_fields:
                # Convert comma-separated fields into lists.  Entries
                # in such lists must be unique.
                try:
                    sub_row = comma_split(row[key])
                except (ValueError, csv.Error) as exc:
                    return str(exc)
                row[key] = [val.strip() for val in sub_row]
                if len(row[key]) != len(set(row[key])):
                    return 'duplicate entries in %s' % key
    return (file_data, check_only)


def bulk_csv_contact_emails(row):
    """Return main and extra contact emails from an uploaded CSV."""
    contact_email = row.get('Contact Email 1', '')
    if contact_email:
        contact_list = [contact_email]
        n = 2
        while ('Contact Email %d' % n) in row:
            contact_list.append(row['Contact Email %d' % n])
            n += 1
        return contact_list
    else:
        return []


def bulk_csv_country_number_url(db, row):
    """
    Return the country number and previous participation URL for a
    bulk-registered country.
    """
    country_number = row.get('Country Number', '')
    if country_number and valid_int_str(country_number, None):
        gubase = db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
        return (int(country_number),
                '%scountries/country%s/' % (gubase, country_number))
    else:
        return None, None


def bulk_csv_person_number_url(db, row):
    """
    Return the person number and previous participation URL for a
    bulk-registered person.
    """
    person_number = row.get('Person Number', '')
    if person_number and valid_int_str(person_number, None):
        gubase = db.config.ext['MATHOLYMP_GENERIC_URL_BASE']
        return (int(person_number),
                '%speople/person%s/' % (gubase, person_number))
    else:
        return None, None


def upload_path_from_hash(db, hashstr):
    """
    Return the path to use for an uploaded file, creating any required
    directories.  This is used to stash uploaded ZIP files between the
    first and second stages of bulk registration.  At present, such
    uploaded files are never deleted once created.
    """
    db_path = db.config.DATABASE
    upload_path = os.path.join(db_path, 'upload')
    os.makedirs(upload_path, exist_ok=True)
    return os.path.join(upload_path, hashstr)


def bulk_zip_data(db, form):
    """
    Return a ZipFile object for an uploaded ZIP file, or None if no
    such file was uploaded, or a string on error.
    """
    # A zip_file form input with nonempty filename means a ZIP file
    # has been uploaded now.  A nonempty zip_ref form input refers to
    # such a file previously uploaded.
    if 'zip_file' in form and form['zip_file'].filename != '':
        file_bytes = form['zip_file'].value
        if not isinstance(file_bytes, bytes):
            return 'zip_file not an uploaded file'
        hashstr = hashlib.sha256(file_bytes).hexdigest()
        file_path = upload_path_from_hash(db, hashstr)
        if not os.access(file_path, os.F_OK):
            with open(file_path, 'wb') as file:
                file.write(file_bytes)
        try:
            return zipfile.ZipFile(file_path)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError,
                ValueError, NotImplementedError, EOFError) as exc:
            return str(exc)
    elif 'zip_ref' in form and form['zip_ref'].value != '':
        hashstr = form['zip_ref'].value
        if not isinstance(hashstr, str):
            return 'zip_ref an uploaded file'
        if not re.fullmatch('[0-9a-f]{64}', hashstr):
            return 'zip_ref not a valid hash'
        file_path = upload_path_from_hash(db, hashstr)
        if not os.access(file_path, os.F_OK):
            return 'zip_ref not a known hash'
        try:
            return zipfile.ZipFile(file_path)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError,
                ValueError, NotImplementedError, EOFError) as exc:
            return str(exc)
    else:
        return None
