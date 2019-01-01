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
           'ScoresRSSAction', 'register_actions']

import cgi
import io
import os

from PIL import Image
from roundup.cgi.actions import Action
from roundup.cgi.exceptions import Unauthorised
from roundup.exceptions import Reject

from matholymp.roundupreg.roundupsitegen import RoundupSiteGenerator
from matholymp.roundupreg.rounduputil import get_marks_per_problem, \
    scores_from_str, person_is_contestant, contestant_code, scores_final, \
    valid_country_problem, valid_score, create_rss


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
                if score != '' and not valid_score(score, max_this_problem):
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
        return RoundupSiteGenerator(self.db).countries_csv_bytes()


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
                 % (cgi.escape(short_name), cgi.escape(year),
                    cgi.escape(title_extra)))
        text += '    <link>%s</link>\n' % link_url
        text += ('    <description>%s %s%s Scores Live Feed</description>\n'
                 % (cgi.escape(short_name), cgi.escape(year),
                    cgi.escape(title_extra)))
        text += '    <language>en-gb</language>\n'
        text += '    <docs>http://www.rssboard.org/rss-specification</docs>\n'
        text += ('    <atom:link href="%s" rel="self"'
                 ' type="application/rss+xml" />\n    '
                 % cgi.escape((self.base + 'country' + url_id
                               + '?@action=scores_rss'), quote=True))

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
