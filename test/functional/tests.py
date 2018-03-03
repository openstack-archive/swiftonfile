#!/usr/bin/python -u
# Copyright (c) 2010-2012 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
import hashlib
import hmac
import itertools
import json
import locale
import random
import six
import time
import unittest
import urllib
import uuid
from copy import deepcopy
import eventlet
from nose import SkipTest
from swift.common.http import is_success, is_client_error

from test.functional import normalized_urls, load_constraint, cluster_info
from test.functional import check_response, retry, requires_acls
import test.functional as tf
from test.functional.swift_test_client import Account, Connection, File, \
    ResponseError


class Utils(object):
    @classmethod
    def create_ascii_name(cls, length=None):
        return uuid.uuid4().hex

    @classmethod
    def create_utf8_name(cls, length=None):
        if length is None:
            length = 15
        else:
            length = int(length)

        utf8_chars = u'\uF10F\uD20D\uB30B\u9409\u8508\u5605\u3703\u1801'\
                     u'\u0900\uF110\uD20E\uB30C\u940A\u8509\u5606\u3704'\
                     u'\u1802\u0901\uF111\uD20F\uB30D\u940B\u850A\u5607'\
                     u'\u3705\u1803\u0902\uF112\uD210\uB30E\u940C\u850B'\
                     u'\u5608\u3706\u1804\u0903\u03A9\u2603'
        return ''.join([random.choice(utf8_chars)
                        for x in range(length)]).encode('utf-8')

    create_name = create_ascii_name


class Base(unittest.TestCase):
    def setUp(self):
        cls = type(self)
        if not cls.set_up:
            cls.env.setUp()
            cls.set_up = True

    def assert_body(self, body):
        response_body = self.env.conn.response.read()
        self.assertTrue(response_body == body,
                        'Body returned: %s' % (response_body))

    def assert_status(self, status_or_statuses):
        self.assertTrue(
            self.env.conn.response.status == status_or_statuses or
            (hasattr(status_or_statuses, '__iter__') and
                self.env.conn.response.status in status_or_statuses),
            'Status returned: %d Expected: %s' %
            (self.env.conn.response.status, status_or_statuses))


class Base2(object):
    def setUp(self):
        Utils.create_name = Utils.create_utf8_name
        super(Base2, self).setUp()

    def tearDown(self):
        Utils.create_name = Utils.create_ascii_name


class TestAccountEnv(object):
    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.account.delete_containers()

        cls.containers = []
        for i in range(10):
            cont = cls.account.container(Utils.create_name())
            if not cont.create():
                raise ResponseError(cls.conn.response)

            cls.containers.append(cont)


class TestAccountDev(Base):
    env = TestAccountEnv
    set_up = False


class TestAccountDevUTF8(Base2, TestAccountDev):
    set_up = False


class TestAccount(Base):
    env = TestAccountEnv
    set_up = False

    def testNoAuthToken(self):
        self.assertRaises(ResponseError, self.env.account.info,
                          cfg={'no_auth_token': True})
        self.assert_status([401, 412])

        self.assertRaises(ResponseError, self.env.account.containers,
                          cfg={'no_auth_token': True})
        self.assert_status([401, 412])

    def testInvalidUTF8Path(self):
        invalid_utf8 = Utils.create_utf8_name()[::-1]
        container = self.env.account.container(invalid_utf8)
        self.assertFalse(container.create(cfg={'no_path_quote': True}))
        self.assert_status(412)
        self.assert_body('Invalid UTF8 or contains NULL')

    def testVersionOnlyPath(self):
        self.env.account.conn.make_request('PUT',
                                           cfg={'version_only_path': True})
        self.assert_status(412)
        self.assert_body('Bad URL')

    def testInvalidPath(self):
        was_url = self.env.account.conn.storage_url
        if (normalized_urls):
            self.env.account.conn.storage_url = '/'
        else:
            self.env.account.conn.storage_url = "/%s" % was_url
        self.env.account.conn.make_request('GET')
        try:
            self.assert_status(404)
        finally:
            self.env.account.conn.storage_url = was_url

    def testPUT(self):
        self.env.account.conn.make_request('PUT')
        self.assert_status([403, 405])

    def testAccountHead(self):
        try_count = 0
        while try_count < 5:
            try_count += 1

            info = self.env.account.info()
            for field in ['object_count', 'container_count', 'bytes_used']:
                self.assertTrue(info[field] >= 0)

            if info['container_count'] == len(self.env.containers):
                break

            if try_count < 5:
                time.sleep(1)

        self.assertEqual(info['container_count'], len(self.env.containers))
        self.assert_status(204)

    def testContainerSerializedInfo(self):
        container_info = {}
        for container in self.env.containers:
            info = {'bytes': 0}
            info['count'] = random.randint(10, 30)
            for i in range(info['count']):
                file_item = container.file(Utils.create_name())
                bytes = random.randint(1, 32768)
                file_item.write_random(bytes)
                info['bytes'] += bytes

            container_info[container.name] = info

        for format_type in ['json', 'xml']:
            for a in self.env.account.containers(
                    parms={'format': format_type}):
                self.assertTrue(a['count'] >= 0)
                self.assertTrue(a['bytes'] >= 0)

            headers = dict(self.env.conn.response.getheaders())
            if format_type == 'json':
                self.assertEqual(headers['content-type'],
                                 'application/json; charset=utf-8')
            elif format_type == 'xml':
                self.assertEqual(headers['content-type'],
                                 'application/xml; charset=utf-8')

    def testListingLimit(self):
        limit = load_constraint('account_listing_limit')
        for l in (1, 100, limit / 2, limit - 1, limit, limit + 1, limit * 2):
            p = {'limit': l}

            if l <= limit:
                self.assertTrue(len(self.env.account.containers(parms=p)) <= l)
                self.assert_status(200)
            else:
                self.assertRaises(ResponseError,
                                  self.env.account.containers, parms=p)
                self.assert_status(412)

    def testContainerListing(self):
        a = sorted([c.name for c in self.env.containers])

        for format_type in [None, 'json', 'xml']:
            b = self.env.account.containers(parms={'format': format_type})

            if isinstance(b[0], dict):
                b = [x['name'] for x in b]

            self.assertEqual(a, b)

    def testInvalidAuthToken(self):
        hdrs = {'X-Auth-Token': 'bogus_auth_token'}
        self.assertRaises(ResponseError, self.env.account.info, hdrs=hdrs)
        self.assert_status(401)

    def testLastContainerMarker(self):
        for format_type in [None, 'json', 'xml']:
            containers = self.env.account.containers({'format': format_type})
            self.assertEqual(len(containers), len(self.env.containers))
            self.assert_status(200)

            containers = self.env.account.containers(
                parms={'format': format_type, 'marker': containers[-1]})
            self.assertEqual(len(containers), 0)
            if format_type is None:
                self.assert_status(204)
            else:
                self.assert_status(200)

    def testMarkerLimitContainerList(self):
        for format_type in [None, 'json', 'xml']:
            for marker in ['0', 'A', 'I', 'R', 'Z', 'a', 'i', 'r', 'z',
                           'abc123', 'mnop', 'xyz']:

                limit = random.randint(2, 9)
                containers = self.env.account.containers(
                    parms={'format': format_type,
                           'marker': marker,
                           'limit': limit})
                self.assertTrue(len(containers) <= limit)
                if containers:
                    if isinstance(containers[0], dict):
                        containers = [x['name'] for x in containers]
                    self.assertTrue(locale.strcoll(containers[0], marker) > 0)

    def testContainersOrderedByName(self):
        for format_type in [None, 'json', 'xml']:
            containers = self.env.account.containers(
                parms={'format': format_type})
            if isinstance(containers[0], dict):
                containers = [x['name'] for x in containers]
            self.assertEqual(sorted(containers, cmp=locale.strcoll),
                             containers)

    def testQuotedWWWAuthenticateHeader(self):
        # check that the www-authenticate header value with the swift realm
        # is correctly quoted.
        conn = Connection(tf.config)
        conn.authenticate()
        inserted_html = '<b>Hello World'
        hax = 'AUTH_haxx"\nContent-Length: %d\n\n%s' % (len(inserted_html),
                                                        inserted_html)
        quoted_hax = urllib.quote(hax)
        conn.connection.request('GET', '/v1/' + quoted_hax, None, {})
        resp = conn.connection.getresponse()
        resp_headers = dict(resp.getheaders())
        self.assertIn('www-authenticate', resp_headers)
        actual = resp_headers['www-authenticate']
        expected = 'Swift realm="%s"' % quoted_hax
        # other middleware e.g. auth_token may also set www-authenticate
        # headers in which case actual values will be a comma separated list.
        # check that expected value is among the actual values
        self.assertIn(expected, actual)


class TestAccountUTF8(Base2, TestAccount):
    set_up = False


class TestAccountNoContainersEnv(object):
    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.account.delete_containers()


class TestAccountNoContainers(Base):
    env = TestAccountNoContainersEnv
    set_up = False

    def testGetRequest(self):
        for format_type in [None, 'json', 'xml']:
            self.assertFalse(self.env.account.containers(
                parms={'format': format_type}))

            if format_type is None:
                self.assert_status(204)
            else:
                self.assert_status(200)


class TestAccountNoContainersUTF8(Base2, TestAccountNoContainers):
    set_up = False


class TestContainerEnv(object):
    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.account.delete_containers()

        cls.container = cls.account.container(Utils.create_name())
        if not cls.container.create():
            raise ResponseError(cls.conn.response)

        cls.file_count = 10
        cls.file_size = 128
        cls.files = list()
        for x in range(cls.file_count):
            file_item = cls.container.file(Utils.create_name())
            file_item.write_random(cls.file_size)
            cls.files.append(file_item.name)


class TestContainerDev(Base):
    env = TestContainerEnv
    set_up = False


class TestContainerDevUTF8(Base2, TestContainerDev):
    set_up = False


class TestContainer(Base):
    env = TestContainerEnv
    set_up = False

    def testContainerNameLimit(self):
	raise SkipTest('SOF constraints middleware enforces constraints.')
        limit = load_constraint('max_container_name_length')

        for l in (limit - 100, limit - 10, limit - 1, limit,
                  limit + 1, limit + 10, limit + 100):
            cont = self.env.account.container('a' * l)
            if l <= limit:
                self.assertTrue(cont.create())
                self.assert_status(201)
            else:
                self.assertFalse(cont.create())
                self.assert_status(400)

    def testFileThenContainerDelete(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())
        file_item = cont.file(Utils.create_name())
        self.assertTrue(file_item.write_random())

        self.assertTrue(file_item.delete())
        self.assert_status(204)
        self.assertNotIn(file_item.name, cont.files())

        self.assertTrue(cont.delete())
        self.assert_status(204)
        self.assertNotIn(cont.name, self.env.account.containers())

    def testFileListingLimitMarkerPrefix(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())

        files = sorted([Utils.create_name() for x in range(10)])
        for f in files:
            file_item = cont.file(f)
            self.assertTrue(file_item.write_random())

        for i in range(len(files)):
            f = files[i]
            for j in range(1, len(files) - i):
                self.assertTrue(
                    cont.files(parms={'limit': j, 'marker': f}) ==
                    files[i + 1: i + j + 1])
            self.assertTrue(cont.files(parms={'marker': f}) == files[i + 1:])
            self.assertTrue(cont.files(parms={'marker': f, 'prefix': f}) == [])
            self.assertTrue(cont.files(parms={'prefix': f}) == [f])

    def testPrefixAndLimit(self):
        load_constraint('container_listing_limit')
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())

        prefix_file_count = 10
        limit_count = 2
        prefixs = ['alpha/', 'beta/', 'kappa/']
        prefix_files = {}

        for prefix in prefixs:
            prefix_files[prefix] = []

            for i in range(prefix_file_count):
                file_item = cont.file(prefix + Utils.create_name())
                file_item.write()
                prefix_files[prefix].append(file_item.name)

        for format_type in [None, 'json', 'xml']:
            for prefix in prefixs:
                files = cont.files(parms={'prefix': prefix})
                self.assertEqual(files, sorted(prefix_files[prefix]))

        for format_type in [None, 'json', 'xml']:
            for prefix in prefixs:
                files = cont.files(parms={'limit': limit_count,
                                   'prefix': prefix})
                self.assertEqual(len(files), limit_count)

                for file_item in files:
                    self.assertTrue(file_item.startswith(prefix))

    def testListDelimiter(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())

        delimiter = '-'
        files = ['test', delimiter.join(['test', 'bar']),
                 delimiter.join(['test', 'foo'])]
        for f in files:
            file_item = cont.file(f)
            self.assertTrue(file_item.write_random())

        results = cont.files()
        results = cont.files(parms={'delimiter': delimiter})
        self.assertEqual(results, ['test', 'test-'])

    def testListDelimiterAndPrefix(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())

        delimiter = 'a'
        files = ['bar', 'bazar']
        for f in files:
            file_item = cont.file(f)
            self.assertTrue(file_item.write_random())

        results = cont.files(parms={'delimiter': delimiter, 'prefix': 'ba'})
        self.assertEqual(results, ['bar', 'baza'])

    def testCreate(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())
        self.assert_status(201)
        self.assertIn(cont.name, self.env.account.containers())

    def testContainerFileListOnContainerThatDoesNotExist(self):
        for format_type in [None, 'json', 'xml']:
            container = self.env.account.container(Utils.create_name())
            self.assertRaises(ResponseError, container.files,
                              parms={'format': format_type})
            self.assert_status(404)

    def testUtf8Container(self):
        valid_utf8 = Utils.create_utf8_name()
        invalid_utf8 = valid_utf8[::-1]
        container = self.env.account.container(valid_utf8)
        self.assertTrue(container.create(cfg={'no_path_quote': True}))
        self.assertIn(container.name, self.env.account.containers())
        self.assertEqual(container.files(), [])
        self.assertTrue(container.delete())

        container = self.env.account.container(invalid_utf8)
        self.assertFalse(container.create(cfg={'no_path_quote': True}))
        self.assert_status(412)
        self.assertRaises(ResponseError, container.files,
                          cfg={'no_path_quote': True})
        self.assert_status(412)

    def testCreateOnExisting(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())
        self.assert_status(201)
        self.assertTrue(cont.create())
        self.assert_status(202)

    def testSlashInName(self):
        if Utils.create_name == Utils.create_utf8_name:
            cont_name = list(unicode(Utils.create_name(), 'utf-8'))
        else:
            cont_name = list(Utils.create_name())

        cont_name[random.randint(2, len(cont_name) - 2)] = '/'
        cont_name = ''.join(cont_name)

        if Utils.create_name == Utils.create_utf8_name:
            cont_name = cont_name.encode('utf-8')

        cont = self.env.account.container(cont_name)
        self.assertFalse(cont.create(cfg={'no_path_quote': True}),
                         'created container with name %s' % (cont_name))
        self.assert_status(404)
        self.assertNotIn(cont.name, self.env.account.containers())

    def testDelete(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())
        self.assert_status(201)
        self.assertTrue(cont.delete())
        self.assert_status(204)
        self.assertNotIn(cont.name, self.env.account.containers())

    def testDeleteOnContainerThatDoesNotExist(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertFalse(cont.delete())
        self.assert_status(404)

    def testDeleteOnContainerWithFiles(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertTrue(cont.create())
        file_item = cont.file(Utils.create_name())
        file_item.write_random(self.env.file_size)
        self.assertIn(file_item.name, cont.files())
        self.assertFalse(cont.delete())
        self.assert_status(409)

    def testFileCreateInContainerThatDoesNotExist(self):
        file_item = File(self.env.conn, self.env.account, Utils.create_name(),
                         Utils.create_name())
        self.assertRaises(ResponseError, file_item.write)
        self.assert_status(404)

    def testLastFileMarker(self):
        for format_type in [None, 'json', 'xml']:
            files = self.env.container.files({'format': format_type})
            self.assertEqual(len(files), len(self.env.files))
            self.assert_status(200)

            files = self.env.container.files(
                parms={'format': format_type, 'marker': files[-1]})
            self.assertEqual(len(files), 0)

            if format_type is None:
                self.assert_status(204)
            else:
                self.assert_status(200)

    def testContainerFileList(self):
        for format_type in [None, 'json', 'xml']:
            files = self.env.container.files(parms={'format': format_type})
            self.assert_status(200)
            if isinstance(files[0], dict):
                files = [x['name'] for x in files]

            for file_item in self.env.files:
                self.assertIn(file_item, files)

            for file_item in files:
                self.assertIn(file_item, self.env.files)

    def testMarkerLimitFileList(self):
        for format_type in [None, 'json', 'xml']:
            for marker in ['0', 'A', 'I', 'R', 'Z', 'a', 'i', 'r', 'z',
                           'abc123', 'mnop', 'xyz']:
                limit = random.randint(2, self.env.file_count - 1)
                files = self.env.container.files(parms={'format': format_type,
                                                        'marker': marker,
                                                        'limit': limit})

                if not files:
                    continue

                if isinstance(files[0], dict):
                    files = [x['name'] for x in files]

                self.assertTrue(len(files) <= limit)
                if files:
                    if isinstance(files[0], dict):
                        files = [x['name'] for x in files]
                    self.assertTrue(locale.strcoll(files[0], marker) > 0)

    def testFileOrder(self):
        for format_type in [None, 'json', 'xml']:
            files = self.env.container.files(parms={'format': format_type})
            if isinstance(files[0], dict):
                files = [x['name'] for x in files]
            self.assertEqual(sorted(files, cmp=locale.strcoll), files)

    def testContainerInfo(self):
        info = self.env.container.info()
        self.assert_status(204)
        self.assertEqual(info['object_count'], self.env.file_count)
        self.assertEqual(info['bytes_used'],
                         self.env.file_count * self.env.file_size)

    def testContainerInfoOnContainerThatDoesNotExist(self):
        container = self.env.account.container(Utils.create_name())
        self.assertRaises(ResponseError, container.info)
        self.assert_status(404)

    def testContainerFileListWithLimit(self):
        for format_type in [None, 'json', 'xml']:
            files = self.env.container.files(parms={'format': format_type,
                                                    'limit': 2})
            self.assertEqual(len(files), 2)

    def testTooLongName(self):
        cont = self.env.account.container('x' * 257)
        self.assertFalse(cont.create(),
                         'created container with name %s' % (cont.name))
        self.assert_status(400)

    def testContainerExistenceCachingProblem(self):
        cont = self.env.account.container(Utils.create_name())
        self.assertRaises(ResponseError, cont.files)
        self.assertTrue(cont.create())
        cont.files()

        cont = self.env.account.container(Utils.create_name())
        self.assertRaises(ResponseError, cont.files)
        self.assertTrue(cont.create())
        file_item = cont.file(Utils.create_name())
        file_item.write_random()


class TestContainerUTF8(Base2, TestContainer):
    set_up = False


class TestContainerPathsEnv(object):
    @classmethod
    def setUp(cls):
	raise SkipTest('Objects ending in / are not supported')
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.account.delete_containers()

        cls.file_size = 8

        cls.container = cls.account.container(Utils.create_name())
        if not cls.container.create():
            raise ResponseError(cls.conn.response)

        cls.files = [
            '/file1',
            '/file A',
            '/dir1/',
            '/dir2/',
            '/dir1/file2',
            '/dir1/subdir1/',
            '/dir1/subdir2/',
            '/dir1/subdir1/file2',
            '/dir1/subdir1/file3',
            '/dir1/subdir1/file4',
            '/dir1/subdir1/subsubdir1/',
            '/dir1/subdir1/subsubdir1/file5',
            '/dir1/subdir1/subsubdir1/file6',
            '/dir1/subdir1/subsubdir1/file7',
            '/dir1/subdir1/subsubdir1/file8',
            '/dir1/subdir1/subsubdir2/',
            '/dir1/subdir1/subsubdir2/file9',
            '/dir1/subdir1/subsubdir2/file0',
            'file1',
            'dir1/',
            'dir2/',
            'dir1/file2',
            'dir1/subdir1/',
            'dir1/subdir2/',
            'dir1/subdir1/file2',
            'dir1/subdir1/file3',
            'dir1/subdir1/file4',
            'dir1/subdir1/subsubdir1/',
            'dir1/subdir1/subsubdir1/file5',
            'dir1/subdir1/subsubdir1/file6',
            'dir1/subdir1/subsubdir1/file7',
            'dir1/subdir1/subsubdir1/file8',
            'dir1/subdir1/subsubdir2/',
            'dir1/subdir1/subsubdir2/file9',
            'dir1/subdir1/subsubdir2/file0',
            'dir1/subdir with spaces/',
            'dir1/subdir with spaces/file B',
            'dir1/subdir+with{whatever/',
            'dir1/subdir+with{whatever/file D',
        ]

        stored_files = set()
        for f in cls.files:
            file_item = cls.container.file(f)
            if f.endswith('/'):
                file_item.write(hdrs={'Content-Type': 'application/directory'})
            else:
                file_item.write_random(cls.file_size,
                                       hdrs={'Content-Type':
                                             'application/directory'})
            if (normalized_urls):
                nfile = '/'.join(filter(None, f.split('/')))
                if (f[-1] == '/'):
                    nfile += '/'
                stored_files.add(nfile)
            else:
                stored_files.add(f)
        cls.stored_files = sorted(stored_files)


class TestContainerPaths(Base):
    env = TestContainerPathsEnv
    set_up = False

    def testTraverseContainer(self):
        found_files = []
        found_dirs = []

        def recurse_path(path, count=0):
            if count > 10:
                raise ValueError('too deep recursion')

            for file_item in self.env.container.files(parms={'path': path}):
                self.assertTrue(file_item.startswith(path))
                if file_item.endswith('/'):
                    recurse_path(file_item, count + 1)
                    found_dirs.append(file_item)
                else:
                    found_files.append(file_item)

        recurse_path('')
        for file_item in self.env.stored_files:
            if file_item.startswith('/'):
                self.assertNotIn(file_item, found_dirs)
                self.assertNotIn(file_item, found_files)
            elif file_item.endswith('/'):
                self.assertIn(file_item, found_dirs)
                self.assertNotIn(file_item, found_files)
            else:
                self.assertIn(file_item, found_files)
                self.assertNotIn(file_item, found_dirs)

        found_files = []
        found_dirs = []
        recurse_path('/')
        for file_item in self.env.stored_files:
            if not file_item.startswith('/'):
                self.assertNotIn(file_item, found_dirs)
                self.assertNotIn(file_item, found_files)
            elif file_item.endswith('/'):
                self.assertIn(file_item, found_dirs)
                self.assertNotIn(file_item, found_files)
            else:
                self.assertIn(file_item, found_files)
                self.assertNotIn(file_item, found_dirs)

    def testContainerListing(self):
        for format_type in (None, 'json', 'xml'):
            files = self.env.container.files(parms={'format': format_type})

            if isinstance(files[0], dict):
                files = [str(x['name']) for x in files]

            self.assertEqual(files, self.env.stored_files)

        for format_type in ('json', 'xml'):
            for file_item in self.env.container.files(parms={'format':
                                                             format_type}):
                self.assertTrue(int(file_item['bytes']) >= 0)
                self.assertIn('last_modified', file_item)
                if file_item['name'].endswith('/'):
                    self.assertEqual(file_item['content_type'],
                                     'application/directory')

    def testStructure(self):
        def assert_listing(path, file_list):
            files = self.env.container.files(parms={'path': path})
            self.assertEqual(sorted(file_list, cmp=locale.strcoll), files)
        if not normalized_urls:
            assert_listing('/', ['/dir1/', '/dir2/', '/file1', '/file A'])
            assert_listing('/dir1',
                           ['/dir1/file2', '/dir1/subdir1/', '/dir1/subdir2/'])
            assert_listing('/dir1/',
                           ['/dir1/file2', '/dir1/subdir1/', '/dir1/subdir2/'])
            assert_listing('/dir1/subdir1',
                           ['/dir1/subdir1/subsubdir2/', '/dir1/subdir1/file2',
                            '/dir1/subdir1/file3', '/dir1/subdir1/file4',
                            '/dir1/subdir1/subsubdir1/'])
            assert_listing('/dir1/subdir2', [])
            assert_listing('', ['file1', 'dir1/', 'dir2/'])
        else:
            assert_listing('', ['file1', 'dir1/', 'dir2/', 'file A'])
        assert_listing('dir1', ['dir1/file2', 'dir1/subdir1/',
                                'dir1/subdir2/', 'dir1/subdir with spaces/',
                                'dir1/subdir+with{whatever/'])
        assert_listing('dir1/subdir1',
                       ['dir1/subdir1/file4', 'dir1/subdir1/subsubdir2/',
                        'dir1/subdir1/file2', 'dir1/subdir1/file3',
                        'dir1/subdir1/subsubdir1/'])
        assert_listing('dir1/subdir1/subsubdir1',
                       ['dir1/subdir1/subsubdir1/file7',
                        'dir1/subdir1/subsubdir1/file5',
                        'dir1/subdir1/subsubdir1/file8',
                        'dir1/subdir1/subsubdir1/file6'])
        assert_listing('dir1/subdir1/subsubdir1/',
                       ['dir1/subdir1/subsubdir1/file7',
                        'dir1/subdir1/subsubdir1/file5',
                        'dir1/subdir1/subsubdir1/file8',
                        'dir1/subdir1/subsubdir1/file6'])
        assert_listing('dir1/subdir with spaces/',
                       ['dir1/subdir with spaces/file B'])


class TestFileEnv(object):
    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        # creating another account and connection
        # for account to account copy tests
        config2 = deepcopy(tf.config)
        config2['account'] = tf.config['account2']
        config2['username'] = tf.config['username2']
        config2['password'] = tf.config['password2']
        cls.conn2 = Connection(config2)
        cls.conn2.authenticate()

        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.account.delete_containers()
        cls.account2 = cls.conn2.get_account()
        cls.account2.delete_containers()

        cls.container = cls.account.container(Utils.create_name())
        if not cls.container.create():
            raise ResponseError(cls.conn.response)

        cls.file_size = 128


class TestFileDev(Base):
    env = TestFileEnv
    set_up = False


class TestFileDevUTF8(Base2, TestFileDev):
    set_up = False


class TestFile(Base):
    env = TestFileEnv
    set_up = False

    def testCopy(self):
        # makes sure to test encoded characters
        source_filename = 'dealde%2Fl04 011e%204c8df/flash.png'
        file_item = self.env.container.file(source_filename)

        metadata = {}
        for i in range(1):
            metadata[Utils.create_ascii_name()] = Utils.create_name()

        data = file_item.write_random()
        file_item.sync_metadata(metadata)

        dest_cont = self.env.account.container(Utils.create_name())
        self.assertTrue(dest_cont.create())

        # copy both from within and across containers
        for cont in (self.env.container, dest_cont):
            # copy both with and without initial slash
            for prefix in ('', '/'):
                dest_filename = Utils.create_name()

                file_item = self.env.container.file(source_filename)
                file_item.copy('%s%s' % (prefix, cont), dest_filename)

                self.assertIn(dest_filename, cont.files())

                file_item = cont.file(dest_filename)

                self.assertTrue(data == file_item.read())
                self.assertTrue(file_item.initialize())
                self.assertTrue(metadata == file_item.metadata)

    def testCopyAccount(self):
        # makes sure to test encoded characters
        source_filename = 'dealde%2Fl04 011e%204c8df/flash.png'
        file_item = self.env.container.file(source_filename)

        metadata = {Utils.create_ascii_name(): Utils.create_name()}

        data = file_item.write_random()
        file_item.sync_metadata(metadata)

        dest_cont = self.env.account.container(Utils.create_name())
        self.assertTrue(dest_cont.create())

        acct = self.env.conn.account_name
        # copy both from within and across containers
        for cont in (self.env.container, dest_cont):
            # copy both with and without initial slash
            for prefix in ('', '/'):
                dest_filename = Utils.create_name()

                file_item = self.env.container.file(source_filename)
                file_item.copy_account(acct,
                                       '%s%s' % (prefix, cont),
                                       dest_filename)

                self.assertIn(dest_filename, cont.files())

                file_item = cont.file(dest_filename)

                self.assertEqual(data, file_item.read())
                self.assertTrue(file_item.initialize())
                self.assertEqual(metadata, file_item.metadata)

        dest_cont = self.env.account2.container(Utils.create_name())
        self.assertTrue(dest_cont.create(hdrs={
            'X-Container-Write': self.env.conn.user_acl
        }))

        acct = self.env.conn2.account_name
        # copy both with and without initial slash
        for prefix in ('', '/'):
            dest_filename = Utils.create_name()

            file_item = self.env.container.file(source_filename)
            file_item.copy_account(acct,
                                   '%s%s' % (prefix, dest_cont),
                                   dest_filename)

            self.assertIn(dest_filename, dest_cont.files())

            file_item = dest_cont.file(dest_filename)

            self.assertTrue(data == file_item.read())
            self.assertTrue(file_item.initialize())
            self.assertTrue(metadata == file_item.metadata)

    def testCopy404s(self):
        source_filename = Utils.create_name()
        file_item = self.env.container.file(source_filename)
        file_item.write_random()

        dest_cont = self.env.account.container(Utils.create_name())
        self.assertTrue(dest_cont.create())

        for prefix in ('', '/'):
            # invalid source container
            source_cont = self.env.account.container(Utils.create_name())
            file_item = source_cont.file(source_filename)
            self.assertFalse(file_item.copy(
                '%s%s' % (prefix, self.env.container),
                Utils.create_name()))
            self.assert_status(404)

            self.assertFalse(file_item.copy('%s%s' % (prefix, dest_cont),
                             Utils.create_name()))
            self.assert_status(404)

            # invalid source object
            file_item = self.env.container.file(Utils.create_name())
            self.assertFalse(file_item.copy(
                '%s%s' % (prefix, self.env.container),
                Utils.create_name()))
            self.assert_status(404)

            self.assertFalse(file_item.copy('%s%s' % (prefix, dest_cont),
                                            Utils.create_name()))
            self.assert_status(404)

            # invalid destination container
            file_item = self.env.container.file(source_filename)
            self.assertTrue(
                not file_item.copy(
                    '%s%s' % (prefix, Utils.create_name()),
                    Utils.create_name()))

    def testCopyAccount404s(self):
        acct = self.env.conn.account_name
        acct2 = self.env.conn2.account_name
        source_filename = Utils.create_name()
        file_item = self.env.container.file(source_filename)
        file_item.write_random()

        dest_cont = self.env.account.container(Utils.create_name())
        self.assertTrue(dest_cont.create(hdrs={
            'X-Container-Read': self.env.conn2.user_acl
        }))
        dest_cont2 = self.env.account2.container(Utils.create_name())
        self.assertTrue(dest_cont2.create(hdrs={
            'X-Container-Write': self.env.conn.user_acl,
            'X-Container-Read': self.env.conn.user_acl
        }))

        for acct, cont in ((acct, dest_cont), (acct2, dest_cont2)):
            for prefix in ('', '/'):
                # invalid source container
                source_cont = self.env.account.container(Utils.create_name())
                file_item = source_cont.file(source_filename)
                self.assertFalse(file_item.copy_account(
                    acct,
                    '%s%s' % (prefix, self.env.container),
                    Utils.create_name()))
                if acct == acct2:
                    # there is no such source container
                    # and foreign user can have no permission to read it
                    self.assert_status(403)
                else:
                    self.assert_status(404)

                self.assertFalse(file_item.copy_account(
                    acct,
                    '%s%s' % (prefix, cont),
                    Utils.create_name()))
                self.assert_status(404)

                # invalid source object
                file_item = self.env.container.file(Utils.create_name())
                self.assertFalse(file_item.copy_account(
                    acct,
                    '%s%s' % (prefix, self.env.container),
                    Utils.create_name()))
                if acct == acct2:
                    # there is no such object
                    # and foreign user can have no permission to read it
                    self.assert_status(403)
                else:
                    self.assert_status(404)

                self.assertFalse(file_item.copy_account(
                    acct,
                    '%s%s' % (prefix, cont),
                    Utils.create_name()))
                self.assert_status(404)

                # invalid destination container
                file_item = self.env.container.file(source_filename)
                self.assertFalse(file_item.copy_account(
                    acct,
                    '%s%s' % (prefix, Utils.create_name()),
                    Utils.create_name()))
                if acct == acct2:
                    # there is no such destination container
                    # and foreign user can have no permission to write there
                    self.assert_status(403)
                else:
                    self.assert_status(404)

    def testCopyNoDestinationHeader(self):
        source_filename = Utils.create_name()
        file_item = self.env.container.file(source_filename)
        file_item.write_random()

        file_item = self.env.container.file(source_filename)
        self.assertFalse(file_item.copy(Utils.create_name(),
                         Utils.create_name(),
                         cfg={'no_destination': True}))
        self.assert_status(412)

    def testCopyDestinationSlashProblems(self):
        source_filename = Utils.create_name()
        file_item = self.env.container.file(source_filename)
        file_item.write_random()

        # no slash
        self.assertFalse(file_item.copy(Utils.create_name(),
                         Utils.create_name(),
                         cfg={'destination': Utils.create_name()}))
        self.assert_status(412)

    def testCopyFromHeader(self):
        source_filename = Utils.create_name()
        file_item = self.env.container.file(source_filename)

        metadata = {}
        for i in range(1):
            metadata[Utils.create_ascii_name()] = Utils.create_name()
        file_item.metadata = metadata

        data = file_item.write_random()

        dest_cont = self.env.account.container(Utils.create_name())
        self.assertTrue(dest_cont.create())

        # copy both from within and across containers
        for cont in (self.env.container, dest_cont):
            # copy both with and without initial slash
            for prefix in ('', '/'):
                dest_filename = Utils.create_name()

                file_item = cont.file(dest_filename)
                file_item.write(hdrs={'X-Copy-From': '%s%s/%s' % (
                    prefix, self.env.container.name, source_filename)})

                self.assertIn(dest_filename, cont.files())

                file_item = cont.file(dest_filename)

                self.assertTrue(data == file_item.read())
                self.assertTrue(file_item.initialize())
                self.assertTrue(metadata == file_item.metadata)

    def testCopyFromAccountHeader(self):
        acct = self.env.conn.account_name
        src_cont = self.env.account.container(Utils.create_name())
        self.assertTrue(src_cont.create(hdrs={
            'X-Container-Read': self.env.conn2.user_acl
        }))
        source_filename = Utils.create_name()
        file_item = src_cont.file(source_filename)

        metadata = {}
        for i in range(1):
            metadata[Utils.create_ascii_name()] = Utils.create_name()
        file_item.metadata = metadata

        data = file_item.write_random()

        dest_cont = self.env.account.container(Utils.create_name())
        self.assertTrue(dest_cont.create())
        dest_cont2 = self.env.account2.container(Utils.create_name())
        self.assertTrue(dest_cont2.create(hdrs={
            'X-Container-Write': self.env.conn.user_acl
        }))

        for cont in (src_cont, dest_cont, dest_cont2):
            # copy both with and without initial slash
            for prefix in ('', '/'):
                dest_filename = Utils.create_name()

                file_item = cont.file(dest_filename)
                file_item.write(hdrs={'X-Copy-From-Account': acct,
                                      'X-Copy-From': '%s%s/%s' % (
                                          prefix,
                                          src_cont.name,
                                          source_filename)})

                self.assertIn(dest_filename, cont.files())

                file_item = cont.file(dest_filename)

                self.assertTrue(data == file_item.read())
                self.assertTrue(file_item.initialize())
                self.assertTrue(metadata == file_item.metadata)

    def testCopyFromHeader404s(self):
        source_filename = Utils.create_name()
        file_item = self.env.container.file(source_filename)
        file_item.write_random()

        for prefix in ('', '/'):
            # invalid source container
            file_item = self.env.container.file(Utils.create_name())
            copy_from = ('%s%s/%s'
                         % (prefix, Utils.create_name(), source_filename))
            self.assertRaises(ResponseError, file_item.write,
                              hdrs={'X-Copy-From': copy_from})
            self.assert_status(404)

            # invalid source object
            copy_from = ('%s%s/%s'
                         % (prefix, self.env.container.name,
                            Utils.create_name()))
            file_item = self.env.container.file(Utils.create_name())
            self.assertRaises(ResponseError, file_item.write,
                              hdrs={'X-Copy-From': copy_from})
            self.assert_status(404)

            # invalid destination container
            dest_cont = self.env.account.container(Utils.create_name())
            file_item = dest_cont.file(Utils.create_name())
            copy_from = ('%s%s/%s'
                         % (prefix, self.env.container.name, source_filename))
            self.assertRaises(ResponseError, file_item.write,
                              hdrs={'X-Copy-From': copy_from})
            self.assert_status(404)

    def testCopyFromAccountHeader404s(self):
        acct = self.env.conn2.account_name
        src_cont = self.env.account2.container(Utils.create_name())
        self.assertTrue(src_cont.create(hdrs={
            'X-Container-Read': self.env.conn.user_acl
        }))
        source_filename = Utils.create_name()
        file_item = src_cont.file(source_filename)
        file_item.write_random()
        dest_cont = self.env.account.container(Utils.create_name())
        self.assertTrue(dest_cont.create())

        for prefix in ('', '/'):
            # invalid source container
            file_item = dest_cont.file(Utils.create_name())
            self.assertRaises(ResponseError, file_item.write,
                              hdrs={'X-Copy-From-Account': acct,
                                    'X-Copy-From': '%s%s/%s' %
                                                   (prefix,
                                                    Utils.create_name(),
                                                    source_filename)})
            # looks like cached responses leak "not found"
            # to un-authorized users, not going to fix it now, but...
            self.assert_status([403, 404])

            # invalid source object
            file_item = self.env.container.file(Utils.create_name())
            self.assertRaises(ResponseError, file_item.write,
                              hdrs={'X-Copy-From-Account': acct,
                                    'X-Copy-From': '%s%s/%s' %
                                                   (prefix,
                                                    src_cont,
                                                    Utils.create_name())})
            self.assert_status(404)

            # invalid destination container
            dest_cont = self.env.account.container(Utils.create_name())
            file_item = dest_cont.file(Utils.create_name())
            self.assertRaises(ResponseError, file_item.write,
                              hdrs={'X-Copy-From-Account': acct,
                                    'X-Copy-From': '%s%s/%s' %
                                                   (prefix,
                                                    src_cont,
                                                    source_filename)})
            self.assert_status(404)

    def testNameLimit(self):
	raise SkipTest('SOF constraints middleware enforces constraints.')
        limit = load_constraint('max_object_name_length')

        for l in (1, 10, limit / 2, limit - 1, limit, limit + 1, limit * 2):
            file_item = self.env.container.file('a' * l)

            if l <= limit:
                self.assertTrue(file_item.write())
                self.assert_status(201)
            else:
                self.assertRaises(ResponseError, file_item.write)
                self.assert_status(400)

    def testQuestionMarkInName(self):
        if Utils.create_name == Utils.create_ascii_name:
            file_name = list(Utils.create_name())
            file_name[random.randint(2, len(file_name) - 2)] = '?'
            file_name = "".join(file_name)
        else:
            file_name = Utils.create_name(6) + '?' + Utils.create_name(6)

        file_item = self.env.container.file(file_name)
        self.assertTrue(file_item.write(cfg={'no_path_quote': True}))
        self.assertNotIn(file_name, self.env.container.files())
        self.assertIn(file_name.split('?')[0], self.env.container.files())

    def testDeleteThen404s(self):
        file_item = self.env.container.file(Utils.create_name())
        self.assertTrue(file_item.write_random())
        self.assert_status(201)

        self.assertTrue(file_item.delete())
        self.assert_status(204)

        file_item.metadata = {Utils.create_ascii_name(): Utils.create_name()}

        for method in (file_item.info,
                       file_item.read,
                       file_item.sync_metadata,
                       file_item.delete):
            self.assertRaises(ResponseError, method)
            self.assert_status(404)

    def testBlankMetadataName(self):
        file_item = self.env.container.file(Utils.create_name())
        file_item.metadata = {'': Utils.create_name()}
        self.assertRaises(ResponseError, file_item.write_random)
        self.assert_status(400)

    def testMetadataNumberLimit(self):
	raise SkipTest("Bad test")
        # TODO(ppai): Fix it in upstream swift first
        # Refer to comments below
        number_limit = load_constraint('max_meta_count')
        size_limit = load_constraint('max_meta_overall_size')

        for i in (number_limit - 10, number_limit - 1, number_limit,
                  number_limit + 1, number_limit + 10, number_limit + 100):

            j = size_limit / (i * 2)

            size = 0
            metadata = {}
            while len(metadata.keys()) < i:
                key = Utils.create_ascii_name()
		# The following line returns a valid utf8 byte sequence
                val = Utils.create_name()

                if len(key) > j:
                    key = key[:j]
		    # This slicing done below can make the 'utf8' byte
                    # sequence invalid and hence it cannot be decoded.
                    val = val[:j]

                size += len(key) + len(val)
                metadata[key] = val

            file_item = self.env.container.file(Utils.create_name())
            file_item.metadata = metadata

            if i <= number_limit:
                self.assertTrue(file_item.write())
                self.assert_status(201)
                self.assertTrue(file_item.sync_metadata())
                self.assert_status((201, 202))
            else:
                self.assertRaises(ResponseError, file_item.write)
                self.assert_status(400)
                file_item.metadata = {}
                self.assertTrue(file_item.write())
                self.assert_status(201)
                file_item.metadata = metadata
                self.assertRaises(ResponseError, file_item.sync_metadata)
                self.assert_status(400)

    def testContentTypeGuessing(self):
        file_types = {'wav': 'audio/x-wav', 'txt': 'text/plain',
                      'zip': 'application/zip'}

        container = self.env.account.container(Utils.create_name())
        self.assertTrue(container.create())

        for i in file_types.keys():
            file_item = container.file(Utils.create_name() + '.' + i)
            file_item.write('', cfg={'no_content_type': True})

        file_types_read = {}
        for i in container.files(parms={'format': 'json'}):
            file_types_read[i['name'].split('.')[1]] = i['content_type']

        self.assertEqual(file_types, file_types_read)

    def testRangedGets(self):
        # We set the file_length to a strange multiple here. This is to check
        # that ranges still work in the EC case when the requested range
        # spans EC segment boundaries. The 1 MiB base value is chosen because
        # that's a common EC segment size. The 1.33 multiple is to ensure we
        # aren't aligned on segment boundaries
        file_length = int(1048576 * 1.33)
        range_size = file_length / 10
        file_item = self.env.container.file(Utils.create_name())
        data = file_item.write_random(file_length)

        for i in range(0, file_length, range_size):
            range_string = 'bytes=%d-%d' % (i, i + range_size - 1)
            hdrs = {'Range': range_string}
            self.assertTrue(
                data[i: i + range_size] == file_item.read(hdrs=hdrs),
                range_string)

            range_string = 'bytes=-%d' % (i)
            hdrs = {'Range': range_string}
            if i == 0:
                # RFC 2616 14.35.1
                # "If a syntactically valid byte-range-set includes ... at
                # least one suffix-byte-range-spec with a NON-ZERO
                # suffix-length, then the byte-range-set is satisfiable.
                # Otherwise, the byte-range-set is unsatisfiable.
                self.assertRaises(ResponseError, file_item.read, hdrs=hdrs)
                self.assert_status(416)
            else:
                self.assertEqual(file_item.read(hdrs=hdrs), data[-i:])

            range_string = 'bytes=%d-' % (i)
            hdrs = {'Range': range_string}
            self.assertTrue(
                file_item.read(hdrs=hdrs) == data[i - file_length:],
                range_string)

        range_string = 'bytes=%d-%d' % (file_length + 1000, file_length + 2000)
        hdrs = {'Range': range_string}
        self.assertRaises(ResponseError, file_item.read, hdrs=hdrs)
        self.assert_status(416)

        range_string = 'bytes=%d-%d' % (file_length - 1000, file_length + 2000)
        hdrs = {'Range': range_string}
        self.assertTrue(
            file_item.read(hdrs=hdrs) == data[-1000:], range_string)

        hdrs = {'Range': '0-4'}
        self.assertTrue(file_item.read(hdrs=hdrs) == data, range_string)

        # RFC 2616 14.35.1
        # "If the entity is shorter than the specified suffix-length, the
        # entire entity-body is used."
        range_string = 'bytes=-%d' % (file_length + 10)
        hdrs = {'Range': range_string}
        self.assertTrue(file_item.read(hdrs=hdrs) == data, range_string)

    def testRangedGetsWithLWSinHeader(self):
        # Skip this test until webob 1.2 can tolerate LWS in Range header.
        file_length = 10000
        file_item = self.env.container.file(Utils.create_name())
        data = file_item.write_random(file_length)

        for r in ('BYTES=0-999', 'bytes = 0-999', 'BYTES = 0 - 999',
                  'bytes = 0 - 999', 'bytes=0 - 999', 'bytes=0-999 '):

            self.assertTrue(file_item.read(hdrs={'Range': r}) == data[0:1000])

    def testFileSizeLimit(self):
        limit = load_constraint('max_file_size')
        tsecs = 3

        def timeout(seconds, method, *args, **kwargs):
            try:
                with eventlet.Timeout(seconds):
                    method(*args, **kwargs)
            except eventlet.Timeout:
                return True
            else:
                return False

        for i in (limit - 100, limit - 10, limit - 1, limit, limit + 1,
                  limit + 10, limit + 100):

            file_item = self.env.container.file(Utils.create_name())

            if i <= limit:
                self.assertTrue(timeout(tsecs, file_item.write,
                                cfg={'set_content_length': i}))
            else:
                self.assertRaises(ResponseError, timeout, tsecs,
                                  file_item.write,
                                  cfg={'set_content_length': i})

    def testNoContentLengthForPut(self):
        file_item = self.env.container.file(Utils.create_name())
        self.assertRaises(ResponseError, file_item.write, 'testing',
                          cfg={'no_content_length': True})
        self.assert_status(411)

    def testDelete(self):
        file_item = self.env.container.file(Utils.create_name())
        file_item.write_random(self.env.file_size)

        self.assertIn(file_item.name, self.env.container.files())
        self.assertTrue(file_item.delete())
        self.assertNotIn(file_item.name, self.env.container.files())

    def testBadHeaders(self):
        file_length = 100

        # no content type on puts should be ok
        file_item = self.env.container.file(Utils.create_name())
        file_item.write_random(file_length, cfg={'no_content_type': True})
        self.assert_status(201)

        # content length x
        self.assertRaises(ResponseError, file_item.write_random, file_length,
                          hdrs={'Content-Length': 'X'},
                          cfg={'no_content_length': True})
        self.assert_status(400)

        # no content-length
        self.assertRaises(ResponseError, file_item.write_random, file_length,
                          cfg={'no_content_length': True})
        self.assert_status(411)

        self.assertRaises(ResponseError, file_item.write_random, file_length,
                          hdrs={'transfer-encoding': 'gzip,chunked'},
                          cfg={'no_content_length': True})
        self.assert_status(501)

        # bad request types
        # for req in ('LICK', 'GETorHEAD_base', 'container_info',
        #             'best_response'):
        for req in ('LICK', 'GETorHEAD_base'):
            self.env.account.conn.make_request(req)
            self.assert_status(405)

        # bad range headers
        self.assertTrue(
            len(file_item.read(hdrs={'Range': 'parsecs=8-12'})) ==
            file_length)
        self.assert_status(200)

    def testMetadataLengthLimits(self):
        key_limit = load_constraint('max_meta_name_length')
        value_limit = load_constraint('max_meta_value_length')
        lengths = [[key_limit, value_limit], [key_limit, value_limit + 1],
                   [key_limit + 1, value_limit], [key_limit, 0],
                   [key_limit, value_limit * 10],
                   [key_limit * 10, value_limit]]

        for l in lengths:
            metadata = {'a' * l[0]: 'b' * l[1]}
            file_item = self.env.container.file(Utils.create_name())
            file_item.metadata = metadata

            if l[0] <= key_limit and l[1] <= value_limit:
                self.assertTrue(file_item.write())
                self.assert_status(201)
                self.assertTrue(file_item.sync_metadata())
            else:
                self.assertRaises(ResponseError, file_item.write)
                self.assert_status(400)
                file_item.metadata = {}
                self.assertTrue(file_item.write())
                self.assert_status(201)
                file_item.metadata = metadata
                self.assertRaises(ResponseError, file_item.sync_metadata)
                self.assert_status(400)

    def testEtagWayoff(self):
        file_item = self.env.container.file(Utils.create_name())
        hdrs = {'etag': 'reallylonganddefinitelynotavalidetagvalue'}
        self.assertRaises(ResponseError, file_item.write_random, hdrs=hdrs)
        self.assert_status(422)

    def testFileCreate(self):
        for i in range(10):
            file_item = self.env.container.file(Utils.create_name())
            data = file_item.write_random()
            self.assert_status(201)
            self.assertTrue(data == file_item.read())
            self.assert_status(200)

    def testHead(self):
        file_name = Utils.create_name()
        content_type = Utils.create_name()

        file_item = self.env.container.file(file_name)
        file_item.content_type = content_type
        file_item.write_random(self.env.file_size)

        md5 = file_item.md5

        file_item = self.env.container.file(file_name)
        info = file_item.info()

        self.assert_status(200)
        self.assertEqual(info['content_length'], self.env.file_size)
        self.assertEqual(info['etag'], md5)
        self.assertEqual(info['content_type'], content_type)
        self.assertIn('last_modified', info)

    def testDeleteOfFileThatDoesNotExist(self):
        # in container that exists
        file_item = self.env.container.file(Utils.create_name())
        self.assertRaises(ResponseError, file_item.delete)
        self.assert_status(404)

        # in container that does not exist
        container = self.env.account.container(Utils.create_name())
        file_item = container.file(Utils.create_name())
        self.assertRaises(ResponseError, file_item.delete)
        self.assert_status(404)

    def testHeadOnFileThatDoesNotExist(self):
        # in container that exists
        file_item = self.env.container.file(Utils.create_name())
        self.assertRaises(ResponseError, file_item.info)
        self.assert_status(404)

        # in container that does not exist
        container = self.env.account.container(Utils.create_name())
        file_item = container.file(Utils.create_name())
        self.assertRaises(ResponseError, file_item.info)
        self.assert_status(404)

    def testMetadataOnPost(self):
        file_item = self.env.container.file(Utils.create_name())
        file_item.write_random(self.env.file_size)

        for i in range(10):
            metadata = {}
            for j in range(10):
                metadata[Utils.create_ascii_name()] = Utils.create_name()

            file_item.metadata = metadata
            self.assertTrue(file_item.sync_metadata())
            self.assert_status((201, 202))

            file_item = self.env.container.file(file_item.name)
            self.assertTrue(file_item.initialize())
            self.assert_status(200)
            self.assertEqual(file_item.metadata, metadata)

    def testGetContentType(self):
        file_name = Utils.create_name()
        content_type = Utils.create_name()

        file_item = self.env.container.file(file_name)
        file_item.content_type = content_type
        file_item.write_random()

        file_item = self.env.container.file(file_name)
        file_item.read()

        self.assertEqual(content_type, file_item.content_type)

    def testGetOnFileThatDoesNotExist(self):
        # in container that exists
        file_item = self.env.container.file(Utils.create_name())
        self.assertRaises(ResponseError, file_item.read)
        self.assert_status(404)

        # in container that does not exist
        container = self.env.account.container(Utils.create_name())
        file_item = container.file(Utils.create_name())
        self.assertRaises(ResponseError, file_item.read)
        self.assert_status(404)

    def testPostOnFileThatDoesNotExist(self):
        # in container that exists
        file_item = self.env.container.file(Utils.create_name())
        file_item.metadata['Field'] = 'Value'
        self.assertRaises(ResponseError, file_item.sync_metadata)
        self.assert_status(404)

        # in container that does not exist
        container = self.env.account.container(Utils.create_name())
        file_item = container.file(Utils.create_name())
        file_item.metadata['Field'] = 'Value'
        self.assertRaises(ResponseError, file_item.sync_metadata)
        self.assert_status(404)

    def testMetadataOnPut(self):
        for i in range(10):
            metadata = {}
            for j in range(10):
                metadata[Utils.create_ascii_name()] = Utils.create_name()

            file_item = self.env.container.file(Utils.create_name())
            file_item.metadata = metadata
            file_item.write_random(self.env.file_size)

            file_item = self.env.container.file(file_item.name)
            self.assertTrue(file_item.initialize())
            self.assert_status(200)
            self.assertEqual(file_item.metadata, metadata)

    def testSerialization(self):
        container = self.env.account.container(Utils.create_name())
        self.assertTrue(container.create())

        files = []
        for i in (0, 1, 10, 100, 1000, 10000):
            files.append({'name': Utils.create_name(),
                          'content_type': Utils.create_name(), 'bytes': i})

        write_time = time.time()
        for f in files:
            file_item = container.file(f['name'])
            file_item.content_type = f['content_type']
            file_item.write_random(f['bytes'])

            f['hash'] = file_item.md5
            f['json'] = False
            f['xml'] = False
        write_time = time.time() - write_time

        for format_type in ['json', 'xml']:
            for file_item in container.files(parms={'format': format_type}):
                found = False
                for f in files:
                    if f['name'] != file_item['name']:
                        continue

                    self.assertEqual(file_item['content_type'],
                                     f['content_type'])
                    self.assertEqual(int(file_item['bytes']), f['bytes'])

                    d = datetime.strptime(
                        file_item['last_modified'].split('.')[0],
                        "%Y-%m-%dT%H:%M:%S")
                    lm = time.mktime(d.timetuple())

                    if 'last_modified' in f:
                        self.assertEqual(f['last_modified'], lm)
                    else:
                        f['last_modified'] = lm

                    f[format_type] = True
                    found = True

                self.assertTrue(
                    found, 'Unexpected file %s found in '
                    '%s listing' % (file_item['name'], format_type))

            headers = dict(self.env.conn.response.getheaders())
            if format_type == 'json':
                self.assertEqual(headers['content-type'],
                                 'application/json; charset=utf-8')
            elif format_type == 'xml':
                self.assertEqual(headers['content-type'],
                                 'application/xml; charset=utf-8')

        lm_diff = max([f['last_modified'] for f in files]) -\
            min([f['last_modified'] for f in files])
        self.assertTrue(
            lm_diff < write_time + 1, 'Diff in last '
            'modified times should be less than time to write files')

        for f in files:
            for format_type in ['json', 'xml']:
                self.assertTrue(
                    f[format_type], 'File %s not found in %s listing'
                    % (f['name'], format_type))

    def testStackedOverwrite(self):
        file_item = self.env.container.file(Utils.create_name())

        for i in range(1, 11):
            data = file_item.write_random(512)
            file_item.write(data)

        self.assertTrue(file_item.read() == data)

    def testTooLongName(self):
        file_item = self.env.container.file('x' * 1025)
        self.assertRaises(ResponseError, file_item.write)
        self.assert_status(400)

    def testZeroByteFile(self):
        file_item = self.env.container.file(Utils.create_name())

        self.assertTrue(file_item.write(''))
        self.assertIn(file_item.name, self.env.container.files())
        self.assertTrue(file_item.read() == '')

    def testEtagResponse(self):
        file_item = self.env.container.file(Utils.create_name())

        data = six.StringIO(file_item.write_random(512))
        etag = File.compute_md5sum(data)

        headers = dict(self.env.conn.response.getheaders())
        self.assertIn('etag', headers.keys())

        header_etag = headers['etag'].strip('"')
        self.assertEqual(etag, header_etag)

    def testChunkedPut(self):
        if (tf.web_front_end == 'apache2'):
            raise SkipTest("Chunked PUT can only be tested with apache2 web"
                           " front end")

        def chunks(s, length=3):
            i, j = 0, length
            while i < len(s):
                yield s[i:j]
                i, j = j, j + length

        data = File.random_data(10000)
        etag = File.compute_md5sum(data)

        for i in (1, 10, 100, 1000):
            file_item = self.env.container.file(Utils.create_name())

            for j in chunks(data, i):
                file_item.chunked_write(j)

            self.assertTrue(file_item.chunked_write())
            self.assertTrue(data == file_item.read())

            info = file_item.info()
            self.assertEqual(etag, info['etag'])


class TestFileUTF8(Base2, TestFile):
    set_up = False


class TestDloEnv(object):
    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.account.delete_containers()

        cls.container = cls.account.container(Utils.create_name())

        if not cls.container.create():
            raise ResponseError(cls.conn.response)

        # avoid getting a prefix that stops halfway through an encoded
        # character
        prefix = Utils.create_name().decode("utf-8")[:10].encode("utf-8")
        cls.segment_prefix = prefix

        for letter in ('a', 'b', 'c', 'd', 'e'):
            file_item = cls.container.file("%s/seg_lower%s" % (prefix, letter))
            file_item.write(letter * 10)

            file_item = cls.container.file("%s/seg_upper%s" % (prefix, letter))
            file_item.write(letter.upper() * 10)

        man1 = cls.container.file("man1")
        man1.write('man1-contents',
                   hdrs={"X-Object-Manifest": "%s/%s/seg_lower" %
                         (cls.container.name, prefix)})

        man1 = cls.container.file("man2")
        man1.write('man2-contents',
                   hdrs={"X-Object-Manifest": "%s/%s/seg_upper" %
                         (cls.container.name, prefix)})

        manall = cls.container.file("manall")
        manall.write('manall-contents',
                     hdrs={"X-Object-Manifest": "%s/%s/seg" %
                           (cls.container.name, prefix)})


class TestDlo(Base):
    env = TestDloEnv
    set_up = False

    def test_get_manifest(self):
        file_item = self.env.container.file('man1')
        file_contents = file_item.read()
        self.assertEqual(
            file_contents,
            "aaaaaaaaaabbbbbbbbbbccccccccccddddddddddeeeeeeeeee")

        file_item = self.env.container.file('man2')
        file_contents = file_item.read()
        self.assertEqual(
            file_contents,
            "AAAAAAAAAABBBBBBBBBBCCCCCCCCCCDDDDDDDDDDEEEEEEEEEE")

        file_item = self.env.container.file('manall')
        file_contents = file_item.read()
        self.assertEqual(
            file_contents,
            ("aaaaaaaaaabbbbbbbbbbccccccccccddddddddddeeeeeeeeee" +
             "AAAAAAAAAABBBBBBBBBBCCCCCCCCCCDDDDDDDDDDEEEEEEEEEE"))

    def test_get_manifest_document_itself(self):
        file_item = self.env.container.file('man1')
        file_contents = file_item.read(parms={'multipart-manifest': 'get'})
        self.assertEqual(file_contents, "man1-contents")
        self.assertEqual(file_item.info()['x_object_manifest'],
                         "%s/%s/seg_lower" %
                         (self.env.container.name, self.env.segment_prefix))

    def test_get_range(self):
        file_item = self.env.container.file('man1')
        file_contents = file_item.read(size=25, offset=8)
        self.assertEqual(file_contents, "aabbbbbbbbbbccccccccccddd")

        file_contents = file_item.read(size=1, offset=47)
        self.assertEqual(file_contents, "e")

    def test_get_range_out_of_range(self):
        file_item = self.env.container.file('man1')

        self.assertRaises(ResponseError, file_item.read, size=7, offset=50)
        self.assert_status(416)

    def test_copy(self):
        # Adding a new segment, copying the manifest, and then deleting the
        # segment proves that the new object is really the concatenated
        # segments and not just a manifest.
        f_segment = self.env.container.file("%s/seg_lowerf" %
                                            (self.env.segment_prefix))
        f_segment.write('ffffffffff')
        try:
            man1_item = self.env.container.file('man1')
            man1_item.copy(self.env.container.name, "copied-man1")
        finally:
            # try not to leave this around for other tests to stumble over
            f_segment.delete()

        file_item = self.env.container.file('copied-man1')
        file_contents = file_item.read()
        self.assertEqual(
            file_contents,
            "aaaaaaaaaabbbbbbbbbbccccccccccddddddddddeeeeeeeeeeffffffffff")
        # The copied object must not have X-Object-Manifest
        self.assertNotIn("x_object_manifest", file_item.info())

    def test_copy_account(self):
        # dlo use same account and same container only
        acct = self.env.conn.account_name
        # Adding a new segment, copying the manifest, and then deleting the
        # segment proves that the new object is really the concatenated
        # segments and not just a manifest.
        f_segment = self.env.container.file("%s/seg_lowerf" %
                                            (self.env.segment_prefix))
        f_segment.write('ffffffffff')
        try:
            man1_item = self.env.container.file('man1')
            man1_item.copy_account(acct,
                                   self.env.container.name,
                                   "copied-man1")
        finally:
            # try not to leave this around for other tests to stumble over
            f_segment.delete()

        file_item = self.env.container.file('copied-man1')
        file_contents = file_item.read()
        self.assertEqual(
            file_contents,
            "aaaaaaaaaabbbbbbbbbbccccccccccddddddddddeeeeeeeeeeffffffffff")
        # The copied object must not have X-Object-Manifest
        self.assertNotIn("x_object_manifest", file_item.info())

    def test_copy_manifest(self):
        # Copying the manifest with multipart-manifest=get query string
        # should result in another manifest
        try:
            man1_item = self.env.container.file('man1')
            man1_item.copy(self.env.container.name, "copied-man1",
                           parms={'multipart-manifest': 'get'})

            copied = self.env.container.file("copied-man1")
            copied_contents = copied.read(parms={'multipart-manifest': 'get'})
            self.assertEqual(copied_contents, "man1-contents")

            copied_contents = copied.read()
            self.assertEqual(
                copied_contents,
                "aaaaaaaaaabbbbbbbbbbccccccccccddddddddddeeeeeeeeee")
            self.assertEqual(man1_item.info()['x_object_manifest'],
                             copied.info()['x_object_manifest'])
        finally:
            # try not to leave this around for other tests to stumble over
            self.env.container.file("copied-man1").delete()

    def test_dlo_if_match_get(self):
        manifest = self.env.container.file("man1")
        etag = manifest.info()['etag']

        self.assertRaises(ResponseError, manifest.read,
                          hdrs={'If-Match': 'not-%s' % etag})
        self.assert_status(412)

        manifest.read(hdrs={'If-Match': etag})
        self.assert_status(200)

    def test_dlo_if_none_match_get(self):
        manifest = self.env.container.file("man1")
        etag = manifest.info()['etag']

        self.assertRaises(ResponseError, manifest.read,
                          hdrs={'If-None-Match': etag})
        self.assert_status(304)

        manifest.read(hdrs={'If-None-Match': "not-%s" % etag})
        self.assert_status(200)

    def test_dlo_if_match_head(self):
        manifest = self.env.container.file("man1")
        etag = manifest.info()['etag']

        self.assertRaises(ResponseError, manifest.info,
                          hdrs={'If-Match': 'not-%s' % etag})
        self.assert_status(412)

        manifest.info(hdrs={'If-Match': etag})
        self.assert_status(200)

    def test_dlo_if_none_match_head(self):
        manifest = self.env.container.file("man1")
        etag = manifest.info()['etag']

        self.assertRaises(ResponseError, manifest.info,
                          hdrs={'If-None-Match': etag})
        self.assert_status(304)

        manifest.info(hdrs={'If-None-Match': "not-%s" % etag})
        self.assert_status(200)


class TestDloUTF8(Base2, TestDlo):
    set_up = False


class TestFileComparisonEnv(object):
    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.account.delete_containers()

        cls.container = cls.account.container(Utils.create_name())

        if not cls.container.create():
            raise ResponseError(cls.conn.response)

        cls.file_count = 20
        cls.file_size = 128
        cls.files = list()
        for x in range(cls.file_count):
            file_item = cls.container.file(Utils.create_name())
            file_item.write_random(cls.file_size)
            cls.files.append(file_item)

        cls.time_old_f1 = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                        time.gmtime(time.time() - 86400))
        cls.time_old_f2 = time.strftime("%A, %d-%b-%y %H:%M:%S GMT",
                                        time.gmtime(time.time() - 86400))
        cls.time_old_f3 = time.strftime("%a %b %d %H:%M:%S %Y",
                                        time.gmtime(time.time() - 86400))
        cls.time_new = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                     time.gmtime(time.time() + 86400))


class TestFileComparison(Base):
    env = TestFileComparisonEnv
    set_up = False

    def testIfMatch(self):
        for file_item in self.env.files:
            hdrs = {'If-Match': file_item.md5}
            self.assertTrue(file_item.read(hdrs=hdrs))

            hdrs = {'If-Match': 'bogus'}
            self.assertRaises(ResponseError, file_item.read, hdrs=hdrs)
            self.assert_status(412)

    def testIfNoneMatch(self):
        for file_item in self.env.files:
            hdrs = {'If-None-Match': 'bogus'}
            self.assertTrue(file_item.read(hdrs=hdrs))

            hdrs = {'If-None-Match': file_item.md5}
            self.assertRaises(ResponseError, file_item.read, hdrs=hdrs)
            self.assert_status(304)

    def testIfModifiedSince(self):
        for file_item in self.env.files:
            hdrs = {'If-Modified-Since': self.env.time_old_f1}
            self.assertTrue(file_item.read(hdrs=hdrs))
            self.assertTrue(file_item.info(hdrs=hdrs))

            hdrs = {'If-Modified-Since': self.env.time_new}
            self.assertRaises(ResponseError, file_item.read, hdrs=hdrs)
            self.assert_status(304)
            self.assertRaises(ResponseError, file_item.info, hdrs=hdrs)
            self.assert_status(304)

    def testIfUnmodifiedSince(self):
        for file_item in self.env.files:
            hdrs = {'If-Unmodified-Since': self.env.time_new}
            self.assertTrue(file_item.read(hdrs=hdrs))
            self.assertTrue(file_item.info(hdrs=hdrs))

            hdrs = {'If-Unmodified-Since': self.env.time_old_f2}
            self.assertRaises(ResponseError, file_item.read, hdrs=hdrs)
            self.assert_status(412)
            self.assertRaises(ResponseError, file_item.info, hdrs=hdrs)
            self.assert_status(412)

    def testIfMatchAndUnmodified(self):
        for file_item in self.env.files:
            hdrs = {'If-Match': file_item.md5,
                    'If-Unmodified-Since': self.env.time_new}
            self.assertTrue(file_item.read(hdrs=hdrs))

            hdrs = {'If-Match': 'bogus',
                    'If-Unmodified-Since': self.env.time_new}
            self.assertRaises(ResponseError, file_item.read, hdrs=hdrs)
            self.assert_status(412)

            hdrs = {'If-Match': file_item.md5,
                    'If-Unmodified-Since': self.env.time_old_f3}
            self.assertRaises(ResponseError, file_item.read, hdrs=hdrs)
            self.assert_status(412)

    def testLastModified(self):
        file_name = Utils.create_name()
        content_type = Utils.create_name()

        file = self.env.container.file(file_name)
        file.content_type = content_type
        resp = file.write_random_return_resp(self.env.file_size)
        put_last_modified = resp.getheader('last-modified')

        file = self.env.container.file(file_name)
        info = file.info()
        self.assertIn('last_modified', info)
        last_modified = info['last_modified']
        self.assertEqual(put_last_modified, info['last_modified'])

        hdrs = {'If-Modified-Since': last_modified}
        self.assertRaises(ResponseError, file.read, hdrs=hdrs)
        self.assert_status(304)

        hdrs = {'If-Unmodified-Since': last_modified}
        self.assertTrue(file.read(hdrs=hdrs))


class TestFileComparisonUTF8(Base2, TestFileComparison):
    set_up = False


class TestSloEnv(object):
    slo_enabled = None  # tri-state: None initially, then True/False

    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        config2 = deepcopy(tf.config)
        config2['account'] = tf.config['account2']
        config2['username'] = tf.config['username2']
        config2['password'] = tf.config['password2']
        cls.conn2 = Connection(config2)
        cls.conn2.authenticate()
        cls.account2 = cls.conn2.get_account()
        cls.account2.delete_containers()

        if cls.slo_enabled is None:
            cls.slo_enabled = 'slo' in cluster_info
            if not cls.slo_enabled:
                return

        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.account.delete_containers()

        cls.container = cls.account.container(Utils.create_name())

        if not cls.container.create():
            raise ResponseError(cls.conn.response)

        cls.seg_info = seg_info = {}
        for letter, size in (('a', 1024 * 1024),
                             ('b', 1024 * 1024),
                             ('c', 1024 * 1024),
                             ('d', 1024 * 1024),
                             ('e', 1)):
            seg_name = "seg_%s" % letter
            file_item = cls.container.file(seg_name)
            file_item.write(letter * size)
            seg_info[seg_name] = {
                'size_bytes': size,
                'etag': file_item.md5,
                'path': '/%s/%s' % (cls.container.name, seg_name)}

        file_item = cls.container.file("manifest-abcde")
        file_item.write(
            json.dumps([seg_info['seg_a'], seg_info['seg_b'],
                        seg_info['seg_c'], seg_info['seg_d'],
                        seg_info['seg_e']]),
            parms={'multipart-manifest': 'put'})

        file_item = cls.container.file('manifest-cd')
        cd_json = json.dumps([seg_info['seg_c'], seg_info['seg_d']])
        file_item.write(cd_json, parms={'multipart-manifest': 'put'})
        cd_etag = hashlib.md5(seg_info['seg_c']['etag'] +
                              seg_info['seg_d']['etag']).hexdigest()

        file_item = cls.container.file("manifest-bcd-submanifest")
        file_item.write(
            json.dumps([seg_info['seg_b'],
                        {'etag': cd_etag,
                         'size_bytes': (seg_info['seg_c']['size_bytes'] +
                                        seg_info['seg_d']['size_bytes']),
                         'path': '/%s/%s' % (cls.container.name,
                                             'manifest-cd')}]),
            parms={'multipart-manifest': 'put'})
        bcd_submanifest_etag = hashlib.md5(
            seg_info['seg_b']['etag'] + cd_etag).hexdigest()

        file_item = cls.container.file("manifest-abcde-submanifest")
        file_item.write(
            json.dumps([
                seg_info['seg_a'],
                {'etag': bcd_submanifest_etag,
                 'size_bytes': (seg_info['seg_b']['size_bytes'] +
                                seg_info['seg_c']['size_bytes'] +
                                seg_info['seg_d']['size_bytes']),
                 'path': '/%s/%s' % (cls.container.name,
                                     'manifest-bcd-submanifest')},
                seg_info['seg_e']]),
            parms={'multipart-manifest': 'put'})
        abcde_submanifest_etag = hashlib.md5(
            seg_info['seg_a']['etag'] + bcd_submanifest_etag +
            seg_info['seg_e']['etag']).hexdigest()
        abcde_submanifest_size = (seg_info['seg_a']['size_bytes'] +
                                  seg_info['seg_b']['size_bytes'] +
                                  seg_info['seg_c']['size_bytes'] +
                                  seg_info['seg_d']['size_bytes'] +
                                  seg_info['seg_e']['size_bytes'])

        file_item = cls.container.file("ranged-manifest")
        file_item.write(
            json.dumps([
                {'etag': abcde_submanifest_etag,
                 'size_bytes': abcde_submanifest_size,
                 'path': '/%s/%s' % (cls.container.name,
                                     'manifest-abcde-submanifest'),
                 'range': '-1048578'},  # 'c' + ('d' * 2**20) + 'e'
                {'etag': abcde_submanifest_etag,
                 'size_bytes': abcde_submanifest_size,
                 'path': '/%s/%s' % (cls.container.name,
                                     'manifest-abcde-submanifest'),
                 'range': '524288-1572863'},  # 'a' * 2**19 + 'b' * 2**19
                {'etag': abcde_submanifest_etag,
                 'size_bytes': abcde_submanifest_size,
                 'path': '/%s/%s' % (cls.container.name,
                                     'manifest-abcde-submanifest'),
                 'range': '3145727-3145728'}]),  # 'cd'
            parms={'multipart-manifest': 'put'})
        ranged_manifest_etag = hashlib.md5(
            abcde_submanifest_etag + ':3145727-4194304;' +
            abcde_submanifest_etag + ':524288-1572863;' +
            abcde_submanifest_etag + ':3145727-3145728;').hexdigest()
        ranged_manifest_size = 2 * 1024 * 1024 + 4

        file_item = cls.container.file("ranged-submanifest")
        file_item.write(
            json.dumps([
                seg_info['seg_c'],
                {'etag': ranged_manifest_etag,
                 'size_bytes': ranged_manifest_size,
                 'path': '/%s/%s' % (cls.container.name,
                                     'ranged-manifest')},
                {'etag': ranged_manifest_etag,
                 'size_bytes': ranged_manifest_size,
                 'path': '/%s/%s' % (cls.container.name,
                                     'ranged-manifest'),
                 'range': '524289-1572865'},
                {'etag': ranged_manifest_etag,
                 'size_bytes': ranged_manifest_size,
                 'path': '/%s/%s' % (cls.container.name,
                                     'ranged-manifest'),
                 'range': '-3'}]),
            parms={'multipart-manifest': 'put'})

        file_item = cls.container.file("manifest-db")
        file_item.write(
            json.dumps([
                {'path': seg_info['seg_d']['path'], 'etag': None,
                 'size_bytes': None},
                {'path': seg_info['seg_b']['path'], 'etag': None,
                 'size_bytes': None},
            ]), parms={'multipart-manifest': 'put'})


class TestSlo(Base):
    env = TestSloEnv
    set_up = False

    def setUp(self):
        super(TestSlo, self).setUp()
        if self.env.slo_enabled is False:
            raise SkipTest("SLO not enabled")
        elif self.env.slo_enabled is not True:
            # just some sanity checking
            raise Exception(
                "Expected slo_enabled to be True/False, got %r" %
                (self.env.slo_enabled,))

    def test_slo_get_simple_manifest(self):
        file_item = self.env.container.file('manifest-abcde')
        file_contents = file_item.read()
        self.assertEqual(4 * 1024 * 1024 + 1, len(file_contents))
        self.assertEqual('a', file_contents[0])
        self.assertEqual('a', file_contents[1024 * 1024 - 1])
        self.assertEqual('b', file_contents[1024 * 1024])
        self.assertEqual('d', file_contents[-2])
        self.assertEqual('e', file_contents[-1])

    def test_slo_get_nested_manifest(self):
        file_item = self.env.container.file('manifest-abcde-submanifest')
        file_contents = file_item.read()
        self.assertEqual(4 * 1024 * 1024 + 1, len(file_contents))
        self.assertEqual('a', file_contents[0])
        self.assertEqual('a', file_contents[1024 * 1024 - 1])
        self.assertEqual('b', file_contents[1024 * 1024])
        self.assertEqual('d', file_contents[-2])
        self.assertEqual('e', file_contents[-1])

    def test_slo_get_ranged_manifest(self):
        file_item = self.env.container.file('ranged-manifest')
        grouped_file_contents = [
            (char, sum(1 for _char in grp))
            for char, grp in itertools.groupby(file_item.read())]
        self.assertEqual([
            ('c', 1),
            ('d', 1024 * 1024),
            ('e', 1),
            ('a', 512 * 1024),
            ('b', 512 * 1024),
            ('c', 1),
            ('d', 1)], grouped_file_contents)

    def test_slo_get_ranged_submanifest(self):
        file_item = self.env.container.file('ranged-submanifest')
        grouped_file_contents = [
            (char, sum(1 for _char in grp))
            for char, grp in itertools.groupby(file_item.read())]
        self.assertEqual([
            ('c', 1024 * 1024 + 1),
            ('d', 1024 * 1024),
            ('e', 1),
            ('a', 512 * 1024),
            ('b', 512 * 1024),
            ('c', 1),
            ('d', 512 * 1024 + 1),
            ('e', 1),
            ('a', 512 * 1024),
            ('b', 1),
            ('c', 1),
            ('d', 1)], grouped_file_contents)

    def test_slo_ranged_get(self):
        file_item = self.env.container.file('manifest-abcde')
        file_contents = file_item.read(size=1024 * 1024 + 2,
                                       offset=1024 * 1024 - 1)
        self.assertEqual('a', file_contents[0])
        self.assertEqual('b', file_contents[1])
        self.assertEqual('b', file_contents[-2])
        self.assertEqual('c', file_contents[-1])

    def test_slo_ranged_submanifest(self):
        file_item = self.env.container.file('manifest-abcde-submanifest')
        file_contents = file_item.read(size=1024 * 1024 + 2,
                                       offset=1024 * 1024 * 2 - 1)
        self.assertEqual('b', file_contents[0])
        self.assertEqual('c', file_contents[1])
        self.assertEqual('c', file_contents[-2])
        self.assertEqual('d', file_contents[-1])

    def test_slo_etag_is_hash_of_etags(self):
        expected_hash = hashlib.md5()
        expected_hash.update(hashlib.md5('a' * 1024 * 1024).hexdigest())
        expected_hash.update(hashlib.md5('b' * 1024 * 1024).hexdigest())
        expected_hash.update(hashlib.md5('c' * 1024 * 1024).hexdigest())
        expected_hash.update(hashlib.md5('d' * 1024 * 1024).hexdigest())
        expected_hash.update(hashlib.md5('e').hexdigest())
        expected_etag = expected_hash.hexdigest()

        file_item = self.env.container.file('manifest-abcde')
        self.assertEqual(expected_etag, file_item.info()['etag'])

    def test_slo_etag_is_hash_of_etags_submanifests(self):

        def hd(x):
            return hashlib.md5(x).hexdigest()

        expected_etag = hd(hd('a' * 1024 * 1024) +
                           hd(hd('b' * 1024 * 1024) +
                              hd(hd('c' * 1024 * 1024) +
                                 hd('d' * 1024 * 1024))) +
                           hd('e'))

        file_item = self.env.container.file('manifest-abcde-submanifest')
        self.assertEqual(expected_etag, file_item.info()['etag'])

    def test_slo_etag_mismatch(self):
        file_item = self.env.container.file("manifest-a-bad-etag")
        try:
            file_item.write(
                json.dumps([{
                    'size_bytes': 1024 * 1024,
                    'etag': 'not it',
                    'path': '/%s/%s' % (self.env.container.name, 'seg_a')}]),
                parms={'multipart-manifest': 'put'})
        except ResponseError as err:
            self.assertEqual(400, err.status)
        else:
            self.fail("Expected ResponseError but didn't get it")

    def test_slo_size_mismatch(self):
        file_item = self.env.container.file("manifest-a-bad-size")
        try:
            file_item.write(
                json.dumps([{
                    'size_bytes': 1024 * 1024 - 1,
                    'etag': hashlib.md5('a' * 1024 * 1024).hexdigest(),
                    'path': '/%s/%s' % (self.env.container.name, 'seg_a')}]),
                parms={'multipart-manifest': 'put'})
        except ResponseError as err:
            self.assertEqual(400, err.status)
        else:
            self.fail("Expected ResponseError but didn't get it")

    def test_slo_unspecified_etag(self):
        file_item = self.env.container.file("manifest-a-unspecified-etag")
        file_item.write(
            json.dumps([{
                'size_bytes': 1024 * 1024,
                'etag': None,
                'path': '/%s/%s' % (self.env.container.name, 'seg_a')}]),
            parms={'multipart-manifest': 'put'})
        self.assert_status(201)

    def test_slo_unspecified_size(self):
        file_item = self.env.container.file("manifest-a-unspecified-size")
        file_item.write(
            json.dumps([{
                'size_bytes': None,
                'etag': hashlib.md5('a' * 1024 * 1024).hexdigest(),
                'path': '/%s/%s' % (self.env.container.name, 'seg_a')}]),
            parms={'multipart-manifest': 'put'})
        self.assert_status(201)

    def test_slo_missing_etag(self):
        file_item = self.env.container.file("manifest-a-missing-etag")
        try:
            file_item.write(
                json.dumps([{
                    'size_bytes': 1024 * 1024,
                    'path': '/%s/%s' % (self.env.container.name, 'seg_a')}]),
                parms={'multipart-manifest': 'put'})
        except ResponseError as err:
            self.assertEqual(400, err.status)
        else:
            self.fail("Expected ResponseError but didn't get it")

    def test_slo_missing_size(self):
        file_item = self.env.container.file("manifest-a-missing-size")
        try:
            file_item.write(
                json.dumps([{
                    'etag': hashlib.md5('a' * 1024 * 1024).hexdigest(),
                    'path': '/%s/%s' % (self.env.container.name, 'seg_a')}]),
                parms={'multipart-manifest': 'put'})
        except ResponseError as err:
            self.assertEqual(400, err.status)
        else:
            self.fail("Expected ResponseError but didn't get it")

    def test_slo_overwrite_segment_with_manifest(self):
        file_item = self.env.container.file("seg_b")
        try:
            file_item.write(
                json.dumps([
                    {'size_bytes': 1024 * 1024,
                     'etag': hashlib.md5('a' * 1024 * 1024).hexdigest(),
                     'path': '/%s/%s' % (self.env.container.name, 'seg_a')},
                    {'size_bytes': 1024 * 1024,
                     'etag': hashlib.md5('b' * 1024 * 1024).hexdigest(),
                     'path': '/%s/%s' % (self.env.container.name, 'seg_b')},
                    {'size_bytes': 1024 * 1024,
                     'etag': hashlib.md5('c' * 1024 * 1024).hexdigest(),
                     'path': '/%s/%s' % (self.env.container.name, 'seg_c')}]),
                parms={'multipart-manifest': 'put'})
        except ResponseError as err:
            self.assertEqual(409, err.status)
        else:
            self.fail("Expected ResponseError but didn't get it")

    def test_slo_copy(self):
        file_item = self.env.container.file("manifest-abcde")
        file_item.copy(self.env.container.name, "copied-abcde")

        copied = self.env.container.file("copied-abcde")
        copied_contents = copied.read(parms={'multipart-manifest': 'get'})
        self.assertEqual(4 * 1024 * 1024 + 1, len(copied_contents))

    def test_slo_copy_account(self):
        acct = self.env.conn.account_name
        # same account copy
        file_item = self.env.container.file("manifest-abcde")
        file_item.copy_account(acct, self.env.container.name, "copied-abcde")

        copied = self.env.container.file("copied-abcde")
        copied_contents = copied.read(parms={'multipart-manifest': 'get'})
        self.assertEqual(4 * 1024 * 1024 + 1, len(copied_contents))

        # copy to different account
        acct = self.env.conn2.account_name
        dest_cont = self.env.account2.container(Utils.create_name())
        self.assertTrue(dest_cont.create(hdrs={
            'X-Container-Write': self.env.conn.user_acl
        }))
        file_item = self.env.container.file("manifest-abcde")
        file_item.copy_account(acct, dest_cont, "copied-abcde")

        copied = dest_cont.file("copied-abcde")
        copied_contents = copied.read(parms={'multipart-manifest': 'get'})
        self.assertEqual(4 * 1024 * 1024 + 1, len(copied_contents))

    def test_slo_copy_the_manifest(self):
        file_item = self.env.container.file("manifest-abcde")
        file_item.copy(self.env.container.name, "copied-abcde-manifest-only",
                       parms={'multipart-manifest': 'get'})

        copied = self.env.container.file("copied-abcde-manifest-only")
        copied_contents = copied.read(parms={'multipart-manifest': 'get'})
        try:
            json.loads(copied_contents)
        except ValueError:
            self.fail("COPY didn't copy the manifest (invalid json on GET)")

    def test_slo_copy_the_manifest_account(self):
        acct = self.env.conn.account_name
        # same account
        file_item = self.env.container.file("manifest-abcde")
        file_item.copy_account(acct,
                               self.env.container.name,
                               "copied-abcde-manifest-only",
                               parms={'multipart-manifest': 'get'})

        copied = self.env.container.file("copied-abcde-manifest-only")
        copied_contents = copied.read(parms={'multipart-manifest': 'get'})
        try:
            json.loads(copied_contents)
        except ValueError:
            self.fail("COPY didn't copy the manifest (invalid json on GET)")

        # different account
        acct = self.env.conn2.account_name
        dest_cont = self.env.account2.container(Utils.create_name())
        self.assertTrue(dest_cont.create(hdrs={
            'X-Container-Write': self.env.conn.user_acl
        }))
        self.assertTrue(file_item.copy_account(
            acct, dest_cont, "copied-abcde-manifest-only",
            parms={'multipart-manifest': 'get'}))

        copied = dest_cont.file("copied-abcde-manifest-only")
        copied_contents = copied.read(parms={'multipart-manifest': 'get'})
        try:
            json.loads(copied_contents)
        except ValueError:
            self.fail("COPY didn't copy the manifest (invalid json on GET)")

    def _make_manifest(self):
        file_item = self.env.container.file("manifest-post")
        seg_info = self.env.seg_info
        file_item.write(
            json.dumps([seg_info['seg_a'], seg_info['seg_b'],
                        seg_info['seg_c'], seg_info['seg_d'],
                        seg_info['seg_e']]),
            parms={'multipart-manifest': 'put'})
        return file_item

    def test_slo_post_the_manifest_metadata_update(self):
        file_item = self._make_manifest()
        # sanity check, check the object is an SLO manifest
        file_item.info()
        file_item.header_fields([('slo', 'x-static-large-object')])

        # POST a user metadata (i.e. x-object-meta-post)
        self.assertTrue(file_item.sync_metadata({'post': 'update'}))

        updated = self.env.container.file("manifest-post")
        updated.info()
        updated.header_fields([('user-meta', 'x-object-meta-post')])  # sanity
        updated.header_fields([('slo', 'x-static-large-object')])
        updated_contents = updated.read(parms={'multipart-manifest': 'get'})
        try:
            json.loads(updated_contents)
        except ValueError:
            self.fail("Unexpected content on GET, expected a json body")

    def test_slo_post_the_manifest_metadata_update_with_qs(self):
        # multipart-manifest query should be ignored on post
        for verb in ('put', 'get', 'delete'):
            file_item = self._make_manifest()
            # sanity check, check the object is an SLO manifest
            file_item.info()
            file_item.header_fields([('slo', 'x-static-large-object')])
            # POST a user metadata (i.e. x-object-meta-post)
            self.assertTrue(file_item.sync_metadata(
                metadata={'post': 'update'},
                parms={'multipart-manifest': verb}))
            updated = self.env.container.file("manifest-post")
            updated.info()
            updated.header_fields(
                [('user-meta', 'x-object-meta-post')])  # sanity
            updated.header_fields([('slo', 'x-static-large-object')])
            updated_contents = updated.read(
                parms={'multipart-manifest': 'get'})
            try:
                json.loads(updated_contents)
            except ValueError:
                self.fail(
                    "Unexpected content on GET, expected a json body")

    def test_slo_get_the_manifest(self):
        manifest = self.env.container.file("manifest-abcde")
        got_body = manifest.read(parms={'multipart-manifest': 'get'})

        self.assertEqual('application/json; charset=utf-8',
                         manifest.content_type)
        try:
            json.loads(got_body)
        except ValueError:
            self.fail("GET with multipart-manifest=get got invalid json")

    def test_slo_get_the_manifest_with_details_from_server(self):
        manifest = self.env.container.file("manifest-db")
        got_body = manifest.read(parms={'multipart-manifest': 'get'})

        self.assertEqual('application/json; charset=utf-8',
                         manifest.content_type)
        try:
            value = json.loads(got_body)
        except ValueError:
            self.fail("GET with multipart-manifest=get got invalid json")

        self.assertEqual(len(value), 2)
        self.assertEqual(value[0]['bytes'], 1024 * 1024)
        self.assertEqual(value[0]['hash'],
                         hashlib.md5('d' * 1024 * 1024).hexdigest())
        self.assertEqual(value[0]['name'],
                         '/%s/seg_d' % self.env.container.name.decode("utf-8"))

        self.assertEqual(value[1]['bytes'], 1024 * 1024)
        self.assertEqual(value[1]['hash'],
                         hashlib.md5('b' * 1024 * 1024).hexdigest())
        self.assertEqual(value[1]['name'],
                         '/%s/seg_b' % self.env.container.name.decode("utf-8"))

    def test_slo_head_the_manifest(self):
        manifest = self.env.container.file("manifest-abcde")
        got_info = manifest.info(parms={'multipart-manifest': 'get'})

        self.assertEqual('application/json; charset=utf-8',
                         got_info['content_type'])

    def test_slo_if_match_get(self):
        manifest = self.env.container.file("manifest-abcde")
        etag = manifest.info()['etag']

        self.assertRaises(ResponseError, manifest.read,
                          hdrs={'If-Match': 'not-%s' % etag})
        self.assert_status(412)

        manifest.read(hdrs={'If-Match': etag})
        self.assert_status(200)

    def test_slo_if_none_match_get(self):
        manifest = self.env.container.file("manifest-abcde")
        etag = manifest.info()['etag']

        self.assertRaises(ResponseError, manifest.read,
                          hdrs={'If-None-Match': etag})
        self.assert_status(304)

        manifest.read(hdrs={'If-None-Match': "not-%s" % etag})
        self.assert_status(200)

    def test_slo_if_match_head(self):
        manifest = self.env.container.file("manifest-abcde")
        etag = manifest.info()['etag']

        self.assertRaises(ResponseError, manifest.info,
                          hdrs={'If-Match': 'not-%s' % etag})
        self.assert_status(412)

        manifest.info(hdrs={'If-Match': etag})
        self.assert_status(200)

    def test_slo_if_none_match_head(self):
        manifest = self.env.container.file("manifest-abcde")
        etag = manifest.info()['etag']

        self.assertRaises(ResponseError, manifest.info,
                          hdrs={'If-None-Match': etag})
        self.assert_status(304)

        manifest.info(hdrs={'If-None-Match': "not-%s" % etag})
        self.assert_status(200)


class TestSloUTF8(Base2, TestSlo):
    set_up = False


class TestObjectVersioningEnv(object):
    versioning_enabled = None  # tri-state: None initially, then True/False

    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.storage_url, cls.storage_token = cls.conn.authenticate()

        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))

        # Second connection for ACL tests
        config2 = deepcopy(tf.config)
        config2['account'] = tf.config['account2']
        config2['username'] = tf.config['username2']
        config2['password'] = tf.config['password2']
        cls.conn2 = Connection(config2)
        cls.conn2.authenticate()

        # avoid getting a prefix that stops halfway through an encoded
        # character
        prefix = Utils.create_name().decode("utf-8")[:10].encode("utf-8")

        cls.versions_container = cls.account.container(prefix + "-versions")
        if not cls.versions_container.create():
            raise ResponseError(cls.conn.response)

        cls.container = cls.account.container(prefix + "-objs")
        if not cls.container.create(
                hdrs={'X-Versions-Location': cls.versions_container.name}):
            raise ResponseError(cls.conn.response)

        container_info = cls.container.info()
        # if versioning is off, then X-Versions-Location won't persist
        cls.versioning_enabled = 'versions' in container_info

        # setup another account to test ACLs
        config2 = deepcopy(tf.config)
        config2['account'] = tf.config['account2']
        config2['username'] = tf.config['username2']
        config2['password'] = tf.config['password2']
        cls.conn2 = Connection(config2)
        cls.storage_url2, cls.storage_token2 = cls.conn2.authenticate()
        cls.account2 = cls.conn2.get_account()
        cls.account2.delete_containers()

        # setup another account with no access to anything to test ACLs
        config3 = deepcopy(tf.config)
        config3['account'] = tf.config['account']
        config3['username'] = tf.config['username3']
        config3['password'] = tf.config['password3']
        cls.conn3 = Connection(config3)
        cls.storage_url3, cls.storage_token3 = cls.conn3.authenticate()
        cls.account3 = cls.conn3.get_account()

    @classmethod
    def tearDown(cls):
        cls.account.delete_containers()
        cls.account2.delete_containers()


class TestCrossPolicyObjectVersioningEnv(object):
    # tri-state: None initially, then True/False
    versioning_enabled = None
    multiple_policies_enabled = None
    policies = None

    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()

        if cls.multiple_policies_enabled is None:
            try:
                cls.policies = tf.FunctionalStoragePolicyCollection.from_info()
            except AssertionError:
                pass

        if cls.policies and len(cls.policies) > 1:
            cls.multiple_policies_enabled = True
        else:
            cls.multiple_policies_enabled = False
            cls.versioning_enabled = False
            return

        if cls.versioning_enabled is None:
            cls.versioning_enabled = 'versioned_writes' in cluster_info
            if not cls.versioning_enabled:
                return

        policy = cls.policies.select()
        version_policy = cls.policies.exclude(name=policy['name']).select()

        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))

        # Second connection for ACL tests
        config2 = deepcopy(tf.config)
        config2['account'] = tf.config['account2']
        config2['username'] = tf.config['username2']
        config2['password'] = tf.config['password2']
        cls.conn2 = Connection(config2)
        cls.conn2.authenticate()

        # avoid getting a prefix that stops halfway through an encoded
        # character
        prefix = Utils.create_name().decode("utf-8")[:10].encode("utf-8")

        cls.versions_container = cls.account.container(prefix + "-versions")
        if not cls.versions_container.create(
                {'X-Storage-Policy': policy['name']}):
            raise ResponseError(cls.conn.response)

        cls.container = cls.account.container(prefix + "-objs")
        if not cls.container.create(
                hdrs={'X-Versions-Location': cls.versions_container.name,
                      'X-Storage-Policy': version_policy['name']}):
            raise ResponseError(cls.conn.response)

        container_info = cls.container.info()
        # if versioning is off, then X-Versions-Location won't persist
        cls.versioning_enabled = 'versions' in container_info

        # setup another account to test ACLs
        config2 = deepcopy(tf.config)
        config2['account'] = tf.config['account2']
        config2['username'] = tf.config['username2']
        config2['password'] = tf.config['password2']
        cls.conn2 = Connection(config2)
        cls.storage_url2, cls.storage_token2 = cls.conn2.authenticate()
        cls.account2 = cls.conn2.get_account()
        cls.account2.delete_containers()

        # setup another account with no access to anything to test ACLs
        config3 = deepcopy(tf.config)
        config3['account'] = tf.config['account']
        config3['username'] = tf.config['username3']
        config3['password'] = tf.config['password3']
        cls.conn3 = Connection(config3)
        cls.storage_url3, cls.storage_token3 = cls.conn3.authenticate()
        cls.account3 = cls.conn3.get_account()


class TestObjectVersioning(Base):
    env = TestObjectVersioningEnv
    set_up = False

    def setUp(self):
        super(TestObjectVersioning, self).setUp()
        if self.env.versioning_enabled is False:
            raise SkipTest("Object versioning not enabled")
        elif self.env.versioning_enabled is not True:
            # just some sanity checking
            raise Exception(
                "Expected versioning_enabled to be True/False, got %r" %
                (self.env.versioning_enabled,))

    def tearDown(self):
        super(TestObjectVersioning, self).tearDown()
        try:
            # only delete files and not container
            # as they were configured in self.env
            self.env.versions_container.delete_files()
            self.env.container.delete_files()
        except ResponseError:
            pass

    def test_clear_version_option(self):
        # sanity
        self.assertEqual(self.env.container.info()['versions'],
                         self.env.versions_container.name)
        self.env.container.update_metadata(
            hdrs={'X-Versions-Location': ''})
        self.assertEqual(self.env.container.info().get('versions'), None)

        # set location back to the way it was
        self.env.container.update_metadata(
            hdrs={'X-Versions-Location': self.env.versions_container.name})
        self.assertEqual(self.env.container.info()['versions'],
                         self.env.versions_container.name)

    def test_overwriting(self):
        container = self.env.container
        versions_container = self.env.versions_container
        cont_info = container.info()
        self.assertEqual(cont_info['versions'], versions_container.name)

        obj_name = Utils.create_name()

        versioned_obj = container.file(obj_name)
        versioned_obj.write("aaaaa", hdrs={'Content-Type': 'text/jibberish01'})
        obj_info = versioned_obj.info()
        self.assertEqual('text/jibberish01', obj_info['content_type'])

        self.assertEqual(0, versions_container.info()['object_count'])
        versioned_obj.write("bbbbb", hdrs={'Content-Type': 'text/jibberish02',
                            'X-Object-Meta-Foo': 'Bar'})
        versioned_obj.initialize()
        self.assertEqual(versioned_obj.content_type, 'text/jibberish02')
        self.assertEqual(versioned_obj.metadata['foo'], 'Bar')

        # the old version got saved off
        self.assertEqual(1, versions_container.info()['object_count'])
        versioned_obj_name = versions_container.files()[0]
        prev_version = versions_container.file(versioned_obj_name)
        prev_version.initialize()
        self.assertEqual("aaaaa", prev_version.read())
        self.assertEqual(prev_version.content_type, 'text/jibberish01')

        # make sure the new obj metadata did not leak to the prev. version
        self.assertTrue('foo' not in prev_version.metadata)

        # check that POST does not create a new version
        versioned_obj.sync_metadata(metadata={'fu': 'baz'})
        self.assertEqual(1, versions_container.info()['object_count'])

        # if we overwrite it again, there are two versions
        versioned_obj.write("ccccc")
        self.assertEqual(2, versions_container.info()['object_count'])
        versioned_obj_name = versions_container.files()[1]
        prev_version = versions_container.file(versioned_obj_name)
        prev_version.initialize()
        self.assertEqual("bbbbb", prev_version.read())
        self.assertEqual(prev_version.content_type, 'text/jibberish02')
        self.assertTrue('foo' in prev_version.metadata)
        self.assertTrue('fu' in prev_version.metadata)

        # as we delete things, the old contents return
        self.assertEqual("ccccc", versioned_obj.read())

        # test copy from a different container
        src_container = self.env.account.container(Utils.create_name())
        self.assertTrue(src_container.create())
        src_name = Utils.create_name()
        src_obj = src_container.file(src_name)
        src_obj.write("ddddd", hdrs={'Content-Type': 'text/jibberish04'})
        src_obj.copy(container.name, obj_name)

        self.assertEqual("ddddd", versioned_obj.read())
        versioned_obj.initialize()
        self.assertEqual(versioned_obj.content_type, 'text/jibberish04')

        # make sure versions container has the previous version
        self.assertEqual(3, versions_container.info()['object_count'])
        versioned_obj_name = versions_container.files()[2]
        prev_version = versions_container.file(versioned_obj_name)
        prev_version.initialize()
        self.assertEqual("ccccc", prev_version.read())

        # test delete
        versioned_obj.delete()
        self.assertEqual("ccccc", versioned_obj.read())
        versioned_obj.delete()
        self.assertEqual("bbbbb", versioned_obj.read())
        versioned_obj.delete()
        self.assertEqual("aaaaa", versioned_obj.read())
        self.assertEqual(0, versions_container.info()['object_count'])
        versioned_obj.delete()
        self.assertRaises(ResponseError, versioned_obj.read)

    def test_versioning_dlo(self):
        # SOF
        # Modified the swift test a little to avoid 409 in SoF
        # because of destination path already being a directory.
        # Example:
        # PUT AUTH_test/animals/cat/seg1.jpg
        # PUT AUTH_test/animals/cat/seg2.jpg
        # PUT AUTH_test/animals/cat -H "X-Object-Manifest: animals/cat/"
        # The last PUT above fails as animals/cat is already a directory in SoF
        #
        # The Change:
        # Name the manifest object in such a way that it is not an existing
        # file or directory in SwiftOnFile.
        # Example:
        # PUT AUTH_test/animals/cat_seg1.jpg
        # PUT AUTH_test/animals/cat_seg2.jpg
        # PUT AUTH_test/animals/cat -H "X-Object-Manifest: animals/cat_"
        #
        # TODO: Modify this test in Swift upstream

        container = self.env.container
        versions_container = self.env.versions_container
        obj_name = Utils.create_name()

        for i in ('1', '2', '3'):
            time.sleep(.01)  # guarantee that the timestamp changes
            obj_name_seg = obj_name + '_seg' + i
            versioned_obj = container.file(obj_name_seg)
            versioned_obj.write(i)
            versioned_obj.write(i + i)

        self.assertEqual(3, versions_container.info()['object_count'])

        manifest_obj_name = obj_name + '_'
        man_file = container.file(manifest_obj_name)
        man_file.write('', hdrs={"X-Object-Manifest": "%s/%s" %
                       (self.env.container.name, obj_name + '_')})

        # guarantee that the timestamp changes
        time.sleep(.01)

        # write manifest file again
        man_file.write('', hdrs={"X-Object-Manifest": "%s/%s" %
                       (self.env.container.name, obj_name + '_')})

        self.assertEqual(3, versions_container.info()['object_count'])
        self.assertEqual("112233", man_file.read())

    def test_versioning_container_acl(self):
        # create versions container and DO NOT give write access to account2
        versions_container = self.env.account.container(Utils.create_name())
        self.assertTrue(versions_container.create(hdrs={
            'X-Container-Write': ''
        }))

        # check account2 cannot write to versions container
        fail_obj_name = Utils.create_name()
        fail_obj = versions_container.file(fail_obj_name)
        self.assertRaises(ResponseError, fail_obj.write, "should fail",
                          cfg={'use_token': self.env.storage_token2})

        # create container and give write access to account2
        # don't set X-Versions-Location just yet
        container = self.env.account.container(Utils.create_name())
        self.assertTrue(container.create(hdrs={
            'X-Container-Write': self.env.conn2.user_acl}))

        # check account2 cannot set X-Versions-Location on container
        self.assertRaises(ResponseError, container.update_metadata, hdrs={
            'X-Versions-Location': versions_container},
            cfg={'use_token': self.env.storage_token2})

        # good! now let admin set the X-Versions-Location
        # p.s.: sticking a 'x-remove' header here to test precedence
        # of both headers. Setting the location should succeed.
        self.assertTrue(container.update_metadata(hdrs={
            'X-Remove-Versions-Location': versions_container,
            'X-Versions-Location': versions_container}))

        # write object twice to container and check version
        obj_name = Utils.create_name()
        versioned_obj = container.file(obj_name)
        self.assertTrue(versioned_obj.write("never argue with the data",
                        cfg={'use_token': self.env.storage_token2}))
        self.assertEqual(versioned_obj.read(), "never argue with the data")

        self.assertTrue(
            versioned_obj.write("we don't have no beer, just tequila",
                                cfg={'use_token': self.env.storage_token2}))
        self.assertEqual(versioned_obj.read(),
                         "we don't have no beer, just tequila")
        self.assertEqual(1, versions_container.info()['object_count'])

        # read the original uploaded object
        for filename in versions_container.files():
            backup_file = versions_container.file(filename)
            break
        self.assertEqual(backup_file.read(), "never argue with the data")

        # user3 (some random user with no access to anything)
        # tries to read from versioned container
        self.assertRaises(ResponseError, backup_file.read,
                          cfg={'use_token': self.env.storage_token3})

        # user3 cannot write or delete from source container either
        self.assertRaises(ResponseError, versioned_obj.write,
                          "some random user trying to write data",
                          cfg={'use_token': self.env.storage_token3})
        self.assertRaises(ResponseError, versioned_obj.delete,
                          cfg={'use_token': self.env.storage_token3})

        # user2 can't read or delete from versions-location
        self.assertRaises(ResponseError, backup_file.read,
                          cfg={'use_token': self.env.storage_token2})
        self.assertRaises(ResponseError, backup_file.delete,
                          cfg={'use_token': self.env.storage_token2})

        # but is able to delete from the source container
        # this could be a helpful scenario for dev ops that want to setup
        # just one container to hold object versions of multiple containers
        # and each one of those containers are owned by different users
        self.assertTrue(versioned_obj.delete(
                        cfg={'use_token': self.env.storage_token2}))

        # tear-down since we create these containers here
        # and not in self.env
        versions_container.delete_recursive()
        container.delete_recursive()

    def test_versioning_check_acl(self):
        container = self.env.container
        versions_container = self.env.versions_container
        versions_container.create(hdrs={'X-Container-Read': '.r:*,.rlistings'})

        obj_name = Utils.create_name()
        versioned_obj = container.file(obj_name)
        versioned_obj.write("aaaaa")
        self.assertEqual("aaaaa", versioned_obj.read())

        versioned_obj.write("bbbbb")
        self.assertEqual("bbbbb", versioned_obj.read())

        # Use token from second account and try to delete the object
        org_token = self.env.account.conn.storage_token
        self.env.account.conn.storage_token = self.env.conn2.storage_token
        try:
            self.assertRaises(ResponseError, versioned_obj.delete)
        finally:
            self.env.account.conn.storage_token = org_token

        # Verify with token from first account
        self.assertEqual("bbbbb", versioned_obj.read())

        versioned_obj.delete()
        self.assertEqual("aaaaa", versioned_obj.read())


class TestObjectVersioningUTF8(Base2, TestObjectVersioning):
    set_up = False


class TestCrossPolicyObjectVersioning(TestObjectVersioning):
    env = TestCrossPolicyObjectVersioningEnv
    set_up = False

    def setUp(self):
        super(TestCrossPolicyObjectVersioning, self).setUp()
        if self.env.multiple_policies_enabled is False:
            raise SkipTest('Cross policy test requires multiple policies')
        elif self.env.multiple_policies_enabled is not True:
            # just some sanity checking
            raise Exception("Expected multiple_policies_enabled "
                            "to be True/False, got %r" % (
                                self.env.versioning_enabled,))


class TestTempurlEnv(object):
    tempurl_enabled = None  # tri-state: None initially, then True/False

    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()

        if cls.tempurl_enabled is None:
            cls.tempurl_enabled = 'tempurl' in cluster_info
            if not cls.tempurl_enabled:
                return

        cls.tempurl_key = Utils.create_name()
        cls.tempurl_key2 = Utils.create_name()

        cls.account = Account(
            cls.conn, tf.config.get('account', tf.config['username']))
        cls.account.delete_containers()
        cls.account.update_metadata({
            'temp-url-key': cls.tempurl_key,
            'temp-url-key-2': cls.tempurl_key2
        })

        cls.container = cls.account.container(Utils.create_name())
        if not cls.container.create():
            raise ResponseError(cls.conn.response)

        cls.obj = cls.container.file(Utils.create_name())
        cls.obj.write("obj contents")
        cls.other_obj = cls.container.file(Utils.create_name())
        cls.other_obj.write("other obj contents")


class TestTempurl(Base):
    env = TestTempurlEnv
    set_up = False

    def setUp(self):
        super(TestTempurl, self).setUp()
        if self.env.tempurl_enabled is False:
            raise SkipTest("TempURL not enabled")
        elif self.env.tempurl_enabled is not True:
            # just some sanity checking
            raise Exception(
                "Expected tempurl_enabled to be True/False, got %r" %
                (self.env.tempurl_enabled,))

        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(self.env.obj.path),
            self.env.tempurl_key)
        self.obj_tempurl_parms = {'temp_url_sig': sig,
                                  'temp_url_expires': str(expires)}

    def tempurl_sig(self, method, expires, path, key):
        return hmac.new(
            key,
            '%s\n%s\n%s' % (method, expires, urllib.unquote(path)),
            hashlib.sha1).hexdigest()

    def test_GET(self):
        contents = self.env.obj.read(
            parms=self.obj_tempurl_parms,
            cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

        # GET tempurls also allow HEAD requests
        self.assertTrue(self.env.obj.info(parms=self.obj_tempurl_parms,
                                          cfg={'no_auth_token': True}))

    def test_GET_with_key_2(self):
        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(self.env.obj.path),
            self.env.tempurl_key2)
        parms = {'temp_url_sig': sig,
                 'temp_url_expires': str(expires)}

        contents = self.env.obj.read(parms=parms, cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

    def test_GET_DLO_inside_container(self):
        seg1 = self.env.container.file(
            "get-dlo-inside-seg1" + Utils.create_name())
        seg2 = self.env.container.file(
            "get-dlo-inside-seg2" + Utils.create_name())
        seg1.write("one fish two fish ")
        seg2.write("red fish blue fish")

        manifest = self.env.container.file("manifest" + Utils.create_name())
        manifest.write(
            '',
            hdrs={"X-Object-Manifest": "%s/get-dlo-inside-seg" %
                  (self.env.container.name,)})

        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(manifest.path),
            self.env.tempurl_key)
        parms = {'temp_url_sig': sig,
                 'temp_url_expires': str(expires)}

        contents = manifest.read(parms=parms, cfg={'no_auth_token': True})
        self.assertEqual(contents, "one fish two fish red fish blue fish")

    def test_GET_DLO_outside_container(self):
        seg1 = self.env.container.file(
            "get-dlo-outside-seg1" + Utils.create_name())
        seg2 = self.env.container.file(
            "get-dlo-outside-seg2" + Utils.create_name())
        seg1.write("one fish two fish ")
        seg2.write("red fish blue fish")

        container2 = self.env.account.container(Utils.create_name())
        container2.create()

        manifest = container2.file("manifest" + Utils.create_name())
        manifest.write(
            '',
            hdrs={"X-Object-Manifest": "%s/get-dlo-outside-seg" %
                  (self.env.container.name,)})

        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(manifest.path),
            self.env.tempurl_key)
        parms = {'temp_url_sig': sig,
                 'temp_url_expires': str(expires)}

        # cross container tempurl works fine for account tempurl key
        contents = manifest.read(parms=parms, cfg={'no_auth_token': True})
        self.assertEqual(contents, "one fish two fish red fish blue fish")
        self.assert_status([200])

    def test_PUT(self):
        new_obj = self.env.container.file(Utils.create_name())

        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'PUT', expires, self.env.conn.make_path(new_obj.path),
            self.env.tempurl_key)
        put_parms = {'temp_url_sig': sig,
                     'temp_url_expires': str(expires)}

        new_obj.write('new obj contents',
                      parms=put_parms, cfg={'no_auth_token': True})
        self.assertEqual(new_obj.read(), "new obj contents")

        # PUT tempurls also allow HEAD requests
        self.assertTrue(new_obj.info(parms=put_parms,
                                     cfg={'no_auth_token': True}))

    def test_PUT_manifest_access(self):
        new_obj = self.env.container.file(Utils.create_name())

        # give out a signature which allows a PUT to new_obj
        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'PUT', expires, self.env.conn.make_path(new_obj.path),
            self.env.tempurl_key)
        put_parms = {'temp_url_sig': sig,
                     'temp_url_expires': str(expires)}

        # try to create manifest pointing to some random container
        try:
            new_obj.write('', {
                'x-object-manifest': '%s/foo' % 'some_random_container'
            }, parms=put_parms, cfg={'no_auth_token': True})
        except ResponseError as e:
            self.assertEqual(e.status, 400)
        else:
            self.fail('request did not error')

        # create some other container
        other_container = self.env.account.container(Utils.create_name())
        if not other_container.create():
            raise ResponseError(self.conn.response)

        # try to create manifest pointing to new container
        try:
            new_obj.write('', {
                'x-object-manifest': '%s/foo' % other_container
            }, parms=put_parms, cfg={'no_auth_token': True})
        except ResponseError as e:
            self.assertEqual(e.status, 400)
        else:
            self.fail('request did not error')

        # try again using a tempurl POST to an already created object
        new_obj.write('', {}, parms=put_parms, cfg={'no_auth_token': True})
        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'POST', expires, self.env.conn.make_path(new_obj.path),
            self.env.tempurl_key)
        post_parms = {'temp_url_sig': sig,
                      'temp_url_expires': str(expires)}
        try:
            new_obj.post({'x-object-manifest': '%s/foo' % other_container},
                         parms=post_parms, cfg={'no_auth_token': True})
        except ResponseError as e:
            self.assertEqual(e.status, 400)
        else:
            self.fail('request did not error')

    def test_HEAD(self):
        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'HEAD', expires, self.env.conn.make_path(self.env.obj.path),
            self.env.tempurl_key)
        head_parms = {'temp_url_sig': sig,
                      'temp_url_expires': str(expires)}

        self.assertTrue(self.env.obj.info(parms=head_parms,
                                          cfg={'no_auth_token': True}))
        # HEAD tempurls don't allow PUT or GET requests, despite the fact that
        # PUT and GET tempurls both allow HEAD requests
        self.assertRaises(ResponseError, self.env.other_obj.read,
                          cfg={'no_auth_token': True},
                          parms=self.obj_tempurl_parms)
        self.assert_status([401])

        self.assertRaises(ResponseError, self.env.other_obj.write,
                          'new contents',
                          cfg={'no_auth_token': True},
                          parms=self.obj_tempurl_parms)
        self.assert_status([401])

    def test_different_object(self):
        contents = self.env.obj.read(
            parms=self.obj_tempurl_parms,
            cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

        self.assertRaises(ResponseError, self.env.other_obj.read,
                          cfg={'no_auth_token': True},
                          parms=self.obj_tempurl_parms)
        self.assert_status([401])

    def test_changing_sig(self):
        contents = self.env.obj.read(
            parms=self.obj_tempurl_parms,
            cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

        parms = self.obj_tempurl_parms.copy()
        if parms['temp_url_sig'][0] == 'a':
            parms['temp_url_sig'] = 'b' + parms['temp_url_sig'][1:]
        else:
            parms['temp_url_sig'] = 'a' + parms['temp_url_sig'][1:]

        self.assertRaises(ResponseError, self.env.obj.read,
                          cfg={'no_auth_token': True},
                          parms=parms)
        self.assert_status([401])

    def test_changing_expires(self):
        contents = self.env.obj.read(
            parms=self.obj_tempurl_parms,
            cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

        parms = self.obj_tempurl_parms.copy()
        if parms['temp_url_expires'][-1] == '0':
            parms['temp_url_expires'] = parms['temp_url_expires'][:-1] + '1'
        else:
            parms['temp_url_expires'] = parms['temp_url_expires'][:-1] + '0'

        self.assertRaises(ResponseError, self.env.obj.read,
                          cfg={'no_auth_token': True},
                          parms=parms)
        self.assert_status([401])


class TestTempurlUTF8(Base2, TestTempurl):
    set_up = False


class TestContainerTempurlEnv(object):
    tempurl_enabled = None  # tri-state: None initially, then True/False

    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()

        if cls.tempurl_enabled is None:
            cls.tempurl_enabled = 'tempurl' in cluster_info
            if not cls.tempurl_enabled:
                return

        cls.tempurl_key = Utils.create_name()
        cls.tempurl_key2 = Utils.create_name()

        cls.account = Account(
            cls.conn, tf.config.get('account', tf.config['username']))
        cls.account.delete_containers()

        # creating another account and connection
        # for ACL tests
        config2 = deepcopy(tf.config)
        config2['account'] = tf.config['account2']
        config2['username'] = tf.config['username2']
        config2['password'] = tf.config['password2']
        cls.conn2 = Connection(config2)
        cls.conn2.authenticate()
        cls.account2 = Account(
            cls.conn2, config2.get('account', config2['username']))
        cls.account2 = cls.conn2.get_account()

        cls.container = cls.account.container(Utils.create_name())
        if not cls.container.create({
                'x-container-meta-temp-url-key': cls.tempurl_key,
                'x-container-meta-temp-url-key-2': cls.tempurl_key2,
                'x-container-read': cls.account2.name}):
            raise ResponseError(cls.conn.response)

        cls.obj = cls.container.file(Utils.create_name())
        cls.obj.write("obj contents")
        cls.other_obj = cls.container.file(Utils.create_name())
        cls.other_obj.write("other obj contents")


class TestContainerTempurl(Base):
    env = TestContainerTempurlEnv
    set_up = False

    def setUp(self):
        super(TestContainerTempurl, self).setUp()
        if self.env.tempurl_enabled is False:
            raise SkipTest("TempURL not enabled")
        elif self.env.tempurl_enabled is not True:
            # just some sanity checking
            raise Exception(
                "Expected tempurl_enabled to be True/False, got %r" %
                (self.env.tempurl_enabled,))

        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(self.env.obj.path),
            self.env.tempurl_key)
        self.obj_tempurl_parms = {'temp_url_sig': sig,
                                  'temp_url_expires': str(expires)}

    def tempurl_sig(self, method, expires, path, key):
        return hmac.new(
            key,
            '%s\n%s\n%s' % (method, expires, urllib.unquote(path)),
            hashlib.sha1).hexdigest()

    def test_GET(self):
        contents = self.env.obj.read(
            parms=self.obj_tempurl_parms,
            cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

        # GET tempurls also allow HEAD requests
        self.assertTrue(self.env.obj.info(parms=self.obj_tempurl_parms,
                                          cfg={'no_auth_token': True}))

    def test_GET_with_key_2(self):
        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(self.env.obj.path),
            self.env.tempurl_key2)
        parms = {'temp_url_sig': sig,
                 'temp_url_expires': str(expires)}

        contents = self.env.obj.read(parms=parms, cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

    def test_PUT(self):
        new_obj = self.env.container.file(Utils.create_name())

        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'PUT', expires, self.env.conn.make_path(new_obj.path),
            self.env.tempurl_key)
        put_parms = {'temp_url_sig': sig,
                     'temp_url_expires': str(expires)}

        new_obj.write('new obj contents',
                      parms=put_parms, cfg={'no_auth_token': True})
        self.assertEqual(new_obj.read(), "new obj contents")

        # PUT tempurls also allow HEAD requests
        self.assertTrue(new_obj.info(parms=put_parms,
                                     cfg={'no_auth_token': True}))

    def test_HEAD(self):
        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'HEAD', expires, self.env.conn.make_path(self.env.obj.path),
            self.env.tempurl_key)
        head_parms = {'temp_url_sig': sig,
                      'temp_url_expires': str(expires)}

        self.assertTrue(self.env.obj.info(parms=head_parms,
                                          cfg={'no_auth_token': True}))
        # HEAD tempurls don't allow PUT or GET requests, despite the fact that
        # PUT and GET tempurls both allow HEAD requests
        self.assertRaises(ResponseError, self.env.other_obj.read,
                          cfg={'no_auth_token': True},
                          parms=self.obj_tempurl_parms)
        self.assert_status([401])

        self.assertRaises(ResponseError, self.env.other_obj.write,
                          'new contents',
                          cfg={'no_auth_token': True},
                          parms=self.obj_tempurl_parms)
        self.assert_status([401])

    def test_different_object(self):
        contents = self.env.obj.read(
            parms=self.obj_tempurl_parms,
            cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

        self.assertRaises(ResponseError, self.env.other_obj.read,
                          cfg={'no_auth_token': True},
                          parms=self.obj_tempurl_parms)
        self.assert_status([401])

    def test_changing_sig(self):
        contents = self.env.obj.read(
            parms=self.obj_tempurl_parms,
            cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

        parms = self.obj_tempurl_parms.copy()
        if parms['temp_url_sig'][0] == 'a':
            parms['temp_url_sig'] = 'b' + parms['temp_url_sig'][1:]
        else:
            parms['temp_url_sig'] = 'a' + parms['temp_url_sig'][1:]

        self.assertRaises(ResponseError, self.env.obj.read,
                          cfg={'no_auth_token': True},
                          parms=parms)
        self.assert_status([401])

    def test_changing_expires(self):
        contents = self.env.obj.read(
            parms=self.obj_tempurl_parms,
            cfg={'no_auth_token': True})
        self.assertEqual(contents, "obj contents")

        parms = self.obj_tempurl_parms.copy()
        if parms['temp_url_expires'][-1] == '0':
            parms['temp_url_expires'] = parms['temp_url_expires'][:-1] + '1'
        else:
            parms['temp_url_expires'] = parms['temp_url_expires'][:-1] + '0'

        self.assertRaises(ResponseError, self.env.obj.read,
                          cfg={'no_auth_token': True},
                          parms=parms)
        self.assert_status([401])

    @requires_acls
    def test_tempurl_keys_visible_to_account_owner(self):
        if not tf.cluster_info.get('tempauth'):
            raise SkipTest('TEMP AUTH SPECIFIC TEST')
        metadata = self.env.container.info()
        self.assertEqual(metadata.get('tempurl_key'), self.env.tempurl_key)
        self.assertEqual(metadata.get('tempurl_key2'), self.env.tempurl_key2)

    @requires_acls
    def test_tempurl_keys_hidden_from_acl_readonly(self):
        if not tf.cluster_info.get('tempauth'):
            raise SkipTest('TEMP AUTH SPECIFIC TEST')
        original_token = self.env.container.conn.storage_token
        self.env.container.conn.storage_token = self.env.conn2.storage_token
        metadata = self.env.container.info()
        self.env.container.conn.storage_token = original_token

        self.assertNotIn(
            'tempurl_key', metadata,
            'Container TempURL key found, should not be visible '
            'to readonly ACLs')
        self.assertNotIn(
            'tempurl_key2', metadata,
            'Container TempURL key-2 found, should not be visible '
            'to readonly ACLs')

    def test_GET_DLO_inside_container(self):
        seg1 = self.env.container.file(
            "get-dlo-inside-seg1" + Utils.create_name())
        seg2 = self.env.container.file(
            "get-dlo-inside-seg2" + Utils.create_name())
        seg1.write("one fish two fish ")
        seg2.write("red fish blue fish")

        manifest = self.env.container.file("manifest" + Utils.create_name())
        manifest.write(
            '',
            hdrs={"X-Object-Manifest": "%s/get-dlo-inside-seg" %
                  (self.env.container.name,)})

        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(manifest.path),
            self.env.tempurl_key)
        parms = {'temp_url_sig': sig,
                 'temp_url_expires': str(expires)}

        contents = manifest.read(parms=parms, cfg={'no_auth_token': True})
        self.assertEqual(contents, "one fish two fish red fish blue fish")

    def test_GET_DLO_outside_container(self):
        container2 = self.env.account.container(Utils.create_name())
        container2.create()
        seg1 = container2.file(
            "get-dlo-outside-seg1" + Utils.create_name())
        seg2 = container2.file(
            "get-dlo-outside-seg2" + Utils.create_name())
        seg1.write("one fish two fish ")
        seg2.write("red fish blue fish")

        manifest = self.env.container.file("manifest" + Utils.create_name())
        manifest.write(
            '',
            hdrs={"X-Object-Manifest": "%s/get-dlo-outside-seg" %
                  (container2.name,)})

        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(manifest.path),
            self.env.tempurl_key)
        parms = {'temp_url_sig': sig,
                 'temp_url_expires': str(expires)}

        # cross container tempurl does not work for container tempurl key
        try:
            manifest.read(parms=parms, cfg={'no_auth_token': True})
        except ResponseError as e:
            self.assertEqual(e.status, 401)
        else:
            self.fail('request did not error')
        try:
            manifest.info(parms=parms, cfg={'no_auth_token': True})
        except ResponseError as e:
            self.assertEqual(e.status, 401)
        else:
            self.fail('request did not error')


class TestContainerTempurlUTF8(Base2, TestContainerTempurl):
    set_up = False


class TestSloTempurlEnv(object):
    enabled = None  # tri-state: None initially, then True/False

    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()

        if cls.enabled is None:
            cls.enabled = 'tempurl' in cluster_info and 'slo' in cluster_info

        cls.tempurl_key = Utils.create_name()

        cls.account = Account(
            cls.conn, tf.config.get('account', tf.config['username']))
        cls.account.delete_containers()
        cls.account.update_metadata({'temp-url-key': cls.tempurl_key})

        cls.manifest_container = cls.account.container(Utils.create_name())
        cls.segments_container = cls.account.container(Utils.create_name())
        if not cls.manifest_container.create():
            raise ResponseError(cls.conn.response)
        if not cls.segments_container.create():
            raise ResponseError(cls.conn.response)

        seg1 = cls.segments_container.file(Utils.create_name())
        seg1.write('1' * 1024 * 1024)

        seg2 = cls.segments_container.file(Utils.create_name())
        seg2.write('2' * 1024 * 1024)

        cls.manifest_data = [{'size_bytes': 1024 * 1024,
                              'etag': seg1.md5,
                              'path': '/%s/%s' % (cls.segments_container.name,
                                                  seg1.name)},
                             {'size_bytes': 1024 * 1024,
                              'etag': seg2.md5,
                              'path': '/%s/%s' % (cls.segments_container.name,
                                                  seg2.name)}]

        cls.manifest = cls.manifest_container.file(Utils.create_name())
        cls.manifest.write(
            json.dumps(cls.manifest_data),
            parms={'multipart-manifest': 'put'})


class TestSloTempurl(Base):
    env = TestSloTempurlEnv
    set_up = False

    def setUp(self):
        super(TestSloTempurl, self).setUp()
        if self.env.enabled is False:
            raise SkipTest("TempURL and SLO not both enabled")
        elif self.env.enabled is not True:
            # just some sanity checking
            raise Exception(
                "Expected enabled to be True/False, got %r" %
                (self.env.enabled,))

    def tempurl_sig(self, method, expires, path, key):
        return hmac.new(
            key,
            '%s\n%s\n%s' % (method, expires, urllib.unquote(path)),
            hashlib.sha1).hexdigest()

    def test_GET(self):
        expires = int(time.time()) + 86400
        sig = self.tempurl_sig(
            'GET', expires, self.env.conn.make_path(self.env.manifest.path),
            self.env.tempurl_key)
        parms = {'temp_url_sig': sig, 'temp_url_expires': str(expires)}

        contents = self.env.manifest.read(
            parms=parms,
            cfg={'no_auth_token': True})
        self.assertEqual(len(contents), 2 * 1024 * 1024)

        # GET tempurls also allow HEAD requests
        self.assertTrue(self.env.manifest.info(
            parms=parms, cfg={'no_auth_token': True}))


class TestSloTempurlUTF8(Base2, TestSloTempurl):
    set_up = False


class TestServiceToken(unittest.TestCase):

    def setUp(self):
        if tf.skip_service_tokens:
            raise SkipTest

        self.SET_TO_USERS_TOKEN = 1
        self.SET_TO_SERVICE_TOKEN = 2

        # keystoneauth and tempauth differ in allowing PUT account
        # Even if keystoneauth allows it, the proxy-server uses
        # allow_account_management to decide if accounts can be created
        self.put_account_expect = is_client_error
        if tf.swift_test_auth_version != '1':
            if cluster_info.get('swift').get('allow_account_management'):
                self.put_account_expect = is_success

    def _scenario_generator(self):
        paths = ((None, None), ('c', None), ('c', 'o'))
        for path in paths:
            for method in ('PUT', 'POST', 'HEAD', 'GET', 'OPTIONS'):
                yield method, path[0], path[1]
        for path in reversed(paths):
            yield 'DELETE', path[0], path[1]

    def _assert_is_authed_response(self, method, container, object, resp):
        resp.read()
        expect = is_success
        if method == 'DELETE' and not container:
            expect = is_client_error
        if method == 'PUT' and not container:
            expect = self.put_account_expect
        self.assertTrue(expect(resp.status), 'Unexpected %s for %s %s %s'
                        % (resp.status, method, container, object))

    def _assert_not_authed_response(self, method, container, object, resp):
        resp.read()
        expect = is_client_error
        if method == 'OPTIONS':
            expect = is_success
        self.assertTrue(expect(resp.status), 'Unexpected %s for %s %s %s'
                        % (resp.status, method, container, object))

    def prepare_request(self, method, use_service_account=False,
                        container=None, obj=None, body=None, headers=None,
                        x_auth_token=None,
                        x_service_token=None, dbg=False):
        """
        Setup for making the request

        When retry() calls the do_request() function, it calls it the
        test user's token, the parsed path, a connection and (optionally)
        a token from the test service user. We save options here so that
        do_request() can make the appropriate request.

        :param method: The operation (e.g'. 'HEAD')
        :param use_service_account: Optional. Set True to change the path to
               be the service account
        :param container: Optional. Adds a container name to the path
        :param obj: Optional. Adds an object name to the path
        :param body: Optional. Adds a body (string) in the request
        :param headers: Optional. Adds additional headers.
        :param x_auth_token: Optional. Default is SET_TO_USERS_TOKEN. One of:
                   SET_TO_USERS_TOKEN     Put the test user's token in
                                          X-Auth-Token
                   SET_TO_SERVICE_TOKEN   Put the service token in X-Auth-Token
        :param x_service_token: Optional. Default is to not set X-Service-Token
                   to any value. If specified, is one of following:
                   SET_TO_USERS_TOKEN     Put the test user's token in
                                          X-Service-Token
                   SET_TO_SERVICE_TOKEN   Put the service token in
                                          X-Service-Token
        :param dbg: Optional. Set true to check request arguments
        """
        self.method = method
        self.use_service_account = use_service_account
        self.container = container
        self.obj = obj
        self.body = body
        self.headers = headers
        if x_auth_token:
            self.x_auth_token = x_auth_token
        else:
            self.x_auth_token = self.SET_TO_USERS_TOKEN
        self.x_service_token = x_service_token
        self.dbg = dbg

    def do_request(self, url, token, parsed, conn, service_token=''):
            if self.use_service_account:
                path = self._service_account(parsed.path)
            else:
                path = parsed.path
            if self.container:
                path += '/%s' % self.container
            if self.obj:
                path += '/%s' % self.obj
            headers = {}
            if self.body:
                headers.update({'Content-Length': len(self.body)})
            if self.x_auth_token == self.SET_TO_USERS_TOKEN:
                headers.update({'X-Auth-Token': token})
            elif self.x_auth_token == self.SET_TO_SERVICE_TOKEN:
                headers.update({'X-Auth-Token': service_token})
            if self.x_service_token == self.SET_TO_USERS_TOKEN:
                headers.update({'X-Service-Token': token})
            elif self.x_service_token == self.SET_TO_SERVICE_TOKEN:
                headers.update({'X-Service-Token': service_token})
            if self.dbg:
                print('DEBUG: conn.request: method:%s path:%s'
                      ' body:%s headers:%s' % (self.method, path, self.body,
                                               headers))
            conn.request(self.method, path, self.body, headers=headers)
            return check_response(conn)

    def _service_account(self, path):
        parts = path.split('/', 3)
        account = parts[2]
        try:
            project_id = account[account.index('_') + 1:]
        except ValueError:
            project_id = account
        parts[2] = '%s%s' % (tf.swift_test_service_prefix, project_id)
        return '/'.join(parts)

    def test_user_access_own_auth_account(self):
        # This covers ground tested elsewhere (tests a user doing HEAD
        # on own account). However, if this fails, none of the remaining
        # tests will work
        self.prepare_request('HEAD')
        resp = retry(self.do_request)
        resp.read()
        self.assertIn(resp.status, (200, 204))

    def test_user_cannot_access_service_account(self):
        for method, container, obj in self._scenario_generator():
            self.prepare_request(method, use_service_account=True,
                                 container=container, obj=obj)
            resp = retry(self.do_request)
            self._assert_not_authed_response(method, container, obj, resp)

    def test_service_user_denied_with_x_auth_token(self):
        for method, container, obj in self._scenario_generator():
            self.prepare_request(method, use_service_account=True,
                                 container=container, obj=obj,
                                 x_auth_token=self.SET_TO_SERVICE_TOKEN)
            resp = retry(self.do_request, service_user=5)
            self._assert_not_authed_response(method, container, obj, resp)

    def test_service_user_denied_with_x_service_token(self):
        for method, container, obj in self._scenario_generator():
            self.prepare_request(method, use_service_account=True,
                                 container=container, obj=obj,
                                 x_auth_token=self.SET_TO_SERVICE_TOKEN,
                                 x_service_token=self.SET_TO_SERVICE_TOKEN)
            resp = retry(self.do_request, service_user=5)
            self._assert_not_authed_response(method, container, obj, resp)

    def test_user_plus_service_can_access_service_account(self):
        for method, container, obj in self._scenario_generator():
            self.prepare_request(method, use_service_account=True,
                                 container=container, obj=obj,
                                 x_auth_token=self.SET_TO_USERS_TOKEN,
                                 x_service_token=self.SET_TO_SERVICE_TOKEN)
            resp = retry(self.do_request, service_user=5)
            self._assert_is_authed_response(method, container, obj, resp)


if __name__ == '__main__':
    unittest.main()
