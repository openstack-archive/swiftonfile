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
#
# Pablo Llopis 2011

import unittest
import gluster.swift.common.middleware.gswauth.swauth.authtypes as authtypes


class TestPlaintext(unittest.TestCase):

    def setUp(self):
        self.auth_encoder = authtypes.Plaintext()

    def test_plaintext_encode(self):
        enc_key = self.auth_encoder.encode('keystring')
        self.assertEquals('plaintext:keystring', enc_key)

    def test_plaintext_valid_match(self):
        creds = 'plaintext:keystring'
        match = self.auth_encoder.match('keystring', creds)
        self.assertEquals(match, True)

    def test_plaintext_invalid_match(self):
        creds = 'plaintext:other-keystring'
        match = self.auth_encoder.match('keystring', creds)
        self.assertEquals(match, False)


class TestSha1(unittest.TestCase):

    def setUp(self):
        self.auth_encoder = authtypes.Sha1()
        self.auth_encoder.salt = 'salt'

    def test_sha1_encode(self):
        enc_key = self.auth_encoder.encode('keystring')
        self.assertEquals('sha1:salt$d50dc700c296e23ce5b41f7431a0e01f69010f06',
                          enc_key)

    def test_sha1_valid_match(self):
        creds = 'sha1:salt$d50dc700c296e23ce5b41f7431a0e01f69010f06'
        match = self.auth_encoder.match('keystring', creds)
        self.assertEquals(match, True)

    def test_sha1_invalid_match(self):
        creds = 'sha1:salt$deadbabedeadbabedeadbabec0ffeebadc0ffeee'
        match = self.auth_encoder.match('keystring', creds)
        self.assertEquals(match, False)


if __name__ == '__main__':
    unittest.main()
