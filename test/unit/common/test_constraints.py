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
from mock import Mock, patch
from swiftonfile.swift.common import constraints as cnt


def mock_check_object_creation(*args, **kwargs):
    return None


class TestConstraints(unittest.TestCase):
    """ Tests for common.constraints """

    def test_validate_obj_name_component(self):
        max_obj_len = cnt.SOF_MAX_OBJECT_NAME_LENGTH
        self.assertFalse(
            cnt.validate_obj_name_component('tests' * (max_obj_len / 5)))
        self.assertEqual(cnt.validate_obj_name_component(
            'tests' * 60), 'too long (300)')

    def test_validate_obj_name_component_err(self):
        max_obj_len = cnt.SOF_MAX_OBJECT_NAME_LENGTH
        self.assertTrue(cnt.validate_obj_name_component(
            'tests' * (max_obj_len / 5 + 1)))
        self.assertTrue(cnt.validate_obj_name_component('.'))
        self.assertTrue(cnt.validate_obj_name_component('..'))
        self.assertTrue(cnt.validate_obj_name_component(''))

    def test_sof_check_object_creation(self):
        with patch('swiftonfile.swift.common.constraints.swift_check_object_creation',
                   mock_check_object_creation):
            req = Mock()
            req.headers = []
            self.assertFalse(cnt.sof_check_object_creation(req, 'dir/z'))
