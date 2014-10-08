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
from mock import Mock
from swiftonfile.swift.common import constraints as cnt


def mock_check_object_creation(*args, **kwargs):
    return None


class TestConstraints(unittest.TestCase):
    """ Tests for common.constraints """

    def test_validate_obj_name_component(self):

        # Non-last object name component - success
        for i in (220, 221, 222, 254, 255):
            obj_comp_name = 'a' * i
            self.assertFalse(cnt.validate_obj_name_component(obj_comp_name))

        # Last object name component - success
        for i in (220, 221):
            obj_comp_name = 'a' * i
            self.assertFalse(
                cnt.validate_obj_name_component(obj_comp_name, True))

    def test_validate_obj_name_component_err(self):

        # Non-last object name component - err
        for i in (256, 257):
            obj_comp_name = 'a' * i
            result = cnt.validate_obj_name_component(obj_comp_name)
            self.assertEqual(result, "too long (%d)" % i)

        # Last object name component - err
        for i in (222, 223):
            obj_comp_name = 'a' * i
            result = cnt.validate_obj_name_component(obj_comp_name, True)
            self.assertEqual(result, "too long (%d)" % i)

        self.assertTrue(cnt.validate_obj_name_component('.'))
        self.assertTrue(cnt.validate_obj_name_component('..'))
        self.assertTrue(cnt.validate_obj_name_component(''))

    def test_check_object_creation(self):
        req = Mock()
        req.headers = []

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
