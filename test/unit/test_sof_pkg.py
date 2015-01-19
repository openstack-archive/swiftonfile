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

""" Tests for swiftonfile.swift """

import os
import unittest
import shutil
import tempfile

import swiftonfile.swift as sof


class TestPkgInfo(unittest.TestCase):
    """
    Tests for swiftonfile.swift PkgInfo class.
    """

    def test_constructor(self):
        pi = sof.PkgInfo('a', 'b', 'c', 'd')
        assert pi.canonical_version == 'a'
        assert pi.name == 'c'
        self.assertEqual(pi.release, 'b')
        assert pi.final == 'd'

    def test_pretty_version(self):
        pi = sof.PkgInfo('a', 'b', 'c', False)
        assert pi.pretty_version == 'a-dev'
        pi = sof.PkgInfo('a', 'b', 'c', True)
        assert pi.pretty_version == 'a'

    def test_save_config(self):
        pi = sof.PkgInfo('a', 'b', 'c', 'd')
        td = tempfile.mkdtemp()
        try:
            sc = os.path.join(td, 'saved_config.txt')
            pi.save_config(sc)
            exp = 'NAME=c\nVERSION=a\nRELEASE=b\n'
            contents = file(sc, 'r').read()
            assert contents == exp
        finally:
            shutil.rmtree(td)
