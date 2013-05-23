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

""" Tests for gluster.swift.common.DiskDir """

import os
import errno
import tempfile
import cPickle as pickle
import unittest
import shutil
import tarfile
from nose import SkipTest
from swift.common.utils import normalize_timestamp
from gluster.swift.common import utils
import gluster.swift.common.Glusterfs
from test_utils import _initxattr, _destroyxattr, _setxattr, _getxattr
from test.unit import FakeLogger

gluster.swift.common.Glusterfs.RUN_DIR = '/tmp/gluster_unit_tests/run'
try:
    os.makedirs(gluster.swift.common.Glusterfs.RUN_DIR)
except OSError as e:
    if e.errno != errno.EEXIST:
        raise

import gluster.swift.common.DiskDir as dd


def timestamp_in_range(ts, base):
    low = normalize_timestamp(base - 5)
    high = normalize_timestamp(base + 5)
    assert low <= ts, "timestamp %s is less than %s" % (ts, low)
    assert high >= ts, "timestamp %s is greater than %s" % (ts, high)


class TestDiskDirModuleFunctions(unittest.TestCase):
    """ Tests for gluster.swift.common.DiskDir module functions """

    def setUp(self):
        raise SkipTest

    def test__read_metadata(self):
        def fake_read_metadata(p):
            return { 'a': 1, 'b': ('c', 5) }
        orig_rm = dd.read_metadata
        dd.read_metadata = fake_read_metadata
        try:
            md = dd._read_metadata("/tmp/foo")
        finally:
            dd.read_metadata = orig_rm
        assert md['a'] == (1, 0)
        assert md['b'] == ('c', 5)

    def test_filter_end_marker(self):
        in_objs, end_marker = [], ''
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == []

        in_objs, end_marker = [], 'abc'
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == []

        in_objs, end_marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], ''
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == []

        in_objs, end_marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'ABC'
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == []

        in_objs, end_marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'efg'
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == ['abc_123', 'abc_456', 'abc_789', 'def_101']

        # Input not sorted, so we should only expect one name
        in_objs, end_marker = ['abc_123', 'def_101', 'abc_456', 'abc_789'], 'abc_789'
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == ['abc_123',]

        in_objs, end_marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'abc_789'
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == ['abc_123', 'abc_456']

        in_objs, end_marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'abc_5'
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == ['abc_123', 'abc_456']

        in_objs, end_marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'abc_123'
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == []

        in_objs, end_marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'def_101'
        out_objs = dd.filter_end_marker(in_objs, end_marker)
        assert list(out_objs) == ['abc_123', 'abc_456', 'abc_789']

    def test_filter_marker(self):
        in_objs, marker = [], ''
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == []

        in_objs, marker = [], 'abc'
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == []

        in_objs, marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], ''
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == in_objs

        in_objs, marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'ABC'
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == in_objs

        in_objs, marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'efg'
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == []

        # Input not sorted, so we should expect the names as listed
        in_objs, marker = ['abc_123', 'def_101', 'abc_456', 'abc_789'], 'abc_456'
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == ['def_101', 'abc_789']

        in_objs, marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'abc_456'
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == ['abc_789', 'def_101']

        in_objs, marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'abc_5'
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == ['abc_789', 'def_101']

        in_objs, marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'abc_123'
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == ['abc_456', 'abc_789', 'def_101']

        in_objs, marker = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'def_101'
        out_objs = dd.filter_marker(in_objs, marker)
        assert list(out_objs) == []

    def test_filter_prefix(self):
        in_objs, prefix = [], ''
        out_objs = dd.filter_prefix(in_objs, prefix)
        assert list(out_objs) == []

        in_objs, prefix = [], 'abc'
        out_objs = dd.filter_prefix(in_objs, prefix)
        assert list(out_objs) == []

        in_objs, prefix = ['abc_123', 'abc_456', 'abc_789', 'def_101'], ''
        out_objs = dd.filter_prefix(in_objs, prefix)
        assert list(out_objs) == in_objs

        in_objs, prefix = ['abc_123', 'abc_456', 'abc_789', 'def_101'], 'abc'
        out_objs = dd.filter_prefix(in_objs, prefix)
        assert list(out_objs) == ['abc_123', 'abc_456', 'abc_789']

        in_objs, prefix = ['abc_123', 'def_101', 'abc_456', 'abc_789'], 'abc'
        out_objs = dd.filter_prefix(in_objs, prefix)
        assert list(out_objs) == ['abc_123',]

    def test_filter_delimiter(self):
        in_objs, delimiter, prefix = [], None, ''
        try:
            out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        except AssertionError:
            pass
        except Exception:
            raise SkipTest
            self.fail("Failed to raise assertion")

        in_objs, delimiter, prefix = [], '', ''
        try:
            out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        except AssertionError:
            pass
        except Exception:
            self.fail("Failed to raise assertion")

        in_objs, delimiter, prefix = [], str(255), ''
        try:
            out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        except AssertionError:
            pass
        except Exception:
            self.fail("Failed to raise assertion")

        in_objs, delimiter, prefix = [], '_', ''
        out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        assert list(out_objs) == []

        in_objs, delimiter, prefix = ['abc_'], '_', ''
        out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        assert list(out_objs) == in_objs

        in_objs, delimiter, prefix = ['abc_123', 'abc_456'], '_', ''
        out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        assert list(out_objs) == ['abc_']

        in_objs, delimiter, prefix = ['abc_123', 'abc_456', 'def_123', 'def_456'], '_', ''
        out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        assert list(out_objs) == ['abc_', 'def_']

        in_objs, delimiter, prefix = ['abc_123', 'abc_456', 'abc_789', 'def_101'], '_', 'abc_'
        out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        l = list(out_objs)
        assert l == ['abc_123', 'abc_456', 'abc_789'], repr(l)

        in_objs, delimiter, prefix = ['abc_123_a', 'abc_456', 'abc_789_', 'def_101'], '_', 'abc_'
        out_objs = dd.filter_delimiter(in_objs, delimiter, prefix)
        assert list(out_objs) == ['abc_123_a', 'abc_789_']

    def test_filter_limit(self):
        try:
            l = list(dd.filter_limit([], 0))
        except AssertionError:
            pass
        else:
            self.fail("Accepted a zero limit")

        l = list(dd.filter_limit([], 1))
        assert l == []
        l = list(dd.filter_limit([1,], 1))
        assert l == [1,]
        l = list(dd.filter_limit([1,], 10))
        assert l == [1,]
        l = list(dd.filter_limit([1,2,3], 1))
        assert l == [1,]
        l = list(dd.filter_limit([1,2,3], 2))
        assert l == [1,2]
        l = list(dd.filter_limit([1,2,3], 3))
        assert l == [1,2,3]
        l = list(dd.filter_limit([1,2,3], 4))
        assert l == [1,2,3]

class TestDiskCommon(unittest.TestCase):
    """ Tests for gluster.swift.common.DiskDir.DiskCommon """

    def setUp(self):
        raise SkipTest
        _initxattr()
        self.fake_logger = FakeLogger()
        self.td = tempfile.mkdtemp()
        self.fake_drives = []
        self.fake_accounts = []
        for i in range(0,3):
            self.fake_drives.append("drv%d" % i)
            os.makedirs(os.path.join(self.td, self.fake_drives[i]))
            self.fake_accounts.append(self.fake_drives[i])

    def tearDown(self):
        _destroyxattr()
        shutil.rmtree(self.td)

    def test_constructor(self):
        dc = dd.DiskCommon(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        assert dc.metadata == {}
        assert dc.db_file == dd._db_file
        assert dc.pending_timeout == 0
        assert dc.stale_reads_ok == False
        assert dc.root == self.td
        assert dc.logger == self.fake_logger
        assert dc.account == self.fake_accounts[0]
        assert dc.datadir == os.path.join(self.td, self.fake_drives[0])
        assert dc._dir_exists is None

    def test__dir_exists_read_metadata_exists(self):
        datadir = os.path.join(self.td, self.fake_drives[0])
        fake_md = { "fake": (True,0) }
        fake_md_p = pickle.dumps(fake_md, utils.PICKLE_PROTOCOL)
        _setxattr(datadir, utils.METADATA_KEY, fake_md_p)
        dc = dd.DiskCommon(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        dc._dir_exists_read_metadata()
        assert dc.metadata == fake_md, repr(dc.metadata)
        assert dc.db_file == dd._db_file
        assert dc.pending_timeout == 0
        assert dc.stale_reads_ok == False
        assert dc.root == self.td
        assert dc.logger == self.fake_logger
        assert dc.account == self.fake_accounts[0]
        assert dc.datadir == datadir
        assert dc._dir_exists is True

    def test__dir_exists_read_metadata_does_not_exist(self):
        dc = dd.DiskCommon(self.td, "dne0", "dne0", self.fake_logger)
        dc._dir_exists_read_metadata()
        assert dc.metadata == {}
        assert dc.db_file == dd._db_file
        assert dc.pending_timeout == 0
        assert dc.stale_reads_ok == False
        assert dc.root == self.td
        assert dc.logger == self.fake_logger
        assert dc.account == "dne0"
        assert dc.datadir == os.path.join(self.td, "dne0")
        assert dc._dir_exists is False

    def test_initialize(self):
        dc = dd.DiskCommon(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        dc.initialize('12345')
        assert dc.metadata == {}
        assert dc.db_file == dd._db_file
        assert dc.pending_timeout == 0
        assert dc.stale_reads_ok == False
        assert dc.root == self.td
        assert dc.logger == self.fake_logger
        assert dc.account == self.fake_accounts[0]
        assert dc.datadir == os.path.join(self.td, self.fake_drives[0])
        assert dc._dir_exists is None

    def test_is_deleted(self):
        dc = dd.DiskCommon(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        assert dc.is_deleted() == False

    def test_update_metadata(self):
        dc = dd.DiskCommon(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        utils.create_container_metadata(dc.datadir)
        dc.metadata = dd._read_metadata(dc.datadir)
        md_copy = dc.metadata.copy()

        def _mock_write_metadata(path, md):
            self.fail("write_metadata should not have been called")

        orig_wm = dd.write_metadata
        dd.write_metadata = _mock_write_metadata
        try:
            dc.update_metadata({})
            assert dc.metadata == md_copy
            dc.update_metadata(md_copy)
            assert dc.metadata == md_copy
        finally:
            dd.write_metadata = orig_wm

        dc.update_metadata({'X-Container-Meta-foo': '42'})
        assert 'X-Container-Meta-foo' in dc.metadata
        assert dc.metadata['X-Container-Meta-foo'] == '42'
        md = pickle.loads(_getxattr(dc.datadir, utils.METADATA_KEY))
        assert dc.metadata == md, "%r != %r" % (dc.metadata, md)
        del dc.metadata['X-Container-Meta-foo']
        assert dc.metadata == md_copy


class TestDiskDir(unittest.TestCase):
    """ Tests for gluster.swift.common.DiskDir.DiskDir """

    def setUp(self):
        _initxattr()
        self.fake_logger = FakeLogger()
        self.td = tempfile.mkdtemp()
        self.fake_drives = []
        self.fake_accounts = []
        for i in range(0,3):
            self.fake_drives.append("drv%d" % i)
            os.makedirs(os.path.join(self.td, self.fake_drives[i]))
            self.fake_accounts.append(self.fake_drives[i])

    def tearDown(self):
        _destroyxattr()
        shutil.rmtree(self.td)

    def test_constructor(self):
        raise SkipTest
        self.fail("Implement me")

    def test_empty(self):
        raise SkipTest
        self.fail("Implement me")

    def test_list_objects_iter(self):
        raise SkipTest
        self.fail("Implement me")

    def test_get_info(self):
        raise SkipTest
        self.fail("Implement me")

    def test_delete_db(self):
        raise SkipTest
        self.fail("Implement me")


class TestDiskAccount(unittest.TestCase):
    """ Tests for gluster.swift.common.DiskDir.DiskAccount """

    def setUp(self):
        _initxattr()
        self.fake_logger = FakeLogger()
        self.td = tempfile.mkdtemp()
        self.fake_drives = []
        self.fake_accounts = []
        self.fake_md = []
        for i in range(0,3):
            self.fake_drives.append("drv%d" % i)
            os.makedirs(os.path.join(self.td, self.fake_drives[i]))
            self.fake_accounts.append(self.fake_drives[i])
            if i == 0:
                # First drive does not have any initial account metadata
                continue
            if i == 1:
                # Second drive has account metadata but it is not valid
                datadir = os.path.join(self.td, self.fake_drives[i])
                fake_md = { "fake-drv-%d" % i: (True,0) }
                self.fake_md.append(fake_md)
                fake_md_p = pickle.dumps(fake_md, utils.PICKLE_PROTOCOL)
                _setxattr(datadir, utils.METADATA_KEY, fake_md_p)
            if i == 2:
                # Third drive has valid account metadata
                utils.create_account_metadata(datadir)

    def tearDown(self):
        _destroyxattr()
        shutil.rmtree(self.td)

    def test_constructor_no_metadata(self):
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        raise SkipTest
        assert da._container_info is None
        assert da._dir_exists is True
        ctime = os.path.getctime(da.datadir)
        mtime = os.path.getmtime(da.datadir)
        exp_md = {
            'X-Bytes-Used': (0, 0),
            'X-Timestamp': (normalize_timestamp(ctime), 0),
            'X-Object-Count': (0, 0),
            'X-Type': ('Account', 0),
            'X-PUT-Timestamp': (normalize_timestamp(mtime), 0),
            'X-Container-Count': (0, 0)}
        assert da.metadata == exp_md, repr(da.metadata)

    def test_constructor_metadata_not_valid(self):
        da = dd.DiskAccount(self.td, self.fake_drives[1],
                            self.fake_accounts[1], self.fake_logger)
        raise SkipTest
        assert da._container_info is None
        assert da._dir_exists is True
        ctime = os.path.getctime(da.datadir)
        mtime = os.path.getmtime(da.datadir)
        exp_md = {
            'X-Bytes-Used': (0, 0),
            'X-Timestamp': (normalize_timestamp(ctime), 0),
            'X-Object-Count': (0, 0),
            'X-Type': ('Account', 0),
            'X-PUT-Timestamp': (normalize_timestamp(mtime), 0),
            'X-Container-Count': (0, 0),
            'fake-drv-1': (True, 0)}
        assert da.metadata == exp_md, repr(da.metadata)

    def test_constructor_metadata_valid(self):
        da = dd.DiskAccount(self.td, self.fake_drives[2],
                            self.fake_accounts[2], self.fake_logger)
        raise SkipTest
        assert da._container_info is None
        assert da._dir_exists is True
        ctime = os.path.getctime(da.datadir)
        mtime = os.path.getmtime(da.datadir)
        exp_md = {
            'X-Bytes-Used': (0, 0),
            'X-Timestamp': (normalize_timestamp(ctime), 0),
            'X-Object-Count': (0, 0),
            'X-Type': ('Account', 0),
            'X-PUT-Timestamp': (normalize_timestamp(mtime), 0),
            'X-Container-Count': (0, 0)}
        assert da.metadata == exp_md, repr(da.metadata)

    def test_list_containers_iter(self):
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        raise SkipTest
        self.fail("Implement me")

    get_info_keys = set(['account', 'created_at', 'put_timestamp',
                        'delete_timestamp', 'container_count',
                        'object_count', 'bytes_used', 'hash', 'id'])

    def test_get_info_empty(self):
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        data = da.get_info()
        assert set(data.keys()) == self.get_info_keys
        assert data['account'] == self.fake_accounts[0]
        assert data['created_at'] == '1'
        assert data['put_timestamp'] == '1'
        assert data['delete_timestamp'] == '1'
        assert data['container_count'] == 0
        assert data['object_count'] == 0
        assert data['bytes_used'] == 0
        assert data['hash'] == ''
        assert data['id'] == ''

    def test_get_info(self):
        tf = tarfile.open("common/data/account_tree.tar.bz2", "r:bz2")
        orig_cwd = os.getcwd()
        os.chdir(os.path.join(self.td, self.fake_drives[0]))
        try:
            tf.extractall()
        finally:
            os.chdir(orig_cwd)
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        data = da.get_info()
        assert set(data.keys()) == self.get_info_keys
        assert data['account'] == self.fake_accounts[0]
        assert data['created_at'] == '1'
        assert data['put_timestamp'] == '1'
        assert data['delete_timestamp'] == '1'
        assert data['container_count'] == 3
        assert data['object_count'] == 0
        assert data['bytes_used'] == 0
        assert data['hash'] == ''
        assert data['id'] == ''

    def test_get_container_timestamp(self):
        tf = tarfile.open("common/data/account_tree.tar.bz2", "r:bz2")
        orig_cwd = os.getcwd()
        datadir = os.path.join(self.td, self.fake_drives[0])
        os.chdir(datadir)
        try:
            tf.extractall()
        finally:
            os.chdir(orig_cwd)
        md = dd.create_container_metadata(os.path.join(datadir, 'c2'))
        assert 'X-PUT-Timestamp' in md, repr(md)
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        raise SkipTest
        cts = da.get_container_timestamp('c2')
        assert md['X-PUT-Timestamp'][0] == cts, repr(cts)

    def test_update_put_timestamp_not_updated(self):
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        raise SkipTest
        da.update_put_timestamp('12345')
        assert da.metadata['X-PUT-Timestamp'][0] != '12345', repr(da.metadata)

    def test_update_put_timestamp_updated(self):
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        exp_pts = str(float(da.metadata['X-PUT-Timestamp'][0]) + 100)
        da.update_put_timestamp(exp_pts)
        raise SkipTest
        assert da.metadata['X-PUT-Timestamp'][0] == exp_pts, repr(da.metadata)

    def test_delete_db(self):
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        raise SkipTest
        assert da._dir_exists == True
        da.delete_db('12345')
        assert da._dir_exists == True

    def test_put_container(self):
        raise SkipTest
        self.fail("Implement me")

    def test_is_status_deleted(self):
        da = dd.DiskAccount(self.td, self.fake_drives[0],
                            self.fake_accounts[0], self.fake_logger)
        raise SkipTest
        assert da.is_status_deleted() == False
