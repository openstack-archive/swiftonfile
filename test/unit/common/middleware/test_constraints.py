# Copyright (c) 2014 Red Hat, Inc.
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

import unittest
from swift.common.swob import Request, Response
from swiftonfile.swift.common.middleware import check_constraints
from mock import Mock, patch
from contextlib import nested


class FakeApp(object):

    def __call__(self, env, start_response):
        return Response(body="OK")(env, start_response)


def check_object_creation(req, object_name):
        return


class TestConstraintsMiddleware(unittest.TestCase):

    """ Tests for common.middleware.constraints.check_constraints """

    def setUp(self):
        self.conf = {
            'policies': '2'}

        self.container1_info_mock = Mock()
        self.container1_info_mock.return_value = {'status': 0,
            'sync_key': None, 'storage_policy': '0', 'meta': {},
            'cors': {'allow_origin': None, 'expose_headers': None,
            'max_age': None}, 'sysmeta': {}, 'read_acl': None,
            'object_count': None, 'write_acl': None, 'versions': None,
            'bytes': None}

        self.container2_info_mock = Mock()
        self.container2_info_mock.return_value = {'status': 0,
            'sync_key': None, 'storage_policy': '2', 'meta': {},
            'cors': {'allow_origin': None, 'expose_headers': None,
            'max_age': None}, 'sysmeta': {}, 'read_acl': None,
            'object_count': None, 'write_acl': None, 'versions': None,
            'bytes': None}

        self.test_check = check_constraints.filter_factory(
            self.conf)(FakeApp())

    def test_GET(self):
        path = '/V1.0/a/c/o'
        resp = Request.blank(path, environ={'REQUEST_METHOD': 'GET'}
                             ).get_response(self.test_check)
        self.assertEquals(resp.status_int, 200)

    def test_PUT_container(self):
        path = '/V1.0/a/c'
        resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                             ).get_response(self.test_check)
        self.assertEquals(resp.status_int, 200)

    def test_PUT_object_with_double_slashes(self):
        path = '/V1.0/a/c2//o'

        with patch("swiftonfile.swift.common.middleware.check_constraints."
                   "get_container_info", self.container2_info_mock):
            resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                                 ).get_response(self.test_check)
            self.assertEquals(resp.status_int, 400)
            self.assertTrue('Invalid object name' in resp.body)
            self.assertTrue('cannot begin, end, or have' in resp.body)

    def test_PUT_object_end_with_slashes(self):
        path = '/V1.0/a/c2/o/'

        with patch("swiftonfile.swift.common.middleware.check_constraints."
                   "get_container_info", self.container2_info_mock):
            resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                                 ).get_response(self.test_check)
            self.assertEquals(resp.status_int, 400)
            self.assertTrue('Invalid object name' in resp.body)
            self.assertTrue('cannot begin, end, or have' in resp.body)

    def test_PUT_object_named_dot(self):
        path = '/V1.0/a/c2/.'

        with patch("swiftonfile.swift.common.middleware.check_constraints."
                   "get_container_info", self.container2_info_mock):
            resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                                 ).get_response(self.test_check)
            self.assertEquals(resp.status_int, 400)
            self.assertTrue('Invalid object name' in resp.body)
            self.assertTrue('cannot be . or ..' in resp.body)

    def test_PUT_object_wth_long_names(self):
        longname = 'o' * 220
        path = '/V1.0/a/c2/' + longname

        with patch("swiftonfile.swift.common.middleware.check_constraints."
                   "get_container_info", self.container2_info_mock):
            resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                                 ).get_response(self.test_check)
            self.assertEquals(resp.status_int, 200)

        longname = 'o' * 221
        path = '/V1.0/a/c2/' + longname

        with patch("swiftonfile.swift.common.middleware.check_constraints."
                   "get_container_info", self.container2_info_mock):
            resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                                 ).get_response(self.test_check)
            self.assertEquals(resp.status_int, 200)

        longname = 'o' * 222
        path = '/V1.0/a/c2/' + longname

        with patch("swiftonfile.swift.common.middleware.check_constraints."
                   "get_container_info", self.container2_info_mock):
            resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                                 ).get_response(self.test_check)
            self.assertEquals(resp.status_int, 400)
            self.assertTrue('too long' in resp.body)

    def test_PUT_object_with_policy0(self):
        path = '/V1.0/a/c1//o'

        with nested(patch("swiftonfile.swift.common.middleware."
                          "check_constraints.get_container_info",
                          self.container1_info_mock)):
            resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                                 ).get_response(self.test_check)
            self.assertEquals(resp.status_int, 200)

        longname = 'o' * 222
        path = '/V1.0/a/c2/' + longname

        with patch("swiftonfile.swift.common.middleware.check_constraints."
                   "get_container_info", self.container1_info_mock):
            resp = Request.blank(path, environ={'REQUEST_METHOD': 'PUT'}
                                 ).get_response(self.test_check)
            self.assertEquals(resp.status_int, 200)
