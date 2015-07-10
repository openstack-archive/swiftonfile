# Copyright (c) 2015 Red Hat, Inc.
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

""" Tests for swiftonfile.swift.obj.server subclass """

import os
from tempfile import mkdtemp
from shutil import rmtree
from eventlet import tpool

from swift.common.swob import Request

from swiftonfile.swift.obj import server as object_server
from swiftonfile.swift.obj import diskfile

import unittest
from test.unit import debug_logger


class TestObjectController(unittest.TestCase):
    """Test swiftonfile.swift.obj.server.ObjectController"""

    def setUp(self):
        self.tmpdir = mkdtemp()
        self.testdir = os.path.join(self.tmpdir,
                                    'tmp_test_sof_TestObjectController')
        conf = {'devices': self.testdir, 'mount_check': 'false'}
        self.object_controller = object_server.ObjectController(
            conf, logger=debug_logger())
        self.object_controller.bytes_per_sync = 1
        self._orig_tpool_exc = tpool.execute
        tpool.execute = lambda f, *args, **kwargs: f(*args, **kwargs)
        self.df_mgr = diskfile.DiskFileManager(conf,
                                               self.object_controller.logger)

    def tearDown(self):
        rmtree(self.tmpdir)
        tpool.execute = self._orig_tpool_exc

    def test_REPLICATE(self):
        req = Request.blank('/sda1/p/suff',
                            environ={'REQUEST_METHOD': 'REPLICATE'},
                            headers={})
        resp = req.get_response(self.object_controller)
        self.assertEquals(resp.status_int, 501)  # HTTPNotImplemented

    def test_REPLICATION(self):
        req = Request.blank('/sda1/p/suff',
                            environ={'REQUEST_METHOD': 'REPLICATION'},
                            headers={})
        resp = req.get_response(self.object_controller)
        self.assertEquals(resp.status_int, 501)  # HTTPNotImplemented
