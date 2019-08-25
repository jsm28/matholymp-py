# Website generation for matholymp package.

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
This module provides the SiteGenerator class that can be used to
generate a whole website or individual pages or page fragments.
"""

import cgi
import os
import os.path
import re

from matholymp.collate import coll_get_sort_key
from matholymp.csvsource import CSVDataSource
from matholymp.data import EventGroup
from matholymp.datetimeutil import date_range_html, date_to_ymd_iso, \
    time_to_hhmm
from matholymp.fileutil import read_utf8_csv, write_utf8_csv, \
    comma_join, write_text_to_file, read_text_from_file, read_config

__all__ = ['read_sitegen_config', 'sitegen_events_csv', 'sitegen_papers_csv',
           'sitegen_countries_csv', 'sitegen_people_csv',
           'sitegen_event_group', 'SiteGenerator']


def read_sitegen_config(top_directory):
    """Read the configuration file for site generation."""
    cfg_file_name = os.path.join(top_directory, 'staticsite.cfg')
    cfg_str_keys = ['long_name', 'short_name', 'short_name_plural',
                    'num_key', 'scores_css', 'list_css', 'photo_css',
                    'page_suffix', 'page_include_extra', 'url_base',
                    'short_name_url', 'short_name_url_plural',
                    'official_desc', 'official_desc_lc', 'official_adj',
                    'age_day_desc']
    cfg_int_keys = []
    cfg_int_none_keys = ['rank_top_n', 'event_active_number']
    cfg_bool_keys = ['use_xhtml', 'distinguish_official',
                     'honourable_mentions_available']
    cfg_data = read_config(cfg_file_name, 'matholymp.staticsite',
                           cfg_str_keys, cfg_int_keys, cfg_int_none_keys,
                           cfg_bool_keys)

    template_file_name = os.path.join(top_directory, 'page-template')
    cfg_data['page_template'] = read_text_from_file(template_file_name)

    return cfg_data


def sitegen_events_csv(top_directory, cfg_data):
    """Return the path to the CSV file of events."""
    return os.path.join(top_directory, 'data',
                        cfg_data['short_name_url_plural'] + '.csv')


def sitegen_papers_csv(top_directory, cfg_data):
    """Return the path to the CSV file of papers."""
    return os.path.join(top_directory, 'data', 'papers.csv')


def sitegen_countries_csv(top_directory, cfg_data):
    """Return the path to the CSV file of papers."""
    return os.path.join(top_directory, 'data', 'countries.csv')


def sitegen_people_csv(top_directory, cfg_data):
    """Return the path to the CSV file of papers."""
    return os.path.join(top_directory, 'data', 'people.csv')


def sitegen_event_group(top_directory, cfg_data):
    """Return an EventGroup based on the static site data."""
    events_csv = sitegen_events_csv(top_directory, cfg_data)
    papers_csv = sitegen_papers_csv(top_directory, cfg_data)
    countries_csv = sitegen_countries_csv(top_directory, cfg_data)
    people_csv = sitegen_people_csv(top_directory, cfg_data)

    events_data = read_utf8_csv(events_csv)
    countries_data = read_utf8_csv(countries_csv)
    people_data = read_utf8_csv(people_csv)
    papers_data = read_utf8_csv(papers_csv)

    return EventGroup(CSVDataSource(cfg_data, events_data, papers_data,
                                    countries_data, people_data,
                                    top_directory))


class SiteGenerator(object):

    """
    A SiteGenerator supports website generation for a particular
    EventGroup and configuration data describing options for how the
    site is generated from it.
    """

    def __init__(self, cfg, event_group, out_dir=None):
        """
        Initialise a SiteGenerator from the given configuration
        information and EventGroup.
        """
        self._cfg = cfg
        self._data = event_group
        self._out_dir = out_dir
        self._url_base_rel = re.sub('^https?://[^/]*', '',
                                    self._cfg['url_base'])
        if out_dir is not None:
            self._auto_out_dir = os.path.join(out_dir, cfg['short_name_url'],
                                              'auto')

    def write_html_to_file(self, out_text, title, header, out_path):
        """Write HTML text to a file in standard template."""
        long_title = cgi.escape(self._data.long_name) + ': ' + title
        short_title = cgi.escape(self._data.short_name) + ': ' + header
        page_data = {'title': long_title,
                     'header': short_title,
                     'body': out_text}
        text = self._cfg['page_template'] % page_data
        out_file_name = os.path.join(self._out_dir, *out_path)
        out_file_name = os.path.join(out_file_name,
                                     'index' + self._cfg['page_suffix'])
        write_text_to_file(text, out_file_name)

    def write_csv_to_file(self, csv_file_path, rows, keys):
        """Write a CSV file in the output directory."""
        csv_file_name = os.path.join(self._out_dir, *csv_file_path)
        write_utf8_csv(csv_file_name, rows, keys)

    def _attr_text(self, attrs):
        nattrs = {}
        for k in attrs:
            if k.endswith('_'):
                nk = k[0:len(k) - 1]
            else:
                nk = k
            nattrs[nk] = attrs[k]
        return ''.join([' %s="%s"' % (k, cgi.escape(nattrs[k], quote=True))
                        for k in sorted(nattrs.keys())])

    def html_element(self, tag, contents, **attrs):
        """
        Generate an HTML element with the given name, contents and
        attributes.  Tag and attribute names are expected to be in
        lower-case; a single trailing underscore is removed from
        attribute names to support Python keywords as attribute names.
        Contents are HTML text; the caller must do any necessary
        escaping.
        """
        return '<%s%s>%s</%s>' % (tag, self._attr_text(attrs), contents, tag)

    def html_element_empty(self, tag, **attrs):
        """
        Generate an empty HTML element with the given name and
        attributes.  Tag and attribute names are expected to be in
        lower-case; a single trailing underscore is removed from
        attribute names to support Python keywords as attribute names.
        """
        if self._cfg['use_xhtml']:
            return '<%s%s />' % (tag, self._attr_text(attrs))
        else:
            return '<%s%s>' % (tag, self._attr_text(attrs))

    def html_a(self, contents, href, **attrs):
        """Generate an HTML link."""
        return self.html_element('a', contents, href=href, **attrs)

    def html_a_external(self, contents, href, **attrs):
        """Generate an HTML link to an external page."""
        return self.html_a(contents, href, target='_blank', **attrs)

    def html_img(self, **attrs):
        return self.html_element_empty('img', **attrs)

    def html_th(self, contents, **attrs):
        """Generate an HTML th element."""
        return self.html_element('th', contents, **attrs)

    def html_th_scores(self, contents, **attrs):
        """Generate an HTML th element, using the CSS for tables of scores."""
        return self.html_th(contents, class_=self._cfg['scores_css'], **attrs)

    def html_td(self, contents, **attrs):
        """Generate an HTML td element."""
        return self.html_element('td', contents, **attrs)

    def html_td_scores(self, contents, **attrs):
        """Generate an HTML td element, using the CSS for tables of scores."""
        return self.html_td(contents, class_=self._cfg['scores_css'], **attrs)

    def html_tr(self, contents, **attrs):
        """Generate an HTML tr element."""
        return self.html_element('tr', contents, **attrs)

    def html_tr_list(self, contents_list, **attrs):
        """
        Generate an HTML tr element, with contents the concatenation of a list.
        """
        return self.html_tr(''.join(contents_list), **attrs)

    def html_tr_th_list(self, th_list, **attrs):
        """
        Generate an HTML tr element, with contents a sequence of th elements.
        """
        return self.html_tr_list([self.html_th(s) for s in th_list], **attrs)

    def html_tr_th_scores_list(self, th_list, **attrs):
        """
        Generate an HTML tr element, with contents a sequence of th
        elements, each using the CSS for tables of scores.
        """
        return self.html_tr_list([self.html_th_scores(s) for s in th_list],
                                 **attrs)

    def html_tr_td_list(self, td_list, **attrs):
        """
        Generate an HTML tr element, with contents a sequence of td elements.
        """
        return self.html_tr_list([self.html_td(s) for s in td_list], **attrs)

    def html_tr_td_scores_list(self, td_list, **attrs):
        """
        Generate an HTML tr element, with contents a sequence of td
        elements, each using the CSS for tables of scores.
        """
        return self.html_tr_list([self.html_td_scores(s) for s in td_list],
                                 **attrs)

    def html_tr_th_td(self, th, td, **attrs):
        """
        Generate an HTML tr element, with contents a th element and a
        td element.
        """
        return self.html_tr_list([self.html_th(th), self.html_td(td)], **attrs)

    def html_thead(self, contents, **attrs):
        """Generate an HTML thead element."""
        return self.html_element('thead', contents, **attrs)

    def html_thead_list(self, contents_list, **attrs):
        """Generate an HTML thead element, with contents a list of rows."""
        return self.html_thead('\n' + '\n'.join(contents_list) + '\n', **attrs)

    def html_tbody(self, contents, **attrs):
        """Generate an HTML tbody element."""
        return self.html_element('tbody', contents, **attrs)

    def html_tbody_list(self, contents_list, **attrs):
        """Generate an HTML tbody element, with contents a list of rows."""
        return self.html_tbody('\n' + '\n'.join(contents_list) + '\n', **attrs)

    def html_table(self, contents, **attrs):
        """Generate an HTML table element."""
        return self.html_element('table', contents, **attrs)

    def html_table_thead_tbody_list(self, head_list, body_list, **attrs):
        """
        Generate an HTML table element, with contents a sequence of
        header rows and a sequence of body rows, using the CSS for
        lists.
        """
        head = self.html_thead_list(head_list)
        body = self.html_tbody_list(body_list)
        return self.html_table('\n' + head + '\n' + body + '\n',
                               class_=self._cfg['list_css'], **attrs)

    def html_table_list(self, row_list, **attrs):
        """
        Generate an HTML table element, with contents a sequence of
        rows, using the CSS for lists.
        """
        return self.html_table('\n' + '\n'.join(row_list) + '\n',
                               class_=self._cfg['list_css'], **attrs)

    def html_table_list_th_td(self, row_list, **attrs):
        """
        Generate an HTML table element, with contents a sequence of
        rows, each row having a th and a td element, using the CSS for
        lists.
        """
        tr_list = [self.html_tr_th_td(r[0], r[1]) for r in row_list]
        return self.html_table_list(tr_list, **attrs)

    def home_page_link_for_event(self, e):
        """Generate a link to an event's home page."""
        url = e.home_page_url
        if url is None:
            return ''
        return ' (%s)' % self.html_a_external('home page', url)

    def link_for_file(self, path_list, link_body):
        """Generate a link to a given file on this site."""
        url = self._url_base_rel + '/'.join(path_list)
        return self.html_a(link_body, url)

    def link_for_page(self, path_list, link_body):
        """Generate a link to a given page, ending with '/', on this site."""
        url = self._url_base_rel + '/'.join(path_list) + '/'
        return self.html_a(link_body, url)

    def link_for_registration(self, event, reg_path, link_body):
        """
        Generate a link to the registration system for a given event
        on this site.
        """
        path_list = ['registration', event.year, reg_path]
        return self.link_for_file(path_list, link_body)

    def path_for_events(self):
        """Return the path (a list) of the directory of events."""
        return [self._cfg['short_name_url_plural']]

    def path_for_event(self, event):
        """Return the path (a list) of the directory for a given event."""
        p = self.path_for_events()
        p.append(self._cfg['short_name_url'] + str(event.id))
        return p

    def link_for_event(self, event, link_body):
        """Generate a link to the main page for a given event."""
        return self.link_for_page(self.path_for_event(event), link_body)

    def path_for_event_countries(self, event):
        """
        Return the path (a list) of the directory of countries for a
        given event.
        """
        p = self.path_for_event(event)
        p.append('countries')
        return p

    def link_for_event_countries(self, event, link_body):
        """Generate a link to the list of countries for a given event."""
        return self.link_for_page(self.path_for_event_countries(event),
                                  link_body)

    def path_for_event_countries_csv(self, event):
        """
        Return the path (a list) of the CSV file of countries for a
        given event.
        """
        p = self.path_for_event_countries(event)
        p.append('countries.csv')
        return p

    def link_for_event_countries_csv(self, event, link_body):
        """Generate a link to the CSV file of countries for a given event."""
        return self.link_for_file(self.path_for_event_countries_csv(event),
                                  link_body)

    def path_for_event_people(self, event):
        """
        Return the path (a list) of the directory of people for a given event.
        """
        p = self.path_for_event(event)
        p.append('people')
        return p

    def link_for_event_people(self, event, link_body):
        """Generate a link to the list of people for a given event."""
        return self.link_for_page(self.path_for_event_people(event),
                                  link_body)

    def path_for_event_people_csv(self, event):
        """
        Return the path (a list) of the CSV file of people for a given event.
        """
        p = self.path_for_event_people(event)
        p.append('people.csv')
        return p

    def link_for_event_people_csv(self, event, link_body):
        """Generate a link to the CSV file of people for a given event."""
        return self.link_for_file(self.path_for_event_people_csv(event),
                                  link_body)

    def path_for_event_scoreboard(self, event):
        """
        Return the path (a list) of the directory of the scoreboard
        for a given event.
        """
        p = self.path_for_event(event)
        p.append('scoreboard')
        return p

    def link_for_event_scoreboard(self, event, link_body):
        """Generate a link to the scoreboard for a given event."""
        return self.link_for_page(self.path_for_event_scoreboard(event),
                                  link_body)

    def path_for_event_scores_csv(self, event):
        """
        Return the path (a list) of the CSV file of scores for a given event.
        """
        p = self.path_for_event_scoreboard(event)
        p.append('scores.csv')
        return p

    def link_for_event_scores_csv(self, event, link_body):
        """Generate a link to the CSV file of scores for a given event."""
        return self.link_for_file(self.path_for_event_scores_csv(event),
                                  link_body)

    def path_for_event_scores_rss(self, event):
        """
        Return the path (a list) of the RSS feed of scores for a given event.
        """
        p = self.path_for_event_scoreboard(event)
        p.append('rss.xml')
        return p

    def link_for_event_scores_rss(self, event, link_body):
        """Generate a link to the RSS feed of scores for a given event."""
        return self.link_for_file(self.path_for_event_scores_rss(event),
                                  link_body)

    def path_for_country_at_event(self, country):
        """
        Return the path (a list) of the directory for a given country
        at a given event.
        """
        p = self.path_for_event_countries(country.event)
        p.append('country' + str(country.country.id))
        return p

    def link_for_country_at_event(self, country, link_body):
        """Generate a link to the page for a given country at a given event."""
        return self.link_for_page(self.path_for_country_at_event(country),
                                  link_body)

    def path_for_countries(self):
        """Return the path (a list) of the directory of countries."""
        return ['countries']

    def path_for_country(self, country):
        """Return the path (a list) of the directory for a given country."""
        p = self.path_for_countries()
        p.append('country' + str(country.id))
        return p

    def link_for_country(self, country, link_body):
        """Generate a link to the main page for a given country."""
        return self.link_for_page(self.path_for_country(country), link_body)

    def path_for_people(self):
        """Return the path (a list) of the directory of people."""
        return ['people']

    def path_for_hall_of_fame(self):
        """Return the path (a list) of the directory of the hall of fame."""
        p = self.path_for_people()
        p.append('halloffame')
        return p

    def link_for_hall_of_fame(self, link_body):
        """Generate a link to the hall of fame."""
        return self.link_for_page(self.path_for_hall_of_fame(), link_body)

    def path_for_person(self, person):
        """Return the path (a list) of the directory for a given person."""
        p = self.path_for_people()
        p.append('person' + str(person.id))
        return p

    def link_for_person(self, person, link_body):
        """Generate a link to the main page for a given person."""
        return self.link_for_page(self.path_for_person(person), link_body)

    def path_for_data_events(self):
        """Return the path (a list) for the data for all events."""
        return ['data', self._cfg['short_name_url_plural'] + '-all.csv']

    def link_for_data_events(self, link_body):
        """Generate a link to the data for all events."""
        return self.link_for_file(self.path_for_data_events(), link_body)

    def path_for_data_papers(self):
        """Return the path (a list) for the data for all papers."""
        return ['data', 'papers.csv']

    def link_for_data_papers(self, link_body):
        """Generate a link to the data for all papers."""
        return self.link_for_file(self.path_for_data_papers(), link_body)

    def path_for_data_countries(self):
        """Return the path (a list) for the data for all countries."""
        return ['data', 'countries-all.csv']

    def link_for_data_countries(self, link_body):
        """Generate a link to the data for all countries."""
        return self.link_for_file(self.path_for_data_countries(), link_body)

    def path_for_data_people(self):
        """Return the path (a list) for the data for all people."""
        return ['data', 'people-all.csv']

    def link_for_data_people(self, link_body):
        """Generate a link to the data for all people."""
        return self.link_for_file(self.path_for_data_people(), link_body)

    def link_for_event_and_host(self, event):
        """
        Generate header text referring to an event and its host
        country, with links.
        """
        return ('%s in %s'
                % (self.link_for_event(event,
                                       cgi.escape(event.short_name_with_year)),
                   self.link_for_country(event.host_country,
                                         cgi.escape(
                                             event.host_country_name_in))))

    def generate_sidebar_out(self):
        """Generate HTML text for the sidebar."""
        out_filename = 'sidebar-%s-list%s' % (self._cfg['short_name_url'],
                                              self._cfg['page_suffix'])
        sidebar_out = os.path.join(self._auto_out_dir, out_filename)
        out_list = []
        for e in self._data.event_list:
            short_name = cgi.escape(e.short_name_with_year)
            location = cgi.escape(e.host_location)
            event_link = self.link_for_event(e, short_name)
            home_link = self.home_page_link_for_event(e)
            text = ('<li><strong>%s</strong>, %s%s</li>'
                    % (event_link, location, home_link))
            out_list.append(text)
        out_list.reverse()
        out_text = '\n'.join(out_list) + '\n'
        write_text_to_file(out_text, sidebar_out)

    def generate_contact_out(self):
        """Generate HTML text for contact details."""
        out_filename = '%s-contact-list%s' % (self._cfg['short_name_url'],
                                              self._cfg['page_suffix'])
        contact_out = os.path.join(self._auto_out_dir, out_filename)
        out_list = []
        for e in self._data.event_list:
            short_name = cgi.escape(e.short_name_with_year)
            contact = cgi.escape(e.contact or '')
            if contact:
                text = ('  <li>For communications about %s,'
                        ' please contact %s.</li>'
                        % (short_name, contact))
                out_list.append(text)
        out_text = '\n'.join(out_list) + '\n'
        write_text_to_file(out_text, contact_out)

    def generate_events_summary(self):
        """Generate a summmary of all events."""
        text = ''
        text += ('<p>Details of all %s may also be %s in CSV format,'
                 ' as may %s.</p>\n'
                 % (cgi.escape(self._data.short_name_plural),
                    self.link_for_data_events('downloaded'),
                    self.link_for_data_papers('a list of all language versions'
                                              ' of all papers')))
        awards_colspan = 4
        if self._data.honourable_mentions_available:
            awards_colspan += 1
        awards_colspan = str(awards_colspan)
        head_row_1 = [self.html_th_scores('#', rowspan='2',
                                          title=('%s number'
                                                 % self._data.short_name)),
                      self.html_th_scores('Year', rowspan='2'),
                      self.html_th_scores('Country', rowspan='2'),
                      self.html_th_scores('City', rowspan='2'),
                      self.html_th_scores('Dates', rowspan='2'),
                      self.html_th_scores('Teams', rowspan='2'),
                      self.html_th_scores('Contestants',
                                          colspan=awards_colspan)]
        head_row_2 = [self.html_th_scores('All'),
                      self.html_th_scores('G', title='Gold'),
                      self.html_th_scores('S', title='Silver'),
                      self.html_th_scores('B', title='Bronze')]
        if self._data.honourable_mentions_available:
            head_row_2.extend([self.html_th_scores(
                'HM',
                title='Honourable Mention')])
        head_row_list = [self.html_tr_list(head_row_1),
                         self.html_tr_list(head_row_2)]
        body_row_list = []
        for e in self._data.event_list:
            number = self.link_for_event(e, str(e.id))
            year = self.link_for_event(e, cgi.escape(e.year))
            country = self.link_for_country(e.host_country,
                                            cgi.escape(e.host_country_name))
            city = cgi.escape(e.host_city or '')
            if e.start_date is None or e.end_date is None:
                dates = ''
            else:
                dates = date_range_html(e.start_date, e.end_date, int(e.year))
            num_contestants = e.num_contestants
            if num_contestants:
                num_gold = e.num_awards['Gold Medal']
                num_silver = e.num_awards['Silver Medal']
                num_bronze = e.num_awards['Bronze Medal']
                if e.honourable_mentions_available:
                    num_hm = e.num_awards['Honourable Mention']
                else:
                    num_hm = ''
                num_countries = e.num_countries
            else:
                num_contestants = ''
                num_gold = ''
                num_silver = ''
                num_bronze = ''
                num_hm = ''
                num_countries = ''
            row_list = [number, year, country, city, dates, num_countries,
                        num_contestants, num_gold, num_silver, num_bronze]
            if self._data.honourable_mentions_available:
                row_list.extend([num_hm])
            row = self.html_tr_td_scores_list(row_list)
            body_row_list.append(row)
        body_row_list.reverse()
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'
        title = 'List of %s' % cgi.escape(self._data.short_name_plural)
        self.write_html_to_file(text, title, title, self.path_for_events())

    def host_year_text(self, c):
        """Generate text listing years for which one country was host."""
        host_year_list = [self.link_for_event(e, cgi.escape(e.year))
                          for e in c.host_list]
        return ', '.join(host_year_list)

    def generate_countries_summary(self):
        """Generate a summary of all countries."""
        text = ''
        text += ('<p>Details of all countries at all %s may also be'
                 ' %s in CSV format.</p>\n'
                 % (cgi.escape(self._data.short_name_plural),
                    self.link_for_data_countries('downloaded')))
        head_row = [self.html_th('Code'),
                    self.html_th('Name')]
        if self._data.distinguish_official:
            head_row.extend([self.html_th(
                cgi.escape(self._cfg['official_desc']))])
        head_row.extend(
            [self.html_th('First'),
             self.html_th('Last'),
             self.html_th('#', title=('Number of %s'
                                      % self._data.short_name_plural)),
             self.html_th('Host')])
        head_row_list = [self.html_tr_list(head_row)]
        body_row_list = []
        countries = sorted(self._data.country_list, key=lambda x: x.sort_key)
        for c in countries:
            first_c = c.participation_list[0]
            last_c = c.participation_list[-1]
            first_year = cgi.escape(first_c.event.year)
            last_year = cgi.escape(last_c.event.year)
            row = [self.link_for_country(c, cgi.escape(c.code)),
                   self.link_for_country(c, cgi.escape(c.name))]
            if self._data.distinguish_official:
                row.extend(['' if c.is_official is None
                            else 'Yes' if c.is_official else 'No'])
            row.extend(
                [self.link_for_country_at_event(first_c, first_year),
                 self.link_for_country_at_event(last_c, last_year),
                 c.num_participations,
                 self.host_year_text(c)])
            body_row_list.append(self.html_tr_td_list(row))
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'
        title = 'Countries'
        header = 'Countries'
        self.write_html_to_file(text, title, header, self.path_for_countries())

    def generate_people_summary(self):
        """Generate a summary of all people."""
        text = ''
        hoftxt = ('hall of fame of %s contestants by medal count'
                  % cgi.escape(self._data.short_name))
        text += ('<p>A %s is also available.  Details of all people at'
                 ' all %s may also be %s in CSV format.</p>\n'
                 % (self.link_for_hall_of_fame(hoftxt),
                    cgi.escape(self._data.short_name_plural),
                    self.link_for_data_people('downloaded')))
        head_row_list = [self.html_tr_th_scores_list(['Given Name',
                                                      'Family Name',
                                                      'Participations'])]
        body_row_list = []
        for pd in sorted(self._data.person_list,
                         key=lambda x: x.sort_key_alpha):
            pd_list = []
            for p in pd.participation_list:
                e = p.event
                year_text = ''
                year_text += ('%s: '
                              % self.link_for_event(e, cgi.escape(e.year)))
                cl = self.link_for_country_at_event(p.country,
                                                    cgi.escape(p.country.name))
                year_text += '%s ' % cl
                role_text = cgi.escape(p.primary_role)
                if p.is_contestant and p.awards_str:
                    role_text += ': %s' % cgi.escape(p.awards_str)
                if p.guide_for:
                    glist = sorted(p.guide_for, key=lambda x: x.sort_key)
                    gtlist = []
                    for c in glist:
                        cl = self.link_for_country_at_event(c,
                                                            cgi.escape(c.name))
                        gtlist.append(cl)
                    role_text += ': %s' % ', '.join(gtlist)
                if p.other_roles:
                    rs = sorted(p.other_roles, key=coll_get_sort_key)
                    role_text += ', %s' % cgi.escape(', '.join(rs))
                year_text += '(%s)' % role_text
                pd_list.append(year_text)
            row = [self.link_for_person(p.person, cgi.escape(p.given_name)),
                   self.link_for_person(p.person, cgi.escape(p.family_name)),
                   ', '.join(pd_list)]
            body_row_list.append(self.html_tr_td_scores_list(row))
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'
        title = 'People'
        header = 'People'
        self.write_html_to_file(text, title, header, self.path_for_people())

    def generate_hall_of_fame(self):
        """Generate hall of fame by medal count."""
        text = ''
        head_row = [self.html_th_scores('Given Name'),
                    self.html_th_scores('Family Name'),
                    self.html_th_scores('Country'),
                    self.html_th_scores('G', title='Gold'),
                    self.html_th_scores('S', title='Silver'),
                    self.html_th_scores('B', title='Bronze')]
        if self._data.honourable_mentions_available:
            head_row.extend([self.html_th_scores('HM',
                                                 title='Honourable Mention')])
        head_row.extend([self.html_th_scores('Participations')])
        head_row_list = [self.html_tr_list(head_row)]
        contestants = sorted(self._data.contestant_list,
                             key=lambda x: x.sort_key_hall_of_fame)
        body_row_list = []
        for p in contestants:
            row = [self.link_for_person(p, cgi.escape(p.given_name)),
                   self.link_for_person(p, cgi.escape(p.family_name)),
                   ', '.join([self.link_for_country(c, cgi.escape(c.code))
                              for c in p.country_list]),
                   str(p.num_awards['Gold Medal']),
                   str(p.num_awards['Silver Medal']),
                   str(p.num_awards['Bronze Medal'])]
            if self._data.honourable_mentions_available:
                row.extend([str(p.num_awards['Honourable Mention'])])
            row.extend([str(p.num_participations)])
            body_row_list.append(self.html_tr_td_scores_list(row))
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'
        title = 'Hall of Fame'
        header = 'Hall of Fame'
        self.write_html_to_file(text, title, header,
                                self.path_for_hall_of_fame())

    def generate_one_event_summary(self, e):
        """Generate a summmary of one event."""
        text = ''
        row_list = [['%s number' % cgi.escape(e.short_name), str(e.id)],
                    ['Year', '%s%s' % (cgi.escape(e.year),
                                       self.home_page_link_for_event(e))],
                    ['Country',
                     self.link_for_country(e.host_country,
                                           cgi.escape(e.host_country_name))],
                    ['City', cgi.escape(e.host_city or '')],
                    ['Start date', cgi.escape(date_to_ymd_iso(e.start_date))],
                    ['End date', cgi.escape(date_to_ymd_iso(e.end_date))],
                    ['Contact name', cgi.escape(e.contact_name or '')],
                    ['Contact email', cgi.escape(e.contact_email or '')]]
        if e.num_contestants:
            prob_marks = str(e.num_problems)
            prob_marks += (' (marked out of: %s)'
                           % '+'.join([str(m) for m in e.marks_per_problem]))
            if e.distinguish_official:
                part_c_off = (' (%d %s)'
                              % (e.num_countries_official,
                                 cgi.escape(self._cfg['official_desc_lc'])))
                cont_off = (' (%d %s)'
                            % (e.num_contestants_official,
                               cgi.escape(self._cfg['official_desc_lc'])))
                gold_off = (' (%d %s)'
                            % (e.num_awards_official['Gold Medal'],
                               cgi.escape(self._cfg['official_desc_lc'])))
                silver_off = (' (%d %s)'
                              % (e.num_awards_official['Silver Medal'],
                                 cgi.escape(self._cfg['official_desc_lc'])))
                bronze_off = (' (%d %s)'
                              % (e.num_awards_official['Bronze Medal'],
                                 cgi.escape(self._cfg['official_desc_lc'])))
                if e.honourable_mentions_available:
                    hm_off = (' (%d %s)'
                              % (e.num_awards_official['Honourable Mention'],
                                 cgi.escape(self._cfg['official_desc_lc'])))
                else:
                    hm_off = ''
            else:
                part_c_off = ''
                cont_off = ''
                gold_off = ''
                silver_off = ''
                bronze_off = ''
                hm_off = ''
            more_rows = [['Participating teams',
                          ('%d%s (%s)'
                           % (e.num_countries, part_c_off,
                              self.link_for_event_countries(e, 'list')))],
                         ['Contestants',
                          '%d%s (%s, %s)'
                          % (e.num_contestants, cont_off,
                             self.link_for_event_scoreboard(e, 'scoreboard'),
                             self.link_for_event_people(e,
                                                        'list of'
                                                        ' participants'))],
                         ['Number of exams', str(e.num_exams)],
                         ['Number of problems', prob_marks],
                         ['Gold medals',
                          '%d%s (scores &ge; %d)'
                          % (e.num_awards['Gold Medal'], gold_off,
                             e.gold_boundary)],
                         ['Silver medals',
                          '%d%s (scores &ge; %d)'
                          % (e.num_awards['Silver Medal'], silver_off,
                             e.silver_boundary)],
                         ['Bronze medals',
                          '%d%s (scores &ge; %d)'
                          % (e.num_awards['Bronze Medal'], bronze_off,
                             e.bronze_boundary)]]
            row_list.extend(more_rows)
            if e.honourable_mentions_available:
                more_rows = [['Honourable mentions',
                              '%d%s'
                              % (e.num_awards['Honourable Mention'], hm_off)]]
                row_list.extend(more_rows)
        text += self.html_table_list_th_td(row_list) + '\n'
        if e.registration_active:
            text += ('<p>Lists of currently registered %s and %s'
                     ' are available, as is the %s.</p>\n'
                     % (self.link_for_registration(e, 'country', 'countries'),
                        self.link_for_registration(e, 'person',
                                                   'participants'),
                        self.link_for_registration(e,
                                                   'person?'
                                                   '@template=scoreboard',
                                                   'live scoreboard')))
        extra_dir = '/'.join(self.path_for_event(e))
        text += self._cfg['page_include_extra'] % {'dir': extra_dir}
        text += '\n'
        if e.num_exams:
            for day in range(1, e.num_exams + 1):
                papers = [p for p in e.paper_list if p.day == day]
                if papers:
                    if e.num_exams == 1:
                        text += '<h2>Papers</h2>\n'
                    else:
                        text += '<h2>Day %d papers</h2>\n' % day
                    text += '<ul>\n'
                    for p in papers:
                        if p.description:
                            desc = ' (%s)' % p.description
                        else:
                            desc = ''
                        text += ('<li>%s%s</li>\n'
                                 % (self.html_a(cgi.escape(p.language), p.url),
                                    cgi.escape(desc)))
                    text += '</ul>\n'
        title = cgi.escape(e.short_name_with_year_and_country)
        header = ('%s in %s'
                  % (cgi.escape(e.short_name_with_year),
                     self.link_for_country(
                         e.host_country,
                         cgi.escape(e.host_country_name_in))))
        self.write_html_to_file(text, title, header, self.path_for_event(e))

    def generate_one_event_countries_summary(self, e):
        """Generate a summary list of the countries at one event."""
        text = ''
        text += ('<p>Details of all countries at this %s may also be %s'
                 ' in CSV format.</p>\n'
                 % (cgi.escape(e.short_name),
                    self.link_for_event_countries_csv(e, 'downloaded')))
        head_row = ['Code', 'Name']
        if e.distinguish_official:
            head_row.extend([cgi.escape(self._cfg['official_desc'])])
        head_row_list = [self.html_tr_th_list(head_row)]
        body_row_list = []
        countries = sorted(e.country_list, key=lambda x: x.sort_key)
        for c in countries:
            row = [self.link_for_country_at_event(c, cgi.escape(c.code)),
                   self.link_for_country_at_event(c, cgi.escape(c.name))]
            if e.distinguish_official:
                row.extend([c.is_official and 'Yes' or 'No'])
            row = self.html_tr_td_list(row)
            body_row_list.append(row)
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'
        title = ('Countries at %s'
                 % cgi.escape(e.short_name_with_year_and_country))
        header = 'Countries at ' + self.link_for_event_and_host(e)
        self.write_html_to_file(text, title, header,
                                self.path_for_event_countries(e))

    def event_people_table(self, e):
        """Generate the table of people at one event."""
        ctext_list = []
        countries = sorted(e.country_list, key=lambda x: x.sort_key)
        for c in countries:
            text = ''
            people = sorted(c.person_list, key=lambda x: x.sort_key)
            cl = self.link_for_country_at_event(c,
                                                cgi.escape(c.name_with_code))
            text += '<h2>%s</h2>\n' % cl
            head_row_list = [self.html_tr_th_list(['Given Name', 'Family Name',
                                                   'Role'])]
            body_row_list = []
            for p in people:
                row = self.html_tr_td_list(
                    [self.link_for_person(p.person, cgi.escape(p.given_name)),
                     self.link_for_person(p.person, cgi.escape(p.family_name)),
                     cgi.escape(p.primary_role)])
                body_row_list.append(row)
            text += self.html_table_thead_tbody_list(head_row_list,
                                                     body_row_list)
            ctext_list.append(text)
        return '\n'.join(ctext_list)

    def generate_one_event_people_summary(self, e):
        """Generate a summary list of the people at one event."""
        text = ''
        text += ('<p>Details of all people at this %s may also be %s'
                 ' in CSV format.</p>\n'
                 % (cgi.escape(e.short_name),
                    self.link_for_event_people_csv(e, 'downloaded')))
        text += self.event_people_table(e)
        text += '\n'
        title = 'People at ' + cgi.escape(e.short_name_with_year_and_country)
        header = 'People at ' + self.link_for_event_and_host(e)
        self.write_html_to_file(text, title, header,
                                self.path_for_event_people(e))

    def person_scoreboard_header(self, event, show_rank=True, show_code=True,
                                 show_name=True, show_award=True):
        """Generate the header for a scoreboard for individual people."""
        row = []
        if show_rank:
            row.extend([self.html_th_scores('#', title='Rank')])
            if event.distinguish_official:
                row.extend([self.html_th_scores(
                    '#<sub>O</sub>',
                    title='Rank (%s)' % self._cfg['official_desc_lc'])])
        if show_code:
            row.extend([self.html_th_scores('Code')])
        if show_name:
            row.extend([self.html_th_scores('Name')])
        row.extend([self.html_th_scores('P%d' % (i + 1))
                    for i in range(event.num_problems)])
        row.extend([self.html_th_scores('&Sigma;', title='Total score')])
        if show_award:
            row.extend([self.html_th_scores('Award')])
        return self.html_tr_list(row)

    def person_scoreboard_row(self, p, show_rank=True, show_code=True,
                              show_name=True, show_range=True, show_award=True,
                              link=True):
        """Generate the scoreboard row for one person."""
        scores_row = []
        for i in range(p.event.num_problems):
            s = p.problem_scores[i]
            if s is None:
                s = ''
            else:
                s = str(s)
            scores_row.append(s)
        row = []
        if show_rank:
            row.extend([str(p.rank)])
            if p.event.distinguish_official:
                row.extend([''
                            if p.rank_official is None
                            else str(p.rank_official)])
        if link:
            linker = self.link_for_person
        else:
            def linker(person, text):
                return text
        if show_code:
            row.extend([linker(p.person, cgi.escape(p.contestant_code))])
        if show_name:
            row.extend([linker(p.person, cgi.escape(p.name))])
        row.extend(scores_row)
        total_score_str = str(p.total_score)
        if not p.have_any_scores:
            total_score_str = ''
        elif show_range and p.max_total_score > p.total_score:
            total_score_str = ('%d (max %d)'
                               % (p.total_score, p.max_total_score))
        row.extend([total_score_str])
        if show_award:
            row.extend([cgi.escape(p.awards_str)])
        return self.html_tr_td_scores_list(row)

    def country_scoreboard_header(self, event, country):
        """Generate the header for a scoreboard for countries."""
        assert event or country
        if event:
            show_year = False
            show_rank_official = event.distinguish_official
            num_problems_to_show = event.num_problems
            total_top_n_header = event.rank_top_n_if_matters
            show_hm = event.honourable_mentions_available
        else:
            show_year = True
            show_rank_official = self._data.distinguish_official
            num_problems_to_show = country.max_num_problems
            total_top_n_header = None
            show_hm = country.honourable_mentions_available
        row = []
        if show_year:
            row.append(self.html_th_scores('Year'))
        row.append(self.html_th_scores('#', title='Rank'))
        if show_rank_official:
            row.append(self.html_th_scores(
                '#<sub>O</sub>',
                title='Rank (%s)' % self._cfg['official_desc_lc']))
        if not show_year:
            row.append(self.html_th_scores('Country'))
        row.append(self.html_th_scores('Size'))
        row.extend([self.html_th_scores('P%d' % (i + 1))
                    for i in range(num_problems_to_show)])
        row.extend([self.html_th_scores('&Sigma;', title='Total score')])
        if total_top_n_header is not None:
            row.extend([self.html_th_scores(('&Sigma;<sub>%d</sub>'
                                             % total_top_n_header),
                                            title=('Total score (top %d)'
                                                   % total_top_n_header))])
        row.extend([self.html_th_scores('G', title='Gold'),
                    self.html_th_scores('S', title='Silver'),
                    self.html_th_scores('B', title='Bronze')])
        if show_hm:
            row.extend([self.html_th_scores('HM', title='Honourable Mention')])
        return self.html_tr_list(row)

    def country_scoreboard_row(self, event, c):
        """Generate the scoreboard row for one country."""
        if event:
            assert event is c.event
            show_year = False
            show_rank_official = event.distinguish_official
            num_problems_to_show = event.num_problems
            total_top_n = event.rank_top_n_matters
            show_hm = event.honourable_mentions_available
        else:
            show_year = True
            show_rank_official = self._data.distinguish_official
            num_problems_to_show = c.country.max_num_problems
            total_top_n = None
            show_hm = c.country.honourable_mentions_available
        row = []
        if show_year:
            row.append(
                self.link_for_country_at_event(c,
                                               cgi.escape(c.event.year)))
        row.append(str(c.rank))
        if show_rank_official:
            row.append('' if c.rank_official is None else str(c.rank_official))
        if not show_year:
            row.append(
                self.link_for_country_at_event(c,
                                               cgi.escape(c.name_with_code)))
        row.append(str(c.num_contestants))
        for i in range(c.event.num_problems):
            t = c.problem_totals[i]
            tmax = c.max_problem_totals[i]
            if not c.have_any_problem_scores[i]:
                s = ''
            elif t < tmax:
                s = '%d (max %d)' % (t, tmax)
            else:
                s = str(t)
            row.append(s)
        row.extend(['' for i in range(c.event.num_problems,
                                      num_problems_to_show)])
        t = c.total_score
        tmax = c.max_total_score
        if not c.have_any_scores:
            s = ''
        elif t < tmax:
            s = '%d (max %d)' % (t, tmax)
        else:
            s = str(t)
        row.append(s)
        if total_top_n:
            t = c.total_score_for_rank
            tmax = c.max_total_score_for_rank
            if not c.have_any_scores:
                s = ''
            elif t < tmax:
                s = '%d (max %d)' % (t, tmax)
            else:
                s = str(t)
            row.append(s)
        row.extend([(c.num_awards['Gold Medal'] is not None
                     and str(c.num_awards['Gold Medal']) or ''),
                    (c.num_awards['Silver Medal'] is not None
                     and str(c.num_awards['Silver Medal']) or ''),
                    (c.num_awards['Bronze Medal'] is not None
                     and str(c.num_awards['Bronze Medal']) or '')])
        if show_hm:
            hm_text = ''
            if (c.event.honourable_mentions_available
                and c.num_awards['Honourable Mention'] is not None):
                hm_text = str(c.num_awards['Honourable Mention'])
            row.extend([hm_text])
        return self.html_tr_td_scores_list(row)

    def num_text_contestants(self, n):
        """Return text describing a number of contestants."""
        if n == 1:
            return '1 contestant'
        else:
            return '%d contestants' % n

    def num_text_gold(self, n):
        """Return text describing a number of gold medals."""
        if n == 1:
            return '1 gold medal'
        else:
            return '%d gold medals' % n

    def num_text_silver(self, n):
        """Return text describing a number of silver medals."""
        if n == 1:
            return '1 silver medal'
        else:
            return '%d silver medals' % n

    def num_text_bronze(self, n):
        """Return text describing a number of bronze medals."""
        if n == 1:
            return '1 bronze medal'
        else:
            return '%d bronze medals' % n

    def num_text_hm(self, n):
        """Return text describing a number of honourable mentions."""
        if n == 1:
            return '1 honourable mention'
        else:
            return '%d honourable mentions' % n

    def cum_stat_text(self, nmin, nmax):
        """Return text for an entry in the cumulative statistics table."""
        if nmin == nmax:
            return str(nmin)
        else:
            return '%d (max %d)' % (nmin, nmax)

    def scoreboard_text(self, e):
        """Return the main text of the scoreboard for one event."""
        text = ''
        countries = e.country_with_contestants_list
        contestants = sorted(e.contestant_list, key=lambda x: x.sort_key)
        num_problems = e.num_problems

        text += '<h2>Scores by contestant code</h2>\n'
        head_row_list = [self.person_scoreboard_header(e)]
        body_row_list = []
        for p in contestants:
            body_row_list.append(self.person_scoreboard_row(p))
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'

        text += '<h2>Ranked scores</h2>\n'
        body_row_list = []
        rank_sorted_contestants = sorted(contestants, key=lambda x: x.rank)
        for p in rank_sorted_contestants:
            body_row_list.append(self.person_scoreboard_row(p))
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'

        text += '<h2>Statistics</h2>\n'
        if e.scores_final:
            hm_text = ''
            if e.honourable_mentions_available:
                hm_text = ', ' + self.num_text_hm(
                    e.num_awards['Honourable Mention'])
            text += ('<p>%s (scores &ge; %d),'
                     ' %s (scores &ge; %d),'
                     ' %s (scores &ge; %d)%s'
                     ' from %s'
                     ' total.</p>\n'
                     % (self.num_text_gold(e.num_awards['Gold Medal']),
                        e.gold_boundary,
                        self.num_text_silver(e.num_awards['Silver Medal']),
                        e.silver_boundary,
                        self.num_text_bronze(e.num_awards['Bronze Medal']),
                        e.bronze_boundary,
                        hm_text, self.num_text_contestants(e.num_contestants)))
            if e.distinguish_official:
                hm_text = ''
                if e.honourable_mentions_available:
                    hm_text = ', ' + self.num_text_hm(
                        e.num_awards_official['Honourable Mention'])
                text += ('<p>From %s teams: %s, %s,'
                         ' %s%s'
                         ' from %s total.</p>\n'
                         % (cgi.escape(self._cfg['official_desc_lc']),
                            self.num_text_gold(
                                e.num_awards_official['Gold Medal']),
                            self.num_text_silver(
                                e.num_awards_official['Silver Medal']),
                            self.num_text_bronze(
                                e.num_awards_official['Bronze Medal']),
                            hm_text,
                            self.num_text_contestants(
                                e.num_contestants_official)))
        else:
            if e.distinguish_official:
                off_text = (' (%d from %s teams)'
                            % (e.num_contestants_official,
                               cgi.escape(self._cfg['official_desc_lc'])))
            else:
                off_text = ''
            text += ('<p>%s%s.</p>\n'
                     % (self.num_text_contestants(e.num_contestants),
                        off_text))
        head_row = ['Total score',
                    'Candidates',
                    'Cumulative']
        if e.distinguish_official:
            head_row.extend([('Cumulative (%s)'
                              % cgi.escape(self._cfg['official_desc_lc']))])
        head_row_list = [self.html_tr_th_scores_list(head_row)]
        body_row_list = []
        ctot = 0
        ctot_max = 0
        ctot_official = 0
        ctot_max_official = 0
        for i in range(e.marks_total, -1, -1):
            this_tot = e.total_stats[i]
            ctot += this_tot
            ctot_max += e.max_total_stats[i]
            row = [str(i), str(this_tot), self.cum_stat_text(ctot, ctot_max)]
            if e.distinguish_official:
                ctot_official += e.total_stats_official[i]
                ctot_max_official += e.max_total_stats_official[i]
                row.extend([self.cum_stat_text(ctot_official,
                                               ctot_max_official)])
            body_row_list.append(self.html_tr_td_scores_list(row))
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'

        total_mean_std_dev = e.total_mean_std_dev
        if total_mean_std_dev is not None:
            text += ('<p>Mean score = %.3f; standard deviation = %.3f.</p>\n'
                     % total_mean_std_dev)

        text += '<h2>Statistics by problem</h2>\n'
        row_list = []
        row = ['']
        row.extend(['P%d' % (i + 1) for i in range(num_problems)])
        row_list.append(self.html_tr_th_scores_list(row))
        for i in range(e.max_marks_per_problem + 1):
            row = [self.html_th_scores('Score = %d' % i)]
            for j in range(num_problems):
                if i <= e.marks_per_problem[j]:
                    s = str(e.problem_stats[j][i])
                else:
                    s = ''
                row.append(self.html_td_scores(s))
            row_list.append(self.html_tr_list(row))
        row = [self.html_th_scores('Mean(Score)')]
        for j in range(num_problems):
            if e.problem_mean[j] is None:
                s = ''
            else:
                s = '%.3f' % e.problem_mean[j]
            row.append(self.html_td_scores(s))
        row_list.append(self.html_tr_list(row))
        row = [self.html_th_scores('&sigma;(Score)')]
        for j in range(num_problems):
            if e.problem_std_dev[j] is None:
                s = ''
            else:
                s = '%.3f' % e.problem_std_dev[j]
            row.append(self.html_td_scores(s))
        row_list.append(self.html_tr_list(row))
        row = [self.html_th_scores('Corr(Score, Total)')]
        for j in range(num_problems):
            corr = e.problem_corr_with_total[j]
            if corr is None:
                s = ''
            elif corr < 0:
                s = '&minus;%.3f' % -corr
            else:
                s = '%.3f' % corr
            row.append(self.html_td_scores(s))
        row_list.append(self.html_tr_list(row))
        text += self.html_table_list(row_list)
        text += '\n'

        text += '<h2>Correlation coefficients between problems</h2>\n'
        row_list = []
        row = ['']
        row.extend(['P%d' % (i + 1) for i in range(num_problems)])
        row_list.append(self.html_tr_th_scores_list(row))
        for i in range(num_problems):
            row = [self.html_th_scores('P%d' % (i + 1))]
            for j in range(num_problems):
                corr = e.problem_corr[i][j]
                if corr is None or i == j:
                    s = ''
                elif corr < 0:
                    s = '&minus;%.3f' % -corr
                else:
                    s = '%.3f' % corr
                row.append(self.html_td_scores(s))
            row_list.append(self.html_tr_list(row))
        text += self.html_table_list(row_list)
        text += '\n'

        text += '<h2>Country results</h2>\n'
        head_row_list = [self.country_scoreboard_header(e, None)]
        rank_sorted_countries = sorted(countries, key=lambda x: x.sort_key)
        rank_sorted_countries = sorted(rank_sorted_countries,
                                       key=lambda x: x.rank)
        body_row_list = []
        for c in rank_sorted_countries:
            body_row_list.append(self.country_scoreboard_row(e, c))
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        text += '\n'

        if e.rank_top_n_matters:
            text += ('<p>Country ranks are determined by the total score of'
                     ' the top %s from each country.</p>\n'
                     % self.num_text_contestants(e.rank_top_n))

        if not e.scores_final:
            text += ('<p>The statistics by problem only include the'
                     ' scores shown on the scoreboard; correlation'
                     ' coefficients between problems only include contestants'
                     ' with scores shown for both problems.  Other statistics'
                     ' treat such blanks as 0.</p>\n')

        return text

    def generate_one_event_scoreboard(self, e):
        """Generate a scoreboard for one event."""
        text = ''
        rss_file = os.path.join(self._out_dir,
                                *self.path_for_event_scores_rss(e))
        if os.access(rss_file, os.F_OK):
            rss_note = ('  An %s is also available.'
                        % self.link_for_event_scores_rss(e, 'RSS feed of the'
                                                         ' scores as they were'
                                                         ' published'))
        else:
            rss_note = ''
        text += ('<p>The table of scores may also be %s in CSV format.'
                 '%s</p>\n'
                 % (self.link_for_event_scores_csv(e, 'downloaded'),
                    rss_note))

        text += self.scoreboard_text(e)

        title = ('Scoreboard for %s'
                 % cgi.escape(e.short_name_with_year_and_country))
        header = 'Scoreboard for %s' % self.link_for_event_and_host(e)
        self.write_html_to_file(text, title, header,
                                self.path_for_event_scoreboard(e))

    def generate_redirect(self, src_url, src_query_string, dest_url):
        """Generate a single redirect."""
        text = ''
        src_path = re.sub('^https?://[^/]*', '', src_url)
        text += 'RewriteCond %{REQUEST_URI} ^' + src_path + '$\n'
        if src_query_string != '':
            text += 'RewriteCond %{QUERY_STRING} ^' + src_query_string + '$\n'
        text += 'RewriteRule ^.* ' + dest_url + '? [R=301,L]\n'
        return text

    def generate_redirect_file(self, src_url, src_query_string, dest_path):
        """Generate a single redirect to a file."""
        dest_url = self._cfg['url_base'] + '/'.join(dest_path)
        return self.generate_redirect(src_url, src_query_string, dest_url)

    def generate_redirect_page(self, src_url, src_query_string, dest_path):
        """Generate a single redirect to a page (ending with '/')."""
        dest_url = self._cfg['url_base'] + '/'.join(dest_path) + '/'
        return self.generate_redirect(src_url, src_query_string, dest_url)

    def generate_one_event_redirects(self, e):
        """Generate redirects from registration system at one event."""
        e_redirects_out = os.path.join(self._auto_out_dir,
                                       'redirects-%d' % e.id)
        text = ''
        base_url = ''
        countries = sorted(e.country_list, key=lambda x: x.sort_key)
        people = sorted(e.person_list, key=lambda x: x.sort_key)
        for c in countries:
            src_url = c.annual_url
            if src_url:
                text += self.generate_redirect_page(
                    src_url, '',
                    self.path_for_country_at_event(c))
                this_base_url = re.sub('country[0-9]*$', '', src_url)
                if base_url:
                    if this_base_url != base_url:
                        raise ValueError('annual URL inconsistency: %s != %s'
                                         % (base_url, this_base_url))
                else:
                    base_url = this_base_url
        if not base_url:
            return
        src_url = base_url + 'country'
        dest_path = self.path_for_event_countries_csv(e)
        text += self.generate_redirect_file(src_url, '@action=country_csv',
                                            dest_path)
        text += self.generate_redirect_file(src_url, '%40action=country_csv',
                                            dest_path)
        src_url = base_url + 'country'
        dest_path = self.path_for_event_scores_rss(e)
        text += self.generate_redirect_file(src_url, '@action=scores_rss',
                                            dest_path)
        text += self.generate_redirect_file(src_url, '%40action=scores_rss',
                                            dest_path)
        src_url = base_url + 'country'
        dest_path = self.path_for_event_countries(e)
        text += self.generate_redirect_page(src_url, '', dest_path)
        for p in people:
            src_url = p.annual_url
            if src_url:
                dest_path = self.path_for_person(p.person)
                text += self.generate_redirect_page(src_url, '', dest_path)
        src_url = base_url + 'person'
        dest_path = self.path_for_event_scoreboard(e)
        text += self.generate_redirect_page(src_url, '@template=scoreboard',
                                            dest_path)
        text += self.generate_redirect_page(src_url, '%40template=scoreboard',
                                            dest_path)
        src_url = base_url + 'person'
        dest_path = self.path_for_event_people_csv(e)
        text += self.generate_redirect_file(src_url, '@action=people_csv',
                                            dest_path)
        text += self.generate_redirect_file(src_url, '%40action=people_csv',
                                            dest_path)
        src_url = base_url + 'person'
        dest_path = self.path_for_event_scores_csv(e)
        text += self.generate_redirect_file(src_url, '@action=scores_csv',
                                            dest_path)
        text += self.generate_redirect_file(src_url, '%40action=scores_csv',
                                            dest_path)
        src_url = base_url + 'person'
        dest_path = self.path_for_event_people(e)
        text += self.generate_redirect_page(src_url, '', dest_path)
        src_url = base_url
        dest_path = self.path_for_event_countries(e)
        text += self.generate_redirect_page(src_url, '', dest_path)
        write_text_to_file(text, e_redirects_out)

    def country_event_scores_table(self, c, show_rank=True):
        """
        Generate the table of contestant scores for one country at one
        event, given that this country has contestants.
        """
        c_contestants = sorted(c.contestant_list, key=lambda x: x.sort_key)
        head_row_list = [self.person_scoreboard_header(c.event,
                                                       show_rank=show_rank)]
        body_row_list = []
        for p in c_contestants:
            body_row_list.append(self.person_scoreboard_row(
                p, show_rank=show_rank))
        return self.html_table_thead_tbody_list(head_row_list,
                                                body_row_list)

    def country_event_people_table(self, c, show_photos):
        """Generate the table of people for one country at one event."""
        text = ''
        c_people = sorted(c.person_list, key=lambda x: x.sort_key)
        c_guides = sorted(c.guide_list, key=lambda x: x.sort_key)
        c_people.extend(c_guides)
        hrow = ['Given Name', 'Family Name', 'Role']
        if show_photos:
            hrow.append('Photo')
        head_row_list = [self.html_tr_th_list(hrow)]
        body_row_list = []
        for p in c_people:
            if p.photo_url:
                photo = self.html_img(width='150', alt='', src=p.photo_url)
            else:
                photo = ''
            row = [self.link_for_person(p.person, cgi.escape(p.given_name)),
                   self.link_for_person(p.person, cgi.escape(p.family_name)),
                   cgi.escape(p.primary_role)]
            if show_photos:
                row.append(photo)
            body_row_list.append(self.html_tr_td_list(row))
        text += self.html_table_thead_tbody_list(head_row_list, body_row_list)
        return text

    def country_event_text(self, c, h_level, show_photos):
        """Generate the text for one country at one event."""
        text = ''
        text += '<%s>Participants</%s>\n' % (h_level, h_level)
        text += self.country_event_people_table(c, show_photos)
        text += '\n'
        if c.num_contestants:
            text += '<%s>Scores</%s>\n' % (h_level, h_level)
            text += self.country_event_scores_table(c)
            text += '\n'
        return text

    def generate_one_event_country_page(self, c):
        """Generate a page for one country at one event."""
        text = ''
        if c.flag_url:
            text += ('<p class="%s">%s</p>\n'
                     % (self._cfg['photo_css'],
                        self.html_img(width='300', alt='', src=c.flag_url)))
        text += self.country_event_text(c, 'h2', True)

        if c.num_contestants:
            text += '<h2>National results</h2>\n'
            head_row_list = [self.country_scoreboard_header(c.event, None)]
            body_row_list = [self.country_scoreboard_row(c.event, c)]
            text += self.html_table_thead_tbody_list(head_row_list,
                                                     body_row_list)
            text += '\n'

        title = ('%s at %s' % (c.name_with_code,
                               c.event.short_name_with_year_and_country))
        title = cgi.escape(title)
        header = ('%s (%s) at %s'
                  % (self.link_for_country(c.country, cgi.escape(c.name)),
                     self.link_for_country(c.country, cgi.escape(c.code)),
                     self.link_for_event_and_host(c.event)))
        self.write_html_to_file(text, title, header,
                                self.path_for_country_at_event(c))

    def generate_one_country_page(self, cd):
        """Generate main page for one country."""
        text = ''
        if cd.flag_url:
            text += ('<p class="%s">%s</p>\n'
                     % (self._cfg['photo_css'],
                        self.html_img(width='300', alt='', src=cd.flag_url)))
        host = self.host_year_text(cd)
        if host:
            text += ('<p><strong>%s host</strong>: %s.</p>\n'
                     % (cgi.escape(self._data.short_name), host))
        year_list = []
        year_list_table = []
        for c in cd.participation_list:
            e = c.event
            year_text = ''
            cltxt = ('%s at %s'
                     % (cgi.escape(c.name_with_code),
                        cgi.escape(e.short_name_with_year)))
            hl = self.link_for_country(e.host_country,
                                       cgi.escape(e.host_country_name_in))
            year_text += ('<h2>%s in %s</h2>\n'
                          % (self.link_for_country_at_event(c, cltxt), hl))
            year_text += self.country_event_text(c, 'h3', False)
            year_list.append(year_text)
            if c.num_contestants:
                year_list_table.append(self.country_scoreboard_row(None, c))
        year_list.reverse()
        year_list_table.reverse()
        if year_list_table:
            text += '<h2>National results</h2>\n'
            head_row_list = [self.country_scoreboard_header(None, cd)]
            text += self.html_table_thead_tbody_list(head_row_list,
                                                     year_list_table)
            text += '\n'
        text += '\n'.join(year_list)
        title = cgi.escape(cd.name_with_code)
        self.write_html_to_file(text, title, title, self.path_for_country(cd))

    def person_event_scores_table(self, p, show_rank=True, show_code=True,
                                  show_name=True):
        """
        Generate the table of scores for one person at one event,
        given that this person was a contestant there.
        """
        head_row_list = [self.person_scoreboard_header(p.event,
                                                       show_rank=show_rank,
                                                       show_code=show_code,
                                                       show_name=show_name)]
        body_row_list = [self.person_scoreboard_row(p, show_rank=show_rank,
                                                    show_code=show_code,
                                                    show_name=show_name)]
        return self.html_table_thead_tbody_list(head_row_list,
                                                body_row_list)

    def generate_one_person_page(self, pd):
        """Generate main page for one person."""
        text = ''
        year_list = []
        age_desc_list = []
        for p in pd.participation_list:
            e = p.event
            year_text = ''
            el = self.link_for_event(e, cgi.escape(e.short_name_with_year))
            year_text += '<h2>%s</h2>\n' % el
            year_text += '<table>\n<tr><td>\n'
            cl = self.link_for_country_at_event(p.country,
                                                cgi.escape(p.country.name))
            year_rows = [['Country', cl],
                         ['Given name', cgi.escape(p.given_name)],
                         ['Family name', cgi.escape(p.family_name)],
                         ['Primary role', cgi.escape(p.primary_role)]]
            if p.other_roles:
                rs = sorted(p.other_roles, key=coll_get_sort_key)
                year_rows.append(['Other roles', cgi.escape(', '.join(rs))])
            if p.guide_for:
                glist = sorted(p.guide_for, key=lambda x: x.sort_key)
                gtlist = []
                for c in glist:
                    cl = self.link_for_country_at_event(c, cgi.escape(c.name))
                    gtlist.append(cl)
                year_rows.append(['Guide for', ', '.join(gtlist)])
            if p.is_contestant and p.contestant_age is not None:
                year_rows.append(['Contestant age', str(p.contestant_age)])
                age_desc = e.age_day_desc
                if age_desc_list and age_desc_list[-1][0] == age_desc:
                    age_desc_list[-1][2] = e.year
                else:
                    age_desc_list.append([age_desc, e.year, e.year])
            year_text += self.html_table_list_th_td(year_rows) + '\n'
            year_text += '</td><td>\n'
            if p.photo_url:
                year_text += self.html_img(width='200', alt='',
                                           src=p.photo_url)
            year_text += '</td></tr>\n</table>\n'
            if p.is_contestant:
                year_text += '<h3>Scores</h3>\n'
                year_text += self.person_event_scores_table(p)
                year_text += '\n'
            year_list.append(year_text)
        year_list.reverse()
        text += '\n'.join(year_list)
        if len(age_desc_list) > 1:
            age_text_list = []
            for a in age_desc_list:
                if a[1] == a[2]:
                    age_text_list.append('%s (%s)' % (a[0], a[1]))
                else:
                    age_text_list.append('%s (%s&ndash;%s)'
                                         % (a[0], a[1], a[2]))
            age_text = ', '.join(age_text_list)
            text += '<p>Contestant ages are given on %s.</p>\n' % age_text
        elif age_desc_list:
            text += ('<p>Contestant ages are given on %s at each %s.</p>\n'
                     % (cgi.escape(age_desc_list[0][0]),
                        cgi.escape(self._data.short_name)))
        title = cgi.escape(pd.name)
        header = title
        self.write_html_to_file(text, title, header, self.path_for_person(pd))

    def generate_events_csv(self):
        """Generate the CSV file for all events."""
        events_data_output = []
        for e in self._data.event_list:
            csv_out = {}
            csv_out['Number'] = str(e.id)
            csv_out['Year'] = e.year
            csv_out['Country Number'] = str(e.host_country.id)
            csv_out['Country'] = e.host_country_name
            csv_out['Country Name In'] = e.host_country_name_in
            csv_out['City'] = e.host_city or ''
            csv_out['Start Date'] = date_to_ymd_iso(e.start_date)
            csv_out['End Date'] = date_to_ymd_iso(e.end_date)
            csv_out['Home Page URL'] = e.home_page_url or ''
            csv_out['Contact Name'] = e.contact_name or ''
            csv_out['Contact Email'] = e.contact_email or ''
            csv_out['Number of Exams'] = str(e.num_exams or '')
            csv_out['Number of Problems'] = str(e.num_problems or '')
            if e.num_problems:
                for i in range(self._data.max_num_problems):
                    if i < e.num_problems:
                        csv_out['P%d Max' % (i + 1)] = \
                            str(e.marks_per_problem[i])
                    else:
                        csv_out['P%d Max' % (i + 1)] = ''
            else:
                for i in range(self._data.max_num_problems):
                    csv_out['P%d Max' % (i + 1)] = ''
            if e.num_contestants:
                csv_out['Gold Boundary'] = str(e.gold_boundary)
                csv_out['Silver Boundary'] = str(e.silver_boundary)
                csv_out['Bronze Boundary'] = str(e.bronze_boundary)
            else:
                csv_out['Gold Boundary'] = ''
                csv_out['Silver Boundary'] = ''
                csv_out['Bronze Boundary'] = ''
            if self._data.honourable_mentions_available_varies:
                csv_out['Honourable Mentions Available'] = \
                    e.honourable_mentions_available and 'Yes' or 'No'
            if self._data.distinguish_official_varies:
                csv_out['Distinguish Official Countries'] = \
                    e.distinguish_official and 'Yes' or 'No'
            if self._data.age_day_desc_varies:
                csv_out['Age Day Description'] = e.age_day_desc
            if e.num_contestants:
                csv_out['Contestants'] = str(e.num_contestants)
                csv_out['Gold Medals'] = str(e.num_awards['Gold Medal'])
                csv_out['Silver Medals'] = str(e.num_awards['Silver Medal'])
                csv_out['Bronze Medals'] = str(e.num_awards['Bronze Medal'])
                if self._data.honourable_mentions_available:
                    if e.honourable_mentions_available:
                        csv_out['Honourable Mentions'] = \
                            str(e.num_awards['Honourable Mention'])
                    else:
                        csv_out['Honourable Mentions'] = ''
                csv_out['Number of Teams'] = str(e.num_countries)
                if e.distinguish_official:
                    csv_out[self._cfg['official_adj'] + ' Contestants'] = \
                        str(e.num_contestants_official)
                    csv_out[self._cfg['official_adj'] + ' Gold Medals'] = \
                        str(e.num_awards_official['Gold Medal'])
                    csv_out[self._cfg['official_adj'] + ' Silver Medals'] = \
                        str(e.num_awards_official['Silver Medal'])
                    csv_out[self._cfg['official_adj'] + ' Bronze Medals'] = \
                        str(e.num_awards_official['Bronze Medal'])
                    csv_out[self._cfg['official_adj']
                            + ' Honourable Mentions'] = \
                        str(e.num_awards_official['Honourable Mention'])
                    csv_out['Number of ' + self._cfg['official_adj']
                            + ' Teams'] = str(e.num_countries_official)
            else:
                csv_out['Contestants'] = ''
                csv_out['Gold Medals'] = ''
                csv_out['Silver Medals'] = ''
                csv_out['Bronze Medals'] = ''
                if self._data.honourable_mentions_available:
                    csv_out['Honourable Mentions'] = ''
                csv_out['Number of Teams'] = ''
            if (self._data.distinguish_official
                and (not e.distinguish_official or not e.num_contestants)):
                csv_out[self._cfg['official_adj'] + ' Contestants'] = ''
                csv_out[self._cfg['official_adj'] + ' Gold Medals'] = ''
                csv_out[self._cfg['official_adj'] + ' Silver Medals'] = ''
                csv_out[self._cfg['official_adj'] + ' Bronze Medals'] = ''
                csv_out[self._cfg['official_adj'] + ' Honourable Mentions'] = \
                    ''
                csv_out['Number of ' + self._cfg['official_adj']
                        + ' Teams'] = ''
            events_data_output.append(csv_out)
        events_columns = ['Number', 'Year', 'Country Number', 'Country',
                          'Country Name In', 'City', 'Start Date', 'End Date',
                          'Home Page URL', 'Contact Name',
                          'Contact Email', 'Number of Exams',
                          'Number of Problems']
        events_columns.extend(['P%d Max' % (i + 1)
                               for i in range(self._data.max_num_problems)])
        events_columns.extend(['Gold Boundary', 'Silver Boundary',
                               'Bronze Boundary'])
        if self._data.honourable_mentions_available_varies:
            events_columns.extend(['Honourable Mentions Available'])
        if self._data.distinguish_official_varies:
            events_columns.extend(['Distinguish Official Countries'])
        if self._data.age_day_desc_varies:
            events_columns.extend(['Age Day Description'])
        events_columns.extend(['Contestants', 'Gold Medals', 'Silver Medals',
                               'Bronze Medals'])
        if self._data.honourable_mentions_available:
            events_columns.extend(['Honourable Mentions'])
        events_columns.extend(['Number of Teams'])
        if self._data.distinguish_official:
            events_columns.extend([self._cfg['official_adj'] + ' Contestants',
                                   self._cfg['official_adj'] + ' Gold Medals',
                                   self._cfg['official_adj']
                                   + ' Silver Medals',
                                   self._cfg['official_adj']
                                   + ' Bronze Medals'])
            if self._data.honourable_mentions_available:
                events_columns.extend([self._cfg['official_adj']
                                       + ' Honourable Mentions'])
            events_columns.extend(['Number of ' + self._cfg['official_adj']
                                   + ' Teams'])
        self.write_csv_to_file(self.path_for_data_events(), events_data_output,
                               events_columns)

    def pn_csv_header(self, num_problems):
        """Return list of Pn headers for CSV file."""
        return [('P%d' % (i + 1)) for i in range(num_problems)]

    def countries_csv_columns(self, event, reg_system=False,
                              private_data=False):
        """Return list of headers for CSV file of countries."""
        if event:
            num_problems = event.num_problems
            distinguish_official = event.distinguish_official
            show_hm = event.honourable_mentions_available
        else:
            num_problems = self._data.max_num_problems
            distinguish_official = self._data.distinguish_official
            show_hm = self._data.honourable_mentions_available
        cols = [self._cfg['num_key'], 'Country Number', 'Annual URL',
                'Code', 'Name', 'Flag URL']
        if reg_system:
            cols.extend(['Generic Number'])
        if distinguish_official:
            cols.extend([self._cfg['official_desc']])
        cols.extend(['Normal'])
        if private_data:
            cols.extend(['Contact Emails'])
        if not reg_system:
            cols.extend(['Contestants', 'Gold Medals', 'Silver Medals',
                         'Bronze Medals'])
            if show_hm:
                cols.extend(['Honourable Mentions'])
            cols.extend(['Total Score', 'Rank'])
            if distinguish_official:
                cols.extend(['%s Rank' % self._cfg['official_adj']])
            cols.extend(self.pn_csv_header(num_problems))
        return cols

    def country_csv_data(self, c, event, reg_system=False, private_data=False):
        """Return the CSV data for a given country."""
        if event:
            assert event is c.event
            num_problems = event.num_problems
            distinguish_official = event.distinguish_official
            show_hm = event.honourable_mentions_available
        else:
            num_problems = self._data.max_num_problems
            distinguish_official = self._data.distinguish_official
            show_hm = self._data.honourable_mentions_available
        csv_out = {}
        csv_out[self._cfg['num_key']] = str(c.event.id)
        csv_out['Country Number'] = str(c.country.id)
        csv_out['Annual URL'] = c.annual_url or ''
        csv_out['Code'] = c.code
        csv_out['Name'] = c.name
        csv_out['Flag URL'] = c.flag_url or ''
        if reg_system:
            if c.generic_id is None:
                csv_out['Generic Number'] = ''
            else:
                csv_out['Generic Number'] = str(c.generic_id)
        if distinguish_official:
            if c.event.distinguish_official:
                csv_out[self._cfg['official_desc']] = \
                    c.is_official and 'Yes' or 'No'
            else:
                csv_out[self._cfg['official_desc']] = ''
        csv_out['Normal'] = 'Yes' if c.is_normal else 'No'
        if private_data:
            csv_out['Contact Emails'] = comma_join(c.contact_emails)
        if not reg_system:
            if c.num_contestants:
                csv_out['Contestants'] = str(c.num_contestants)
                csv_out['Gold Medals'] = str(c.num_awards['Gold Medal'])
                csv_out['Silver Medals'] = str(c.num_awards['Silver Medal'])
                csv_out['Bronze Medals'] = str(c.num_awards['Bronze Medal'])
                if show_hm:
                    if c.event.honourable_mentions_available:
                        csv_out['Honourable Mentions'] = \
                            str(c.num_awards['Honourable Mention'])
                    else:
                        csv_out['Honourable Mentions'] = ''
                csv_out['Total Score'] = str(c.total_score)
                csv_out['Rank'] = str(c.rank)
                if distinguish_official:
                    csv_out['%s Rank' % self._cfg['official_adj']] = (
                        ''
                        if c.rank_official is None
                        else str(c.rank_official))
                for i in range(num_problems):
                    if i < c.event.num_problems:
                        csv_out['P%d' % (i + 1)] = str(c.problem_totals[i])
                    else:
                        csv_out['P%d' % (i + 1)] = ''
            else:
                csv_out['Contestants'] = ''
                csv_out['Gold Medals'] = ''
                csv_out['Silver Medals'] = ''
                csv_out['Bronze Medals'] = ''
                if show_hm:
                    csv_out['Honourable Mentions'] = ''
                csv_out['Total Score'] = ''
                csv_out['Rank'] = ''
                if distinguish_official:
                    csv_out['%s Rank' % self._cfg['official_adj']] = ''
                for i in range(num_problems):
                    csv_out['P%d' % (i + 1)] = ''
        return csv_out

    def generate_countries_csv(self):
        """Generate the CSV file for all countries."""
        countries_sorted = sorted(self._data.country_event_list,
                                  key=lambda x: x.sort_key)
        countries_data_output = [self.country_csv_data(c, None)
                                 for c in countries_sorted]
        countries_columns = self.countries_csv_columns(None)
        self.write_csv_to_file(self.path_for_data_countries(),
                               countries_data_output, countries_columns)

    def one_event_countries_csv_content(self, e, reg_system=False,
                                        private_data=False):
        """
        Return a tuple of the data and column headers for the CSV file
        for countries at one event.
        """
        e_countries_sorted = sorted(e.country_list, key=lambda x: x.sort_key)
        e_countries_data_output = [self.country_csv_data(
            c, e, reg_system=reg_system, private_data=private_data)
                                   for c in e_countries_sorted]
        e_countries_columns = self.countries_csv_columns(
            e, reg_system=reg_system, private_data=private_data)
        return (e_countries_data_output, e_countries_columns)

    def generate_one_event_countries_csv(self, e):
        """Generate the CSV file for countries at one event."""
        data = self.one_event_countries_csv_content(e)
        self.write_csv_to_file(self.path_for_event_countries_csv(e),
                               data[0], data[1])

    def people_csv_columns(self, num_problems, distinguish_official,
                           reg_system=False, private_data=False):
        """Return list of headers for CSV file of people."""
        cols = [self._cfg['num_key'], 'Country Number', 'Person Number',
                'Annual URL', 'Country Name', 'Country Code',
                'Primary Role', 'Other Roles', 'Guide For',
                'Contestant Code',
                'Contestant Age', 'Given Name', 'Family Name']
        cols.extend(self.pn_csv_header(num_problems))
        cols.extend(['Total', 'Award', 'Extra Awards', 'Photo URL'])
        if reg_system:
            cols.extend(['Generic Number'])
        if not reg_system:
            cols.extend(['Rank'])
            if distinguish_official:
                cols.extend(['%s Rank' % self._cfg['official_adj']])
        if private_data:
            cols.extend(['Gender', 'Date of Birth', 'Languages',
                         'Allergies and Dietary Requirements',
                         'T-Shirt Size', 'Arrival Place', 'Arrival Date',
                         'Arrival Time', 'Arrival Flight', 'Departure Place',
                         'Departure Date', 'Departure Time',
                         'Departure Flight', 'Room Number', 'Phone Number',
                         'Badge Photo URL', 'Consent Form URL',
                         'Passport or Identity Card Number', 'Nationality',
                         'Event Photos Consent'])
        return cols

    def person_csv_data(self, p, num_problems=None, distinguish_official=None,
                        scores_only=False, reg_system=False,
                        private_data=False):
        """Return the CSV data for a given person."""
        if num_problems is None:
            num_problems = p.event.num_problems
        if distinguish_official is None:
            distinguish_official = p.event.distinguish_official
        csv_out = {}
        if not scores_only:
            csv_out[self._cfg['num_key']] = str(p.event.id)
            csv_out['Country Number'] = str(p.country.country.id)
            csv_out['Person Number'] = str(p.person.id)
            csv_out['Annual URL'] = p.annual_url or ''
        csv_out['Country Name'] = p.country.name
        csv_out['Country Code'] = p.country.code
        if not scores_only:
            csv_out['Primary Role'] = p.primary_role
            csv_out['Other Roles'] = comma_join(sorted(p.other_roles,
                                                       key=coll_get_sort_key))
            guide_for = sorted(p.guide_for, key=lambda x: x.sort_key)
            guide_for = [c.name for c in guide_for]
            csv_out['Guide For'] = comma_join(guide_for)
        csv_out['Given Name'] = p.given_name
        csv_out['Family Name'] = p.family_name
        if not scores_only:
            csv_out['Photo URL'] = p.photo_url or ''
        if p.is_contestant:
            csv_out['Contestant Code'] = p.contestant_code
            if not scores_only:
                if p.contestant_age is None:
                    csv_out['Contestant Age'] = ''
                else:
                    csv_out['Contestant Age'] = str(p.contestant_age)
            for i in range(num_problems):
                if i < p.event.num_problems:
                    s = p.problem_scores[i]
                    if s is None:
                        s = ''
                    else:
                        s = str(s)
                    csv_out['P%d' % (i + 1)] = s
                else:
                    csv_out['P%d' % (i + 1)] = ''
            csv_out['Total'] = str(p.total_score)
            csv_out['Award'] = p.award or ''
            csv_out['Extra Awards'] = comma_join(p.extra_awards)
            if not reg_system:
                csv_out['Rank'] = str(p.rank)
                if distinguish_official:
                    csv_out['%s Rank' % self._cfg['official_adj']] = (
                        ''
                        if p.rank_official is None
                        else str(p.rank_official))
        else:
            csv_out['Contestant Code'] = ''
            if not scores_only:
                csv_out['Contestant Age'] = ''
            for i in range(num_problems):
                csv_out['P%d' % (i + 1)] = ''
            csv_out['Total'] = ''
            csv_out['Award'] = ''
            csv_out['Extra Awards'] = ''
            if not reg_system:
                csv_out['Rank'] = ''
                if distinguish_official:
                    csv_out['%s Rank' % self._cfg['official_adj']] = ''
        if reg_system and not scores_only:
            if p.generic_id is None:
                csv_out['Generic Number'] = ''
            else:
                csv_out['Generic Number'] = str(p.generic_id)
        if private_data:
            csv_out['Gender'] = p.gender or ''
            csv_out['Date of Birth'] = date_to_ymd_iso(p.date_of_birth)
            csv_out['Languages'] = comma_join(p.languages)
            csv_out['Allergies and Dietary Requirements'] = p.diet or ''
            csv_out['T-Shirt Size'] = p.tshirt or ''
            csv_out['Arrival Place'] = p.arrival_place or ''
            csv_out['Arrival Date'] = date_to_ymd_iso(p.arrival_date)
            csv_out['Arrival Time'] = time_to_hhmm(p.arrival_time)
            csv_out['Arrival Flight'] = p.arrival_flight or ''
            csv_out['Departure Place'] = p.departure_place or ''
            csv_out['Departure Date'] = date_to_ymd_iso(p.departure_date)
            csv_out['Departure Time'] = time_to_hhmm(p.departure_time)
            csv_out['Departure Flight'] = p.departure_flight or ''
            csv_out['Room Number'] = p.room_number or ''
            csv_out['Phone Number'] = p.phone_number or ''
            csv_out['Badge Photo URL'] = p.badge_photo_url or ''
            csv_out['Consent Form URL'] = p.consent_form_url or ''
            csv_out['Passport or Identity Card Number'] = (p.passport_number
                                                           or '')
            csv_out['Nationality'] = p.nationality or ''
            if p.event_photos_consent is None:
                csv_out['Event Photos Consent'] = ''
            else:
                csv_out['Event Photos Consent'] = ('Yes'
                                                   if p.event_photos_consent
                                                   else 'No')
        return csv_out

    def generate_people_csv(self):
        """Generate the CSV file for all peoples."""
        people_sorted = sorted(self._data.person_event_list,
                               key=lambda x: x.sort_key)
        people_data_output = [
            self.person_csv_data(
                p, num_problems=self._data.max_num_problems,
                distinguish_official=self._data.distinguish_official)
            for p in people_sorted]
        people_columns = \
            self.people_csv_columns(self._data.max_num_problems,
                                    self._data.distinguish_official)
        self.write_csv_to_file(self.path_for_data_people(),
                               people_data_output, people_columns)

    def one_event_people_csv_content(self, e, reg_system=False,
                                     private_data=False):
        """
        Return a tuple of the data and column headers for the CSV file
        for people at one event.
        """
        e_people_sorted = sorted(e.person_list, key=lambda x: x.sort_key)
        e_people_data_output = [self.person_csv_data(p, reg_system=reg_system,
                                                     private_data=private_data)
                                for p in e_people_sorted]
        e_people_columns = self.people_csv_columns(e.num_problems,
                                                   e.distinguish_official,
                                                   reg_system=reg_system,
                                                   private_data=private_data)
        return (e_people_data_output, e_people_columns)

    def generate_one_event_people_csv(self, e):
        """Generate the CSV file for people at one event."""
        data = self.one_event_people_csv_content(e)
        self.write_csv_to_file(self.path_for_event_people_csv(e),
                               data[0], data[1])

    def scores_csv_columns(self, num_problems, distinguish_official,
                           reg_system=False):
        """Return list of headers for CSV file of scores."""
        cols = ['Country Name', 'Country Code',
                'Contestant Code', 'Given Name', 'Family Name']
        cols.extend(self.pn_csv_header(num_problems))
        cols.extend(['Total', 'Award', 'Extra Awards'])
        if not reg_system:
            cols.extend(['Rank'])
            if distinguish_official:
                cols.extend(['%s Rank' % self._cfg['official_adj']])
        return cols

    def one_event_scores_csv_content(self, e, reg_system=False):
        """
        Return a tuple of the data and column headers for the CSV file
        for scores at one event.
        """
        e_people_sorted = sorted(e.contestant_list, key=lambda x: x.sort_key)
        e_scores_data_output = [self.person_csv_data(p, scores_only=True,
                                                     reg_system=reg_system)
                                for p in e_people_sorted]
        e_scores_columns = self.scores_csv_columns(e.num_problems,
                                                   e.distinguish_official,
                                                   reg_system=reg_system)
        return (e_scores_data_output, e_scores_columns)

    def generate_one_event_scores_csv(self, e):
        """Generate the CSV file for scores at one event."""
        data = self.one_event_scores_csv_content(e)
        self.write_csv_to_file(self.path_for_event_scores_csv(e),
                               data[0], data[1])

    def generate_site(self):
        """Generate the complete static site."""
        self.generate_sidebar_out()
        self.generate_contact_out()
        self.generate_events_summary()
        self.generate_countries_summary()
        self.generate_people_summary()
        self.generate_hall_of_fame()

        for e in self._data.event_list:
            e_extra = os.path.join(self._out_dir, *self.path_for_event(e))
            e_extra = os.path.join(e_extra, 'extra' + self._cfg['page_suffix'])
            if not os.access(e_extra, os.F_OK):
                write_text_to_file('', e_extra)
            self.generate_one_event_summary(e)
            if e.num_contestants:
                self.generate_one_event_countries_summary(e)
                self.generate_one_event_people_summary(e)
                self.generate_one_event_scoreboard(e)
                self.generate_one_event_redirects(e)
                for c in e.country_list:
                    self.generate_one_event_country_page(c)

        for c in self._data.country_list:
            self.generate_one_country_page(c)

        for p in self._data.person_list:
            self.generate_one_person_page(p)

        self.generate_events_csv()
        self.generate_countries_csv()
        self.generate_people_csv()

        for e in self._data.event_list:
            if e.num_contestants:
                self.generate_one_event_countries_csv(e)
                self.generate_one_event_people_csv(e)
                self.generate_one_event_scores_csv(e)
