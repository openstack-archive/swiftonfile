#!/usr/bin/python

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

import unittest
from nose import SkipTest
from swift.common.bufferedhttp import http_connect_raw as http_connect
from test import get_config

config = get_config('func_test')

class TestGSWauth(unittest.TestCase):

    def setUp(self):
        #TODO
        None

    def tearDown(self):
        #TODO
        None

    def _get_admin_headers(self):
        return {'X-Auth-Admin-User': config['admin_user'],
                'X-Auth-Admin-Key': config['admin_key']}

    def _check_test_account_does_not_exist(self):
        # check account exists
        path = '%sv2/%s' % (config['auth_prefix'], config['account'])

        headers = self._get_admin_headers()
        headers.update({'Content-Length': '0'})
        conn = http_connect(config['auth_host'], config['auth_port'], 'GET',
                path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 404)

    def _create_test_account(self):
        # create account in swauth (not a swift account)
        # This current version only supports one account per volume
        # and the account name is the same as the volume name
        # still an account must be created with swauth to map
        # swauth accounts with swift accounts
        path = '%sv2/%s' % (config['auth_prefix'], config['account'])
        headers = self._get_admin_headers()
        headers.update({'Content-Length': '0'})
        conn = http_connect(config['auth_host'], config['auth_port'], 'PUT',
                path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 201)

    def _delete_test_account(self):
        # delete account in swauth (not a swift account)
        # @see _create_test_account
        path = '%sv2/%s' % (config['auth_prefix'], config['account'])
        headers = self._get_admin_headers()
        headers.update({'Content-Length': '0'})
        conn = http_connect(config['auth_host'], config['auth_port'],
                'DELETE', path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 204)

    def test_add_account(self):
        self._check_test_account_does_not_exist()
        self._create_test_account()
        self._delete_test_account()

    def test_add_user(self):
        # check and create account
        self._check_test_account_does_not_exist()
        self._create_test_account()

        # create user
        path = '%sv2/%s/%s' % (config['auth_prefix'], config['account'],
                config['username'])
        headers = self._get_admin_headers()
        headers.update({'X-Auth-User-Key': config['password'],
                        'Content-Length': '0',
                        'X-Auth-User-Admin': 'true'})
        conn = http_connect(config['auth_host'], config['auth_port'], 'PUT',
                path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 201)
