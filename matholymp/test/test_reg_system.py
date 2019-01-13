# Test matholymp registration system.

# Copyright 2018-2019 Joseph Samuel Myers.

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

import os
import os.path
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
_py3 = sys.version_info.major >= 3
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

from matholymp.fileutil import read_utf8_csv, write_text_to_file, \
    read_text_from_file, replace_text_in_file, read_config_raw, \
    write_config_raw

__all__ = ['gen_image', 'gen_image_file', 'gen_pdf_file',
           'RoundupTestInstance', 'RoundupTestSession', 'RegSystemTestCase']


def gen_image(size_x, size_y, scale):
    """Generate an image with random blocks scale by scale of pixels."""
    data = bytearray(size_x * size_y * scale * scale * 3)
    line_size = size_x * scale * 3
    for y in range(size_y):
        for x in range(size_x):
            for color in range(3):
                pixel = random.randint(0, 255)
                for y_sub in range(scale):
                    for x_sub in range(scale):
                        x_pos = color + 3 * (x_sub + scale * x)
                        y_pos = y_sub + scale * y
                        pos = x_pos + line_size * y_pos
                        data[pos] = pixel
    data = memoryview(data).tobytes()
    return Image.frombytes('RGB', (size_x * scale, size_y * scale), data)


def gen_image_file(size_x, size_y, scale, filename, format, **kwargs):
    """Generate an image, in a file."""
    image = gen_image(size_x, size_y, scale)
    image.save(filename, format, **kwargs)


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
    with open(os.devnull, 'w+') as devnull:
        subprocess.check_call(['pdflatex', tex_file], cwd=dirname,
                              stdin=devnull, stdout=devnull, stderr=devnull)
    pdf_file = os.path.join(dirname, 'test.pdf')
    ret_file = os.path.join(dirname, 'test%s' % suffix)
    if ret_file != pdf_file:
        os.rename(pdf_file, ret_file)
    return ret_file


class RoundupTestInstance(object):

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
            except Exception:
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
            except Exception:
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


class RoundupTestSession(object):

    """
    A RoundupTestSession automates interation with a RoundupTestInstance.
    """

    def __init__(self, instance, username=None):
        """Initialise a RoundupTestSession."""
        self.instance = instance
        self.b = mechanicalsoup.StatefulBrowser(raise_on_404=True)
        self.last_mail_bin = None
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

            def fn(*args, **kwargs):
                # This code can be simplified once we require Python 3
                # and thus can use keyword-only parameters.
                mail = False
                if 'mail' in kwargs:
                    mail = kwargs['mail']
                    del kwargs['mail']
                error = False
                if 'error' in kwargs:
                    error = kwargs['error']
                    del kwargs['error']
                status = None
                if 'status' in kwargs:
                    status = kwargs['status']
                    del kwargs['status']
                login = False
                if 'login' in kwargs:
                    login = kwargs['login']
                    del kwargs['login']
                html = True
                if 'html' in kwargs:
                    html = kwargs['html']
                    del kwargs['html']
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
                        self.last_mail_bin = f.read()[old_mail_size:]
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
                             % (response.headers['content-disposition'],
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

    def get_people_csv(self):
        """Get the CSV file of people."""
        return self.get_download_csv('person?@action=people_csv',
                                     'people.csv')

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

    def get_img_contents(self):
        """Get the contents of the (first) img tag from the current page."""
        img_src = self.get_img()['src']
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

    def set(self, data):
        """Set the contents of fields in the selected form.

        Unlike the MechanicalSoup interfaces, 'select' fields are set
        by the labels on those fields, not their values.

        """
        form = self.b.get_current_form().form
        for key in data:
            value = data[key]
            select = form.find('select', attrs={'name': key})
            if select:
                if not (isinstance(value, list) or isinstance(value, tuple)):
                    value = (value,)
                new_value = []
                for v in value:
                    option = select.find('option', string=v)
                    new_value.append(option['value'])
                if len(new_value) == 1:
                    new_value = new_value[0]
                value = new_value
            self.b[key] = value

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
            mail_bin = self.last_mail_bin
            username_idx = mail_bin.rindex(b'Username: ')
            mail_bin = mail_bin[username_idx:]
            mail_data = mail_bin.split(b'\n')
            username_str = mail_data[0][len(b'Username: '):]
            password_str = mail_data[1]
            if not password_str.startswith(b'Password: '):
                raise ValueError('unexpected password line: %s'
                                 % str(password_str))
            password_str = password_str[len(b'Password: '):]
            if _py3:
                username = username_str.decode()
                password = password_str.decode()
            else:
                username = username_str
                password = password_str
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

    def edit(self, cls, entity_id, data, error=False, mail=False):
        """Edit some kind of entity through the corresponding form."""
        self.check_open_relative('%s%s' % (cls, entity_id))
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
        super(RegSystemTestCase, self).__init__(method_name)        

    def __str__(self):
        # Generate test names similar to those for script tests.
        test_name = self.method_name
        if test_name.startswith('test_'):
            test_name = test_name[len('test_'):]
        test_name = test_name.replace('_', '-')
        return 'registration-system ' + test_name

    def setUp(self):
        self.sessions = []
        self.temp_dir = tempfile.mkdtemp()
        self.instance = RoundupTestInstance(sys.path[0], self.temp_dir,
                                            self.config, self.coverage)

    def tearDown(self):
        for s in self.sessions:
            s.close()
        self.instance.stop_server()
        if self.coverage:
            from coverage import Coverage
            cov_base = os.path.join(sys.path[0], '.coverage.reg-system')
            cov = Coverage(data_file=cov_base)
            cov.load()
            cov.combine(data_paths=[self.temp_dir])
            cov.save()
        shutil.rmtree(self.temp_dir)

    def get_session(self, username=None):
        """Get a session for the specified username."""
        session = RoundupTestSession(self.instance, username)
        self.sessions.append(session)
        return session

    def gen_test_image(self, size_x, size_y, scale, suffix, format):
        """Generate a test image and return a tuple of the filename and the
        contents."""
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix,
                                                dir=self.temp_dir,
                                                delete=False)
        filename = temp_file.name
        temp_file.close()
        gen_image_file(size_x, size_y, scale, filename, format)
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

    def all_templates_test(self, session, forbid_classes, forbid_templates,
                           allow_templates, can_score, scoring_user):
        """Test that all page templates load without errors."""
        for t in sorted(os.listdir(self.instance.html_dir)):
            if t.startswith('_generic') or not t.endswith('.html'):
                continue
            if scoring_user and t == 'person.item.html':
                # Because scoring users have Create permission for the
                # person class, country property only, in order to
                # allow a menu of countries to be displayed properly,
                # this template (not actually useful for such users)
                # displays some [hidden] text for them.
                continue
            m = re.match(r'([a-z_]+)\.([a-z_]+)\.html\Z', t)
            if not m:
                continue
            # This template should give an error, if able to enter
            # scores, unless country and problem are specified.
            error = can_score and t == 'person.scoreenter.html'
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
        self.all_templates_test(session, forbid_classes=set(),
                                forbid_templates=set(), allow_templates=set(),
                                can_score=True, scoring_user=False)

    def test_all_templates_anon(self):
        """
        Test that all page templates load without errors, not logged in.
        """
        session = self.get_session()
        forbid_classes = {'event', 'rss', 'arrival', 'consent_form', 'gender',
                          'language', 'tshirt', 'user'}
        forbid_templates = {'country.retireconfirm.html',
                            'person.retireconfirm.html',
                            'person.rooms.html',
                            'person.scoreenter.html',
                            'person.scoreselect.html',
                            'person.status.html'}
        self.all_templates_test(session, forbid_classes=forbid_classes,
                                forbid_templates=forbid_templates,
                                allow_templates={'user.forgotten.html'},
                                can_score=False, scoring_user=False)

    def test_all_templates_score(self):
        """
        Test that all page templates load without errors, for a scoring user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_scoring_user()
        session = self.get_session('scoring')
        forbid_classes = {'event', 'rss', 'arrival', 'consent_form', 'gender',
                          'language', 'tshirt'}
        forbid_templates = {'country.retireconfirm.html',
                            'person.retireconfirm.html',
                            'person.rooms.html',
                            'person.status.html'}
        self.all_templates_test(session, forbid_classes=forbid_classes,
                                forbid_templates=forbid_templates,
                                allow_templates=set(),
                                can_score=True, scoring_user=True)

    def test_all_templates_register(self):
        """
        Test that all page templates load without errors, for a
        registering user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        session = self.get_session('ABC_reg')
        forbid_classes = {'event', 'rss'}
        forbid_templates = {'country.retireconfirm.html',
                            'person.retireconfirm.html',
                            'person.rooms.html',
                            'person.scoreenter.html',
                            'person.scoreselect.html'}
        self.all_templates_test(session, forbid_classes=forbid_classes,
                                forbid_templates=forbid_templates,
                                allow_templates=set(),
                                can_score=False, scoring_user=False)

    def all_templates_item_test(self, admin_session, session, forbid_classes):
        """Test that all page templates for existing items load without
        errors."""
        admin_session.create('arrival', {'name': 'Example Airport'})
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_country('DEF', 'Test Second Country',
                                     {'flag-1@content': flag_filename})
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                         'JPEG')
        pdf_filename, pdf_bytes = self.gen_test_pdf()
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
            m = re.match(r'([a-z_]+)\.([a-z_]+)\.html\Z', t)
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
        forbid_classes = {'event', 'rss', 'arrival', 'consent_form', 'gender',
                          'language', 'tshirt', 'user'}
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
        forbid_classes = {'event', 'rss', 'arrival', 'consent_form', 'gender',
                          'language', 'tshirt', 'user'}
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
        forbid_classes = {'consent_form', 'event', 'rss', 'user'}
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
            b'\nTO: DEF@example.invalid, webmaster@example.invalid, '
            b'DEF2@example.invalid, DEF3@example.invalid, '
            b'DEF5@example.invalid\n',
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
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        admin_session.create_country_generic()
        reg_session = self.get_session('ABC_reg')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
        reg_csv = reg_session.get_countries_csv()
        expected_abc = {'XMO Number': '2', 'Country Number': '3',
                        'Annual URL': self.instance.url + 'country3',
                        'Code': 'ABC', 'Name': 'Test First Country',
                        'Flag URL': '', 'Generic Number': '', 'Normal': 'Yes'}
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])
        self.assertEqual(reg_csv, [expected_abc, expected_staff])

    @_with_config(distinguish_official='Yes')
    def test_country_csv_official(self):
        """
        Test CSV file of countries, official / unofficial distinction.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])
        # Check the old flag image is no longer public, but is still
        # accessible to admin.
        admin_bytes = admin_session.get_bytes(img_url_csv)
        self.assertEqual(admin_bytes, flag_bytes)
        session.check_open(img_url_csv,
                           error='You are not allowed to view this file',
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
        admin_session.create_country('ABC', 'Test First Country',
                                     {'contact_email': 'bad_email'},
                                     error='Email address syntax is invalid')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'contact_extra': 'bad_email'},
                                     error='Email address syntax is invalid')
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                        'JPEG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename},
                                     error='Flags must be in PNG format')
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                        'PNG')
        admin_session.create_country('ABC', 'Test First Country',
                                     {'flag-1@content': flag_filename},
                                     error=r'Filename extension for flag '
                                     'must match contents \(png\)')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url': 'https://www.example.invalid/countries/country0/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url':
             'https://www.example.invalid/countries/country01/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url': 'https://www.example.invalid/countries/country1'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.create_country(
            'ABC', 'Test First Country',
            {'generic_url':
             'https://www.example.invalid/countries/country1N/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                        'JPEG')
        admin_session.edit('country', '3',
                           {'flag-1@content': flag_filename},
                           error='Flags must be in PNG format')
        flag_filename, flag_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                        'PNG')
        admin_session.edit('country', '3',
                           {'flag-1@content': flag_filename},
                           error=r'Filename extension for flag must match '
                           'contents \(png\)')
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/countries/country0/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.edit(
            'country', '3',
            {'generic_url':
             'https://www.example.invalid/countries/country01/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.edit(
            'country', '3',
            {'generic_url': 'https://www.example.invalid/countries/country1'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        admin_session.edit(
            'country', '3',
            {'generic_url':
             'https://www.example.invalid/countries/country1N/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/countries/countryN/')
        anon_csv = session.get_countries_csv()
        admin_csv = admin_session.get_countries_csv()
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
        admin_csv = admin_session.get_countries_csv()
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
        self.assertEqual(admin_csv,
                         [expected_abc, expected_def, expected_staff])

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
        admin_csv = admin_session.get_countries_csv()
        self.assertEqual(anon_csv, [expected_abc, expected_staff])
        self.assertEqual(admin_csv, [expected_abc, expected_staff])

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
        admin_csv = admin_session.get_countries_csv()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff])

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
             'departure_flight': 'ABC987'})
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
             'Departure Flight': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Event Photos Consent': ''})
        expected_leader_admin.update(
            {'Gender': 'Male', 'Date of Birth': '',
             'Languages': 'English,French',
             'Allergies and Dietary Requirements': '', 'T-Shirt Size': 'M',
             'Arrival Place': '', 'Arrival Date': '', 'Arrival Time': '',
             'Arrival Flight': '', 'Departure Place': 'Example Airport',
             'Departure Date': '2015-04-03', 'Departure Time': '14:50',
             'Departure Flight': 'ABC987', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Event Photos Consent': ''})
        expected_staff_admin.update(
            {'Gender': 'Female', 'Date of Birth': '2000-01-01',
             'Languages': 'English',
             'Allergies and Dietary Requirements': 'Vegetarian',
             'T-Shirt Size': 'S', 'Arrival Place': '', 'Arrival Date': '',
             'Arrival Time': '', 'Arrival Flight': '', 'Departure Place': '',
             'Departure Date': '', 'Departure Time': '',
             'Departure Flight': '', 'Room Number': '',
             'Phone Number': '9876543210', 'Badge Photo URL': '',
             'Consent Form URL': '', 'Passport or Identity Card Number': '',
             'Nationality': '',
             'Event Photos Consent': ''})
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
             'Departure Flight': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Event Photos Consent': ''})
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
             'Departure Flight': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '123456789',
             'Nationality': '', 'Event Photos Consent': ''})
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
             'Departure Flight': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': 'Matholympian', 'Event Photos Consent': ''})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_cont])
        self.assertEqual(admin_csv, [expected_cont_admin])
        self.assertEqual(reg_csv, [expected_cont])

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
             'Departure Flight': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': '', 'Event Photos Consent': 'Yes'})
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
             'Departure Flight': '', 'Room Number': '987', 'Phone Number': '',
             'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '',
             'Nationality': '', 'Event Photos Consent': 'No'})
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
             'Departure Time': '', 'Departure Flight': '', 'Room Number': '',
             'Phone Number': '', 'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Event Photos Consent': ''})
        expected_cont2 = expected_cont1.copy()
        expected_cont2_admin = expected_cont1_admin.copy()
        expected_cont2.update(
            {'Person Number': '2', 'Annual URL': self.instance.url + 'person2',
             'Primary Role': 'Contestant 2', 'Contestant Code': 'ABC2',
             'Given Name': 'Given 2', 'Family Name': 'Family 2'})
        expected_cont2_admin.update(expected_cont2)
        expected_cont2_admin['Date of Birth'] = '2000-04-01'
        expected_cont3 = expected_cont1.copy()
        expected_cont3_admin = expected_cont1_admin.copy()
        expected_cont3.update(
            {'Person Number': '3', 'Annual URL': self.instance.url + 'person3',
             'Primary Role': 'Contestant 3', 'Contestant Code': 'ABC3',
             'Given Name': 'Given 3', 'Family Name': 'Family 3'})
        expected_cont3_admin.update(expected_cont3)
        expected_cont3_admin['Date of Birth'] = '2000-04-02'
        expected_cont4 = expected_cont1.copy()
        expected_cont4_admin = expected_cont1_admin.copy()
        expected_cont4.update(
            {'Person Number': '4', 'Annual URL': self.instance.url + 'person4',
             'Primary Role': 'Contestant 4', 'Contestant Code': 'ABC4',
             'Contestant Age': '14', 'Given Name': 'Given 4',
             'Family Name': 'Family 4'})
        expected_cont4_admin.update(expected_cont4)
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
        admin_session.create('matholymprole', {'name': 'Extra,Role'})
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
             'Departure Flight': '', 'Room Number': '', 'Phone Number': '',
             'Badge Photo URL': '', 'Consent Form URL': '',
             'Passport or Identity Card Number': '', 'Nationality': '',
             'Event Photos Consent': ''})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(anon_csv, [expected_staff])
        self.assertEqual(admin_csv, [expected_staff_admin])
        self.assertEqual(reg_csv, [expected_staff])

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

    @_with_config(consent_ui='Yes')
    def test_person_photo_create_consent_no(self):
        """
        Test photos uploaded at person creation time, with consent
        information handling, no consent given.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
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

    @_with_config(static_site_directory='static-site', consent_ui='Yes')
    def test_person_photo_create_static_consent_no(self):
        """
        Test photos copied from static site at person creation time,
        with consent information handling, no consent given so not
        copied.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
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
        photo_bytes = self.instance.static_site_bytes(
            'people/person1/photo1.jpg')
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
        photo_filename, photo_bytes = self.gen_test_pdf()
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'photo-1@content': photo_filename},
                                    error='Photos must be in JPEG or PNG '
                                    'format')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'photo-1@content': photo_filename},
                                  error='Photos must be in JPEG or PNG '
                                  'format')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'PNG')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'photo-1@content': photo_filename},
                                    error='Filename extension for photo must '
                                    'match contents \(png\)')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'photo-1@content': photo_filename},
                                  error='Filename extension for photo must '
                                  'match contents \(png\)')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.png',
                                                          'JPEG')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'photo-1@content': photo_filename},
                                    error='Filename extension for photo must '
                                    'match contents \(jpg\)')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'photo-1@content': photo_filename},
                                  error='Filename extension for photo must '
                                  'match contents \(jpg\)')
        cf_filename, cf_bytes = self.gen_test_image(2, 2, 2, '.png', 'PNG')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'consent_form-1@content': cf_filename},
                                    error='Consent forms must be in PDF '
                                    'format')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'consent_form-1@content': cf_filename},
                                  error='Consent forms must be in PDF '
                                  'format')
        cf_filename, cf_bytes = self.gen_test_pdf('.png')
        admin_session.create_person('Test First Country', 'Contestant 1',
                                    {'consent_form-1@content': cf_filename},
                                    error='Filename extension for consent '
                                    'form must match contents \(pdf\)')
        reg_session.create_person('Test First Country', 'Contestant 1',
                                  {'consent_form-1@content': cf_filename},
                                  error='Filename extension for consent '
                                  'form must match contents \(pdf\)')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person0/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person01/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person1'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        admin_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person1N/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/test'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person0/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person01/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url': 'https://www.example.invalid/people/person1'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
        reg_session.create_person(
            'Test First Country', 'Contestant 1',
            {'generic_url':
             'https://www.example.invalid/people/person1N/'},
            error=r'example.invalid URLs for previous participation must be '
            'in the form https://www\.example\.invalid/people/personN/')
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
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
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
                             {'name': 'Extra Guide', 'canguide': 'yes'})
        admin_session.create_person(
            'XMO 2015 Staff', 'Extra Guide',
            {'guide_for': ['Test First Country']})
        anon_csv = session.get_people_csv()
        admin_csv = admin_session.get_people_csv()
        reg_csv = reg_session.get_people_csv()
        self.assertEqual(len(anon_csv), 1)
        self.assertEqual(len(admin_csv), 1)
        self.assertEqual(len(reg_csv), 1)

    @_with_config(consent_ui='Yes')
    def test_person_edit_audit_errors_missing_consent(self):
        """
        Test errors from person edit auditor, missing required consent
        information.
        """
        session = self.get_session()
        admin_session = self.get_session('admin')
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                          'JPEG')
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
        # It should not be necessary to upload a photo here, but
        # MechanicalSoup ignores the specified enctype, resulting in
        # an application/x-www-form-urlencoded submission, and
        # Python's cgi module defaults to ignoring blank fields in
        # such submissions, whereas the blank fields are required here
        # for the correct semantics.
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                         'JPEG')
        admin_session.set({'arrival_time_hour': '(hour)',
                           'departure_date': '(date)',
                           'photo-1@content': photo_filename})
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
        # It should not be necessary to upload a photo here, but
        # MechanicalSoup ignores the specified enctype, resulting in
        # an application/x-www-form-urlencoded submission, and
        # Python's cgi module defaults to ignoring blank fields in
        # such submissions, whereas the blank fields are required here
        # for the correct semantics.
        photo_filename, photo_bytes = self.gen_test_image(2, 2, 2, '.jpg',
                                                         'JPEG')
        admin_session.set({'date_of_birth_day': '(day)',
                           'photo-1@content': photo_filename})
        admin_session.check_submit_selected()
        admin_csv = admin_session.get_people_csv()
        self.assertEqual(len(admin_csv), 3)
        self.assertEqual(admin_csv[0]['Date of Birth'], '')
        self.assertEqual(admin_csv[1]['Date of Birth'], '')
        self.assertEqual(admin_csv[2]['Date of Birth'], '')

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
