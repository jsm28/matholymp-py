# Actions for Roundup registration system for matholymp package.

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

"""This module provides actions for the Roundup registration system."""

__all__ = ['ScoreAction', 'RetireCountryAction', 'ScalePhotoAction',
           'CountryCSVAction', 'ScoresCSVAction', 'PeopleCSVAction',
           'MedalBoundariesCSVAction', 'FlagsZIPAction', 'PhotosZIPAction',
           'ScoresRSSAction', 'DocumentGenerateAction', 'NameBadgeAction',
           'InvitationLetterAction', 'BulkRegisterAction',
           'CountryBulkRegisterAction', 'PersonBulkRegisterAction',
           'register_actions']

import collections
import html
import io
import os
import os.path
import subprocess
import tempfile

from PIL import Image
from roundup.cgi.actions import Action
from roundup.cgi.exceptions import Unauthorised
from roundup.exceptions import Reject
import roundup.password

from matholymp.data import EventGroup
from matholymp.docgen import read_docgen_config, DocumentGenerator
from matholymp.fileutil import read_text_from_file, boolean_states
from matholymp.roundupreg.auditors import audit_country_fields, \
    audit_person_fields
from matholymp.roundupreg.roundupemail import send_email
from matholymp.roundupreg.roundupsitegen import RoundupSiteGenerator
from matholymp.roundupreg.roundupsource import RoundupDataSource
from matholymp.roundupreg.rounduputil import distinguish_official, \
    get_marks_per_problem, scores_from_str, person_is_contestant, \
    contestant_code, scores_final, valid_country_problem, valid_int_str, \
    create_rss, bulk_csv_data, bulk_csv_contact_emails, \
    bulk_csv_country_number_url, bulk_csv_person_number_url, country_from_code
from matholymp.roundupreg.userauditor import valid_address


class ScoreAction(Action):

    """Action to enter scores."""

    name = 'enter scores for'
    permissionType = 'Score'

    def handle(self):
        """Set the scores for a given country and problem."""
        if self.client.env['REQUEST_METHOD'] != 'POST':
            raise Reject(self._('Invalid request'))
        if scores_final(self.db):
            raise Unauthorised('Scores cannot be entered after'
                               ' medal boundaries are set')
        if self.db.event.get('1', 'registration_enabled'):
            raise Unauthorised('Registration must be disabled before'
                               ' scores are entered')
        if self.classname != 'person':
            raise ValueError('Scores can only be entered for people')
        if self.nodeid is not None:
            raise ValueError('Node id specified when entering scores')
        if not valid_country_problem(self.db, self.form):
            raise ValueError('Country or problem invalid or not specified')
        country = self.form['country'].value
        problem = self.form['problem'].value
        country_node = self.db.country.getnode(country)
        problem_number = int(problem)
        marks_per_problem = get_marks_per_problem(self.db)
        max_this_problem = marks_per_problem[problem_number - 1]
        results_list = []
        people = self.db.person.filter(None, {'country': country})
        for person in people:
            if person_is_contestant(self.db, person):
                code = contestant_code(self.db, person)
                if code not in self.form:
                    raise ValueError('No score specified for ' + code)
                score = self.form[code].value
                if score != '' and not valid_int_str(score, max_this_problem):
                    raise ValueError('Invalid score specified for ' + code)
                score_str = self.db.person.get(person, 'scores')
                scores = scores_from_str(self.db, score_str)
                scores[problem_number - 1] = score
                new_scores = ','.join(scores)
                self.db.person.set(person, scores=new_scores)
                results_text = code + ' = ' + score
                if score == '':
                    results_text += '?'
                results_list.append(results_text)
        results_list = sorted(results_list)
        title_text = country_node.code + ' P' + problem
        full_results_text = title_text + ': ' + ', '.join(results_list)
        create_rss(self.db, title_text, full_results_text, country=country)
        self.client.add_ok_message('Scores entered for %s problem %s'
                                   % (country_node.name, problem))
        self.db.commit()


class RetireCountryAction(Action):

    """Action to retire a country."""

    name = 'retire'
    permissionType = 'Edit'

    def handle(self):
        """Retire a country, making other consequent changes."""
        if self.client.env['REQUEST_METHOD'] != 'POST':
            raise Reject(self._('Invalid request'))
        if self.nodeid is None:
            raise ValueError('No id specified to retire')
        if self.classname != 'country':
            raise ValueError('This action only applies to countries')
        if not self.hasPermission('Retire', classname=self.classname,
                                  itemid=self.nodeid):
            raise Unauthorised('You do not have permission to retire'
                               ' this country')
        if not self.db.country.get(self.nodeid, 'is_normal'):
            raise Unauthorised('Special countries cannot be retired')
        users = self.db.user.filter(None, {'country': self.nodeid})
        people = self.db.person.filter(None, {'country': self.nodeid})
        guides = self.db.person.filter(None, {'guide_for': self.nodeid})
        for u in users:
            self.db.user.retire(u)
        for p in people:
            self.db.person.retire(p)
        for g in guides:
            guide_for = self.db.person.get(g, 'guide_for')
            guide_for = [gf for gf in guide_for if gf != self.nodeid]
            self.db.person.set(g, guide_for=guide_for)
        self.db.country.retire(self.nodeid)
        self.db.commit()


class ScalePhotoAction(Action):

    """Action to scale a person's photo to make the file size smaller."""

    name = 'scale the photo for'
    permissionType = 'EditPhotos'

    def handle(self):
        """Scale a person's photo."""
        if self.client.env['REQUEST_METHOD'] != 'POST':
            raise Reject(self._('Invalid request'))
        if self.nodeid is None:
            raise ValueError('No id specified to scale photo for')
        if self.classname != 'person':
            raise ValueError('Photos can only be scaled for people')
        photo_id = self.db.person.get(self.nodeid, 'photo')
        if not photo_id:
            raise ValueError('This person has no photo to scale')
        filename = self.db.filename('photo', photo_id)
        max_size_bytes = int(self.db.config.ext['MATHOLYMP_PHOTO_MAX_SIZE'])
        min_photo_dimen = int(self.db.config.ext['MATHOLYMP_PHOTO_MIN_DIMEN'])
        cur_size_bytes = os.stat(filename).st_size
        if cur_size_bytes <= max_size_bytes:
            raise ValueError('This photo is already small enough')
        photo_orig = Image.open(filename)
        if photo_orig.mode not in ('RGB', 'L'):
            # Convert to RGB, removing any alpha channel.
            if (photo_orig.mode in ('RGBA', 'LA')
                or (photo_orig.mode == 'P'
                    and 'transparency' in photo_orig.info)):
                photo_orig = photo_orig.convert('RGBA')
                background = Image.new('RGBA', photo_orig.size,
                                       (255, 255, 255, 255))
                photo_orig = Image.alpha_composite(background, photo_orig)
            photo_orig = photo_orig.convert('RGB')
        size_xy = photo_orig.size
        scale_factor = 1
        while size_xy[0] >= min_photo_dimen and size_xy[1] >= min_photo_dimen:
            photo_scaled = photo_orig.resize(size_xy, Image.LANCZOS)
            photo_out = io.BytesIO()
            photo_scaled.save(photo_out, format='JPEG', quality=90)
            photo_bytes = photo_out.getvalue()
            photo_out.close()
            if len(photo_bytes) <= max_size_bytes:
                photo_data = {'name': 'photo-smaller.jpg',
                              'type': 'image/jpeg',
                              'content': photo_bytes}
                new_photo_id = self.db.photo.create(**photo_data)
                self.db.person.set(self.nodeid, photo=new_photo_id)
                self.db.commit()
                self.client.add_ok_message('Photo reduced in size, '
                                           'scaled down by %d' % scale_factor)
                return
            size_xy = (size_xy[0] // 2, size_xy[1] // 2)
            scale_factor *= 2
        raise ValueError('Could not make this photo small enough')


class CountryCSVAction(Action):

    """Action to return a CSV file of countries."""

    def handle(self):
        """Output the list of countries as a CSV file."""
        if self.classname != 'country':
            raise ValueError('This action only applies to countries')
        if self.nodeid is not None:
            raise ValueError('Node id specified for CSV generation')
        self.client.setHeader('Content-Type', 'text/csv; charset=UTF-8')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=countries.csv')
        show_all = self.hasPermission('Omnivident')
        return RoundupSiteGenerator(self.db).countries_csv_bytes(show_all)


class ScoresCSVAction(Action):

    """Action to return a CSV file of scores."""

    def handle(self):
        """Output the scores as a CSV file."""
        if self.classname != 'person':
            raise ValueError('This action only applies to people')
        if self.nodeid is not None:
            raise ValueError('Node id specified for CSV generation')
        self.client.setHeader('Content-Type', 'text/csv; charset=UTF-8')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=scores.csv')
        return RoundupSiteGenerator(self.db).scores_csv_bytes()


class PeopleCSVAction(Action):

    """Action to return a CSV file of people."""

    def handle(self):
        """Output the list of people as a CSV file."""
        if self.classname != 'person':
            raise ValueError('This action only applies to people')
        if self.nodeid is not None:
            raise ValueError('Node id specified for CSV generation')
        self.client.setHeader('Content-Type', 'text/csv; charset=UTF-8')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=people.csv')
        show_all = self.hasPermission('Omnivident')
        return RoundupSiteGenerator(self.db).people_csv_bytes(show_all)


class MedalBoundariesCSVAction(Action):

    """Action to return a CSV file of medal boundaries."""

    def handle(self):
        """Output the medal boundaries as a CSV file."""
        if self.classname != 'event':
            raise ValueError('This action only applies to events')
        if self.nodeid is not None:
            raise ValueError('Node id specified for CSV generation')
        self.client.setHeader('Content-Type', 'text/csv; charset=UTF-8')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=medal-boundaries.csv')
        return RoundupSiteGenerator(self.db).medal_boundaries_csv_bytes()


class FlagsZIPAction(Action):

    """Action to return a ZIP file of flags."""

    def handle(self):
        """Output a ZIP file of flags of registered countries."""
        if self.classname != 'country':
            raise ValueError('This action only applies to countries')
        if self.nodeid is not None:
            raise ValueError('Node id specified for ZIP generation')
        self.client.setHeader('Content-Type', 'application/zip')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=flags.zip')
        return RoundupSiteGenerator(self.db).flags_zip_bytes()


class PhotosZIPAction(Action):

    """Action to return a ZIP file of photos."""

    def handle(self):
        """Output a ZIP file of photos of registered participants."""
        if self.classname != 'person':
            raise ValueError('This action only applies to people')
        if self.nodeid is not None:
            raise ValueError('Node id specified for ZIP generation')
        self.client.setHeader('Content-Type', 'application/zip')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=photos.zip')
        badge_photos = self.hasPermission('Omnivident')
        return RoundupSiteGenerator(self.db).photos_zip_bytes(badge_photos)


class ConsentFormsZIPAction(Action):

    """Action to return a ZIP file of consent forms."""

    def handle(self):
        """Output a ZIP file of consent forms of registered participants."""
        if self.classname != 'person':
            raise ValueError('This action only applies to people')
        if self.nodeid is not None:
            raise ValueError('Node id specified for ZIP generation')
        if not self.hasPermission('Omnivident'):
            raise Unauthorised('You do not have permission to access '
                               'consent forms')
        self.client.setHeader('Content-Type', 'application/zip')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=consent-forms.zip')
        return RoundupSiteGenerator(self.db).consent_forms_zip_bytes()


class ScoresRSSAction(Action):

    """Action to return an RSS feed of scores."""

    def handle(self):
        """Output the RSS feed for scores."""
        if self.classname != 'country':
            raise ValueError('This action only applies to countries')

        self.client.setHeader('Content-Type', 'application/rss+xml')

        if self.nodeid is None:
            title_extra = ''
            link_url = self.base + 'person?@template=scoreboard'
            url_id = ''
        else:
            title_extra = ' ' + self.db.country.get(self.nodeid, 'name')
            link_url = self.base + 'country' + self.nodeid
            url_id = self.nodeid

        short_name = self.db.config.ext['MATHOLYMP_SHORT_NAME']
        year = self.db.config.ext['MATHOLYMP_YEAR']
        text = '<?xml version="1.0"?>\n'
        text += ('<rss version="2.0"'
                 ' xmlns:atom="http://www.w3.org/2005/Atom">\n')
        text += '  <channel>\n'
        text += ('    <title>%s %s%s Scores</title>\n'
                 % (html.escape(short_name), html.escape(year),
                    html.escape(title_extra)))
        text += '    <link>%s</link>\n' % link_url
        text += ('    <description>%s %s%s Scores Live Feed</description>\n'
                 % (html.escape(short_name), html.escape(year),
                    html.escape(title_extra)))
        text += '    <language>en-gb</language>\n'
        text += '    <docs>http://www.rssboard.org/rss-specification</docs>\n'
        text += ('    <atom:link href="%s" rel="self"'
                 ' type="application/rss+xml" />\n    '
                 % html.escape((self.base + 'country' + url_id
                                + '?@action=scores_rss')))

        rss_list = self.db.rss.list()
        rss_list = sorted(rss_list, key=int, reverse=True)
        rss_text_list = [self.db.rss.get(r, 'text')
                         for r in rss_list
                         if (self.nodeid is None
                             or self.db.rss.get(r, 'country') is None
                             or self.db.rss.get(r, 'country') == self.nodeid)]
        text += '\n    '.join(rss_text_list)

        text += '\n  </channel>\n</rss>\n'
        return text


class DocumentGenerateAction(Action):

    """Base class for document generation actions."""

    # Subclasses must set this.
    required_classname = None

    def generate_document(self, docgen, event):
        """Do the actual document generation."""
        raise NotImplementedError

    def document_filename(self):
        """Return the filename of the generated PDF document."""
        raise NotImplementedError

    def handle(self):
        """Generate a document."""
        if self.classname != self.required_classname:
            raise ValueError('Invalid class for document generation')
        if self.nodeid is None:
            raise ValueError('No id specified for document generation')
        docgen_path = self.db.config.ext['MATHOLYMP_DOCGEN_DIRECTORY']
        if not docgen_path:
            raise ValueError('Online document generation not enabled')
        docgen_path = os.path.join(self.db.config.TRACKER_HOME, docgen_path)
        event_group = EventGroup(RoundupDataSource(self.db))
        event = event_group.event_list[0]
        config_data = read_docgen_config(docgen_path)
        with tempfile.TemporaryDirectory() as temp_dir:
            docgen = DocumentGenerator(config_data, event,
                                       os.path.join(docgen_path, 'templates'),
                                       None, None, temp_dir, False)
            try:
                self.generate_document(docgen, event)
                doc_filename = self.document_filename()
                self.client.setHeader('Content-Type', 'application/pdf')
                self.client.setHeader('Content-Disposition',
                                      'attachment; filename=%s'
                                      % doc_filename)
                doc_path = os.path.join(temp_dir, doc_filename)
                with open(doc_path, 'rb') as doc_file:
                    return doc_file.read()
            except subprocess.CalledProcessError as e:
                # Report this error both to the admin and to the web
                # client.
                msg_text = ('LaTeX errors:\n\n%s\n'
                            % e.stdout.decode('utf-8',
                                              errors='backslashreplace'))
                send_email(self.db, [],
                           ('Document generation error for %s %s'
                            % (self.classname, self.nodeid)),
                           msg_text, 'docgen')
                self.client.setHeader('Content-Type',
                                      'text/plain; charset=UTF-8')
                return e.stdout


class NameBadgeAction(DocumentGenerateAction):

    """Action to generate a person's name badge."""

    name = 'generate the name badge for'
    permissionType = 'GenerateNameBadges'
    required_classname = 'person'

    def generate_document(self, docgen, event):
        person = event.person_map[int(self.nodeid)][0]
        use_background = self.db.config.ext['MATHOLYMP_BADGE_USE_BACKGROUND']
        use_background = boolean_states[use_background.lower()]
        docgen.generate_badge(person, use_background)

    def document_filename(self):
        return 'badge-person%s.pdf' % self.nodeid


class InvitationLetterAction(DocumentGenerateAction):

    """Action to generate a person's invitation letter."""

    name = 'generate the invitation letter for'
    permissionType = 'GenerateInvitationLetters'
    required_classname = 'person'

    def generate_document(self, docgen, event):
        docgen.generate_invitation_letter(self.nodeid)

    def document_filename(self):
        return 'invitation-letter-person%s.pdf' % self.nodeid


class BulkRegisterAction(Action):

    """Base class for bulk registration actions."""

    # Subclasses must set this.
    required_classname = None

    @staticmethod
    def auditor(db, cl, nodeid, newvalues):
        """Check validity of proposed item creation."""
        raise NotImplementedError

    def handle(self):
        """Bulk register or check bulk registration data."""
        if self.client.env['REQUEST_METHOD'] != 'POST':
            raise Reject(self._('Invalid request'))
        if self.classname != self.required_classname:
            raise ValueError('Invalid class for bulk registration')
        if self.nodeid is not None:
            raise ValueError('Node id specified for bulk registration')
        csv_data = bulk_csv_data(self.form, self.get_comma_sep_columns())
        if isinstance(csv_data, str):
            self.client.add_error_message(csv_data)
            return
        file_data, check_only = csv_data
        # Verify the rows individually, generating corresponding data
        # for subsequent item creation.
        required_columns = self.get_required_columns()
        unique_columns = self.get_unique_columns()
        unique_vals = collections.defaultdict(set)
        default_values = self.get_default_values()
        str_column_map = self.get_str_column_map()
        bool_column_map = self.get_bool_column_map()
        item_class = self.db.getclass(self.classname)
        item_data = []
        for row_num, row in enumerate(file_data, start=1):
            for key in required_columns:
                if key not in row:
                    self.client.add_error_message(
                        "'%s' missing in row %d" % (key, row_num))
                    return
            for key in unique_columns:
                if key in row:
                    if row[key] in unique_vals[key]:
                        self.client.add_error_message(
                            "'%s' duplicate value in row %d" % (key, row_num))
                        return
                    unique_vals[key].add(row[key])
            newvalues = default_values.copy()
            for key in str_column_map:
                if key in row:
                    newvalues[str_column_map[key]] = row[key]
            for key in bool_column_map:
                if key in row:
                    try:
                        bool_val = boolean_states[row[key].lower()]
                    except KeyError:
                        self.client.add_error_message(
                            "'%s' bad value in row %d" % (key, row_num))
                        return
                    newvalues[bool_column_map[key]] = bool_val
            try:
                self.map_csv_data(row, newvalues)
                # Run the auditor for each item at this point to
                # detect errors early and avoid possibly confusing
                # effects of errors after some items have been
                # created.
                self.auditor(self.db, item_class, None, newvalues)
                self.adjust_after_audit(row, newvalues)
            except ValueError as exc:
                self.client.add_error_message('row %d: %s'
                                              % (row_num, str(exc)))
                return
            item_data.append(newvalues)
        if check_only:
            self.client.template = 'bulkconfirm'
        else:
            self.client.template = 'index'
            for csv_row, item in zip(file_data, item_data):
                item_id = item_class.create(**item)
                self.db.commit()
                self.client.add_ok_message('%s%s created'
                                           % (self.classname, item_id))
                self.act_after_create(item_id, item, csv_row)

    def get_required_columns(self):
        """Return the list of columns that must have nonempty values."""
        return ()

    def get_unique_columns(self):
        """Return the list of columns that must have unique values."""
        return ()

    def get_default_values(self):
        """Return default property values."""
        return {}

    def get_str_column_map(self):
        """Return the mapping of string column names to property names."""
        return {}

    def get_bool_column_map(self):
        """Return the mapping of boolean column names to property names."""
        return {}

    def get_comma_sep_columns(self):
        """Return the list of columns with comma-separated values."""
        return ()

    def map_csv_data(self, row, newvalues):
        """Convert CSV data into item properties in class-specific way."""

    def adjust_after_audit(self, row, newvalues):
        """Adjust item properties after call to auditor."""

    def act_after_create(self, item_id, item, csv_row):
        """Act after the creation of a new item."""


class CountryBulkRegisterAction(BulkRegisterAction):

    """Action to bulk register countries from a CSV file."""

    name = 'bulk register'
    permissionType = 'BulkRegisterCountry'
    required_classname = 'country'
    auditor = staticmethod(audit_country_fields)

    def get_required_columns(self):
        req_cols = ['Name', 'Code']
        if distinguish_official(self.db):
            req_cols.append(self.db.config.ext['MATHOLYMP_OFFICIAL_DESC'])
        return req_cols

    def get_unique_columns(self):
        # Country Number is not actually checked by other code to be
        # unique, but multiple countries corresponding to the same
        # past country is an error, so check it here.
        return ('Country Number', 'Name', 'Code')

    def get_default_values(self):
        return {'is_normal': True,
                'participants_ok': True,
                'reuse_flag': False,
                'expected_numbers_confirmed': False}

    def get_str_column_map(self):
        return {'Name': 'name', 'Code': 'code'}

    def get_bool_column_map(self):
        if distinguish_official(self.db):
            return {self.db.config.ext['MATHOLYMP_OFFICIAL_DESC']: 'official'}
        else:
            return {}

    def map_csv_data(self, row, newvalues):
        dummy_number, generic_url = bulk_csv_country_number_url(self.db, row)
        if generic_url:
            newvalues['generic_url'] = generic_url
        contact_list = bulk_csv_contact_emails(row)
        if contact_list:
            newvalues['contact_email'] = contact_list[0]
            contact_extra = contact_list[1:]
            if contact_extra:
                newvalues['contact_extra'] = '\n'.join(contact_extra)

    def adjust_after_audit(self, row, newvalues):
        # reuse_flag is set to false until the auditor is called, to
        # avoid creating flag items when only doing initial
        # validation, then to True afterwards.
        newvalues['reuse_flag'] = True


class PersonBulkRegisterAction(BulkRegisterAction):

    """Action to bulk register participants from a CSV file."""

    name = 'bulk register'
    permissionType = 'BulkRegisterPerson'
    required_classname = 'person'
    auditor = staticmethod(audit_person_fields)

    def get_required_columns(self):
        req_cols = ['Given Name', 'Family Name', 'Country Code',
                    'Primary Role']
        return req_cols

    def get_unique_columns(self):
        # Person Number is not actually checked by other code to be
        # unique, but multiple people corresponding to the same past
        # person is an error, so check it here.
        return ('Person Number',)

    def get_default_values(self):
        return {'incomplete': True,
                'reuse_photo': False}

    def get_str_column_map(self):
        return {'Given Name': 'given_name', 'Family Name': 'family_name'}

    def get_comma_sep_columns(self):
        return ('Other Roles', 'Guide For Codes')

    def map_csv_data(self, row, newvalues):
        dummy_number, generic_url = bulk_csv_person_number_url(self.db, row)
        if generic_url:
            newvalues['generic_url'] = generic_url
        newvalues['country'] = country_from_code(self.db, row['Country Code'])
        # Because the checks for uniqueness of certain roles from
        # non-staff countries are not applied here, do not allow bulk
        # registration of non-staff to avoid possible errors arising
        # only part way through the creation of person records.
        if self.db.country.get(newvalues['country'], 'is_normal'):
            raise ValueError('non-staff country specified')
        primary_role = row['Primary Role']
        try:
            newvalues['primary_role'] = self.db.matholymprole.lookup(
                primary_role)
        except KeyError:
            raise ValueError('unknown role %s' % primary_role)
        if 'Other Roles' in row:
            newvalues['other_roles'] = []
            for role in row['Other Roles']:
                try:
                    role_id = self.db.matholymprole.lookup(role)
                    newvalues['other_roles'].append(role_id)
                except KeyError:
                    raise ValueError('unknown role %s' % role)
        if 'Guide For Codes' in row:
            newvalues['guide_for'] = []
            for code in row['Guide For Codes']:
                newvalues['guide_for'].append(country_from_code(self.db, code))
        contact_list = bulk_csv_contact_emails(row)
        for email in contact_list:
            if not valid_address(email):
                raise ValueError('Email address syntax is invalid')

    def adjust_after_audit(self, row, newvalues):
        # reuse_photo is set to false until the auditor is called, to
        # avoid creating photo items when only doing initial
        # validation, then to True afterwards.
        newvalues['reuse_photo'] = True

    def act_after_create(self, item_id, item, csv_row):
        contact_list = bulk_csv_contact_emails(csv_row)
        if contact_list:
            # Create the self-registration account.
            username = 'selfreg_%s' % item_id
            if self.db.user.stringFind(username=username):
                return
            realname = '%s %s' % (item['given_name'], item['family_name'])
            pw = roundup.password.generatePassword()
            self.db.user.create(username=username, realname=realname,
                                password=roundup.password.Password(pw),
                                address=contact_list[0],
                                country=item['country'], person=item_id,
                                roles='User,SelfRegister')
            self.db.commit()
            template_path = os.path.join(self.db.config.TRACKER_HOME,
                                         'extensions',
                                         'email-template-self-reg')
            template_text = read_text_from_file(template_path)
            email_text = template_text % {'role': csv_row['Primary Role'],
                                          'id': item_id,
                                          'username': username,
                                          'password': pw}
            short_name = self.db.config.ext['MATHOLYMP_SHORT_NAME']
            year = self.db.config.ext['MATHOLYMP_YEAR']
            subject = '%s %s registration (%s, %s)' % (short_name, year,
                                                       realname,
                                                       csv_row['Primary Role'])
            send_email(self.db, contact_list, subject, email_text,
                       'selfreg%s' % item_id)


def register_actions(instance):
    """Register the matholymp actions with Roundup."""
    instance.registerAction('score', ScoreAction)
    instance.registerAction('retirecountry', RetireCountryAction)
    instance.registerAction('scale_photo', ScalePhotoAction)
    instance.registerAction('country_csv', CountryCSVAction)
    instance.registerAction('scores_csv', ScoresCSVAction)
    instance.registerAction('people_csv', PeopleCSVAction)
    instance.registerAction('medal_boundaries_csv', MedalBoundariesCSVAction)
    instance.registerAction('flags_zip', FlagsZIPAction)
    instance.registerAction('photos_zip', PhotosZIPAction)
    instance.registerAction('consent_forms_zip', ConsentFormsZIPAction)
    instance.registerAction('scores_rss', ScoresRSSAction)
    instance.registerAction('name_badge', NameBadgeAction)
    instance.registerAction('invitation_letter', InvitationLetterAction)
    instance.registerAction('country_bulk_register', CountryBulkRegisterAction)
    instance.registerAction('person_bulk_register', PersonBulkRegisterAction)
