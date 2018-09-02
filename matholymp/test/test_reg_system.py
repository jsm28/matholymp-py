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
import tempfile
import traceback
import unittest

try:
    import mechanicalsoup
    import roundup.instance
    import roundup.password
    # roundup_server modifies sys.path on import, so save and restore it.
    _save_path = list(sys.path)
    from roundup.scripts import roundup_server
    sys.path = _save_path
    _skip_test = False
except ImportError:
    _skip_test = True

from matholymp.fileutil import write_text_to_file, read_text_from_file, \
    replace_text_in_file

__all__ = ['RoundupTestInstance', 'RoundupTestSession', 'RegSystemTestCase']


class RoundupTestInstance(object):

    """
    A RoundupTestInstance provides a temporary Roundup installation
    used for testing.
    """

    def __init__(self, top_dir, temp_dir):
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
        os.makedirs(os.path.join(self.instance_dir, 'db'))
        self.passwords = {'admin': roundup.password.generatePassword()}
        self.config_ini = os.path.join(self.instance_dir, 'config.ini')
        self.ext_config_ini = os.path.join(self.instance_dir, 'extensions',
                                           'config.ini')
        # Ensure that example.org references cannot leak out as actual
        # network access attempts during testing, if anything
        # mistakenly tries to send email or access CSS / favicon
        # links.
        for f in (self.config_ini, self.ext_config_ini,
                  os.path.join(self.html_dir, 'page.html'),
                  os.path.join(self.html_dir, 'dpage.html')):
            replace_text_in_file(f, 'example.org', 'example.invalid')
        replace_text_in_file(self.config_ini, '\nbackend = postgresql\n',
                             '\nbackend = anydbm\n')
        replace_text_in_file(self.ext_config_ini,
                             '\nmatholymp_static_site_directory = '
                             '/some/where\n',
                             '\nmatholymp_static_site_directory =\n')
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
            os.close(write_fd)
            self.port = int(os.read(read_fd, 5))
            os.close(read_fd)
            self.url = 'http://localhost:%d/xmo/' % self.port

    def stop_server(self):
        """Stop the server started for a RoundupTestInstance."""
        if self.pid:
            os.kill(self.pid, signal.SIGINT)
            os.waitpid(self.pid, 0)


class RoundupTestSession(object):

    """
    A RoundupTestSession automates interation with a RoundupTestInstance.
    """

    def __init__(self, instance, username=None):
        """Initialise a RoundupTestSession."""
        self.instance = instance
        self.b = mechanicalsoup.StatefulBrowser(raise_on_404=True)
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
                response = sb_method(*args, **kwargs)
                response.raise_for_status()
                mail_size = os.stat(self.instance.mail_file).st_size
                mail_generated = mail_size > old_mail_size
                if mail and not mail_generated:
                    raise ValueError('request failed to generate mail')
                elif mail_generated and not mail:
                    with open(self.instance.mail_file, 'rb') as f:
                        mail_bin = f.read()[old_mail_size:]
                    raise ValueError('request generated mail: %s'
                                     % str(mail_bin))
                if hasattr(response, 'soup'):
                    soup = response.soup
                    error_generated = soup.find('p', class_='error-message')
                    if error and error_generated is None:
                        raise ValueError('request did not produce error: %s'
                                         % str(soup))
                    elif error_generated is not None and not error:
                        raise ValueError('request produced error: %s'
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

            return fn
        else:
            raise AttributeError(name)

    def get_sidebar(self):
        """Get the sidebar from the current page."""
        return self.b.get_current_page().find(id='xmo-sidebar')

    def get_main(self):
        """Get the main contents from the current page."""
        return self.b.get_current_page().find(id='xmo-main')

    def login(self, username):
        """Log in as the specified user."""
        self.b.select_form(self.get_sidebar().find('form'))
        self.b['__login_name'] = username
        self.b['__login_password'] = self.instance.passwords[username]
        self.check_submit_selected()

    def select_main_form(self):
        """Get the main form from the current page."""
        self.b.select_form(self.get_main().find('form'))

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

    def create_scoring_user(self):
        """Create a scoring user."""
        self.create_user('scoring', 'XMO 2015 Staff', 'User,Score')

    def create_country(self, code, name, other=None):
        """Create a country and corresponding user account."""
        data = {'code': code, 'name': name}
        if other is not None:
            data.update(other)
        # Currently only supports separate user account creation.
        self.create('country', data)
        self.create_user('%s_reg' % code, name, 'User,Register')

    def create_country_generic(self):
        """Create a generic country for testing."""
        self.create_country('ABC', 'Test First Country')


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
        self.instance = RoundupTestInstance(sys.path[0], self.temp_dir)

    def tearDown(self):
        for s in self.sessions:
            s.close()
        self.instance.stop_server()
        shutil.rmtree(self.temp_dir)

    def get_session(self, username=None):
        """Get a session for the specified username."""
        session = RoundupTestSession(self.instance, username)
        self.sessions.append(session)
        return session

    def all_templates_test(self, session, can_score, scoring_user):
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
            session.check_open_relative('%s?@template=%s'
                                        % (m.group(1), m.group(2)),
                                        error=error)

    def test_all_templates_admin(self):
        """
        Test that all page templates load without errors, for the admin user.
        """
        session = self.get_session('admin')
        self.all_templates_test(session, can_score=True, scoring_user=False)

    def test_all_templates_anon(self):
        """
        Test that all page templates load without errors, not logged in.
        """
        session = self.get_session()
        self.all_templates_test(session, can_score=False, scoring_user=False)

    def test_all_templates_score(self):
        """
        Test that all page templates load without errors, for a scoring user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_scoring_user()
        session = self.get_session('scoring')
        self.all_templates_test(session, can_score=True, scoring_user=True)

    def test_all_templates_register(self):
        """
        Test that all page templates load without errors, for a
        registering user.
        """
        admin_session = self.get_session('admin')
        admin_session.create_country_generic()
        session = self.get_session('ABC_reg')
        self.all_templates_test(session, can_score=False, scoring_user=False)
