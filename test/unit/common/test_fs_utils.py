# Copyright (c) 2012 Red Hat, Inc.
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
    FileOrDirNotFoundError

def mock_os_fsync(fd):
    return True

def mock_tpool_execute(func, *args, **kwargs):
    func(*args, **kwargs)

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


    def test_do_open(self):
        fd, tmpfile = mkstemp()
        try:
            f = fs.do_open(tmpfile, 'r')
            try:
                f.write('test')
            except IOError as err:
                pass
            else:
                self.fail("IOError expected")
            finally:
                f.close()
        finally:
            os.close(fd)
            os.remove(tmpfile)


    def test_do_open_err(self):
        try:
            fs.do_open(os.path.join('/tmp', str(random.random())), 'r')
        except IOError:
            pass
        else:
            self.fail("IOError expected")

    def test_do_open_err_int_mode(self):
        try:
            fs.do_open(os.path.join('/tmp', str(random.random())),
                       os.O_RDONLY)
        except OSError:
            pass
        else:
            self.fail("IOError expected")

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
            except OSError:
                pass
            else:
                self.fail("OSError expected")
        except OSError as ose:
            self.fail("Open failed with %s" %ose.strerror)
        else:
            os.close(fd1)
        finally:
            os.close(fd)
            os.remove(tmpfile)

    def test_do_mkdir(self):
        try:
            path = os.path.join('/tmp', str(random.random()))
            fs.do_mkdir(path)
            assert os.path.exists(path)
            assert fs.do_mkdir(path)
        finally:
            os.rmdir(path)

    def test_do_mkdir_err(self):
        try:
            path = os.path.join('/tmp', str(random.random()), str(random.random()))
            fs.do_mkdir(path)
        except OSError:
            pass
        else:
            self.fail("OSError expected")


    def test_do_makedirs(self):
        try:
            subdir = os.path.join('/tmp', str(random.random()))
            path = os.path.join(subdir, str(random.random()))
            fs.do_makedirs(path)
            assert os.path.exists(path)
            assert fs.do_makedirs(path)
        finally:
            shutil.rmtree(subdir)

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
        except OSError:
            pass
        else:
            self.fail("OSError expected")

    def test_do_stat(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            buf1 = os.stat(tmpfile)
            buf2 = fs.do_stat(fd)
            buf3 = fs.do_stat(tmpfile)

            assert buf1 == buf2
            assert buf1 == buf3
        finally:
            os.close(fd)
            os.remove(tmpfile)
            os.rmdir(tmpdir)

    def test_do_stat_err(self):
        try:
            fs.do_stat(os.path.join('/tmp', str(random.random())))
        except OSError:
            pass
        else:
            self.fail("OSError expected")

    def test_do_close(self):
        fd, tmpfile = mkstemp()
        try:
            fs.do_close(fd);
            try:
                os.write(fd, "test")
            except OSError:
                pass
            else:
                self.fail("OSError expected")
            fp = open(tmpfile)
            fs.do_close(fp)
        finally:
            os.remove(tmpfile)

    def test_do_close_err(self):
        fd, tmpfile = mkstemp()
        try:
            fs.do_close(fd);

            try:
                fs.do_close(fd);
            except OSError:
                pass
            else:
                self.fail("OSError expected")
        finally:
            os.remove(tmpfile)

    def test_do_unlink(self):
        fd, tmpfile = mkstemp()
        try:
            fs.do_unlink(tmpfile)
            assert not os.path.exists(tmpfile)
            assert fs.do_unlink(os.path.join('/tmp', str(random.random())))
        finally:
            os.close(fd)

    def test_do_unlink_err(self):
        tmpdir = mkdtemp()
        try:
            fs.do_unlink(tmpdir)
        except OSError:
            pass
        else:
            self.fail('OSError expected')
        finally:
            os.rmdir(tmpdir)

    def test_do_rmdir(self):
        tmpdir = mkdtemp()
        fs.do_rmdir(tmpdir)
        assert not os.path.exists(tmpdir)
        assert not fs.do_rmdir(os.path.join('/tmp', str(random.random())))

    def test_do_rmdir_err(self):
        fd, tmpfile = mkstemp()
        try:
            fs.do_rmdir(tmpfile)
        except OSError:
            pass
        else:
            self.fail('OSError expected')
        finally:
            os.close(fd)
            os.remove(tmpfile)

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
        except OSError:
            pass
        else:
            self.fail("OSError expected")

    def test_dir_empty(self):
        tmpdir = mkdtemp()
        try:
            subdir = mkdtemp(dir=tmpdir)
            assert not fs.dir_empty(tmpdir)
            assert fs.dir_empty(subdir)
        finally:
            shutil.rmtree(tmpdir)

    def test_dir_empty_err(self):
        try:
            try:
                assert fs.dir_empty(os.path.join('/tmp', str(random.random())))
            except FileOrDirNotFoundError:
                pass
            else:
                self.fail("FileOrDirNotFoundError exception expected")

            fd, tmpfile = mkstemp()
            try:
                fs.dir_empty(tmpfile)
            except NotDirectoryError:
                pass
            else:
                self.fail("NotDirectoryError exception expected")
        finally:
            os.close(fd)
            os.unlink(tmpfile)

    def test_rmdirs(self):
        tmpdir = mkdtemp()
        try:
            subdir = mkdtemp(dir=tmpdir)
            fd, tmpfile = mkstemp(dir=tmpdir)
            assert not fs.rmdirs(tmpfile)
            assert not fs.rmdirs(tmpdir)
            assert fs.rmdirs(subdir)
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
                except OSError as ex:
                    if ex.errno != errno.EPERM:
                        self.fail("Expected OSError")
                else:
                        self.fail("Expected OSError")
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
                except OSError as ex:
                    if ex.errno != errno.EPERM:
                        self.fail("Expected OSError")
                else:
                        self.fail("Expected OSError")
        finally:
            os.close(fd)
            shutil.rmtree(tmpdir)

    def test_chown_file_err(self):
        try:
            fs.do_chown(os.path.join('/tmp', str(random.random())),
                        20000, 20000)
        except OSError:
            pass
        else:
            self.fail("Expected OSError")


    def test_do_fsync(self):
        tmpdir = mkdtemp()
        try:
            fd, tmpfile = mkstemp(dir=tmpdir)
            try:
                os.write(fd, 'test')
                with patch('eventlet.tpool.execute', mock_tpool_execute):
                    with patch('os.fsync', mock_os_fsync):
                        assert fs.do_fsync(fd)
            except OSError as ose:
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
            with patch('eventlet.tpool.execute', mock_tpool_execute):
                with patch('os.fsync', mock_os_fsync):
                    assert fs.do_fsync(fd)
                os.close(fd)
                try:
                    fs.do_fsync(fd)
                except OSError:
                    pass
                else:
                    self.fail("Expected OSError")
        finally:
            shutil.rmtree(tmpdir)
