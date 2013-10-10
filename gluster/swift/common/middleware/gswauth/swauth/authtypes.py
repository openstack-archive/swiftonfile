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


"""
This module hosts available auth types for encoding and matching user keys.
For adding a new auth type, simply write a class that satisfies the following
conditions:

- For the class name, capitalize first letter only. This makes sure the user
  can specify an all-lowercase config option such as "plaintext" or "sha1".
  Swauth takes care of capitalizing the first letter before instantiating it.
- Write an encode(key) method that will take a single argument, the user's key,
  and returns the encoded string. For plaintext, this would be
  "plaintext:<key>"
- Write a match(key, creds) method that will take two arguments: the user's
  key, and the user's retrieved credentials. Return a boolean value that
  indicates whether the match is True or False.

Note that, since some of the encodings will be hashes, swauth supports the
notion of salts. Thus, self.salt will be set to either a user-specified salt
value or to a default value.
"""

import hashlib


#: Maximum length any valid token should ever be.
MAX_TOKEN_LENGTH = 5000


class Plaintext(object):
    """
    Provides a particular auth type for encoding format for encoding and
    matching user keys.

    This class must be all lowercase except for the first character, which
    must be capitalized. encode and match methods must be provided and are
    the only ones that will be used by swauth.
    """
    def encode(self, key):
        """
        Encodes a user key into a particular format. The result of this method
        will be used by swauth for storing user credentials.

        :param key: User's secret key
        :returns: A string representing user credentials
        """
        return "plaintext:%s" % key

    def match(self, key, creds):
        """
        Checks whether the user-provided key matches the user's credentials

        :param key: User-supplied key
        :param creds: User's stored credentials
        :returns: True if the supplied key is valid, False otherwise
        """
        return self.encode(key) == creds


class Sha1(object):
    """
    Provides a particular auth type for encoding format for encoding and
    matching user keys.

    This class must be all lowercase except for the first character, which
    must be capitalized. encode and match methods must be provided and are
    the only ones that will be used by swauth.
    """
    def encode(self, key):
        """
        Encodes a user key into a particular format. The result of this method
        will be used by swauth for storing user credentials.

        :param key: User's secret key
        :returns: A string representing user credentials
        """
        enc_key = '%s%s' % (self.salt, key)
        enc_val = hashlib.sha1(enc_key).hexdigest()
        return "sha1:%s$%s" % (self.salt, enc_val)

    def match(self, key, creds):
        """
        Checks whether the user-provided key matches the user's credentials

        :param key: User-supplied key
        :param creds: User's stored credentials
        :returns: True if the supplied key is valid, False otherwise
        """
        return self.encode(key) == creds
