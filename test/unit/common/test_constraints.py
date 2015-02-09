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
from mock import patch, Mock
from swiftonfile.swift.common import constraints as cnt


def mock_check_object_creation(*args, **kwargs):
    return None


class TestConstraints(unittest.TestCase):
    """ Tests for common.constraints """

    def test_validate_obj_name_component(self):
        req = Mock()

        # Non-last object name component - success
        for i in (220, 221, 222, 254, 255):
            obj_comp_name = 'a' * i
            self.assertFalse(cnt.validate_obj_name_component(obj_comp_name,
                                                             req))

        # Last object name component - success
        for i in (220, 221):
            obj_comp_name = 'a' * i
            self.assertFalse(
                cnt.validate_obj_name_component(obj_comp_name, req, True))

    def test_validate_obj_name_component_err(self):
        req = Mock()

        # Non-last object name component - err
        for i in (256, 257):
            obj_comp_name = 'a' * i
            result = cnt.validate_obj_name_component(obj_comp_name, req)
            self.assertTrue(("too long (%d)" % i) in result)

        # Last object name component - err
        for i in (222, 223):
            obj_comp_name = 'a' * i
            result = cnt.validate_obj_name_component(obj_comp_name, req, True)
            self.assertTrue(("too long (%d)" % i) in result)

        self.assertTrue(cnt.validate_obj_name_component('.', req))
        self.assertTrue(cnt.validate_obj_name_component('..', req))
        self.assertTrue(cnt.validate_obj_name_component('', req))

    def test_check_object_creation(self):
        req = Mock()
        req.headers = dict()

        valid_object_names = ["a/b/c/d",
                              '/'.join(("1@3%&*0-", "};+=]|")),
                              '/'.join(('a' * 255, 'b' * 255, 'c' * 221))]
        for o in valid_object_names:
            self.assertFalse(cnt.check_object_creation(req, o))

        invalid_object_names = ["a/./b",
                                "a/b/../d",
                                "a//b",
                                "a/c//",
                                '/'.join(('a' * 256, 'b' * 255, 'c' * 221)),
                                '/'.join(('a' * 255, 'b' * 255, 'c' * 222))]
        for o in invalid_object_names:
            self.assertTrue(cnt.check_object_creation(req, o))

        # Check for creation of directory marker objects that ends with slash
        with patch.dict(req.headers, {'content-type':
                                      'application/directory'}):
            self.assertFalse(cnt.check_object_creation(req, "a/b/c/d/"))

        # Check creation of objects ending with slash having any other content
        # type than application/directory is not allowed
        for content_type in ('text/plain', 'text/html', 'image/jpg',
                             'application/octet-stream', 'blah/blah'):
            with patch.dict(req.headers, {'content-type':
                                          content_type}):
                self.assertTrue(cnt.check_object_creation(req, "a/b/c/d/"))
