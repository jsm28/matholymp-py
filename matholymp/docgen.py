# Document generation for matholymp package.

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
This module provides the DocumentGenerator class that can be used to
generate various documents from registration system data.
"""

import filecmp
import os
import os.path
import re
import shutil
import subprocess

from PyPDF2 import PdfFileReader

from matholymp.collate import coll_get_sort_key
from matholymp.datetimeutil import date_to_name
from matholymp.fileutil import read_utf8_csv, make_dirs_for_file, \
    write_text_to_file, read_text_from_file, read_config, remove_if_exists, \
    file_extension
from matholymp.regdata import lang_to_filename

__all__ = ['read_docgen_config', 'DocumentGenerator']


def read_docgen_config(top_directory):
    """Read the configuration file for document generation."""
    config_file_name = os.path.join(top_directory, 'documentgen.cfg')
    cfg_str_keys = ['year', 'short_name', 'long_name', 'num_key',
                    'marks_per_problem', 'badge_phone_desc',
                    'badge_event_phone', 'badge_emergency_phone',
                    'badge_event_ordinal', 'badge_event_venue',
                    'badge_event_dates']
    cfg_int_keys = ['event_number', 'num_exams', 'num_problems',
                    'num_contestants_per_team']
    cfg_int_none_keys = ['gold_boundary', 'silver_boundary', 'bronze_boundary']
    cfg_bool_keys = ['show_countries_for_guides', 'show_rooms_for_guides',
                     'paper_print_logo', 'paper_text_left',
                     'coord_form_print_logo', 'coord_form_text_left',
                     'honourable_mentions_available']
    config_data = read_config(config_file_name, 'matholymp.documentgen',
                              cfg_str_keys, cfg_int_keys,
                              cfg_int_none_keys, cfg_bool_keys)
    return config_data


class DocumentGenerator:

    """
    A DocumentGenerator supports generating documents for a particular
    EventGroup with associated configuration data.
    """

    def __init__(self, cfg, event, templates_dir, problems_dir, data_dir,
                 out_dir, print_tex_output):
        """
        Initialise a DocumentGenerator from the given configuration
        information, Event and directories.
        """
        self._cfg = cfg
        self._event = event
        self._templates_dir = templates_dir
        self._problems_dir = problems_dir
        self._data_dir = data_dir
        self._out_dir = out_dir
        self._cache_dir = os.path.join(out_dir, 'cache')
        self._cache_papers_tex_dir = os.path.join(self._cache_dir,
                                                  'papers-tex')
        self._cache_drafts_src_dir = os.path.join(self._cache_dir,
                                                  'drafts-src')
        self._cache_images_dir = os.path.join(self._cache_dir, 'images')
        self._cache_images_rel = os.path.join('cache', 'images')
        self._langs_num_pages = {}
        self._print_tex_output = print_tex_output

    def text_to_latex(self, text):
        """Convert text into a form suitable for LaTeX input."""
        special_chars = {'#': '\\#',
                         '$': '\\$',
                         '%': '\\%',
                         '&': '\\&',
                         '~': '\\~{ }',
                         '_': '\\_',
                         '^': '\\^{ }',
                         '\\': '$\\backslash$',
                         '{': '$\\{$',
                         '}': '$\\}$',
                         '"': '\\texttt{"}',
                         '|': '$|$',
                         '<': '$<$',
                         '>': '$>$'}
        text = re.sub('[\\000-\\037]', ' ', text)
        text = re.sub('[\\\\#$%&~_^{}"|<>]',
                      lambda x: special_chars[x.group(0)],
                      text)
        return text

    def field_to_latex(self, name, data, raw_fields):
        """Return the contents of a field, either raw or converted to LaTeX."""
        if name in raw_fields:
            return data[name]
        else:
            return self.text_to_latex(data[name])

    def hex_to_decimal_float(self, text):
        """Convert a two-digit hex value to a floating-point value."""
        return int(text, 16) / 255.0

    def colour_to_latex(self, colour):
        """Convert a hex RGB colour to a suitable form for LaTeX."""
        return '%.6f,%.6f,%.6f' % (self.hex_to_decimal_float(colour[:2]),
                                   self.hex_to_decimal_float(colour[2:4]),
                                   self.hex_to_decimal_float(colour[4:]))

    def subst_values_in_template_text(self, template_text, data, raw_fields):
        """Substitute values from a dictionary in a LaTeX template."""
        output_text = re.sub('@@([A-Za-z0-9_]+)@@',
                             lambda x: self.field_to_latex(x.group(1), data,
                                                           raw_fields),
                             template_text)
        return output_text

    def subst_values_in_template_file(self, template_file_name,
                                      output_file_name, data, raw_fields):
        """Substitute values from a dictionary in a LaTeX template file."""
        template_text = read_text_from_file(template_file_name)
        output_text = self.subst_values_in_template_text(template_text, data,
                                                         raw_fields)
        write_text_to_file(output_text, output_file_name)

    def pdflatex_file(self, output_file_name):
        """Run pdflatex on a (generated) LaTeX file."""
        env = dict(os.environ)
        latex_dirs = []
        if self._problems_dir is not None:
            # No problems directory is available for online document
            # generation from the registration system.
            latex_dirs.append(self._problems_dir)
        latex_dirs.append(self._templates_dir)
        latex_dirs.append('')
        env['TEXINPUTS'] = os.pathsep.join(latex_dirs)
        results = subprocess.run(  # pylint: disable=subprocess-run-check
            ['pdflatex', output_file_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self._out_dir,
            env=env)
        output = results.stdout.decode('ascii', errors='backslashreplace')
        if self._print_tex_output:
            print(output, end='')
        results.check_returncode()

    def pdflatex_cleanup(self, output_file_base):
        """Clean up .aux and .log files from running pdflatex."""
        remove_if_exists(os.path.join(self._out_dir,
                                      output_file_base + '.aux'))
        remove_if_exists(os.path.join(self._out_dir,
                                      output_file_base + '.log'))

    def subst_and_pdflatex(self, template_file_base, output_file_base,
                           data, raw_fields):
        """Substitute values from a dictionary in a LaTeX template file,
        run pdflatex and clean up afterwards."""
        template_file_name = os.path.join(self._templates_dir,
                                          template_file_base + '.tex')
        output_file_name = os.path.join(self._out_dir,
                                        output_file_base + '.tex')
        self.subst_values_in_template_file(template_file_name,
                                           output_file_name, data,
                                           raw_fields)
        self.pdflatex_file(output_file_name)
        self.pdflatex_cleanup(output_file_base)

    def get_person_by_id(self, person_id):
        """
        Given that the selected id must represent a valid person, return
        that person.
        """
        id_numeric = re.match('^[0-9]+\\Z', person_id)
        if person_id == '':
            raise ValueError('Empty person identifier')
        elif person_id in self._event.contestant_map:
            return self._event.contestant_map[person_id]
        elif id_numeric and int(person_id) in self._event.person_map:
            p = self._event.person_map[int(person_id)]
            if len(p) != 1:
                raise ValueError('Person %s present more than once')
            return p[0]
        else:
            raise ValueError('Person %s not found' % person_id)

    def get_contestant_by_id(self, person_id):
        """
        Given that the selected id must represent a valid contestant,
        return that person.
        """
        p = self.get_person_by_id(person_id)
        if not p.is_contestant:
            raise ValueError('Person %d not a contestant' % p.person.id)
        return p

    def adjust_image_path(self, filename, url, new_name):
        """Return a local path to an image with suitable filename extension."""
        url_ext = file_extension(url)
        if filename.endswith('.%s' % url_ext):
            return filename
        # Copy the file to a location with a known-good extension for
        # inclusion in LaTeX documents.  A relative path must be
        # returned to avoid problems when a random temporary directory
        # name includes '_'.
        cache_image_name_only = '%s.%s' % (new_name, url_ext)
        cache_image_name = os.path.join(self._cache_images_dir,
                                        cache_image_name_only)
        cache_image_rel = os.path.join(self._cache_images_rel,
                                       cache_image_name_only)
        if (os.access(cache_image_name, os.F_OK)
            and filecmp.cmp(filename, cache_image_name)):
            return cache_image_rel
        remove_if_exists(cache_image_name)
        make_dirs_for_file(cache_image_name)
        shutil.copyfile(filename, cache_image_name)
        return cache_image_rel

    def country_flag(self, country):
        """Return the local path to the flag for a given country, empty for a
        country given as None."""
        if country is None:
            return ''
        flag_filename = country.flag_filename
        if flag_filename is None:
            return ''
        return self.adjust_image_path(flag_filename, country.flag_url,
                                      'flag%d' % country.country.id)

    def room_list_text(self, person):
        """
        Return LaTeX text for one person's entry in a room list on a badge.
        """
        if person.is_contestant:
            code = person.contestant_code
        else:
            role = person.primary_role
            if role == 'Deputy Leader':
                role = 'Deputy'
            elif role == 'Observer with Leader':
                role = 'Observer A'
            elif role == 'Observer with Deputy':
                role = 'Observer B'
            elif role == 'Observer with Contestants':
                role = 'Observer C'
            code = person.country.code + ' ' + role
        name = person.name
        room = person.room_number or ''
        return (self.text_to_latex('(' + code + ') ' + name + ' ')
                + '\\textbf{' + self.text_to_latex(room) + '}')

    def role_text(self, person):
        """Return a listing of one person's roles."""
        primary_role = person.primary_role
        other_roles = sorted(person.other_roles, key=coll_get_sort_key)
        role = primary_role
        if person.is_contestant:
            role = 'Contestant ' + person.contestant_code
        if other_roles:
            role = role + ', ' + ', '.join(other_roles)
        return role

    def generate_badge(self, person, use_background):
        """Generate the badge for a particular person."""
        person_id = person.person.id
        template_file_base = 'badge-template'
        output_file_base = 'badge-person' + str(person_id)
        template_fields = {}
        raw_fields = ['team_rooms', 'event_ordinal']

        template_fields['phone_desc'] = self._cfg['badge_phone_desc']
        template_fields['event_phone'] = self._cfg['badge_event_phone']
        template_fields['emergency_phone'] = self._cfg['badge_emergency_phone']
        template_fields['event_ordinal'] = self._cfg['badge_event_ordinal']
        template_fields['event_short_name'] = self._event.short_name
        template_fields['event_venue'] = self._cfg['badge_event_venue']
        template_fields['event_dates'] = self._cfg['badge_event_dates']

        if use_background:
            template_fields['use_background'] = 'true'
        else:
            template_fields['use_background'] = 'false'

        role = self.role_text(person)
        template_fields['role'] = role

        template_fields['background_type'] = person.badge_background
        template_fields['colour_outer'] = self.colour_to_latex(
            person.badge_colour_outer)
        template_fields['colour_inner'] = self.colour_to_latex(
            person.badge_colour_inner)

        photo_filename = person.badge_photo_filename
        if photo_filename is None:
            template_fields['photo'] = ''
        else:
            template_fields['photo'] = self.adjust_image_path(
                photo_filename, person.badge_photo_url,
                'photo%d' % person_id)

        template_fields['name'] = person.name

        country = person.country
        if not country.is_normal:
            is_staff = True
            if (self._cfg['show_countries_for_guides']
                and person.guide_for):
                is_non_guide_staff = not self._cfg['show_rooms_for_guides']
                country_list = sorted(person.guide_for,
                                      key=lambda x: x.sort_key)
            else:
                is_non_guide_staff = True
                country_list = []
        else:
            is_staff = False
            is_non_guide_staff = False
            country_list = [country]

        if len(country_list) > 5:
            raise ValueError('Too many countries for person ' + str(person_id))
        else:
            clnew = [None for i in range(5 - len(country_list))]
            clnew.extend(country_list)
            country_list = clnew
        country_name_list = [c and c.name or '' for c in country_list]
        template_fields['countrye'] = country_name_list[0]
        template_fields['countryd'] = country_name_list[1]
        template_fields['countryc'] = country_name_list[2]
        template_fields['countryb'] = country_name_list[3]
        template_fields['countrya'] = country_name_list[4]
        country_flag_list = [self.country_flag(c) for c in country_list]
        template_fields['flage'] = country_flag_list[0]
        template_fields['flagd'] = country_flag_list[1]
        template_fields['flagc'] = country_flag_list[2]
        template_fields['flagb'] = country_flag_list[3]
        template_fields['flaga'] = country_flag_list[4]

        if is_staff:
            template_fields['guide_name'] = ''
            template_fields['guide_room'] = ''
            template_fields['guide_phone'] = ''
        else:
            guide_list = country.guide_list
            if len(guide_list) == 1:
                g = guide_list[0]
                template_fields['guide_name'] = g.name
                template_fields['guide_room'] = g.room_number or ''
                template_fields['guide_phone'] = g.phone_number or ''
            else:
                template_fields['guide_name'] = ''
                template_fields['guide_room'] = ''
                template_fields['guide_phone'] = ''

        template_fields['room'] = person.room_number or ''

        template_fields['diet'] = person.diet or ''

        if is_non_guide_staff:
            template_fields['have_team_rooms'] = 'false'
            template_fields['team_rooms'] = ''
        else:
            template_fields['have_team_rooms'] = 'true'
            room_list = [self.room_list_text(p)
                         for p in sorted(person.event.person_list,
                                         key=lambda x: x.sort_key)
                         if p.country in country_list]
            template_fields['team_rooms'] = ' \\\\ '.join(room_list)
            if template_fields['team_rooms'] == '':
                template_fields['have_team_rooms'] = 'false'

        self.subst_and_pdflatex(template_file_base, output_file_base,
                                template_fields, raw_fields)

    def generate_badges(self, person_id, use_background):
        """Generate all badges requested by the command line."""
        if person_id == 'all':
            for p in self._event.person_list:
                self.generate_badge(p, use_background)
        else:
            p = self.get_person_by_id(person_id)
            self.generate_badge(p, use_background)

    def generate_invitation_letter(self, person):
        """Generate the invitation letter for a particular person."""
        template_file_base = 'invitation-letter-template'
        template_fields = {'given_name': person.passport_given_name,
                           'family_name': person.passport_family_name,
                           'nationality': person.nationality or '',
                           'passport_number': person.passport_number or '',
                           'gender': person.gender or '',
                           'date_of_birth': date_to_name(person.date_of_birth)}
        output_file_base = 'invitation-letter-person' + str(person.person.id)
        self.subst_and_pdflatex(template_file_base, output_file_base,
                                template_fields, [])

    def generate_invitation_letters(self, person_id):
        """Generate all invitation letters requested by the command line."""
        if person_id == 'all':
            for p in self._event.person_list:
                self.generate_invitation_letter(p)
        else:
            p = self.get_person_by_id(person_id)
            self.generate_invitation_letter(p)

    def generate_desk_labels(self, person_id):
        """Generate all desk labels requested by the command line."""
        template_file_base = 'desk-label-template'
        if person_id == 'all':
            contestants = sorted(self._event.contestant_list,
                                 key=lambda x: x.sort_key_exams)
            output_file_base = 'desk-labels'
        else:
            p = self.get_contestant_by_id(person_id)
            contestants = [p]
            output_file_base = 'desk-label-person' + person_id
        label_list = [('\\placecard{%s}{%s}{%s}{%s}'
                       % (self.text_to_latex(p.contestant_code),
                          self.text_to_latex(p.name),
                          self.text_to_latex(p.languages[0]
                                             if p.languages
                                             else ''),
                          self.text_to_latex(p.languages[1]
                                             if len(p.languages) > 1
                                             else '')))
                      for p in contestants]
        label_list_text = '%\n'.join(label_list)
        template_fields = {'desk_labels': label_list_text}
        raw_fields = ['desk_labels']
        self.subst_and_pdflatex(template_file_base, output_file_base,
                                template_fields, raw_fields)

    def generate_award_certs(self, person_id, use_background):
        """Generate all award certificates requested by the command line."""
        template_file_base = 'certificate-template'
        contestants = sorted(self._event.contestant_list,
                             key=lambda x: x.sort_key)
        if person_id == 'gold':
            contestants = [p for p in contestants if p.award == 'Gold Medal']
            output_file_base = 'gold-certificates'
        elif person_id == 'silver':
            contestants = [p for p in contestants if p.award == 'Silver Medal']
            output_file_base = 'silver-certificates'
        elif person_id == 'bronze':
            contestants = [p for p in contestants if p.award == 'Bronze Medal']
            output_file_base = 'bronze-certificates'
        elif person_id == 'hm':
            contestants = [p for p in contestants
                           if p.award == 'Honourable Mention']
            output_file_base = 'hm-certificates'
        else:
            p = self.get_contestant_by_id(person_id)
            if not p.award:
                raise ValueError('Person %s not awarded' % person_id)
            contestants = [p]
            output_file_base = 'certificate-person' + person_id
        award_map = {'Gold Medal': 'gold',
                     'Silver Medal': 'silver',
                     'Bronze Medal': 'bronze',
                     'Honourable Mention': 'hm'}
        cert_list = [('\\%scert{%s}{%s}'
                      % (award_map[p.award],
                         self.text_to_latex(p.name),
                         self.text_to_latex(p.country.name)))
                     for p in contestants]
        cert_list_text = '%\n'.join(cert_list)
        template_fields = {'certificates': cert_list_text}
        if use_background:
            template_fields['use_background'] = 'true'
        else:
            template_fields['use_background'] = 'false'
        raw_fields = ['certificates']
        self.subst_and_pdflatex(template_file_base, output_file_base,
                                template_fields, raw_fields)

    def generate_part_certs(self, person_id, use_background):
        """
        Generate all participation certificates requested by the command line.
        """
        template_file_base = 'certificate-template'
        if person_id == 'all':
            people = sorted(self._event.person_list, key=lambda x: x.sort_key)
            output_file_base = 'participation-certificates'
        else:
            p = self.get_person_by_id(person_id)
            people = [p]
            output_file_base = 'participation-certificate-person' + person_id
        cert_list = [('\\partcert{%s}{%s}{%s}'
                      % (self.text_to_latex(p.name),
                         self.text_to_latex(p.country.name),
                         self.role_text(p))) for p in people]
        cert_list_text = '%\n'.join(cert_list)
        template_fields = {'certificates': cert_list_text}
        if use_background:
            template_fields['use_background'] = 'true'
        else:
            template_fields['use_background'] = 'false'
        raw_fields = ['certificates']
        self.subst_and_pdflatex(template_file_base, output_file_base,
                                template_fields, raw_fields)

    def get_paper_pdf(self, lang_filename_day):
        """
        Return the filename for the PDF version of a paper, generating
        it first if necessary.
        """
        pdf_file_name = lang_filename_day + '.pdf'
        tex_file_name = lang_filename_day + '.tex'
        papers_dir_pdf_name = os.path.join(self._problems_dir, pdf_file_name)
        papers_dir_tex_name = os.path.join(self._problems_dir, tex_file_name)
        cache_pdf_name = os.path.join(self._out_dir, pdf_file_name)
        cache_tex_name = os.path.join(self._cache_papers_tex_dir,
                                      tex_file_name)
        if os.access(papers_dir_pdf_name, os.F_OK):
            remove_if_exists(cache_pdf_name)
            remove_if_exists(cache_tex_name)
            return papers_dir_pdf_name
        if not os.access(papers_dir_tex_name, os.F_OK):
            raise IOError('PDF or TeX for %s not found' % lang_filename_day)
        if (os.access(cache_tex_name, os.F_OK)
            and os.access(cache_pdf_name, os.F_OK)
            and filecmp.cmp(papers_dir_tex_name, cache_tex_name)):
            return cache_pdf_name
        remove_if_exists(cache_pdf_name)
        remove_if_exists(cache_tex_name)
        make_dirs_for_file(cache_pdf_name)
        self.pdflatex_file(tex_file_name)
        self.pdflatex_cleanup(os.path.join(self._out_dir, lang_filename_day))
        make_dirs_for_file(cache_tex_name)
        shutil.copyfile(papers_dir_tex_name, cache_tex_name)
        return cache_pdf_name

    def new_paper(self, lang_filename_day):
        """
        If a version of the paper for the given language and day is
        available, and has not yet had a draft generated for it,
        return a tuple of the source filename and the filename to use
        for a cached copy; otherwise, return (None, None).
        """
        pdf_file_name = lang_filename_day + '.pdf'
        tex_file_name = lang_filename_day + '.tex'
        src_pdf_name = os.path.join(self._problems_dir, pdf_file_name)
        src_tex_name = os.path.join(self._problems_dir, tex_file_name)
        dst_name = os.path.join(self._cache_drafts_src_dir, lang_filename_day)
        if os.access(src_pdf_name, os.F_OK):
            src_name = src_pdf_name
        elif os.access(src_tex_name, os.F_OK):
            src_name = src_tex_name
        else:
            return (None, None)
        if os.access(dst_name, os.F_OK) and filecmp.cmp(src_name, dst_name):
            return (None, None)
        return (src_name, dst_name)

    def one_paper_latex(self, lang_filename, lang, day, desc, code):
        """Generate the LaTeX fragment for a single paper."""
        if day:
            lang_filename_day = lang_filename + '-day' + day
        else:
            lang_filename_day = lang_filename
        if lang_filename_day not in self._langs_num_pages:
            pdf_file = open(self.get_paper_pdf(lang_filename_day), 'rb')
            r = PdfFileReader(pdf_file)
            self._langs_num_pages[lang_filename_day] = r.getNumPages()
            pdf_file.close()
        npages = self._langs_num_pages[lang_filename_day]
        if npages == 1:
            return ('\\onepaper{%s}{%s}{%s}{%s}{%s}{}{1}'
                    % (lang_filename_day, self.text_to_latex(lang), day,
                       self.text_to_latex(desc), self.text_to_latex(code)))
        else:
            pages_list = []
            for n in range(1, npages + 1):
                paper = ('\\onepaper{%s}{%s}{%s}{%s}{%s}{%d}{%d}'
                         % (lang_filename_day, self.text_to_latex(lang), day,
                            self.text_to_latex(desc),
                            self.text_to_latex(code), n, npages))
                pages_list.append(paper)
            return '%\n'.join(pages_list)

    def generate_papers(self, person_id, day_opt, use_background):
        """Generate all papers requested by the command line."""
        template_file_base = 'paper-template'

        template_fields = {}
        template_fields['year'] = self._event.year
        template_fields['short_name'] = self._event.short_name
        template_fields['long_name'] = self._event.long_name
        if use_background:
            template_fields['use_background'] = 'true'
        else:
            template_fields['use_background'] = 'false'
        if self._cfg['paper_print_logo']:
            template_fields['print_logo'] = 'true'
        else:
            template_fields['print_logo'] = 'false'
        if self._cfg['paper_text_left']:
            template_fields['text_left'] = 'true'
        else:
            template_fields['text_left'] = 'false'
        raw_fields = ['papers']

        if day_opt:
            days = [day_opt]
            day_text = '-day' + day_opt
        elif self._event.num_exams == 1:
            days = ['']
            day_text = ''
        else:
            days = [str(i + 1) for i in range(self._event.num_exams)]
            day_text = ''

        all_languages = sorted(self._event.language_list,
                               key=coll_get_sort_key)
        lang_filenames = {}
        for lang in all_languages:
            lang_filenames[lang_to_filename(lang)] = lang

        new_drafts_only = False
        if person_id == 'all':
            contestants = self._event.contestant_list
            contestants = sorted(contestants, key=lambda x: x.sort_key_exams)
            languages = []
            output_file_base = 'papers' + day_text
        elif person_id == 'all-languages':
            contestants = []
            languages = all_languages
            paper_draft = ''
            draft_text = ''
        elif person_id == 'new-drafts':
            contestants = []
            languages = all_languages
            new_drafts_only = True
            paper_draft = 'Draft'
            draft_text = '-draft'
        elif person_id in lang_filenames:
            contestants = []
            languages = [lang_filenames[person_id]]
            paper_draft = 'Draft'
            draft_text = '-draft'
        else:
            p = self.get_contestant_by_id(person_id)
            contestants = [p]
            languages = []
            output_file_base = 'paper' + day_text + '-person' + person_id

        if languages:
            for d in days:
                if d:
                    day_text = '-day' + d
                else:
                    day_text = ''
                paper_list = []
                if use_background:
                    bg_text = '-bg'
                else:
                    bg_text = ''
                for lang in languages:
                    lang_filename = lang_to_filename(lang)
                    do_this_paper = True
                    new_paper_src = None
                    new_paper_dst = None
                    if new_drafts_only:
                        new_paper = self.new_paper(lang_filename + day_text)
                        new_paper_src = new_paper[0]
                        new_paper_dst = new_paper[1]
                        if new_paper_src is None:
                            do_this_paper = False
                    if do_this_paper:
                        output_file_base = ('paper' + day_text + draft_text
                                            + bg_text + '-' + lang_filename)
                        paper_text = self.one_paper_latex(lang_filename, lang,
                                                          d, paper_draft, '')
                        paper_list.append(paper_text)
                        template_fields['papers'] = paper_text
                        self.subst_and_pdflatex(template_file_base,
                                                output_file_base,
                                                template_fields, raw_fields)
                        if new_paper_src is not None:
                            make_dirs_for_file(new_paper_dst)
                            shutil.copyfile(new_paper_src, new_paper_dst)
                if person_id == 'all-languages':
                    output_file_base = ('paper' + day_text + draft_text
                                        + bg_text + '-All')
                    paper_list_text = '%\n'.join(paper_list)
                    template_fields['papers'] = paper_list_text
                    self.subst_and_pdflatex(template_file_base,
                                            output_file_base, template_fields,
                                            raw_fields)
        else:
            country_langs = {}
            paper_list = []
            for d in days:
                for p in contestants:
                    ccode = p.contestant_code
                    lang_list = p.languages
                    for lang in lang_list:
                        lang_filename = lang_to_filename(lang)
                        paper_text = self.one_paper_latex(lang_filename,
                                                          lang, d,
                                                          'Contestant: ',
                                                          ccode)
                        paper_list.append(paper_text)
                    country_code = p.country.code
                    if country_code not in country_langs:
                        country_langs[country_code] = list(lang_list)
                    else:
                        for lang in lang_list:
                            if lang not in country_langs[country_code]:
                                country_langs[country_code].append(lang)

            paper_list_text = '%\n'.join(paper_list)
            template_fields['papers'] = paper_list_text
            self.subst_and_pdflatex(template_file_base, output_file_base,
                                    template_fields, raw_fields)
            if person_id == 'all':
                leader_roles = ('Leader', 'Observer with Leader')
                for kind in ('leaders', 'deputies'):
                    output_file_base = 'papers-%s%s' % (kind, day_text)
                    country_leader_counts = {}
                    for p in self._event.person_list:
                        if p.country.code not in country_leader_counts:
                            country_leader_counts[p.country.code] = 0
                        if not p.is_contestant:
                            is_leader = p.primary_role in leader_roles
                            if is_leader == (kind == 'leaders'):
                                country_leader_counts[p.country.code] += 1
                    paper_list = []
                    for d in days:
                        for c in sorted(country_langs.keys(),
                                        key=coll_get_sort_key):
                            if 'English' not in country_langs[c]:
                                country_langs[c].append('English')
                            country_langs[c].sort(key=coll_get_sort_key)
                            for dummy in range(country_leader_counts[c]):
                                for lang in country_langs[c]:
                                    lang_filename = lang_to_filename(lang)
                                    paper_text = self.one_paper_latex(
                                        lang_filename, lang, d,
                                        '%s: ' % kind.capitalize(), c)
                                    paper_list.append(paper_text)
                    paper_list_text = '%\n'.join(paper_list)
                    template_fields['papers'] = paper_list_text
                    self.subst_and_pdflatex(template_file_base,
                                            output_file_base, template_fields,
                                            raw_fields)

    def generate_language_list(self):
        """Generate a list of languages and the contestants using them."""

        all_languages = {}
        one_language_contestants = []
        for p in sorted(self._event.contestant_list, key=lambda x: x.sort_key):
            ccode = p.contestant_code
            for lang in p.languages:
                if lang not in all_languages:
                    all_languages[lang] = []
                all_languages[lang].append(ccode)
            if len(p.languages) <= 1:
                one_language_contestants.append(ccode)
        lang_text_list = []
        for lang in sorted(all_languages, key=coll_get_sort_key):
            code_list = ' '.join(all_languages[lang])
            lang_text_list.append(lang + ' ' + code_list)
        out_text = '\n'.join(lang_text_list) + '\n'
        out_text += ('\nOnly one language: '
                     + ' '.join(one_language_contestants))
        out_text += '\n'
        write_text_to_file(out_text, os.path.join(self._out_dir,
                                                  'language-list.txt'))

    def generate_coord_forms(self, use_background):
        """Generate all coordination forms requested by the command line."""
        template_file_base = 'coord-form-template'
        form_list = []
        output_file_base = 'coord-forms'
        for pn in range(1, self._event.num_problems + 1):
            for c in sorted(self._event.country_list,
                            key=lambda x: x.sort_key):
                contestants = c.contestant_list
                if contestants:
                    clist = []
                    for n in range(1,
                                   self._cfg['num_contestants_per_team'] + 1):
                        ccode = c.code + str(n)
                        cext = [p for p in contestants
                                if p.contestant_code == ccode]
                        if cext:
                            clist.append(ccode)
                        else:
                            clist.append('')
                    ctext_conts = ''.join([('\\formrow{%s}'
                                            % self.text_to_latex(cl))
                                           for cl in clist])
                    ctext = ('\\twoforms{%s}{%d}{%s}'
                             % (self.text_to_latex(c.name), pn, ctext_conts))
                    form_list.append(ctext)
        form_list_text = '%\n'.join(form_list)
        template_fields = {'coord_forms': form_list_text}
        template_fields['year'] = self._event.year
        template_fields['short_name'] = self._event.short_name
        template_fields['long_name'] = self._event.long_name
        if use_background:
            template_fields['use_background'] = 'true'
        else:
            template_fields['use_background'] = 'false'
        if self._cfg['coord_form_print_logo']:
            template_fields['print_logo'] = 'true'
        else:
            template_fields['print_logo'] = 'false'
        if self._cfg['coord_form_text_left']:
            template_fields['text_left'] = 'true'
        else:
            template_fields['text_left'] = 'false'
        raw_fields = ['coord_forms']
        self.subst_and_pdflatex(template_file_base, output_file_base,
                                template_fields, raw_fields)

    def generate_scores_commands(self):
        """Generate commands to upload scores in bulk."""

        out_text = ''
        out_text += '#! /bin/sh\n'
        out_text += ('# Run as: sh upload-scores path-to-roundup-admin '
                     'path-to-instance\n')
        out_text += 'roundup_admin=$1\n'
        out_text += 'instance=$2\n'
        scores_data = read_utf8_csv(os.path.join(self._data_dir,
                                                 'scores-in.csv'))
        out_text_list = []
        for p in scores_data:
            ccode = p['Contestant Code']
            if ccode:
                person_id = self._event.contestant_map[ccode].person.id
                scores = []
                for pn in range(1, self._event.num_problems + 1):
                    pnstr = 'P%d' % pn
                    scores.append(p[pnstr])
                scores_text = ','.join(scores)
                cmd = ('$roundup_admin -i $instance set person%d scores=%s'
                       % (person_id, scores_text))
                out_text_list.append(cmd)
        out_text += '\n'.join(out_text_list) + '\n'
        write_text_to_file(out_text, os.path.join(self._out_dir,
                                                  'upload-scores'))
