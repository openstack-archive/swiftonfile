# Copyright (c) 2012-2013 Red Hat, Inc.
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

""" Tests for gluster.swift.obj.diskfile """

import os
import stat
import errno
import unittest
import tempfile
import shutil
import mock
from mock import Mock, patch
from hashlib import md5

from swift.common.utils import normalize_timestamp
from swift.common.exceptions import DiskFileNotExist, DiskFileError, \
    DiskFileNoSpace

from gluster.swift.common.exceptions import GlusterFileSystemOSError
import gluster.swift.common.utils
import gluster.swift.obj.diskfile
from gluster.swift.obj.diskfile import DiskFile
from gluster.swift.common.utils import DEFAULT_UID, DEFAULT_GID, X_TYPE, \
    X_OBJECT_TYPE, DIR_OBJECT
from gluster.swift.common.fs_utils import Fake_file

from test.unit.common.test_utils import _initxattr, _destroyxattr
from test.unit import FakeLogger

_metadata = {}


def _mapit(filename_or_fd):
    if isinstance(filename_or_fd, int):
        statmeth = os.fstat
    else:
        statmeth = os.lstat
    try:
        stats = statmeth(filename_or_fd)
    except OSError as err:
        if err.errno == errno.ENOENT:
            raise GlusterFileSystemOSError(
                err.errno, '%s, os.fstat(%s)' % (err.strerror, filename_or_fd))
        raise
    return stats.st_ino


def _mock_read_metadata(filename_or_fd):
    global _metadata
    ino = _mapit(filename_or_fd)
    if ino in _metadata:
        md = _metadata[ino].copy()
    else:
        md = {}
    return md


def _mock_write_metadata(filename_or_fd, metadata):
    global _metadata
    ino = _mapit(filename_or_fd)
    _metadata[ino] = metadata.copy()


def _mock_clear_metadata():
    global _metadata
    _metadata = {}


class MockException(Exception):
    pass


def _mock_rmobjdir(p):
    raise MockException("gluster.swift.obj.diskfile.rmobjdir() called")


def _mock_do_fsync(fd):
    return


class MockRenamerCalled(Exception):
    pass


def _mock_renamer(a, b):
    raise MockRenamerCalled()


class TestDiskFile(unittest.TestCase):
    """ Tests for gluster.swift.obj.diskfile """

    def setUp(self):
        self.lg = FakeLogger()
        _initxattr()
        _mock_clear_metadata()
        self._saved_df_wm = gluster.swift.obj.diskfile.write_metadata
        self._saved_df_rm = gluster.swift.obj.diskfile.read_metadata
        gluster.swift.obj.diskfile.write_metadata = _mock_write_metadata
        gluster.swift.obj.diskfile.read_metadata = _mock_read_metadata
        self._saved_ut_wm = gluster.swift.common.utils.write_metadata
        self._saved_ut_rm = gluster.swift.common.utils.read_metadata
        gluster.swift.common.utils.write_metadata = _mock_write_metadata
        gluster.swift.common.utils.read_metadata = _mock_read_metadata
        self._saved_do_fsync = gluster.swift.obj.diskfile.do_fsync
        gluster.swift.obj.diskfile.do_fsync = _mock_do_fsync
        self.td = tempfile.mkdtemp()

    def tearDown(self):
        self.lg = None
        _destroyxattr()
        gluster.swift.obj.diskfile.write_metadata = self._saved_df_wm
        gluster.swift.obj.diskfile.read_metadata = self._saved_df_rm
        gluster.swift.common.utils.write_metadata = self._saved_ut_wm
        gluster.swift.common.utils.read_metadata = self._saved_ut_rm
        gluster.swift.obj.diskfile.do_fsync = self._saved_do_fsync
        shutil.rmtree(self.td)

    def _get_diskfile(self, d, p, a, c, o, **kwargs):
        return DiskFile(self.td, d, p, a, c, o, self.lg, **kwargs)

    def test_constructor_no_slash(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        assert gdf._obj_path == ""
        assert gdf.name == "bar"
        assert gdf.datadir == os.path.join(self.td, "vol0", "bar")
        assert gdf.device_path == os.path.join(self.td, "vol0")
        assert gdf._container_path == os.path.join(self.td, "vol0", "bar")
        assert gdf.disk_chunk_size == 65536
        assert gdf.iter_hook is None
        assert gdf.logger == self.lg
        assert gdf.uid == DEFAULT_UID
        assert gdf.gid == DEFAULT_GID
        assert gdf._metadata == None
        assert gdf.data_file is None
        assert gdf.fp is None
        assert gdf.iter_etag is None
        assert not gdf.started_at_0
        assert not gdf.read_to_eof
        assert gdf.quarantined_dir is None
        assert not gdf.keep_cache
        assert not gdf._is_dir

    def test_constructor_leadtrail_slash(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "/b/a/z/")
        assert gdf._obj == "z"
        assert gdf._obj_path == os.path.join("b", "a")
        assert gdf.name == os.path.join("bar", "b", "a")
        assert gdf.datadir == os.path.join(self.td, "vol0", "bar", "b", "a")
        assert gdf.device_path == os.path.join(self.td, "vol0")

    def test_open_no_logging_on_enoent(self):

        def _mock_do_open(path, flags):
            raise GlusterFileSystemOSError(errno.ENOENT,
                                           os.strerror(errno.ENOENT))

        with patch("gluster.swift.obj.diskfile.do_open",
            _mock_do_open):
            gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
            gdf.logger = Mock()
            gdf.open()
            self.assertEqual(0, gdf.logger.exception.call_count)

    def test_open_logging_on_no_enoent(self):
        def _mock_do_open(path, flags):
            raise GlusterFileSystemOSError(errno.EIO,
                                           os.strerror(errno.EIO))

        with patch("gluster.swift.obj.diskfile.do_open",
            _mock_do_open):
            gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
            gdf.logger = Mock()
            gdf.open()
            self.assertEqual(1, gdf.logger.exception.call_count)

    def test_open_no_metadata(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        stats = os.stat(the_file)
        ts = normalize_timestamp(stats.st_ctime)
        etag = md5()
        etag.update("1234")
        etag = etag.hexdigest()
        exp_md = {
            'Content-Length': 4,
            'ETag': etag,
            'X-Timestamp': ts,
            'Content-Type': 'application/octet-stream'}
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            assert gdf.data_file == the_file
            assert not gdf._is_dir
            assert gdf.fp is not None
            assert gdf._metadata == exp_md

    def test_open_existing_metadata(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        ini_md = {
            'X-Type': 'Object',
            'X-Object-Type': 'file',
            'Content-Length': 5,
            'ETag': 'etag',
            'X-Timestamp': 'ts',
            'Content-Type': 'application/loctet-stream'}
        _metadata[_mapit(the_file)] = ini_md
        exp_md = ini_md.copy()
        del exp_md['X-Type']
        del exp_md['X-Object-Type']
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            assert gdf.data_file == the_file
            assert not gdf._is_dir
            assert gdf.fp is not None
            assert gdf._metadata == exp_md

    def test_open_invalid_existing_metadata(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        inv_md = {
            'Content-Length': 5,
            'ETag': 'etag',
            'X-Timestamp': 'ts',
            'Content-Type': 'application/loctet-stream'}
        _metadata[_mapit(the_file)] = inv_md
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            assert gdf.data_file == the_file
            assert not gdf._is_dir
            assert gdf.fp is not None
            assert gdf._metadata != inv_md

    def test_open_isdir(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_path, "d")
        os.makedirs(the_dir)
        ini_md = {
            'X-Type': 'Object',
            'X-Object-Type': 'dir',
            'Content-Length': 5,
            'ETag': 'etag',
            'X-Timestamp': 'ts',
            'Content-Type': 'application/loctet-stream'}
        _metadata[_mapit(the_dir)] = ini_md
        exp_md = ini_md.copy()
        del exp_md['X-Type']
        del exp_md['X-Object-Type']
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "d")
        assert gdf._obj == "d"
        with gdf.open():
            assert gdf.data_file == the_dir
            assert gdf._is_dir
            assert gdf._metadata == exp_md

    def test_constructor_chunk_size(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z",
                                 disk_chunk_size=8192)
        assert gdf.disk_chunk_size == 8192

    def test_constructor_iter_hook(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z",
                                 iter_hook='hook')
        assert gdf.iter_hook == 'hook'

    def test_close_no_open_fp(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        gdf._is_dir = False
        self.called = False

        def our_do_close(fp):
            self.called = True

        with mock.patch("gluster.swift.obj.diskfile.do_close", our_do_close):
            gdf.close()
            assert not self.called
            assert gdf.fp is None

    def test_all_dir_object(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        the_dir = "dir"
        self.called = False
        os.makedirs(os.path.join(the_cont, the_dir))
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir")
        with gdf.open():
            ret = isinstance(gdf.fp, Fake_file)
            self.assertTrue(ret)

            # Get a "Fake_file" pointer
            ffp = gdf.fp

            # This expected to call Fake_file interfaces
            ret = ffp.tell()
            self.assertEqual(ret, 0)

            ret = ffp.read(1)
            self.assertEqual(ret, None)

            ret = ffp.fileno()
            self.assertEqual(ret, -1)

            def our_do_close(ffp):
                self.called = True

            with mock.patch("gluster.swift.obj.diskfile.do_close",
                            our_do_close):
                ret = ffp.close()
            self.assertEqual(ret, None)
            self.assertFalse(self.called)

    def test_close_file_object(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_cont, "z")
        self.called = False
        os.makedirs(the_cont)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")

        def our_do_close(fp):
            self.called = True

        with mock.patch("gluster.swift.obj.diskfile.do_close",
                        our_do_close):
            with gdf.open():
                assert not self.called
            assert self.called

    def test_is_deleted(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        with gdf.open():
            assert gdf.is_deleted()
            gdf.data_file = os.path.join(self.td, "bar")
            assert not gdf.is_deleted()

    def test_create_dir_object_no_md(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        the_dir = "dir"
        os.makedirs(the_cont)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar",
                                 os.path.join(the_dir, "z"))
        # Not created, dir object path is different, just checking
        assert gdf._obj == "z"
        gdf._create_dir_object(the_dir)
        full_dir_path = os.path.join(the_cont, the_dir)
        assert os.path.isdir(full_dir_path)
        assert _mapit(full_dir_path) not in _metadata

    def test_create_dir_object_with_md(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        the_dir = "dir"
        os.makedirs(the_cont)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar",
                                 os.path.join(the_dir, "z"))
        # Not created, dir object path is different, just checking
        assert gdf._obj == "z"
        dir_md = {'Content-Type': 'application/directory',
                  X_OBJECT_TYPE: DIR_OBJECT}
        gdf._create_dir_object(the_dir, dir_md)
        full_dir_path = os.path.join(the_cont, the_dir)
        assert os.path.isdir(full_dir_path)
        assert _mapit(full_dir_path) in _metadata

    def test_create_dir_object_exists(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_path, "dir")
        os.makedirs(the_path)
        with open(the_dir, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir/z")
        # Not created, dir object path is different, just checking
        assert gdf._obj == "z"

        def _mock_do_chown(p, u, g):
            assert u == DEFAULT_UID
            assert g == DEFAULT_GID

        dc = gluster.swift.obj.diskfile.do_chown
        gluster.swift.obj.diskfile.do_chown = _mock_do_chown
        self.assertRaises(
            DiskFileError, gdf._create_dir_object, the_dir)
        gluster.swift.obj.diskfile.do_chown = dc
        self.assertFalse(os.path.isdir(the_dir))
        self.assertFalse(_mapit(the_dir) in _metadata)

    def test_create_dir_object_do_stat_failure(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_path, "dir")
        os.makedirs(the_path)
        with open(the_dir, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir/z")
        # Not created, dir object path is different, just checking
        assert gdf._obj == "z"

        def _mock_do_chown(p, u, g):
            assert u == DEFAULT_UID
            assert g == DEFAULT_GID

        dc = gluster.swift.obj.diskfile.do_chown
        gluster.swift.obj.diskfile.do_chown = _mock_do_chown
        self.assertRaises(
            DiskFileError, gdf._create_dir_object, the_dir)
        gluster.swift.obj.diskfile.do_chown = dc
        self.assertFalse(os.path.isdir(the_dir))
        self.assertFalse(_mapit(the_dir) in _metadata)

    def test_put_metadata(self):
        the_dir = os.path.join(self.td, "vol0", "bar", "z")
        os.makedirs(the_dir)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        md = {'Content-Type': 'application/octet-stream', 'a': 'b'}
        gdf.put_metadata(md.copy())
        assert gdf._metadata is None
        fmd = _metadata[_mapit(the_dir)]
        md.update({'X-Object-Type': 'file', 'X-Type': 'Object'})
        assert fmd['a'] == md['a']
        assert fmd['Content-Type'] == md['Content-Type']

    def test_add_metadata_to_existing_file(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        ini_md = {
            'X-Type': 'Object',
            'X-Object-Type': 'file',
            'Content-Length': 4,
            'ETag': 'etag',
            'X-Timestamp': 'ts',
            'Content-Type': 'application/loctet-stream'}
        _metadata[_mapit(the_file)] = ini_md
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        md = {'Content-Type': 'application/octet-stream', 'a': 'b'}
        gdf.put_metadata(md.copy())
        self.assertTrue(_metadata[_mapit(the_file)]['a'], 'b')
        newmd = {'X-Object-Meta-test':'1234'}
        gdf.put_metadata(newmd.copy())
        on_disk_md = _metadata[_mapit(the_file)]
        self.assertTrue(on_disk_md['Content-Length'], 4)
        self.assertTrue(on_disk_md['X-Object-Meta-test'], '1234')
        self.assertTrue(on_disk_md['X-Type'], 'Object')
        self.assertTrue(on_disk_md['X-Object-Type'], 'file')
        self.assertTrue(on_disk_md['ETag'], 'etag')
        self.assertFalse('a' in on_disk_md)

    def test_add_md_to_existing_file_with_md_in_gdf(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        ini_md = {
            'X-Type': 'Object',
            'X-Object-Type': 'file',
            'Content-Length': 4,
            'name': 'z',
            'ETag': 'etag',
            'X-Timestamp': 'ts'}
        _metadata[_mapit(the_file)] = ini_md
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")

        # make sure gdf has the _metadata
        gdf.open()
        md = {'a': 'b'}
        gdf.put_metadata(md.copy())
        self.assertTrue(_metadata[_mapit(the_file)]['a'], 'b')
        newmd = {'X-Object-Meta-test':'1234'}
        gdf.put_metadata(newmd.copy())
        on_disk_md = _metadata[_mapit(the_file)]
        self.assertTrue(on_disk_md['Content-Length'], 4)
        self.assertTrue(on_disk_md['X-Object-Meta-test'], '1234')
        self.assertFalse('a' in on_disk_md)

    def test_add_metadata_to_existing_dir(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_cont, "dir")
        os.makedirs(the_dir)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir")
        self.assertEquals(gdf._metadata, None)
        init_md = {
            'X-Type': 'Object',
            'Content-Length': 0,
            'ETag': 'etag',
            'X-Timestamp': 'ts',
            'X-Object-Meta-test':'test',
            'Content-Type': 'application/directory'}
        _metadata[_mapit(the_dir)] = init_md

        md = {'X-Object-Meta-test':'test'}
        gdf.put_metadata(md.copy())
        self.assertEqual(_metadata[_mapit(the_dir)]['X-Object-Meta-test'],
                'test')
        self.assertEqual(_metadata[_mapit(the_dir)]['Content-Type'].lower(),
                'application/directory')

        # set new metadata
        newmd = {'X-Object-Meta-test2':'1234'}
        gdf.put_metadata(newmd.copy())
        self.assertEqual(_metadata[_mapit(the_dir)]['Content-Type'].lower(),
                'application/directory')
        self.assertEqual(_metadata[_mapit(the_dir)]["X-Object-Meta-test2"],
                '1234')
        self.assertEqual(_metadata[_mapit(the_dir)]['X-Object-Type'],
                DIR_OBJECT)
        self.assertFalse('X-Object-Meta-test' in _metadata[_mapit(the_dir)])

    def test_put_w_tombstone(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._metadata == None

        gdf.put_metadata({'x': '1'}, tombstone=True)
        assert gdf._metadata is None
        assert _metadata == {}

    def test_put_w_meta_file(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        with gdf.open():
            newmd = gdf.get_metadata().copy()
            newmd['X-Object-Meta-test'] = '1234'
        gdf.put_metadata(newmd)
        assert gdf._metadata is None
        fmd = _metadata[_mapit(the_file)]
        assert fmd == newmd, "on-disk md = %r, newmd = %r" % (fmd, newmd)

    def test_put_w_meta_file_no_content_type(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        with gdf.open():
            newmd = gdf.get_metadata().copy()
            newmd['Content-Type'] = ''
            newmd['X-Object-Meta-test'] = '1234'
        gdf.put_metadata(newmd)
        assert gdf._metadata is None
        fmd = _metadata[_mapit(the_file)]
        assert fmd == newmd, "on-disk md = %r, newmd = %r" % (fmd, newmd)

    def test_put_w_meta_dir(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_path, "dir")
        os.makedirs(the_dir)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir")
        with gdf.open():
            newmd = gdf.get_metadata().copy()
            newmd['X-Object-Meta-test'] = '1234'
        gdf.put_metadata(newmd)
        assert gdf._metadata is None
        fmd = _metadata[_mapit(the_dir)]
        assert fmd == newmd, "on-disk md = %r, newmd = %r" % (fmd, newmd)

    def test_put_w_marker_dir(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_path, "dir")
        os.makedirs(the_dir)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir")
        with gdf.open():
            newmd = gdf.get_metadata().copy()
            newmd['X-Object-Meta-test'] = '1234'
        gdf.put_metadata(newmd)
        assert gdf._metadata is None
        fmd = _metadata[_mapit(the_dir)]
        assert fmd == newmd, "on-disk md = %r, newmd = %r" % (fmd, newmd)

    def test_put_w_marker_dir_create(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_cont, "dir")
        os.makedirs(the_cont)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir")
        assert gdf._metadata == None
        newmd = {
            'ETag': 'etag',
            'X-Timestamp': 'ts',
            'Content-Type': 'application/directory'}
        with gdf.create() as dw:
            dw.put(newmd.copy(), extension='.dir')
        with gdf.open():
            assert gdf.data_file == the_dir
            for key, val in newmd.items():
                assert gdf._metadata[key] == val
                assert _metadata[_mapit(the_dir)][key] == val
            assert X_OBJECT_TYPE not in gdf._metadata, "md = %r" % gdf._metadata
            assert _metadata[_mapit(the_dir)][X_OBJECT_TYPE] == DIR_OBJECT

    def test_put_is_dir(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_path, "dir")
        os.makedirs(the_dir)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir")
        # FIXME: This is a hack to get to the code-path; it is not clear
        # how this can happen normally.
        newmd = {
            'Content-Type': '',
            'X-Object-Meta-test': '1234'}
        with gdf.create() as dw:
            try:
                dw.put(newmd, extension='.data')
            except DiskFileError:
                pass
            else:
                self.fail("Expected to encounter"
                          " 'already-exists-as-dir' exception")

    def test_put(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        os.makedirs(the_cont)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        assert gdf._obj_path == ""
        assert gdf.name == "bar"
        assert gdf.datadir == the_cont
        assert gdf.data_file is None

        body = '1234\n'
        etag = md5()
        etag.update(body)
        etag = etag.hexdigest()
        metadata = {
            'X-Timestamp': '1234',
            'Content-Type': 'file',
            'ETag': etag,
            'Content-Length': '5',
        }

        with gdf.create() as dw:
            assert dw.tmppath is not None
            tmppath = dw.tmppath
            dw.write(body)
            dw.put(metadata)

        assert gdf.data_file == os.path.join(self.td, "vol0", "bar", "z")
        assert os.path.exists(gdf.data_file)
        assert not os.path.exists(tmppath)

    def test_put_ENOSPC(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        os.makedirs(the_cont)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        assert gdf._obj_path == ""
        assert gdf.name == "bar"
        assert gdf.datadir == the_cont
        assert gdf.data_file is None

        body = '1234\n'
        etag = md5()
        etag.update(body)
        etag = etag.hexdigest()
        metadata = {
            'X-Timestamp': '1234',
            'Content-Type': 'file',
            'ETag': etag,
            'Content-Length': '5',
        }

        def mock_open(*args, **kwargs):
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

        with mock.patch("os.open", mock_open):
            try:
                with gdf.create() as dw:
                    assert dw.tmppath is not None
                    dw.write(body)
                    dw.put(metadata)
            except DiskFileNoSpace:
                pass
            else:
                self.fail("Expected exception DiskFileNoSpace")

    def test_put_rename_ENOENT(self):
        the_cont = os.path.join(self.td, "vol0", "bar")
        os.makedirs(the_cont)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        assert gdf._obj_path == ""
        assert gdf.name == "bar"
        assert gdf.datadir == the_cont
        assert gdf.data_file is None

        body = '1234\n'
        etag = md5()
        etag.update(body)
        etag = etag.hexdigest()
        metadata = {
            'X-Timestamp': '1234',
            'Content-Type': 'file',
            'ETag': etag,
            'Content-Length': '5',
        }

        def mock_sleep(*args, **kwargs):
            # Return without sleep, no need to dely unit tests
            return

        def mock_rename(*args, **kwargs):
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

        with mock.patch("gluster.swift.obj.diskfile.sleep", mock_sleep):
            with mock.patch("os.rename", mock_rename):
                try:
                    with gdf.create() as dw:
                        assert dw.tmppath is not None
                        dw.write(body)
                        dw.put(metadata)
                except GlusterFileSystemOSError:
                    pass
                else:
                    self.fail("Expected exception DiskFileError")

    def test_put_obj_path(self):
        the_obj_path = os.path.join("b", "a")
        the_file = os.path.join(the_obj_path, "z")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", the_file)
        assert gdf._obj == "z"
        assert gdf._obj_path == the_obj_path
        assert gdf.name == os.path.join("bar", "b", "a")
        assert gdf.datadir == os.path.join(self.td, "vol0", "bar", "b", "a")
        assert gdf.data_file is None

        body = '1234\n'
        etag = md5()
        etag.update(body)
        etag = etag.hexdigest()
        metadata = {
            'X-Timestamp': '1234',
            'Content-Type': 'file',
            'ETag': etag,
            'Content-Length': '5',
        }

        with gdf.create() as dw:
            assert dw.tmppath is not None
            tmppath = dw.tmppath
            dw.write(body)
            dw.put(metadata)

        assert gdf.data_file == os.path.join(
            self.td, "vol0", "bar", "b", "a", "z")
        assert os.path.exists(gdf.data_file)
        assert not os.path.exists(tmppath)

    def test_delete_no_metadata(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._metadata == None
        _saved_rmobjdir = gluster.swift.obj.diskfile.rmobjdir
        gluster.swift.obj.diskfile.rmobjdir = _mock_rmobjdir
        try:
            gdf.delete(1.0)
        except MockException as exp:
            self.fail(str(exp))
        finally:
            gluster.swift.obj.diskfile.rmobjdir = _saved_rmobjdir

    def test_delete_same_timestamp(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._metadata == None
        gdf._metadata = {'X-Timestamp': 1}
        _saved_rmobjdir = gluster.swift.obj.diskfile.rmobjdir
        gluster.swift.obj.diskfile.rmobjdir = _mock_rmobjdir
        try:
            gdf.delete(1)
        except MockException as exp:
            self.fail(str(exp))
        finally:
            gluster.swift.obj.diskfile.rmobjdir = _saved_rmobjdir

    def test_delete_file(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            later = float(gdf.get_metadata()['X-Timestamp']) + 1
            assert gdf.data_file == the_file
        gdf.delete(normalize_timestamp(later))
        assert os.path.isdir(gdf.datadir)
        assert not os.path.exists(os.path.join(gdf.datadir, gdf._obj))

    def test_delete_file_not_found(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            later = float(gdf._metadata['X-Timestamp']) + 1
            assert gdf.data_file == the_file
            assert not gdf._is_dir

        # Handle the case the file is not in the directory listing.
        os.unlink(the_file)

        gdf.delete(normalize_timestamp(later))
        assert os.path.isdir(gdf.datadir)
        assert not os.path.exists(os.path.join(gdf.datadir, gdf._obj))

    def test_delete_file_unlink_error(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            assert gdf.data_file == the_file
            assert not gdf._is_dir
            later = float(gdf._metadata['X-Timestamp']) + 1

        def _mock_os_unlink_eacces_err(f):
            raise OSError(errno.EACCES, os.strerror(errno.EACCES))

        stats = os.stat(the_path)
        try:
            os.chmod(the_path, stats.st_mode & (~stat.S_IWUSR))

            # Handle the case os_unlink() raises an OSError
            with patch("os.unlink", _mock_os_unlink_eacces_err):
                try:
                    gdf.delete(normalize_timestamp(later))
                except OSError as e:
                    assert e.errno == errno.EACCES
                else:
                    self.fail("Excepted an OSError when unlinking file")
        finally:
            os.chmod(the_path, stats.st_mode)

        assert os.path.isdir(gdf.datadir)
        assert os.path.exists(os.path.join(gdf.datadir, gdf._obj))

    def test_delete_is_dir(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_path, "d")
        os.makedirs(the_dir)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "d")
        assert gdf._obj == "d"
        with gdf.open():
            assert gdf.data_file == the_dir
            assert gdf._is_dir
            later = float(gdf._metadata['X-Timestamp']) + 1
        gdf.delete(normalize_timestamp(later))
        assert os.path.isdir(gdf.datadir)
        assert not os.path.exists(os.path.join(gdf.datadir, gdf._obj))

    def test_get_data_file_size(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            assert gdf.data_file == the_file
            assert not gdf._is_dir
            assert 4 == gdf.get_data_file_size()

    def test_get_data_file_size_md_restored(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            assert gdf.data_file == the_file
            assert not gdf._is_dir
            assert 4 == gdf._metadata['Content-Length']
            gdf._metadata['Content-Length'] = 3
            assert 4 == gdf.get_data_file_size()
            assert 4 == gdf._metadata['Content-Length']

    def test_get_data_file_size_dne(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar",
                                 "/b/a/z/")
        try:
            gdf.get_data_file_size()
        except DiskFileNotExist:
            pass
        else:
            self.fail("Expected DiskFileNotExist exception")

    def test_get_data_file_size_dne_os_err(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            assert gdf.data_file == the_file
            assert not gdf._is_dir
            gdf.data_file = gdf.data_file + ".dne"
            try:
                gdf.get_data_file_size()
            except DiskFileNotExist:
                pass
            else:
                self.fail("Expected DiskFileNotExist exception")

    def test_get_data_file_size_os_err(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_file = os.path.join(the_path, "z")
        os.makedirs(the_path)
        with open(the_file, "wb") as fd:
            fd.write("1234")
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._obj == "z"
        with gdf.open():
            assert gdf.data_file == the_file
            assert not gdf._is_dir
            stats = os.stat(the_path)
            try:
                os.chmod(the_path, 0)

                def _mock_getsize_eaccess_err(f):
                    raise OSError(errno.EACCES, os.strerror(errno.EACCES))

                with patch("os.path.getsize", _mock_getsize_eaccess_err):
                    try:
                        gdf.get_data_file_size()
                    except OSError as err:
                        assert err.errno == errno.EACCES
                    else:
                        self.fail("Expected OSError exception")
            finally:
                os.chmod(the_path, stats.st_mode)

    def test_get_data_file_size_dir(self):
        the_path = os.path.join(self.td, "vol0", "bar")
        the_dir = os.path.join(the_path, "d")
        os.makedirs(the_dir)
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "d")
        assert gdf._obj == "d"
        with gdf.open():
            assert gdf.data_file == the_dir
            assert gdf._is_dir
            assert 0 == gdf.get_data_file_size()

    def test_filter_metadata(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "z")
        assert gdf._metadata == None
        gdf._filter_metadata()
        assert gdf._metadata == None

        gdf._metadata = {}
        gdf._metadata[X_TYPE] = 'a'
        gdf._metadata[X_OBJECT_TYPE] = 'b'
        gdf._metadata['foobar'] = 'c'
        gdf._filter_metadata()
        assert X_TYPE not in gdf._metadata
        assert X_OBJECT_TYPE not in gdf._metadata
        assert 'foobar' in gdf._metadata

    def test_create(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir/z")
        saved_tmppath = ''
        saved_fd = None
        with gdf.create() as dw:
            assert gdf.datadir == os.path.join(self.td, "vol0", "bar", "dir")
            assert os.path.isdir(gdf.datadir)
            saved_tmppath = dw.tmppath
            assert os.path.dirname(saved_tmppath) == gdf.datadir
            assert os.path.basename(saved_tmppath)[:3] == '.z.'
            assert os.path.exists(saved_tmppath)
            dw.write("123")
            saved_fd = dw.fd
        # At the end of previous with block a close on fd is called.
        # Calling os.close on the same fd will raise an OSError
        # exception and we must catch it.
        try:
            os.close(saved_fd)
        except OSError:
            pass
        else:
            self.fail("Exception expected")
        assert not os.path.exists(saved_tmppath)

    def test_create_err_on_close(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir/z")
        saved_tmppath = ''
        with gdf.create() as dw:
            assert gdf.datadir == os.path.join(self.td, "vol0", "bar", "dir")
            assert os.path.isdir(gdf.datadir)
            saved_tmppath = dw.tmppath
            assert os.path.dirname(saved_tmppath) == gdf.datadir
            assert os.path.basename(saved_tmppath)[:3] == '.z.'
            assert os.path.exists(saved_tmppath)
            dw.write("123")
            # Closing the fd prematurely should not raise any exceptions.
            os.close(dw.fd)
        assert not os.path.exists(saved_tmppath)

    def test_create_err_on_unlink(self):
        gdf = self._get_diskfile("vol0", "p57", "ufo47", "bar", "dir/z")
        saved_tmppath = ''
        with gdf.create() as dw:
            assert gdf.datadir == os.path.join(self.td, "vol0", "bar", "dir")
            assert os.path.isdir(gdf.datadir)
            saved_tmppath = dw.tmppath
            assert os.path.dirname(saved_tmppath) == gdf.datadir
            assert os.path.basename(saved_tmppath)[:3] == '.z.'
            assert os.path.exists(saved_tmppath)
            dw.write("123")
            os.unlink(saved_tmppath)
        assert not os.path.exists(saved_tmppath)
