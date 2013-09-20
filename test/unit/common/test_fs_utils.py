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

import os
import shutil
import random
import errno
import unittest
import eventlet
from nose import SkipTest
from mock import patch
from tempfile import mkdtemp, mkstemp
from gluster.swift.common import fs_utils as fs
from gluster.swift.common.exceptions import NotDirectoryError, \
    FileOrDirNotFoundError, GlusterFileSystemOSError, \
    GlusterFileSystemIOError

def mock_os_fsync(fd):
    return True

def mock_os_fdatasync(fd):
    return True


class TestFsUtils(unittest.TestCase):
    """ Tests for common.fs_utils """

    def test_do_walk(self):
        # create directory structure
        tmpparent = mkdtemp()
        try:
            tmpdirs = []
            tmpfiles = []
            for i in range(5):
                tmpdirs.append(mkdtemp(dir=tmpparent).rsplit(os.path.sep, 1)[1])
                tmpfiles.append(mkstemp(dir=tmpparent)[1].rsplit(os.path.sep, \
                                                                     1)[1])

                for path, dirnames, filenames in fs.do_walk(tmpparent):
                    assert path == tmpparent
                    assert dirnames.sort() == tmpdirs.sort()
                    assert filenames.sort() == tmpfiles.sort()
                    break
        finally:
            shutil.rmtree(tmpparent)

    def test_do_ismount_path_does_not_exist(self):
        tmpdir = mkdtemp()
        try:
            assert False == fs.do_ismount(os.path.join(tmpdir, 'bar'))
        finally:
            shutil.rmtree(tmpdir)

    def test_do_ismount_path_not_mount(self):
        tmpdir = mkdtemp()
        try:
            assert False == fs.do_ismount(tmpdir)
        finally:
            shutil.rmtree(tmpdir)

    def test_do_ismount_path_error(self):

        def _mock_os_lstat(path):
            raise OSError(13, "foo")

        tmpdir = mkdtemp()
        try:
            with patch("os.lstat", _mock_os_lstat):
                try:
                    fs.do_ismount(tmpdir)
                except GlusterFileSystemOSError as err:
                    pass
                else:
                    self.fail("Expected GlusterFileSystemOSError")
        finally:
            shutil.rmtree(tmpdir)

    def test_do_ismount_path_is_symlink(self):
        tmpdir = mkdtemp()
        try:
            link = os.path.join(tmpdir, "tmp")
            os.symlink("/tmp", link)
            assert False == fs.do_ismount(link)
        finally:
            shutil.rmtree(tmpdir)

    def test_do_ismount_path_is_root(self):
        assert True == fs.do_ismount('/')

    def test_do_ismount_parent_path_error(self):

        _os_lstat = os.lstat

        def _mock_os_lstat(path):
            if path.endswith(".."):
                raise OSError(13, "foo")
            else:
                return _os_lstat(path)

        tmpdir = mkdtemp()
        try:
            with patch("os.lstat", _mock_os_lstat):
                try:
                    fs.do_ismount(tmpdir)
                except GlusterFileSystemOSError as err:
                    pass
                else:
                    self.fail("Expected GlusterFileSystemOSError")
        finally:
            shutil.rmtree(tmpdir)

    def test_do_ismount_successes_dev(self):

        _os_lstat = os.lstat

        class MockStat(object):
            def __init__(self, mode, dev, ino):
                self.st_mode = mode
                self.st_dev = dev
                self.st_ino = ino

        def _mock_os_lstat(path):
            if path.endswith(".."):
                parent = _os_lstat(path)
                return MockStat(parent.st_mode, parent.st_dev + 1,
                                parent.st_ino)
            else:
                return _os_lstat(path)

        tmpdir = mkdtemp()
        try:
            with patch("os.lstat", _mock_os_lstat):
                try:
                    fs.do_ismount(tmpdir)
                except GlusterFileSystemOSError as err:
                    self.fail("Unexpected exception")
                else:
                    pass
        finally:
            shutil.rmtree(tmpdir)

    def test_do_ismount_successes_ino(self):

        _os_lstat = os.lstat

        class MockStat(object):
            def __init__(self, mode, dev, ino):
                self.st_mode = mode
                self.st_dev = dev
                self.st_ino = ino

        def _mock_os_lstat(path):
            if path.endswith(".."):
                return _os_lstat(path)
            else:
                parent_path = os.path.join(path, "..")
                child = _os_lstat(path)
                parent = _os_lstat(parent_path)
                return MockStat(child.st_mode, parent.st_ino,
                                child.st_dev)

        tmpdir = mkdtemp()
        try:
            with patch("os.lstat", _mock_os_lstat):
                try:
                    fs.do_ismount(tmpdir)
                except GlusterFileSystemOSError as err:
                    self.fail("Unexpected exception")
                else:
                    pass
        finally:
            shutil.rmtree(tmpdir)

    def test_do_open(self):
        _fd, tmpfile = mkstemp()
        try:
            fd = fs.do_open(tmpfile, os.O_RDONLY)
            try:
                os.write(fd, 'test')
            except OSError as err:
                pass
            else:
                self.fail("OSError expected")
            finally:
                os.close(fd)
        finally:
            os.close(_fd)
            os.remove(tmpfile)

    def test_do_open_err_int_mode(self):
        try:
            fs.do_open(os.path.join('/tmp', str(random.random())),
                       os.O_RDONLY)
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail("GlusterFileSystemOSError expected")

    def test_do_write(self):
        fd, tmpfile = mkstemp()
        try:
            cnt = fs.do_write(fd, "test")
            assert cnt == len("test")
        finally:
            os.close(fd)
            os.remove(tmpfile)

    def test_do_write_err(self):
        fd, tmpfile = mkstemp()
        try:
            fd1 = os.open(tmpfile, os.O_RDONLY)
            try:
                fs.do_write(fd1, "test")
            except GlusterFileSystemOSError:
                pass
            else:
                self.fail("GlusterFileSystemOSError expected")
            finally:
                os.close(fd1)
        except GlusterFileSystemOSError as ose:
            self.fail("Open failed with %s" %ose.strerror)
        finally:
            os.close(fd)
            os.remove(tmpfile)

    def test_mkdirs(self):
        try:
            subdir = os.path.join('/tmp', str(random.random()))
            path = os.path.join(subdir, str(random.random()))
            fs.mkdirs(path)
            assert os.path.exists(path)
            assert fs.mkdirs(path)
        finally:
            shutil.rmtree(subdir)

    def test_mkdirs_already_dir(self):
        tmpdir = mkdtemp()
        try:
            fs.mkdirs(tmpdir)
        except (GlusterFileSystemOSError, OSError):
            self.fail("Unexpected exception")
        else:
            pass
        finally:
            shutil.rmtree(tmpdir)

    def test_mkdirs(self):
        tmpdir = mkdtemp()
        try:
            fs.mkdirs(os.path.join(tmpdir, "a", "b", "c"))
        except OSError:
            self.fail("Unexpected exception")
        else:
            pass
        finally:
            shutil.rmtree(tmpdir)

    def test_mkdirs_existing_file(self):
        tmpdir = mkdtemp()
        fd, tmpfile = mkstemp(dir=tmpdir)
        try:
            fs.mkdirs(tmpfile)
        except OSError:
            pass
        else:
            self.fail("Expected GlusterFileSystemOSError exception")
        finally:
            os.close(fd)
            shutil.rmtree(tmpdir)

    def test_mkdirs_existing_file_on_path(self):
        tmpdir = mkdtemp()
        fd, tmpfile = mkstemp(dir=tmpdir)
        try:
            fs.mkdirs(os.path.join(tmpfile, 'b'))
        except OSError:
            pass
        else:
            self.fail("Expected GlusterFileSystemOSError exception")
        finally:
            os.close(fd)
            shutil.rmtree(tmpdir)

    def test_do_mkdir(self):
        try:
            path = os.path.join('/tmp', str(random.random()))
            fs.do_mkdir(path)
            assert os.path.exists(path)
            assert fs.do_mkdir(path) is None
        finally:
            os.rmdir(path)

    def test_do_mkdir_err(self):
        try:
            path = os.path.join('/tmp', str(random.random()), str(random.random()))
            fs.do_mkdir(path)
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail("GlusterFileSystemOSError expected")

    def test_do_listdir(self):
        tmpdir = mkdtemp()
        try:
            subdir = []
            for i in range(5):
                subdir.append(mkdtemp(dir=tmpdir).rsplit(os.path.sep, 1)[1])

            assert subdir.sort() == fs.do_listdir(tmpdir).sort()
        finally:
            shutil.rmtree(tmpdir)

    def test_do_listdir_err(self):
        try:
            path = os.path.join('/tmp', str(random.random()))
            fs.do_listdir(path)
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail("GlusterFileSystemOSError expected")

    def test_do_fstat(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            buf1 = os.stat(tmpfile)
            buf2 = fs.do_fstat(fd)

            assert buf1 == buf2
        finally:
            os.close(fd)
            os.remove(tmpfile)
            os.rmdir(tmpdir)

    def test_do_fstat_err(self):
        try:
            fs.do_fstat(1000)
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail("Expected GlusterFileSystemOSError")


    def test_do_stat(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            buf1 = os.stat(tmpfile)
            buf2 = fs.do_stat(tmpfile)

            assert buf1 == buf2
        finally:
            os.close(fd)
            os.remove(tmpfile)
            os.rmdir(tmpdir)

    def test_do_stat_enoent(self):
        res = fs.do_stat(os.path.join('/tmp', str(random.random())))
        assert res is None

    def test_do_stat_err(self):

        def mock_os_stat_eacces(path):
            raise OSError(errno.EACCES, os.strerror(errno.EACCES))

        try:
            with patch('os.stat', mock_os_stat_eacces):
                fs.do_stat('/tmp')
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail("GlusterFileSystemOSError expected")

    def test_do_stat_eio_once(self):
        count = [0]
        _os_stat = os.stat

        def mock_os_stat_eio(path):
            count[0] += 1
            if count[0] <= 1:
                raise OSError(errno.EIO, os.strerror(errno.EIO))
            return _os_stat(path)

        with patch('os.stat', mock_os_stat_eio):
            fs.do_stat('/tmp') is not None

    def test_do_stat_eio_twice(self):
        count = [0]
        _os_stat = os.stat

        def mock_os_stat_eio(path):
            count[0] += 1
            if count[0] <= 2:
                raise OSError(errno.EIO, os.strerror(errno.EIO))
            return _os_stat(path)

        with patch('os.stat', mock_os_stat_eio):
            fs.do_stat('/tmp') is not None

    def test_do_stat_eio_ten(self):

        def mock_os_stat_eio(path):
            raise OSError(errno.EIO, os.strerror(errno.EIO))

        try:
            with patch('os.stat', mock_os_stat_eio):
                fs.do_stat('/tmp')
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail("GlusterFileSystemOSError expected")

    def test_do_close(self):
        fd, tmpfile = mkstemp()
        try:
            fs.do_close(fd)
            try:
                os.write(fd, "test")
            except OSError:
                pass
            else:
                self.fail("OSError expected")
        finally:
            os.remove(tmpfile)

    def test_do_close_err_fd(self):
        fd, tmpfile = mkstemp()
        try:
            fs.do_close(fd)

            try:
                fs.do_close(fd)
            except GlusterFileSystemOSError:
                pass
            else:
                self.fail("GlusterFileSystemOSError expected")
        finally:
            os.remove(tmpfile)

    def test_do_unlink(self):
        fd, tmpfile = mkstemp()
        try:
            assert fs.do_unlink(tmpfile) is None
            assert not os.path.exists(tmpfile)
            res = fs.do_unlink(os.path.join('/tmp', str(random.random())))
            assert res is None
        finally:
            os.close(fd)

    def test_do_unlink_err(self):
        tmpdir = mkdtemp()
        try:
            fs.do_unlink(tmpdir)
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail('GlusterFileSystemOSError expected')
        finally:
            os.rmdir(tmpdir)

    def test_do_rename(self):
        srcpath = mkdtemp()
        try:
            destpath = os.path.join('/tmp', str(random.random()))
            fs.do_rename(srcpath, destpath)
            assert not os.path.exists(srcpath)
            assert os.path.exists(destpath)
        finally:
            os.rmdir(destpath)

    def test_do_rename_err(self):
        try:
            srcpath = os.path.join('/tmp', str(random.random()))
            destpath = os.path.join('/tmp', str(random.random()))
            fs.do_rename(srcpath, destpath)
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail("GlusterFileSystemOSError expected")

    def test_dir_empty(self):
        tmpdir = mkdtemp()
        try:
            subdir = mkdtemp(dir=tmpdir)
            assert not fs.dir_empty(tmpdir)
            assert fs.dir_empty(subdir)
        finally:
            shutil.rmtree(tmpdir)

    def test_dir_empty_err(self):
        def _mock_os_listdir(path):
            raise OSError(13, "foo")

        with patch("os.listdir", _mock_os_listdir):
            try:
                fs.dir_empty("/tmp")
            except GlusterFileSystemOSError:
                pass
            else:
                self.fail("GlusterFileSystemOSError exception expected")

    def test_dir_empty_notfound(self):
        try:
            assert fs.dir_empty(os.path.join('/tmp', str(random.random())))
        except FileOrDirNotFoundError:
            pass
        else:
            self.fail("FileOrDirNotFoundError exception expected")

    def test_dir_empty_notdir(self):
        fd, tmpfile = mkstemp()
        try:
            try:
                fs.dir_empty(tmpfile)
            except NotDirectoryError:
                pass
            else:
                self.fail("NotDirectoryError exception expected")
        finally:
            os.close(fd)
            os.unlink(tmpfile)

    def test_do_rmdir(self):
        tmpdir = mkdtemp()
        try:
            subdir = mkdtemp(dir=tmpdir)
            fd, tmpfile = mkstemp(dir=tmpdir)
            try:
                fs.do_rmdir(tmpfile)
            except GlusterFileSystemOSError:
                pass
            else:
                self.fail("Expected GlusterFileSystemOSError")
            assert os.path.exists(subdir)
            try:
                fs.do_rmdir(tmpdir)
            except GlusterFileSystemOSError:
                pass
            else:
                self.fail("Expected GlusterFileSystemOSError")
            assert os.path.exists(subdir)
            fs.do_rmdir(subdir)
            assert not os.path.exists(subdir)
        finally:
            os.close(fd)
            shutil.rmtree(tmpdir)

    def test_chown_dir(self):
        tmpdir = mkdtemp()
        try:
            subdir = mkdtemp(dir=tmpdir)
            buf = os.stat(subdir)
            if buf.st_uid == 0:
                raise SkipTest
            else:
                try:
                    fs.do_chown(subdir, 20000, 20000)
                except GlusterFileSystemOSError as ex:
                    if ex.errno != errno.EPERM:
                        self.fail(
                            "Expected GlusterFileSystemOSError(errno=EPERM)")
                else:
                    self.fail("Expected GlusterFileSystemOSError")
        finally:
            shutil.rmtree(tmpdir)

    def test_chown_file(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            buf = os.stat(tmpfile)
            if buf.st_uid == 0:
                raise SkipTest
            else:
                try:
                    fs.do_chown(tmpfile, 20000, 20000)
                except GlusterFileSystemOSError as ex:
                    if ex.errno != errno.EPERM:
                        self.fail(
                            "Expected GlusterFileSystemOSError(errno=EPERM")
                else:
                    self.fail("Expected GlusterFileSystemOSError")
        finally:
            os.close(fd)
            shutil.rmtree(tmpdir)

    def test_chown_file_err(self):
        try:
            fs.do_chown(os.path.join('/tmp', str(random.random())),
                        20000, 20000)
        except GlusterFileSystemOSError:
            pass
        else:
            self.fail("Expected GlusterFileSystemOSError")

    def test_fchown(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            buf = os.stat(tmpfile)
            if buf.st_uid == 0:
                raise SkipTest
            else:
                try:
                    fs.do_fchown(fd, 20000, 20000)
                except GlusterFileSystemOSError as ex:
                    if ex.errno != errno.EPERM:
                        self.fail(
                            "Expected GlusterFileSystemOSError(errno=EPERM)")
                else:
                    self.fail("Expected GlusterFileSystemOSError")
        finally:
            os.close(fd)
            shutil.rmtree(tmpdir)

    def test_fchown_err(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            fd_rd = os.open(tmpfile, os.O_RDONLY)
            buf = os.stat(tmpfile)
            if buf.st_uid == 0:
                raise SkipTest
            else:
                try:
                    fs.do_fchown(fd_rd, 20000, 20000)
                except GlusterFileSystemOSError as ex:
                    if ex.errno != errno.EPERM:
                        self.fail(
                            "Expected GlusterFileSystemOSError(errno=EPERM)")
                else:
                    self.fail("Expected GlusterFileSystemOSError")
        finally:
            os.close(fd_rd)
            os.close(fd)
            shutil.rmtree(tmpdir)

    def test_do_fsync(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            try:
                os.write(fd, 'test')
                with patch('os.fsync', mock_os_fsync):
                    assert fs.do_fsync(fd) is None
            except GlusterFileSystemOSError as ose:
                self.fail('Opening a temporary file failed with %s' %ose.strerror)
            else:
                os.close(fd)
        finally:
            shutil.rmtree(tmpdir)


    def test_do_fsync_err(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            os.write(fd, 'test')
            with patch('os.fsync', mock_os_fsync):
                assert fs.do_fsync(fd) is None
            os.close(fd)
            try:
                fs.do_fsync(fd)
            except GlusterFileSystemOSError:
                pass
            else:
                self.fail("Expected GlusterFileSystemOSError")
        finally:
            shutil.rmtree(tmpdir)

    def test_do_fdatasync(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            try:
                os.write(fd, 'test')
                with patch('os.fdatasync', mock_os_fdatasync):
                    assert fs.do_fdatasync(fd) is None
            except GlusterFileSystemOSError as ose:
                self.fail('Opening a temporary file failed with %s' %ose.strerror)
            else:
                os.close(fd)
        finally:
            shutil.rmtree(tmpdir)


    def test_do_fdatasync_err(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            os.write(fd, 'test')
            with patch('os.fdatasync', mock_os_fdatasync):
                assert fs.do_fdatasync(fd) is None
            os.close(fd)
            try:
                fs.do_fdatasync(fd)
            except GlusterFileSystemOSError:
                pass
            else:
                self.fail("Expected GlusterFileSystemOSError")
        finally:
            shutil.rmtree(tmpdir)
