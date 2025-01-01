# Image processing for matholymp package.

# Copyright 2017-2025 Joseph Samuel Myers.

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

"""This module provides image processing support for matholymp use."""

__all__ = ['open_image_no_alpha', 'scale_image_to_size',
           'scale_image_to_size_jpeg', 'scale_image_to_size_png',
           'image_size_for_width', 'scale_image_to_width_jpeg',
           'scale_image_to_width_png']

import io
import fractions

from PIL import Image


def open_image_no_alpha(filename):
    """Open an image, returning an Image object with no alpha channel."""
    image = Image.open(filename)
    if image.mode not in ('RGB', 'L'):
        # Convert to RGB, removing any alpha channel.
        if (image.mode in ('RGBA', 'LA')
            or (image.mode == 'P'
                and 'transparency' in image.info)):
            image = image.convert('RGBA')
            background = Image.new('RGBA', image.size,
                                   (255, 255, 255, 255))
            image = Image.alpha_composite(background, image)
        image = image.convert('RGB')
    return image


def scale_image_to_size(image, size_xy):
    """Return an image scaled to the given size."""
    return image.resize(size_xy, Image.LANCZOS)


def scale_image_to_size_jpeg(image, size_xy):
    """Return an image scaled to the given size, as JPEG file contents."""
    image = scale_image_to_size(image, size_xy)
    image_out = io.BytesIO()
    image.save(image_out, format='JPEG', quality=90)
    image_bytes = image_out.getvalue()
    image_out.close()
    return image_bytes


def scale_image_to_size_png(image, size_xy):
    """Return an image scaled to the given size, as PNG file contents."""
    image = scale_image_to_size(image, size_xy)
    image_out = io.BytesIO()
    image.save(image_out, format='PNG')
    image_bytes = image_out.getvalue()
    image_out.close()
    return image_bytes


def image_size_for_width(image, width):
    """Return the size of an image, scaled to the given width."""
    orig_size = image.size
    scaled_y = orig_size[1] * fractions.Fraction(width, orig_size[0])
    return (width, round(scaled_y))


def scale_image_to_width_jpeg(image, width):
    """Return an image scaled to the given width, as JPEG file contents."""
    return scale_image_to_size_jpeg(image, image_size_for_width(image, width))


def scale_image_to_width_png(image, width):
    """Return an image scaled to the given width, as PNG file contents."""
    return scale_image_to_size_png(image, image_size_for_width(image, width))
