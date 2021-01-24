# Test matholymp registration system.

# Copyright 2018-2021 Joseph Samuel Myers.

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
Tests for matholymp registration system.
"""

import base64
import codecs
import io
import os
import os.path
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import traceback
import unittest
import zipfile

try:
    import mechanicalsoup
    from PIL import Image
    import roundup.instance
    import roundup.password
    # roundup_server modifies sys.path on import, so save and restore it.
    _save_path = list(sys.path)
    from roundup.scripts import roundup_server
    sys.path = _save_path
    _skip_test = False
except ImportError:
    _skip_test = True

from matholymp.fileutil import read_utf8_csv, write_utf8_csv_bytes, \
    write_utf8_csv, write_bytes_to_file, write_text_to_file, \
    replace_text_in_file, read_config_raw, write_config_raw, \
    file_format_contents

__all__ = ['gen_image', 'gen_image_file', 'gen_pdf_file',
           'RoundupTestInstance', 'RoundupTestSession', 'RegSystemTestCase']


def gen_image(size_x, size_y, scale, mode):
    """Generate an image with random blocks scale by scale of pixels."""
    mode_bytes = {'L': 1,
                  'LA': 2,
                  'RGB': 3,
                  'RGBA': 4}
    nbytes = mode_bytes[mode]
    data = bytearray(size_x * size_y * scale * scale * nbytes)
    line_size = size_x * scale * nbytes
    for y in range(size_y):
        for x in range(size_x):
            for color in range(nbytes):
                pixel = random.randint(0, 255)
                for y_sub in range(scale):
                    for x_sub in range(scale):
                        x_pos = color + nbytes * (x_sub + scale * x)
                        y_pos = y_sub + scale * y
                        pos = x_pos + line_size * y_pos
                        data[pos] = pixel
    data = memoryview(data).tobytes()
    return Image.frombytes(mode, (size_x * scale, size_y * scale), data)


def gen_image_file(size_x, size_y, scale, filename, fmt, mode='RGB',
                   **kwargs):
    """Generate an image, in a file."""
    image = gen_image(size_x, size_y, scale, mode)
    image.save(filename, fmt, **kwargs)


def gen_pdf_file(dirname, suffix):
    """Generate a PDF file in the given empty directory and return its name."""
    tex_file = os.path.join(dirname, 'test.tex')
    rand_nums = [random.randint(0, 9) for n in range(20)]
    rand_text = ''.join([str(n) for n in rand_nums])
    tex_text = ('\\documentclass[a4paper]{article}\n'
                '\\begin{document}\n'
                '%s\n'
                '\\end{document}\n'
                % rand_text)
    write_text_to_file(tex_text, tex_file)
    subprocess.run(['pdflatex', tex_file], cwd=dirname,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True)
    pdf_file = os.path.join(dirname, 'test.pdf')
    ret_file = os.path.join(dirname, 'test%s' % suffix)
    if ret_file != pdf_file:
        os.rename(pdf_file, ret_file)
    return ret_file


class RoundupTestInstance:

    """
    A RoundupTestInstance provides a temporary Roundup installation
    used for testing.
    """

    def __init__(self, top_dir, temp_dir, config, coverage):
        """Initialise a RoundupTestInstance."""
        self.pid = None
        self.port = None
        self.example_dir = os.path.join(top_dir, 'examples',
                                        'online-registration')
        self.temp_dir = temp_dir
        self.instance_dir = os.path.join(self.temp_dir, 'instance')
        self.mail_file = os.path.join(self.temp_dir, 'mail')
        # Create mail file as empty to avoid needing to check for
        # existence later when checking size.
        with open(self.mail_file, 'w') as f:
            pass
        self.log_file = os.path.join(self.temp_dir, 'log')
        self.html_dir = os.path.join(self.instance_dir, 'html')
        shutil.copytree(self.example_dir, self.instance_dir)
        self.config_ini = os.path.join(self.instance_dir, 'config.ini')
        self.ext_config_ini = os.path.join(self.instance_dir, 'extensions',
                                           'config.ini')
        # Ensure that example.org references cannot leak out as actual
        # network access attempts during testing, if anything
        # mistakenly tries to send email or access CSS / favicon
        # links.
        subst_files = [self.config_ini, self.ext_config_ini,
                       os.path.join(self.html_dir, 'page.html'),
                       os.path.join(self.html_dir, 'dpage.html')]
        if config and 'static_site_directory' in config:
            # Construct a static site directory.  We assume it is to
            # be called 'static-site' relative to the Roundup
            # instance.
            self.static_example_dir = os.path.join(top_dir, 'test-data',
                                                   'mo-static-generate',
                                                   'basic', 'in')
            self.static_site_dir = os.path.join(self.instance_dir,
                                                'static-site')
            shutil.copytree(self.static_example_dir, self.static_site_dir)
            # Ensure the static site directory has a country without a
            # flag.  Ensure flags and photos listed in the .csv files
            # are present.
            countries_csv = os.path.join(self.static_site_dir, 'data',
                                         'countries.csv')
            replace_text_in_file(
                countries_csv,
                'https://www.example.org/countries/country3/flag1.png', '')
            static_base = 'https://www.example.org/'
            for country in read_utf8_csv(countries_csv):
                url = country['Flag URL']
                if url.startswith(static_base):
                    url_rest = url[len(static_base):]
                    url_dirs = url_rest.split('/')
                    image_file = os.path.join(self.static_site_dir, *url_dirs)
                    os.makedirs(os.path.dirname(image_file))
                    gen_image_file(2, 2, 2, image_file, 'PNG')
            people_csv = os.path.join(self.static_site_dir, 'data',
                                      'people.csv')
            for person in read_utf8_csv(people_csv):
                url = person['Photo URL']
                if url.startswith(static_base):
                    url_rest = url[len(static_base):]
                    url_dirs = url_rest.split('/')
                    image_file = os.path.join(self.static_site_dir, *url_dirs)
                    os.makedirs(os.path.dirname(image_file))
                    gen_image_file(2, 2, 2, image_file, 'JPEG')
            subst_files.extend([countries_csv, people_csv])
        if config and 'docgen_directory' in config:
            # Construct a document generation directory.  We assume it
            # is to be called 'docgen' relative to the Roundup
            # instance.
            self.docgen_example_dir = os.path.join(top_dir, 'examples',
                                                   'document-generation')
            self.docgen_dir = os.path.join(self.instance_dir, 'docgen')
            shutil.copytree(self.docgen_example_dir, self.docgen_dir)
            # We don't create a badge background PDF here, to allow
            # testing the case where it is missing, but some tests
            # need to create one.
            self.docgen_badge_background_pdf = os.path.join(
                self.docgen_dir, 'templates', 'lanyard-generic.pdf')
        os.makedirs(os.path.join(self.instance_dir, 'db'))
        self.passwords = {'admin': roundup.password.generatePassword()}
        self.userids = {'admin': '1'}
        self.num_users = 2
        for f in subst_files:
            replace_text_in_file(f, 'example.org', 'example.invalid')
        replace_text_in_file(self.config_ini, '\nbackend = postgresql\n',
                             '\nbackend = anydbm\n')
        replace_text_in_file(self.ext_config_ini,
                             '\nmatholymp_static_site_directory = '
                             '/some/where\n',
                             '\nmatholymp_static_site_directory =\n')
        replace_text_in_file(self.ext_config_ini,
                             '\nmatholymp_docgen_directory = '
                             '/some/where\n',
                             '\nmatholymp_docgen_directory =\n')
        if config:
            cfg = read_config_raw(self.ext_config_ini)
            for key, value in config.items():
                cfg.set('main', 'matholymp_%s' % key, value)
            write_config_raw(cfg, self.ext_config_ini)
        if coverage:
            # Record code coverage; arrange for the data to be saved
            # on exit.  Exit occurs both from this code and from
            # forked children handling requests, so _exit and fork
            # need to be wrapped.
            # pylint: disable=import-outside-toplevel
            from coverage import Coverage
            cov_base = os.path.join(self.temp_dir, '.coverage.reg-system')
            self.cov = Coverage(data_file=cov_base, data_suffix=True)
            self.cov.start()

            orig_exit = os._exit
            orig_fork = os.fork

            def wrap_fork():
                self.cov.stop()
                pid = orig_fork()
                if pid == 0:
                    self.cov = Coverage(data_file=cov_base, data_suffix=True)
                self.cov.start()
                return pid

            def wrap_exit(status):
                os._exit = orig_exit
                try:
                    self.cov.stop()
                    self.cov.save()
                finally:
                    os._exit(status)

            os.fork = wrap_fork
            os._exit = wrap_exit
        instance = roundup.instance.open(self.instance_dir)
        instance.init(roundup.password.Password(self.passwords['admin']))
        # Start up a server in a forked child, which reports back the
        # port number used to the parent (repeatedly trying random
        # ports as needed until one is free).
        read_fd, write_fd = os.pipe()
        sys.stdout.flush()
        sys.stderr.flush()
        self.pid = os.fork()
        if self.pid == 0:
            # Child.
            try:
                web_text = ('\nweb = https://www.example.invalid/'
                            'registration/2015/\n')
                retry = True
                while retry:
                    retry = False
                    self.port = random.SystemRandom().randrange(32768, 65536)
                    self.url = 'http://localhost:%d/xmo/' % self.port
                    web_text_new = '\nweb = %s\n' % self.url
                    replace_text_in_file(self.config_ini, web_text,
                                         web_text_new)
                    web_text = web_text_new
                    config = roundup_server.ServerConfig()
                    config.add_option(roundup_server.TrackerHomeOption(
                        config, 'trackers', 'xmo'))
                    config['TRACKERS_XMO'] = self.instance_dir
                    config.PORT = self.port
                    config['LOGFILE'] = self.log_file
                    config.set_logging()
                    os.environ['SENDMAILDEBUG'] = self.mail_file
                    try:
                        server = config.get_server()
                    except socket.error as e:
                        if 'port already in use' in str(e.args[0]):
                            retry = True
                        else:
                            raise
                os.close(read_fd)
                os.write(write_fd, str(self.port).encode('utf-8'))
                os.close(write_fd)
            except Exception:  # pylint: disable=broad-except
                sys.stdout.flush()
                sys.stderr.flush()
                traceback.print_exc()
                # Avoid cleanups running in child process.
                os._exit(1)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                sys.stdout.flush()
                sys.stderr.flush()
                print('Test server requested to exit')
                os._exit(0)
            except Exception:  # pylint: disable=broad-except
                sys.stdout.flush()
                sys.stderr.flush()
                traceback.print_exc()
                os._exit(1)
        else:
            # Parent.
            if coverage:
                # Code coverage in the parent, beyond the code read at
                # Roundup instance initialisation before forking, is
                # not of interest.
                self.cov.stop()
                self.cov.save()
                os._exit = orig_exit
                os.fork = orig_fork
            os.close(write_fd)
            self.port = int(os.read(read_fd, 5))
            os.close(read_fd)
            self.url = 'http://localhost:%d/xmo/' % self.port

    def stop_server(self):
        """Stop the server started for a RoundupTestInstance."""
        if self.pid:
            os.kill(self.pid, signal.SIGINT)
            os.waitpid(self.pid, 0)

    def static_site_bytes(self, filename):
        """Return the byte content of a file in the static site."""
        with open(os.path.join(self.static_site_dir, filename),
                  'rb') as in_file:
            return in_file.read()


class RoundupTestSession:

    """
    A RoundupTestSession automates interation with a RoundupTestInstance.
    """

    def __init__(self, instance, username=None):
        """Initialise a RoundupTestSession."""
        self.instance = instance
        self.b = mechanicalsoup.StatefulBrowser(raise_on_404=True)
        self.last_mail_bin = None
        self.last_mail_dec = None
        self.num_people = 0
        self.check_open(self.instance.url)
        if username is not None:
            self.login(username)

    def close(self):
        """Close this session."""
        self.b.close()

    def __getattr__(self, name):
        """Do a computed attribute lookup.

        check_* method names call the corresponding StatefulBrowser
        methods, which are expected to return a Response object, and
        carry out checks on both that object and the resulting
        page.
        """
        if name.startswith('check_'):
            sb_name = name[len('check_'):]
            sb_method = getattr(self.b, sb_name)
            old_mail_size = os.stat(self.instance.mail_file).st_size

            def fn(*args, mail=False, error=False, status=None, login=False,
                   html=True, **kwargs):
                response = sb_method(*args, **kwargs)
                if status is None:
                    response.raise_for_status()
                else:
                    if response.status_code != status:
                        raise ValueError('request generated status %d '
                                         'instead of %d'
                                         % (response.status_code, status))
                mail_size = os.stat(self.instance.mail_file).st_size
                mail_generated = mail_size > old_mail_size
                if mail_generated:
                    with open(self.instance.mail_file, 'rb') as f:
                        mail_bin = f.read()[old_mail_size:]
                        self.last_mail_bin = mail_bin
                        if b'Content-Transfer-Encoding: base64' in mail_bin:
                            content_idx = mail_bin.index(b'\n\n') + 2
                            mail_bin = mail_bin[content_idx:]
                            self.last_mail_dec = base64.b64decode(mail_bin)
                        else:
                            self.last_mail_dec = mail_bin
                if mail and not mail_generated:
                    raise ValueError('request failed to generate mail')
                elif mail_generated and not mail:
                    raise ValueError('request generated mail: %s'
                                     % str(self.last_mail_bin))
                if hasattr(response, 'soup') and html:
                    soup = response.soup
                    error_p = soup.find('p', class_='error-message')
                    error_generated = error_p is not None
                    if error and not error_generated:
                        raise ValueError('request did not produce error: %s'
                                         % str(soup))
                    elif error_generated and not error:
                        raise ValueError('request produced error: %s'
                                         % str(soup))
                    elif error and error_generated:
                        if isinstance(error, str):
                            if not error_p.find(string=re.compile(error)):
                                raise ValueError('request did not produce '
                                                 'expected error: %s'
                                                 % str(soup))
                    if soup.find('title',
                                 string=re.compile('An error has occurred')):
                        raise ValueError('request produced internal error: %s'
                                         % str(soup))
                    # Page templates should not try to format output
                    # at all for any fields the user lacks permission
                    # to see, so Roundup's [hidden] should never
                    # appear in the output.
                    if soup.find(string=re.compile(r'\[hidden\]')):
                        raise ValueError('request produced [hidden] text: %s'
                                         % str(soup))
                    wants_login = soup.find(string=re.compile(
                        'You are not allowed to view this page'
                        '|Please login with your username and password'))
                    wants_login = wants_login is not None
                    if login and not wants_login:
                        raise ValueError('request did not ask for login: %s'
                                         % str(soup))
                    elif wants_login and not login:
                        raise ValueError('request asked for login: %s'
                                         % str(soup))
                return response

            return fn
        else:
            raise AttributeError(name)

    def get_sidebar(self):
        """Get the sidebar from the current page."""
        return self.b.get_current_page().find(id='xmo-sidebar')

    def get_main(self):
        """Get the main contents from the current page."""
        return self.b.get_current_page().find(id='xmo-main')

    def get_download(self, url, content_type, filename):
        """Get a downloadable file and verify its content-type and filename."""
        response = self.check_get(self.instance.url + url, html=False)
        if response.headers['content-type'] != content_type:
            raise ValueError('request for %s produced content type %s, not %s'
                             % (url, response.headers['content-type'],
                                content_type))
        expected_disposition = 'attachment; filename=%s' % filename
        if response.headers['content-disposition'] != expected_disposition:
            raise ValueError('request for %s produced content disposition '
                             '%s, not %s'
                             % (url, response.headers['content-disposition'],
                                expected_disposition))
        return response.content

    def get_download_file(self, url, content_type, filename):
        """Get a download in a temporary file."""
        content = self.get_download(url, content_type, filename)
        temp_file = tempfile.NamedTemporaryFile(dir=self.instance.temp_dir,
                                                delete=False)
        temp_file.write(content)
        name = temp_file.name
        temp_file.close()
        return name

    def get_download_csv(self, url, filename):
        """Get the contents of a CSV download."""
        temp_name = self.get_download_file(url, 'text/csv; charset=UTF-8',
                                           filename)
        return read_utf8_csv(temp_name)

    def get_countries_csv(self):
        """Get the CSV file of countries."""
        return self.get_download_csv('country?@action=country_csv',
                                     'countries.csv')

    def get_countries_csv_public_only(self):
        """Get the CSV file of countries, public data only."""
        countries_csv = self.get_download_csv('country?@action=country_csv',
                                              'countries.csv')
        # For convenience in testing when non-public data is
        # irrelevant for what is being tested.
        for entry in countries_csv:
            del entry['Contact Emails']
            del entry['Expected Leaders']
            del entry['Expected Deputies']
            del entry['Expected Contestants']
            del entry['Expected Observers with Leader']
            del entry['Expected Observers with Deputy']
            del entry['Expected Observers with Contestants']
            del entry['Expected Single Rooms']
            del entry['Expected Numbers Confirmed']
            del entry['Leader Email']
            del entry['Physical Address']
        return countries_csv

    def get_people_csv(self):
        """Get the CSV file of people."""
        return self.get_download_csv('person?@action=people_csv',
                                     'people.csv')

    def get_scores_csv(self):
        """Get the CSV file of scores."""
        return self.get_download_csv('person?@action=scores_csv',
                                     'scores.csv')

    def get_people_csv_scores(self):
        """Get the scores from the CSV file of people."""
        people_csv = self.get_people_csv()
        cols = {'Country Name', 'Country Code', 'Contestant Code',
                'Given Name', 'Family Name', 'P1', 'P2', 'P3', 'P4', 'P5',
                'P6', 'Total', 'Award', 'Extra Awards'}
        people_csv = [entry for entry in people_csv
                      if entry['Contestant Code']]
        for entry in people_csv:
            for column in list(entry.keys()):
                if column not in cols:
                    del entry[column]
        return people_csv

    def get_download_zip(self, url, filename):
        """Get the contents of a ZIP download."""
        temp_name = self.get_download_file(url, 'application/zip', filename)
        return zipfile.ZipFile(temp_name, 'r')

    def get_flags_zip(self):
        """Get the ZIP file of flags."""
        return self.get_download_zip('country?@action=flags_zip', 'flags.zip')

    def get_photos_zip(self):
        """Get the ZIP file of photos."""
        return self.get_download_zip('person?@action=photos_zip', 'photos.zip')

    def get_consent_forms_zip(self):
        """Get the ZIP file of consent forms."""
        return self.get_download_zip('person?@action=consent_forms_zip',
                                     'consent-forms.zip')

    def get_bytes(self, url):
        """Get the bytes contents of a non-HTML URL."""
        return self.check_get(url, html=False).content

    def get_img(self):
        """Get the (first) img tag from the current page."""
        return self.get_main().find('img')

    def get_img_contents(self, use_parent_link=True):
        """
        Get the contents of the (first) img tag from the current page.
        If it is inside a link, get the target of that link instead (a
        full-size image, where the img tag is for a thumbnail), unless
        use_parent_link is False.
        """
        img = self.get_img()
        parent = img.parent
        if use_parent_link and parent.name == 'a':
            img_src = parent['href']
        else:
            img_src = img['src']
        img_src = self.b.absolute_url(img_src)
        return self.check_get(img_src, html=False).content

    def get_link(self, text):
        """Get the (first) link from the current page with given text."""
        return self.get_main().find('a', string=re.compile(text))

    def get_link_contents(self, text):
        """Get the target of the (first) link from the current page with the
        given text."""
        url = self.get_link(text)['href']
        url = self.b.absolute_url(url)
        return self.check_get(url, html=False).content

    def login(self, username):
        """Log in as the specified user."""
        self.b.select_form(self.get_sidebar().find('form'))
        self.b['__login_name'] = username
        self.b['__login_password'] = self.instance.passwords[username]
        self.check_submit_selected()

    def get_main_form(self):
        """Select the main form from the current page."""
        return self.get_main().find('form')

    def select_main_form(self):
        """Select the main form from the current page."""
        self.b.select_form(self.get_main_form())

    def workaround_ms_issue_242(self):
        """Work around MechanicalSoup issue 242."""
        ms_version = mechanicalsoup.__version__.split('.')
        if (int(ms_version[0]), int(ms_version[1])) > (0, 11):
            # 0.11.0 buggy, later versions fixed.
            return
        # Dummy file upload to work around a MechanicalSoup issue when
        # some field values are deliberately blank,
        # <https://github.com/MechanicalSoup/MechanicalSoup/issues/242>).
        form = self.b.get_current_form().form
        dummy = form.find('input', attrs={'name': 'dummy'})
        if dummy:
            # Dummy input already present.
            return
        temp_file = tempfile.NamedTemporaryFile(dir=self.instance.temp_dir,
                                                delete=False)
        filename = temp_file.name
        temp_file.close()
        self.b.new_control('file', 'dummy', '')
        self.b['dummy'] = filename

    def set(self, data):
        """Set the contents of fields in the selected form.

        Unlike the MechanicalSoup interfaces, 'select' fields are set
        by the labels on those fields, not their values.

        """
        form = self.b.get_current_form().form
        any_empty = False
        for key in data:
            value = data[key]
            select = form.find('select', attrs={'name': key})
            if select:
                if not isinstance(value, (list, tuple)):
                    value = (value,)
                new_value = []
                for v in value:
                    option = select.find('option', string=v)
                    new_value.append(option['value'])
                if len(new_value) == 1:
                    new_value = new_value[0]
                value = new_value
            self.b[key] = value
            if value == '':
                any_empty = True
        if any_empty:
            self.workaround_ms_issue_242()

    def create(self, cls, data, error=False, mail=False):
        """Create some kind of entity through the corresponding form."""
        self.check_open_relative('%s?@template=item' % cls)
        self.select_main_form()
        self.set(data)
        self.check_submit_selected(error=error, mail=mail)

    def create_defaults(self, cls, data, defaults, error=False, mail=False):
        """Create some kind of entity with default settings for some fields.

        Where a default setting is specified, it is used if no
        explicit setting is specified in data.  If None is specified
        in data, that setting is removed but the default is not
        applied.

        """
        new_data = dict(data)
        for key in defaults:
            if key in data:
                if data[key] is None:
                    del new_data[key]
            else:
                new_data[key] = defaults[key]
        self.create(cls, new_data, error=error, mail=mail)

    def create_user(self, username, country, roles, other=None):
        """Create a new user account."""
        password = roundup.password.generatePassword()
        data = {'username': username,
                'password': password,
                '@confirm@password': password,
                'country': country,
                'roles': roles}
        if other is not None:
            data.update(other)
        defaults = {'realname': username, 'address': 'test@example.invalid'}
        self.create_defaults('user', data, defaults)
        self.instance.passwords[username] = password
        self.instance.num_users += 1
        self.instance.userids[username] = str(self.instance.num_users)
        # Verify the id is as expected.
        expected_url = '%suser%s' % (self.instance.url,
                                     self.instance.userids[username])
        url = self.b.get_url().split('?')[0]
        if url != expected_url:
            raise ValueError('expected user URL %s, got %s'
                             % (expected_url, url))

    def create_scoring_user(self):
        """Create a scoring user."""
        self.create_user('scoring', 'XMO 2015 Staff', 'User,Score')

    def create_country(self, code, name, other=None, error=False):
        """Create a country and corresponding user account."""
        data = {'code': code, 'name': name}
        if other is not None:
            data.update(other)
        auto_user = 'contact_email' in data and not error
        self.create('country', data, error=error, mail=auto_user)
        if auto_user:
            mail_dec = self.last_mail_dec
            username_idx = mail_dec.rindex(b'Username: ')
            mail_dec = mail_dec[username_idx:]
            mail_data = mail_dec.split(b'\n')
            username_str = mail_data[0][len(b'Username: '):]
            password_str = mail_data[1]
            if not password_str.startswith(b'Password: '):
                raise ValueError('unexpected password line: %s'
                                 % str(password_str))
            password_str = password_str[len(b'Password: '):]
            username = username_str.decode()
            password = password_str.decode()
            self.instance.passwords[username] = password
            self.instance.num_users += 1
            self.instance.userids[username] = str(self.instance.num_users)
        elif not error:
            self.create_user('%s_reg' % code, name, 'User,Register')

    def create_country_generic(self):
        """Create a generic country for testing."""
        self.create_country('ABC', 'Test First Country')

    def create_person(self, country, role, other=None, error=False,
                      mail=False):
        """Create a person."""
        data = {'country': country, 'primary_role': role}
        if other is not None:
            data.update(other)
        self.num_people += 1
        defaults = {'given_name': 'Given %d' % self.num_people,
                    'family_name': 'Family %d' % self.num_people,
                    'gender': 'Female',
                    'date_of_birth_year': '2000',
                    'date_of_birth_month': 'January',
                    'date_of_birth_day': '1',
                    'language_1': 'English',
                    'tshirt': 'S'}
        self.create_defaults('person', data, defaults, error=error, mail=mail)

    def edit(self, cls, entity_id, data, error=False, mail=False, status=None):
        """Edit some kind of entity through the corresponding form."""
        self.check_open_relative('%s%s' % (cls, entity_id))
        self.select_main_form()
        self.set(data)
        self.check_submit_selected(error=error, mail=mail, status=status)

    def enter_scores(self, country_name, country_code, problem, scores,
                     error=False):
        """Enter some scores through the corresponding form."""
        self.check_open_relative('person?@template=scoreselect')
        self.select_main_form()
        self.set({'country': country_name, 'problem': problem})
        self.check_submit_selected()
        self.select_main_form()
        for num, score in enumerate(scores, start=1):
            if score is not None:
                self.set({'%s%d' % (country_code, num): score})
        self.workaround_ms_issue_242()
        self.check_submit_selected(error=error)

    def edit_prereg(self, entity_id, data, error=False, mail=False):
        """Edit preregistration data through the corresponding form."""
        self.check_open_relative('country%s?@template=prereg'
                                 % entity_id)
        self.select_main_form()
        self.set(data)
        self.check_submit_selected(error=error, mail=mail)


def _with_config(**kwargs):
    """A decorator to add a config attribute to a test method."""

    def decorator(test_fn):
        test_fn.config = kwargs
        return test_fn

    return decorator


@unittest.skipIf(_skip_test, 'required modules not installed')
class RegSystemTestCase(unittest.TestCase):

    """
    A RegSystemTestCase verifies the operation of the matholymp
    registration system.
    """

    def __init__(self, method_name='runTest'):
        """Initialise a RegSystemTestCase."""
        # Save the method name for use in __str__ without relying on
        # unittest internals of how it stores the method name.
        self.method_name = method_name
        method = getattr(self, method_name)
        self.config = getattr(method, 'config', {})
        self.coverage = False
        super().__init__(method_name)

    def __str__(self):
        # Generate test names similar to those for script tests.
        test_name = self.method_name
        if test_name.startswith('test_'):
            test_name = test_name[len('test_'):]
        test_name = test_name.replace('_', '-')
        return 'registration-system ' + test_name

    def setUp(self):
        self.sessions = []
        self.temp_dir_td = tempfile.TemporaryDirectory()
        self.temp_dir = self.temp_dir_td.name
        self.instance = RoundupTestInstance(sys.path[0], self.temp_dir,
                                            self.config, self.coverage)

    def tearDown(self):
        for s in self.sessions:
            s.close()
        self.instance.stop_server()
        if self.coverage:
            # pylint: disable=import-outside-toplevel
            from coverage import Coverage
            cov_base = os.path.join(sys.path[0], '.coverage.reg-system')
            cov = Coverage(data_file=cov_base)
            cov.load()
            cov.combine(data_paths=[self.temp_dir])
            cov.save()
        self.temp_dir_td.cleanup()

    def get_session(self, username=None):
        """Get a session for the specified username."""
        session = RoundupTestSession(self.instance, username)
        self.sessions.append(session)
        return session

    def gen_test_image(self, size_x, size_y, scale, suffix, fmt, mode='RGB'):
        """Generate a test image and return a tuple of the filename and the
        contents."""
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix,
                                                dir=self.temp_dir,
                                                delete=False)
        filename = temp_file.name
        temp_file.close()
        gen_image_file(size_x, size_y, scale, filename, fmt, mode)
        with open(filename, 'rb') as f:
            contents = f.read()
        return filename, contents

    def gen_test_pdf(self, suffix='.pdf'):
        """Generate a test PDF and return a tuple of the filename and the
        contents."""
        temp_dir = tempfile.mkdtemp(dir=self.temp_dir)
        filename = gen_pdf_file(temp_dir, suffix)
        with open(filename, 'rb') as f:
            contents = f.read()
        return filename, contents

    def gen_test_csv(self, rows, keys, delimiter=','):
        """Generate a CSV file with specified contents."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.csv',
                                                dir=self.temp_dir,
                                                delete=False)
        filename = temp_file.name
        temp_file.close()
        write_utf8_csv(filename, rows, keys, delimiter=delimiter)
        return filename

    def gen_test_csv_no_bom(self, rows, keys):
        """Generate a CSV file with specified contents and no BOM."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.csv',
                                                dir=self.temp_dir,
                                                delete=False)
        filename = temp_file.name
        temp_file.close()
        file_contents = write_utf8_csv_bytes(rows, keys)
        file_contents = file_contents[len(codecs.BOM_UTF8):]
        write_bytes_to_file(file_contents, filename)
        return filename

    def gen_test_csv_no_trailing_empty(self, rows, keys):
        """Generate a CSV file with specified contents and no trailing empty
        fields."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.csv',
                                                dir=self.temp_dir,
                                                delete=False)
        filename = temp_file.name
        temp_file.close()
        file_contents = write_utf8_csv_bytes(rows, keys)
        file_contents = re.sub(b',*\r', b'\r', file_contents)
        write_bytes_to_file(file_contents, filename)
        return filename

    def gen_test_zip(self, data):
        """Generate a ZIP file with specified contents."""
        temp_file = tempfile.NamedTemporaryFile(suffix='.zip',
                                                dir=self.temp_dir,
                                                delete=False)
        filename = temp_file.name
        temp_file.close()
        with zipfile.ZipFile(filename, 'w') as zip_zip:
            for member_filename, contents in data.items():
                zip_zip.writestr(member_filename, contents)
        return filename

    def all_templates_test(self, session, forbid_classes, forbid_templates,
                           allow_templates, can_score, admin_user):
        """Test that all page templates load without errors."""
        for t in sorted(os.listdir(self.instance.html_dir)):
            if t.startswith('_generic') or not t.endswith('.html'):
                continue
            m = re.fullmatch(r'([a-z_]+)\.([a-z_]+)\.html', t)
            if not m:
                continue
            # country.bulkconfirm.html and person.bulkconfirm.html
            # should given an error, if an admin user, unless used
            # with an upload of a CSV file.  person.scoreenter.html
            # should give an error, if able to enter scores, unless
            # country and problem are specified.
            error = ((can_score and t == 'person.scoreenter.html')
                     or (admin_user and t.endswith('.bulkconfirm.html')))
            login = ((m.group(1) in forbid_classes or t in forbid_templates)
                     and t not in allow_templates)
            session.check_open_relative('%s?@template=%s'
                                        % (m.group(1), m.group(2)),
                                        error=error, login=login)

    def test_all_templates_admin(self):
        """
        Test that all page templates load without errors, for the admin user.
        """
        session = self.get_session('admin')
        # This one gives an error when used without a particular
        # country specified.
        forbid_templates = {'country.prereg.html'}
        self.all_templates_test(session, forbid_classes=set(),
                                forbid_templates=forbid_templates,
                                allow_templates=set(), can_score=True,
                                admin_user=True)

    def test_all_templates_anon(self):
        """
        Test that all page templates load without errors, not logged in.
        """
        session = self.get_session()
        forbid_classes = {'event', 'rss', 'arrival', 'badge_type',
                          'consent_form', 'gender', 'language', 'room_type',
                          'tshirt', 'user'}
        forbid_templates = {'country.bulkconfirm.html',
                            'country.bulkregister.html',
                            'country.retireconfirm.html',
                            'person.bulkconfirm.html',
                            'person.bulkregister.html',
                            'person.retireconfirm.html',
                            'person.rooms.html',
                            'person.scoreenter.html',
                            'person.scoreselect.html',
                            'person.status.html'}
        self.all_templates_test(session, forbid_classes=forbid_classes,
                                forbid_templates=forbid_templates,
                                allow_templates={'user.forgotten.html'},
                                can_score=False, admin_user=False)

    def test_all_templates_score(self):
        """
        Test that all page templates load without errors, for a scoring user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_scoring_user()
        session = self.get_session('scoring')
        forbid_classes = {'event', 'rss', 'arrival', 'badge_type',
                          'consent_form', 'gender', 'language', 'room_type',
                          'tshirt'}
        forbid_templates = {'country.bulkconfirm.html',
                            'country.bulkregister.html',
                            'country.prereg.html',
                            'country.retireconfirm.html',
                            'person.bulkconfirm.html',
                            'person.bulkregister.html',
                            'person.retireconfirm.html',
                            'person.rooms.html',
                            'person.status.html'}
        self.all_templates_test(session, forbid_classes=forbid_classes,
                                forbid_templates=forbid_templates,
                                allow_templates=set(),
                                can_score=True, admin_user=False)

    def test_all_templates_register(self):
        """
        Test that all page templates load without errors, for a
        registering user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        session = self.get_session('ABC_reg')
        forbid_classes = {'badge_type', 'event', 'rss'}
        forbid_templates = {'country.bulkconfirm.html',
                            'country.bulkregister.html',
                            'country.prereg.html',
                            'country.retireconfirm.html',
                            'person.bulkconfirm.html',
                            'person.bulkregister.html',
                            'person.retireconfirm.html',
                            'person.rooms.html',
                            'person.scoreenter.html',
                            'person.scoreselect.html'}
        self.all_templates_test(session, forbid_classes=forbid_classes,
                                forbid_templates=forbid_templates,
                                allow_templates=set(),
                                can_score=False, admin_user=False)

    def all_templates_item_test(self, admin_session, session, forbid_classes):
        """Test that all page templates for existing items load without
        errors."""
        admin_session.create('arrival', {'name': 'Example Airport'})
        flag_filename, dummy = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('DEF', 'Test Second Country',
                                     {'flag-1@content': flag_filename})
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        pdf_filename, dummy = self.gen_test_pdf()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename,
                                     'consent_form-1@content': pdf_filename})
        # Set medal boundaries to create an rss item.
        admin_session.edit('event', '1',
                           {'registration_enabled': 'no',
                            'gold': '40', 'silver': '30', 'bronze': '20'})
        for t in sorted(os.listdir(self.instance.html_dir)):
            if t.startswith('_generic') or not t.endswith('.item.html'):
                continue
            m = re.fullmatch(r'([a-z_]+)\.([a-z_]+)\.html', t)
            if not m:
                continue
            login = m.group(1) in forbid_classes
            session.check_open_relative('%s1' % m.group(1),
                                        login=login)

    def test_all_templates_item_admin(self):
        """
        Test that all page templates for existing items load without
        errors, for the admin user.
        """
        session = self.get_session('admin')
        self.all_templates_item_test(session, session, forbid_classes=set())

    def test_all_templates_item_anon(self):
        """
        Test that all page templates for existing items load without
        errors, not logged in.
        """
        admin_session = self.get_session('admin')
        session = self.get_session()
        forbid_classes = {'event', 'rss', 'arrival', 'badge_type',
                          'consent_form', 'gender', 'language', 'room_type',
                          'tshirt', 'user'}
        self.all_templates_item_test(admin_session, session,
                                     forbid_classes=forbid_classes)

    def test_all_templates_item_score(self):
        """
        Test that all page templates for existing items load without
        errors, for a scoring user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_scoring_user()
        session = self.get_session('scoring')
        # user1 is another user, so gives an error.
        forbid_classes = {'event', 'rss', 'arrival', 'badge_type',
                          'consent_form', 'gender', 'language', 'room_type',
                          'tshirt', 'user'}
        self.all_templates_item_test(admin_session, session,
                                     forbid_classes=forbid_classes)

    def test_all_templates_item_register(self):
        """
        Test that all page templates for existing items load without
        errors, for a registering user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        session = self.get_session('ABC_reg')
        # consent_form1 is for another country, so gives an error.
        # user1 is another user, so gives an error.
        forbid_classes = {'badge_type', 'consent_form', 'event', 'rss', 'user'}
        self.all_templates_item_test(admin_session, session,
                                     forbid_classes=forbid_classes)

    def test_bad_login(self):
        """
        Test login failure with an incorrect password.
        """
        session = self.get_session()
        session.b.select_form(session.get_sidebar().find('form'))
        session.b['__login_name'] = 'admin'
        session.b['__login_password'] = (session.instance.passwords['admin']
                                         + 'x')
        session.check_submit_selected(error=True)

    def test_country_create_auto_user(self):
        """
        Test automatic user creation when creating a country.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'contact_email': 'ABC@example.invalid'})
        # Check where the email was sent.
        self.assertIn(
            b'\nTO: ABC@example.invalid, webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        # Test login with the new user works.
        self.get_session('ABC_reg')
        # Test case of extra contact addresses.
        admin_session.create_country('DEF', 'Test Second Country',
                                     {'contact_email': 'DEF@example.invalid',
                                      'contact_extra':
                                      'DEF2@example.invalid\n'
                                      '  DEF3@example.invalid \n\n'
                                      'DEF5@example.invalid'})
        self.assertIn(
            b'\nTO: DEF@example.invalid, DEF2@example.invalid, '
            b'DEF3@example.invalid, DEF5@example.invalid, '
            b'webmaster@example.invalid\n',
            admin_session.last_mail_bin)

    def test_country_csv(self):
        """
        Test CSV file of countries.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '0',
             'Expected Deputies': '0',
             'Expected Contestants': '0',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff_admin])
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        expected_abc_admin = expected_abc.copy()
        expected_abc_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'No',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Test contact email addresses in CSV file.
        admin_session.edit('country', '3',
                           {'contact_email': 'ABC@example.invalid'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin['Contact Emails'] = 'ABC@example.invalid'
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        admin_session.edit('country', '3',
                           {'contact_extra':
                            'ABC2@example.invalid\n'
                            '  ABC3@example.invalid \n\n'
                            'ABC6@example.invalid'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin['Contact Emails'] = ('ABC@example.invalid,'
                                                'ABC2@example.invalid,'
                                                'ABC3@example.invalid,'
                                                'ABC6@example.invalid')
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        admin_session.edit('country', '3',
                           {'contact_email': ''})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin['Contact Emails'] = ('ABC2@example.invalid,'
                                                'ABC3@example.invalid,'
                                                'ABC6@example.invalid')
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Test different values in CSV file for expected numbers of
        # participants.
        admin_session.edit('country', '3',
                           {'expected_leaders': '0',
                            'expected_contestants': '3',
                            'expected_observers_a': '5',
                            'expected_observers_b': '7',
                            'expected_observers_c': '11',
                            'expected_single_rooms': '13'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin.update(
            {'Expected Leaders': '0',
             'Expected Contestants': '3',
             'Expected Observers with Leader': '5',
             'Expected Observers with Deputy': '7',
             'Expected Observers with Contestants': '11',
             'Expected Single Rooms': '13'})
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        admin_session.edit('country', '3',
                           {'expected_numbers_confirmed': 'yes'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin['Expected Numbers Confirmed'] = 'Yes'
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])

    @_with_config(distinguish_official='Yes')
    def test_country_csv_official(self):
        """
        Test CSV file of countries, official / unofficial distinction.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '',
                          'Official Example': 'No', 'Normal': 'No'}
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '',
                        'Official Example': 'Yes', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        admin_session.create_country('DEF', 'Test Second Country',
                                     {'official': 'no'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        expected_def = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'DEF', 'Name': 'Test Second Country',
                        'Flag URL': '', 'Generic Number': '',
                        'Official Example': 'No', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_def,
                                    expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def,
                                     expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_def, expected_staff])

    @_with_config(virtual_event='Yes')
    def test_country_csv_virtual(self):
        """
        Test CSV file of countries, virtual event.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '0',
             'Expected Deputies': '0',
             'Expected Contestants': '0',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff_admin])
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        expected_abc_admin = expected_abc.copy()
        expected_abc_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'No',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Test virtual event data in CSV file.
        admin_session.edit('country', '3',
                           {'leader_email': 'ABCleader@example.invalid',
                            'physical_address': 'Maths HQ\nThis Country'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin['Leader Email'] = 'ABCleader@example.invalid'
        expected_abc_admin['Physical Address'] = 'Maths HQ\nThis Country'
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])

    def test_country_csv_errors(self):
        """
        Test errors from country_csv action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        session.check_open_relative('person?@action=country_csv',
                                    error='This action only applies '
                                    'to countries')
        session.check_open_relative('country1?@action=country_csv',
                                    error='Node id specified for CSV '
                                    'generation')
        admin_session.check_open_relative('person?@action=country_csv',
                                          error='This action only applies '
                                          'to countries')
        admin_session.check_open_relative('country1?@action=country_csv',
                                          error='Node id specified for CSV '
                                          'generation')

    def test_country_flag_create(self):
        """
        Test flags uploaded at country creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename})
        # Check the image inline on the country page.
        admin_session.check_open_relative('country3')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        reg_session = self.get_session('ABC_reg')
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': img_url_csv,
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    def test_country_flag_create_upper(self):
        """
        Test flags uploaded at country creation time, uppercase .PNG suffix.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.PNG', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename})
        # Check the image inline on the country page.
        admin_session.check_open_relative('country3')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        reg_session = self.get_session('ABC_reg')
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': img_url_csv,
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    @_with_config(static_site_directory='static-site')
    def test_country_flag_create_static(self):
        """
        Test flags copied from static site at country creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_bytes = self.instance.static_site_bytes(
            'countries/country1/flag1.png')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url': 'https://www.example.invalid/countries/country1/'})
        # Check the image inline on the country page.
        admin_session.check_open_relative('country3')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        reg_session = self.get_session('ABC_reg')
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': img_url_csv,
                        'Generic Number': '1', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    @_with_config(static_site_directory='static-site')
    def test_country_flag_create_static_none(self):
        """
        Test flags not present on static site at country creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url': 'https://www.example.invalid/countries/country3/'})
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '',
                        'Generic Number': '3', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])

    @_with_config(static_site_directory='static-site')
    def test_country_flag_create_static_priority(self):
        """
        Test flags uploaded at country creation time take priority
        over those from static site.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'flag-1@content': flag_filename,
             'generic_url': 'https://www.example.invalid/countries/country1/'})
        # Check the image inline on the country page.
        admin_session.check_open_relative('country3')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        reg_session = self.get_session('ABC_reg')
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': img_url_csv,
                        'Generic Number': '1', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    def test_country_flag_edit(self):
        """
        Test flags uploaded after country creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '',
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        admin_session.edit('country', '3', {'flag-1@content': flag_filename})
        img_url_csv = self.instance.url + 'flag1/flag.png'
        # Check the image inline on the country page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc['Flag URL'] = img_url_csv
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    @_with_config(static_site_directory='static-site')
    def test_country_flag_edit_static(self):
        """
        Test flags copied from static site after country creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '',
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        flag_bytes = self.instance.static_site_bytes(
            'countries/country1/flag1.png')
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/countries/country1/'})
        img_url_csv = self.instance.url + 'flag1/flag.png'
        # Check the image inline on the country page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc['Generic Number'] = '1'
        expected_abc['Flag URL'] = img_url_csv
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    @_with_config(static_site_directory='static-site')
    def test_country_flag_edit_static_none(self):
        """
        Test flags not present on static site when generic_url set
        after country creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '',
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/countries/country3/'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        expected_abc['Generic Number'] = '3'
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])

    @_with_config(static_site_directory='static-site')
    def test_country_flag_edit_static_priority(self):
        """
        Test flags uploaded after country creation time take priority
        over those from static site.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '',
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        admin_session.edit(
            'country', '3',
            {'flag-1@content': flag_filename,
             'generic_url': 'https://www.example.invalid/countries/country1/'})
        img_url_csv = self.instance.url + 'flag1/flag.png'
        # Check the image inline on the country page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc['Generic Number'] = '1'
        expected_abc['Flag URL'] = img_url_csv
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    def test_country_flag_replace(self):
        """
        Test replacing previously uploaded flag.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename})
        # Replace the image.
        flag_filename, flag_bytes = self.gen_test_image(3, 3, 3, '.png', 'PNG')
        admin_session.edit('country', '3', {'flag-1@content': flag_filename})
        # Check the image inline on the country page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        reg_session = self.get_session('ABC_reg')
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag2/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': img_url_csv,
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    @_with_config(static_site_directory='static-site')
    def test_country_flag_replace_static(self):
        """
        Test setting generic_url after flag uploaded does not change flag.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename})
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/countries/country1/'})
        # Check the image inline on the country page.
        admin_session.check_open_relative('country3')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, flag_bytes)
        reg_session = self.get_session('ABC_reg')
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('country3')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('country3')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'png')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': img_url_csv,
                        'Generic Number': '1', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)

    def test_country_flag_replace_access(self):
        """
        Test replaced flag is not public.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename})
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': img_url_csv,
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)
        # Replace the image.
        old_flag_bytes = flag_bytes
        flag_filename, flag_bytes = self.gen_test_image(3, 3, 3, '.png', 'PNG')
        admin_session.edit('country', '3', {'flag-1@content': flag_filename})
        # Check the old flag image is no longer public, but is still
        # accessible to admin.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, old_flag_bytes)
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg_session.check_open(img_url_csv,
                               error='You are not allowed to view this file',
                               status=403)
        # Similarly, only admin should be able to access the old flag
        # thumbnail.
        img_url_thumb = (self.instance.url
                         + 'flag1?@action=flag_thumb&width=200')
        admin_session.get_bytes(img_url_thumb)
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'flag',
                           status=403)
        reg_session.check_open(img_url_thumb,
                               error='You do not have permission to view '
                               'this flag',
                               status=403)

    def test_country_flag_zip(self):
        """
        Test ZIP file of flags.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_zip_empty = session.get_flags_zip()
        admin_zip_empty = admin_session.get_flags_zip()
        anon_contents = [f.filename for f in anon_zip_empty.infolist()]
        admin_contents = [f.filename for f in admin_zip_empty.infolist()]
        expected_contents = ['flags/README.txt']
        self.assertEqual(anon_contents, expected_contents)
        self.assertEqual(admin_contents, expected_contents)
        anon_zip_empty.close()
        admin_zip_empty.close()
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename})
        anon_zip = session.get_flags_zip()
        admin_zip = admin_session.get_flags_zip()
        anon_contents = [f.filename for f in anon_zip.infolist()]
        admin_contents = [f.filename for f in admin_zip.infolist()]
        expected_contents = ['flags/README.txt', 'flags/country3/flag.png']
        self.assertEqual(anon_contents, expected_contents)
        self.assertEqual(admin_contents, expected_contents)
        self.assertEqual(anon_zip.read('flags/country3/flag.png'), flag_bytes)
        self.assertEqual(admin_zip.read('flags/country3/flag.png'), flag_bytes)
        anon_zip.close()
        admin_zip.close()

    def test_country_flag_zip_errors(self):
        """
        Test errors from flags_zip action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        session.check_open_relative('person?@action=flags_zip',
                                    error='This action only applies '
                                    'to countries')
        session.check_open_relative('country1?@action=flags_zip',
                                    error='Node id specified for ZIP '
                                    'generation')
        admin_session.check_open_relative('person?@action=flags_zip',
                                          error='This action only applies '
                                          'to countries')
        admin_session.check_open_relative('country1?@action=flags_zip',
                                          error='Node id specified for ZIP '
                                          'generation')

    def test_country_flag_thumb_errors(self):
        """
        Test errors from flag_thumb action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        flag_filename, dummy = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename})
        session.check_open_relative('country?@action=flag_thumb',
                                    error='This action only applies '
                                    'to flags')
        session.check_open_relative('flag?@action=flag_thumb',
                                    error='No id specified to generate '
                                    'thumbnail')
        session.check_open_relative('flag1?@action=flag_thumb',
                                    error='No width specified to generate '
                                    'thumbnail')
        session.check_open_relative('flag1?@action=flag_thumb&width=300',
                                    error='Invalid width specified to '
                                    'generate thumbnail')
        # Permission errors are tested in
        # test_country_flag_replace_access and
        # test_country_retire_flag_access.
        admin_session.check_open_relative('country?@action=flag_thumb',
                                          error='This action only applies '
                                          'to flags')
        admin_session.check_open_relative('flag?@action=flag_thumb',
                                          error='No id specified to '
                                          'generate thumbnail')
        admin_session.check_open_relative('flag1?@action=flag_thumb',
                                          error='No width specified to '
                                          'generate thumbnail')
        admin_session.check_open_relative('flag1?@action=flag_thumb&width=300',
                                          error='Invalid width specified to '
                                          'generate thumbnail')

    def test_country_retire(self):
        """
        Test retiring countries.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_session.create_person('XMO 2015 Staff', 'Guide',
                                    {'guide_for': ['Test First Country',
                                                   'Test Second Country']})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(anon_csv[0]['Given Name'], 'Given 1')
        self.assertEqual(anon_csv[0]['Country Name'], 'Test First Country')
        self.assertEqual(anon_csv[1]['Family Name'], 'Family 2')
        self.assertEqual(anon_csv[1]['Primary Role'], 'Guide')
        self.assertEqual(anon_csv[1]['Guide For'],
                         'Test First Country,Test Second Country')
        self.assertEqual(anon_csv, reg_csv)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(admin_csv[0]['Given Name'], 'Given 1')
        self.assertEqual(admin_csv[0]['Country Name'], 'Test First Country')
        self.assertEqual(admin_csv[1]['Family Name'], 'Family 2')
        self.assertEqual(admin_csv[1]['Primary Role'], 'Guide')
        self.assertEqual(admin_csv[1]['Guide For'],
                         'Test First Country,Test Second Country')
        admin_session.check_open_relative('country3')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        expected_def = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'DEF', 'Name': 'Test Second Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_def, expected_staff])
        self.assertEqual(admin_csv, [expected_def, expected_staff])
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(anon_csv[0]['Family Name'], 'Family 2')
        self.assertEqual(anon_csv[0]['Primary Role'], 'Guide')
        self.assertEqual(anon_csv[0]['Guide For'], 'Test Second Country')
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(admin_csv[0]['Family Name'], 'Family 2')
        self.assertEqual(admin_csv[0]['Primary Role'], 'Guide')
        self.assertEqual(admin_csv[0]['Guide For'], 'Test Second Country')
        # Test lack of anonymous access to the retired country and
        # person pages.
        session.check_open_relative('country3', login=True)
        session.check_open_relative('person1', login=True)
        session.check_open_relative('person2')
        # The registration user for the retired country should no
        # longer be able to log in.
        nreg_session = self.get_session()
        nreg_session.b.select_form(session.get_sidebar().find('form'))
        nreg_session.b['__login_name'] = 'ABC_reg'
        nreg_session.b['__login_password'] \
            = session.instance.passwords['ABC_reg']
        nreg_session.check_submit_selected(error=True)
        # The existing session for that user should no longer be
        # active.
        reg_session.check_open_relative('country')
        reg_login = reg_session.get_sidebar().find('form')
        self.assertIsNotNone(reg_login)

    def test_country_retire_flag_access(self):
        """
        Test flag of retired country is not public.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename})
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        reg_csv = reg_session.get_countries_csv()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': img_url_csv,
                        'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)
        self.assertEqual(reg_bytes, flag_bytes)
        admin_session.check_open_relative('country3')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        # Check the old flag image is no longer public, but is still
        # accessible to admin.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, flag_bytes)
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        # Similarly, only admin should be able to access the old flag
        # thumbnail.
        img_url_thumb = (self.instance.url
                         + 'flag1?@action=flag_thumb&width=200')
        admin_session.get_bytes(img_url_thumb)
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'flag',
                           status=403)
        reg_session.check_open(img_url_thumb,
                               error='You do not have permission to view '
                               'this flag',
                               status=403)

    def test_country_retire_errors(self):
        """
        Test errors retiring countries.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        # Error trying to retire country via GET request.
        admin_session.check_open_relative('country3?@action=retirecountry',
                                          error='Invalid request')
        # Errors applying action to bad class or without id specified
        # (requires modifying the form to exercise).
        admin_session.check_open_relative('country3')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        admin_session.check_submit_selected()
        form = admin_session.get_main_form()
        form['action'] = 'country'
        admin_session.b.select_form(form)
        admin_session.check_submit_selected(error='No id specified to retire')
        admin_session.check_open_relative('country3')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        admin_session.check_submit_selected()
        form = admin_session.get_main_form()
        form['action'] = 'gender1'
        admin_session.b.select_form(form)
        admin_session.check_submit_selected(error='This action only applies '
                                            'to countries')
        # Errors retiring special countries.
        admin_session.check_open_relative('country1')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(error='Special countries cannot '
                                            'be retired', status=403)
        admin_session.check_open_relative('country2')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(error='Special countries cannot '
                                            'be retired', status=403)
        # Permission error (requires user to have valid form, then
        # have permissions removed, then try submitting it).
        admin_session.create_user('admin2', 'XMO 2015 Staff', 'Admin')
        admin2_session = self.get_session('admin2')
        admin2_session.check_open_relative('country3')
        admin2_session.b.select_form(
            admin2_session.get_main().find_all('form')[1])
        admin2_session.check_submit_selected()
        admin2_session.select_main_form()
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to retire',
                                             status=403)
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'Admin'})
        reg_session = self.get_session('ABC_reg')
        reg_session.check_open_relative('country3')
        reg_session.b.select_form(
            reg_session.get_main().find_all('form')[1])
        reg_session.check_submit_selected()
        reg_session.select_main_form()
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'User,Register'})
        reg_session.check_submit_selected(error='You do not have '
                                          'permission to retire', status=403)

    def test_country_edit_substring(self):
        """
        Test country edit with name or code a substring of that for
        another country.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country('MATC', 'Complete Mathsland')
        admin_session.create_country('MATO', 'Compact Mathsland')
        admin_session.edit('country', '4',
                           {'code': 'MAT', 'name': 'Mathsland'})
        expected_matc = {'XMO Number': '2', 'Country Number': '3',
                         'Annual URL': self.instance.url + 'country3',
                         'Code': 'MATC', 'Name': 'Complete Mathsland',
                         'Flag URL': '',
                         'Generic Number': '', 'Normal': 'Yes'}
        expected_mat = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'MAT', 'Name': 'Mathsland',
                        'Flag URL': '',
                        'Generic Number': '', 'Normal': 'Yes'}
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv,
                         [expected_mat, expected_matc, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_mat, expected_matc, expected_staff])

    def test_country_create_substring(self):
        """
        Test country creation with name or code a substring of that
        for another country.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country('MATC', 'Complete Mathsland')
        admin_session.create_country('MAT', 'Mathsland')
        expected_matc = {'XMO Number': '2', 'Country Number': '3',
                         'Annual URL': self.instance.url + 'country3',
                         'Code': 'MATC', 'Name': 'Complete Mathsland',
                         'Flag URL': '',
                         'Generic Number': '', 'Normal': 'Yes'}
        expected_mat = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'MAT', 'Name': 'Mathsland',
                        'Flag URL': '',
                        'Generic Number': '', 'Normal': 'Yes'}
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv,
                         [expected_mat, expected_matc, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_mat, expected_matc, expected_staff])

    def test_country_create_audit_errors(self):
        """
        Test errors from country creation auditor.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country('Abc', 'Test First Country',
                                     error='Country codes must be all '
                                     'capital letters')
        admin_session.create_country('ZZA', 'Test First Country',
                                     error='A country with code ZZA already '
                                     'exists')
        admin_session.create_country('ZZX', 'XMO 2015 Staff',
                                     error='A country with name XMO 2015 '
                                     'Staff already exists')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'contact_email': 'bad_email'},
                                     error='Email address syntax is invalid')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'contact_extra': 'bad_email'},
                                     error='Email address syntax is invalid')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_leaders': '2'},
                                     error='Invalid expected number of '
                                     'Leaders')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_leaders': '-1'},
                                     error='Invalid expected number of '
                                     'Leaders')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_leaders': '01'},
                                     error='Invalid expected number of '
                                     'Leaders')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_leaders': '1x'},
                                     error='Invalid expected number of '
                                     'Leaders')
        admin_session.create_country('ZZB', 'Extra Staff',
                                     {'is_normal': 'no',
                                      'expected_leaders': '1'},
                                     error='Invalid expected number of '
                                     'Leaders')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_deputies': '2'},
                                     error='Invalid expected number of '
                                     'Deputy Leaders')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_deputies': '-1'},
                                     error='Invalid expected number of '
                                     'Deputy Leaders')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_deputies': '01'},
                                     error='Invalid expected number of '
                                     'Deputy Leaders')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_deputies': '1x'},
                                     error='Invalid expected number of '
                                     'Deputy Leaders')
        admin_session.create_country('ZZB', 'Extra Staff',
                                     {'is_normal': 'no',
                                      'expected_deputies': '1'},
                                     error='Invalid expected number of '
                                     'Deputy Leaders')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_contestants': '7'},
                                     error='Invalid expected number of '
                                     'Contestants')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_contestants': '-1'},
                                     error='Invalid expected number of '
                                     'Contestants')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_contestants': '01'},
                                     error='Invalid expected number of '
                                     'Contestants')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_contestants': '1x'},
                                     error='Invalid expected number of '
                                     'Contestants')
        admin_session.create_country('ZZB', 'Extra Staff',
                                     {'is_normal': 'no',
                                      'expected_contestants': '1'},
                                     error='Invalid expected number of '
                                     'Contestants')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_a': '-1'},
                                     error='Invalid expected number of '
                                     'Observers with Leader')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_a': '01'},
                                     error='Invalid expected number of '
                                     'Observers with Leader')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_a': '1x'},
                                     error='Invalid expected number of '
                                     'Observers with Leader')
        admin_session.create_country('ZZB', 'Extra Staff',
                                     {'is_normal': 'no',
                                      'expected_observers_a': '1'},
                                     error='Invalid expected number of '
                                     'Observers with Leader')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_b': '-1'},
                                     error='Invalid expected number of '
                                     'Observers with Deputy')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_b': '01'},
                                     error='Invalid expected number of '
                                     'Observers with Deputy')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_b': '1x'},
                                     error='Invalid expected number of '
                                     'Observers with Deputy')
        admin_session.create_country('ZZB', 'Extra Staff',
                                     {'is_normal': 'no',
                                      'expected_observers_b': '1'},
                                     error='Invalid expected number of '
                                     'Observers with Deputy')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_c': '-1'},
                                     error='Invalid expected number of '
                                     'Observers with Contestants')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_c': '01'},
                                     error='Invalid expected number of '
                                     'Observers with Contestants')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_observers_c': '1x'},
                                     error='Invalid expected number of '
                                     'Observers with Contestants')
        admin_session.create_country('ZZB', 'Extra Staff',
                                     {'is_normal': 'no',
                                      'expected_observers_c': '1'},
                                     error='Invalid expected number of '
                                     'Observers with Contestants')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_single_rooms': '-1'},
                                     error='Invalid expected number of '
                                     'single room requests')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_single_rooms': '01'},
                                     error='Invalid expected number of '
                                     'single room requests')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'expected_single_rooms': '1x'},
                                     error='Invalid expected number of '
                                     'single room requests')
        flag_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename},
                                     error='Flags must be in PNG format')
        flag_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename},
                                     error=r'Filename extension for flag '
                                     r'must match contents \(png\)')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url': 'https://www.example.invalid/countries/country0/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url':
             'https://www.example.invalid/countries/country01/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url': 'https://www.example.invalid/countries/country1'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url':
             'https://www.example.invalid/countries/country1N/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        # Without static site data available, any country number is
        # OK.
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url':
             'https://www.example.invalid/countries/country12345/'})
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '',
                        'Generic Number': '12345', 'Normal': 'Yes'}
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])

    @_with_config(static_site_directory='static-site')
    def test_country_create_audit_errors_static(self):
        """
        Test errors from country creation auditor, static site checks.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url':
             'https://www.example.invalid/countries/country12345/'},
            error=r'example\.invalid URL for previous participation not valid')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])

    @_with_config(virtual_event='Yes')
    def test_country_create_audit_errors_virtual(self):
        """
        Test errors from country creation auditor, virtual event.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country('ABC', 'Test First Country',
                                     {'leader_email': 'bad_email'},
                                     error='Email address syntax is invalid')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])

    def test_country_create_audit_errors_missing(self):
        """
        Test errors from country creation auditor, missing required data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country('', 'Test First Country',
                                     error='Required country property code '
                                     'not supplied')
        admin_session.create_country('ABC', '',
                                     error='Required country property name '
                                     'not supplied')
        # The above errors are generic Roundup ones that rely on
        # @required being sent by the browser, so must not be relied
        # upon to maintain required properties of data since the
        # browser should not be trusted; also verify the checks from
        # the auditor in case @required is not sent.
        admin_session.create_country('', 'Test First Country',
                                     {'@required': ''},
                                     error='No country code specified')
        admin_session.create_country('ABC', '',
                                     {'@required': ''},
                                     error='No country name specified')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])

    def test_country_edit_audit_errors(self):
        """
        Test errors from country edit auditor.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country_generic()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        admin_session.edit('country', '1', {'code': 'Zza'},
                           error='Country codes must be all capital letters')
        admin_session.edit('country', '1', {'code': 'ABC'},
                           error='A country with code ABC already exists')
        admin_session.edit('country', '1', {'name': 'Test First Country'},
                           error='A country with name Test First Country '
                           'already exists')
        admin_session.edit('country', '1', {'is_normal': 'yes'},
                           error='Cannot change whether a country is normal')
        admin_session.edit('country', '3', {'is_normal': 'no'},
                           error='Cannot change whether a country is normal')
        admin_session.edit('country', '1', {'participants_ok': 'no'},
                           error='Cannot change whether a country can have '
                           'participants')
        admin_session.edit('country', '2', {'participants_ok': 'yes'},
                           error='Cannot change whether a country can have '
                           'participants')
        admin_session.edit('country', '3', {'participants_ok': 'no'},
                           error='Cannot change whether a country can have '
                           'participants')
        admin_session.edit('country', '3', {'contact_email': 'bad'},
                           error='Email address syntax is invalid')
        admin_session.edit('country', '3', {'contact_extra': 'bad'},
                           error='Email address syntax is invalid')
        admin_session.edit('country', '3',
                           {'expected_leaders': '2'},
                           error='Invalid expected number of Leaders')
        admin_session.edit('country', '3',
                           {'expected_leaders': '-1'},
                           error='Invalid expected number of Leaders')
        admin_session.edit('country', '3',
                           {'expected_leaders': '01'},
                           error='Invalid expected number of Leaders')
        admin_session.edit('country', '3',
                           {'expected_leaders': '1x'},
                           error='Invalid expected number of Leaders')
        admin_session.edit('country', '1',
                           {'expected_leaders': '1'},
                           error='Invalid expected number of Leaders')
        admin_session.edit('country', '3',
                           {'expected_deputies': '2'},
                           error='Invalid expected number of Deputy Leaders')
        admin_session.edit('country', '3',
                           {'expected_deputies': '-1'},
                           error='Invalid expected number of Deputy Leaders')
        admin_session.edit('country', '3',
                           {'expected_deputies': '01'},
                           error='Invalid expected number of Deputy Leaders')
        admin_session.edit('country', '3',
                           {'expected_deputies': '1x'},
                           error='Invalid expected number of Deputy Leaders')
        admin_session.edit('country', '1',
                           {'expected_deputies': '1'},
                           error='Invalid expected number of Deputy Leaders')
        admin_session.edit('country', '3',
                           {'expected_contestants': '7'},
                           error='Invalid expected number of Contestants')
        admin_session.edit('country', '3',
                           {'expected_contestants': '-1'},
                           error='Invalid expected number of Contestants')
        admin_session.edit('country', '3',
                           {'expected_contestants': '01'},
                           error='Invalid expected number of Contestants')
        admin_session.edit('country', '3',
                           {'expected_contestants': '1x'},
                           error='Invalid expected number of Contestants')
        admin_session.edit('country', '1',
                           {'expected_contestants': '1'},
                           error='Invalid expected number of Contestants')
        admin_session.edit('country', '3',
                           {'expected_observers_a': '-1'},
                           error='Invalid expected number of Observers with '
                           'Leader')
        admin_session.edit('country', '3',
                           {'expected_observers_a': '01'},
                           error='Invalid expected number of Observers with '
                           'Leader')
        admin_session.edit('country', '3',
                           {'expected_observers_a': '1x'},
                           error='Invalid expected number of Observers with '
                           'Leader')
        admin_session.edit('country', '1',
                           {'expected_observers_a': '1'},
                           error='Invalid expected number of Observers with '
                           'Leader')
        admin_session.edit('country', '3',
                           {'expected_observers_b': '-1'},
                           error='Invalid expected number of Observers with '
                           'Deputy')
        admin_session.edit('country', '3',
                           {'expected_observers_b': '01'},
                           error='Invalid expected number of Observers with '
                           'Deputy')
        admin_session.edit('country', '3',
                           {'expected_observers_b': '1x'},
                           error='Invalid expected number of Observers with '
                           'Deputy')
        admin_session.edit('country', '1',
                           {'expected_observers_b': '1'},
                           error='Invalid expected number of Observers with '
                           'Deputy')
        admin_session.edit('country', '3',
                           {'expected_observers_c': '-1'},
                           error='Invalid expected number of Observers with '
                           'Contestants')
        admin_session.edit('country', '3',
                           {'expected_observers_c': '01'},
                           error='Invalid expected number of Observers with '
                           'Contestants')
        admin_session.edit('country', '3',
                           {'expected_observers_c': '1x'},
                           error='Invalid expected number of Observers with '
                           'Contestants')
        admin_session.edit('country', '1',
                           {'expected_observers_c': '1'},
                           error='Invalid expected number of Observers with '
                           'Contestants')
        admin_session.edit('country', '3',
                           {'expected_single_rooms': '-1'},
                           error='Invalid expected number of single room '
                           'requests')
        admin_session.edit('country', '3',
                           {'expected_single_rooms': '01'},
                           error='Invalid expected number of single room '
                           'requests')
        admin_session.edit('country', '3',
                           {'expected_single_rooms': '1x'},
                           error='Invalid expected number of single room '
                           'requests')
        flag_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        admin_session.edit('country', '3',
                           {'flag-1@content': flag_filename},
                           error='Flags must be in PNG format')
        flag_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'PNG')
        admin_session.edit('country', '3',
                           {'flag-1@content': flag_filename},
                           error=r'Filename extension for flag must match '
                           r'contents \(png\)')
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/countries/country0/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.edit(
            'country', '3',
            {'generic_url':
             'https://www.example.invalid/countries/country01/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/countries/country1'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.edit(
            'country', '3',
            {'generic_url':
             'https://www.example.invalid/countries/country1N/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/countries/countryN/')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        # Without static site data available, any country number is
        # OK.
        admin_session.edit(
            'country', '3',
            {'generic_url':
             'https://www.example.invalid/countries/country12345/'})
        expected_abc['Generic Number'] = '12345'
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        # Deleting a specified email address is OK.
        admin_session.create_country('DEF', 'Test Second Country',
                                     {'contact_email': 'DEF@example.invalid',
                                      'contact_extra': 'DEF2@example.invalid'})
        admin_session.edit('country', '4', {'contact_email': '',
                                            'contact_extra': ''})
        expected_def = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'DEF', 'Name': 'Test Second Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        self.assertEqual(anon_csv,
                         [expected_abc, expected_def, expected_staff])
        expected_abc_admin = expected_abc.copy()
        expected_abc_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'No',
             'Leader Email': '',
             'Physical Address': ''})
        expected_def_admin = expected_def.copy()
        expected_def_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'No',
             'Leader Email': '',
             'Physical Address': ''})
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '0',
             'Expected Deputies': '0',
             'Expected Contestants': '0',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(admin_csv,
                         [expected_abc_admin, expected_def_admin,
                          expected_staff_admin])

    @_with_config(static_site_directory='static-site')
    def test_country_edit_audit_errors_static(self):
        """
        Test errors from country edit auditor, static site checks.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country_generic()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        admin_session.edit(
            'country', '3',
            {'generic_url':
             'https://www.example.invalid/countries/country12345/'},
            error=r'example\.invalid URL for previous participation not valid')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])

    @_with_config(virtual_event='Yes')
    def test_country_edit_audit_errors_virtual(self):
        """
        Test errors from country edit auditor, virtual event.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.edit(
            'country', '1',
            {'leader_email': 'bad_email'},
            error='Email address syntax is invalid')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])

    def test_country_edit_audit_errors_missing(self):
        """
        Test errors from country edit auditor, missing required data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.edit('country', '1', {'code': ''},
                           error='Required country property code not supplied')
        admin_session.edit('country', '1', {'name': ''},
                           error='Required country property name not supplied')
        # With @required not sent, the auditor restores the previous
        # values.
        admin_session.edit('country', '1', {'@required': '',
                                            'code': '',
                                            'name': ''})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])

    def test_country_edit_audit_errors_prereg(self):
        """
        Test errors from country edit auditor, preregistration case.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        reg_session.edit_prereg('3',
                                {'expected_leaders': '2'},
                                error='Invalid expected number of Leaders')
        reg_session.edit_prereg('3',
                                {'expected_leaders': '-1'},
                                error='Invalid expected number of Leaders')
        reg_session.edit_prereg('3',
                                {'expected_leaders': '01'},
                                error='Invalid expected number of Leaders')
        reg_session.edit_prereg('3',
                                {'expected_leaders': '1x'},
                                error='Invalid expected number of Leaders')
        reg_session.edit_prereg('3',
                                {'expected_deputies': '2'},
                                error='Invalid expected number of Deputy '
                                'Leaders')
        reg_session.edit_prereg('3',
                                {'expected_deputies': '-1'},
                                error='Invalid expected number of Deputy '
                                'Leaders')
        reg_session.edit_prereg('3',
                                {'expected_deputies': '01'},
                                error='Invalid expected number of Deputy '
                                'Leaders')
        reg_session.edit_prereg('3',
                                {'expected_deputies': '1x'},
                                error='Invalid expected number of Deputy '
                                'Leaders')
        reg_session.edit_prereg('3',
                                {'expected_contestants': '7'},
                                error='Invalid expected number of Contestants')
        reg_session.edit_prereg('3',
                                {'expected_contestants': '-1'},
                                error='Invalid expected number of Contestants')
        reg_session.edit_prereg('3',
                                {'expected_contestants': '01'},
                                error='Invalid expected number of Contestants')
        reg_session.edit_prereg('3',
                                {'expected_contestants': '1x'},
                                error='Invalid expected number of Contestants')
        reg_session.edit_prereg('3',
                                {'expected_observers_a': '-1'},
                                error='Invalid expected number of Observers '
                                'with Leader')
        reg_session.edit_prereg('3',
                                {'expected_observers_a': '01'},
                                error='Invalid expected number of Observers '
                                'with Leader')
        reg_session.edit_prereg('3',
                                {'expected_observers_a': '1x'},
                                error='Invalid expected number of Observers '
                                'with Leader')
        reg_session.edit_prereg('3',
                                {'expected_observers_b': '-1'},
                                error='Invalid expected number of Observers '
                                'with Deputy')
        reg_session.edit_prereg('3',
                                {'expected_observers_b': '01'},
                                error='Invalid expected number of Observers '
                                'with Deputy')
        reg_session.edit_prereg('3',
                                {'expected_observers_b': '1x'},
                                error='Invalid expected number of Observers '
                                'with Deputy')
        reg_session.edit_prereg('3',
                                {'expected_observers_c': '-1'},
                                error='Invalid expected number of Observers '
                                'with Contestants')
        reg_session.edit_prereg('3',
                                {'expected_observers_c': '01'},
                                error='Invalid expected number of Observers '
                                'with Contestants')
        reg_session.edit_prereg('3',
                                {'expected_observers_c': '1x'},
                                error='Invalid expected number of Observers '
                                'with Contestants')
        reg_session.edit_prereg('3',
                                {'expected_single_rooms': '-1'},
                                error='Invalid expected number of single room '
                                'requests')
        reg_session.edit_prereg('3',
                                {'expected_single_rooms': '01'},
                                error='Invalid expected number of single room '
                                'requests')
        reg_session.edit_prereg('3',
                                {'expected_single_rooms': '1x'},
                                error='Invalid expected number of single room '
                                'requests')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        self.assertEqual(anon_csv,
                         [expected_abc, expected_staff])
        expected_abc_admin = expected_abc.copy()
        expected_abc_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'No',
             'Leader Email': '',
             'Physical Address': ''})
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '0',
             'Expected Deputies': '0',
             'Expected Contestants': '0',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(admin_csv,
                         [expected_abc_admin, expected_staff_admin])

    def test_country_edit_audit_errors_prereg_disabled(self):
        """
        Test errors from country edit auditor, preregistration disabled.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        admin_session.edit('event', '1', {'preregistration_enabled': 'no',
                                          'registration_enabled': 'no'})
        # Confirming unchanged numbers is OK even when preregistration
        # is disabled.
        reg_session.edit_prereg('3',
                                {})
        admin_session.edit('event', '1', {'preregistration_enabled': 'yes'})
        reg_session.edit_prereg('3',
                                {'expected_single_rooms': '2'})
        admin_session.edit('event', '1', {'preregistration_enabled': 'no'})
        reg_session.edit_prereg('3',
                                {'expected_leaders': '0'},
                                error='Preregistration is now disabled, '
                                'please contact the event organisers to '
                                'change expected numbers of registered '
                                'participants')
        reg_session.edit_prereg('3',
                                {'expected_deputies': '0'},
                                error='Preregistration is now disabled, '
                                'please contact the event organisers to '
                                'change expected numbers of registered '
                                'participants')
        reg_session.edit_prereg('3',
                                {'expected_contestants': '0'},
                                error='Preregistration is now disabled, '
                                'please contact the event organisers to '
                                'change expected numbers of registered '
                                'participants')
        reg_session.edit_prereg('3',
                                {'expected_observers_a': '1'},
                                error='Preregistration is now disabled, '
                                'please contact the event organisers to '
                                'change expected numbers of registered '
                                'participants')
        reg_session.edit_prereg('3',
                                {'expected_observers_b': '1'},
                                error='Preregistration is now disabled, '
                                'please contact the event organisers to '
                                'change expected numbers of registered '
                                'participants')
        reg_session.edit_prereg('3',
                                {'expected_observers_c': '1'},
                                error='Preregistration is now disabled, '
                                'please contact the event organisers to '
                                'change expected numbers of registered '
                                'participants')
        reg_session.edit_prereg('3',
                                {'expected_single_rooms': '1'},
                                error='Preregistration is now disabled, '
                                'please contact the event organisers to '
                                'change expected numbers of registered '
                                'participants')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        self.assertEqual(anon_csv,
                         [expected_abc, expected_staff])
        expected_abc_admin = expected_abc.copy()
        expected_abc_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '2',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '0',
             'Expected Deputies': '0',
             'Expected Contestants': '0',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(admin_csv,
                         [expected_abc_admin, expected_staff_admin])

    @_with_config(virtual_event='Yes')
    def test_country_edit_audit_errors_prereg_virtual(self):
        """
        Test errors from country edit auditor, preregistration virtual
        event case.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        reg_session.edit_prereg('3',
                                {'leader_email': 'bad'},
                                error='Email address syntax is invalid')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        self.assertEqual(anon_csv,
                         [expected_abc, expected_staff])
        expected_abc_admin = expected_abc.copy()
        expected_abc_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'No',
             'Leader Email': '',
             'Physical Address': ''})
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '0',
             'Expected Deputies': '0',
             'Expected Contestants': '0',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(admin_csv,
                         [expected_abc_admin, expected_staff_admin])

    def test_country_no_participants_access(self):
        """
        Test access to no-participants countries.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        session.check_open_relative('country2', login=True)
        reg_session.check_open_relative('country2', login=True)
        admin_session.check_open_relative('country2')
        admin_session.create_country('ZZZ', 'None 2',
                                     {'participants_ok': 'no'})
        session.check_open_relative('country4', login=True)
        reg_session.check_open_relative('country4', login=True)
        admin_session.check_open_relative('country4')

    def test_country_prereg(self):
        """
        Test preregistration of expected number of participants.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '0',
             'Expected Deputies': '0',
             'Expected Contestants': '0',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff_admin])
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        expected_abc_admin = expected_abc.copy()
        expected_abc_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'No',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Test editing preregistration data.
        reg_session.edit_prereg('3',
                                {'expected_deputies': '0',
                                 'expected_contestants': '3',
                                 'expected_observers_a': '5',
                                 'expected_observers_b': '7',
                                 'expected_observers_c': '11',
                                 'expected_single_rooms': '13'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin.update(
            {'Expected Deputies': '0',
             'Expected Contestants': '3',
             'Expected Observers with Leader': '5',
             'Expected Observers with Deputy': '7',
             'Expected Observers with Contestants': '11',
             'Expected Single Rooms': '13',
             'Expected Numbers Confirmed': 'Yes'})
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        reg_session.edit_prereg('3',
                                {'expected_leaders': '0',
                                 'expected_deputies': '1'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin['Expected Leaders'] = '0'
        expected_abc_admin['Expected Deputies'] = '1'
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])

    @_with_config(virtual_event='Yes')
    def test_country_prereg_virtual(self):
        """
        Test preregistration of virtual event data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '0',
             'Expected Deputies': '0',
             'Expected Contestants': '0',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'Yes',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff_admin])
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        expected_abc_admin = expected_abc.copy()
        expected_abc_admin.update(
            {'Contact Emails': '',
             'Expected Leaders': '1',
             'Expected Deputies': '1',
             'Expected Contestants': '6',
             'Expected Observers with Leader': '0',
             'Expected Observers with Deputy': '0',
             'Expected Observers with Contestants': '0',
             'Expected Single Rooms': '0',
             'Expected Numbers Confirmed': 'No',
             'Leader Email': '',
             'Physical Address': ''})
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # Test editing virtual event data.
        reg_session.edit_prereg('3',
                                {'leader_email': 'gets-papers@example.invalid',
                                 'physical_address': 'Some Address\nCountry'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin.update(
            {'Expected Numbers Confirmed': 'Yes',
             'Leader Email': 'gets-papers@example.invalid',
             'Physical Address': 'Some Address\nCountry'})
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])
        # This data can be edited even when preregistration is disabled.
        admin_session.edit('event', '1', {'preregistration_enabled': 'no'})
        reg_session.edit_prereg('3',
                                {'leader_email':
                                 'gets-papers2@example.invalid',
                                 'physical_address':
                                 'Some Address 2\nCountry'})
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc_admin.update(
            {'Leader Email': 'gets-papers2@example.invalid',
             'Physical Address': 'Some Address 2\nCountry'})
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc_admin, expected_staff_admin])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])

    def test_country_bulk_register(self):
        """
        Test bulk registration of countries.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        csv_cols = ['Country Number', 'Name', 'Ignore', 'Code',
                    'Contact Email 1', 'Contact Email 2', 'Contact Email 3']
        csv_in = [{'Country Number': '123',
                   'Name': 'Test First Country  ',
                   'Ignore': 'Random text',
                   'Code': 'ABC'},
                  {'Name': ' Test Second Countr\u00fd',
                   'Code': 'DEF',
                   'Contact Email 1': 'DEF1@example.invalid',
                   'Contact Email 2': 'DEF2@example.invalid',
                   'Contact Email 3': 'DEF3@example.invalid'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(mail=True)
        self.assertIn(
            b'\nTO: DEF1@example.invalid, DEF2@example.invalid, '
            b'DEF3@example.invalid, webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        # The non-ASCII name means a Content-Transfer-Encoding must be
        # specified rather than attempting to send the mail as 8-bit
        # (which fails when Roundup is run in an ASCII locale).
        self.assertIn(
            b'\nContent-Transfer-Encoding:',
            admin_session.last_mail_bin)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '123',
                        'Normal': 'Yes'}
        expected_def = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'DEF', 'Name': 'Test Second Countr\u00fd',
                        'Flag URL': '', 'Generic Number': '',
                        'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_def,
                                    expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def,
                                     expected_staff])
        # Test without BOM in CSV file.
        csv_in = [{'Name': 'Test Third Countr\u00fd',
                   'Code': 'GHI'}]
        csv_filename = self.gen_test_csv_no_bom(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_ghi = {'XMO Number': '2', 'Country Number': '5',
                        'Annual URL': self.instance.url + 'country5',
                        'Code': 'GHI', 'Name': 'Test Third Countr\u00fd',
                        'Flag URL': '', 'Generic Number': '',
                        'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_def, expected_ghi,
                                    expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def, expected_ghi,
                                     expected_staff])
        # Test without trailing empty columns.
        csv_in = [{'Name': 'Test Fourth Country',
                   'Code': 'JKL'}]
        csv_filename = self.gen_test_csv_no_trailing_empty(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_jkl = {'XMO Number': '2', 'Country Number': '6',
                        'Annual URL': self.instance.url + 'country6',
                        'Code': 'JKL', 'Name': 'Test Fourth Country',
                        'Flag URL': '', 'Generic Number': '',
                        'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_def, expected_ghi,
                                    expected_jkl, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def, expected_ghi,
                                     expected_jkl, expected_staff])

    @_with_config(distinguish_official='Yes')
    def test_country_bulk_register_official(self):
        """
        Test bulk registration of countries, official / unofficial distinction.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '',
                          'Official Example': 'No', 'Normal': 'No'}
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        csv_cols = ['Country Number', 'Name', 'Ignore', 'Code',
                    'Official Example', 'Contact Email 1', 'Contact Email 2',
                    'Contact Email 3']
        csv_in = [{'Country Number': '123',
                   'Name': 'Test First Country',
                   'Ignore': 'Random text',
                   'Code': 'ABC', 'Official Example': 'No'},
                  {'Name': 'Test Second Countr\u00fd',
                   'Code': 'DEF',
                   'Contact Email 1': 'DEF1@example.invalid',
                   'Contact Email 2': 'DEF2@example.invalid',
                   'Contact Email 3': 'DEF3@example.invalid',
                   'Official Example': 'Yes'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(mail=True)
        self.assertIn(
            b'\nTO: DEF1@example.invalid, DEF2@example.invalid, '
            b'DEF3@example.invalid, webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '123',
                        'Official Example': 'No', 'Normal': 'Yes'}
        expected_def = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'DEF', 'Name': 'Test Second Countr\u00fd',
                        'Flag URL': '', 'Generic Number': '',
                        'Official Example': 'Yes', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_def,
                                    expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def,
                                     expected_staff])

    @_with_config(static_site_directory='static-site')
    def test_country_bulk_register_static(self):
        """
        Test bulk registration of countries, flags available on static site.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        flag_bytes = self.instance.static_site_bytes(
            'countries/country2/flag1.png')
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        csv_cols = ['Country Number', 'Name', 'Ignore', 'Code',
                    'Contact Email 1', 'Contact Email 2', 'Contact Email 3']
        csv_in = [{'Country Number': '3',
                   'Name': 'Test First Country',
                   'Ignore': 'Random text',
                   'Code': 'ABC'},
                  {'Country Number': '2', 'Name': 'Test Second Countr\u00fd',
                   'Code': 'DEF',
                   'Contact Email 1': 'DEF1@example.invalid',
                   'Contact Email 2': 'DEF2@example.invalid',
                   'Contact Email 3': 'DEF3@example.invalid'},
                  {'Name': 'Test Third Countr\u00fd',
                   'Code': 'GHI'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(mail=True)
        self.assertIn(
            b'\nTO: DEF1@example.invalid, DEF2@example.invalid, '
            b'DEF3@example.invalid, webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        img_url_csv = self.instance.url + 'flag1/flag.png'
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '3',
                        'Normal': 'Yes'}
        expected_def = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'DEF', 'Name': 'Test Second Countr\u00fd',
                        'Flag URL': img_url_csv, 'Generic Number': '2',
                        'Normal': 'Yes'}
        expected_ghi = {'XMO Number': '2', 'Country Number': '5',
                        'Annual URL': self.instance.url + 'country5',
                        'Code': 'GHI', 'Name': 'Test Third Countr\u00fd',
                        'Flag URL': '', 'Generic Number': '',
                        'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_def, expected_ghi,
                                    expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def, expected_ghi,
                                     expected_staff])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, flag_bytes)
        self.assertEqual(admin_bytes, flag_bytes)

    def test_country_bulk_register_semicolon(self):
        """
        Test bulk registration of countries, semicolon separator used.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        csv_cols = ['Country Number', 'Name', 'Ignore', 'Code',
                    'Contact Email 1', 'Contact Email 2', 'Contact Email 3']
        csv_in = [{'Country Number': '123',
                   'Name': 'Test First Country  ',
                   'Ignore': 'Random text',
                   'Code': 'ABC'},
                  {'Name': ' Test Second Countr\u00fd',
                   'Code': 'DEF',
                   'Contact Email 1': 'DEF1@example.invalid',
                   'Contact Email 2': 'DEF2@example.invalid',
                   'Contact Email 3': 'DEF3@example.invalid'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols, delimiter=';')
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'csv_delimiter': ';'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(mail=True)
        self.assertIn(
            b'\nTO: DEF1@example.invalid, DEF2@example.invalid, '
            b'DEF3@example.invalid, webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        # The non-ASCII name means a Content-Transfer-Encoding must be
        # specified rather than attempting to send the mail as 8-bit
        # (which fails when Roundup is run in an ASCII locale).
        self.assertIn(
            b'\nContent-Transfer-Encoding:',
            admin_session.last_mail_bin)
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '123',
                        'Normal': 'Yes'}
        expected_def = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'DEF', 'Name': 'Test Second Countr\u00fd',
                        'Flag URL': '', 'Generic Number': '',
                        'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_def,
                                    expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def,
                                     expected_staff])

    def test_country_bulk_register_errors(self):
        """
        Test errors from bulk registration of countries.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        # Error using bulk registration via GET request.
        admin_session.check_open_relative(
            'country?@action=country_bulk_register',
            error='Invalid request')
        # Errors applying action to bad class or with id specified
        # (requires modifying the form to exercise).
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        form['action'] = 'person'
        admin_session.set({'@template': 'index'})
        admin_session.check_submit_selected(error='Invalid class for bulk '
                                            'registration')
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        form['action'] = 'country1'
        admin_session.set({'@template': 'item'})
        admin_session.check_submit_selected(error='Node id specified for bulk '
                                            'registration')
        # Errors missing uploaded CSV data.  The first case (csv_file
        # present in the form but no file submitted there) is wrongly
        # handled the same as the second (no csv_file in the form) by
        # MechanicalSoup versions 0.11 and earlier
        # <https://github.com/MechanicalSoup/MechanicalSoup/issues/250>.
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        admin_session.check_submit_selected(error='no CSV file uploaded')
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.check_submit_selected(error='no CSV file uploaded')
        # Errors with CSV data of wrong type.
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.b.new_control('text', 'csv_file', 'some text')
        admin_session.check_submit_selected(error='csv_file not an uploaded '
                                            'file')
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.b.new_control('file', 'csv_contents', '')
        csv_filename = self.gen_test_csv([{'Test': 'text'}], ['Test'])
        admin_session.set({'csv_contents': csv_filename})
        admin_session.check_submit_selected(error='csv_contents an uploaded '
                                            'file')
        # Errors with encoding of CSV data.
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.b.new_control('text', 'csv_contents', '\u00ff')
        # error='.' used for cases where the error message comes from
        # the standard Python library, to avoid depending on the exact
        # text of such errors.
        admin_session.check_submit_selected(error='.')
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.b.new_control('text', 'csv_contents', '!')
        admin_session.check_submit_selected(error='.')
        temp_file = tempfile.NamedTemporaryFile(suffix='.csv',
                                                dir=self.temp_dir,
                                                delete=False)
        csv_filename = temp_file.name
        temp_file.close()
        write_bytes_to_file(b'\xff', csv_filename)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='.')
        # Errors with content, where the uploaded file is a valid CSV
        # file.
        csv_cols = ['Country Number', 'Name', 'Ignore', 'Code',
                    'Contact Email 1', 'Contact Email 2', 'Contact Email 3']
        csv_in = [{'Country Number': '123',
                   'Name': 'Test First Country',
                   'Ignore': 'Random text',
                   'Code': 'ABC'},
                  {'Name': 'Test Second Country'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Code' missing in row 2")
        csv_in = [{'Country Number': '123',
                   'Name': 'Test First Country',
                   'Ignore': 'Random text',
                   'Code': 'ABC'},
                  {'Code': 'DEF', 'Name': '   '}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Name' missing in row 2")
        csv_in = [{'Country Number': '123',
                   'Name': 'Test First Country',
                   'Ignore': 'Random text',
                   'Code': 'ABC'},
                  {'Code': 'ABC', 'Name': 'Test Second Country'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Code' duplicate value in "
                                            "row 2")
        csv_in = [{'Country Number': '123',
                   'Name': 'Test First Country',
                   'Ignore': 'Random text',
                   'Code': 'ABC'},
                  {'Code': 'DEF', 'Name': 'Test First Country'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Name' duplicate value in "
                                            "row 2")
        csv_in = [{'Code': 'ABC', 'Name': 'Test First Country'},
                  {'Code': 'DEF', 'Name': 'Test Second Country'},
                  {'Country Number': '1', 'Code': 'GHI', 'Name': 'GHI'},
                  {'Country Number': '1', 'Code': 'JKL', 'Name': 'JKL'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Country Number' duplicate "
                                            "value in row 4")
        # Errors from auditor.
        csv_in = [{'Code': 'ABC', 'Name': 'Test First Country'},
                  {'Code': 'def', 'Name': 'Test Second Country'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 2: Country codes must '
                                            'be all capital letters')
        csv_in = [{'Code': 'ABC', 'Name': 'Test First Country'},
                  {'Code': 'DEF', 'Name': 'Test Second Country',
                   'Contact Email 1': 'invalid email'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 2: Email address '
                                            'syntax is invalid')
        csv_in = [{'Code': 'ABC', 'Name': 'Test First Country'},
                  {'Code': 'DEF', 'Name': 'Test Second Country',
                   'Contact Email 1': 'DEF@example.invalid',
                   'Contact Email 2': '! ! !'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 2: Email address '
                                            'syntax is invalid')
        csv_in = [{'Code': 'ABC', 'Name': 'Test First Country'},
                  {'Code': 'DEF', 'Name': 'Test Second Country',
                   'Country Number': '0'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error=r'row 2: example\.invalid URLs for previous participation '
            r'must be in the form https://www\.example\.invalid/countries/'
            r'countryN/')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        # Errors from auditor when existing countries are duplicated.
        admin_session.create_country_generic()
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        csv_in = [{'Code': 'ABC', 'Name': 'Test'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: A country with code '
                                            'ABC already exists')
        csv_in = [{'Code': 'DEF', 'Name': 'Test First Country'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: A country with name '
                                            'Test First Country already '
                                            'exists')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        # Errors from auditor bulk creation stage when duplicate
        # countries were added after initial validation.
        admin2_session = self.get_session('admin')
        csv_in = [{'Code': 'DEF', 'Name': 'Test Second Country'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin2_session.create_country('DEF', 'Another Test Country')
        anon_csv = session.get_countries_csv()
        admin_csv = admin2_session.get_countries_csv_public_only()
        expected_def = {'XMO Number': '2', 'Country Number': '4',
                        'Annual URL': self.instance.url + 'country4',
                        'Code': 'DEF', 'Name': 'Another Test Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_def,
                                    expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def,
                                     expected_staff])
        admin_session.select_main_form()
        admin_session.check_submit_selected(error='row 1: A country with code '
                                            'DEF already exists')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_abc, expected_def,
                                    expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_def,
                                     expected_staff])
        # Permission error (requires user to have valid form, then
        # have permissions removed, then try submitting it).
        admin_session.create_user('admin2', 'XMO 2015 Staff', 'Admin')
        admin2_session = self.get_session('admin2')
        csv_in = [{'Code': 'GHI', 'Name': 'Test Third Country'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin2_session.check_open_relative('country?@template=bulkregister')
        admin2_session.select_main_form()
        admin2_session.set({'csv_file': csv_filename})
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to bulk register',
                                             status=403)
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'Admin'})
        admin2_session.check_open_relative('country?@template=bulkregister')
        admin2_session.select_main_form()
        admin2_session.set({'csv_file': csv_filename})
        admin2_session.check_submit_selected()
        admin2_session.select_main_form()
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to bulk register',
                                             status=403)

    @_with_config(distinguish_official='Yes')
    def test_country_bulk_register_errors_official(self):
        """
        Test errors from bulk registration of countries, official /
        unofficial distinction.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '',
                          'Official Example': 'No', 'Normal': 'No'}
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        csv_cols = ['Name', 'Code', 'Official Example']
        csv_in = [{'Name': 'Test First Country', 'Code': 'ABC',
                   'Official Example': 'Yes'},
                  {'Name': 'Test Second Country', 'Code': 'DEF'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Official Example' missing "
                                            "in row 2")
        csv_in = [{'Name': 'Test First Country', 'Code': 'ABC',
                   'Official Example': 'Yes'},
                  {'Name': 'Test Second Country', 'Code': 'DEF',
                   'Official Example': 'abc'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Official Example' bad "
                                            "value in row 2")
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])

    @_with_config(static_site_directory='static-site')
    def test_country_bulk_register_errors_static(self):
        """
        Test errors from bulk registration of countries, static site checks.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Annual URL': self.instance.url + 'country1',
                          'Code': 'ZZA', 'Name': 'XMO 2015 Staff',
                          'Flag URL': '', 'Generic Number': '', 'Normal': 'No'}
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        csv_cols = ['Name', 'Code', 'Country Number']
        csv_in = [{'Code': 'ABC', 'Name': 'Test First Country'},
                  {'Code': 'DEF', 'Name': 'Test Second Country',
                   'Country Number': '12345'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('country?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error=r'row 2: example\.invalid URL for previous participation '
            r'not valid')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv_public_only()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])

    def test_country_scores_rss_errors(self):
        """
        Test errors from scores_rss action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        session.check_open_relative('person?@action=scores_rss',
                                    error='This action only applies '
                                    'to countries')
        admin_session.check_open_relative('person?@action=scores_rss',
                                          error='This action only applies '
                                          'to countries')

    def test_person_csv(self):
        """
        Test CSV file of people.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'arrival_place': 'Example Airport',
             'arrival_date': '2 April 2015',
             'arrival_time_hour': '13',
             'arrival_time_minute': '30',
             'arrival_flight': 'ABC123',
             'room_share_with': 'Some Other Person',
             'room_number': '987'})
        admin_session.create_person(
            'Test First Country', 'Leader',
            {'gender': 'Male',
             'date_of_birth_year': None,
             'date_of_birth_month': None,
             'date_of_birth_day': None,
             'language_2': 'French',
             'tshirt': 'M',
             'departure_place': 'Example Airport',
             'departure_date': '3 April 2015',
             'departure_time_hour': '14',
             'departure_time_minute': '50',
             'departure_flight': 'ABC987',
             'room_type': 'Single room'})
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'guide_for': ['Test First Country'],
             'diet': 'Vegetarian',
             'other_roles': ['Logistics', 'Jury Chair'],
             'phone_number': '9876543210'})
        expected_cont = {'XMO Number': '2', 'Country Number': '3',
                         'Person Number': '1',
                         'Annual URL': self.instance.url + 'person1',
                         'Country Name': 'Test First Country',
                         'Country Code': 'ABC', 'Primary Role': 'Contestant 1',
                         'Other Roles': '', 'Guide For': '',
                         'Contestant Code': 'ABC1', 'Contestant Age': '15',
                         'Given Name': 'Given 1', 'Family Name': 'Family 1',
                         'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                         'P6': '', 'Total': '0', 'Award': '',
                         'Extra Awards': '', 'Photo URL': '',
                         'Generic Number': ''}
        expected_leader = {'XMO Number': '2', 'Country Number': '3',
                           'Person Number': '2',
                           'Annual URL': self.instance.url + 'person2',
                           'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Primary Role': 'Leader',
                           'Other Roles': '', 'Guide For': '',
                           'Contestant Code': '', 'Contestant Age': '',
                           'Given Name': 'Given 2', 'Family Name': 'Family 2',
                           'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                           'P6': '', 'Total': '', 'Award': '',
                           'Extra Awards': '', 'Photo URL': '',
                           'Generic Number': ''}
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Person Number': '3',
                          'Annual URL': self.instance.url + 'person3',
                          'Country Name': 'XMO 2015 Staff',
                          'Country Code': 'ZZA', 'Primary Role': 'Guide',
                          'Other Roles': 'Jury Chair,Logistics',
                          'Guide For': 'Test First Country',
                          'Contestant Code': '', 'Contestant Age': '',
                          'Given Name': 'Given 3', 'Family Name': 'Family 3',
                          'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                          'P6': '', 'Total': '', 'Award': '',
                          'Extra Awards': '', 'Photo URL': '',
                          'Generic Number': ''}
        expected_cont_admin = expected_cont.copy()
        expected_leader_admin = expected_leader.copy()
        expected_staff_admin = expected_staff.copy()
        expected_cont_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'S',
             'Arrival Place': 'Example Airport', 'Arrival Date': '2015-04-02',
             'Arrival Time': '13:30', 'Arrival Flight': 'ABC123',
             'Departure Place': '', 'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': 'Some Other Person', 'Room Number': '987',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '7ab558',
             'Badge Inner Colour': 'c9deb0', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        expected_leader_admin.update(
            {'Gender': 'Male', 'Date of Birth': '',
             'Languages': 'English,French',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'M',
             'Arrival Place': '', 'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': 'Example Airport',
             'Departure Date': '2015-04-03', 'Departure Time': '14:50',
             'Departure Flight': 'ABC987', 'Room Type': 'Single room',
             'Share Room With': '', 'Room Number': '', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': 'd22027', 'Badge Inner Colour': 'eb9984',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': '', 'Passport Given Name': 'Given 2',
             'Passport Family Name': 'Family 2', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        expected_staff_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': 'Vegetarian',
             'T-Shirt Size': 'S', 'Arrival Place': '', 'Arrival Date': '',
             'Arrival Time': '', 'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '9876543210', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given 3',
             'Passport Family Name': 'Family 3', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_cont, expected_leader, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_cont_admin, expected_leader_admin,
                          expected_staff_admin])
        self.assertEqual(reg_csv,
                         [expected_cont, expected_leader, expected_staff])

    @_with_config(consent_forms_date='', consent_forms_url='')
    def test_person_csv_no_consent_forms(self):
        """
        Test CSV file of people, no consent forms in database schema.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'arrival_place': 'Example Airport',
             'arrival_date': '2 April 2015',
             'arrival_time_hour': '13',
             'arrival_time_minute': '30',
             'arrival_flight': 'ABC123',
             'room_number': '987'})
        expected_cont = {'XMO Number': '2', 'Country Number': '3',
                         'Person Number': '1',
                         'Annual URL': self.instance.url + 'person1',
                         'Country Name': 'Test First Country',
                         'Country Code': 'ABC', 'Primary Role': 'Contestant 1',
                         'Other Roles': '', 'Guide For': '',
                         'Contestant Code': 'ABC1', 'Contestant Age': '15',
                         'Given Name': 'Given 1', 'Family Name': 'Family 1',
                         'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                         'P6': '', 'Total': '0', 'Award': '',
                         'Extra Awards': '', 'Photo URL': '',
                         'Generic Number': ''}
        expected_cont_admin = expected_cont.copy()
        expected_cont_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'S',
             'Arrival Place': 'Example Airport', 'Arrival Date': '2015-04-02',
             'Arrival Time': '13:30', 'Arrival Flight': 'ABC123',
             'Departure Place': '', 'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': '7ab558', 'Badge Inner Colour': 'c9deb0',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': '', 'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])

    @_with_config(require_passport_number='Yes')
    def test_person_csv_passport_number(self):
        """
        Test CSV file of people, passport numbers collected.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'arrival_place': 'Example Airport',
             'arrival_date': '2 April 2015',
             'arrival_time_hour': '13',
             'arrival_time_minute': '30',
             'arrival_flight': 'ABC123',
             'room_number': '987',
             'passport_number': '123456789'})
        expected_cont = {'XMO Number': '2', 'Country Number': '3',
                         'Person Number': '1',
                         'Annual URL': self.instance.url + 'person1',
                         'Country Name': 'Test First Country',
                         'Country Code': 'ABC', 'Primary Role': 'Contestant 1',
                         'Other Roles': '', 'Guide For': '',
                         'Contestant Code': 'ABC1', 'Contestant Age': '15',
                         'Given Name': 'Given 1', 'Family Name': 'Family 1',
                         'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                         'P6': '', 'Total': '0', 'Award': '',
                         'Extra Awards': '', 'Photo URL': '',
                         'Generic Number': ''}
        expected_cont_admin = expected_cont.copy()
        expected_cont_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'S',
             'Arrival Place': 'Example Airport', 'Arrival Date': '2015-04-02',
             'Arrival Time': '13:30', 'Arrival Flight': 'ABC123',
             'Departure Place': '', 'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': '7ab558', 'Badge Inner Colour': 'c9deb0',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '123456789',
             'Nationality': '', 'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])

    @_with_config(require_nationality='Yes')
    def test_person_csv_nationality(self):
        """
        Test CSV file of people, nationalities collected.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'arrival_place': 'Example Airport',
             'arrival_date': '2 April 2015',
             'arrival_time_hour': '13',
             'arrival_time_minute': '30',
             'arrival_flight': 'ABC123',
             'room_number': '987',
             'nationality': 'Matholympian'})
        expected_cont = {'XMO Number': '2', 'Country Number': '3',
                         'Person Number': '1',
                         'Annual URL': self.instance.url + 'person1',
                         'Country Name': 'Test First Country',
                         'Country Code': 'ABC', 'Primary Role': 'Contestant 1',
                         'Other Roles': '', 'Guide For': '',
                         'Contestant Code': 'ABC1', 'Contestant Age': '15',
                         'Given Name': 'Given 1', 'Family Name': 'Family 1',
                         'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                         'P6': '', 'Total': '0', 'Award': '',
                         'Extra Awards': '', 'Photo URL': '',
                         'Generic Number': ''}
        expected_cont_admin = expected_cont.copy()
        expected_cont_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'S',
             'Arrival Place': 'Example Airport', 'Arrival Date': '2015-04-02',
             'Arrival Time': '13:30', 'Arrival Flight': 'ABC123',
             'Departure Place': '', 'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': '7ab558', 'Badge Inner Colour': 'c9deb0',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': 'Matholympian', 'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])

    @_with_config(require_passport_number='Yes', require_nationality='Yes')
    def test_person_csv_passport_name(self):
        """
        Test CSV file of people, names as in passports collected.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'arrival_place': 'Example Airport',
             'arrival_date': '2 April 2015',
             'arrival_time_hour': '13',
             'arrival_time_minute': '30',
             'arrival_flight': 'ABC123',
             'room_number': '987',
             'passport_number': '123456789',
             'nationality': 'Matholympian'})
        expected_cont = {'XMO Number': '2', 'Country Number': '3',
                         'Person Number': '1',
                         'Annual URL': self.instance.url + 'person1',
                         'Country Name': 'Test First Country',
                         'Country Code': 'ABC', 'Primary Role': 'Contestant 1',
                         'Other Roles': '', 'Guide For': '',
                         'Contestant Code': 'ABC1', 'Contestant Age': '15',
                         'Given Name': 'Given 1', 'Family Name': 'Family 1',
                         'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                         'P6': '', 'Total': '0', 'Award': '',
                         'Extra Awards': '', 'Photo URL': '',
                         'Generic Number': ''}
        expected_cont_admin = expected_cont.copy()
        # By default passport names are copied from non-passport names.
        expected_cont_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'S',
             'Arrival Place': 'Example Airport', 'Arrival Date': '2015-04-02',
             'Arrival Time': '13:30', 'Arrival Flight': 'ABC123',
             'Departure Place': '', 'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': '7ab558', 'Badge Inner Colour': 'c9deb0',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '123456789',
             'Nationality': 'Matholympian', 'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])
        # Non-default passport names may be set, at person creation or
        # edit time.
        reg_session.edit('person', '1',
                         {'passport_given_name': 'Other Given',
                          'passport_family_name': 'Other Family'})
        expected_cont_admin.update(
            {'Passport Given Name': 'Other Given',
             'Passport Family Name': 'Other Family'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])
        reg_session.create_person(
            'Test First Country', 'Contestant 2',
            {'given_name': 'Given 2',
             'family_name': 'Family 2',
             'arrival_place': 'Example Airport',
             'arrival_date': '2 April 2015',
             'arrival_time_hour': '13',
             'arrival_time_minute': '30',
             'arrival_flight': 'ABC123',
             'passport_number': '123456790',
             'nationality': 'Other-olympian',
             'passport_given_name': 'Random',
             'passport_family_name': 'Randomer'})
        expected_cont2 = {'XMO Number': '2', 'Country Number': '3',
                          'Person Number': '2',
                          'Annual URL': self.instance.url + 'person2',
                          'Country Name': 'Test First Country',
                          'Country Code': 'ABC',
                          'Primary Role': 'Contestant 2', 'Other Roles': '',
                          'Guide For': '', 'Contestant Code': 'ABC2',
                          'Contestant Age': '15', 'Given Name': 'Given 2',
                          'Family Name': 'Family 2',
                          'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                          'P6': '', 'Total': '0', 'Award': '',
                          'Extra Awards': '', 'Photo URL': '',
                          'Generic Number': ''}
        expected_cont2_admin = expected_cont2.copy()
        expected_cont2_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'S',
             'Arrival Place': 'Example Airport', 'Arrival Date': '2015-04-02',
             'Arrival Time': '13:30', 'Arrival Flight': 'ABC123',
             'Departure Place': '', 'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': '7ab558', 'Badge Inner Colour': 'c9deb0',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '123456790',
             'Nationality': 'Other-olympian', 'Passport Given Name': 'Random',
             'Passport Family Name': 'Randomer', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont, expected_cont2])
        self.assertEqual(admin_csv, [expected_cont_admin,
                                     expected_cont2_admin])
        self.assertEqual(reg_csv, [expected_cont, expected_cont2])

    @_with_config(consent_ui='Yes')
    def test_person_csv_consent_ui(self):
        """
        Test CSV file of people, consent information collected.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'arrival_place': 'Example Airport',
             'arrival_date': '2 April 2015',
             'arrival_time_hour': '13',
             'arrival_time_minute': '30',
             'arrival_flight': 'ABC123',
             'room_number': '987',
             'diet': 'Vegetarian',
             'event_photos_consent': 'yes', 'diet_consent': 'yes'})
        expected_cont = {'XMO Number': '2', 'Country Number': '3',
                         'Person Number': '1',
                         'Annual URL': self.instance.url + 'person1',
                         'Country Name': 'Test First Country',
                         'Country Code': 'ABC', 'Primary Role': 'Contestant 1',
                         'Other Roles': '', 'Guide For': '',
                         'Contestant Code': 'ABC1', 'Contestant Age': '15',
                         'Given Name': 'Given 1', 'Family Name': 'Family 1',
                         'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                         'P6': '', 'Total': '0', 'Award': '',
                         'Extra Awards': '', 'Photo URL': '',
                         'Generic Number': ''}
        expected_cont_admin = expected_cont.copy()
        expected_cont_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': 'Vegetarian',
             'T-Shirt Size': 'S', 'Arrival Place': 'Example Airport',
             'Arrival Date': '2015-04-02', 'Arrival Time': '13:30',
             'Arrival Flight': 'ABC123', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': '7ab558', 'Badge Inner Colour': 'c9deb0',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': '', 'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1',
             'Event Photos Consent': 'Yes', 'Remote Participant': 'No',
             'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])
        admin_session.edit('person', '1', {'event_photos_consent': 'no'})
        expected_cont_admin['Event Photos Consent'] = 'No'
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])
        # Test removing previously given consent for diet information
        # sets that information to "Unknown".
        admin_session.edit('person', '1', {'diet_consent': 'no'})
        expected_cont_admin['Allergies and Dietary Requirements'] = 'Unknown'
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])
        # Test diet information specified without consent is discarded.
        admin_session.create_person(
            'Test First Country', 'Contestant 2',
            {'arrival_place': 'Example Airport',
             'arrival_date': '2 April 2015',
             'arrival_time_hour': '13',
             'arrival_time_minute': '30',
             'arrival_flight': 'ABC123',
             'room_number': '987',
             'diet': 'Vegetarian',
             'event_photos_consent': 'no', 'diet_consent': 'no'})
        expected_cont2 = {'XMO Number': '2', 'Country Number': '3',
                          'Person Number': '2',
                          'Annual URL': self.instance.url + 'person2',
                          'Country Name': 'Test First Country',
                          'Country Code': 'ABC',
                          'Primary Role': 'Contestant 2', 'Other Roles': '',
                          'Guide For': '', 'Contestant Code': 'ABC2',
                          'Contestant Age': '15', 'Given Name': 'Given 2',
                          'Family Name': 'Family 2', 'P1': '', 'P2': '',
                          'P3': '', 'P4': '', 'P5': '', 'P6': '', 'Total': '0',
                          'Award': '', 'Extra Awards': '', 'Photo URL': '',
                          'Generic Number': ''}
        expected_cont2_admin = expected_cont2.copy()
        expected_cont2_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': 'Unknown',
             'T-Shirt Size': 'S', 'Arrival Place': 'Example Airport',
             'Arrival Date': '2015-04-02', 'Arrival Time': '13:30',
             'Arrival Flight': 'ABC123', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': '7ab558', 'Badge Inner Colour': 'c9deb0',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': '', 'Passport Given Name': 'Given 2',
             'Passport Family Name': 'Family 2', 'Event Photos Consent': 'No',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont, expected_cont2])
        self.assertEqual(admin_csv, [expected_cont_admin,
                                     expected_cont2_admin])
        self.assertEqual(reg_csv, [expected_cont, expected_cont2])

    @_with_config(age_day_date='2015-04-02')
    def test_person_csv_age(self):
        """
        Test ages in CSV file of people in more detail.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'date_of_birth_year': '2000',
             'date_of_birth_month': 'March',
             'date_of_birth_day': '31'})
        admin_session.create_person(
            'Test First Country', 'Contestant 2',
            {'date_of_birth_year': '2000',
             'date_of_birth_month': 'April',
             'date_of_birth_day': '1'})
        admin_session.create_person(
            'Test First Country', 'Contestant 3',
            {'date_of_birth_year': '2000',
             'date_of_birth_month': 'April',
             'date_of_birth_day': '2'})
        admin_session.create_person(
            'Test First Country', 'Contestant 4',
            {'date_of_birth_year': '2000',
             'date_of_birth_month': 'April',
             'date_of_birth_day': '3'})
        expected_cont1 = {'XMO Number': '2', 'Country Number': '3',
                          'Person Number': '1',
                          'Annual URL': self.instance.url + 'person1',
                          'Country Name': 'Test First Country',
                          'Country Code': 'ABC',
                          'Primary Role': 'Contestant 1', 'Other Roles': '',
                          'Guide For': '', 'Contestant Code': 'ABC1',
                          'Contestant Age': '15', 'Given Name': 'Given 1',
                          'Family Name': 'Family 1', 'P1': '', 'P2': '',
                          'P3': '', 'P4': '', 'P5': '', 'P6': '', 'Total': '0',
                          'Award': '', 'Extra Awards': '', 'Photo URL': '',
                          'Generic Number': ''}
        expected_cont1_admin = expected_cont1.copy()
        expected_cont1_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-03-31',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'S',
             'Arrival Place': '', 'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '', 'Departure Date': '',
             'Departure Time': '', 'Departure Flight': '',
             'Room Type': 'Shared room', 'Share Room With': '',
             'Room Number': '', 'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '7ab558',
             'Badge Inner Colour': 'c9deb0', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        expected_cont2 = expected_cont1.copy()
        expected_cont2_admin = expected_cont1_admin.copy()
        expected_cont2.update(
            {'Person Number': '2', 'Annual URL': self.instance.url + 'person2',
             'Primary Role': 'Contestant 2', 'Contestant Code': 'ABC2',
             'Given Name': 'Given 2', 'Family Name': 'Family 2'})
        expected_cont2_admin.update(expected_cont2)
        expected_cont2_admin.update({'Passport Given Name': 'Given 2',
                                     'Passport Family Name': 'Family 2'})
        expected_cont2_admin['Date of Birth'] = '2000-04-01'
        expected_cont3 = expected_cont1.copy()
        expected_cont3_admin = expected_cont1_admin.copy()
        expected_cont3.update(
            {'Person Number': '3', 'Annual URL': self.instance.url + 'person3',
             'Primary Role': 'Contestant 3', 'Contestant Code': 'ABC3',
             'Given Name': 'Given 3', 'Family Name': 'Family 3'})
        expected_cont3_admin.update(expected_cont3)
        expected_cont3_admin.update({'Passport Given Name': 'Given 3',
                                     'Passport Family Name': 'Family 3'})
        expected_cont3_admin['Date of Birth'] = '2000-04-02'
        expected_cont4 = expected_cont1.copy()
        expected_cont4_admin = expected_cont1_admin.copy()
        expected_cont4.update(
            {'Person Number': '4', 'Annual URL': self.instance.url + 'person4',
             'Primary Role': 'Contestant 4', 'Contestant Code': 'ABC4',
             'Contestant Age': '14', 'Given Name': 'Given 4',
             'Family Name': 'Family 4'})
        expected_cont4_admin.update(expected_cont4)
        expected_cont4_admin.update({'Passport Given Name': 'Given 4',
                                     'Passport Family Name': 'Family 4'})
        expected_cont4_admin['Date of Birth'] = '2000-04-03'
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_cont1, expected_cont2, expected_cont3,
                          expected_cont4])
        self.assertEqual(admin_csv,
                         [expected_cont1_admin, expected_cont2_admin,
                          expected_cont3_admin, expected_cont4_admin])
        self.assertEqual(reg_csv,
                         [expected_cont1, expected_cont2, expected_cont3,
                          expected_cont4])

    def test_person_csv_multilink_comma(self):
        """
        Test CSV file of people with commas in multilink values.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Second,Country')
        admin_session.create('matholymprole',
                             {'name': 'Extra,Role',
                              'default_room_type': 'Shared room',
                              'badge_type': 'Organiser'})
        admin_session.create('language', {'name': 'Another,Language'})
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'guide_for': ['Test First Country', 'Second,Country'],
             'other_roles': ['Logistics', 'Extra,Role'],
             'language_2': 'Another,Language'})
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Person Number': '1',
                          'Annual URL': self.instance.url + 'person1',
                          'Country Name': 'XMO 2015 Staff',
                          'Country Code': 'ZZA', 'Primary Role': 'Guide',
                          'Other Roles': '"Extra,Role",Logistics',
                          'Guide For': 'Test First Country,"Second,Country"',
                          'Contestant Code': '', 'Contestant Age': '',
                          'Given Name': 'Given 1', 'Family Name': 'Family 1',
                          'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                          'P6': '', 'Total': '', 'Award': '',
                          'Extra Awards': '', 'Photo URL': '',
                          'Generic Number': ''}
        expected_staff_admin = expected_staff.copy()
        expected_staff_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English,"Another,Language"',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': 'S', 'Arrival Place': '', 'Arrival Date': '',
             'Arrival Time': '', 'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': 'Shared room',
             'Share Room With': '', 'Room Number': '', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': '2a3e92', 'Badge Inner Colour': '9c95cc',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': '', 'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1', 'Event Photos Consent': '',
             'Remote Participant': 'No', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff_admin])
        self.assertEqual(reg_csv, [expected_staff])

    @_with_config(virtual_event='Yes')
    def test_person_csv_virtual(self):
        """
        Test CSV file of people for a virtual event.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1')
        admin_session.create_person(
            'Test First Country', 'Leader',
            {'gender': 'Male',
             'date_of_birth_year': None,
             'date_of_birth_month': None,
             'date_of_birth_day': None,
             'language_2': 'French',
             'tshirt': 'M'})
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'guide_for': ['Test First Country'],
             'other_roles': ['Logistics', 'Jury Chair'],
             'phone_number': '9876543210'})
        expected_cont = {'XMO Number': '2', 'Country Number': '3',
                         'Person Number': '1',
                         'Annual URL': self.instance.url + 'person1',
                         'Country Name': 'Test First Country',
                         'Country Code': 'ABC', 'Primary Role': 'Contestant 1',
                         'Other Roles': '', 'Guide For': '',
                         'Contestant Code': 'ABC1', 'Contestant Age': '15',
                         'Given Name': 'Given 1', 'Family Name': 'Family 1',
                         'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                         'P6': '', 'Total': '0', 'Award': '',
                         'Extra Awards': '', 'Photo URL': '',
                         'Generic Number': ''}
        expected_leader = {'XMO Number': '2', 'Country Number': '3',
                           'Person Number': '2',
                           'Annual URL': self.instance.url + 'person2',
                           'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Primary Role': 'Leader',
                           'Other Roles': '', 'Guide For': '',
                           'Contestant Code': '', 'Contestant Age': '',
                           'Given Name': 'Given 2', 'Family Name': 'Family 2',
                           'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                           'P6': '', 'Total': '', 'Award': '',
                           'Extra Awards': '', 'Photo URL': '',
                           'Generic Number': ''}
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Person Number': '3',
                          'Annual URL': self.instance.url + 'person3',
                          'Country Name': 'XMO 2015 Staff',
                          'Country Code': 'ZZA', 'Primary Role': 'Guide',
                          'Other Roles': 'Jury Chair,Logistics',
                          'Guide For': 'Test First Country',
                          'Contestant Code': '', 'Contestant Age': '',
                          'Given Name': 'Given 3', 'Family Name': 'Family 3',
                          'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                          'P6': '', 'Total': '', 'Award': '',
                          'Extra Awards': '', 'Photo URL': '',
                          'Generic Number': ''}
        expected_cont_admin = expected_cont.copy()
        expected_leader_admin = expected_leader.copy()
        expected_staff_admin = expected_staff.copy()
        expected_cont_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'S',
             'Arrival Place': '', 'Arrival Date': '',
             'Arrival Time': '', 'Arrival Flight': '',
             'Departure Place': '', 'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '7ab558',
             'Badge Inner Colour': 'c9deb0', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1', 'Event Photos Consent': '',
             'Remote Participant': 'Yes', 'Basic Data Missing': 'No'})
        expected_leader_admin.update(
            {'Gender': 'Male', 'Date of Birth': '',
             'Languages': 'English,French',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'M',
             'Arrival Place': '', 'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '', 'Phone Number': '',
             'Badge Photo URL': '', 'Badge Background': 'generic',
             'Badge Outer Colour': 'd22027', 'Badge Inner Colour': 'eb9984',
             'Badge Text Colour': '000000', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': '', 'Passport Given Name': 'Given 2',
             'Passport Family Name': 'Family 2', 'Event Photos Consent': '',
             'Remote Participant': 'Yes', 'Basic Data Missing': 'No'})
        expected_staff_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': 'S', 'Arrival Place': '', 'Arrival Date': '',
             'Arrival Time': '', 'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '9876543210', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given 3',
             'Passport Family Name': 'Family 3', 'Event Photos Consent': '',
             'Remote Participant': 'Yes', 'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_cont, expected_leader, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_cont_admin, expected_leader_admin,
                          expected_staff_admin])
        self.assertEqual(reg_csv,
                         [expected_cont, expected_leader, expected_staff])

    def test_person_csv_errors(self):
        """
        Test errors from people_csv action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        session.check_open_relative('country?@action=people_csv',
                                    error='This action only applies '
                                    'to people')
        session.check_open_relative('person1?@action=people_csv',
                                    error='Node id specified for CSV '
                                    'generation')
        admin_session.check_open_relative('country?@action=people_csv',
                                          error='This action only applies '
                                          'to people')
        admin_session.check_open_relative('person1?@action=people_csv',
                                          error='Node id specified for CSV '
                                          'generation')

    def test_person_scores_csv_errors(self):
        """
        Test errors from scores_csv action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        session.check_open_relative('country?@action=scores_csv',
                                    error='This action only applies '
                                    'to people')
        session.check_open_relative('person1?@action=scores_csv',
                                    error='Node id specified for CSV '
                                    'generation')
        admin_session.check_open_relative('country?@action=scores_csv',
                                          error='This action only applies '
                                          'to people')
        admin_session.check_open_relative('person1?@action=scores_csv',
                                          error='Node id specified for CSV '
                                          'generation')

    def test_person_photo_create(self):
        """
        Test photos uploaded at person creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(consent_ui='Yes')
    def test_person_photo_create_consent(self):
        """
        Test photos uploaded at person creation time, with consent
        information handling.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'event_photos_consent': 'yes',
             'photo-1@content': photo_filename,
             'photo_consent': 'Yes, for website and name badge',
             'diet_consent': 'yes'})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        session.check_open_relative('person1')
        got_bytes = session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        reg_session.check_open_relative('person1')
        got_bytes = reg_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        anon_thumb = session.get_img_contents(False)
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(consent_ui='Yes')
    def test_person_photo_create_consent_badge_only(self):
        """
        Test photos uploaded at person creation time, with consent
        information handling, badge-only photo.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'event_photos_consent': 'yes',
             'photo-1@content': photo_filename,
             'photo_consent': 'Yes, for name badge only',
             'diet_consent': 'yes'})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        reg_session.check_open_relative('person1')
        got_bytes = reg_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        # Check no image inline on the person page for other users.
        session.check_open_relative('person1')
        self.assertIsNone(session.get_img())
        reg2_session.check_open_relative('person1')
        self.assertIsNone(reg2_session.get_img())
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': img_url_csv,
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)
        # Check the photo is not accessible anonymously or by
        # registering users from other countries.
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(img_url_csv,
                                error='You are not allowed to view this file',
                                status=403)
        # Similarly, other users should not be able to access the
        # photo thumbnail.
        img_url_thumb = (self.instance.url
                         + 'photo1?@action=photo_thumb&width=200')
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg2_session.check_open(img_url_thumb,
                                error='You do not have permission to view '
                                'this photo',
                                status=403)

    @_with_config(consent_ui='Yes')
    def test_person_photo_create_consent_no(self):
        """
        Test photos uploaded at person creation time, with consent
        information handling, no consent given.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'event_photos_consent': 'yes',
             'photo-1@content': photo_filename,
             'photo_consent': 'No',
             'diet_consent': 'yes'})
        # Check no image inline on the person page.
        admin_session.check_open_relative('person1')
        self.assertIsNone(admin_session.get_img())
        session.check_open_relative('person1')
        self.assertIsNone(session.get_img())
        reg_session.check_open_relative('person1')
        self.assertIsNone(reg_session.get_img())
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_none = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # A photo was in fact uploaded (nothing in the auditors
        # prevents the creation of the photo item); check it is not
        # accessible anonymously or by registering users.
        session.check_open(img_url_none,
                           error='You are not allowed to view this file',
                           status=403)
        reg_session.check_open(img_url_none,
                               error='You are not allowed to view this file',
                               status=403)
        # Similarly, other users should not be able to access the
        # photo thumbnail.
        img_url_thumb = (self.instance.url
                         + 'photo1?@action=photo_thumb&width=200')
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg_session.check_open(img_url_thumb,
                               error='You do not have permission to view this '
                               'photo',
                               status=403)

    def test_person_photo_create_upper(self):
        """
        Test photos uploaded at person creation time, uppercase .JPG suffix.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.JPG',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    def test_person_photo_create_png(self):
        """
        Test photos uploaded at person creation time, PNG format.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.png',
                                                          'PNG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.png'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    def test_person_photo_create_jpeg(self):
        """
        Test photos uploaded at person creation time, .jpeg suffix.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpeg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(static_site_directory='static-site')
    def test_person_photo_create_static(self):
        """
        Test photos copied from static site at person creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'generic_url': 'https://www.example.invalid/people/person1/'})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(static_site_directory='static-site')
    def test_person_photo_create_static_none(self):
        """
        Test photos not present on static site at person creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'generic_url': 'https://www.example.invalid/people/person3/'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': '3'}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': '3'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])

    @_with_config(static_site_directory='static-site')
    def test_person_photo_create_static_priority(self):
        """
        Test photos uploaded at person creation time take priority
        over those from static site.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'photo-1@content': photo_filename,
             'generic_url': 'https://www.example.invalid/people/person1/'})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_create_static_consent(self):
        """
        Test photos copied from static site at person creation time,
        with consent information handling.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'generic_url': 'https://www.example.invalid/people/person1/',
             'event_photos_consent': 'yes',
             'photo_consent': 'Yes, for website and name badge',
             'diet_consent': 'yes'})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        session.check_open_relative('person1')
        got_bytes = session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        reg_session.check_open_relative('person1')
        got_bytes = reg_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        anon_thumb = session.get_img_contents(False)
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_create_static_consent_badge_only(self):
        """
        Test photos copied from static site at person creation time,
        with consent information handling, badge-only photo.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person1/',
             'event_photos_consent': 'yes',
             'photo_consent': 'Yes, for name badge only',
             'diet_consent': 'yes'})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        reg_session.check_open_relative('person1')
        got_bytes = reg_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(reg_thumb, admin_thumb)
        # Check no image inline on the person page for other users.
        session.check_open_relative('person1')
        self.assertIsNone(session.get_img())
        reg2_session.check_open_relative('person1')
        self.assertIsNone(reg2_session.get_img())
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)
        # Check the photo is not accessible anonymously or by
        # registering users from other countries.
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(img_url_csv,
                                error='You are not allowed to view this file',
                                status=403)
        # Similarly, other users should not be able to access the
        # photo thumbnail.
        img_url_thumb = (self.instance.url
                         + 'photo1?@action=photo_thumb&width=200')
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg2_session.check_open(img_url_thumb,
                                error='You do not have permission to view '
                                'this photo',
                                status=403)

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_create_static_consent_no(self):
        """
        Test photos copied from static site at person creation time,
        with consent information handling, no consent given so not
        copied.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person1/',
             'event_photos_consent': 'yes',
             'photo_consent': 'No',
             'diet_consent': 'yes'})
        # Check no image inline on the person page.
        admin_session.check_open_relative('person1')
        self.assertIsNone(admin_session.get_img())
        session.check_open_relative('person1')
        self.assertIsNone(session.get_img())
        reg_session.check_open_relative('person1')
        self.assertIsNone(reg_session.get_img())
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_create_static_consent_not_applicable(self):
        """
        Test photos copied from static site at person creation time,
        with consent information handling, consent specified as not
        applicable so not copied.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person1/',
             'event_photos_consent': 'yes',
             'photo_consent': 'Not applicable, no photo uploaded',
             'diet_consent': 'yes'})
        # Check no image inline on the person page.
        admin_session.check_open_relative('person1')
        self.assertIsNone(admin_session.get_img())
        session.check_open_relative('person1')
        self.assertIsNone(session.get_img())
        reg_session.check_open_relative('person1')
        self.assertIsNone(reg_session.get_img())
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])

    def test_person_photo_edit(self):
        """
        Test photos uploaded after person creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        admin_session.edit('person', '1', {'photo-1@content': photo_filename})
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        # Check the image inline on the person page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(consent_ui='Yes')
    def test_person_photo_edit_consent(self):
        """
        Test photos uploaded after person creation time, with consent
        information handling.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'event_photos_consent': 'yes',
             'photo_consent': 'Yes, for website and name badge',
             'diet_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        admin_session.edit('person', '1', {'photo-1@content': photo_filename})
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        # Check the image inline on the person page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        session.check_open_relative('person1')
        got_bytes = session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        reg_session.check_open_relative('person1')
        got_bytes = reg_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        anon_thumb = session.get_img_contents(False)
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)
        # Change the consent to badge-only.
        admin_session.edit('person', '1',
                           {'photo_consent': 'Yes, for name badge only'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected2 = {'Photo URL': '', 'Badge Photo URL': None,
                     'Generic Number': ''}
        expected2_admin = {'Photo URL': '', 'Badge Photo URL': img_url_csv,
                           'Generic Number': ''}
        self.assertEqual(anon_csv, [expected2])
        self.assertEqual(admin_csv, [expected2_admin])
        self.assertEqual(reg_csv, [expected2])
        # Check the photo is not accessible anonymously or by
        # registering users from other countries.
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(img_url_csv,
                                error='You are not allowed to view this file',
                                status=403)
        # Likewise, for the thumbnail.
        img_url_thumb = (self.instance.url
                         + 'photo1?@action=photo_thumb&width=200')
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg2_session.check_open(img_url_thumb,
                                error='You do not have permission to view '
                                'this photo',
                                status=403)
        # Restore consent for website.
        admin_session.edit(
            'person', '1',
            {'photo_consent': 'Yes, for website and name badge'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        reg2_bytes = reg2_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)
        self.assertEqual(reg2_bytes, photo_bytes)
        # Likewise, for the thumbnail.
        anon_thumb2 = session.get_bytes(img_url_thumb)
        admin_thumb2 = admin_session.get_bytes(img_url_thumb)
        reg_thumb2 = reg_session.get_bytes(img_url_thumb)
        reg2_thumb2 = reg2_session.get_bytes(img_url_thumb)
        self.assertEqual(anon_thumb2, admin_thumb)
        self.assertEqual(admin_thumb2, admin_thumb)
        self.assertEqual(reg_thumb2, admin_thumb)
        self.assertEqual(reg2_thumb2, admin_thumb)
        # Remove consent, thereby removing the photo.
        admin_session.edit('person', '1',
                           {'photo_consent': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected3 = {'Photo URL': '', 'Badge Photo URL': None,
                     'Generic Number': ''}
        expected3_admin = {'Photo URL': '', 'Badge Photo URL': '',
                           'Generic Number': ''}
        self.assertEqual(anon_csv, [expected3])
        self.assertEqual(admin_csv, [expected3_admin])
        self.assertEqual(reg_csv, [expected3])
        # Check the photo is not accessible anonymously or by
        # registering users from other countries.
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(img_url_csv,
                                error='You are not allowed to view this file',
                                status=403)
        # Likewise, for the thumbnail.
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg2_session.check_open(img_url_thumb,
                                error='You do not have permission to view '
                                'this photo',
                                status=403)
        # Now restoring the consent does not bring the photo back.
        admin_session.edit(
            'person', '1',
            {'photo_consent': 'Yes, for website and name badge'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        self.assertEqual(anon_csv, [expected3])
        self.assertEqual(admin_csv, [expected3_admin])
        self.assertEqual(reg_csv, [expected3])
        # Check the photo is still not accessible anonymously or by
        # registering users from other countries.
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(img_url_csv,
                                error='You are not allowed to view this file',
                                status=403)
        # Likewise, for the thumbnail.
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg2_session.check_open(img_url_thumb,
                                error='You do not have permission to view '
                                'this photo',
                                status=403)

    @_with_config(static_site_directory='static-site')
    def test_person_photo_edit_static(self):
        """
        Test photos copied from static site after person creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
        admin_session.edit(
            'person', '1',
            {'generic_url': 'https://www.example.invalid/people/person1/'})
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        # Check the image inline on the person page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(static_site_directory='static-site')
    def test_person_photo_edit_static_none(self):
        """
        Test photos not present on static site when generic_url set
        after person creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        admin_session.edit(
            'person', '1',
            {'generic_url': 'https://www.example.invalid/people/person3/'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': '3'}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': '3'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])

    @_with_config(static_site_directory='static-site')
    def test_person_photo_edit_static_priority(self):
        """
        Test photos uploaded after person creation time take priority
        over those from static site.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        admin_session.edit(
            'person', '1',
            {'photo-1@content': photo_filename,
             'generic_url': 'https://www.example.invalid/people/person1/'})
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        # Check the image inline on the person page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_edit_static_consent(self):
        """
        Test photos copied from static site after person creation
        time, with consent information handling.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'event_photos_consent': 'yes',
             'photo_consent': 'Yes, for website and name badge',
             'diet_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
        admin_session.edit(
            'person', '1',
            {'generic_url': 'https://www.example.invalid/people/person1/'})
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        # Check the image inline on the person page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        session.check_open_relative('person1')
        got_bytes = session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        reg_session.check_open_relative('person1')
        got_bytes = reg_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        anon_thumb = session.get_img_contents(False)
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_edit_static_consent_badge_only(self):
        """
        Test photos copied from static site after person creation
        time, with consent information handling, badge-only photo.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'event_photos_consent': 'yes',
             'photo_consent': 'Yes, for name badge only',
             'diet_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
        admin_session.edit(
            'person', '1',
            {'generic_url': 'https://www.example.invalid/people/person1/'})
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        # Check the image inline on the person page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        reg_session.check_open_relative('person1')
        got_bytes = reg_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(reg_thumb, admin_thumb)
        # Check no image inline on the person page for other users.
        session.check_open_relative('person1')
        self.assertIsNone(session.get_img())
        reg2_session.check_open_relative('person1')
        self.assertIsNone(reg2_session.get_img())
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)
        # Check the photo is not accessible anonymously or by
        # registering users from other countries.
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(img_url_csv,
                                error='You are not allowed to view this file',
                                status=403)
        # Likewise, for the thumbnail.
        img_url_thumb = (self.instance.url
                         + 'photo1?@action=photo_thumb&width=200')
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg2_session.check_open(img_url_thumb,
                                error='You do not have permission to view '
                                'this photo',
                                status=403)

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_edit_static_consent_no(self):
        """
        Test photos copied from static site after person creation
        time, with consent information handling, no consent given so
        not copied.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'event_photos_consent': 'yes',
             'photo_consent': 'No',
             'diet_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        admin_session.edit(
            'person', '1',
            {'generic_url': 'https://www.example.invalid/people/person1/'})
        # Check no image inline on the person page.
        admin_session.check_open_relative('person1')
        self.assertIsNone(admin_session.get_img())
        session.check_open_relative('person1')
        self.assertIsNone(session.get_img())
        reg_session.check_open_relative('person1')
        self.assertIsNone(reg_session.get_img())
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_edit_static_consent_not_applicable(self):
        """
        Test photos copied from static site after person creation
        time, with consent information handling, consent specified as
        not applicable so not copied.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'event_photos_consent': 'yes',
             'photo_consent': 'Not applicable, no photo uploaded',
             'diet_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        admin_session.edit(
            'person', '1',
            {'generic_url': 'https://www.example.invalid/people/person1/'})
        # Check no image inline on the person page.
        admin_session.check_open_relative('person1')
        self.assertIsNone(admin_session.get_img())
        session.check_open_relative('person1')
        self.assertIsNone(session.get_img())
        reg_session.check_open_relative('person1')
        self.assertIsNone(reg_session.get_img())
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        expected = {'Photo URL': '', 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': '', 'Badge Photo URL': '',
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])

    def test_person_photo_replace(self):
        """
        Test replacing previously uploaded photo.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # Replace the image.
        photo_filename, photo_bytes = self.gen_test_image(3, 3, 3, '.jpg',
                                                          'JPEG')
        admin_session.edit('person', '1', {'photo-1@content': photo_filename})
        # Check the image inline on the person page.
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo2/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    @_with_config(static_site_directory='static-site')
    def test_person_photo_replace_static(self):
        """
        Test setting generic_url after photo uploaded does not change photo.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        admin_session.edit(
            'person', '1',
            {'generic_url': 'https://www.example.invalid/people/person1/'})
        # Check the image inline on the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_img_contents()
        self.assertEqual(got_bytes, photo_bytes)
        admin_thumb = admin_session.get_img_contents(False)
        session.check_open_relative('person1')
        anon_thumb = session.get_img_contents(False)
        reg_session.check_open_relative('person1')
        reg_thumb = reg_session.get_img_contents(False)
        self.assertEqual(file_format_contents(None, admin_thumb), 'jpg')
        self.assertEqual(anon_thumb, admin_thumb)
        self.assertEqual(reg_thumb, admin_thumb)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': '1'}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv,
                          'Generic Number': '1'}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)

    def test_person_photo_replace_access(self):
        """
        Test replaced photo is not public.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)
        # Replace the image.
        old_photo_bytes = photo_bytes
        photo_filename, photo_bytes = self.gen_test_image(3, 3, 3, '.jpg',
                                                          'JPEG')
        admin_session.edit('person', '1', {'photo-1@content': photo_filename})
        # Check the old photo image is no longer public, but is still
        # accessible to admin.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, old_photo_bytes)
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg_session.check_open(img_url_csv,
                               error='You are not allowed to view this file',
                               status=403)
        # Likewise, for the thumbnail.
        img_url_thumb = (self.instance.url
                         + 'photo1?@action=photo_thumb&width=200')
        admin_session.check_get(img_url_thumb, html=False)
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg_session.check_open(img_url_thumb,
                               error='You do not have permission to view '
                               'this photo',
                               status=403)

    def test_person_photo_replace_access_reg(self):
        """
        Test replaced photo is not accessible to registering users
        from other countries.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'photo-1@content': photo_filename})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)
        # Replace the image.
        old_photo_bytes = photo_bytes
        photo_filename, photo_bytes = self.gen_test_image(3, 3, 3, '.jpg',
                                                          'JPEG')
        admin_session.edit('person', '1', {'photo-1@content': photo_filename})
        # Check the old photo image is no longer public, but is still
        # accessible to admin and registering users from that person's
        # country.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, old_photo_bytes)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        self.assertEqual(reg_bytes, old_photo_bytes)
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(img_url_csv,
                                error='You are not allowed to view this file',
                                status=403)
        # Likewise, for the thumbnail.
        img_url_thumb = (self.instance.url
                         + 'photo1?@action=photo_thumb&width=200')
        admin_session.check_get(img_url_thumb, html=False)
        reg_session.check_get(img_url_thumb, html=False)
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg2_session.check_open(img_url_thumb,
                                error='You do not have permission to view '
                                'this photo',
                                status=403)

    def test_person_photo_zip(self):
        """
        Test ZIP file of photos.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_zip_empty = session.get_photos_zip()
        admin_zip_empty = admin_session.get_photos_zip()
        anon_contents = [f.filename for f in anon_zip_empty.infolist()]
        admin_contents = [f.filename for f in admin_zip_empty.infolist()]
        expected_contents = ['photos/README.txt']
        self.assertEqual(anon_contents, expected_contents)
        self.assertEqual(admin_contents, expected_contents)
        anon_zip_empty.close()
        admin_zip_empty.close()
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        anon_zip = session.get_photos_zip()
        admin_zip = admin_session.get_photos_zip()
        anon_contents = [f.filename for f in anon_zip.infolist()]
        admin_contents = [f.filename for f in admin_zip.infolist()]
        expected_contents = ['photos/README.txt', 'photos/person1/photo.jpg']
        self.assertEqual(anon_contents, expected_contents)
        self.assertEqual(admin_contents, expected_contents)
        self.assertEqual(anon_zip.read('photos/person1/photo.jpg'),
                         photo_bytes)
        self.assertEqual(admin_zip.read('photos/person1/photo.jpg'),
                         photo_bytes)
        anon_zip.close()
        admin_zip.close()

    @_with_config(consent_ui='Yes')
    def test_person_photo_zip_consent(self):
        """
        Test ZIP file of photos with consent information handling.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_zip_empty = session.get_photos_zip()
        admin_zip_empty = admin_session.get_photos_zip()
        reg_zip_empty = reg_session.get_photos_zip()
        anon_contents = [f.filename for f in anon_zip_empty.infolist()]
        admin_contents = [f.filename for f in admin_zip_empty.infolist()]
        reg_contents = [f.filename for f in reg_zip_empty.infolist()]
        expected_contents = ['photos/README.txt']
        self.assertEqual(anon_contents, expected_contents)
        self.assertEqual(admin_contents, expected_contents)
        self.assertEqual(reg_contents, expected_contents)
        anon_zip_empty.close()
        admin_zip_empty.close()
        reg_zip_empty.close()
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'event_photos_consent': 'yes',
             'photo-1@content': photo_filename,
             'photo_consent': 'Yes, for website and name badge',
             'diet_consent': 'yes'})
        anon_zip = session.get_photos_zip()
        admin_zip = admin_session.get_photos_zip()
        reg_zip = reg_session.get_photos_zip()
        anon_contents = [f.filename for f in anon_zip.infolist()]
        admin_contents = [f.filename for f in admin_zip.infolist()]
        reg_contents = [f.filename for f in reg_zip.infolist()]
        expected_contents = ['photos/README.txt', 'photos/person1/photo.jpg']
        self.assertEqual(anon_contents, expected_contents)
        self.assertEqual(admin_contents, expected_contents)
        self.assertEqual(reg_contents, expected_contents)
        self.assertEqual(anon_zip.read('photos/person1/photo.jpg'),
                         photo_bytes)
        self.assertEqual(admin_zip.read('photos/person1/photo.jpg'),
                         photo_bytes)
        self.assertEqual(reg_zip.read('photos/person1/photo.jpg'),
                         photo_bytes)
        anon_zip.close()
        admin_zip.close()
        reg_zip.close()
        admin_session.edit('person', '1',
                           {'photo_consent': 'Yes, for name badge only'})
        anon_zip = session.get_photos_zip()
        admin_zip = admin_session.get_photos_zip()
        reg_zip = reg_session.get_photos_zip()
        anon_contents = [f.filename for f in anon_zip.infolist()]
        admin_contents = [f.filename for f in admin_zip.infolist()]
        reg_contents = [f.filename for f in reg_zip.infolist()]
        expected_contents_admin = ['photos/README.txt',
                                   'photos/person1/photo.jpg']
        expected_contents_public = ['photos/README.txt']
        self.assertEqual(anon_contents, expected_contents_public)
        self.assertEqual(admin_contents, expected_contents_admin)
        self.assertEqual(reg_contents, expected_contents_public)
        self.assertEqual(admin_zip.read('photos/person1/photo.jpg'),
                         photo_bytes)
        anon_zip.close()
        admin_zip.close()
        reg_zip.close()
        admin_session.edit('person', '1', {'photo_consent': 'No'})
        anon_zip = session.get_photos_zip()
        admin_zip = admin_session.get_photos_zip()
        reg_zip = reg_session.get_photos_zip()
        anon_contents = [f.filename for f in anon_zip.infolist()]
        admin_contents = [f.filename for f in admin_zip.infolist()]
        reg_contents = [f.filename for f in reg_zip.infolist()]
        expected_contents = ['photos/README.txt']
        self.assertEqual(anon_contents, expected_contents)
        self.assertEqual(admin_contents, expected_contents)
        self.assertEqual(reg_contents, expected_contents)
        anon_zip.close()
        admin_zip.close()
        reg_zip.close()

    def test_person_photo_zip_errors(self):
        """
        Test errors from photos_zip action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        session.check_open_relative('country?@action=photos_zip',
                                    error='This action only applies '
                                    'to people')
        session.check_open_relative('person1?@action=photos_zip',
                                    error='Node id specified for ZIP '
                                    'generation')
        admin_session.check_open_relative('country?@action=photos_zip',
                                          error='This action only applies '
                                          'to people')
        admin_session.check_open_relative('person1?@action=photos_zip',
                                          error='Node id specified for ZIP '
                                          'generation')

    def test_person_photo_thumb_errors(self):
        """
        Test errors from photo_thumb action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        session.check_open_relative('person?@action=photo_thumb',
                                    error='This action only applies '
                                    'to photos')
        session.check_open_relative('photo?@action=photo_thumb',
                                    error='No id specified to generate '
                                    'thumbnail')
        session.check_open_relative('photo1?@action=photo_thumb',
                                    error='No width specified to generate '
                                    'thumbnail')
        session.check_open_relative('photo1?@action=photo_thumb&width=300',
                                    error='Invalid width specified to '
                                    'generate thumbnail')
        # Permission errors are tested in the same functions that test
        # them for non-thumbnail access to photos.
        admin_session.check_open_relative('country?@action=photo_thumb',
                                          error='This action only applies '
                                          'to photos')
        admin_session.check_open_relative('photo?@action=photo_thumb',
                                          error='No id specified to '
                                          'generate thumbnail')
        admin_session.check_open_relative('photo1?@action=photo_thumb',
                                          error='No width specified to '
                                          'generate thumbnail')
        admin_session.check_open_relative('photo1?@action=photo_thumb'
                                          '&width=300',
                                          error='Invalid width specified to '
                                          'generate thumbnail')

    def test_person_consent_form_create(self):
        """
        Test consent forms uploaded at person creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        cf_filename, cf_bytes = self.gen_test_pdf()
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'consent_form-1@content': cf_filename})
        # Check the consent form linked from the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_link_contents(
            'consent form for this person')
        self.assertEqual(got_bytes, cf_bytes)
        admin_csv = admin_session.get_people_csv()
        admin_csv[0] = {'Consent Form URL': admin_csv[0]['Consent Form URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        cf_url_csv = self.instance.url + 'consent_form1/consent-form.pdf'
        expected = {'Consent Form URL': cf_url_csv, 'Generic Number': ''}
        self.assertEqual(admin_csv, [expected])
        # Check the consent form from the URL in the .csv file.
        admin_bytes = admin_session.get_bytes(cf_url_csv)
        reg_bytes = reg_session.get_bytes(cf_url_csv)
        self.assertEqual(admin_bytes, cf_bytes)
        self.assertEqual(reg_bytes, cf_bytes)
        # Check the form is not accessible anonymously or by
        # registering users from other countries.
        session.check_open(cf_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(cf_url_csv,
                                error='You are not allowed to view this file',
                                status=403)

    def test_person_consent_form_create_upper(self):
        """
        Test consent forms uploaded at person creation time, uppercase
        .PDF suffix.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        cf_filename, cf_bytes = self.gen_test_pdf('.PDF')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'consent_form-1@content': cf_filename})
        # Check the consent form linked from the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_link_contents(
            'consent form for this person')
        self.assertEqual(got_bytes, cf_bytes)
        admin_csv = admin_session.get_people_csv()
        admin_csv[0] = {'Consent Form URL': admin_csv[0]['Consent Form URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        cf_url_csv = self.instance.url + 'consent_form1/consent-form.pdf'
        expected = {'Consent Form URL': cf_url_csv, 'Generic Number': ''}
        self.assertEqual(admin_csv, [expected])
        # Check the consent form from the URL in the .csv file.
        admin_bytes = admin_session.get_bytes(cf_url_csv)
        reg_bytes = reg_session.get_bytes(cf_url_csv)
        self.assertEqual(admin_bytes, cf_bytes)
        self.assertEqual(reg_bytes, cf_bytes)
        # Check the form is not accessible anonymously or by
        # registering users from other countries.
        session.check_open(cf_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(cf_url_csv,
                                error='You are not allowed to view this file',
                                status=403)

    def test_person_consent_form_edit(self):
        """
        Test consent forms uploaded after person creation time.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        cf_filename, cf_bytes = self.gen_test_pdf()
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_csv = admin_session.get_people_csv()
        admin_csv[0] = {'Consent Form URL': admin_csv[0]['Consent Form URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        expected = {'Consent Form URL': '', 'Generic Number': ''}
        self.assertEqual(admin_csv, [expected])
        admin_session.edit('person', '1',
                           {'consent_form-1@content': cf_filename})
        cf_url_csv = self.instance.url + 'consent_form1/consent-form.jpg'
        # Check the consent form linked from the person page.
        admin_session.check_open_relative('person1')
        got_bytes = admin_session.get_link_contents(
            'consent form for this person')
        self.assertEqual(got_bytes, cf_bytes)
        admin_csv = admin_session.get_people_csv()
        admin_csv[0] = {'Consent Form URL': admin_csv[0]['Consent Form URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        cf_url_csv = self.instance.url + 'consent_form1/consent-form.pdf'
        expected = {'Consent Form URL': cf_url_csv, 'Generic Number': ''}
        self.assertEqual(admin_csv, [expected])
        # Check the consent form from the URL in the .csv file.
        admin_bytes = admin_session.get_bytes(cf_url_csv)
        reg_bytes = reg_session.get_bytes(cf_url_csv)
        self.assertEqual(admin_bytes, cf_bytes)
        self.assertEqual(reg_bytes, cf_bytes)
        # Check the form is not accessible anonymously or by
        # registering users from other countries.
        session.check_open(cf_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(cf_url_csv,
                                error='You are not allowed to view this file',
                                status=403)

    def test_person_consent_form_zip(self):
        """
        Test ZIP file of consent forms.
        """
        admin_session = self.get_session('admin')
        admin_zip_empty = admin_session.get_consent_forms_zip()
        admin_contents = [f.filename for f in admin_zip_empty.infolist()]
        expected_contents = ['consent-forms/README.txt']
        self.assertEqual(admin_contents, expected_contents)
        admin_zip_empty.close()
        cf_filename, cf_bytes = self.gen_test_pdf()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'consent_form-1@content': cf_filename})
        admin_zip = admin_session.get_consent_forms_zip()
        admin_contents = [f.filename for f in admin_zip.infolist()]
        expected_contents = ['consent-forms/README.txt',
                             'consent-forms/person1/consent-form.pdf']
        self.assertEqual(admin_contents, expected_contents)
        self.assertEqual(
            admin_zip.read('consent-forms/person1/consent-form.pdf'),
            cf_bytes)
        admin_zip.close()

    def test_person_consent_form_zip_errors(self):
        """
        Test errors from consent_forms_zip action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        session.check_open_relative('country?@action=consent_forms_zip',
                                    error='This action only applies '
                                    'to people')
        session.check_open_relative('person1?@action=consent_forms_zip',
                                    error='Node id specified for ZIP '
                                    'generation')
        admin_session.check_open_relative('country?@action=consent_forms_zip',
                                          error='This action only applies '
                                          'to people')
        admin_session.check_open_relative('person1?@action=consent_forms_zip',
                                          error='Node id specified for ZIP '
                                          'generation')
        session.check_open_relative('person?@action=consent_forms_zip',
                                    error='You do not have permission to '
                                    'access consent forms', status=403)
        reg_session.check_open_relative('person?@action=consent_forms_zip',
                                        error='You do not have permission to '
                                        'access consent forms', status=403)

    def test_person_retire(self):
        """
        Test retiring people.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_session.check_open_relative('person1')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        # Test lack of anonymous access to the retired person page
        # (but a registering user for that country should still be
        # able to view it).
        session.check_open_relative('person1', login=True)
        reg_session.check_open_relative('person1')
        reg2_session.check_open_relative('person1', login=True)
        admin_session.check_open_relative('person1')

    def test_person_retire_photo_access(self):
        """
        Test photo of retired person is not public.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'photo-1@content': photo_filename})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        anon_csv[0] = {'Photo URL': anon_csv[0]['Photo URL'],
                       'Badge Photo URL': anon_csv[0].get('Badge Photo URL'),
                       'Generic Number': anon_csv[0]['Generic Number']}
        admin_csv[0] = {'Photo URL': admin_csv[0]['Photo URL'],
                        'Badge Photo URL': admin_csv[0]['Badge Photo URL'],
                        'Generic Number': admin_csv[0]['Generic Number']}
        reg_csv[0] = {'Photo URL': reg_csv[0]['Photo URL'],
                      'Badge Photo URL': reg_csv[0].get('Badge Photo URL'),
                      'Generic Number': reg_csv[0]['Generic Number']}
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected = {'Photo URL': img_url_csv, 'Badge Photo URL': None,
                    'Generic Number': ''}
        expected_admin = {'Photo URL': img_url_csv,
                          'Badge Photo URL': img_url_csv, 'Generic Number': ''}
        self.assertEqual(anon_csv, [expected])
        self.assertEqual(admin_csv, [expected_admin])
        self.assertEqual(reg_csv, [expected])
        admin_session.check_open_relative('person1')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        # Check the old photo image is no longer public, but is still
        # accessible to admin and to a registering user from that
        # country.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, photo_bytes)
        reg_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(reg_bytes, photo_bytes)
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg2_session.check_open(img_url_csv,
                                error='You are not allowed to view this file',
                                status=403)
        # Likewise, for the thumbnail.
        img_url_thumb = (self.instance.url
                         + 'photo1?@action=photo_thumb&width=200')
        admin_session.check_get(img_url_thumb, html=False)
        reg_session.check_get(img_url_thumb, html=False)
        session.check_open(img_url_thumb,
                           error='You do not have permission to view this '
                           'photo',
                           status=403)
        reg2_session.check_open(img_url_thumb,
                                error='You do not have permission to view '
                                'this photo',
                                status=403)

    def test_person_retire_errors(self):
        """
        Test errors retiring people.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        # Error trying to retire person via GET request.
        admin_session.check_open_relative('person1?@action=retire',
                                          error='Invalid request')
        # Permission error (requires user to have valid form, then
        # have permissions removed, then try submitting it).
        admin_session.create_user('admin2', 'XMO 2015 Staff', 'Admin')
        admin2_session = self.get_session('admin2')
        admin2_session.check_open_relative('person1')
        admin2_session.b.select_form(
            admin2_session.get_main().find_all('form')[1])
        admin2_session.check_submit_selected()
        admin2_session.select_main_form()
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to retire',
                                             status=403)
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'Admin'})
        reg_session = self.get_session('ABC_reg')
        reg_session.check_open_relative('person1')
        reg_session.b.select_form(
            reg_session.get_main().find_all('form')[1])
        reg_session.check_submit_selected()
        reg_session.select_main_form()
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'User,Register'})
        reg_session.check_submit_selected(error='You do not have '
                                          'permission to retire', status=403)

    def test_person_create_audit_errors(self):
        """
        Test errors from person creation auditor.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '(day)'},
                                    error='No day of birth specified')
        admin_session.create_person('Test First Country', 'Contestant 2',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': '(month)',
                                     'date_of_birth_day': '10'},
                                    error='No month of birth specified')
        admin_session.create_person('Test First Country', 'Contestant 3',
                                    {'date_of_birth_year': '(year)',
                                     'date_of_birth_month': 'December',
                                     'date_of_birth_day': '10'},
                                    error='No year of birth specified')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'date_of_birth_year': '2000',
                                   'date_of_birth_month': 'January',
                                   'date_of_birth_day': '(day)'},
                                  error='No day of birth specified')
        reg_session.create_person('Test First Country', 'Contestant 2',
                                  {'date_of_birth_year': '2000',
                                   'date_of_birth_month': '(month)',
                                   'date_of_birth_day': '10'},
                                  error='No month of birth specified')
        reg_session.create_person('Test First Country', 'Contestant 3',
                                  {'date_of_birth_year': '(year)',
                                   'date_of_birth_month': 'December',
                                   'date_of_birth_day': '10'},
                                  error='No year of birth specified')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '1995',
                                     'date_of_birth_month': 'April',
                                     'date_of_birth_day': '1'},
                                    error='Contestant too old')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '1995',
                                     'date_of_birth_month': 'March',
                                     'date_of_birth_day': '31'},
                                    error='Contestant too old')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '1994',
                                     'date_of_birth_month': 'December',
                                     'date_of_birth_day': '31'},
                                    error='Contestant too old')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'date_of_birth_year': '1995',
                                   'date_of_birth_month': 'April',
                                   'date_of_birth_day': '1'},
                                  error='Contestant too old')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'date_of_birth_year': '1995',
                                   'date_of_birth_month': 'March',
                                   'date_of_birth_day': '31'},
                                  error='Contestant too old')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'date_of_birth_year': '1994',
                                   'date_of_birth_month': 'December',
                                   'date_of_birth_day': '31'},
                                  error='Contestant too old')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'arrival_date': '2 April 2015',
                                     'departure_date': '1 April 2015'},
                                    error='Departure date before arrival date')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'arrival_date': '2 April 2015',
                                     'arrival_time_hour': '14',
                                     'arrival_time_minute': '00',
                                     'departure_date': '2 April 2015',
                                     'departure_time_hour': '13',
                                     'departure_time_minute': '59'},
                                    error='Departure time before arrival time')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'arrival_date': '2 April 2015',
                                   'departure_date': '1 April 2015'},
                                  error='Departure date before arrival date')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'arrival_date': '2 April 2015',
                                   'arrival_time_hour': '14',
                                   'arrival_time_minute': '00',
                                   'departure_date': '2 April 2015',
                                   'departure_time_hour': '13',
                                   'departure_time_minute': '59'},
                                  error='Departure time before arrival time')
        photo_filename, dummy = self.gen_test_pdf()
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'photo-1@content': photo_filename},
                                    error='Photos must be in JPEG or PNG '
                                    'format')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'photo-1@content': photo_filename},
                                  error='Photos must be in JPEG or PNG '
                                  'format')
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'PNG')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'photo-1@content': photo_filename},
                                    error=r'Filename extension for photo must '
                                    r'match contents \(png\)')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'photo-1@content': photo_filename},
                                  error=r'Filename extension for photo must '
                                  r'match contents \(png\)')
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.png', 'JPEG')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'photo-1@content': photo_filename},
                                    error=r'Filename extension for photo must '
                                    r'match contents \(jpg\)')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'photo-1@content': photo_filename},
                                  error=r'Filename extension for photo must '
                                  r'match contents \(jpg\)')
        cf_filename, dummy = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'consent_form-1@content': cf_filename},
                                    error='Consent forms must be in PDF '
                                    'format')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'consent_form-1@content': cf_filename},
                                  error='Consent forms must be in PDF '
                                  'format')
        cf_filename, dummy = self.gen_test_pdf('.png')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'consent_form-1@content': cf_filename},
                                    error=r'Filename extension for consent '
                                    r'form must match contents \(pdf\)')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'consent_form-1@content': cf_filename},
                                  error=r'Filename extension for consent '
                                  r'form must match contents \(pdf\)')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person0/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person01/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person1'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person1N/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person0/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person01/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person1'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person1N/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_country('ZZZ', 'None 2',
                                     {'participants_ok': 'no'})
        admin_session.create_person(
            'None', 'Jury Chair', error='Invalid country')
        admin_session.create_person(
            'None 2', 'Chief Coordinator', error='Invalid country')
        admin_session.create_person('XMO 2015 Staff', 'Contestant 1',
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Leader',
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Deputy Leader',
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Observer with Leader',
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Observer with Deputy',
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff',
                                    'Observer with Contestants',
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Chief Invigilator',
                                    {'other_roles': ['Chief Guide',
                                                     'Contestant 1']},
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Chief Invigilator',
                                    {'other_roles': ['Leader']},
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Chief Invigilator',
                                    {'other_roles': ['Deputy Leader']},
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Chief Invigilator',
                                    {'other_roles': ['Observer with Leader']},
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Chief Invigilator',
                                    {'other_roles': ['Observer with Deputy']},
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Chief Invigilator',
                                    {'other_roles':
                                     ['Observer with Contestants']},
                                    error='Staff must have administrative '
                                    'roles')
        admin_session.create_person('Test First Country', 'Coordinator',
                                    error='Invalid role for participant')
        admin_session.create_person('Test First Country', 'Leader',
                                    {'other_roles': ['Jury Chair']},
                                    error='Non-staff may not have secondary '
                                    'roles')
        admin_session.create_person('XMO 2015 Staff', 'Chief Guide',
                                    {'guide_for': ['Test First Country']},
                                    error='People with this role may not '
                                    'guide a country')
        admin_session.create_person('XMO 2015 Staff', 'Guide',
                                    {'guide_for': ['XMO 2015 Staff']},
                                    error='May only guide normal countries')
        admin_session.create_person('Test First Country', 'Leader',
                                    {'phone_number': '123456789'},
                                    error='Phone numbers may only be entered '
                                    'for staff')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])

    def test_person_create_audit_errors_missing(self):
        """
        Test errors from person creation auditor, missing required data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create('person',
                             {'primary_role': 'Leader',
                              'given_name': 'Given',
                              'family_name': 'Family',
                              'gender': 'Female',
                              'language_1': 'English',
                              'tshirt': 'S'},
                             error='Required person property country '
                             'not supplied')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'given_name': None},
                                    error='Required person property '
                                    'given_name not supplied')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'given_name': None},
                                  error='Required person property '
                                  'given_name not supplied')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'family_name': None},
                                    error='Required person property '
                                    'family_name not supplied')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'family_name': None},
                                  error='Required person property '
                                  'family_name not supplied')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'gender': None},
                                    error='Required person property gender '
                                    'not supplied')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'gender': None},
                                  error='Required person property gender '
                                  'not supplied')
        admin_session.create('person',
                             {'country': 'Test First Country',
                              'given_name': 'Given',
                              'family_name': 'Family',
                              'gender': 'Female',
                              'language_1': 'English',
                              'tshirt': 'S'},
                             error='Required person property primary_role '
                             'not supplied')
        reg_session.create('person',
                           {'country': 'Test First Country',
                            'given_name': 'Given',
                            'family_name': 'Family',
                            'gender': 'Female',
                            'language_1': 'English',
                            'tshirt': 'S'},
                           error='Required person property primary_role '
                           'not supplied')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'language_1': None},
                                    error='Required person property '
                                    'language_1 not supplied')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'language_1': None},
                                  error='Required person property '
                                  'language_1 not supplied')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'tshirt': None},
                                    error='Required person property tshirt '
                                    'not supplied')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'tshirt': None},
                                  error='Required person property tshirt '
                                  'not supplied')
        # The above errors are generic Roundup ones that rely on
        # @required being sent by the browser, so must not be relied
        # upon to maintain required properties of data since the
        # browser should not be trusted; also verify the checks from
        # the auditor in case @required is not sent.
        admin_session.create('person',
                             {'@required': '',
                              'primary_role': 'Leader',
                              'given_name': 'Given',
                              'family_name': 'Family',
                              'gender': 'Female',
                              'language_1': 'English',
                              'tshirt': 'S'},
                             error='No country specified')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'@required': '',
                                     'given_name': None},
                                    error='No given name specified')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'@required': '',
                                   'given_name': None},
                                  error='No given name specified')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'@required': '',
                                     'family_name': None},
                                    error='No family name specified')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'@required': '',
                                   'family_name': None},
                                  error='No family name specified')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'@required': '',
                                     'gender': None},
                                    error='No gender specified')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'@required': '',
                                   'gender': None},
                                  error='No gender specified')
        admin_session.create('person',
                             {'@required': '',
                              'country': 'Test First Country',
                              'given_name': 'Given',
                              'family_name': 'Family',
                              'gender': 'Female',
                              'language_1': 'English',
                              'tshirt': 'S'},
                             error='No primary role specified')
        reg_session.create('person',
                           {'@required': '',
                            'country': 'Test First Country',
                            'given_name': 'Given',
                            'family_name': 'Family',
                            'gender': 'Female',
                            'language_1': 'English',
                            'tshirt': 'S'},
                           error='No primary role specified')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'@required': '',
                                     'language_1': None},
                                    error='No first language specified')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'@required': '',
                                   'language_1': None},
                                  error='No first language specified')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'@required': '',
                                     'tshirt': None},
                                    error='No T-shirt size specified')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'@required': '',
                                   'tshirt': None},
                                  error='No T-shirt size specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])

    @_with_config(require_date_of_birth='Yes')
    def test_person_create_audit_errors_missing_date_of_birth(self):
        """
        Test errors from person creation auditor, missing date of birth.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '(day)'},
                                    error='Required person property '
                                    'date_of_birth_day not supplied')
        admin_session.create_person('Test First Country', 'Leader',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': '(month)',
                                     'date_of_birth_day': '10'},
                                    error='Required person property '
                                    'date_of_birth_month not supplied')
        admin_session.create_person('Test First Country', 'Leader',
                                    {'date_of_birth_year': '(year)',
                                     'date_of_birth_month': 'December',
                                     'date_of_birth_day': '10'},
                                    error='Required person property '
                                    'date_of_birth_year not supplied')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'date_of_birth_year': '2000',
                                   'date_of_birth_month': 'January',
                                   'date_of_birth_day': '(day)'},
                                  error='Required person property '
                                  'date_of_birth_day not supplied')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'date_of_birth_year': '2000',
                                   'date_of_birth_month': '(month)',
                                   'date_of_birth_day': '10'},
                                  error='Required person property '
                                  'date_of_birth_month not supplied')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'date_of_birth_year': '(year)',
                                   'date_of_birth_month': 'December',
                                   'date_of_birth_day': '10'},
                                  error='Required person property '
                                  'date_of_birth_year not supplied')
        # The above errors are generic Roundup ones that rely on
        # @required being sent by the browser, so must not be relied
        # upon to maintain required properties of data since the
        # browser should not be trusted; also verify the checks from
        # the auditor in case @required is not sent.
        admin_session.create_person('Test First Country', 'Deputy Leader',
                                    {'@required': '',
                                     'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '(day)'},
                                    error='No day of birth specified')
        admin_session.create_person('Test First Country', 'Deputy Leader',
                                    {'@required': '',
                                     'date_of_birth_year': '2000',
                                     'date_of_birth_month': '(month)',
                                     'date_of_birth_day': '10'},
                                    error='No month of birth specified')
        admin_session.create_person('Test First Country', 'Deputy Leader',
                                    {'@required': '',
                                     'date_of_birth_year': '(year)',
                                     'date_of_birth_month': 'December',
                                     'date_of_birth_day': '10'},
                                    error='No year of birth specified')
        reg_session.create_person('Test First Country', 'Deputy Leader',
                                  {'@required': '',
                                   'date_of_birth_year': '2000',
                                   'date_of_birth_month': 'January',
                                   'date_of_birth_day': '(day)'},
                                  error='No day of birth specified')
        reg_session.create_person('Test First Country', 'Deputy Leader',
                                  {'@required': '',
                                   'date_of_birth_year': '2000',
                                   'date_of_birth_month': '(month)',
                                   'date_of_birth_day': '10'},
                                  error='No month of birth specified')
        reg_session.create_person('Test First Country', 'Deputy Leader',
                                  {'@required': '',
                                   'date_of_birth_year': '(year)',
                                   'date_of_birth_month': 'December',
                                   'date_of_birth_day': '10'},
                                  error='No year of birth specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])

    @_with_config(consent_ui='Yes')
    def test_person_create_audit_errors_missing_consent(self):
        """
        Test errors from person creation auditor, missing required
        consent information.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'diet_consent': 'yes'},
            error='No choice of consent for photos specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'event_photos_consent': 'yes'},
            error='No choice of consent for allergies and dietary '
            'requirements information specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'photo-1@content': photo_filename,
             'event_photos_consent': 'yes',
             'photo_consent': 'Not applicable, no photo uploaded',
             'diet_consent': 'yes'},
            error='No choice of consent for registration photo specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])

    @_with_config(require_passport_number='Yes')
    def test_person_create_audit_errors_missing_passport_number(self):
        """
        Test errors from person creation auditor, missing passport number.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader',
                                    error='Required person property '
                                    'passport_number not supplied')
        reg_session.create_person('Test First Country', 'Leader',
                                  error='Required person property '
                                  'passport_number not supplied')
        # The above errors are generic Roundup ones that rely on
        # @required being sent by the browser, so must not be relied
        # upon to maintain required properties of data since the
        # browser should not be trusted; also verify the checks from
        # the auditor in case @required is not sent.
        admin_session.create_person('Test First Country', 'Leader',
                                    {'@required': ''},
                                    error='No passport or identity card '
                                    'number specified')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'@required': ''},
                                  error='No passport or identity card number '
                                  'specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])

    @_with_config(require_nationality='Yes')
    def test_person_create_audit_errors_missing_nationality(self):
        """
        Test errors from person creation auditor, missing nationality.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader',
                                    error='Required person property '
                                    'nationality not supplied')
        reg_session.create_person('Test First Country', 'Leader',
                                  error='Required person property '
                                  'nationality not supplied')
        # The above errors are generic Roundup ones that rely on
        # @required being sent by the browser, so must not be relied
        # upon to maintain required properties of data since the
        # browser should not be trusted; also verify the checks from
        # the auditor in case @required is not sent.
        admin_session.create_person('Test First Country', 'Leader',
                                    {'@required': ''},
                                    error='No nationality specified')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'@required': ''},
                                  error='No nationality specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])

    @_with_config(require_diet='Yes')
    def test_person_create_audit_errors_missing_diet(self):
        """
        Test errors from person creation auditor, missing diet.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader',
                                    error='Required person property '
                                    'diet not supplied')
        reg_session.create_person('Test First Country', 'Leader',
                                  error='Required person property '
                                  'diet not supplied')
        # The above errors are generic Roundup ones that rely on
        # @required being sent by the browser, so must not be relied
        # upon to maintain required properties of data since the
        # browser should not be trusted; also verify the checks from
        # the auditor in case @required is not sent.
        admin_session.create_person('Test First Country', 'Leader',
                                    {'@required': ''},
                                    error='Allergies and dietary requirements '
                                    'not specified')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'@required': ''},
                                  error='Allergies and dietary requirements '
                                  'not specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        # Verify creation is OK once diet specified (require_diet not
        # otherwise tested).
        reg_session.create_person('Test First Country', 'Leader',
                                  {'diet': 'Vegetarian'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_create_audit_errors_bad_country(self):
        """
        Test errors from person creation auditor: bad country for
        registering user.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'Admin', 'country': 'XMO 2015 Staff'})
        reg_session = self.get_session('ABC_reg')
        reg_session.check_open_relative('person?@template=item')
        reg_session.select_main_form()
        reg_session.set({'country': 'XMO 2015 Staff',
                         'primary_role': 'Leader',
                         'given_name': 'Given',
                         'family_name': 'Family',
                         'gender': 'Female',
                         'language_1': 'English',
                         'tshirt': 'M'})
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'User,Register',
                            'country': 'Test First Country'})
        reg_session.check_submit_selected(error='Person must be from your '
                                          'country')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])

    def test_person_create_audit_errors_registration_disabled(self):
        """
        Test errors from person creation auditor: registration disabled.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.edit('event', '1', {'registration_enabled': 'no'})
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  error='Registration has not yet opened')
        admin_session.edit('event', '1', {'preregistration_enabled': 'no'})
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  error='Registration is now disabled, please '
                                  'contact the event organisers to change '
                                  'details of registered participants')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        # Admin accounts can still register people.
        admin_session.create_person('Test First Country', 'Contestant 1')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_create_audit_errors_gender_any(self):
        """
        Test errors from person creation auditor: all contestant
        genders allowed by default.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'gender': 'Female'})
        reg_session.create_person('Test First Country', 'Contestant 2',
                                  {'gender': 'Male'})
        admin_session.create_person('Test First Country', 'Contestant 3',
                                    {'gender': 'Non-binary'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 3)
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(len(reg_csv), 3)

    @_with_config(contestant_genders='Female')
    def test_person_create_audit_errors_gender_one(self):
        """
        Test errors from person creation auditor: one contestant
        gender allowed.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 2',
                                  {'gender': 'Male'},
                                  error='Contestant gender must be Female')
        admin_session.create_person('Test First Country', 'Contestant 3',
                                    {'gender': 'Non-binary'},
                                    error='Contestant gender must be Female')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'gender': 'Female'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    @_with_config(contestant_genders='Female, Non-binary')
    def test_person_create_audit_errors_gender_multi(self):
        """
        Test errors from person creation auditor: multiple contestant
        genders allowed.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 2',
                                  {'gender': 'Male'},
                                  error='Contestant gender must be Female or '
                                  'Non-binary')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'gender': 'Female'})
        admin_session.create_person('Test First Country', 'Contestant 3',
                                    {'gender': 'Non-binary'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)

    def test_person_create_audit_errors_room_type_one(self):
        """
        Test errors from person creation auditor: restrictions on room
        types.  One room type allowed for contestants by default.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 2',
                                  {'room_type': 'Single room'},
                                  error='Room type for this role must be '
                                  'Shared room')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'room_type': 'Shared room'})
        reg_session.create_person('Test First Country', 'Leader',
                                  {'room_type': 'Single room'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)

    def test_person_create_audit_errors_room_type_one_admin(self):
        """
        Test errors from person creation auditor: restrictions on room
        types.  One room type allowed for contestants by default, but
        administrative users can override.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 2',
                                    {'room_type': 'Single room'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    @_with_config(initial_room_types='Shared room, Single room, Tent, Palace',
                  initial_room_types_non_contestant='Single room, Palace',
                  initial_room_types_contestant='Tent, Shared room',
                  initial_default_room_type_non_contestant='Palace',
                  initial_default_room_type_contestant='Tent')
    def test_person_create_audit_errors_room_type_config(self):
        """
        Test errors from person creation auditor: restrictions on room
        types.  Configured variations on default rules.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 2',
                                  {'room_type': 'Palace'},
                                  error='Room type for this role must be '
                                  'Tent or Shared room')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'room_type': 'Tent'},
                                  error='Room type for this role must be '
                                  'Single room or Palace')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'room_type': 'Shared room'})
        reg_session.create_person('Test First Country', 'Contestant 2',
                                  {'room_type': 'Tent'})
        reg_session.create_person('Test First Country', 'Contestant 6')
        reg_session.create_person('Test First Country', 'Leader')
        reg_session.create_person('Test First Country', 'Observer with Deputy',
                                  {'room_type': 'Single room'})
        reg_session.create_person('Test First Country', 'Observer with Leader',
                                  {'room_type': 'Palace'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 6)
        self.assertEqual(len(admin_csv), 6)
        self.assertEqual(len(reg_csv), 6)
        # Test the defaults.
        self.assertEqual(admin_csv[2]['Primary Role'], 'Contestant 6')
        self.assertEqual(admin_csv[2]['Room Type'], 'Tent')
        self.assertEqual(admin_csv[3]['Primary Role'], 'Leader')
        self.assertEqual(admin_csv[3]['Room Type'], 'Palace')

    @_with_config(sanity_date_of_birth='2014-02-03')
    def test_person_create_audit_errors_date_of_birth_edge(self):
        """
        Test errors from person creation auditor: date of birth edge cases.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        # Invalid: date of birth before the sanity-check date (note
        # year before that not actually offered on form, so needs to
        # be added here to exercise that auditor check).
        reg_session.check_open_relative('person?@template=item')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'date_of_birth_year'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='1901')
        new_option.string = '1901'
        select.append(new_option)
        reg_session.set({'country': 'Test First Country',
                         'primary_role': 'Leader',
                         'given_name': 'Given',
                         'family_name': 'Family',
                         'gender': 'Female',
                         'language_1': 'English',
                         'tshirt': 'M',
                         'date_of_birth_year': '1901',
                         'date_of_birth_month': 'December',
                         'date_of_birth_day': '31'})
        reg_session.check_submit_selected(error='Participant implausibly old')
        # Invalid: date of birth after the sanity-check date (note
        # sanity check date changed for this test to make it more
        # convenient to enter such dates than with the default
        # setting).
        admin_session.create_person('Test First Country', 'Contestant 2',
                                    {'date_of_birth_year': '2014',
                                     'date_of_birth_month': 'February',
                                     'date_of_birth_day': '3'},
                                    error='Participant implausibly young')
        admin_session.create_person('Test First Country', 'Contestant 2',
                                    {'date_of_birth_year': '2014',
                                     'date_of_birth_month': 'December',
                                     'date_of_birth_day': '1'},
                                    error='Participant implausibly young')
        # Last invalid contestant date of birth is tested above.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        # Valid: first possible date of birth.
        reg_session.create_person('Test First Country', 'Leader',
                                  {'date_of_birth_year': '1902',
                                   'date_of_birth_month': 'January',
                                   'date_of_birth_day': '1'})
        # Valid: last possible date of birth.
        admin_session.create_person('Test First Country', 'Deputy Leader',
                                    {'date_of_birth_year': '2014',
                                     'date_of_birth_month': 'February',
                                     'date_of_birth_day': '2'})
        # Valid: first possible contestant date of birth.
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'date_of_birth_year': '1995',
                                   'date_of_birth_month': 'April',
                                   'date_of_birth_day': '2'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 3)
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(len(reg_csv), 3)

    def test_person_create_audit_errors_arrival_departure_edge(self):
        """
        Test errors from person creation auditor: arrival / departure
        date and time edge cases.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        # Invalid: arrival or departure dates too early or too late
        # (note not actually offered on form, so needs to be added
        # here to exercise that auditor check).
        reg_session.check_open_relative('person?@template=item')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'arrival_date'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='2015-03-30')
        new_option.string = '30 March 2015'
        select.append(new_option)
        reg_session.set({'country': 'Test First Country',
                         'primary_role': 'Leader',
                         'given_name': 'Given',
                         'family_name': 'Family',
                         'gender': 'Female',
                         'language_1': 'English',
                         'tshirt': 'M',
                         'arrival_date': '30 March 2015'})
        reg_session.check_submit_selected(error='arrival date too early')
        reg_session.check_open_relative('person?@template=item')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'arrival_date'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='2015-04-03')
        new_option.string = '3 April 2015'
        select.append(new_option)
        reg_session.set({'country': 'Test First Country',
                         'primary_role': 'Leader',
                         'given_name': 'Given',
                         'family_name': 'Family',
                         'gender': 'Female',
                         'language_1': 'English',
                         'tshirt': 'M',
                         'arrival_date': '3 April 2015'})
        reg_session.check_submit_selected(error='arrival date too late')
        reg_session.check_open_relative('person?@template=item')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'departure_date'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='2015-03-31')
        new_option.string = '31 March 2015'
        select.append(new_option)
        reg_session.set({'country': 'Test First Country',
                         'primary_role': 'Leader',
                         'given_name': 'Given',
                         'family_name': 'Family',
                         'gender': 'Female',
                         'language_1': 'English',
                         'tshirt': 'M',
                         'departure_date': '31 March 2015'})
        reg_session.check_submit_selected(error='departure date too early')
        reg_session.check_open_relative('person?@template=item')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'departure_date'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='2015-04-04')
        new_option.string = '4 April 2015'
        select.append(new_option)
        reg_session.set({'country': 'Test First Country',
                         'primary_role': 'Leader',
                         'given_name': 'Given',
                         'family_name': 'Family',
                         'gender': 'Female',
                         'language_1': 'English',
                         'tshirt': 'M',
                         'departure_date': '4 April 2015'})
        reg_session.check_submit_selected(error='departure date too late')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        # Valid: earliest possible arrival and departure dates.
        reg_session.create_person('Test First Country', 'Leader',
                                  {'arrival_date': '31 March 2015',
                                   'departure_date': '1 April 2015'})
        # Valid: latest possible arrival and departure dates.
        admin_session.create_person('Test First Country', 'Deputy Leader',
                                    {'arrival_date': '2 April 2015',
                                     'departure_date': '3 April 2015'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)

    @_with_config(static_site_directory='static-site')
    def test_person_create_audit_errors_static(self):
        """
        Test errors from person creation auditor, static site checks.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person12345/'},
            error=r'example\.invalid URL for previous participation not valid')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person12345/'},
            error=r'example\.invalid URL for previous participation not valid')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])

    def test_person_create_audit_errors_static_none(self):
        """
        Test errors from person creation auditor, any person number
        valid for previous participation when no static site data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person12345/'})
        reg_session.create_person(
            'Test First Country', 'Contestant 2',
            {'generic_url':
             'https://www.example.invalid/people/person54321/'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)

    def test_person_create_audit_errors_role_secondary(self):
        """
        Test errors from person creation auditor, secondary roles OK.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person(
            'Test First Country', 'Leader',
            {'other_roles': ['XMO AB']})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_create_audit_errors_role_unique(self):
        """
        Test errors from person creation auditor, non-observer roles
        for normal countries unique.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader')
        reg_session.create_person('Test First Country', 'Deputy Leader')
        admin_session.create_person('Test First Country', 'Contestant 1')
        reg_session.create_person('Test First Country', 'Observer with Leader')
        admin_session.create_person('Test First Country',
                                    'Observer with Deputy')
        reg_session.create_person('Test First Country',
                                  'Observer with Contestants')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 6)
        self.assertEqual(len(admin_csv), 6)
        self.assertEqual(len(reg_csv), 6)
        admin_session.create_person('Test First Country', 'Leader',
                                    error='A person with this role already '
                                    'exists')
        admin_session.create_person('Test First Country', 'Deputy Leader',
                                    error='A person with this role already '
                                    'exists')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    error='A person with this role already '
                                    'exists')
        reg_session.create_person('Test First Country', 'Leader',
                                  error='A person with this role already '
                                  'exists')
        reg_session.create_person('Test First Country', 'Deputy Leader',
                                  error='A person with this role already '
                                  'exists')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  error='A person with this role already '
                                  'exists')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv, anon_csv_2)
        self.assertEqual(admin_csv, admin_csv_2)
        self.assertEqual(reg_csv, reg_csv_2)
        reg_session.create_person('Test First Country', 'Observer with Leader')
        admin_session.create_person('Test First Country',
                                    'Observer with Deputy')
        reg_session.create_person('Test First Country',
                                  'Observer with Contestants')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 9)
        self.assertEqual(len(admin_csv), 9)
        self.assertEqual(len(reg_csv), 9)

    def test_person_create_audit_errors_guide_extra(self):
        """
        Test errors from person creation auditor, extra roles allowed to guide.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create('matholymprole',
                             {'name': 'Extra Guide', 'canguide': 'yes',
                              'default_room_type': 'Shared room',
                              'badge_type': 'Guide'})
        admin_session.create_person(
            'XMO 2015 Staff', 'Extra Guide',
            {'guide_for': ['Test First Country']})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_create_audit_errors_phone_number(self):
        """
        Test errors from person creation auditor, phone nunbers OK for staff.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        # Phone numbers are allowed for all staff, not just Guides as
        # was originally the case.
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'phone_number': '123'})
        admin_session.create_person(
            'XMO 2015 Staff', 'Jury Chair',
            {'phone_number': '456'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)

    def test_person_edit_audit_errors(self):
        """
        Test errors from person edit auditor.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        # Persons 1, 2, 3: missing some date of birth data (and thus
        # in fact the other such data removed by the auditor on
        # creation), so changing to contestants produces errors.
        admin_session.create_person('Test First Country', 'Leader',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '(day)'})
        admin_session.create_person('Test First Country', 'Deputy Leader',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': '(month)',
                                     'date_of_birth_day': '10'})
        admin_session.create_person('Test First Country',
                                    'Observer with Leader',
                                    {'date_of_birth_year': '(year)',
                                     'date_of_birth_month': 'December',
                                     'date_of_birth_day': '10'})
        # Persons 4, 5: contestant (with arrival date set), and person
        # too old to change to contestant.
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '10',
                                     'arrival_date': '2 April 2015'})
        admin_session.create_person('Test First Country',
                                    'Observer with Deputy',
                                    {'date_of_birth_year': '1980',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '10'})
        # Persons 6, 7, 8: staff with settings preventing certain changes.
        admin_session.create_person('XMO 2015 Staff', 'Guide',
                                    {'guide_for': ['Test First Country']})
        admin_session.create_person('XMO 2015 Staff', 'Jury Chair',
                                    {'phone_number': '123'})
        admin_session.create_person('XMO 2015 Staff', 'Chief Coordinator',
                                    {'other_roles': ['Logistics']})
        # None of the failed edits should change the data for these people.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 8)
        self.assertEqual(len(admin_csv), 8)
        self.assertEqual(len(reg_csv), 8)
        admin_session.edit('person', '1',
                           {'primary_role': 'Contestant 3',
                            'date_of_birth_year': '2000',
                            'date_of_birth_month': 'January'},
                           error='No day of birth specified')
        admin_session.edit('person', '2',
                           {'primary_role': 'Contestant 3',
                            'date_of_birth_year': '2000',
                            'date_of_birth_day': '10'},
                           error='No month of birth specified')
        admin_session.edit('person', '3',
                           {'primary_role': 'Contestant 3',
                            'date_of_birth_month': 'December',
                            'date_of_birth_day': '10'},
                           error='No year of birth specified')
        reg_session.edit('person', '1',
                         {'primary_role': 'Contestant 3',
                          'date_of_birth_year': '2000',
                          'date_of_birth_month': 'January'},
                         error='No day of birth specified')
        reg_session.edit('person', '2',
                         {'primary_role': 'Contestant 3',
                          'date_of_birth_year': '2000',
                          'date_of_birth_day': '10'},
                         error='No month of birth specified')
        reg_session.edit('person', '3',
                         {'primary_role': 'Contestant 3',
                          'date_of_birth_month': 'December',
                          'date_of_birth_day': '10'},
                         error='No year of birth specified')
        admin_session.edit('person', '4',
                           {'date_of_birth_year': '1995',
                            'date_of_birth_month': 'April',
                            'date_of_birth_day': '1'},
                           error='Contestant too old')
        admin_session.edit('person', '4',
                           {'date_of_birth_year': '1995',
                            'date_of_birth_month': 'March',
                            'date_of_birth_day': '31'},
                           error='Contestant too old')
        admin_session.edit('person', '4',
                           {'date_of_birth_year': '1994',
                            'date_of_birth_month': 'December',
                            'date_of_birth_day': '31'},
                           error='Contestant too old')
        reg_session.edit('person', '4',
                         {'date_of_birth_year': '1995',
                          'date_of_birth_month': 'April',
                          'date_of_birth_day': '1'},
                         error='Contestant too old')
        reg_session.edit('person', '4',
                         {'date_of_birth_year': '1995',
                          'date_of_birth_month': 'March',
                          'date_of_birth_day': '31'},
                         error='Contestant too old')
        reg_session.edit('person', '4',
                         {'date_of_birth_year': '1994',
                          'date_of_birth_month': 'December',
                          'date_of_birth_day': '31'},
                         error='Contestant too old')
        admin_session.edit('person', '5',
                           {'primary_role': 'Contestant 3'},
                           error='Contestant too old')
        reg_session.edit('person', '5',
                         {'primary_role': 'Contestant 3'},
                         error='Contestant too old')
        admin_session.edit('person', '4',
                           {'departure_date': '1 April 2015'},
                           error='Departure date before arrival date')
        admin_session.edit('person', '4',
                           {'arrival_time_hour': '14',
                            'arrival_time_minute': '00',
                            'departure_date': '2 April 2015',
                            'departure_time_hour': '13',
                            'departure_time_minute': '59'},
                           error='Departure time before arrival time')
        reg_session.edit('person', '4',
                         {'departure_date': '1 April 2015'},
                         error='Departure date before arrival date')
        reg_session.edit('person', '4',
                         {'arrival_time_hour': '14',
                          'arrival_time_minute': '00',
                          'departure_date': '2 April 2015',
                          'departure_time_hour': '13',
                          'departure_time_minute': '59'},
                         error='Departure time before arrival time')
        photo_filename, dummy = self.gen_test_pdf()
        admin_session.edit('person', '4',
                           {'photo-1@content': photo_filename},
                           error='Photos must be in JPEG or PNG format')
        reg_session.edit('person', '4',
                         {'photo-1@content': photo_filename},
                         error='Photos must be in JPEG or PNG format')
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'PNG')
        admin_session.edit('person', '4',
                           {'photo-1@content': photo_filename},
                           error=r'Filename extension for photo must '
                           r'match contents \(png\)')
        reg_session.edit('person', '4',
                         {'photo-1@content': photo_filename},
                         error=r'Filename extension for photo must '
                         r'match contents \(png\)')
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.png', 'JPEG')
        admin_session.edit('person', '4',
                           {'photo-1@content': photo_filename},
                           error=r'Filename extension for photo must '
                           r'match contents \(jpg\)')
        reg_session.edit('person', '4',
                         {'photo-1@content': photo_filename},
                         error=r'Filename extension for photo must '
                         r'match contents \(jpg\)')
        cf_filename, dummy = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.edit('person', '4',
                           {'consent_form-1@content': cf_filename},
                           error='Consent forms must be in PDF format')
        reg_session.edit('person', '4',
                         {'consent_form-1@content': cf_filename},
                         error='Consent forms must be in PDF format')
        cf_filename, dummy = self.gen_test_pdf('.png')
        admin_session.edit('person', '4',
                           {'consent_form-1@content': cf_filename},
                           error=r'Filename extension for consent '
                           r'form must match contents \(pdf\)')
        reg_session.edit('person', '4',
                         {'consent_form-1@content': cf_filename},
                         error=r'Filename extension for consent '
                         r'form must match contents \(pdf\)')
        admin_session.edit(
            'person', '4',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.edit(
            'person', '4',
            {'generic_url': 'https://www.example.invalid/people/person0/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.edit(
            'person', '4',
            {'generic_url':
             'https://www.example.invalid/people/person01/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.edit(
            'person', '4',
            {'generic_url': 'https://www.example.invalid/people/person1'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.edit(
            'person', '4',
            {'generic_url':
             'https://www.example.invalid/people/person1N/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.edit(
            'person', '4',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.edit(
            'person', '4',
            {'generic_url': 'https://www.example.invalid/people/person0/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.edit(
            'person', '4',
            {'generic_url':
             'https://www.example.invalid/people/person01/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.edit(
            'person', '4',
            {'generic_url': 'https://www.example.invalid/people/person1'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        reg_session.edit(
            'person', '4',
            {'generic_url':
             'https://www.example.invalid/people/person1N/'},
            error=r'example.invalid URLs for previous participation must be '
            r'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_country('ZZZ', 'None 2',
                                     {'participants_ok': 'no'})
        admin_session.edit('person', '4',
                           {'country': 'None', 'primary_role': 'Jury Chair'},
                           error='Invalid country')
        admin_session.edit('person', '4',
                           {'country': 'None 2',
                            'primary_role': 'Chief Coordinator'},
                           error='Invalid country')
        admin_session.edit('person', '1',
                           {'country': 'XMO 2015 Staff'},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '2',
                           {'country': 'XMO 2015 Staff'},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '3',
                           {'country': 'XMO 2015 Staff'},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '4',
                           {'country': 'XMO 2015 Staff'},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '5',
                           {'country': 'XMO 2015 Staff'},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '6',
                           {'primary_role': 'Leader'},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '7',
                           {'primary_role': 'Deputy Leader'},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '6',
                           {'other_roles': ['Contestant 2']},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '7',
                           {'other_roles': ['Transport', 'Contestant 3']},
                           error='Staff must have administrative roles')
        admin_session.edit('person', '1',
                           {'primary_role': 'Coordinator'},
                           error='Invalid role for participant')
        admin_session.edit('person', '6',
                           {'country': 'Test First Country'},
                           error='Invalid role for participant')
        admin_session.edit('person', '1',
                           {'other_roles': ['Coordinator']},
                           error='Non-staff may not have secondary roles')
        admin_session.edit('person', '8',
                           {'country': 'Test First Country',
                            'primary_role': 'Observer with Contestants'},
                           error='Non-staff may not have secondary roles')
        admin_session.edit('person', '6',
                           {'primary_role': 'Chief Guide'},
                           error='People with this role may not guide a '
                           'country')
        admin_session.edit('person', '7',
                           {'guide_for': ['Test First Country']},
                           error='People with this role may not guide a '
                           'country')
        admin_session.edit('person', '6',
                           {'guide_for': ['XMO 2015 Staff']},
                           error='May only guide normal countries')
        admin_session.edit('person', '7',
                           {'country': 'Test First Country',
                            'primary_role': 'Observer with Leader'},
                           error='Phone numbers may only be entered for staff')
        admin_session.edit('person', '5',
                           {'phone_number': '31415926'},
                           error='Phone numbers may only be entered for staff')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    def test_person_edit_audit_errors_missing(self):
        """
        Test errors from person edit auditor, missing required data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '10'})
        # None of the failed edits should change the data for these people.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        admin_session.edit('person', '1',
                           {'country': ['- no selection -']},
                           error='Required person property country not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'country': ['- no selection -']},
                         error='Required person property country not supplied')
        admin_session.edit('person', '1',
                           {'given_name': ''},
                           error='Required person property given_name not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'given_name': ''},
                         error='Required person property given_name not '
                         'supplied')
        admin_session.edit('person', '1',
                           {'family_name': ''},
                           error='Required person property family_name not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'family_name': ''},
                         error='Required person property family_name not '
                         'supplied')
        admin_session.edit('person', '1',
                           {'gender': ['- no selection -']},
                           error='Required person property gender not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'gender': ['- no selection -']},
                         error='Required person property gender not supplied')
        admin_session.edit('person', '1',
                           {'primary_role': ['- no selection -']},
                           error='Required person property primary_role not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'primary_role': ['- no selection -']},
                         error='Required person property primary_role not '
                         'supplied')
        admin_session.edit('person', '1',
                           {'language_1': ['- no selection -']},
                           error='Required person property language_1 not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'language_1': ['- no selection -']},
                         error='Required person property language_1 not '
                         'supplied')
        admin_session.edit('person', '1',
                           {'tshirt': ['- no selection -']},
                           error='Required person property tshirt not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'tshirt': ['- no selection -']},
                         error='Required person property tshirt not supplied')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # With @required not sent, the auditor restores the previous
        # values.
        admin_session.edit('person', '1',
                           {'@required': '',
                            'country': ['- no selection -'],
                            'given_name': '',
                            'family_name': '',
                            'gender': ['- no selection -'],
                            'primary_role': ['- no selection -'],
                            'language_1': ['- no selection -'],
                            'tshirt': ['- no selection -']})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        reg_session.edit('person', '1',
                         {'@required': '',
                          'country': ['- no selection -'],
                          'given_name': '',
                          'family_name': '',
                          'gender': ['- no selection -'],
                          'primary_role': ['- no selection -'],
                          'language_1': ['- no selection -'],
                          'tshirt': ['- no selection -']})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    @_with_config(require_date_of_birth='Yes')
    def test_person_edit_audit_errors_missing_date_of_birth(self):
        """
        Test errors from person edit auditor, missing date of birth.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '10'})
        # None of the failed edits should change the data for these
        # people.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        admin_session.edit('person', '1',
                           {'date_of_birth_year': '(year)'},
                           error='Required person property date_of_birth_year '
                           'not supplied')
        reg_session.edit('person', '1',
                         {'date_of_birth_year': '(year)'},
                         error='Required person property date_of_birth_year '
                         'not supplied')
        admin_session.edit('person', '1',
                           {'date_of_birth_month': '(month)'},
                           error='Required person property '
                           'date_of_birth_month not supplied')
        reg_session.edit('person', '1',
                         {'date_of_birth_month': '(month)'},
                         error='Required person property date_of_birth_month '
                         'not supplied')
        admin_session.edit('person', '1',
                           {'date_of_birth_day': '(day)'},
                           error='Required person property date_of_birth_day '
                           'not supplied')
        reg_session.edit('person', '1',
                         {'date_of_birth_day': '(day)'},
                         error='Required person property date_of_birth_day '
                         'not supplied')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # With @required not sent, the auditor restores the previous
        # values.
        admin_session.edit('person', '1',
                           {'@required': '',
                            'date_of_birth_year': '(year)'})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        reg_session.edit('person', '1',
                         {'@required': '',
                          'date_of_birth_year': '(year)'})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        admin_session.edit('person', '1',
                           {'@required': '',
                            'date_of_birth_month': '(month)'})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        reg_session.edit('person', '1',
                         {'@required': '',
                          'date_of_birth_month': '(month)'})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        admin_session.edit('person', '1',
                           {'@required': '',
                            'date_of_birth_day': '(day)'})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        reg_session.edit('person', '1',
                         {'@required': '',
                          'date_of_birth_day': '(day)'})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    @_with_config(consent_ui='Yes')
    def test_person_edit_audit_errors_missing_consent(self):
        """
        Test errors from person edit auditor, missing required consent
        information.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'event_photos_consent': 'yes',
             'photo_consent': 'Not applicable, no photo uploaded',
             'diet_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        # "Not applicable" set, then uploading photo.
        admin_session.edit(
            'person', '1',
            {'photo-1@content': photo_filename},
            error='No choice of consent for registration photo specified')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'photo-1@content': photo_filename,
             'event_photos_consent': 'yes',
             'photo_consent': 'Yes, for website and name badge',
             'diet_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        # Photo uploaded, then "not applicable" set.
        admin_session.edit(
            'person', '2',
            {'photo_consent': 'Not applicable, no photo uploaded'},
            error='No choice of consent for registration photo specified')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        admin_session.create_person(
            'XMO 2015 Staff', 'Coordinator',
            {'event_photos_consent': 'yes',
             'photo_consent': 'Yes, for website and name badge',
             'diet_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(anon_csv), 3)
        self.assertEqual(len(admin_csv), 3)
        # Person created, then "not applicable" set together with
        # uploading photo.
        admin_session.edit(
            'person', '3',
            {'photo-1@content': photo_filename,
             'photo_consent': 'Not applicable, no photo uploaded'},
            error='No choice of consent for registration photo specified')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)

    @_with_config(require_passport_number='Yes')
    def test_person_edit_audit_errors_missing_passport_number(self):
        """
        Test errors from person edit auditor, missing passport number.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '10',
                                     'passport_number': '123456789'})
        # None of the failed edits should change the data for these people.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        admin_session.edit('person', '1',
                           {'passport_number': ''},
                           error='Required person property passport_number '
                           'not supplied')
        reg_session.edit('person', '1',
                         {'passport_number': ''},
                         error='Required person property passport_number '
                         'not supplied')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # With @required not sent, the auditor restores the previous
        # values.
        admin_session.edit('person', '1',
                           {'@required': '',
                            'passport_number': ''})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        reg_session.edit('person', '1',
                         {'@required': '',
                          'passport_number': ''})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    @_with_config(require_nationality='Yes')
    def test_person_edit_audit_errors_missing_nationality(self):
        """
        Test errors from person edit auditor, missing nationality.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '10',
                                     'nationality': 'Matholympian'})
        # None of the failed edits should change the data for these people.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        admin_session.edit('person', '1',
                           {'nationality': ''},
                           error='Required person property nationality not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'nationality': ''},
                         error='Required person property nationality not '
                         'supplied')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # With @required not sent, the auditor restores the previous
        # values.
        admin_session.edit('person', '1',
                           {'@required': '',
                            'nationality': ''})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        reg_session.edit('person', '1',
                         {'@required': '',
                          'nationality': ''})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    @_with_config(require_diet='Yes')
    def test_person_edit_audit_errors_missing_diet(self):
        """
        Test errors from person edit auditor, missing diet.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '10',
                                     'diet': 'Vegan'})
        # None of the failed edits should change the data for these people.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        admin_session.edit('person', '1',
                           {'diet': ''},
                           error='Required person property diet not '
                           'supplied')
        reg_session.edit('person', '1',
                         {'diet': ''},
                         error='Required person property diet not '
                         'supplied')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # With @required not sent, the auditor restores the previous
        # values.
        admin_session.edit('person', '1',
                           {'@required': '',
                            'diet': ''})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        reg_session.edit('person', '1',
                         {'@required': '',
                          'diet': ''})
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    def test_person_edit_audit_errors_bad_country(self):
        """
        Test errors from person edit auditor: bad country for
        registering user.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        # None of the failed edits should change the data for these people.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'Admin', 'country': 'XMO 2015 Staff'})
        reg_session.check_open_relative('person1')
        reg_session.select_main_form()
        reg_session.set({'country': 'XMO 2015 Staff',
                         'primary_role': 'Coordinator'})
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'User,Register',
                            'country': 'Test First Country'})
        reg_session.check_submit_selected(error='Person must be from your '
                                          'country')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # If the person is already registered as from another country,
        # a permission error from the Roundup core results.
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'Admin', 'country': 'XMO 2015 Staff'})
        reg_session.check_open_relative('person2')
        reg_session.select_main_form()
        reg_session.set({'country': 'Test First Country',
                         'primary_role': 'Leader'})
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'User,Register',
                            'country': 'Test First Country'})
        reg_session.check_submit_selected(error='You do not have permission '
                                          'to edit', status=403)
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    def test_person_edit_audit_errors_registration_disabled(self):
        """
        Test errors from person edit auditor: registration disabled.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 1')
        # The failed edit should not change the data for this person.
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        admin_session.edit('event', '1', {'registration_enabled': 'no'})
        reg_session.edit('person', '1',
                         {'primary_role': 'Contestant 2'},
                         error='Registration has not yet opened')
        admin_session.edit('event', '1', {'preregistration_enabled': 'no'})
        reg_session.edit('person', '1',
                         {'primary_role': 'Contestant 2'},
                         error='Registration is now disabled, please contact '
                         'the event organisers to change details of '
                         'registered participants')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # Admin accounts can still change registered details.
        admin_session.edit('person', '1',
                           {'primary_role': 'Contestant 2'})
        anon_csv[0]['Primary Role'] = 'Contestant 2'
        anon_csv[0]['Contestant Code'] = 'ABC2'
        admin_csv[0]['Primary Role'] = 'Contestant 2'
        admin_csv[0]['Contestant Code'] = 'ABC2'
        reg_csv[0]['Primary Role'] = 'Contestant 2'
        reg_csv[0]['Contestant Code'] = 'ABC2'
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    def test_person_edit_audit_errors_gender_any(self):
        """
        Test errors from person edit auditor: all contestant genders
        allowed by default.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'gender': 'Female'})
        reg_session.create_person('Test First Country', 'Contestant 2',
                                  {'gender': 'Male'})
        admin_session.create_person('Test First Country', 'Leader',
                                    {'gender': 'Non-binary'})
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'gender': 'Non-binary'})
        reg_session.edit('person', '1', {'gender': 'Male'})
        admin_session.edit('person', '2', {'gender': 'Non-binary'})
        reg_session.edit('person', '3', {'gender': 'Female',
                                         'primary_role': 'Contestant 3'})
        admin_session.edit('person', '4', {'gender': 'Non-binary',
                                           'country': 'Test First Country',
                                           'primary_role': 'Contestant 4'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 4)
        self.assertEqual(len(admin_csv), 4)
        self.assertEqual(len(reg_csv), 4)

    @_with_config(contestant_genders='Female')
    def test_person_edit_audit_errors_gender_one(self):
        """
        Test errors from person edit auditor: one contestant gender
        allowed.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'gender': 'Female'})
        admin_session.create_person('Test First Country', 'Leader',
                                    {'gender': 'Male'})
        reg_session.create_person('Test First Country', 'Deputy Leader',
                                  {'gender': 'Non-binary'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 3)
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(len(reg_csv), 3)
        reg_session.edit('person', '1', {'gender': 'Male'},
                         error='Contestant gender must be Female')
        admin_session.edit('person', '2', {'primary_role': 'Contestant 2'},
                           error='Contestant gender must be Female')
        reg_session.edit('person', '3', {'primary_role': 'Contestant 3'},
                         error='Contestant gender must be Female')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        admin_session.edit('person', '1', {'primary_role': 'Contestant 2'})
        reg_session.edit('person', '3', {'gender': 'Female',
                                         'primary_role': 'Contestant 3'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 3)
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(len(reg_csv), 3)

    @_with_config(contestant_genders='Female, Non-binary')
    def test_person_edit_audit_errors_gender_multi(self):
        """
        Test errors from person edit auditor: multiple contestant
        genders allowed.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'gender': 'Female'})
        admin_session.create_person('Test First Country', 'Leader',
                                    {'gender': 'Male'})
        reg_session.create_person('Test First Country', 'Deputy Leader',
                                  {'gender': 'Non-binary'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 3)
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(len(reg_csv), 3)
        reg_session.edit('person', '1', {'gender': 'Male'},
                         error='Contestant gender must be Female or '
                         'Non-binary')
        admin_session.edit('person', '2', {'primary_role': 'Contestant 2'},
                           error='Contestant gender must be Female or '
                           'Non-binary')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        admin_session.edit('person', '1', {'primary_role': 'Contestant 2',
                                           'gender': 'Non-binary'})
        reg_session.edit('person', '3', {'primary_role': 'Contestant 3'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 3)
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(len(reg_csv), 3)

    def test_person_edit_audit_errors_room_type_one(self):
        """
        Test errors from person edit auditor: restrictions on room
        types.  One room type allowed for contestants by default.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 2')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'room_type': 'Single room'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)
        reg_session.edit('person', '1',
                         {'room_type': 'Single room'},
                         error='Room type for this role must be Shared room')
        reg_session.edit('person', '2',
                         {'primary_role': 'Contestant 5'},
                         error='Room type for this role must be Shared room')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    def test_person_edit_audit_errors_room_type_one_admin(self):
        """
        Test errors from person edit auditor: restrictions on room
        types.  One room type allowed for contestants by default, but
        administrative users can override.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 2')
        reg_session.create_person('Test First Country', 'Leader',
                                  {'room_type': 'Single room'})
        admin_session.edit('person', '1',
                           {'room_type': 'Single room'})
        admin_session.edit('person', '2',
                           {'primary_role': 'Contestant 5'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)
        # Having been overridden by an administrative user,
        # registering users can still edit other data.
        reg_session.edit('person', '1',
                         {'diet': 'Vegetarian'})
        reg_session.edit('person', '2',
                         {'diet': 'Vegan'})

    @_with_config(initial_room_types='Shared room, Single room, Tent, Palace',
                  initial_room_types_non_contestant='Single room, Palace',
                  initial_room_types_contestant='Tent, Shared room',
                  initial_default_room_type_non_contestant='Palace',
                  initial_default_room_type_contestant='Tent')
    def test_person_edit_audit_errors_room_type_config(self):
        """
        Test errors from person edit auditor: restrictions on room
        types.  Configured variations on default rules.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 1')
        reg_session.create_person('Test First Country', 'Leader')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)
        reg_session.edit('person', '1',
                         {'room_type': 'Palace'},
                         error='Room type for this role must be Tent or '
                         'Shared room')
        reg_session.edit('person', '1',
                         {'room_type': 'Single room'},
                         error='Room type for this role must be Tent or '
                         'Shared room')
        reg_session.edit('person', '1',
                         {'primary_role': 'Deputy Leader'},
                         error='Room type for this role must be '
                         'Single room or Palace')
        reg_session.edit('person', '2',
                         {'room_type': 'Tent'},
                         error='Room type for this role must be '
                         'Single room or Palace')
        reg_session.edit('person', '2',
                         {'room_type': 'Shared room'},
                         error='Room type for this role must be '
                         'Single room or Palace')
        reg_session.edit('person', '2',
                         {'primary_role': 'Contestant 3'},
                         error='Room type for this role must be Tent or '
                         'Shared room')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    @_with_config(sanity_date_of_birth='2014-02-03')
    def test_person_edit_audit_errors_date_of_birth_edge(self):
        """
        Test errors from person edit auditor: date of birth edge cases.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        # Invalid: date of birth before the sanity-check date (note
        # year before that not actually offered on form, so needs to
        # be added here to exercise that auditor check).
        reg_session.check_open_relative('person1')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'date_of_birth_year'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='1901')
        new_option.string = '1901'
        select.append(new_option)
        reg_session.set({'date_of_birth_year': '1901',
                         'date_of_birth_month': 'December',
                         'date_of_birth_day': '31'})
        reg_session.check_submit_selected(error='Participant implausibly old')
        # Invalid: date of birth after the sanity-check date (note
        # sanity check date changed for this test to make it more
        # convenient to enter such dates than with the default
        # setting).
        admin_session.edit('person', '1',
                           {'date_of_birth_year': '2014',
                            'date_of_birth_month': 'February',
                            'date_of_birth_day': '3'},
                           error='Participant implausibly young')
        admin_session.edit('person', '1',
                           {'date_of_birth_year': '2014',
                            'date_of_birth_month': 'December',
                            'date_of_birth_day': '1'},
                           error='Participant implausibly young')
        # Last invalid contestant date of birth is tested above.
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # Valid: first possible date of birth.
        reg_session.edit('person', '1',
                         {'primary_role': 'Leader',
                          'date_of_birth_year': '1902',
                          'date_of_birth_month': 'January',
                          'date_of_birth_day': '1'})
        # Valid: last possible date of birth.
        admin_session.edit('person', '1',
                           {'date_of_birth_year': '2014',
                            'date_of_birth_month': 'February',
                            'date_of_birth_day': '2'})
        # Valid: first possible contestant date of birth.
        reg_session.edit('person', '1',
                         {'primary_role': 'Contestant 4',
                          'date_of_birth_year': '1995',
                          'date_of_birth_month': 'April',
                          'date_of_birth_day': '2'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_edit_audit_errors_arrival_departure_edge(self):
        """
        Test errors from person edit auditor: arrival / departure date
        and time edge cases.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        # Invalid: arrival or departure dates too early or too late
        # (note not actually offered on form, so needs to be added
        # here to exercise that auditor check).
        reg_session.check_open_relative('person1')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'arrival_date'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='2015-03-30')
        new_option.string = '30 March 2015'
        select.append(new_option)
        reg_session.set({'arrival_date': '30 March 2015'})
        reg_session.check_submit_selected(error='arrival date too early')
        reg_session.check_open_relative('person1')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'arrival_date'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='2015-04-03')
        new_option.string = '3 April 2015'
        select.append(new_option)
        reg_session.set({'arrival_date': '3 April 2015'})
        reg_session.check_submit_selected(error='arrival date too late')
        reg_session.check_open_relative('person1')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'departure_date'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='2015-03-31')
        new_option.string = '31 March 2015'
        select.append(new_option)
        reg_session.set({'departure_date': '31 March 2015'})
        reg_session.check_submit_selected(error='departure date too early')
        reg_session.check_open_relative('person1')
        reg_session.select_main_form()
        form = reg_session.b.get_current_form().form
        select = form.find('select', attrs={'name': 'departure_date'})
        new_option = reg_session.b.get_current_page().new_tag(
            'option', value='2015-04-04')
        new_option.string = '4 April 2015'
        select.append(new_option)
        reg_session.set({'departure_date': '4 April 2015'})
        reg_session.check_submit_selected(error='departure date too late')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)
        # Valid: earliest possible arrival and departure dates.
        reg_session.edit('person', '1',
                         {'arrival_date': '31 March 2015',
                          'departure_date': '1 April 2015'})
        # Valid: latest possible arrival and departure dates.
        admin_session.edit('person', '1',
                           {'arrival_date': '2 April 2015',
                            'departure_date': '3 April 2015'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    @_with_config(static_site_directory='static-site')
    def test_person_edit_audit_errors_static(self):
        """
        Test errors from person edit auditor, static site checks.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        admin_session.edit(
            'person', '1',
            {'generic_url':
             'https://www.example.invalid/people/person12345/'},
            error=r'example\.invalid URL for previous participation not valid')
        reg_session.edit(
            'person', '1',
            {'generic_url':
             'https://www.example.invalid/people/person12345/'},
            error=r'example\.invalid URL for previous participation not valid')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv_2, anon_csv)
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(reg_csv_2, reg_csv)

    def test_person_edit_audit_errors_static_none(self):
        """
        Test errors from person edit auditor, any person number valid
        for previous participation when no static site data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        admin_session.edit(
            'person', '1',
            {'generic_url':
             'https://www.example.invalid/people/person12345/'})
        reg_session.edit(
            'person', '1',
            {'generic_url':
             'https://www.example.invalid/people/person54321/'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_edit_audit_errors_role_secondary(self):
        """
        Test errors from person edit auditor, secondary roles OK.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader')
        admin_session.edit(
            'person', '1',
            {'other_roles': ['XMO AB']})
        reg_session.edit(
            'person', '1',
            {'primary_role': 'Deputy Leader'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_edit_audit_errors_role_unique(self):
        """
        Test errors from person edit auditor, non-observer roles for
        normal countries unique.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader')
        reg_session.create_person('Test First Country', 'Deputy Leader')
        admin_session.create_person('Test First Country', 'Contestant 1')
        reg_session.create_person('Test First Country', 'Observer with Leader')
        admin_session.create_person('Test First Country',
                                    'Observer with Deputy')
        reg_session.create_person('Test First Country',
                                  'Observer with Contestants')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 6)
        self.assertEqual(len(admin_csv), 6)
        self.assertEqual(len(reg_csv), 6)
        admin_session.edit('person', '2',
                           {'primary_role': 'Leader'},
                           error='A person with this role already exists')
        admin_session.edit('person', '1',
                           {'primary_role': 'Deputy Leader'},
                           error='A person with this role already exists')
        admin_session.edit('person', '4',
                           {'primary_role': 'Contestant 1'},
                           error='A person with this role already exists')
        reg_session.edit('person', '2',
                         {'primary_role': 'Leader'},
                         error='A person with this role already exists')
        reg_session.edit('person', '1',
                         {'primary_role': 'Deputy Leader'},
                         error='A person with this role already exists')
        reg_session.edit('person', '4',
                         {'primary_role': 'Contestant 1'},
                         error='A person with this role already exists')
        anon_csv_2 = session.get_people_csv()
        admin_csv_2 = admin_session.get_people_csv()
        reg_csv_2 = reg_session.get_people_csv()
        self.assertEqual(anon_csv, anon_csv_2)
        self.assertEqual(admin_csv, admin_csv_2)
        self.assertEqual(reg_csv, reg_csv_2)
        reg_session.edit('person', '1',
                         {'primary_role': 'Observer with Leader'})
        admin_session.edit('person', '2',
                           {'primary_role': 'Observer with Deputy'})
        reg_session.edit('person', '3',
                         {'primary_role': 'Observer with Contestants'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 6)
        self.assertEqual(len(admin_csv), 6)
        self.assertEqual(len(reg_csv), 6)

    def test_person_edit_audit_errors_guide_extra(self):
        """
        Test errors from person edit auditor, extra roles allowed to guide.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create('matholymprole',
                             {'name': 'Extra Guide', 'canguide': 'yes',
                              'default_room_type': 'Shared room',
                              'badge_type': 'Guide'})
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'guide_for': ['Test First Country']})
        admin_session.edit('person', '1',
                           {'primary_role': 'Extra Guide'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_edit_audit_errors_phone_number(self):
        """
        Test errors from person edit auditor, phone nunbers OK for staff.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        # Phone numbers are allowed for all staff, not just Guides as
        # was originally the case.
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'phone_number': '123'})
        admin_session.edit('person', '1',
                           {'primary_role': 'Jury Chair'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    def test_person_multilink_null_edit(self):
        """
        Test null edits on multilinks involving "no selection".

        First case of Roundup issue 2550722.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_csv = admin_session.get_people_csv()
        admin_session.edit('person', '1',
                           {'guide_for': ['Test First Country']},
                           error='People with this role may not '
                           'guide a country')
        admin_session.select_main_form()
        admin_session.set({'guide_for': ['- no selection -']})
        admin_session.check_submit_selected()
        admin_csv_2 = admin_session.get_people_csv()
        self.assertEqual(admin_csv, admin_csv_2)

    def test_person_multilink_create_corrected(self):
        """
        Test corrections to multilinks involving "no selection" when
        creating people.

        Second case of Roundup issue 2550722.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'guide_for': ['Test First Country']},
                                    error='People with this role may not '
                                    'guide a country')
        admin_session.select_main_form()
        admin_session.set({'guide_for': ['- no selection -']})
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(admin_csv[0]['Primary Role'], 'Contestant 1')
        self.assertEqual(admin_csv[0]['Guide For'], '')

    def test_person_multilink_create_error(self):
        """
        Test errors with multilinks involving "no selection" when
        creating people.

        Third case of Roundup issue 2550722.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'guide_for': ['Test First Country']},
                                    error='People with this role may not '
                                    'guide a country')
        admin_session.select_main_form()
        admin_session.set({'primary_role': 'Coordinator',
                           'guide_for': ['- no selection -']})
        admin_session.check_submit_selected(error='Invalid role for '
                                            'participant')
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 0)

    def test_person_date_time_partial(self):
        """
        Test creating people with partial arrival / departure times.
        """
        # Test for a former bug where if arrival / departure time
        # details were deleted at person creation time (because of
        # missing date, or missing hour when minute is specified), an
        # internal error resulted.
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Chief Coordinator',
                                    {'arrival_time_hour': '00',
                                     'departure_time_minute': '01'})
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(admin_csv[0]['Arrival Date'], '')
        self.assertEqual(admin_csv[0]['Arrival Time'], '')
        self.assertEqual(admin_csv[0]['Departure Date'], '')
        self.assertEqual(admin_csv[0]['Departure Time'], '')
        admin_session.create_person('XMO 2015 Staff', 'Chief Guide',
                                    {'arrival_date': '1 April 2015',
                                     'arrival_time_minute': '59',
                                     'departure_date': '2 April 2015',
                                     'departure_time_minute': '01'})
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(admin_csv[0]['Arrival Date'], '')
        self.assertEqual(admin_csv[0]['Arrival Time'], '')
        self.assertEqual(admin_csv[0]['Departure Date'], '')
        self.assertEqual(admin_csv[0]['Departure Time'], '')
        self.assertEqual(admin_csv[1]['Arrival Date'], '2015-04-01')
        self.assertEqual(admin_csv[1]['Arrival Time'], '')
        self.assertEqual(admin_csv[1]['Departure Date'], '2015-04-02')
        self.assertEqual(admin_csv[1]['Departure Time'], '')
        # Verify setting and then partially unsetting details.
        admin_session.select_main_form()
        admin_session.set({'arrival_time_hour': '23',
                           'arrival_time_minute': '30',
                           'departure_time_hour': '09',
                           'departure_time_minute': '45'})
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(admin_csv[0]['Arrival Date'], '')
        self.assertEqual(admin_csv[0]['Arrival Time'], '')
        self.assertEqual(admin_csv[0]['Departure Date'], '')
        self.assertEqual(admin_csv[0]['Departure Time'], '')
        self.assertEqual(admin_csv[1]['Arrival Date'], '2015-04-01')
        self.assertEqual(admin_csv[1]['Arrival Time'], '23:30')
        self.assertEqual(admin_csv[1]['Departure Date'], '2015-04-02')
        self.assertEqual(admin_csv[1]['Departure Time'], '09:45')
        admin_session.select_main_form()
        admin_session.set({'arrival_time_hour': '(hour)',
                           'departure_date': '(date)'})
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(admin_csv[0]['Arrival Date'], '')
        self.assertEqual(admin_csv[0]['Arrival Time'], '')
        self.assertEqual(admin_csv[0]['Departure Date'], '')
        self.assertEqual(admin_csv[0]['Departure Time'], '')
        self.assertEqual(admin_csv[1]['Arrival Date'], '2015-04-01')
        self.assertEqual(admin_csv[1]['Arrival Time'], '')
        self.assertEqual(admin_csv[1]['Departure Date'], '')
        self.assertEqual(admin_csv[1]['Departure Time'], '')
        # Test minute defaulting to 00 when not specified.
        admin_session.create_person('XMO 2015 Staff', 'Transport',
                                    {'arrival_date': '1 April 2015',
                                     'arrival_time_hour': '10',
                                     'departure_date': '2 April 2015',
                                     'departure_time_hour': '20'})
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(admin_csv[0]['Arrival Date'], '')
        self.assertEqual(admin_csv[0]['Arrival Time'], '')
        self.assertEqual(admin_csv[0]['Departure Date'], '')
        self.assertEqual(admin_csv[0]['Departure Time'], '')
        self.assertEqual(admin_csv[1]['Arrival Date'], '2015-04-01')
        self.assertEqual(admin_csv[1]['Arrival Time'], '')
        self.assertEqual(admin_csv[1]['Departure Date'], '')
        self.assertEqual(admin_csv[1]['Departure Time'], '')
        self.assertEqual(admin_csv[2]['Arrival Date'], '2015-04-01')
        self.assertEqual(admin_csv[2]['Arrival Time'], '10:00')
        self.assertEqual(admin_csv[2]['Departure Date'], '2015-04-02')
        self.assertEqual(admin_csv[2]['Departure Time'], '20:00')

    def test_person_date_of_birth_partial(self):
        """
        Test creating people with partial dates of birth.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Chief Coordinator',
                                    {'date_of_birth_year': '1990',
                                     'date_of_birth_month': 'January',
                                     'date_of_birth_day': '(day)'})
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(admin_csv[0]['Date of Birth'], '')
        admin_session.create_person('XMO 2015 Staff', 'Chief Guide',
                                    {'date_of_birth_year': '2000',
                                     'date_of_birth_month': '(month)',
                                     'date_of_birth_day': '10'})
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(admin_csv[0]['Date of Birth'], '')
        self.assertEqual(admin_csv[1]['Date of Birth'], '')
        admin_session.create_person('XMO 2015 Staff', 'Jury Chair',
                                    {'date_of_birth_year': '(year)',
                                     'date_of_birth_month': 'December',
                                     'date_of_birth_day': '10'})
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(admin_csv[0]['Date of Birth'], '')
        self.assertEqual(admin_csv[1]['Date of Birth'], '')
        self.assertEqual(admin_csv[2]['Date of Birth'], '')
        # Verify setting and then partially unsetting details.
        admin_session.select_main_form()
        admin_session.set({'date_of_birth_year': '2001',
                           'date_of_birth_month': 'February',
                           'date_of_birth_day': '20'})
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(admin_csv[0]['Date of Birth'], '')
        self.assertEqual(admin_csv[1]['Date of Birth'], '')
        self.assertEqual(admin_csv[2]['Date of Birth'], '2001-02-20')
        admin_session.select_main_form()
        admin_session.set({'date_of_birth_day': '(day)'})
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(admin_csv[0]['Date of Birth'], '')
        self.assertEqual(admin_csv[1]['Date of Birth'], '')
        self.assertEqual(admin_csv[2]['Date of Birth'], '')

    def test_person_large_text_field(self):
        """
        Test large text fields for people.

        A Roundup bug with such fields was fixed in commit
        f60c44563c3a (Sun Mar 24 21:49:17 2019 +0000).
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        large_text_1 = ''.join(str(n) for n in range(1000))
        large_text_2 = ''.join(str(n) for n in range(2000))
        large_a = '%s\n%s' % (large_text_1, large_text_2)
        large_b = '%s\n%s' % (large_text_2, large_text_1)
        admin_session.create_person('Test First Country', 'Leader',
                                    {'diet': large_a})
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(admin_csv[0]['Allergies and Dietary Requirements'],
                         large_a)
        admin_session.edit('person', '1', {'diet': large_b})
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(admin_csv[0]['Allergies and Dietary Requirements'],
                         large_b)

    def test_person_photo_scale(self):
        """
        Test scaling down photo.
        """
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(1024, 1024, 2,
                                                    '.jpg', 'JPEG')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertLessEqual(len(admin_bytes), 1572864)
        # The button should not appear any more on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNone(main_form)

    @_with_config(photo_max_size='65536')
    def test_person_photo_scale_max_size(self):
        """
        Test scaling down photo: smaller configured maximum size.
        """
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(256, 256, 2,
                                                    '.jpg', 'JPEG')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertLessEqual(len(admin_bytes), 65536)
        # The button should not appear any more on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNone(main_form)

    @_with_config(photo_max_size='65536')
    def test_person_photo_scale_png(self):
        """
        Test scaling down photo: PNG photo.
        """
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(256, 256, 2,
                                                    '.png', 'PNG')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertLessEqual(len(admin_bytes), 65536)
        # The button should not appear any more on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNone(main_form)

    @_with_config(photo_max_size='16384')
    def test_person_photo_scale_min_dimen(self):
        """
        Test scaling down photo: minimum dimension prevents making
        small enough.
        """
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(1024, 256, 2,
                                                    '.jpg', 'JPEG')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected(error='Could not make this photo '
                                            'small enough')
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertGreater(len(admin_bytes), 16384)
        # The button should still appear on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNotNone(main_form)
        # Similarly, for the other dimension.
        photo_filename, dummy = self.gen_test_image(256, 1024, 2,
                                                    '.jpg', 'JPEG')
        admin_session.edit('person', '1', {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected(error='Could not make this photo '
                                            'small enough')
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertGreater(len(admin_bytes), 16384)
        # The button should still appear on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNotNone(main_form)

    @_with_config(photo_max_size='65536', photo_min_dimen='512')
    def test_person_photo_scale_min_dimen_config(self):
        """
        Test scaling down photo: configured minimum dimension prevents
        making small enough.
        """
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(256, 256, 2,
                                                    '.jpg', 'JPEG')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected(error='Could not make this photo '
                                            'small enough')
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertGreater(len(admin_bytes), 16384)
        # The button should still appear on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNotNone(main_form)

    @_with_config(photo_max_size='65536')
    def test_person_photo_scale_grey(self):
        """
        Test scaling down photo: greyscale image.
        """
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(512, 512, 2,
                                                    '.jpg', 'JPEG', 'L')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertLessEqual(len(admin_bytes), 65536)
        # The button should not appear any more on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNone(main_form)

    @_with_config(photo_max_size='65536')
    def test_person_photo_scale_alpha(self):
        """
        Test scaling down photo: image with alpha channel.
        """
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(256, 256, 2,
                                                    '.png', 'PNG', 'RGBA')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertLessEqual(len(admin_bytes), 65536)
        # The button should not appear any more on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNone(main_form)

    @_with_config(photo_max_size='65536')
    def test_person_photo_scale_grey_alpha(self):
        """
        Test scaling down photo: greyscale image with alpha channel.
        """
        admin_session = self.get_session('admin')
        photo_filename, dummy = self.gen_test_image(256, 256, 2,
                                                    '.png', 'PNG', 'LA')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        # The status page should have the button to scale down the photo.
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertLessEqual(len(admin_bytes), 65536)
        # The button should not appear any more on the status page.
        admin_session.check_open_relative('person?@template=status')
        main_form = admin_session.get_main_form()
        self.assertIsNone(main_form)

    @_with_config(photo_max_size='65536')
    def test_person_photo_scale_errors(self):
        """
        Test errors from scale_photo action.

        Errors relating to the size of the photo are tested
        separately.
        """
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(256, 256, 2,
                                                          '.jpg', 'JPEG')
        admin_session.create_country_generic()
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'photo-1@content': photo_filename})
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        # Error trying to scale photo via GET request.
        admin_session.check_open_relative('person1?@action=scale_photo',
                                          error='Invalid request')
        # Errors applying action to bad class or without id specified
        # (requires modifying the form to exercise).
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        main_form['action'] = 'person'
        admin_session.check_submit_selected(error='No id specified to scale '
                                            'photo for')
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        main_form['action'] = 'country1'
        admin_session.check_submit_selected(error='Photos can only be scaled '
                                            'for people')
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        main_form['action'] = 'person2'
        admin_session.check_submit_selected(error='This person has no photo '
                                            'to scale')
        # The photo should not have been changed by these erroneous
        # actions.
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[0]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(admin_csv[1]['Photo URL'], '')
        # Test error with photo already small enough.
        photo_filename, photo_bytes = self.gen_test_image(64, 64, 2,
                                                          '.jpg', 'JPEG')
        admin_session.edit('person', '2', {'photo-1@content': photo_filename})
        admin_session.check_open_relative('person?@template=status')
        admin_session.select_main_form()
        main_form = admin_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        main_form['action'] = 'person2'
        admin_session.check_submit_selected(error='This photo is already '
                                            'small enough')
        # The photo should not have been changed.
        admin_csv = admin_session.get_people_csv()
        img_url_csv = admin_csv[1]['Photo URL']
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, photo_bytes)
        # Permission error (requires user to have valid form, then
        # have permissions removed, then try submitting it).
        admin_session.create_user('admin2', 'XMO 2015 Staff', 'Admin')
        admin2_session = self.get_session('admin2')
        admin2_session.check_open_relative('person?@template=status')
        admin2_session.select_main_form()
        main_form = admin2_session.get_main_form()
        submit = main_form.find('input', type='submit')
        self.assertEqual(submit['value'], 'Scale down')
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to scale the photo '
                                             'for',
                                             status=403)

    @_with_config(require_passport_number='Yes', require_nationality='Yes',
                  consent_ui='Yes')
    def test_person_edit_selfreg(self):
        """
        Test editing people with self-registration accounts.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
        photo2_filename, photo2_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                            'JPEG')
        cf_filename, cf_bytes = self.gen_test_pdf()
        cf2_filename, cf2_bytes = self.gen_test_pdf()
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Leader',
            {'passport_number': '0',
             'nationality': '0',
             'event_photos_consent': 'no',
             'diet_consent': 'no'})
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'passport_number': '0',
             'nationality': '0',
             'event_photos_consent': 'no',
             'diet_consent': 'no'})
        admin_session.create_user('selfreg_1', 'Test First Country',
                                  'User,SelfRegister',
                                  {'person': '1'})
        admin_session.create_user('selfreg_2', 'XMO 2015 Staff',
                                  'User,SelfRegister',
                                  {'person': '2'})
        selfreg_1_session = self.get_session('selfreg_1')
        selfreg_2_session = self.get_session('selfreg_2')
        # Self-registering users can edit most of their data.
        selfreg_1_session.edit('person', '1',
                               {'given_name': 'Edited given',
                                'family_name': 'Edited family',
                                'passport_given_name': 'Passport given',
                                'passport_family_name': 'Passport family',
                                'gender': 'Male',
                                'date_of_birth_year': '1999',
                                'date_of_birth_month': 'December',
                                'date_of_birth_day': '31',
                                'language_1': 'French',
                                'tshirt': 'M',
                                'diet': 'Vegan',
                                'arrival_place': 'Example Airport',
                                'arrival_date': '2 April 2015',
                                'arrival_time_hour': '12',
                                'arrival_time_minute': '34',
                                'arrival_flight': 'ABC123',
                                'departure_place': 'Example Airport',
                                'departure_date': '3 April 2015',
                                'departure_time_hour': '19',
                                'departure_time_minute': '59',
                                'departure_flight': 'DEF987',
                                'room_type': 'Single room',
                                'room_share_with': 'Someone',
                                'generic_url':
                                'https://www.example.invalid/people/person1/',
                                'passport_number': '123',
                                'nationality': 'Matholympian',
                                'photo-1@content': photo_filename,
                                'consent_form-1@content': cf_filename,
                                'event_photos_consent': 'yes',
                                'diet_consent': 'yes',
                                'photo_consent':
                                'Yes, for website and name badge'})
        selfreg_2_session.edit('person', '2',
                               {'given_name': 'Edited given 2',
                                'family_name': 'Edited family 2',
                                'passport_given_name': 'Passport given 2',
                                'passport_family_name': 'Passport family 2',
                                'gender': 'Non-binary',
                                'date_of_birth_year': '1998',
                                'date_of_birth_month': 'December',
                                'date_of_birth_day': '31',
                                'language_1': 'French',
                                'language_2': 'English',
                                'tshirt': 'M',
                                'diet': 'Vegetarian',
                                'arrival_place': 'Example Airport',
                                'arrival_date': '2 April 2015',
                                'arrival_time_hour': '13',
                                'arrival_time_minute': '45',
                                'arrival_flight': 'ABC124',
                                'departure_place': 'Example Airport',
                                'departure_date': '3 April 2015',
                                'departure_time_hour': '18',
                                'departure_time_minute': '48',
                                'departure_flight': 'DEF986',
                                'room_type': 'Single room',
                                'room_share_with': 'Someone else',
                                'generic_url':
                                'https://www.example.invalid/people/person9/',
                                'passport_number': '12345',
                                'nationality': 'Matholympian also',
                                'phone_number': '9876543210',
                                'photo-1@content': photo2_filename,
                                'consent_form-1@content': cf2_filename,
                                'event_photos_consent': 'yes',
                                'diet_consent': 'yes',
                                'photo_consent':
                                'Yes, for website and name badge'})
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        img2_url_csv = self.instance.url + 'photo2/photo.jpg'
        cf_url_csv = self.instance.url + 'consent_form1/consent-form.pdf'
        cf2_url_csv = self.instance.url + 'consent_form2/consent-form.pdf'
        expected_leader = {'XMO Number': '2', 'Country Number': '3',
                           'Person Number': '1',
                           'Annual URL': self.instance.url + 'person1',
                           'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Primary Role': 'Leader',
                           'Other Roles': '', 'Guide For': '',
                           'Contestant Code': '', 'Contestant Age': '',
                           'Given Name': 'Edited given',
                           'Family Name': 'Edited family',
                           'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                           'P6': '', 'Total': '', 'Award': '',
                           'Extra Awards': '', 'Photo URL': img_url_csv,
                           'Generic Number': '1'}
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Person Number': '2',
                          'Annual URL': self.instance.url + 'person2',
                          'Country Name': 'XMO 2015 Staff',
                          'Country Code': 'ZZA', 'Primary Role': 'Guide',
                          'Other Roles': '',
                          'Guide For': '',
                          'Contestant Code': '', 'Contestant Age': '',
                          'Given Name': 'Edited given 2',
                          'Family Name': 'Edited family 2',
                          'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                          'P6': '', 'Total': '', 'Award': '',
                          'Extra Awards': '', 'Photo URL': img2_url_csv,
                          'Generic Number': '9'}
        expected_leader_admin = expected_leader.copy()
        expected_staff_admin = expected_staff.copy()
        expected_leader_admin.update(
            {'Gender': 'Male', 'Date of Birth': '1999-12-31',
             'Languages': 'French',
             'Allergies and Dietary Requirements': 'Vegan',
             'T-Shirt Size': 'M', 'Arrival Place': 'Example Airport',
             'Arrival Date': '2015-04-02', 'Arrival Time': '12:34',
             'Arrival Flight': 'ABC123', 'Departure Place': 'Example Airport',
             'Departure Date': '2015-04-03', 'Departure Time': '19:59',
             'Departure Flight': 'DEF987', 'Room Type': 'Single room',
             'Share Room With': 'Someone', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': img_url_csv,
             'Badge Background': 'generic', 'Badge Outer Colour': 'd22027',
             'Badge Inner Colour': 'eb9984', 'Badge Text Colour': '000000',
             'Consent Form URL': cf_url_csv,
             'Passport or Identity Card Number': '123',
             'Nationality': 'Matholympian',
             'Passport Given Name': 'Passport given',
             'Passport Family Name': 'Passport family',
             'Event Photos Consent': 'Yes', 'Remote Participant': 'No',
             'Basic Data Missing': 'No'})
        expected_staff_admin.update(
            {'Gender': 'Non-binary', 'Date of Birth': '1998-12-31',
             'Languages': 'French,English',
             'Allergies and Dietary Requirements': 'Vegetarian',
             'T-Shirt Size': 'M', 'Arrival Place': 'Example Airport',
             'Arrival Date': '2015-04-02', 'Arrival Time': '13:45',
             'Arrival Flight': 'ABC124', 'Departure Place': 'Example Airport',
             'Departure Date': '2015-04-03', 'Departure Time': '18:48',
             'Departure Flight': 'DEF986', 'Room Type': 'Single room',
             'Share Room With': 'Someone else', 'Room Number': '',
             'Phone Number': '9876543210', 'Badge Photo URL': img2_url_csv,
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': cf2_url_csv,
             'Passport or Identity Card Number': '12345',
             'Nationality': 'Matholympian also',
             'Passport Given Name': 'Passport given 2',
             'Passport Family Name': 'Passport family 2',
             'Event Photos Consent': 'Yes', 'Remote Participant': 'No',
             'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        selfreg_1_csv = selfreg_1_session.get_people_csv()
        selfreg_2_csv = selfreg_2_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_leader, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_leader_admin, expected_staff_admin])
        self.assertEqual(reg_csv,
                         [expected_leader, expected_staff])
        self.assertEqual(selfreg_1_csv,
                         [expected_leader, expected_staff])
        self.assertEqual(selfreg_2_csv,
                         [expected_leader, expected_staff])
        # Check the images from the URLs in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        reg_bytes = reg_session.get_bytes(img_url_csv)
        selfreg_1_bytes = selfreg_1_session.get_bytes(img_url_csv)
        selfreg_2_bytes = selfreg_2_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)
        self.assertEqual(reg_bytes, photo_bytes)
        self.assertEqual(selfreg_1_bytes, photo_bytes)
        self.assertEqual(selfreg_2_bytes, photo_bytes)
        anon_bytes = session.get_bytes(img2_url_csv)
        admin_bytes = admin_session.get_bytes(img2_url_csv)
        reg_bytes = reg_session.get_bytes(img2_url_csv)
        selfreg_1_bytes = selfreg_1_session.get_bytes(img2_url_csv)
        selfreg_2_bytes = selfreg_2_session.get_bytes(img2_url_csv)
        self.assertEqual(anon_bytes, photo2_bytes)
        self.assertEqual(admin_bytes, photo2_bytes)
        self.assertEqual(reg_bytes, photo2_bytes)
        self.assertEqual(selfreg_1_bytes, photo2_bytes)
        self.assertEqual(selfreg_2_bytes, photo2_bytes)
        # Check the consent forms from the URL in the .csv file.
        admin_bytes = admin_session.get_bytes(cf_url_csv)
        selfreg_1_bytes = selfreg_1_session.get_bytes(cf_url_csv)
        self.assertEqual(admin_bytes, cf_bytes)
        self.assertEqual(selfreg_1_bytes, cf_bytes)
        # The form is not accessible by the other self-registration user.
        selfreg_2_session.check_open(cf_url_csv,
                                     error='You are not allowed to view this '
                                     'file',
                                     status=403)
        admin_bytes = admin_session.get_bytes(cf2_url_csv)
        selfreg_2_bytes = selfreg_2_session.get_bytes(cf2_url_csv)
        self.assertEqual(admin_bytes, cf2_bytes)
        self.assertEqual(selfreg_2_bytes, cf2_bytes)
        # The form is not accessible by the other self-registration user.
        selfreg_1_session.check_open(cf2_url_csv,
                                     error='You are not allowed to view this '
                                     'file',
                                     status=403)
        # Another self-registration user from the same country cannot
        # access the form either.
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'passport_number': '0',
             'nationality': '0',
             'event_photos_consent': 'no',
             'diet_consent': 'no'})
        admin_session.create_user('selfreg_3', 'XMO 2015 Staff',
                                  'User,SelfRegister',
                                  {'person': '3'})
        selfreg_3_session = self.get_session('selfreg_3')
        selfreg_3_session.check_open(cf2_url_csv,
                                     error='You are not allowed to view this '
                                     'file',
                                     status=403)
        # Changing consent has that effect for photos.
        selfreg_2_session.check_open(self.instance.url)
        selfreg_2_session.edit('person', '2',
                               {'photo_consent': 'Yes, for name badge only'})
        selfreg_2_bytes = selfreg_2_session.get_bytes(img2_url_csv)
        self.assertEqual(selfreg_2_bytes, photo2_bytes)
        selfreg_3_session.check_open(img2_url_csv,
                                     error='You are not allowed to view this '
                                     'file',
                                     status=403)

    @_with_config(require_passport_number='Yes', require_nationality='Yes',
                  require_diet='Yes', consent_ui='Yes')
    def test_person_incomplete(self):
        """
        Test people with incomplete registrations.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'@required': '',
             'incomplete': 'yes',
             'gender': None,
             'date_of_birth_year': None,
             'date_of_birth_month': None,
             'date_of_birth_day': None,
             'language_1': None,
             'tshirt': None})
        admin_session.create_person(
            'XMO 2015 Staff', 'Guide',
            {'@required': '',
             'incomplete': 'yes',
             'gender': None,
             'date_of_birth_year': None,
             'date_of_birth_month': None,
             'date_of_birth_day': None,
             'language_1': None,
             'tshirt': None})
        admin_session.create_user('selfreg_1', 'Test First Country',
                                  'User,SelfRegister',
                                  {'person': '1'})
        admin_session.create_user('selfreg_2', 'XMO 2015 Staff',
                                  'User,SelfRegister',
                                  {'person': '2'})
        selfreg_1_session = self.get_session('selfreg_1')
        selfreg_2_session = self.get_session('selfreg_2')
        # Incomplete registrations do not have defaults of diet or
        # room type.
        expected_cont = {'XMO Number': '2', 'Country Number': '3',
                         'Person Number': '1',
                         'Annual URL': self.instance.url + 'person1',
                         'Country Name': 'Test First Country',
                         'Country Code': 'ABC', 'Primary Role': 'Contestant 1',
                         'Other Roles': '', 'Guide For': '',
                         'Contestant Code': 'ABC1', 'Contestant Age': '',
                         'Given Name': 'Given 1', 'Family Name': 'Family 1',
                         'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                         'P6': '', 'Total': '0', 'Award': '',
                         'Extra Awards': '', 'Photo URL': '',
                         'Generic Number': ''}
        expected_staff = {'XMO Number': '2', 'Country Number': '1',
                          'Person Number': '2',
                          'Annual URL': self.instance.url + 'person2',
                          'Country Name': 'XMO 2015 Staff',
                          'Country Code': 'ZZA', 'Primary Role': 'Guide',
                          'Other Roles': '', 'Guide For': '',
                          'Contestant Code': '', 'Contestant Age': '',
                          'Given Name': 'Given 2', 'Family Name': 'Family 2',
                          'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                          'P6': '', 'Total': '', 'Award': '',
                          'Extra Awards': '', 'Photo URL': '',
                          'Generic Number': ''}
        expected_cont_admin = expected_cont.copy()
        expected_staff_admin = expected_staff.copy()
        expected_cont_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '7ab558',
             'Badge Inner Colour': 'c9deb0', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given 1',
             'Passport Family Name': 'Family 1',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        expected_staff_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given 2',
             'Passport Family Name': 'Family 2',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        selfreg_1_csv = selfreg_1_session.get_people_csv()
        selfreg_2_csv = selfreg_2_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_cont_admin, expected_staff_admin])
        self.assertEqual(reg_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_1_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_2_csv,
                         [expected_cont, expected_staff])
        # Registration and self-registration users cannot edit those
        # people without completing the incomplete data.
        reg_session.edit('person', '1',
                         {'@required': '',
                          'arrival_place': 'Example Airport'},
                         error='No gender specified')
        selfreg_1_session.edit('person', '1',
                               {'@required': '',
                                'arrival_place': 'Example Airport'},
                               error='No gender specified')
        selfreg_2_session.edit('person', '2',
                               {'@required': '',
                                'arrival_place': 'Example Airport'},
                               error='No gender specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        selfreg_1_csv = selfreg_1_session.get_people_csv()
        selfreg_2_csv = selfreg_2_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_cont_admin, expected_staff_admin])
        self.assertEqual(reg_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_1_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_2_csv,
                         [expected_cont, expected_staff])
        # Administrative users can edit those people without
        # completing the incomplete data.
        admin_session.edit('person', '1',
                           {'arrival_place': 'Example Airport'})
        expected_cont_admin['Arrival Place'] = 'Example Airport'
        admin_session.edit('person', '2',
                           {'departure_place': 'Example Airport'})
        expected_staff_admin['Departure Place'] = 'Example Airport'
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        selfreg_1_csv = selfreg_1_session.get_people_csv()
        selfreg_2_csv = selfreg_2_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_cont_admin, expected_staff_admin])
        self.assertEqual(reg_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_1_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_2_csv,
                         [expected_cont, expected_staff])
        # Registration and self-registration users can edit those
        # people if they do complete the incomplete data.
        reg_session.edit('person', '1',
                         {'gender': 'Female',
                          'date_of_birth_year': '2000',
                          'date_of_birth_month': 'November',
                          'date_of_birth_day': '3',
                          'language_1': 'English',
                          'tshirt': 'S',
                          'diet': 'Food',
                          'passport_number': '987',
                          'nationality': 'Matholympian',
                          'event_photos_consent': 'no',
                          'diet_consent': 'yes',
                          'photo_consent': 'Yes, for website and name badge'})
        expected_cont['Contestant Age'] = '14'
        expected_cont_admin.update(
            {'Contestant Age': '14', 'Gender': 'Female',
             'Date of Birth': '2000-11-03', 'Languages': 'English',
             'Allergies and Dietary Requirements': 'Food',
             'T-Shirt Size': 'S', 'Room Type': 'Shared room',
             'Passport or Identity Card Number': '987',
             'Nationality': 'Matholympian',
             'Event Photos Consent': 'No', 'Remote Participant': 'No',
             'Basic Data Missing': 'No'})
        selfreg_2_session.edit('person', '2',
                               {'gender': 'Male',
                                'date_of_birth_year': '2000',
                                'date_of_birth_month': 'January',
                                'date_of_birth_day': '31',
                                'language_1': 'French',
                                'tshirt': 'M',
                                'diet': 'Less food',
                                'passport_number': '9876',
                                'nationality': 'Matholympianish',
                                'event_photos_consent': 'yes',
                                'diet_consent': 'yes',
                                'photo_consent':
                                'Yes, for website and name badge'})
        expected_staff_admin.update(
            {'Gender': 'Male', 'Date of Birth': '2000-01-31',
             'Languages': 'French',
             'Allergies and Dietary Requirements': 'Less food',
             'T-Shirt Size': 'M', 'Room Type': 'Shared room',
             'Passport or Identity Card Number': '9876',
             'Nationality': 'Matholympianish',
             'Event Photos Consent': 'Yes', 'Remote Participant': 'No',
             'Basic Data Missing': 'No'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        selfreg_1_csv = selfreg_1_session.get_people_csv()
        selfreg_2_csv = selfreg_2_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_cont_admin, expected_staff_admin])
        self.assertEqual(reg_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_1_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_2_csv,
                         [expected_cont, expected_staff])
        # Creation with certain details missing is still an error.
        admin_session.create('person',
                             {'@required': '',
                              'incomplete': 'yes',
                              'primary_role': 'Leader',
                              'given_name': 'Given',
                              'family_name': 'Family',
                              'gender': 'Female',
                              'language_1': 'English',
                              'tshirt': 'S'},
                             error='No country specified')
        admin_session.create_person('Test First Country', 'Contestant 2',
                                    {'@required': '',
                                     'incomplete': 'yes',
                                     'given_name': None},
                                    error='No given name specified')
        admin_session.create_person('Test First Country', 'Contestant 2',
                                    {'@required': '',
                                     'incomplete': 'yes',
                                     'family_name': None},
                                    error='No family name specified')
        admin_session.create('person',
                             {'@required': '',
                              'incomplete': 'yes',
                              'country': 'Test First Country',
                              'given_name': 'Given',
                              'family_name': 'Family',
                              'gender': 'Female',
                              'language_1': 'English',
                              'tshirt': 'S'},
                             error='No primary role specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        selfreg_1_csv = selfreg_1_session.get_people_csv()
        selfreg_2_csv = selfreg_2_session.get_people_csv()
        self.assertEqual(anon_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(admin_csv,
                         [expected_cont_admin, expected_staff_admin])
        self.assertEqual(reg_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_1_csv,
                         [expected_cont, expected_staff])
        self.assertEqual(selfreg_2_csv,
                         [expected_cont, expected_staff])

    @_with_config(require_diet='Yes', consent_ui='Yes', virtual_event='Yes',
                  require_passport_number='Yes', require_nationality='Yes')
    def test_person_virtual(self):
        """
        Test person creation and editing for a virtual event.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Leader',
                                    {'event_photos_consent': 'yes'})
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'event_photos_consent': 'yes'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)
        self.assertEqual(
            admin_csv[0]['Allergies and Dietary Requirements'], '')
        self.assertEqual(
            admin_csv[1]['Allergies and Dietary Requirements'], '')
        self.assertEqual(admin_csv[0]['Room Type'], '')
        self.assertEqual(admin_csv[1]['Room Type'], '')
        self.assertEqual(admin_csv[0]['Passport or Identity Card Number'], '')
        self.assertEqual(admin_csv[1]['Passport or Identity Card Number'], '')
        self.assertEqual(admin_csv[0]['Nationality'], '')
        self.assertEqual(admin_csv[1]['Nationality'], '')
        admin_session.edit('person', '1', {'event_photos_consent': 'no'})
        reg_session.edit('person', '2', {'primary_role': 'Contestant 2'})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 2)
        self.assertEqual(len(admin_csv), 2)
        self.assertEqual(len(reg_csv), 2)
        self.assertEqual(
            admin_csv[0]['Allergies and Dietary Requirements'], '')
        self.assertEqual(
            admin_csv[1]['Allergies and Dietary Requirements'], '')
        self.assertEqual(admin_csv[0]['Room Type'], '')
        self.assertEqual(admin_csv[1]['Room Type'], '')
        self.assertEqual(admin_csv[0]['Passport or Identity Card Number'], '')
        self.assertEqual(admin_csv[1]['Passport or Identity Card Number'], '')
        self.assertEqual(admin_csv[0]['Nationality'], '')
        self.assertEqual(admin_csv[1]['Nationality'], '')

    def test_person_score(self):
        """
        Test entering scores and CSV file of scores.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_scoring_user()
        score_session = self.get_session('scoring')
        admin_session.create_country_generic()
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_session.create_person('Test First Country', 'Contestant 2')
        admin_session.create_person('Test First Country', 'Contestant 4')
        admin_session.create_country('DEF', 'Test Second Country')
        admin_session.create_person('Test Second Country', 'Contestant 2')
        admin_session.create_person('Test Second Country', 'Contestant 3')
        admin_session.create_person('Test Second Country', 'Contestant 4')
        admin_session.create_person('Test Second Country', 'Leader')
        admin_session.edit('event', '1', {'registration_enabled': 'no'})
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        score_csv = score_session.get_scores_csv()
        score_csv_p = score_session.get_people_csv_scores()
        self.assertEqual(len(admin_csv), 6)
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(score_csv, admin_csv)
        self.assertEqual(score_csv_p, admin_csv)
        # Enter some scores and check the results.
        admin_session.enter_scores('Test First Country', 'ABC', '2',
                                   ['3', '4', None, '0'])
        score_session.enter_scores('Test First Country', 'ABC', '4',
                                   ['7', '', None, '5'])
        score_session.enter_scores('Test Second Country', 'DEF', '1',
                                   [None, '5', '1', '2'])
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        score_csv = score_session.get_scores_csv()
        score_csv_p = score_session.get_people_csv_scores()
        self.assertEqual(admin_csv,
                         [{'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC1',
                           'Given Name': 'Given 1', 'Family Name': 'Family 1',
                           'P1': '', 'P2': '3', 'P3': '',
                           'P4': '7', 'P5': '', 'P6': '',
                           'Total': '10', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC2',
                           'Given Name': 'Given 2', 'Family Name': 'Family 2',
                           'P1': '', 'P2': '4', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '4', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC4',
                           'Given Name': 'Given 3', 'Family Name': 'Family 3',
                           'P1': '', 'P2': '0', 'P3': '',
                           'P4': '5', 'P5': '', 'P6': '',
                           'Total': '5', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF2',
                           'Given Name': 'Given 4', 'Family Name': 'Family 4',
                           'P1': '5', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '5', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF3',
                           'Given Name': 'Given 5', 'Family Name': 'Family 5',
                           'P1': '1', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '1', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF4',
                           'Given Name': 'Given 6', 'Family Name': 'Family 6',
                           'P1': '2', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '2', 'Award': '', 'Extra Awards': ''}])
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(score_csv, admin_csv)
        self.assertEqual(score_csv_p, admin_csv)
        # Test a null edit of scores.
        admin_session.enter_scores('Test Second Country', 'DEF', '1',
                                   [])
        score_session.enter_scores('Test First Country', 'ABC', '2',
                                   [])
        admin_session.enter_scores('Test First Country', 'ABC', '4',
                                   [])
        score_session.enter_scores('Test First Country', 'ABC', '6',
                                   [])
        admin_csv_2 = admin_session.get_scores_csv()
        admin_csv_p_2 = admin_session.get_people_csv_scores()
        anon_csv_2 = session.get_scores_csv()
        anon_csv_p_2 = session.get_people_csv_scores()
        score_csv_2 = score_session.get_scores_csv()
        score_csv_p_2 = score_session.get_people_csv_scores()
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(admin_csv_p_2, admin_csv)
        self.assertEqual(anon_csv_2, admin_csv)
        self.assertEqual(anon_csv_p_2, admin_csv)
        self.assertEqual(score_csv_2, admin_csv)
        self.assertEqual(score_csv_p_2, admin_csv)
        # Test an edit that changes some scores.
        admin_session.enter_scores('Test First Country', 'ABC', '2',
                                   ['', '5', None, '0'])
        score_session.enter_scores('Test First Country', 'ABC', '4',
                                   ['', '6', None, '5'])
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        score_csv = score_session.get_scores_csv()
        score_csv_p = score_session.get_people_csv_scores()
        self.assertEqual(admin_csv,
                         [{'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC1',
                           'Given Name': 'Given 1', 'Family Name': 'Family 1',
                           'P1': '', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '0', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC2',
                           'Given Name': 'Given 2', 'Family Name': 'Family 2',
                           'P1': '', 'P2': '5', 'P3': '',
                           'P4': '6', 'P5': '', 'P6': '',
                           'Total': '11', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC4',
                           'Given Name': 'Given 3', 'Family Name': 'Family 3',
                           'P1': '', 'P2': '0', 'P3': '',
                           'P4': '5', 'P5': '', 'P6': '',
                           'Total': '5', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF2',
                           'Given Name': 'Given 4', 'Family Name': 'Family 4',
                           'P1': '5', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '5', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF3',
                           'Given Name': 'Given 5', 'Family Name': 'Family 5',
                           'P1': '1', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '1', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF4',
                           'Given Name': 'Given 6', 'Family Name': 'Family 6',
                           'P1': '2', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '2', 'Award': '', 'Extra Awards': ''}])
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(score_csv, admin_csv)
        self.assertEqual(score_csv_p, admin_csv)

    @_with_config(virtual_event='Yes')
    def test_person_score_virtual(self):
        """
        Test entering scores and CSV file of scores, virtual event.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_scoring_user()
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_session.create_person('Test First Country', 'Contestant 2')
        admin_session.create_person('Test First Country', 'Contestant 4')
        admin_session.create_country('DEF', 'Test Second Country')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person('Test Second Country', 'Contestant 2')
        admin_session.create_person('Test Second Country', 'Contestant 3')
        admin_session.create_person('Test Second Country', 'Contestant 4')
        admin_session.create_person('Test Second Country', 'Leader')
        admin_session.edit('event', '1', {'registration_enabled': 'no',
                                          'self_scoring_enabled': 'yes'})
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        reg_csv = reg_session.get_scores_csv()
        reg_csv_p = reg_session.get_people_csv_scores()
        self.assertEqual(len(admin_csv), 6)
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(reg_csv, admin_csv)
        self.assertEqual(reg_csv_p, admin_csv)
        # Enter some scores and check the results.
        reg_session.enter_scores('Test First Country', 'ABC', '2',
                                 ['3', '4', None, '0'])
        reg_session.enter_scores('Test First Country', 'ABC', '4',
                                 ['7', '', None, '5'])
        reg2_session.enter_scores('Test Second Country', 'DEF', '1',
                                  [None, '5', '1', '2'])
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        reg_csv = reg_session.get_scores_csv()
        reg_csv_p = reg_session.get_people_csv_scores()
        self.assertEqual(admin_csv,
                         [{'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC1',
                           'Given Name': 'Given 1', 'Family Name': 'Family 1',
                           'P1': '', 'P2': '3', 'P3': '',
                           'P4': '7', 'P5': '', 'P6': '',
                           'Total': '10', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC2',
                           'Given Name': 'Given 2', 'Family Name': 'Family 2',
                           'P1': '', 'P2': '4', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '4', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC4',
                           'Given Name': 'Given 3', 'Family Name': 'Family 3',
                           'P1': '', 'P2': '0', 'P3': '',
                           'P4': '5', 'P5': '', 'P6': '',
                           'Total': '5', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF2',
                           'Given Name': 'Given 4', 'Family Name': 'Family 4',
                           'P1': '5', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '5', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF3',
                           'Given Name': 'Given 5', 'Family Name': 'Family 5',
                           'P1': '1', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '1', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF4',
                           'Given Name': 'Given 6', 'Family Name': 'Family 6',
                           'P1': '2', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '2', 'Award': '', 'Extra Awards': ''}])
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(reg_csv, admin_csv)
        self.assertEqual(reg_csv_p, admin_csv)
        # Test a null edit of scores.
        reg2_session.enter_scores('Test Second Country', 'DEF', '1',
                                  [])
        reg_session.enter_scores('Test First Country', 'ABC', '2',
                                 [])
        reg_session.enter_scores('Test First Country', 'ABC', '4',
                                 [])
        reg_session.enter_scores('Test First Country', 'ABC', '6',
                                 [])
        admin_csv_2 = admin_session.get_scores_csv()
        admin_csv_p_2 = admin_session.get_people_csv_scores()
        anon_csv_2 = session.get_scores_csv()
        anon_csv_p_2 = session.get_people_csv_scores()
        reg_csv_2 = reg_session.get_scores_csv()
        reg_csv_p_2 = reg_session.get_people_csv_scores()
        self.assertEqual(admin_csv_2, admin_csv)
        self.assertEqual(admin_csv_p_2, admin_csv)
        self.assertEqual(anon_csv_2, admin_csv)
        self.assertEqual(anon_csv_p_2, admin_csv)
        self.assertEqual(reg_csv_2, admin_csv)
        self.assertEqual(reg_csv_p_2, admin_csv)
        # Test an edit that changes some scores.
        reg_session.enter_scores('Test First Country', 'ABC', '2',
                                 ['', '5', None, '0'])
        reg_session.enter_scores('Test First Country', 'ABC', '4',
                                 ['', '6', None, '5'])
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        reg_csv = reg_session.get_scores_csv()
        reg_csv_p = reg_session.get_people_csv_scores()
        self.assertEqual(admin_csv,
                         [{'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC1',
                           'Given Name': 'Given 1', 'Family Name': 'Family 1',
                           'P1': '', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '0', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC2',
                           'Given Name': 'Given 2', 'Family Name': 'Family 2',
                           'P1': '', 'P2': '5', 'P3': '',
                           'P4': '6', 'P5': '', 'P6': '',
                           'Total': '11', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC4',
                           'Given Name': 'Given 3', 'Family Name': 'Family 3',
                           'P1': '', 'P2': '0', 'P3': '',
                           'P4': '5', 'P5': '', 'P6': '',
                           'Total': '5', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF2',
                           'Given Name': 'Given 4', 'Family Name': 'Family 4',
                           'P1': '5', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '5', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF3',
                           'Given Name': 'Given 5', 'Family Name': 'Family 5',
                           'P1': '1', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '1', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF4',
                           'Given Name': 'Given 6', 'Family Name': 'Family 6',
                           'P1': '2', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '2', 'Award': '', 'Extra Awards': ''}])
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(reg_csv, admin_csv)
        self.assertEqual(reg_csv_p, admin_csv)

    def test_person_score_errors(self):
        """
        Test errors entering scores.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_scoring_user()
        score_session = self.get_session('scoring')
        admin_session.create_country_generic()
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_session.edit('event', '1', {'registration_enabled': 'no'})
        # Error using score action via GET request.
        admin_session.check_open_relative('person?@action=score',
                                          error='Invalid request')
        score_session.check_open_relative('person?@action=score',
                                          error='Invalid request')
        # Error entering scores after medal boundaries are set.
        admin_session.enter_scores('Test First Country', 'ABC', '1', ['0'])
        score_session.enter_scores('Test First Country', 'ABC', '2', ['0'])
        admin_session.enter_scores('Test First Country', 'ABC', '3', ['0'])
        score_session.enter_scores('Test First Country', 'ABC', '4', ['0'])
        admin_session.enter_scores('Test First Country', 'ABC', '5', ['0'])
        score_session.enter_scores('Test First Country', 'ABC', '6', ['0'])
        admin_session.edit('event', '1',
                           {'gold': '40', 'silver': '30', 'bronze': '20'})
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'ABC1': '0'})
        admin_session.check_submit_selected(error='Scores cannot be entered '
                                            'after medal boundaries are set',
                                            status=403)
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '3'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'ABC1': '1'})
        score_session.check_submit_selected(error='Scores cannot be entered '
                                            'after medal boundaries are set',
                                            status=403)
        # Error entering scores with registration enabled.
        admin_session.edit('event', '1',
                           {'registration_enabled': 'yes',
                            'gold': '', 'silver': '', 'bronze': ''})
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'ABC1': '0'})
        admin_session.check_submit_selected(error='Registration must be '
                                            'disabled before scores are '
                                            'entered',
                                            status=403)
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '2'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'ABC1': '1'})
        score_session.check_submit_selected(error='Registration must be '
                                            'disabled before scores are '
                                            'entered',
                                            status=403)
        admin_session.edit('event', '1', {'registration_enabled': 'no'})
        # Errors applying action to bad class or with id specified
        # (requires modifying the form to exercise).
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'ABC1': '7'})
        form = admin_session.get_main_form()
        form['action'] = 'country'
        admin_session.set({'@template': 'index'})
        admin_session.check_submit_selected(error='Scores can only be entered '
                                            'for people')
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '1'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'ABC1': '7'})
        form = score_session.get_main_form()
        form['action'] = 'country'
        score_session.set({'@template': 'index'})
        score_session.check_submit_selected(error='Scores can only be entered '
                                            'for people')
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'ABC1': '7'})
        form = admin_session.get_main_form()
        form['action'] = 'person1'
        admin_session.set({'@template': 'item'})
        admin_session.check_submit_selected(error='Node id specified when '
                                            'entering scores')
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '1'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'ABC1': '7'})
        form = score_session.get_main_form()
        form['action'] = 'person1'
        score_session.set({'@template': 'item'})
        score_session.check_submit_selected(error='Node id specified when '
                                            'entering scores')
        # Invalid country specified.
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'country': '1', 'ABC1': '7'})
        admin_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '1'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'country': '1', 'ABC1': '7'})
        score_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        # Missing country.
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'ABC1': '7'})
        form = admin_session.get_main_form()
        country_input = form.find('input', attrs={'name': 'country'})
        country_input.extract()
        admin_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '1'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'ABC1': '7'})
        form = score_session.get_main_form()
        country_input = form.find('input', attrs={'name': 'country'})
        country_input.extract()
        score_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        # Invalid problem specified.
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'problem': '-1', 'ABC1': '7'})
        admin_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '1'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'problem': '0', 'ABC1': '7'})
        score_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'problem': '7', 'ABC1': '7'})
        admin_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        # Missing problem.
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'ABC1': '7'})
        form = admin_session.get_main_form()
        problem_input = form.find('input', attrs={'name': 'problem'})
        problem_input.extract()
        admin_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '1'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'ABC1': '7'})
        form = score_session.get_main_form()
        problem_input = form.find('input', attrs={'name': 'problem'})
        problem_input.extract()
        score_session.check_submit_selected(error='Country or problem invalid '
                                            'or not specified')
        # Missing score.
        admin_session.check_open_relative('person?@template=scoreselect')
        admin_session.select_main_form()
        admin_session.set({'country': 'Test First Country', 'problem': '1'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.set({'ABC1': '7'})
        form = admin_session.get_main_form()
        abc1_input = form.find('input', attrs={'name': 'ABC1'})
        abc1_input.extract()
        admin_session.check_submit_selected(error='No score specified for '
                                            'ABC1')
        score_session.check_open_relative('person?@template=scoreselect')
        score_session.select_main_form()
        score_session.set({'country': 'Test First Country', 'problem': '1'})
        score_session.check_submit_selected()
        score_session.select_main_form()
        score_session.set({'ABC1': '7'})
        form = score_session.get_main_form()
        abc1_input = form.find('input', attrs={'name': 'ABC1'})
        abc1_input.extract()
        score_session.check_submit_selected(error='No score specified for '
                                            'ABC1')
        # Invalid score.
        admin_session.enter_scores('Test First Country', 'ABC', '1', ['-1'],
                                   error='Invalid score specified for ABC1')
        admin_session.enter_scores('Test First Country', 'ABC', '1', ['8'],
                                   error='Invalid score specified for ABC1')
        # All these failed edits should not have changed the all-0
        # scores entered earlier.
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        score_csv = score_session.get_scores_csv()
        score_csv_p = score_session.get_people_csv_scores()
        self.assertEqual(admin_csv,
                         [{'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC1',
                           'Given Name': 'Given 1', 'Family Name': 'Family 1',
                           'P1': '0', 'P2': '0', 'P3': '0',
                           'P4': '0', 'P5': '0', 'P6': '0',
                           'Total': '0', 'Award': '', 'Extra Awards': ''}])
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(score_csv, admin_csv)
        self.assertEqual(score_csv_p, admin_csv)

    @_with_config(virtual_event='Yes')
    def test_person_score_errors_virtual(self):
        """
        Test errors entering scores, virtual event.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_scoring_user()
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_session.create_country('DEF', 'Test Second Country')
        reg2_session = self.get_session('DEF_reg')
        admin_session.create_person('Test Second Country', 'Contestant 1')
        admin_session.edit('event', '1', {'registration_enabled': 'no'})
        # Error entering scores when self-scoring not enabled.
        reg_session.check_open_relative('person?@template=scoreselect')
        reg_session.select_main_form()
        reg_session.set({'country': 'Test First Country', 'problem': '1'})
        reg_session.check_submit_selected()
        reg_session.select_main_form()
        reg_session.set({'ABC1': '0'})
        reg_session.check_submit_selected(error='Entering scores is currently '
                                          'disabled',
                                          status=403)
        # Error entering scores for another country.
        admin_session.edit('event', '1', {'self_scoring_enabled': 'yes'})
        reg_session.check_open_relative('person?@template=scoreenter'
                                        '&country=4&problem=1')
        reg_session.select_main_form()
        reg_session.set({'DEF1': '0'})
        reg_session.check_submit_selected(error='You do not have permission '
                                          'to enter scores for this country',
                                          status=403)
        reg2_session.check_open_relative('person?@template=scoreenter'
                                         '&country=3&problem=1')
        reg2_session.select_main_form()
        reg2_session.set({'ABC1': '0'})
        reg2_session.check_submit_selected(error='You do not have permission '
                                           'to enter scores for this country',
                                           status=403)
        # All these failed edits should not have changed the empty
        # scores.
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        reg_csv = reg_session.get_scores_csv()
        reg_csv_p = reg_session.get_people_csv_scores()
        self.assertEqual(admin_csv,
                         [{'Country Name': 'Test First Country',
                           'Country Code': 'ABC', 'Contestant Code': 'ABC1',
                           'Given Name': 'Given 1', 'Family Name': 'Family 1',
                           'P1': '', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '0', 'Award': '', 'Extra Awards': ''},
                          {'Country Name': 'Test Second Country',
                           'Country Code': 'DEF', 'Contestant Code': 'DEF1',
                           'Given Name': 'Given 2', 'Family Name': 'Family 2',
                           'P1': '', 'P2': '', 'P3': '',
                           'P4': '', 'P5': '', 'P6': '',
                           'Total': '0', 'Award': '', 'Extra Awards': ''}])
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(reg_csv, admin_csv)
        self.assertEqual(reg_csv_p, admin_csv)

    def test_event_medal_boundaries_csv_errors(self):
        """
        Test errors from medal_boundaries_csv action.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        session.check_open_relative('country?@action=medal_boundaries_csv',
                                    error='This action only applies '
                                    'to events')
        # Because no general permissions are granted on the event
        # class, this page asks for login as well as giving the error
        # message.
        session.check_open_relative('event1?@action=medal_boundaries_csv',
                                    error='Node id specified for CSV '
                                    'generation', login=True)
        admin_session.check_open_relative('country?@action='
                                          'medal_boundaries_csv',
                                          error='This action only applies '
                                          'to events')
        admin_session.check_open_relative('event1?@action='
                                          'medal_boundaries_csv',
                                          error='Node id specified for CSV '
                                          'generation')

    @_with_config(docgen_directory='docgen', badge_use_background='No')
    def test_person_name_badge(self):
        """
        Test online name badge creation.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.check_open_relative('person1')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[2])
        badge_response = admin_session.check_submit_selected(html=False)
        self.assertEqual(badge_response.headers['content-type'],
                         'application/pdf')
        self.assertEqual(badge_response.headers['content-disposition'],
                         'attachment; filename=badge-person1.pdf')
        self.assertTrue(badge_response.content.startswith(b'%PDF-'))

    @_with_config(docgen_directory='docgen')
    def test_person_name_badge_background(self):
        """
        Test online name badge creation, with background.
        """
        pdf_filename, dummy = self.gen_test_pdf()
        shutil.copyfile(pdf_filename,
                        self.instance.docgen_badge_background_pdf)
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        # Also test badge naming for person other than person 1 here.
        admin_session.create_person('XMO 2015 Staff', 'Problem Selection')
        admin_session.check_open_relative('person2')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[2])
        badge_response = admin_session.check_submit_selected(html=False)
        self.assertEqual(badge_response.headers['content-type'],
                         'application/pdf')
        self.assertEqual(badge_response.headers['content-disposition'],
                         'attachment; filename=badge-person2.pdf')
        self.assertTrue(badge_response.content.startswith(b'%PDF-'))

    @_with_config(docgen_directory='docgen')
    def test_person_name_badge_errors(self):
        """
        Test errors from online name badge creation.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.check_open_relative('person1')
        form = admin_session.get_main().find_all('form')[2]
        form['action'] = 'country1'
        admin_session.b.select_form(form)
        admin_session.check_submit_selected(error='Invalid class for document '
                                            'generation')
        admin_session.check_open_relative('person1')
        form = admin_session.get_main().find_all('form')[2]
        admin_session.b.select_form(form)
        # The error here is that this test is configured to use a
        # background but none is available.
        badge_response = admin_session.check_submit_selected(html=False,
                                                             mail=True)
        self.assertEqual(badge_response.headers['content-type'],
                         'text/plain; charset=UTF-8')
        self.assertIn(b'lanyard-generic.pdf', badge_response.content)
        self.assertIn(b'lanyard-generic.pdf', admin_session.last_mail_dec)
        # Permission error (requires user to have valid form, then
        # have permissions removed, then try submitting it).
        admin_session.create_user('admin2', 'XMO 2015 Staff', 'Admin')
        admin2_session = self.get_session('admin2')
        admin2_session.check_open_relative('person1')
        form = admin2_session.get_main().find_all('form')[2]
        admin2_session.b.select_form(form)
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to generate the name '
                                             'badge for',
                                             status=403)

    def test_person_name_badge_none(self):
        """
        Test online name badge creation disabled.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.check_open_relative('person1')
        form_list = admin_session.get_main().find_all('form')
        self.assertEqual(len(form_list), 2)
        # Modify the previous form to use the name_badge action to
        # test the error when no document generation directory is
        # configured.
        form = form_list[1]
        submit = form.find('input', type='submit')
        self.assertEqual(submit['value'],
                         'Remove this person (requires confirmation)')
        admin_session.b.select_form(form)
        admin_session.b.get_current_form().set('@action', 'name_badge',
                                               force=True)
        admin_session.check_submit_selected(error='Online document generation '
                                            'not enabled')

    @_with_config(docgen_directory='docgen', badge_use_background='No')
    def test_person_name_badge_zip(self):
        """
        Test online name badge zip creation.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.create_person('XMO 2015 Staff', 'Problem Selection')
        admin_session.check_open_relative('person')
        admin_session.select_main_form()
        zip_response = admin_session.check_submit_selected(html=False)
        self.assertEqual(zip_response.headers['content-type'],
                         'application/zip')
        self.assertEqual(zip_response.headers['content-disposition'],
                         'attachment; filename=badges.zip')
        zip_io = io.BytesIO(zip_response.content)
        zip_zip = zipfile.ZipFile(zip_io, 'r')
        zip_contents = [f.filename for f in zip_zip.infolist()]
        expected_contents = ['badges/badge-person1.pdf',
                             'badges/badge-person2.pdf']
        self.assertEqual(zip_contents, expected_contents)
        self.assertTrue(zip_zip.read('badges/badge-person1.pdf').startswith(
            b'%PDF-'))
        self.assertTrue(zip_zip.read('badges/badge-person2.pdf').startswith(
            b'%PDF-'))
        zip_zip.close()

    @_with_config(docgen_directory='docgen')
    def test_person_name_badge_zip_background(self):
        """
        Test online name badge zip creation, with background.
        """
        pdf_filename, dummy = self.gen_test_pdf()
        shutil.copyfile(pdf_filename,
                        self.instance.docgen_badge_background_pdf)
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.create_person('XMO 2015 Staff', 'Problem Selection')
        admin_session.check_open_relative('person')
        admin_session.select_main_form()
        zip_response = admin_session.check_submit_selected(html=False)
        self.assertEqual(zip_response.headers['content-type'],
                         'application/zip')
        self.assertEqual(zip_response.headers['content-disposition'],
                         'attachment; filename=badges.zip')
        zip_io = io.BytesIO(zip_response.content)
        zip_zip = zipfile.ZipFile(zip_io, 'r')
        zip_contents = [f.filename for f in zip_zip.infolist()]
        expected_contents = ['badges/badge-person1.pdf',
                             'badges/badge-person2.pdf']
        self.assertEqual(zip_contents, expected_contents)
        self.assertTrue(zip_zip.read('badges/badge-person1.pdf').startswith(
            b'%PDF-'))
        self.assertTrue(zip_zip.read('badges/badge-person2.pdf').startswith(
            b'%PDF-'))
        zip_zip.close()

    @_with_config(docgen_directory='docgen')
    def test_person_name_badge_zip_errors(self):
        """
        Test errors from online name badge zip creation.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.create_person('XMO 2015 Staff', 'Problem Selection')
        admin_session.check_open_relative('person')
        admin_session.select_main_form()
        # The error here is that this test is configured to use a
        # background but none is available.
        zip_response = admin_session.check_submit_selected(html=False,
                                                           mail=True)
        self.assertEqual(zip_response.headers['content-type'],
                         'text/plain; charset=UTF-8')
        self.assertIn(b'lanyard-generic.pdf', zip_response.content)
        self.assertIn(b'lanyard-generic.pdf', admin_session.last_mail_dec)

    def test_person_name_badge_zip_none(self):
        """
        Test online name badge zip creation disabled.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.check_open_relative('person1')
        form_list = admin_session.get_main().find_all('form')
        self.assertEqual(len(form_list), 2)
        # Modify the previous form to use the name_badge action to
        # test the error when no document generation directory is
        # configured, and to try to create a zip file.
        form = form_list[1]
        form['action'] = 'person'
        submit = form.find('input', type='submit')
        self.assertEqual(submit['value'],
                         'Remove this person (requires confirmation)')
        admin_session.b.select_form(form)
        admin_session.b.get_current_form().set('@action', 'name_badge',
                                               force=True)
        admin_session.check_submit_selected(error='Online document generation '
                                            'not enabled')

    @_with_config(docgen_directory='docgen', require_passport_number='Yes',
                  require_nationality='Yes')
    def test_person_invitation_letter(self):
        """
        Test online invitation letter creation.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'passport_number': '123454321',
                                     'nationality': 'Matholympian'})
        admin_session.check_open_relative('person1')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[3])
        invitation_response = admin_session.check_submit_selected(html=False)
        self.assertEqual(invitation_response.headers['content-type'],
                         'application/pdf')
        self.assertEqual(invitation_response.headers['content-disposition'],
                         'attachment; filename=invitation-letter-person1.pdf')
        self.assertTrue(invitation_response.content.startswith(b'%PDF-'))
        # Changing relevant details after an invitation letter was
        # generated results in an email being sent; changing
        # irrelevant details does not.
        admin_session.edit('person', '1',
                           {'given_name': 'Changed Given'},
                           mail=True)
        self.assertIn(
            b'TO: admin@example.invalid, webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        admin_session.edit('person', '1',
                           {'tshirt': 'M'})
        admin_session.edit('person', '1',
                           {'family_name': 'Changed Family'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'passport_given_name': 'Changed Passport Given'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'passport_family_name': 'Changed Passport Family'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'nationality': 'Other'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'passport_number': '987654321'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'gender': 'Male'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'date_of_birth_year': '1999'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'date_of_birth_month': 'February'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'date_of_birth_day': '2'},
                           mail=True)

    @_with_config(docgen_directory='docgen')
    def test_person_invitation_letter_register(self):
        """
        Test online invitation letter creation with registering user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 2')
        reg_session.check_open_relative('person1')
        reg_session.b.select_form(
            reg_session.get_main().find_all('form')[1])
        invitation_response = reg_session.check_submit_selected(html=False)
        self.assertEqual(invitation_response.headers['content-type'],
                         'application/pdf')
        self.assertEqual(invitation_response.headers['content-disposition'],
                         'attachment; filename=invitation-letter-person1.pdf')
        self.assertTrue(invitation_response.content.startswith(b'%PDF-'))

    @_with_config(docgen_directory='docgen')
    def test_person_invitation_letter_errors(self):
        """
        Test errors from online invitation letter creation.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.check_open_relative('person1')
        form = admin_session.get_main().find_all('form')[3]
        form['action'] = 'country1'
        admin_session.b.select_form(form)
        admin_session.check_submit_selected(error='Invalid class for document '
                                            'generation')
        admin_session.check_open_relative('person1')
        form = admin_session.get_main().find_all('form')[3]
        admin_session.b.select_form(form)
        with open(os.path.join(self.instance.docgen_dir, 'templates',
                               'invitation-letter-template.tex'), 'w') as f:
            f.write(r'\notavalidlatexdocument')
        invitation_response = admin_session.check_submit_selected(html=False,
                                                                  mail=True)
        self.assertEqual(invitation_response.headers['content-type'],
                         'text/plain; charset=UTF-8')
        self.assertIn(b'notavalidlatexdocument', invitation_response.content)
        self.assertIn(b'notavalidlatexdocument', admin_session.last_mail_dec)
        # Permission error (requires user to have valid form, then
        # have permissions removed, then try submitting it).
        admin_session.create_user('admin2', 'XMO 2015 Staff', 'Admin')
        admin2_session = self.get_session('admin2')
        admin2_session.check_open_relative('person1')
        form = admin2_session.get_main().find_all('form')[3]
        admin2_session.b.select_form(form)
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to generate the '
                                             'invitation letter for',
                                             status=403)
        # Similarly, with a registering user.
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'Admin'})
        reg_session.check_open_relative('person1')
        form = reg_session.get_main().find_all('form')[3]
        reg_session.b.select_form(form)
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'User,Register'})
        reg_session.check_submit_selected(error='You do not have '
                                          'permission to generate the '
                                          'invitation letter for',
                                          status=403)

    def test_person_invitation_letter_none(self):
        """
        Test online invitation letter creation disabled.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.check_open_relative('person1')
        form_list = admin_session.get_main().find_all('form')
        self.assertEqual(len(form_list), 2)
        # Modify the previous form to use the invitation_letter action
        # to test the error when no document generation directory is
        # configured.
        form = form_list[1]
        submit = form.find('input', type='submit')
        self.assertEqual(submit['value'],
                         'Remove this person (requires confirmation)')
        admin_session.b.select_form(form)
        admin_session.b.get_current_form().set('@action', 'invitation_letter',
                                               force=True)
        admin_session.check_submit_selected(error='Online document generation '
                                            'not enabled')

    @_with_config(docgen_directory='docgen', invitation_letter_register='No')
    def test_person_invitation_letter_register_none(self):
        """
        Test online invitation letter creation by registering user disabled.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 2')
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'Admin'})
        reg_session.check_open_relative('person1')
        form = reg_session.get_main().find_all('form')[3]
        reg_session.b.select_form(form)
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'User,Register'})
        reg_session.check_submit_selected(error='You do not have '
                                          'permission to generate the '
                                          'invitation letter for',
                                          status=403)

    @_with_config(docgen_directory='docgen', require_passport_number='Yes',
                  require_nationality='Yes')
    def test_person_invitation_letter_zip(self):
        """
        Test online invitation letter zip creation.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator',
                                    {'passport_number': '123454321',
                                     'nationality': 'Matholympian'})
        admin_session.create_person('XMO 2015 Staff', 'Problem Selection',
                                    {'passport_number': '543212345',
                                     'nationality': 'Matholympian'})
        admin_session.check_open_relative('person')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        zip_response = admin_session.check_submit_selected(html=False)
        self.assertEqual(zip_response.headers['content-type'],
                         'application/zip')
        self.assertEqual(zip_response.headers['content-disposition'],
                         'attachment; filename=invitation-letters.zip')
        zip_io = io.BytesIO(zip_response.content)
        zip_zip = zipfile.ZipFile(zip_io, 'r')
        zip_contents = [f.filename for f in zip_zip.infolist()]
        expected_contents = [
            'invitation-letters/invitation-letter-person1.pdf',
            'invitation-letters/invitation-letter-person2.pdf']
        self.assertEqual(zip_contents, expected_contents)
        self.assertTrue(zip_zip.read(
            'invitation-letters/invitation-letter-person1.pdf').startswith(
                b'%PDF-'))
        self.assertTrue(zip_zip.read(
            'invitation-letters/invitation-letter-person2.pdf').startswith(
                b'%PDF-'))
        zip_zip.close()
        # Changing relevant details after an invitation letter was
        # generated results in an email being sent; changing
        # irrelevant details does not.
        admin_session.edit('person', '1',
                           {'given_name': 'Changed Given'},
                           mail=True)
        self.assertIn(
            b'TO: admin@example.invalid, webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        admin_session.edit('person', '2',
                           {'tshirt': 'M'})
        admin_session.edit('person', '1',
                           {'family_name': 'Changed Family'},
                           mail=True)
        admin_session.edit('person', '2',
                           {'passport_given_name': 'Changed Passport Given'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'passport_family_name': 'Changed Passport Family'},
                           mail=True)
        admin_session.edit('person', '2',
                           {'nationality': 'Other'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'passport_number': '987654321'},
                           mail=True)
        admin_session.edit('person', '2',
                           {'gender': 'Male'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'date_of_birth_year': '1999'},
                           mail=True)
        admin_session.edit('person', '2',
                           {'date_of_birth_month': 'February'},
                           mail=True)
        admin_session.edit('person', '1',
                           {'date_of_birth_day': '2'},
                           mail=True)

    @_with_config(docgen_directory='docgen')
    def test_person_invitation_letter_zip_errors(self):
        """
        Test errors from online invitation letter zip creation.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.create_person('XMO 2015 Staff', 'Problem Selection')
        # Test permission error with a registering user.
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'Admin'})
        reg_session.check_open_relative('person')
        form = reg_session.get_main().find_all('form')[1]
        reg_session.b.select_form(form)
        admin_session.edit('user', self.instance.userids['ABC_reg'],
                           {'roles': 'User,Register'})
        reg_session.check_submit_selected(error='You do not have '
                                          'permission to generate the '
                                          'invitation letter for',
                                          status=403)
        # Test error from LaTeX.
        admin_session.check_open_relative('person')
        admin_session.b.select_form(
            admin_session.get_main().find_all('form')[1])
        with open(os.path.join(self.instance.docgen_dir, 'templates',
                               'invitation-letter-template.tex'), 'w') as f:
            f.write(r'\notavalidlatexdocument')
        zip_response = admin_session.check_submit_selected(html=False,
                                                           mail=True)
        self.assertEqual(zip_response.headers['content-type'],
                         'text/plain; charset=UTF-8')
        self.assertIn(b'notavalidlatexdocument', zip_response.content)
        self.assertIn(b'notavalidlatexdocument', admin_session.last_mail_dec)

    def test_person_invitation_letter_zip_none(self):
        """
        Test online invitation letter zip creation disabled.
        """
        admin_session = self.get_session('admin')
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        admin_session.check_open_relative('person1')
        form_list = admin_session.get_main().find_all('form')
        self.assertEqual(len(form_list), 2)
        # Modify the previous form to use the invitation_letter action
        # to test the error when no document generation directory is
        # configured, and to try to create a zip file.
        form = form_list[1]
        form['action'] = 'person'
        submit = form.find('input', type='submit')
        self.assertEqual(submit['value'],
                         'Remove this person (requires confirmation)')
        admin_session.b.select_form(form)
        admin_session.b.get_current_form().set('@action', 'invitation_letter',
                                               force=True)
        admin_session.check_submit_selected(error='Online document generation '
                                            'not enabled')

    def test_person_bulk_register(self):
        """
        Test bulk registration of people.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        admin_session.create('arrival', {'name': 'Example Airport'})
        admin_session.create('arrival', {'name': 'Example Station'})
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        reg2_csv = reg2_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        self.assertEqual(reg2_csv, [])
        csv_cols = ['Person Number', 'Given Name', 'Family Name', 'Ignore',
                    'Country Code', 'Primary Role', 'Other Roles',
                    'Guide For Codes', 'Allergies and Dietary Requirements',
                    'Arrival Place', 'Arrival Date', 'Arrival Time',
                    'Arrival Flight', 'Departure Place', 'Departure Date',
                    'Departure Time', 'Departure Flight', 'Phone Number',
                    'Contact Email 1', 'Contact Email 2']
        csv_in = [{'Person Number': '123',
                   'Given Name': 'Given One  ',
                   'Family Name': '  Family One',
                   'Ignore': 'Random text',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator',
                   'Other Roles': 'Jury Chair,Problem Selection',
                   'Arrival Place': 'Example Airport',
                   'Arrival Date': '2015-04-02',
                   'Arrival Time': '12:35',
                   'Arrival Flight': 'ABC987',
                   'Departure Place': 'Example Station',
                   'Departure Date': '2015-04-03',
                   'Departure Time': '23:59',
                   'Departure Flight': 'XYZ123',
                   'Phone Number': '0123456789'},
                  {'Given Name': ' Test\u00fd',
                   'Family Name': 'Test',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Guide',
                   'Guide For Codes': 'ABC,DEF',
                   'Allergies and Dietary Requirements': 'Vegetarian',
                   'Contact Email 1': 'DEF1@example.invalid',
                   'Contact Email 2': 'DEF2@example.invalid'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(mail=True)
        self.assertIn(
            b'\nTO: DEF1@example.invalid, DEF2@example.invalid, '
            b'webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        # The non-ASCII name means a Content-Transfer-Encoding must be
        # specified rather than attempting to send the mail as 8-bit
        # (which fails when Roundup is run in an ASCII locale).
        self.assertIn(
            b'\nContent-Transfer-Encoding:',
            admin_session.last_mail_bin)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        reg2_csv = reg2_session.get_people_csv()
        expected_p1 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '1',
                       'Annual URL': self.instance.url + 'person1',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                       'Other Roles': 'Jury Chair,Problem Selection',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Given One', 'Family Name': 'Family One',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': '123'}
        expected_p2 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '2',
                       'Annual URL': self.instance.url + 'person2',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Guide',
                       'Other Roles': '',
                       'Guide For': 'Test First Country,Test Second Country',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Test\u00fd', 'Family Name': 'Test',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': ''}
        expected_p1_admin = expected_p1.copy()
        expected_p2_admin = expected_p2.copy()
        expected_p1_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': 'Example Airport',
             'Arrival Date': '2015-04-02', 'Arrival Time': '12:35',
             'Arrival Flight': 'ABC987', 'Departure Place': 'Example Station',
             'Departure Date': '2015-04-03', 'Departure Time': '23:59',
             'Departure Flight': 'XYZ123', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '0123456789', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': 'f78b11',
             'Badge Inner Colour': 'fccc8f', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given One',
             'Passport Family Name': 'Family One',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        expected_p2_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': 'Vegetarian',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Test\u00fd',
             'Passport Family Name': 'Test',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        self.assertEqual(anon_csv, [expected_p1, expected_p2])
        self.assertEqual(admin_csv, [expected_p1_admin, expected_p2_admin])
        self.assertEqual(reg_csv, [expected_p1, expected_p2])
        self.assertEqual(reg2_csv, [expected_p1, expected_p2])
        # Test without BOM in CSV file.
        csv_in = [{'Given Name': 'Test\u00fd',
                   'Family Name': 'Doe',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Guide'}]
        csv_filename = self.gen_test_csv_no_bom(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        reg2_csv = reg2_session.get_people_csv()
        expected_p3 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '3',
                       'Annual URL': self.instance.url + 'person3',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Guide',
                       'Other Roles': '',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Test\u00fd', 'Family Name': 'Doe',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': ''}
        expected_p3_admin = expected_p3.copy()
        expected_p3_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Test\u00fd',
             'Passport Family Name': 'Doe',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        self.assertEqual(anon_csv, [expected_p1, expected_p3, expected_p2])
        self.assertEqual(admin_csv,
                         [expected_p1_admin, expected_p3_admin,
                          expected_p2_admin])
        self.assertEqual(reg_csv, [expected_p1, expected_p3, expected_p2])
        self.assertEqual(reg2_csv, [expected_p1, expected_p3, expected_p2])
        # Test without trailing empty columns.
        csv_in = [{'Given Name': 'Test',
                   'Family Name': 'Doe',
                   'Country Code': 'ZZA',
                   'Primary Role': 'VIP'}]
        csv_filename = self.gen_test_csv_no_trailing_empty(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        reg2_csv = reg2_session.get_people_csv()
        expected_p4 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '4',
                       'Annual URL': self.instance.url + 'person4',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'VIP',
                       'Other Roles': '',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Test', 'Family Name': 'Doe',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': ''}
        expected_p4_admin = expected_p4.copy()
        expected_p4_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': 'a9a9a9',
             'Badge Inner Colour': 'dcdcdc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Test',
             'Passport Family Name': 'Doe',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        self.assertEqual(anon_csv, [expected_p1, expected_p3, expected_p2,
                                    expected_p4])
        self.assertEqual(admin_csv,
                         [expected_p1_admin, expected_p3_admin,
                          expected_p2_admin, expected_p4_admin])
        self.assertEqual(reg_csv, [expected_p1, expected_p3, expected_p2,
                                   expected_p4])
        self.assertEqual(reg2_csv, [expected_p1, expected_p3, expected_p2,
                                    expected_p4])

    @_with_config(consent_ui='Yes')
    def test_person_bulk_register_consent_ui(self):
        """
        Test bulk registration of people, consent information collected.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        csv_cols = ['Person Number', 'Given Name', 'Family Name',
                    'Country Code', 'Primary Role',
                    'Allergies and Dietary Requirements',
                    'Event Photos Consent', 'Photo Consent',
                    'Allergies and Dietary Requirements Consent']
        csv_in = [{'Person Number': '123',
                   'Given Name': 'Given One  ',
                   'Family Name': '  Family One',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator',
                   'Event Photos Consent': 'Yes',
                   'Photo Consent': 'badge_only',
                   'Allergies and Dietary Requirements Consent': 'No'},
                  {'Person Number': '124',
                   'Given Name': 'Given Two  ',
                   'Family Name': '  Family Two',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Jury Chair',
                   'Event Photos Consent': 'Yes',
                   'Photo Consent': 'yes',
                   'Allergies and Dietary Requirements': 'Pescetarian',
                   'Allergies and Dietary Requirements Consent': 'Yes'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        expected_p1 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '1',
                       'Annual URL': self.instance.url + 'person1',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                       'Other Roles': '',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Given One', 'Family Name': 'Family One',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': '123'}
        expected_p2 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '2',
                       'Annual URL': self.instance.url + 'person2',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Jury Chair',
                       'Other Roles': '',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Given Two', 'Family Name': 'Family Two',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': '124'}
        expected_p1_admin = expected_p1.copy()
        expected_p2_admin = expected_p2.copy()
        expected_p1_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': 'Unknown',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': 'f78b11',
             'Badge Inner Colour': 'fccc8f', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given One',
             'Passport Family Name': 'Family One',
             'Event Photos Consent': 'Yes', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        expected_p2_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': 'Pescetarian',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '231f20',
             'Badge Inner Colour': 'a7a6a6', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given Two',
             'Passport Family Name': 'Family Two',
             'Event Photos Consent': 'Yes', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        self.assertEqual(anon_csv, [expected_p1, expected_p2])
        self.assertEqual(admin_csv, [expected_p1_admin, expected_p2_admin])
        self.assertEqual(reg_csv, [expected_p1, expected_p2])

    @_with_config(static_site_directory='static-site')
    def test_person_bulk_register_static(self):
        """
        Test bulk registration of people, photos available on static site.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        reg2_csv = reg2_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        self.assertEqual(reg2_csv, [])
        csv_cols = ['Person Number', 'Given Name', 'Family Name', 'Ignore',
                    'Country Code', 'Primary Role', 'Other Roles',
                    'Guide For Codes', 'Contact Email 1', 'Contact Email 2']
        csv_in = [{'Person Number': '1',
                   'Given Name': 'Given One  ',
                   'Family Name': '  Family One',
                   'Ignore': 'Random text',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator',
                   'Other Roles': 'Jury Chair,Problem Selection'},
                  {'Person Number': '3',
                   'Given Name': ' Test\u00fd',
                   'Family Name': 'Test',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Guide',
                   'Guide For Codes': 'ABC,DEF',
                   'Contact Email 1': 'DEF1@example.invalid',
                   'Contact Email 2': 'DEF2@example.invalid'},
                  {'Given Name': 'Test\u00fd',
                   'Family Name': 'Doe',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Guide'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(mail=True)
        self.assertIn(
            b'\nTO: DEF1@example.invalid, DEF2@example.invalid, '
            b'webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        reg2_csv = reg2_session.get_people_csv()
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected_p1 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '1',
                       'Annual URL': self.instance.url + 'person1',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                       'Other Roles': 'Jury Chair,Problem Selection',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Given One', 'Family Name': 'Family One',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': img_url_csv,
                       'Generic Number': '1'}
        expected_p2 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '2',
                       'Annual URL': self.instance.url + 'person2',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Guide',
                       'Other Roles': '',
                       'Guide For': 'Test First Country,Test Second Country',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Test\u00fd', 'Family Name': 'Test',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': '3'}
        expected_p3 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '3',
                       'Annual URL': self.instance.url + 'person3',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Guide',
                       'Other Roles': '',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Test\u00fd', 'Family Name': 'Doe',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': ''}
        expected_p1_admin = expected_p1.copy()
        expected_p2_admin = expected_p2.copy()
        expected_p3_admin = expected_p3.copy()
        expected_p1_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': img_url_csv,
             'Badge Background': 'generic', 'Badge Outer Colour': 'f78b11',
             'Badge Inner Colour': 'fccc8f', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given One',
             'Passport Family Name': 'Family One',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        expected_p2_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Test\u00fd',
             'Passport Family Name': 'Test',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        expected_p3_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Test\u00fd',
             'Passport Family Name': 'Doe',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        self.assertEqual(anon_csv, [expected_p1, expected_p3, expected_p2])
        self.assertEqual(admin_csv,
                         [expected_p1_admin, expected_p3_admin,
                          expected_p2_admin])
        self.assertEqual(reg_csv, [expected_p1, expected_p3, expected_p2])
        self.assertEqual(reg2_csv, [expected_p1, expected_p3, expected_p2])
        # Check the image from the URL in the .csv file.
        anon_bytes = session.get_bytes(img_url_csv)
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(anon_bytes, photo_bytes)
        self.assertEqual(admin_bytes, photo_bytes)

    def test_person_bulk_register_photo(self):
        """
        Test bulk registration of people, photo upload.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        csv_cols = ['Given Name', 'Family Name',
                    'Country Code', 'Primary Role', 'Photo']
        csv_in = [{'Given Name': 'Given One',
                   'Family Name': 'Family One',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator',
                   'Photo': 'example.jpg'},
                  {'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Guide',
                   'Photo': 'example.png'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        dummy, png_contents = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        dummy, jpg_contents = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        zip_filename = self.gen_test_zip({'example.png': png_contents,
                                          'example.jpg': jpg_contents})
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'zip_file': zip_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        img1_url_csv = self.instance.url + 'photo1/photo.jpg'
        img2_url_csv = self.instance.url + 'photo2/photo.png'
        expected_p1 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '1',
                       'Annual URL': self.instance.url + 'person1',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                       'Other Roles': '',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Given One', 'Family Name': 'Family One',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': img1_url_csv,
                       'Generic Number': ''}
        expected_p2 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '2',
                       'Annual URL': self.instance.url + 'person2',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Guide',
                       'Other Roles': '',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Test', 'Family Name': 'Test',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': img2_url_csv,
                       'Generic Number': ''}
        expected_p1_admin = expected_p1.copy()
        expected_p2_admin = expected_p2.copy()
        expected_p1_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': img1_url_csv,
             'Badge Background': 'generic', 'Badge Outer Colour': 'f78b11',
             'Badge Inner Colour': 'fccc8f', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given One',
             'Passport Family Name': 'Family One',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        expected_p2_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': img2_url_csv,
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Test',
             'Passport Family Name': 'Test',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        self.assertEqual(anon_csv, [expected_p1, expected_p2])
        self.assertEqual(admin_csv, [expected_p1_admin, expected_p2_admin])
        self.assertEqual(reg_csv, [expected_p1, expected_p2])
        # Check the images from the URLs in the .csv file.
        anon_bytes1 = session.get_bytes(img1_url_csv)
        admin_bytes1 = admin_session.get_bytes(img1_url_csv)
        reg_bytes1 = reg_session.get_bytes(img1_url_csv)
        self.assertEqual(anon_bytes1, jpg_contents)
        self.assertEqual(admin_bytes1, jpg_contents)
        self.assertEqual(reg_bytes1, jpg_contents)
        anon_bytes2 = session.get_bytes(img2_url_csv)
        admin_bytes2 = admin_session.get_bytes(img2_url_csv)
        reg_bytes2 = reg_session.get_bytes(img2_url_csv)
        self.assertEqual(anon_bytes2, png_contents)
        self.assertEqual(admin_bytes2, png_contents)
        self.assertEqual(reg_bytes2, png_contents)

    @_with_config(consent_ui='Yes')
    def test_person_bulk_register_photo_consent(self):
        """
        Test bulk registration of people, photo upload, consent
        information collected.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        csv_cols = ['Given Name', 'Family Name',
                    'Country Code', 'Primary Role', 'Photo', 'Photo Consent']
        csv_in = [{'Given Name': 'Given One',
                   'Family Name': 'Family One',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator',
                   'Photo': 'example.jpg',
                   'Photo Consent': 'badge_only'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        dummy, jpg_contents = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        zip_filename = self.gen_test_zip({'example.jpg': jpg_contents})
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'zip_file': zip_filename})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected()
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        img_url_csv = self.instance.url + 'photo1/photo.jpg'
        expected_p1 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '1',
                       'Annual URL': self.instance.url + 'person1',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                       'Other Roles': '',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Given One', 'Family Name': 'Family One',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': ''}
        expected_p1_admin = expected_p1.copy()
        expected_p1_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': img_url_csv,
             'Badge Background': 'generic', 'Badge Outer Colour': 'f78b11',
             'Badge Inner Colour': 'fccc8f', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given One',
             'Passport Family Name': 'Family One',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        self.assertEqual(anon_csv, [expected_p1])
        self.assertEqual(admin_csv, [expected_p1_admin])
        self.assertEqual(reg_csv, [expected_p1])
        # Check the image from the URL in the .csv file.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, jpg_contents)
        # Check the photo is not accessible anonymously or by
        # registering users.
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
                           status=403)
        reg_session.check_open(img_url_csv,
                               error='You are not allowed to view this file',
                               status=403)

    def test_person_bulk_register_semicolon(self):
        """
        Test bulk registration of people, semicolon delimiter used.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_country('DEF', 'Test Second Country')
        reg_session = self.get_session('ABC_reg')
        reg2_session = self.get_session('DEF_reg')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        reg2_csv = reg2_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])
        self.assertEqual(reg_csv, [])
        self.assertEqual(reg2_csv, [])
        csv_cols = ['Person Number', 'Given Name', 'Family Name', 'Ignore',
                    'Country Code', 'Primary Role', 'Other Roles',
                    'Guide For Codes', 'Contact Email 1', 'Contact Email 2']
        csv_in = [{'Person Number': '123',
                   'Given Name': 'Given One  ',
                   'Family Name': '  Family One',
                   'Ignore': 'Random text',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator',
                   'Other Roles': 'Jury Chair,Problem Selection'},
                  {'Given Name': ' Test\u00fd',
                   'Family Name': 'Test',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Guide',
                   'Guide For Codes': 'ABC,DEF',
                   'Contact Email 1': 'DEF1@example.invalid',
                   'Contact Email 2': 'DEF2@example.invalid'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols, delimiter=';')
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'csv_delimiter': ';'})
        admin_session.check_submit_selected()
        admin_session.select_main_form()
        admin_session.check_submit_selected(mail=True)
        self.assertIn(
            b'\nTO: DEF1@example.invalid, DEF2@example.invalid, '
            b'webmaster@example.invalid\n',
            admin_session.last_mail_bin)
        # The non-ASCII name means a Content-Transfer-Encoding must be
        # specified rather than attempting to send the mail as 8-bit
        # (which fails when Roundup is run in an ASCII locale).
        self.assertIn(
            b'\nContent-Transfer-Encoding:',
            admin_session.last_mail_bin)
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        reg2_csv = reg2_session.get_people_csv()
        expected_p1 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '1',
                       'Annual URL': self.instance.url + 'person1',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                       'Other Roles': 'Jury Chair,Problem Selection',
                       'Guide For': '',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Given One', 'Family Name': 'Family One',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': '123'}
        expected_p2 = {'XMO Number': '2', 'Country Number': '1',
                       'Person Number': '2',
                       'Annual URL': self.instance.url + 'person2',
                       'Country Name': 'XMO 2015 Staff',
                       'Country Code': 'ZZA', 'Primary Role': 'Guide',
                       'Other Roles': '',
                       'Guide For': 'Test First Country,Test Second Country',
                       'Contestant Code': '', 'Contestant Age': '',
                       'Given Name': 'Test\u00fd', 'Family Name': 'Test',
                       'P1': '', 'P2': '', 'P3': '', 'P4': '', 'P5': '',
                       'P6': '', 'Total': '', 'Award': '',
                       'Extra Awards': '', 'Photo URL': '',
                       'Generic Number': ''}
        expected_p1_admin = expected_p1.copy()
        expected_p2_admin = expected_p2.copy()
        expected_p1_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': 'f78b11',
             'Badge Inner Colour': 'fccc8f', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Given One',
             'Passport Family Name': 'Family One',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        expected_p2_admin.update(
            {'Gender': '', 'Date of Birth': '', 'Languages': '',
             'Allergies and Dietary Requirements': '',
             'T-Shirt Size': '', 'Arrival Place': '',
             'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Type': '',
             'Share Room With': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '',
             'Badge Background': 'generic', 'Badge Outer Colour': '2a3e92',
             'Badge Inner Colour': '9c95cc', 'Badge Text Colour': '000000',
             'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Passport Given Name': 'Test\u00fd',
             'Passport Family Name': 'Test',
             'Event Photos Consent': '', 'Remote Participant': 'No',
             'Basic Data Missing': 'Yes'})
        self.assertEqual(anon_csv, [expected_p1, expected_p2])
        self.assertEqual(admin_csv, [expected_p1_admin, expected_p2_admin])
        self.assertEqual(reg_csv, [expected_p1, expected_p2])
        self.assertEqual(reg2_csv, [expected_p1, expected_p2])

    def test_person_bulk_register_errors(self):
        """
        Test errors from bulk registration of people.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        # Register a person so a node id can be used in a subsequent
        # test.
        admin_session.create_person('XMO 2015 Staff', 'Coordinator')
        anon_csv_orig = session.get_people_csv()
        admin_csv_orig = admin_session.get_people_csv()
        # Error using bulk registration via GET request.
        admin_session.check_open_relative(
            'person?@action=person_bulk_register',
            error='Invalid request')
        # Errors applying action to bad class or with id specified
        # (requires modifying the form to exercise).
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        form['action'] = 'country'
        admin_session.set({'@template': 'index'})
        admin_session.check_submit_selected(error='Invalid class for bulk '
                                            'registration')
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        form['action'] = 'person1'
        admin_session.set({'@template': 'item'})
        admin_session.check_submit_selected(error='Node id specified for bulk '
                                            'registration')
        # Errors missing uploaded CSV data.  The first case (csv_file
        # present in the form but no file submitted there) is wrongly
        # handled the same as the second (no csv_file in the form) by
        # MechanicalSoup versions 0.11 and earlier
        # <https://github.com/MechanicalSoup/MechanicalSoup/issues/250>.
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        admin_session.check_submit_selected(error='no CSV file uploaded')
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.check_submit_selected(error='no CSV file uploaded')
        # Errors with CSV data of wrong type.
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.b.new_control('text', 'csv_file', 'some text')
        admin_session.check_submit_selected(error='csv_file not an uploaded '
                                            'file')
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.b.new_control('file', 'csv_contents', '')
        csv_filename = self.gen_test_csv([{'Test': 'text'}], ['Test'])
        admin_session.set({'csv_contents': csv_filename})
        admin_session.check_submit_selected(error='csv_contents an uploaded '
                                            'file')
        # Errors with encoding of CSV data.
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.b.new_control('text', 'csv_contents', '\u00ff')
        # error='.' used for cases where the error message comes from
        # the standard Python library, to avoid depending on the exact
        # text of such errors.
        admin_session.check_submit_selected(error='.')
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        csv_file_input = form.find('input', attrs={'name': 'csv_file'})
        csv_file_input.extract()
        admin_session.b.new_control('text', 'csv_contents', '!')
        admin_session.check_submit_selected(error='.')
        temp_file = tempfile.NamedTemporaryFile(suffix='.csv',
                                                dir=self.temp_dir,
                                                delete=False)
        csv_filename = temp_file.name
        temp_file.close()
        write_bytes_to_file(b'\xff', csv_filename)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='.')
        # Errors with content, where the uploaded file is a valid CSV
        # file.
        csv_cols = ['Person Number', 'Given Name', 'Family Name', 'Ignore',
                    'Country Code', 'Primary Role', 'Other Roles',
                    'Guide For Codes', 'Arrival Place', 'Arrival Date',
                    'Arrival Time', 'Departure Place', 'Departure Date',
                    'Departure Time', 'Contact Email 1', 'Contact Email 2']
        csv_in = [{'Person Number': '123',
                   'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Ignore': 'Random text',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator'},
                  {'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error="'Given Name' missing in row 2")
        csv_in = [{'Person Number': '123',
                   'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Ignore': 'Random text',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator'},
                  {'Given Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error="'Family Name' missing in row 2")
        csv_in = [{'Person Number': '123',
                   'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Ignore': 'Random text',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator'},
                  {'Given Name': 'Test', 'Family Name': 'Test',
                   'Primary Role': 'Coordinator'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error="'Country Code' missing in row 2")
        csv_in = [{'Person Number': '123',
                   'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Ignore': 'Random text',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator'},
                  {'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error="'Primary Role' missing in row 2")
        csv_in = [{'Person Number': '123',
                   'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator'},
                  {'Person Number': '123',
                   'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Person Number' duplicate "
                                            "value in row 2")
        # Errors from auditor.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Person Number': '0'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error=r'row 1: example\.invalid URLs for previous participation '
            r'must be in the form https://www\.example\.invalid/people/'
            r'personN/')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZN', 'Primary Role': 'Coordinator'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: Invalid country')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Leader'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: Staff must have '
                                            'administrative roles')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Other Roles': 'Leader'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: Staff must have '
                                            'administrative roles')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Guide For Codes': 'ABC'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: People with this '
                                            'role may not guide a country')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Guide',
                   'Guide For Codes': 'ZZA'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: May only guide '
                                            'normal countries')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '1-2-3'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: arrival date: bad '
                                            'date')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '2015-22-33'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        # Error from standard library, so not checking exact text.
        admin_session.check_submit_selected(error='row 1: arrival date: ')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '2015-04-01',
                   'Arrival Time': '000:00'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: arrival time: '
                                            'invalid hour')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '2015-04-01',
                   'Arrival Time': '00:000'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: arrival time: '
                                            'invalid minute')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '2015-04-01',
                   'Arrival Time': '25:61'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        # Error from standard library, so not checking exact text.
        admin_session.check_submit_selected(error='row 1: arrival time: ')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '2000-01-01'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: arrival date too '
                                            'early')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '2030-01-01'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: arrival date too '
                                            'late')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Date': '1-2-3'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: departure date: bad '
                                            'date')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Date': '2015-22-33'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        # Error from standard library, so not checking exact text.
        admin_session.check_submit_selected(error='row 1: departure date: ')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Date': '2015-04-02',
                   'Departure Time': '000:00'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: departure time: '
                                            'invalid hour')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Date': '2015-04-02',
                   'Departure Time': '00:000'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: departure time: '
                                            'invalid minute')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Date': '2015-04-02',
                   'Departure Time': '25:61'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        # Error from standard library, so not checking exact text.
        admin_session.check_submit_selected(error='row 1: departure time: ')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Date': '2000-01-01'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: departure date too '
                                            'early')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Date': '2030-01-01'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: departure date too '
                                            'late')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '2015-04-02',
                   'Departure Date': '2015-04-01'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: Departure date '
                                            'before arrival date')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Date': '2015-04-02', 'Arrival Time': '14:00',
                   'Departure Date': '2015-04-02', 'Departure Time': '13:59'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: Departure time '
                                            'before arrival time')
        # Error for unknown country.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZB', 'Primary Role': 'Coordinator'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: country ZZB not '
                                            'registered')
        # Error for non-staff country.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ABC', 'Primary Role': 'Leader'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: non-staff country '
                                            'specified')
        # Error for unknown role (primary or other).
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Bad role'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: unknown role Bad '
                                            'role')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Other Roles': 'Jury Chair,Random'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: unknown role Random')
        # Error for guiding unknown country.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Guide',
                   'Guide For Codes': 'ABC,DEF'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: country DEF not '
                                            'registered')
        # Error for unknown arrival or departure place.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Place': 'Unknown'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: unknown arrival '
                                            'place Unknown')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Place': 'Unknown'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: unknown departure '
                                            'place Unknown')
        # Error for arrival or departure time not in hh:mm format.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Time': '00'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: invalid arrival '
                                            'time 00')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Arrival Time': '00:00:00'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: invalid arrival '
                                            'time 00:00:00')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Time': '00'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: invalid departure '
                                            'time 00')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'IT',
                   'Departure Time': '00:00:00'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: invalid departure '
                                            'time 00:00:00')
        # Error for bad email address.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Contact Email 1': 'invalid email'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='row 1: Email address '
                                            'syntax is invalid')
        # Error for duplicate entries in Other Roles or Guide For Codes.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Other Roles': 'Jury Chair,Jury Chair'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='duplicate entries in Other '
                                            'Roles')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Guide',
                   'Guide For Codes': 'ABC,ABC'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error='duplicate entries in Guide '
                                            'For Codes')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(anon_csv, anon_csv_orig)
        self.assertEqual(admin_csv, admin_csv_orig)
        # Permission error (requires user to have valid form, then
        # have permissions removed, then try submitting it).
        admin_session.create_user('admin2', 'XMO 2015 Staff', 'Admin')
        admin2_session = self.get_session('admin2')
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin2_session.check_open_relative('person?@template=bulkregister')
        admin2_session.select_main_form()
        admin2_session.set({'csv_file': csv_filename})
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to bulk register',
                                             status=403)
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'Admin'})
        admin2_session.check_open_relative('person?@template=bulkregister')
        admin2_session.select_main_form()
        admin2_session.set({'csv_file': csv_filename})
        admin2_session.check_submit_selected()
        admin2_session.select_main_form()
        admin_session.edit('user', self.instance.userids['admin2'],
                           {'roles': 'User,Score'})
        admin2_session.check_submit_selected(error='You do not have '
                                             'permission to bulk register',
                                             status=403)

    @_with_config(consent_ui='Yes')
    def test_person_bulk_register_errors_consent_ui(self):
        """
        Test errors from bulk registration of people, consent
        information collected.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        # Errors with content, where the uploaded file is a valid CSV
        # file.
        csv_cols = ['Person Number', 'Given Name', 'Family Name',
                    'Country Code', 'Primary Role', 'Event Photos Consent',
                    'Photo Consent',
                    'Allergies and Dietary Requirements Consent']
        # Errors from auditor.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Photo Consent': 'invalid'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error=r'row 1: No choice of consent for registration photo '
            r'specified')
        # Errors for bad boolean consent information.
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Event Photos Consent': 'Maybe'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Event Photos Consent' bad "
                                            "value in row 1")
        csv_in = [{'Given Name': 'Test', 'Family Name': 'Test',
                   'Country Code': 'ZZA', 'Primary Role': 'Coordinator',
                   'Allergies and Dietary Requirements Consent': 'Maybe'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(error="'Allergies and Dietary "
                                            "Requirements Consent' bad value "
                                            "in row 1")
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])

    @_with_config(static_site_directory='static-site')
    def test_person_bulk_register_errors_static(self):
        """
        Test errors from bulk registration of people, static site checks.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        csv_cols = ['Person Number', 'Given Name', 'Family Name',
                    'Country Code', 'Primary Role']
        csv_in = [{'Given Name': 'Given One',
                   'Family Name': 'Family One',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator'},
                  {'Person Number': '12345',
                   'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Guide'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error=r'row 2: example\.invalid URL for previous participation '
            r'not valid')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])

    def test_person_bulk_register_errors_photo(self):
        """
        Test errors from bulk registration of people, photo upload.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        csv_filename = self.gen_test_csv([{'Test': 'text'}], ['Test'])
        # Errors with ZIP data of wrong type.
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        admin_session.set({'csv_file': csv_filename})
        zip_file_input = form.find('input', attrs={'name': 'zip_file'})
        zip_file_input.extract()
        admin_session.b.new_control('text', 'zip_file', 'some text')
        admin_session.check_submit_selected(error='zip_file not an uploaded '
                                            'file')
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        admin_session.set({'csv_file': csv_filename})
        zip_file_input = form.find('input', attrs={'name': 'zip_file'})
        zip_file_input.extract()
        admin_session.b.new_control('file', 'zip_ref', '')
        admin_session.set({'zip_ref': csv_filename})
        admin_session.check_submit_selected(error='zip_ref an uploaded '
                                            'file')
        # Errors with invalid ZIP file.
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        admin_session.set({'csv_file': csv_filename, 'zip_file': csv_filename})
        # error='.' used for cases where the error message comes from
        # the standard Python library, to avoid depending on the exact
        # text of such errors.
        admin_session.check_submit_selected(error='.')
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        admin_session.set({'csv_file': csv_filename})
        zip_file_input = form.find('input', attrs={'name': 'zip_file'})
        zip_file_input.extract()
        admin_session.b.new_control('text', 'zip_ref', 'some text')
        admin_session.check_submit_selected(error='zip_ref not a valid hash')
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        form = admin_session.get_main_form()
        admin_session.set({'csv_file': csv_filename})
        zip_file_input = form.find('input', attrs={'name': 'zip_file'})
        zip_file_input.extract()
        admin_session.b.new_control('text', 'zip_ref', 'f' * 64)
        admin_session.check_submit_selected(error='zip_ref not a known hash')
        # Errors with content, where the uploaded files are valid CSV
        # and ZIP files.
        csv_cols = ['Given Name', 'Family Name',
                    'Country Code', 'Primary Role', 'Photo']
        csv_in = [{'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator',
                   'Photo': 'example.jpg'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename})
        admin_session.check_submit_selected(
            error="'Photo' in row 1 with no ZIP file")
        zip_filename = self.gen_test_zip({'dummy.txt': b'not a photo\n'})
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'zip_file': zip_filename})
        admin_session.check_submit_selected(error='.')
        # Errors from auditor.
        zip_filename = self.gen_test_zip({'example.jpg': b'not a photo\n'})
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'zip_file': zip_filename})
        admin_session.check_submit_selected(error='row 1: Photos must be in '
                                            'JPEG or PNG format')
        dummy, pdf_contents = self.gen_test_pdf()
        zip_filename = self.gen_test_zip({'example.jpg': pdf_contents})
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'zip_file': zip_filename})
        admin_session.check_submit_selected(error='row 1: Photos must be in '
                                            'JPEG or PNG format')
        dummy, png_contents = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        zip_filename = self.gen_test_zip({'example.jpg': png_contents})
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'zip_file': zip_filename})
        admin_session.check_submit_selected(error=r'row 1: Filename extension '
                                            r'for photo must match contents '
                                            r'\(png\)')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])

    @_with_config(consent_ui='Yes')
    def test_person_bulk_register_errors_photo_consent(self):
        """
        Test errors from bulk registration of people, photo upload,
        consent information collected.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        csv_cols = ['Given Name', 'Family Name',
                    'Country Code', 'Primary Role', 'Photo']
        csv_in = [{'Given Name': 'Test',
                   'Family Name': 'Test',
                   'Country Code': 'ZZA',
                   'Primary Role': 'Coordinator',
                   'Photo': 'example.jpg'}]
        csv_filename = self.gen_test_csv(csv_in, csv_cols)
        dummy, jpg_contents = self.gen_test_image(2, 2, 2, '.jpg', 'JPEG')
        zip_filename = self.gen_test_zip({'example.jpg': jpg_contents})
        admin_session.check_open_relative('person?@template=bulkregister')
        admin_session.select_main_form()
        admin_session.set({'csv_file': csv_filename, 'zip_file': zip_filename})
        admin_session.check_submit_selected(error='No choice of consent for '
                                            'registration photo specified')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(anon_csv, [])
        self.assertEqual(admin_csv, [])

    def test_event_create_audit_errors(self):
        """
        Test errors from event creation auditor.
        """
        admin_session = self.get_session('admin')
        admin_session.create('event',
                             {},
                             error='Cannot create a second event object')

    def test_event_edit_audit_errors(self):
        """
        Test errors from event edit auditor.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        admin_session.create_person('Test First Country', 'Contestant 1')
        admin_session.edit('event', '1', {'registration_enabled': 'no'})
        admin_session.enter_scores('Test First Country', 'ABC', '1', ['0'])
        admin_session.enter_scores('Test First Country', 'ABC', '2', ['0'])
        admin_session.enter_scores('Test First Country', 'ABC', '3', ['0'])
        admin_session.enter_scores('Test First Country', 'ABC', '5', ['0'])
        admin_session.enter_scores('Test First Country', 'ABC', '6', ['0'])
        admin_session.edit('event', '1',
                           {'gold': '40', 'silver': '30', 'bronze': '20'},
                           error='Scores not all entered')
        admin_session.enter_scores('Test First Country', 'ABC', '4', ['0'])
        admin_session.edit('event', '1',
                           {'gold': '40', 'silver': '30'},
                           error='Must set all medal boundaries at once')
        admin_session.edit('event', '1',
                           {'silver': '30', 'bronze': '20'},
                           error='Must set all medal boundaries at once')
        admin_session.edit('event', '1',
                           {'gold': '40', 'bronze': '20'},
                           error='Must set all medal boundaries at once')
        admin_session.edit('event', '1',
                           {'gold': '44', 'silver': '30', 'bronze': '20'},
                           error='Invalid gold medal boundary')
        admin_session.edit('event', '1',
                           {'gold': '-1', 'silver': '30', 'bronze': '20'},
                           error='Invalid gold medal boundary')
        admin_session.edit('event', '1',
                           {'gold': '42', 'silver': '44', 'bronze': '20'},
                           error='Invalid silver medal boundary')
        admin_session.edit('event', '1',
                           {'gold': '42', 'silver': '-1', 'bronze': '20'},
                           error='Invalid silver medal boundary')
        admin_session.edit('event', '1',
                           {'gold': '42', 'silver': '42', 'bronze': '44'},
                           error='Invalid bronze medal boundary')
        admin_session.edit('event', '1',
                           {'gold': '42', 'silver': '42', 'bronze': '-1'},
                           error='Invalid bronze medal boundary')
        admin_session.edit('event', '1',
                           {'gold': '40', 'silver': '41', 'bronze': '40'},
                           error='Medal boundaries in wrong order')
        admin_session.edit('event', '1',
                           {'gold': '40', 'silver': '40', 'bronze': '41'},
                           error='Medal boundaries in wrong order')
        # Boundaries one more than the total number of marks (so no
        # medals) are OK.
        admin_session.edit('event', '1',
                           {'gold': '43', 'silver': '43', 'bronze': '43'})
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(admin_csv[0]['Award'], '')
        # Boundaries of 0 are OK.
        admin_session.edit('event', '1',
                           {'bronze': '0'})
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(admin_csv[0]['Award'], 'Bronze Medal')
        admin_session.edit('event', '1',
                           {'silver': '0'})
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(admin_csv[0]['Award'], 'Silver Medal')
        admin_session.edit('event', '1',
                           {'gold': '0'})
        admin_csv = admin_session.get_scores_csv()
        admin_csv_p = admin_session.get_people_csv_scores()
        anon_csv = session.get_scores_csv()
        anon_csv_p = session.get_people_csv_scores()
        self.assertEqual(admin_csv_p, admin_csv)
        self.assertEqual(anon_csv, admin_csv)
        self.assertEqual(anon_csv_p, admin_csv)
        self.assertEqual(admin_csv[0]['Award'], 'Gold Medal')
        # Editing individual boundaries after being set produces same
        # errors as setting them for the first time.
        admin_session.edit('event', '1',
                           {'gold': ''},
                           error='Must set all medal boundaries at once')
        admin_session.edit('event', '1',
                           {'silver': ''},
                           error='Must set all medal boundaries at once')
        admin_session.edit('event', '1',
                           {'bronze': ''},
                           error='Must set all medal boundaries at once')
        admin_session.edit('event', '1',
                           {'gold': '44'},
                           error='Invalid gold medal boundary')
        admin_session.edit('event', '1',
                           {'gold': '-1'},
                           error='Invalid gold medal boundary')
        admin_session.edit('event', '1',
                           {'silver': '44'},
                           error='Invalid silver medal boundary')
        admin_session.edit('event', '1',
                           {'silver': '-1'},
                           error='Invalid silver medal boundary')
        admin_session.edit('event', '1',
                           {'bronze': '44'},
                           error='Invalid bronze medal boundary')
        admin_session.edit('event', '1',
                           {'bronze': '-1'},
                           error='Invalid bronze medal boundary')
        admin_session.edit('event', '1',
                           {'gold': '40', 'silver': '30', 'bronze': '20'})
        admin_session.edit('event', '1',
                           {'gold': '29'},
                           error='Medal boundaries in wrong order')
        admin_session.edit('event', '1',
                           {'silver': '41'},
                           error='Medal boundaries in wrong order')
        admin_session.edit('event', '1',
                           {'silver': '19'},
                           error='Medal boundaries in wrong order')
        admin_session.edit('event', '1',
                           {'bronze': '31'},
                           error='Medal boundaries in wrong order')
        # Unsetting all medal boundaries at once is OK.
        admin_session.edit('event', '1',
                           {'gold': '', 'silver': '', 'bronze': ''})

    def test_role_create_audit_errors(self):
        """
        Test errors from role creation auditor.
        """
        admin_session = self.get_session('admin')
        admin_session.create('matholymprole',
                             {'name': 'Random',
                              'room_types': ['Single room'],
                              'default_room_type': 'Shared room',
                              'badge_type': 'Organiser'},
                             error='Default room type not in permitted '
                             'room types')

    def test_role_create_audit_errors_missing(self):
        """
        Test errors from role creation auditor, missing required data.
        """
        admin_session = self.get_session('admin')
        admin_session.create('matholymprole',
                             {'default_room_type': 'Shared room',
                              'badge_type': 'Organiser'},
                             error='Required matholymprole property name not '
                             'supplied')
        admin_session.create('matholymprole',
                             {'name': 'Something',
                              'badge_type': 'Organiser'},
                             error='Required matholymprole property '
                             'default_room_type not supplied')
        admin_session.create('matholymprole',
                             {'name': 'Something',
                              'default_room_type': 'Shared room'},
                             error='Required matholymprole property '
                             'badge_type not supplied')
        # The above errors are generic Roundup ones that rely on
        # @required being sent by the browser, so must not be relied
        # upon to maintain required properties of data since the
        # browser should not be trusted; also verify the checks from
        # the auditor in case @required is not sent.
        admin_session.create('matholymprole',
                             {'@required': '',
                              'default_room_type': 'Shared room',
                              'badge_type': 'Organiser'},
                             error='No role name specified')
        admin_session.create('matholymprole',
                             {'@required': '',
                              'name': 'Something',
                              'badge_type': 'Organiser'},
                             error='No default room type specified')
        admin_session.create('matholymprole',
                             {'@required': '',
                              'name': 'Something',
                              'default_room_type': 'Shared room'},
                             error='No badge type specified')

    def test_role_edit_audit_errors(self):
        """
        Test errors from role edit auditor.
        """
        admin_session = self.get_session('admin')
        admin_session.edit('matholymprole', '1',
                           {'room_types': ['Single room'],
                            'default_room_type': 'Shared room'},
                           error='Default room type not in permitted '
                           'room types')

    def test_role_edit_audit_errors_missing(self):
        """
        Test errors from role edit auditor, missing required data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.edit('matholymprole', '1',
                           {'name': ''},
                           error='Required matholymprole property name not '
                           'supplied')
        admin_session.edit('matholymprole', '1',
                           {'default_room_type': ['- no selection -']},
                           error='Required matholymprole property '
                           'default_room_type not supplied')
        admin_session.edit('matholymprole', '1',
                           {'badge_type': ['- no selection -']},
                           error='Required matholymprole property '
                           'badge_type not supplied')
        # With @required not sent, the auditor restores the previous
        # values.
        admin_session.edit('matholymprole', '1',
                           {'@required': '',
                            'name': ''})
        admin_session.edit('matholymprole', '1',
                           {'@required': '',
                            'default_room_type': ['- no selection -']},)
        admin_session.edit('matholymprole', '1',
                           {'@required': '',
                            'badge_type': ['- no selection -']},)
        # Role 1 is Contestant 1.
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'room_type': 'Single room'},
                                  error='Room type for this role must be '
                                  'Shared room')
        reg_session.create_person('Test First Country', 'Contestant 1')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        self.assertEqual(admin_csv[0]['Room Type'], 'Shared room')
        self.assertEqual(admin_csv[0]['Badge Background'], 'generic')
        self.assertEqual(admin_csv[0]['Badge Outer Colour'], '7ab558')
        self.assertEqual(admin_csv[0]['Badge Inner Colour'], 'c9deb0')
        self.assertEqual(admin_csv[0]['Badge Text Colour'], '000000')

    def test_badge_type_create_audit_errors(self):
        """
        Test errors from badge type creation auditor.
        """
        admin_session = self.get_session('admin')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': '/../hack',
                              'colour_outer': 'ffffff',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error="Background names must contain only "
                             "alphanumerics, '.', '_' and '-'")
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': '00000g',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error='Outer colour not six hexadecimal '
                             'characters')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': '000',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error='Outer colour not six hexadecimal '
                             'characters')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': '000000',
                              'colour_inner': 'gfffff',
                              'colour_text': '000000'},
                             error='Inner colour not six hexadecimal '
                             'characters')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': '000000',
                              'colour_inner': 'fffff',
                              'colour_text': '000000'},
                             error='Inner colour not six hexadecimal '
                             'characters')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': '000000',
                              'colour_inner': '000000',
                              'colour_text': 'gfffff'},
                             error='Text colour not six hexadecimal '
                             'characters')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': '000000',
                              'colour_inner': '000000',
                              'colour_text': 'fffff'},
                             error='Text colour not six hexadecimal '
                             'characters')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'a-z.A-Z.0_9OK',
                              'colour_outer': 'FeDcBa',
                              'colour_inner': '987654',
                              'colour_text': '3210Ab'})

    def test_badge_type_create_audit_errors_missing(self):
        """
        Test errors from badge type creation auditor, missing required data.
        """
        admin_session = self.get_session('admin')
        admin_session.create('badge_type',
                             {'background_name': 'random',
                              'colour_outer': 'ffffff',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error='Required badge_type property name not '
                             'supplied')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'colour_outer': 'ffffff',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error='Required badge_type property '
                             'background_name not supplied')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error='Required badge_type property '
                             'colour_outer not supplied')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': 'ffffff',
                              'colour_text': '000000'},
                             error='Required badge_type property '
                             'colour_inner not supplied')
        admin_session.create('badge_type',
                             {'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': 'ffffff',
                              'colour_inner': 'ffffff'},
                             error='Required badge_type property '
                             'colour_text not supplied')
        # The above errors are generic Roundup ones that rely on
        # @required being sent by the browser, so must not be relied
        # upon to maintain required properties of data since the
        # browser should not be trusted; also verify the checks from
        # the auditor in case @required is not sent.
        admin_session.create('badge_type',
                             {'@required': '',
                              'background_name': 'random',
                              'colour_outer': 'ffffff',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error='No badge type name specified')
        admin_session.create('badge_type',
                             {'@required': '',
                              'name': 'Random',
                              'colour_outer': 'ffffff',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error='No background name specified')
        admin_session.create('badge_type',
                             {'@required': '',
                              'name': 'Random',
                              'background_name': 'random',
                              'colour_inner': 'ffffff',
                              'colour_text': '000000'},
                             error='No outer colour specified')
        admin_session.create('badge_type',
                             {'@required': '',
                              'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': 'ffffff',
                              'colour_text': '000000'},
                             error='No inner colour specified')
        admin_session.create('badge_type',
                             {'@required': '',
                              'name': 'Random',
                              'background_name': 'random',
                              'colour_outer': 'ffffff',
                              'colour_inner': 'ffffff'},
                             error='No text colour specified')

    def test_badge_type_edit_audit_errors(self):
        """
        Test errors from badge type edit auditor.
        """
        admin_session = self.get_session('admin')
        admin_session.edit('badge_type', '1',
                           {'background_name': '/../hack'},
                           error="Background names must contain only "
                           "alphanumerics, '.', '_' and '-'")
        admin_session.edit('badge_type', '1',
                           {'colour_outer': '00000g'},
                           error='Outer colour not six hexadecimal characters')
        admin_session.edit('badge_type', '1',
                           {'colour_outer': '000'},
                           error='Outer colour not six hexadecimal characters')
        admin_session.edit('badge_type', '1',
                           {'colour_inner': 'gfffff'},
                           error='Inner colour not six hexadecimal characters')
        admin_session.edit('badge_type', '1',
                           {'colour_inner': 'fffff'},
                           error='Inner colour not six hexadecimal characters')
        admin_session.edit('badge_type', '1',
                           {'colour_text': 'gfffff'},
                           error='Text colour not six hexadecimal characters')
        admin_session.edit('badge_type', '1',
                           {'colour_text': 'fffff'},
                           error='Text colour not six hexadecimal characters')
        admin_session.edit('badge_type', '1',
                           {'name': 'Random',
                            'background_name': 'a-z.A-Z.0_9OK',
                            'colour_outer': 'FeDcBa',
                            'colour_inner': '987654',
                            'colour_text': '0123Da'})

    def test_badge_type_edit_audit_errors_missing(self):
        """
        Test errors from badge type edit auditor, missing required data.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        admin_session.edit('badge_type', '1',
                           {'name': ''},
                           error='Required badge_type property name not '
                           'supplied')
        admin_session.edit('badge_type', '1',
                           {'background_name': ''},
                           error='Required badge_type property '
                           'background_name not supplied')
        admin_session.edit('badge_type', '1',
                           {'colour_outer': ''},
                           error='Required badge_type property colour_outer '
                           'not supplied')
        admin_session.edit('badge_type', '1',
                           {'colour_inner': ''},
                           error='Required badge_type property colour_inner '
                           'not supplied')
        admin_session.edit('badge_type', '1',
                           {'colour_text': ''},
                           error='Required badge_type property colour_text '
                           'not supplied')
        # With @required not sent, the auditor restores the previous
        # values.
        admin_session.edit('badge_type', '1',
                           {'@required': '',
                            'name': ''})
        admin_session.edit('badge_type', '1',
                           {'@required': '',
                            'background_name': ''})
        admin_session.edit('badge_type', '1',
                           {'@required': '',
                            'colour_outer': ''})
        admin_session.edit('badge_type', '1',
                           {'@required': '',
                            'colour_inner': ''})
        admin_session.edit('badge_type', '1',
                           {'@required': '',
                            'colour_text': ''})
        # Badge type 1 is Leader.
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        reg_session.create_person('Test First Country', 'Leader')
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)
        self.assertEqual(admin_csv[0]['Badge Background'], 'generic')
        self.assertEqual(admin_csv[0]['Badge Outer Colour'], 'd22027')
        self.assertEqual(admin_csv[0]['Badge Inner Colour'], 'eb9984')
        self.assertEqual(admin_csv[0]['Badge Text Colour'], '000000')

    def test_user_edit_username(self):
        """
        Test errors from user editing their own username.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        # The username field would actually appear readonly in a
        # browser.  Testing this way because the approach of
        # temporarily changing roles, then changing back before
        # submitting the form, runs into the Roundup check for
        # conflicting edits to the same database item.
        reg_session.edit('user', self.instance.userids['ABC_reg'],
                         {'username': 'DEF_reg'},
                         error='You do not have permission to edit',
                         status=403)


def _set_coverage(tests, coverage):
    """Set the coverage attribute on a test or the tests in an iterable."""
    if isinstance(tests, unittest.TestCase):
        tests.coverage = coverage
    else:
        for subtest in tests:
            _set_coverage(subtest, coverage)


def load_tests(loader, standard_tests, pattern):
    """Return a TestSuite for all the registration system tests."""
    _set_coverage(standard_tests, loader.coverage)
    return unittest.TestSuite(standard_tests)
