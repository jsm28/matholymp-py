# Actions for Roundup registration system for matholymp package.

# Copyright 2014-2016 Joseph Samuel Myers.

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

__all__ = ['ScoreAction', 'RetireCountryAction', 'CountryCSVAction',
           'ScoresCSVAction', 'PeopleCSVAction', 'FlagsZIPAction',
           'PhotosZIPAction', 'ScoresRSSAction', 'register_actions']

import cgi
import io
import re
import time
import zipfile

from roundup.cgi.actions import Action
from roundup.cgi.exceptions import Unauthorised

from matholymp.roundupreg.roundupsitegen import RoundupSiteGenerator
from matholymp.roundupreg.rounduputil import get_marks_per_problem, \
    scores_from_str, get_none_country, get_staff_country, \
    person_is_contestant, contestant_code, scores_final, \
    valid_country_problem, valid_score, create_rss

class ScoreAction(Action):

    """Action to enter scores."""

    name = 'enter scores for'
    permissionType = 'Score'

    def handle(self):
        """Set the scores for a given country and problem."""
        if scores_final(self.db):
            raise Unauthorised('Scores cannot be entered after'
                               ' medal boundaries are set')
        if self.db.event.get('1', 'registration_enabled'):
            raise Unauthorised('Registration must be disabled before'
                               ' scores are entered')
        if not valid_country_problem(self.db, self.form):
            raise ValueError('Country or problem invalid or not specified')
        country = self.form['country'].value
        problem = self.form['problem'].value
        country_node = self.db.country.getnode(country)
        problem_number = int(problem)
        marks_per_problem = get_marks_per_problem(self.db)
        max_this_problem = marks_per_problem[problem_number-1]
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
                scores[problem_number-1] = score
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
        if self.nodeid is None:
            raise ValueError('No id specified to retire')
        if not self.hasPermission('Retire', classname=self.classname,
                                  itemid=self.nodeid):
            raise Unauthorised('You do not have permission to retire'
                               ' this country')
        if self.nodeid == get_none_country(self.db):
            raise Unauthorised('The special country None cannot be retired')
        if self.nodeid == get_staff_country(self.db):
            raise Unauthorised('The special staff country cannot be retired')
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

class CountryCSVAction(Action):

    """Action to return a CSV file of countries."""

    def handle(self):
        """Output the list of countries as a CSV file."""
        self.client.setHeader('Content-Type', 'text/csv; charset=UTF-8')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=countries.csv')
        return RoundupSiteGenerator(self.db).countries_csv_bytes()

class ScoresCSVAction(Action):

    """Action to return a CSV file of scores."""

    def handle(self):
        """Output the scores as a CSV file."""
        self.client.setHeader('Content-Type', 'text/csv; charset=UTF-8')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=scores.csv')
        return RoundupSiteGenerator(self.db).scores_csv_bytes()

class PeopleCSVAction(Action):

    """Action to return a CSV file of people."""

    def handle(self):
        """Output the list of people as a CSV file."""
        self.client.setHeader('Content-Type', 'text/csv; charset=UTF-8')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=people.csv')
        show_all = self.hasPermission('Omnivident')
        return RoundupSiteGenerator(self.db).people_csv_bytes(show_all)

class FlagsZIPAction(Action):

    """Action to return a ZIP file of flags."""

    def handle(self):
        """Output a ZIP file of flags of registered countries."""
        self.client.setHeader('Content-Type', 'application/zip')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=flags.zip')
        output = io.BytesIO()
        zip = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
        zip.writestr('flags/README.txt',
                     'The flags in this file are arranged by internal'
                     ' database identifier;\nsee the Flag URL column in'
                     ' the CSV file of countries to match them to\n'
                     'individual countries.\n')

        country_list = self.db.country.list()
        none_country = get_none_country(self.db)
        for country in country_list:
            if country != none_country:
                flag_id = self.db.country.get(country, 'files')
                if flag_id is not None:
                    filename = self.db.filename('file', flag_id)
                    zip_filename_only = self.db.file.get(flag_id, 'name')
                    zip_filename_only = re.sub('[^a-zA-Z0-9_.]', '_',
                                               zip_filename_only)
                    zip_filename_only = re.sub('^.*\\.', 'flag.',
                                               zip_filename_only)
                    zip_filename_only = re.sub('^[^.]*$', 'flag',
                                               zip_filename_only)
                    zip_filename = ('flags/flag' + flag_id + '/' +
                                    zip_filename_only)
                    zip.write(filename, zip_filename)

        zip.close()
        zip_bytes = output.getvalue()
        output.close()
        return zip_bytes

class PhotosZIPAction(Action):

    """Action to return a ZIP file of photos."""

    def handle(self):
        """Output a ZIP file of photos of registered participants."""
        self.client.setHeader('Content-Type', 'application/zip')
        self.client.setHeader('Content-Disposition',
                              'attachment; filename=photos.zip')
        output = io.BytesIO()
        zip = zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED)
        zip.writestr('photos/README.txt',
                     'The photos in this file are arranged by internal'
                     ' database identifier;\nsee the Photo URL column in'
                     ' the CSV file of people to match them to\n'
                     'individual participants.\n')

        person_list = self.db.person.list()
        for person in person_list:
            photo_id = self.db.person.get(person, 'files')
            if photo_id is not None:
                filename = self.db.filename('file', photo_id)
                zip_filename_only = self.db.file.get(photo_id, 'name')
                zip_filename_only = re.sub('[^a-zA-Z0-9_.]', '_',
                                           zip_filename_only)
                zip_filename_only = re.sub('^.*\\.', 'photo.',
                                           zip_filename_only)
                zip_filename_only = re.sub('^[^.]*$', 'photo',
                                           zip_filename_only)
                zip_filename = ('photos/photo' + photo_id + '/' +
                                zip_filename_only)
                zip.write(filename, zip_filename)

        zip.close()
        zip_bytes = output.getvalue()
        output.close()
        return zip_bytes

class ScoresRSSAction(Action):

    """Action to return an RSS feed of scores."""

    def handle(self):
        """Output the RSS feed for scores."""
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
        text += ('    <title>%s %s%s Scores</title>\n' %
                 (cgi.escape(short_name), cgi.escape(year),
                  cgi.escape(title_extra)))
        text += '    <link>%s</link>\n' % link_url
        text += ('    <description>%s %s%s Scores Live Feed</description>\n' %
                 (cgi.escape(short_name), cgi.escape(year),
                  cgi.escape(title_extra)))
        text += '    <language>en-gb</language>\n'
        text += '    <docs>http://www.rssboard.org/rss-specification</docs>\n'
        text += ('    <atom:link href="%s" rel="self"'
                 ' type="application/rss+xml" />\n    ' %
                 cgi.escape((self.base + 'country' + url_id +
                             '?@action=scores_rss'), quote=True))

        rss_list = self.db.rss.list()
        rss_list = sorted(rss_list, key=lambda x:int(x), reverse=True)
        rss_text_list = [self.db.rss.get(r, 'text')
                         for r in rss_list
                         if (self.nodeid is None or
                             self.db.rss.get(r, 'country') is None or
                             self.db.rss.get(r, 'country') == self.nodeid)]
        text += '\n    '.join(rss_text_list)

        text += '\n  </channel>\n</rss>\n'
        return text

def register_actions(instance):
    """Register the matholymp actions with Roundup."""
    instance.registerAction('score', ScoreAction)
    instance.registerAction('retirecountry', RetireCountryAction)
    instance.registerAction('country_csv', CountryCSVAction)
    instance.registerAction('scores_csv', ScoresCSVAction)
    instance.registerAction('people_csv', PeopleCSVAction)
    instance.registerAction('flags_zip', FlagsZIPAction)
    instance.registerAction('photos_zip', PhotosZIPAction)
    instance.registerAction('scores_rss', ScoresRSSAction)
