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

try:
    import simplejson as json
except ImportError:
    import json
import unittest
from nose import SkipTest
from swift.common.bufferedhttp import http_connect_raw as http_connect
from test import get_config

config = get_config('func_test')

class TestGSWauth(unittest.TestCase):

    def _get_admin_headers(self):
        return {'X-Auth-Admin-User': config['admin_user'],
                'X-Auth-Admin-Key': config['admin_key']}

    def _check_test_account_is_not_registered(self):
        # check account exists
        path = '%sv2/%s' % (config['auth_prefix'], config['account'])

        headers = self._get_admin_headers()
        headers.update({'Content-Length': '0'})
        conn = http_connect(config['auth_host'], config['auth_port'], 'GET',
                path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 404)

    def _register_test_account(self):
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

    def _deregister_test_account(self):
        # delete account in swauth (not a swift account)
        # @see _register_test_account
        path = '%sv2/%s' % (config['auth_prefix'], config['account'])
        headers = self._get_admin_headers()
        headers.update({'Content-Length': '0'})
        conn = http_connect(config['auth_host'], config['auth_port'],
                'DELETE', path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 204)

    def test_register_account(self):
        # check and register account
        self._check_test_account_is_not_registered()
        self._register_test_account()

        try:
            # list account
            path = '%sv2/%s' % (config['auth_prefix'], config['account'])
            headers = self._get_admin_headers()
            conn = http_connect(config['auth_host'], config['auth_port'],
                    'GET', path, headers)
            resp = conn.getresponse()
            body = resp.read()
            info = json.loads(body)
            self.assertEqual(info['account_id'], 'AUTH_test')
            self.assertTrue(resp.status == 200)

        finally:
            # de-register account
            self._deregister_test_account()

    def test_add_user(self):
        # check and register account
        self._check_test_account_is_not_registered()
        self._register_test_account()

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

        try:
            # list user
            headers = self._get_admin_headers()
            conn = http_connect(config['auth_host'], config['auth_port'],
                    'GET', path, headers)
            resp = conn.getresponse()
            body = resp.read()
            self.assertEqual(body, '{"groups": [{"name": "test:tester"}, {"name":'
                ' "test"}, {"name": ".admin"}], "auth": "plaintext:testing"}')
            self.assertTrue(resp.status == 200)

        finally:
            try:
                # delete user
                headers = self._get_admin_headers()
                conn = http_connect(config['auth_host'], config['auth_port'],
                        'DELETE', path, headers)
                resp = conn.getresponse()
                self.assertTrue(resp.status == 204)

            finally:
                # de-register account
                self._deregister_test_account()

    def test_register_invalid_account(self):
        # invalid account
        path = '%sv2/%s' % (config['auth_prefix'], '.test')
        headers = self._get_admin_headers()
        headers.update({'Content-Length': '0'})
        conn = http_connect(config['auth_host'], config['auth_port'], 'PUT',
                path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 400)

    def test_add_invalid_user(self):
        path = '%sv2/%s/%s' % (config['auth_prefix'], config['account'],
                '.invaliduser')
        headers = self._get_admin_headers()
        headers.update({'X-Auth-User-Key': config['password'],
                        'Content-Length': '0',
                        'X-Auth-User-Admin': 'true'})
        conn = http_connect(config['auth_host'], config['auth_port'], 'PUT',
                path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 400)

    def test_register_account_without_admin_rights(self):
        path = '%sv2/%s' % (config['auth_prefix'], config['account'])
        headers = {'X-Auth-Admin-User': config['admin_user']}
        headers.update({'Content-Length': '0'})
        conn = http_connect(config['auth_host'], config['auth_port'], 'PUT',
                path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 403)

    def test_change_user_password(self):
        # check and register account
        self._check_test_account_is_not_registered()
        self._register_test_account()

        try:
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
            print "resp creating user %s" % resp.status
            self.assertTrue(resp.status == 201)

            # change password
            path = '%sv2/%s/%s' % (config['auth_prefix'], config['account'],
                    config['username'])
            headers = self._get_admin_headers()
            headers.update({'X-Auth-User-Key': 'newpassword',
                            'Content-Length': '0',
                            'X-Auth-User-Admin': 'true'})
            conn = http_connect(config['auth_host'], config['auth_port'], 'PUT',
                    path, headers)
            resp = conn.getresponse()
            print "resp changing password %s" % resp.status
            self.assertTrue(resp.status == 201)
        finally:
            try:
                # delete user
                headers = self._get_admin_headers()
                conn = http_connect(config['auth_host'], config['auth_port'],
                        'DELETE', path, headers)
                resp = conn.getresponse()
                self.assertTrue(resp.status == 204)

            finally:
                # de-register account
                self._deregister_test_account()

    def test_change_user_password_without_admin_rights(self):
        # check and register account
        self._check_test_account_is_not_registered()
        self._register_test_account()

        try:
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
            print "resp creating user %s" % resp.status
            self.assertTrue(resp.status == 201)

            # attempt to change password
            path = '%sv2/%s/%s' % (config['auth_prefix'], config['account'],
                    config['username'])
            headers = self._get_admin_headers()
            headers.update({'X-Auth-User-Key': 'newpassword',
                            'Content-Length': '0',
                            'X-Auth-Admin-Key': config['password'],
                            'X-Auth-User-Admin': 'true'})
            conn = http_connect(config['auth_host'], config['auth_port'], 'PUT',
                    path, headers)
            resp = conn.getresponse()
            self.assertTrue(resp.status == 403)

        finally:
            try:
                # delete user
                headers = self._get_admin_headers()
                conn = http_connect(config['auth_host'], config['auth_port'],
                        'DELETE', path, headers)
                resp = conn.getresponse()
                self.assertTrue(resp.status == 204)

            finally:
                # de-register account
                self._deregister_test_account()
