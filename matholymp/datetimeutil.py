# Date and time handling for matholymp package.

# Copyright 2017-2018 Joseph Samuel Myers.

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
This module provides date and time support for matholymp use.
"""

import datetime
import re

__all__ = ['date_from_ymd_str', 'date_from_ymd_iso', 'month_name',
           'date_range_html', 'date_to_ymd_iso', 'date_to_name', 'age_on_date',
           'time_from_hhmm_str', 'time_from_hhmm_iso', 'time_to_hhmm']


def date_from_ymd_str(desc, year, month, day):
    """
    Return a date object for the given year, month and day, given as
    strings (month and day must be exactly two digits).
    """
    if not re.match('^[0-9]{1,}\\Z', year):
        raise ValueError('%s: invalid year' % desc)
    if not re.match('^[0-9]{2}\\Z', month):
        raise ValueError('%s: invalid month' % desc)
    if not re.match('^[0-9]{2}\\Z', day):
        raise ValueError('%s: invalid day' % desc)
    year = int(year)
    month = int(month)
    day = int(day)
    err = None
    try:
        ret = datetime.date(year, month, day)
    except ValueError as exc:
        err = exc.args[0]
    if err is not None:
        raise ValueError('%s: %s' % (desc, err))
    return ret


def date_from_ymd_iso(desc, date_str):
    """Return a date object for the given ISO yyyy-mm-dd string."""
    m = re.match('^([0-9]{1,})-([0-9]{2})-([0-9]{2})\\Z', date_str)
    if not m:
        raise ValueError('%s: bad date' % desc)
    year = m.group(1)
    month = m.group(2)
    day = m.group(3)
    return date_from_ymd_str(desc, year, month, day)


# Output is meant to be locale-independent, so hardcode months here.
_english_months = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November',
                   'December']


def month_name(month):
    """Return the English name for a month."""
    return _english_months[month - 1]


def date_range_html(start_date, end_date, year):
    """Return HTML for a range of dates, within the given year."""
    if start_date.year != year or end_date.year != year:
        raise ValueError('Dates not in expected year')
    if start_date > end_date:
        raise ValueError('Start date after end date')
    start_month_name = month_name(start_date.month)
    end_month_name = month_name(end_date.month)
    if start_date.month == end_date.month:
        return ('%02d&ndash;%02d&nbsp;%s'
                % (start_date.day, end_date.day, end_month_name))
    else:
        return ('%02d&nbsp;%s&ndash;%02d&nbsp;%s'
                % (start_date.day, start_month_name,
                 end_date.day, end_month_name))


def date_to_ymd_iso(date):
    """
    Convert a date to an ISO yyyy-mm-dd string.  The date may be None,
    in which case the empty string is returned.
    """
    if date is None:
        return ''
    return '%04d-%02d-%02d' % (date.year, date.month, date.day)


def date_to_name(date):
    """Return the English (day month year) name of a date."""
    return '%d %s %d' % (date.day, month_name(date.month), date.year)


def age_on_date(date1, date2):
    """Return the age on the second date of a person born on the first date."""
    diff = date2.year - date1.year
    if ((date2.month < date1.month) or (date2.month == date1.month
                                        and date2.day < date1.day)):
        diff -= 1
    return diff


def time_from_hhmm_str(desc, hour, minute):
    """
    Return a time object for the given hour and minute, given as
    strings (exactly two digits).
    """
    if not re.match('^[0-9]{2}\\Z', hour):
        raise ValueError('%s: invalid hour' % desc)
    if not re.match('^[0-9]{2}\\Z', minute):
        raise ValueError('%s: invalid minute' % desc)
    hour = int(hour)
    minute = int(minute)
    err = None
    try:
        ret = datetime.time(hour, minute)
    except ValueError as exc:
        err = exc.args[0]
    if err is not None:
        raise ValueError('%s: %s' % (desc, err))
    return ret


def time_from_hhmm_iso(desc, time_str):
    """Return a time object for the given ISO hh:mm string."""
    m = re.match('^([0-9]{2}):([0-9]{2})\\Z', time_str)
    if not m:
        raise ValueError('%s: bad time' % desc)
    hour = m.group(1)
    minute = m.group(2)
    return time_from_hhmm_str(desc, hour, minute)


def time_to_hhmm(time):
    """
    Convert a time to an hh:mm string.  The time may be None, in which
    case the empty string is returned.
    """
    if time is None:
        return ''
    return '%02d:%02d' % (time.hour, time.minute)
