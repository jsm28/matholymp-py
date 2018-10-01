# Test matholymp registration system.

# Copyright 2018 Joseph Samuel Myers.

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

__all__ = ['gen_image', 'gen_image_file', 'RoundupTestInstance',
           'RoundupTestSession', 'RegSystemTestCase']


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
        auto_user = 'contact_email' in data
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
        # Test login with the new user works.
        self.get_session('ABC_reg')

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
        reg_session = self.get_session('ABC_reg')
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
        reg_session = self.get_session('ABC_reg')
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
        reg_session = self.get_session('ABC_reg')
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
