# Copyright (c) 2013 Red Hat, Inc.
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
import swift.common.constraints
from nose import SkipTest
from mock import Mock, patch
from gluster.swift.common import constraints as cnt


def mock_glusterfs_mount(*args, **kwargs):
    return True


def mock_constraints_conf_int(*args, **kwargs):
    return 1000


def mock_check_object_creation(*args, **kwargs):
    return None


def mock_check_mount(*args, **kwargs):
    return True


def mock_check_mount_err(*args, **kwargs):
    return False


class TestConstraints(unittest.TestCase):
    """ Tests for common.constraints """

    def tearDown(self):
        cnt.set_object_name_component_length()

    def test_set_object_name_component_length(self):
        len = cnt.get_object_name_component_length()
        cnt.set_object_name_component_length(len+1)
        self.assertEqual(len, cnt.get_object_name_component_length()-1)

        if hasattr(swift.common.constraints, 'constraints_conf_int'):
            len = swift.common.constraints.constraints_conf_int(
                'max_object_name_component_length', 255)
            cnt.set_object_name_component_length()
            self.assertEqual(len, cnt.get_object_name_component_length())

        with patch('swift.common.constraints.constraints_conf_int',
                   mock_constraints_conf_int):
            cnt.set_object_name_component_length()
            self.assertEqual(cnt.get_object_name_component_length(), 1000)

    def test_validate_obj_name_component(self):
        max_obj_len = cnt.get_object_name_component_length()
        self.assertFalse(cnt.validate_obj_name_component('tests'*(max_obj_len/5)))
        cnt.set_object_name_component_length(300)
        self.assertFalse(cnt.validate_obj_name_component('tests'*60))

    def test_validate_obj_name_component_err(self):
        max_obj_len = cnt.get_object_name_component_length()
        self.assertTrue(cnt.validate_obj_name_component('tests'*(max_obj_len/5+1)))
        self.assertTrue(cnt.validate_obj_name_component('.'))
        self.assertTrue(cnt.validate_obj_name_component('..'))
        self.assertTrue(cnt.validate_obj_name_component(''))

    def test_validate_headers(self):
        req = Mock()
        req.headers = []
        self.assertEqual(cnt.validate_headers(req), '')
        req.headers = ['x-some-header']
        self.assertEqual(cnt.validate_headers(req), '')
        #TODO: Although we now support x-delete-at and x-delete-after,
        #retained this test case as we may add some other header to
        #unsupported list in future
        raise SkipTest
        req.headers = ['x-delete-at', 'x-some-header']
        self.assertNotEqual(cnt.validate_headers(req), '')
        req.headers = ['x-delete-after', 'x-some-header']
        self.assertNotEqual(cnt.validate_headers(req), '')
        req.headers = ['x-delete-at', 'x-delete-after', 'x-some-header']
        self.assertNotEqual(cnt.validate_headers(req), '')

    def test_validate_headers_ignoring_config_set(self):
        with patch('gluster.swift.common.constraints.'
                   'Glusterfs._ignore_unsupported_headers', True):
            req = Mock()
            req.headers = []
            self.assertEqual(cnt.validate_headers(req), '')
            req.headers = ['x-some-header']
            self.assertEqual(cnt.validate_headers(req), '')
            #TODO: Although we now support x-delete-at and x-delete-after,
            #retained this test case as we may add some other header to
            #unsupported list in future
            raise SkipTest
            req.headers = ['x-delete-at', 'x-some-header']
            self.assertEqual(cnt.validate_headers(req), '')
            req.headers = ['x-delete-after', 'x-some-header']
            self.assertEqual(cnt.validate_headers(req), '')
            req.headers = ['x-delete-at', 'x-delete-after', 'x-some-header']
            self.assertEqual(cnt.validate_headers(req), '')

    def test_gluster_check_metadata(self):
        mock_check_metadata = Mock()
        with patch('gluster.swift.common.constraints.__check_metadata',
                   mock_check_metadata):
            req = Mock()
            req.headers = []
            cnt.gluster_check_metadata(req, 'object')
            self.assertTrue(1, mock_check_metadata.call_count)
            cnt.gluster_check_metadata(req, 'object', POST=False)
            self.assertTrue(1, mock_check_metadata.call_count)
            req.headers = ['x-some-header']
            self.assertEqual(cnt.gluster_check_metadata(req, 'object', POST=False), None)
            #TODO: Although we now support x-delete-at and x-delete-after,
            #retained this test case as we may add some other header to
            #unsupported list in future
            raise SkipTest
            req.headers = ['x-delete-at', 'x-some-header']
            self.assertNotEqual(cnt.gluster_check_metadata(req, 'object', POST=False), None)
            req.headers = ['x-delete-after', 'x-some-header']
            self.assertNotEqual(cnt.gluster_check_metadata(req, 'object', POST=False), None)
            req.headers = ['x-delete-at', 'x-delete-after', 'x-some-header']
            self.assertNotEqual(cnt.gluster_check_metadata(req, 'object', POST=False), None)

    def test_gluster_check_object_creation(self):
        with patch('gluster.swift.common.constraints.__check_object_creation',
                   mock_check_object_creation):
            req = Mock()
            req.headers = []
            self.assertFalse(cnt.gluster_check_object_creation(req, 'dir/z'))

    def test_gluster_check_object_creation_err(self):
        with patch('gluster.swift.common.constraints.__check_object_creation',
                   mock_check_object_creation):
            req = Mock()
            req.headers = []
            self.assertTrue(cnt.gluster_check_object_creation(req, 'dir/.'))
            #TODO: Although we now support x-delete-at and x-delete-after,
            #retained this test case as we may add some other header to
            #unsupported list in future
            raise SkipTest
            req.headers = ['x-delete-at']
            self.assertTrue(cnt.gluster_check_object_creation(req, 'dir/z'))
