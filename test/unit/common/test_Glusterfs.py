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
import os, fcntl, errno, shutil
import time
import StringIO
import mock
from tempfile import mkdtemp
import swiftonfile.swift.common.Glusterfs as gfs

def mock_os_path_ismount_false(path):
    return False

def mock_os_path_ismount(path):
    return True

def mock_get_export_list():
    return ['test', 'test2']

def mock_os_system(cmd):
    return False

def mock_fcntl_lockf(f, *a, **kw):
    raise IOError(errno.EAGAIN, os.strerror(errno.EAGAIN))

def mock_time_sleep(secs):
    return True

def _init():
    global _RUN_DIR, _OS_SYSTEM, _FCNTL_LOCKF
    global _OS_PATH_ISMOUNT, __GET_EXPORT_LIST

    _RUN_DIR          = gfs.RUN_DIR
    _OS_SYSTEM        = os.system
    _FCNTL_LOCKF      = fcntl.lockf
    _OS_PATH_ISMOUNT  = os.path.ismount
    __GET_EXPORT_LIST = gfs._get_export_list

def _init_mock_variables(tmpdir):
    os.system            = mock_os_system
    os.path.ismount      = mock_os_path_ismount
    try:
        os.makedirs(os.path.join(tmpdir, "var", "run"))
    except OSError as err:
        if err.errno != errno.EEXIST:
            raise
    gfs.RUN_DIR          = os.path.join(tmpdir, 'var', 'run', 'swift')
    gfs._get_export_list = mock_get_export_list

def _reset_mock_variables():
    gfs.RUN_DIR          = _RUN_DIR
    gfs._get_export_list = __GET_EXPORT_LIST

    os.system       = _OS_SYSTEM
    fcntl.lockf     = _FCNTL_LOCKF
    os.path.ismount = _OS_PATH_ISMOUNT

class TestGlusterfs(unittest.TestCase):
    """ Tests for common.GlusterFS """

    def setUp(self):
        _init()

    def test_busy_wait_timeout(self):
        os.path.ismount = mock_os_path_ismount_false

        # setup time mock
        real_time_sleep = time.sleep
        time.sleep = mock_time_sleep

        try:
            self.assertFalse(gfs._busy_wait("/"))
        finally:
            time.sleep = real_time_sleep

    def test_busy_wait(self):
        self.assertTrue(gfs._busy_wait("/"))

    def test_mount(self):
        try:
            tmpdir = mkdtemp()
            root   = os.path.join(tmpdir, 'mnt/swiftonfile')
            drive  = 'test'

            _init_mock_variables(tmpdir)
            assert gfs.mount(root, drive)
        finally:
            _reset_mock_variables()
            shutil.rmtree(tmpdir)

    def test_mount_egain(self):
        try:
            tmpdir = mkdtemp()
            root   = os.path.join(tmpdir, 'mnt/swiftonfile')
            drive  = 'test'

            _init_mock_variables(tmpdir)
            assert gfs.mount(root, drive)
            fcntl.lockf  = mock_fcntl_lockf
            assert gfs.mount(root, drive)
        finally:
            shutil.rmtree(tmpdir)

    def test_mount_get_export_list_err(self):
        try:
            tmpdir = mkdtemp()
            root   = os.path.join(tmpdir, 'mnt/swiftonfile')
            drive  = 'test3'

            _init_mock_variables(tmpdir)
            gfs._get_export_list = mock_get_export_list
            assert not gfs.mount(root, drive)
        finally:
            shutil.rmtree(tmpdir)

    def test_get_drive_mount_point_name_unique_id_None(self):
        """
        Using the public method mount to test _get_drive_mount_point_name
        """
        try:
            tmpdir = mkdtemp()
            root   = os.path.join(tmpdir, 'mnt/swiftonfile')
            drive  = 'test'

            _init_mock_variables(tmpdir)
            gfs._allow_mount_per_server = True
            self.assertTrue(gfs.mount(root, drive))
        finally:
            gfs._allow_mount_per_server = False
            _reset_mock_variables()
            shutil.rmtree(tmpdir)

    def test_get_drive_mount_point_name_unique_id_exists(self):
        """
        Using the public method mount to test _get_drive_mount_point_name
        and the _unique_id is already defined
        """
        try:
            tmpdir = mkdtemp()
            root   = os.path.join(tmpdir, 'mnt/swiftonfile')
            drive  = 'test'

            _init_mock_variables(tmpdir)
            gfs._allow_mount_per_server = True
            gfs._unique_id = 0
            self.assertTrue(gfs.mount(root, drive))
        finally:
            gfs._allow_mount_per_server = False
            gfs._unique_id = None
            _reset_mock_variables()
            shutil.rmtree(tmpdir)

    def test_invalid_drive_name(self):
        try:
            tmpdir = mkdtemp()
            root   = os.path.join(tmpdir, 'mnt/swiftonfile')
            drive  = 'te st'

            _init_mock_variables(tmpdir)
            self.assertFalse(gfs.mount(root, drive))
        finally:
            _reset_mock_variables()
            shutil.rmtree(tmpdir)

    def test_already_mounted(self):
        try:
            tmpdir = mkdtemp()
            root   = os.path.join(tmpdir, 'mnt/swiftonfile')
            drive  = 'test'

            _init_mock_variables(tmpdir)
            def mock_do_ismount(path):
                return True

            with mock.patch("swiftonfile.swift.common.Glusterfs.do_ismount",
                mock_do_ismount):
                self.assertTrue(gfs.mount(root, drive))
        finally:
            _reset_mock_variables()
            shutil.rmtree(tmpdir)

    def test_get_export_list(self):
        try:
            tmpdir = mkdtemp()
            root   = os.path.join(tmpdir, 'mnt/swiftonfile-object')
            drive  = 'test'

            # undo mocking of _get_export_list
            tmp_get_export_list = gfs._get_export_list
            _init_mock_variables(tmpdir)
            gfs._get_export_list = tmp_get_export_list

            def mock_os_popen(cmd):
                mock_string = """
                Volume Name: test
                Type: Distribute
                Volume ID: 361cfe52-75c0-4a76-88af-0092a92270b5
                Status: Started
                Number of Bricks: 1
                Transport-type: tcp
                Bricks:
                Brick1: myhost:/export/brick/test

                Volume Name: test2
                Type: Distribute
                Volume ID: a6df4e2b-6040-4e19-96f1-b8d8c0a29528
                Status: Started
                Number of Bricks: 1
                Transport-type: tcp
                Bricks:
                Brick1: myhost:/export/brick/test2
                """
                return StringIO.StringIO(mock_string)

            # mock os_popen
            with mock.patch('os.popen', mock_os_popen):
                self.assertTrue(gfs.mount(root, drive))
        finally:
            _reset_mock_variables()
            shutil.rmtree(tmpdir)

    def tearDown(self):
        _reset_mock_variables()
