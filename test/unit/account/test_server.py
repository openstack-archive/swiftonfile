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

""" Tests for gluster.swift.account.server subclass """

import os
import errno
import unittest
from nose import SkipTest

import gluster.swift.common.Glusterfs

gluster.swift.common.Glusterfs.RUN_DIR = '/tmp/gluster_unit_tests/run'
try:
    os.makedirs(gluster.swift.common.Glusterfs.RUN_DIR)
except OSError as e:
    if e.errno != errno.EEXIST:
        raise

import gluster.swift.account.server as server


class TestAccountServer(unittest.TestCase):
    """
    Tests for account server subclass.
    """

    def test_constructor(self):
        raise SkipTest
