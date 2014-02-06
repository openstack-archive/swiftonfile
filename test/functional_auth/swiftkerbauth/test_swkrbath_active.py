#!/usr/bin/python

# Copyright (c) 2010-2014 OpenStack Foundation
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

import re
import unittest
from nose import SkipTest
import commands
import os
from test import get_config
from swift.common.bufferedhttp import http_connect_raw as http_connect

config = get_config('func_test')

class Utils:
    @classmethod
    def SwiftKerbAuthPrep(self,
            user=config['username'],domain=config['domain_name'],\
                passwd=config['password']):
        username = '%s@%s' % (user, domain)
        return commands.getstatusoutput('kinit %s <<< %s' % (username, passwd))

    @classmethod
    def SwiftKerbAuthCleanAll(self):
        return commands.getstatusoutput('kdestroy')


class TestSwKrbAthActive(unittest.TestCase):
    def setUp(self):
        #Perform kinit in active mode.
        (status, output) = Utils.SwiftKerbAuthPrep()
        self.assertEqual(status, 0, \
                'swkrbauth prep failed with valid credentials'+output)
        self.auth_host = config['auth_host']
        self.auth_port = int(config['auth_port'])
        self.auth_prefix = config.get('auth_prefix', '/auth/')
        self.auth_version = str(config.get('auth_version', '1'))
        self.account_name = config['account']
        self.username = config['username']
        self.password = config['password']
        self.auth_scheme = config['auth_scheme']

        #Prepare auth_url. e.g. http://client.rhelbox.com:8080/auth/v1.0
        if self.auth_version == "1":
            self.auth_path = '%sv1.0' % (self.auth_prefix)
        else:
            self.auth_path = self.auth_prefix
        self.auth_netloc = "%s:%d" % (self.auth_host, self.auth_port)
        auth_url = self.auth_scheme + self.auth_netloc + self.auth_path

        #Obtain the X-Auth-Token from kerberos server to use it in furhter
        #testing
        self.auth_token = None
        (status, output) = commands.getstatusoutput('curl -v -u : --negotiate\
                --location-trusted %s' % (auth_url))
        self.assertEqual(status, 0, 'Token negotiation failed:' +output)
        match = re.search('X-Auth-Token: AUTH.*', output)
        if match:
            self.auth_token = match.group(0).split(':')[1].strip()
        else:
            self.fail('No X-Auth-Token found, failed')

    def tearDown(self):
        Utils.SwiftKerbAuthCleanAll()


    def _get_auth_token(self):
        return {'X-Auth-Token' : self.auth_token}

    def testGetAccounts(self):
        #TODO: The test case is to perform GET on the account mentioned via
        #configuration file. This is a sample test case. The whole test
        #suite can be enhanced further to have further complicated test cases.
        path = '/v1/AUTH_%s' % (config['account'])

        headers = self._get_auth_token()
        conn = http_connect(config['auth_host'], config['auth_port'], 'GET',
                path, headers)
        resp = conn.getresponse()
        self.assertTrue(resp.status == 204)
