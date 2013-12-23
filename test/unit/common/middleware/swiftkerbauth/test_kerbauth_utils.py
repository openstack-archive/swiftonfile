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
import re
from time import time
from test.unit import FakeMemcache
from gluster.swift.common.middleware.swiftkerbauth import kerbauth as auth
from gluster.swift.common.middleware.swiftkerbauth import kerbauth_utils as ku


class TestKerbUtils(unittest.TestCase):

    def test_get_remote_user(self):
        env = {'REMOTE_USER': "auth_admin@EXAMPLE.COM"}
        result = ku.get_remote_user(env)
        self.assertEqual(result, "auth_admin")

    def test_get_remote_user_err(self):
        env = {'REMOTE_USER': "auth_admin"}
        try:
            ku.get_remote_user(env)
        except RuntimeError as err:
            self.assertTrue(err.args[0].startswith("Malformed REMOTE_USER"))
        else:
            self.fail("Expected RuntimeError")

    def test_get_auth_data(self):
        mc = FakeMemcache()
        expiry = time() + 100
        ku.set_auth_data(mc, "root", "AUTH_tk", expiry, "root,admin")
        (token, expires, groups) = ku.get_auth_data(mc, "root")
        self.assertEqual(("AUTH_tk", expiry, "root,admin"),
                         (token, expires, groups))

    def test_get_auth_data_err(self):
        mc = FakeMemcache()
        (token, expires, groups) = ku.get_auth_data(mc, "root")
        self.assertEqual((token, expires, groups), (None, None, None))

        expiry = time() - 1
        ku.set_auth_data(mc, "root", "AUTH_tk", expiry, "root,admin")
        (token, expires, groups) = ku.get_auth_data(mc, "root")
        self.assertEqual((token, expires, groups), (None, None, None))

    def test_set_auth_data(self):
        mc = FakeMemcache()
        expiry = time() + 100
        ku.set_auth_data(mc, "root", "AUTH_tk", expiry, "root,admin")

    def test_generate_token(self):
        token = ku.generate_token()
        matches = re.match('AUTH_tk[a-f0-9]{32}', token)
        self.assertNotEqual(matches, None)

    def test_get_groups(self):
        groups = ku.get_groups("root")
        self.assertTrue("root" in groups)

    def test_get_groups_err(self):
        try:
            ku.get_groups("Zroot")
        except RuntimeError as err:
            self.assertTrue(err.args[0].startswith("Failure running id -G"))
        else:
            self.fail("Expected RuntimeError")
