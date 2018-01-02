# Statistical utilities for matholymp package.

# Copyright 2015-2018 Joseph Samuel Myers.

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
This module provides statistics support for matholymp use.
"""

import math

__all__ = ['mean_std_dev', 'corr_coeff']

# These functions do everything with integers before the final
# division and square root, to reduce the chance of floating-point
# rounding affecting the final textual output.

def _sum_sq(data):
    return sum([x * x for x in data])

def mean_std_dev(data):
    """
    Return the mean and standard deviation of a list of integers, or
    None for an empty list.  Values of None in the list are ignored.
    """
    data = [x for x in data if x is not None]
    n = len(data)
    if n == 0:
        return None
    s = sum(data)
    s2 = _sum_sq(data)
    mean = float(s) / float(n)
    std_dev =  math.sqrt(float(n * s2 - s * s) / float(n * n))
    return (mean, std_dev)

def corr_coeff(data):
    """
    Return the correlation coefficient or a list of pairs of integers,
    or None if either variable is constant.  Pairs containing a value
    None are ignored.
    """
    data = [x for x in data if x[0] is not None and x[1] is not None]
    n = len(data)
    if n == 0:
        return None
    xdata = [d[0] for d in data]
    ydata = [d[1] for d in data]
    sx = sum(xdata)
    sx2 = _sum_sq(xdata)
    sy = sum(ydata)
    sy2 = _sum_sq(ydata)
    sxy = sum([d[0] * d[1] for d in data])
    num = n * sxy - sx * sy
    den2 = (n * sx2 - sx * sx) * (n * sy2 - sy * sy)
    if den2 == 0:
        return None
    return float(num) / math.sqrt(float(den2))
