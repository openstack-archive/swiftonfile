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
import hashlib
from time import time
from nose import SkipTest
from swift.common.utils import normalize_timestamp
from gluster.swift.common import utils
import gluster.swift.common.Glusterfs
from test_utils import _initxattr, _destroyxattr, _setxattr, _getxattr
from test.unit import FakeLogger

def setup():
    global _saved_RUN_DIR, _saved_do_getsize
    _saved_do_getsize = gluster.swift.common.Glusterfs._do_getsize
    gluster.swift.common.Glusterfs._do_getsize = True
    _saved_RUN_DIR = gluster.swift.common.Glusterfs.RUN_DIR
    gluster.swift.common.Glusterfs.RUN_DIR = '/tmp/gluster_unit_tests/run'
    try:
        os.makedirs(gluster.swift.common.Glusterfs.RUN_DIR)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def teardown():
    shutil.rmtree(gluster.swift.common.Glusterfs.RUN_DIR)
    gluster.swift.common.Glusterfs.RUN_DIR = _saved_RUN_DIR
    gluster.swift.common.Glusterfs._do_getsize = _saved_do_getsize


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


class TestContainerBroker(unittest.TestCase):
    """
    Tests for DiskDir.DiskDir class (duck-typed
    swift.common.db.ContainerBroker).
    """

    def __init__(self, *args, **kwargs):
        super(TestContainerBroker, self).__init__(*args, **kwargs)
        self.initial_ts = normalize_timestamp('1')

    def setUp(self):
        _initxattr()
        self.path = tempfile.mkdtemp()
        self.drive = 'drv'
        self.container = None

    def tearDown(self):
        self.container = None
        _destroyxattr()
        shutil.rmtree(self.path)

    def _get_broker(self, account=None, container=None):
        assert account is not None
        assert container is not None
        self.container = os.path.join(self.path, self.drive, container)
        return dd.DiskDir(self.path, self.drive, account=account,
                          container=container, logger=FakeLogger())

    def _create_file(self, p):
        fullname = os.path.join(self.container, p)
        dirs = os.path.dirname(fullname)
        try:
            os.makedirs(dirs)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        with open(fullname, 'w') as fp:
            fp.write("file path: %s\n" % fullname)
        return fullname

    def test_creation(self):
        # Test swift.common.db.ContainerBroker.__init__
        broker = self._get_broker(account='a', container='c')
        self.assertEqual(broker.db_file, dd._db_file)
        self.assertEqual(os.path.basename(broker.db_file), 'db_file.db')
        broker.initialize(self.initial_ts)
        self.assertTrue(os.path.isdir(self.container))
        self.assertEquals(self.initial_ts, broker.metadata[utils.X_TIMESTAMP])
        self.assertFalse(broker.is_deleted())

    def test_creation_existing(self):
        # Test swift.common.db.ContainerBroker.__init__
        os.makedirs(os.path.join(self.path, self.drive, 'c'))
        broker = self._get_broker(account='a', container='c')
        self.assertEqual(broker.db_file, dd._db_file)
        self.assertEqual(os.path.basename(broker.db_file), 'db_file.db')
        broker.initialize(self.initial_ts)
        self.assertTrue(os.path.isdir(self.container))
        self.assertEquals(self.initial_ts, broker.metadata[utils.X_TIMESTAMP])
        self.assertFalse(broker.is_deleted())

    def test_creation_existing_bad_metadata(self):
        # Test swift.common.db.ContainerBroker.__init__
        container = os.path.join(self.path, self.drive, 'c')
        os.makedirs(container)
        utils.write_metadata(container, dict(a=1, b=2))
        broker = self._get_broker(account='a', container='c')
        self.assertEqual(broker.db_file, dd._db_file)
        self.assertEqual(os.path.basename(broker.db_file), 'db_file.db')
        broker.initialize(self.initial_ts)
        self.assertTrue(os.path.isdir(self.container))
        self.assertEquals(self.initial_ts, broker.metadata[utils.X_TIMESTAMP])
        self.assertFalse(broker.is_deleted())

    def test_empty(self):
        # Test swift.common.db.ContainerBroker.empty
        broker = self._get_broker(account='a', container='c')
        broker.initialize(self.initial_ts)
        self.assert_(broker.empty())
        obj = self._create_file('o.txt')
        self.assert_(not broker.empty())
        os.unlink(obj)
        self.assert_(broker.empty())

    def test_put_object(self):
        broker = self._get_broker(account='a', container='c')
        broker.initialize(self.initial_ts)
        self.assert_(broker.empty())
        broker.put_object('o', normalize_timestamp(time()), 0, 'text/plain',
                          'd41d8cd98f00b204e9800998ecf8427e')
        # put_object() should be a NOOP
        self.assert_(broker.empty())

    def test_delete_object(self):
        broker = self._get_broker(account='a', container='c')
        broker.initialize(self.initial_ts)
        self.assert_(broker.empty())
        obj = self._create_file('o.txt')
        self.assert_(not broker.empty())
        broker.delete_object('o', normalize_timestamp(time()))
        # delete_object() should be a NOOP
        self.assert_(not broker.empty())
        os.unlink(obj)
        self.assert_(broker.empty())

    def test_get_info(self):
        # Test swift.common.db.ContainerBroker.get_info
        broker = self._get_broker(account='test1',
                                 container='test2')
        broker.initialize(normalize_timestamp('1'))

        info = broker.get_info()
        self.assertEquals(info['account'], 'test1')
        self.assertEquals(info['container'], 'test2')

        info = broker.get_info()
        self.assertEquals(info['object_count'], 0)
        self.assertEquals(info['bytes_used'], 0)

        obj1 = os.path.join(self.container, 'o1')
        with open(obj1, 'w') as fp:
            fp.write("%s\n" % ('x' * 122))
        info = broker.get_info()
        self.assertEquals(info['object_count'], 1)
        self.assertEquals(info['bytes_used'], 123)

        obj2 = os.path.join(self.container, 'o2')
        with open(obj2, 'w') as fp:
            fp.write("%s\n" % ('x' * 122))
        info = broker.get_info()
        self.assertEquals(info['object_count'], 2)
        self.assertEquals(info['bytes_used'], 246)

        with open(obj2, 'w') as fp:
            fp.write("%s\n" % ('x' * 999))
        info = broker.get_info()
        self.assertEquals(info['object_count'], 2)
        self.assertEquals(info['bytes_used'], 1123)

        os.unlink(obj1)
        info = broker.get_info()
        self.assertEquals(info['object_count'], 1)
        self.assertEquals(info['bytes_used'], 1000)

        os.unlink(obj2)
        info = broker.get_info()
        self.assertEquals(info['object_count'], 0)
        self.assertEquals(info['bytes_used'], 0)

        info = broker.get_info()
        self.assertEquals(info['x_container_sync_point1'], -1)
        self.assertEquals(info['x_container_sync_point2'], -1)

    def test_set_x_syncs(self):
        broker = self._get_broker(account='test1',
                                 container='test2')
        broker.initialize(normalize_timestamp('1'))

        info = broker.get_info()
        self.assertEquals(info['x_container_sync_point1'], -1)
        self.assertEquals(info['x_container_sync_point2'], -1)

        broker.set_x_container_sync_points(1, 2)
        info = broker.get_info()
        self.assertEquals(info['x_container_sync_point1'], 1)
        self.assertEquals(info['x_container_sync_point2'], 2)

    def test_list_objects_iter(self):
        # Test swift.common.db.ContainerBroker.list_objects_iter
        broker = self._get_broker(account='a', container='c')
        broker.initialize(normalize_timestamp('1'))

        for obj1 in xrange(4):
            for obj2 in xrange(125):
                self._create_file('%d.d/%04d' % (obj1, obj2))
        for obj in xrange(125):
            self._create_file('2.d/0051.d/%04d' % obj)
        for obj in xrange(125):
            self._create_file('3.d/%04d.d/0049' % obj)

        listing = broker.list_objects_iter(100, '', None, None, '')
        self.assertEquals(len(listing), 100)
        self.assertEquals(listing[0][0], '0.d/0000')
        self.assertEquals(listing[-1][0], '0.d/0099')

        listing = broker.list_objects_iter(100, '', '0.d/0050', None, '')
        self.assertEquals(len(listing), 50)
        self.assertEquals(listing[0][0], '0.d/0000')
        self.assertEquals(listing[-1][0], '0.d/0049')

        listing = broker.list_objects_iter(100, '0.d/0099', None, None, '')
        self.assertEquals(len(listing), 100)
        self.assertEquals(listing[0][0], '0.d/0100')
        self.assertEquals(listing[-1][0], '1.d/0074')

        listing = broker.list_objects_iter(55, '1.d/0074', None, None, '')
        self.assertEquals(len(listing), 55)
        self.assertEquals(listing[0][0], '1.d/0075')
        self.assertEquals(listing[-1][0], '2.d/0004')

        listing = broker.list_objects_iter(10, '', None, '0.d/01', '')
        self.assertEquals(len(listing), 10)
        self.assertEquals(listing[0][0], '0.d/0100')
        self.assertEquals(listing[-1][0], '0.d/0109')

        listing = broker.list_objects_iter(10, '', None, '0.d/', '/')
        self.assertEquals(len(listing), 10)
        self.assertEquals(listing[0][0], '0.d/0000')
        self.assertEquals(listing[-1][0], '0.d/0009')

        listing = broker.list_objects_iter(10, '', None, None, '', '0.d')
        self.assertEquals(len(listing), 10)
        self.assertEquals(listing[0][0], '0.d/0000')
        self.assertEquals(listing[-1][0], '0.d/0009')

        listing = broker.list_objects_iter(10, '', None, '', '/')
        self.assertEquals(len(listing), 0)

        listing = broker.list_objects_iter(10, '2', None, None, '/')
        self.assertEquals(len(listing), 0)

        listing = broker.list_objects_iter(10, '2.d/', None,  None, '/')
        self.assertEquals(len(listing), 0)

        listing = broker.list_objects_iter(10, '2.d/0050', None, '2.d/', '/')
        self.assertEquals(len(listing), 9)
        self.assertEquals(listing[0][0], '2.d/0051')
        self.assertEquals(listing[1][0], '2.d/0052')
        self.assertEquals(listing[-1][0], '2.d/0059')

        listing = broker.list_objects_iter(10, '3.d/0045', None, '3.d/', '/')
        self.assertEquals(len(listing), 5)
        self.assertEquals([row[0] for row in listing],
                           ['3.d/0046', '3.d/0047',
                            '3.d/0048', '3.d/0049',
                            '3.d/0050'])

        # FIXME
        #broker.put_object('3/0049/', normalize_timestamp(time()), 0,
        #                  'text/plain', 'd41d8cd98f00b204e9800998ecf8427e')
        #listing = broker.list_objects_iter(10, '3/0048', None, None, None)
        #self.assertEquals(len(listing), 10)
        #self.assertEquals([row[0] for row in listing],
        #    ['3.d/0048.d/0049', '3.d/0049', '3.d/0049.d/',
        #    '3.d/0049.d/0049', '3.d/0050', '3.d/0050.d/0049', '3.d/0051', '3.d/0051.d/0049',
        #    '3.d/0052', '3.d/0052.d/0049'])

        listing = broker.list_objects_iter(10, '3.d/0048', None, '3.d/', '/')
        self.assertEquals(len(listing), 5)
        self.assertEquals([row[0] for row in listing],
            ['3.d/0049', '3.d/0050',
             '3.d/0051', '3.d/0052', '3.d/0053'])

        listing = broker.list_objects_iter(10, None, None, '3.d/0049.d/', '/')
        self.assertEquals(len(listing), 1)
        self.assertEquals([row[0] for row in listing],
            ['3.d/0049.d/0049'])

        # FIXME
        #listing = broker.list_objects_iter(10, None, None, None, None,
        #                                   '3.d/0049')
        #self.assertEquals(len(listing), 1)
        #self.assertEquals([row[0] for row in listing], ['3.d/0049.d/0049'])

        listing = broker.list_objects_iter(2, None, None, '3.d/', '/')
        self.assertEquals(len(listing), 1)
        self.assertEquals([row[0] for row in listing], ['3.d/0000'])

        # FIXME
        #listing = broker.list_objects_iter(2, None, None, None, None, '3')
        #self.assertEquals(len(listing), 2)
        #self.assertEquals([row[0] for row in listing], ['3.d/0000', '3.d/0001'])

    def test_list_objects_iter_prefix_delim(self):
        # Test swift.common.db.ContainerBroker.list_objects_iter
        broker = self._get_broker(account='a', container='c')
        broker.initialize(normalize_timestamp('1'))

        os.mkdir(os.path.join(self.container, 'pets'))
        os.mkdir(os.path.join(self.container, 'pets', 'dogs'))
        obj1 = os.path.join(self.container, 'pets', 'dogs', '1')
        with open(obj1, 'w') as fp:
            fp.write("one\n")
        obj2 = os.path.join(self.container, 'pets', 'dogs', '2')
        with open(obj2, 'w') as fp:
            fp.write("two\n")
        os.mkdir(os.path.join(self.container, 'pets', 'fish'))
        obja = os.path.join(self.container, 'pets', 'fish', 'a')
        with open(obja, 'w') as fp:
            fp.write("A\n")
        objb = os.path.join(self.container, 'pets', 'fish', 'b')
        with open(objb, 'w') as fp:
            fp.write("B\n")
        objf = os.path.join(self.container, 'pets', 'fish_info.txt')
        with open(objf, 'w') as fp:
            fp.write("one fish\n")
        objs = os.path.join(self.container, 'snakes')
        with open(objs, 'w') as fp:
            fp.write("slither\n")

        listing = broker.list_objects_iter(100, None, None, 'pets/f', '/')
        self.assertEquals([row[0] for row in listing],
                          ['pets/fish_info.txt'])
        listing = broker.list_objects_iter(100, None, None, 'pets/fish', '/')
        self.assertEquals([row[0] for row in listing],
                          ['pets/fish_info.txt'])
        listing = broker.list_objects_iter(100, None, None, 'pets/fish/', '/')
        self.assertEquals([row[0] for row in listing],
                          ['pets/fish/a', 'pets/fish/b'])

    def test_double_check_trailing_delimiter(self):
        # Test swift.common.db.ContainerBroker.list_objects_iter for a
        # container that has an odd file with a trailing delimiter
        broker = self._get_broker(account='a', container='c')
        broker.initialize(normalize_timestamp('1'))

        self._create_file('a')
        self._create_file('a.d/a')
        self._create_file('a.d/a.d/a')
        self._create_file('a.d/a.d/b')
        self._create_file('a.d/b')
        self._create_file('b')
        self._create_file('b.d/a')
        self._create_file('b.d/b')
        self._create_file('c')
        self._create_file('a.d/0')
        self._create_file('0')
        self._create_file('00')
        self._create_file('0.d/0')
        self._create_file('0.d/00')
        self._create_file('0.d/1')
        self._create_file('0.d/1.d/0')
        self._create_file('1')
        self._create_file('1.d/0')

        listing = broker.list_objects_iter(25, None, None, None, None)
        self.assertEquals(len(listing), 18)
        self.assertEquals([row[0] for row in listing],
                          ['0', '0.d/0', '0.d/00', '0.d/1', '0.d/1.d/0', '00',
                           '1', '1.d/0', 'a', 'a.d/0', 'a.d/a', 'a.d/a.d/a',
                           'a.d/a.d/b', 'a.d/b', 'b', 'b.d/a', 'b.d/b', 'c'])
        listing = broker.list_objects_iter(25, None, None, '', '/')
        self.assertEquals(len(listing), 6)
        self.assertEquals([row[0] for row in listing],
                          ['0', '00', '1', 'a', 'b', 'c'])
        listing = broker.list_objects_iter(25, None, None, 'a.d/', '/')
        self.assertEquals(len(listing), 3)
        self.assertEquals([row[0] for row in listing],
                          ['a.d/0', 'a.d/a', 'a.d/b'])
        listing = broker.list_objects_iter(25, None, None, '0.d/', '/')
        self.assertEquals(len(listing), 3)
        self.assertEquals([row[0] for row in listing],
                          ['0.d/0', '0.d/00', '0.d/1'])
        listing = broker.list_objects_iter(25, None, None, '0.d/1.d/', '/')
        self.assertEquals(len(listing), 1)
        self.assertEquals([row[0] for row in listing], ['0.d/1.d/0'])
        listing = broker.list_objects_iter(25, None, None, 'b.d/', '/')
        self.assertEquals(len(listing), 2)
        self.assertEquals([row[0] for row in listing], ['b.d/a', 'b.d/b'])

    def test_metadata(self):
        # Initializes a good broker for us
        broker = self._get_broker(account='a', container='c')
        broker.initialize(normalize_timestamp('1'))

        # Add our first item
        first_timestamp = normalize_timestamp(1)
        first_value = '1'
        broker.update_metadata({'First': [first_value, first_timestamp]})
        self.assert_('First' in broker.metadata)
        self.assertEquals(broker.metadata['First'],
                          [first_value, first_timestamp])
        # Add our second item
        second_timestamp = normalize_timestamp(2)
        second_value = '2'
        broker.update_metadata({'Second': [second_value, second_timestamp]})
        self.assert_('First' in broker.metadata)
        self.assertEquals(broker.metadata['First'],
                          [first_value, first_timestamp])
        self.assert_('Second' in broker.metadata)
        self.assertEquals(broker.metadata['Second'],
                          [second_value, second_timestamp])
        # Update our first item
        first_timestamp = normalize_timestamp(3)
        first_value = '1b'
        broker.update_metadata({'First': [first_value, first_timestamp]})
        self.assert_('First' in broker.metadata)
        self.assertEquals(broker.metadata['First'],
                          [first_value, first_timestamp])
        self.assert_('Second' in broker.metadata)
        self.assertEquals(broker.metadata['Second'],
                          [second_value, second_timestamp])
        # Delete our second item (by setting to empty string)
        second_timestamp = normalize_timestamp(4)
        second_value = ''
        broker.update_metadata({'Second': [second_value, second_timestamp]})
        self.assert_('First' in broker.metadata)
        self.assertEquals(broker.metadata['First'],
                          [first_value, first_timestamp])
        self.assert_('Second' in broker.metadata)
        self.assertEquals(broker.metadata['Second'],
                          [second_value, second_timestamp])

    def test_delete_db(self):
        broker = self._get_broker(account='a', container='c')
        self.assertEqual(broker.db_file, dd._db_file)
        self.assertEqual(os.path.basename(broker.db_file), 'db_file.db')
        broker.initialize(self.initial_ts)
        self.assertTrue(os.path.isdir(self.container))
        self.assertEquals(self.initial_ts, broker.metadata[utils.X_TIMESTAMP])
        self.assertFalse(broker.is_deleted())
        broker.delete_db(normalize_timestamp(time()))
        self.assertTrue(broker.is_deleted())


class TestAccountBroker(unittest.TestCase):
    """
    Tests for DiskDir.DiskAccount class (duck-typed
    swift.common.db.AccountBroker).
    """

    def __init__(self, *args, **kwargs):
        super(TestAccountBroker, self).__init__(*args, **kwargs)
        self.initial_ts = normalize_timestamp('1')

    def setUp(self):
        _initxattr()
        self.path = tempfile.mkdtemp()
        self.drive = 'drv'
        self.drive_fullpath = os.path.join(self.path, self.drive)
        os.mkdir(self.drive_fullpath)
        self.account = None

    def tearDown(self):
        self.account = None
        _destroyxattr()
        shutil.rmtree(self.path)

    def _get_broker(self, account=None):
        assert account is not None
        self.account = account
        return dd.DiskAccount(self.path, self.drive, account=account,
                              logger=FakeLogger())

    def _create_container(self, name):
        cont = os.path.join(self.drive_fullpath, name)
        try:
            os.mkdir(cont)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
        return cont

    def test_creation(self):
        # Test swift.common.db.AccountBroker.__init__
        broker = self._get_broker(account='a')
        self.assertEqual(broker.db_file, dd._db_file)
        self.assertEqual(os.path.basename(broker.db_file), 'db_file.db')
        broker.initialize(self.initial_ts)
        self.assertTrue(os.path.isdir(self.drive_fullpath))
        self.assertEquals(self.initial_ts, broker.metadata[utils.X_TIMESTAMP])
        self.assertFalse(broker.is_deleted())

    def test_creation_bad_metadata(self):
        # Test swift.common.db.AccountBroker.__init__
        utils.write_metadata(self.drive_fullpath, dict(a=1, b=2))
        broker = self._get_broker(account='a')
        self.assertEqual(broker.db_file, dd._db_file)
        self.assertEqual(os.path.basename(broker.db_file), 'db_file.db')
        broker.initialize(self.initial_ts)
        self.assertTrue(os.path.isdir(self.drive_fullpath))
        self.assertEquals(self.initial_ts, broker.metadata[utils.X_TIMESTAMP])
        self.assertFalse(broker.is_deleted())

    def test_empty(self):
        # Test swift.common.db.AccountBroker.empty
        broker = self._get_broker(account='a')
        broker.initialize(self.initial_ts)
        self.assert_(broker.empty())
        c1 = self._create_container('c1')
        self.assert_(not broker.empty())
        os.rmdir(c1)
        self.assert_(broker.empty())

    def test_put_container(self):
        broker = self._get_broker(account='a')
        broker.initialize(self.initial_ts)
        self.assert_(broker.empty())
        broker.put_container('c1', normalize_timestamp(time()), 0, 0, 0)
        # put_container() should be a NOOP
        self.assert_(broker.empty())

    def test_put_container_for_deletes(self):
        broker = self._get_broker(account='a')
        broker.initialize(self.initial_ts)
        self.assert_(broker.empty())
        c1 = self._create_container('c1')
        self.assert_(not broker.empty())
        broker.put_container('c1', 0, normalize_timestamp(time()), 0, 0)
        # put_container() should be a NOOP
        self.assert_(not broker.empty())
        os.rmdir(c1)
        self.assert_(broker.empty())

    def test_get_info(self):
        # Test swift.common.db.AccountBroker.get_info
        broker = self._get_broker(account='test1')
        broker.initialize(normalize_timestamp('1'))

        info = broker.get_info()
        self.assertEquals(info['account'], 'test1')

        info = broker.get_info()
        self.assertEquals(info['container_count'], 0)

        c1 = self._create_container('c1')
        info = broker.get_info()
        self.assertEquals(info['container_count'], 1)

        c2 = self._create_container('c2')
        info = broker.get_info()
        self.assertEquals(info['container_count'], 2)

        c2 = self._create_container('c2')
        info = broker.get_info()
        self.assertEquals(info['container_count'], 2)

        os.rmdir(c1)
        info = broker.get_info()
        self.assertEquals(info['container_count'], 1)

        os.rmdir(c2)
        info = broker.get_info()
        self.assertEquals(info['container_count'], 0)

    def test_list_containers_iter(self):
        # Test swift.common.db.AccountBroker.list_containers_iter
        broker = self._get_broker(account='a')
        broker.initialize(normalize_timestamp('1'))
        for cont1 in xrange(4):
            for cont2 in xrange(125):
                self._create_container('%d-%04d' % (cont1, cont2))
        for cont in xrange(125):
            self._create_container('2-0051-%04d' % cont)
        for cont in xrange(125):
            self._create_container('3-%04d-0049' % cont)

        listing = broker.list_containers_iter(100, '', None, None, '')
        self.assertEquals(len(listing), 100)
        self.assertEquals(listing[0][0], '0-0000')
        self.assertEquals(listing[-1][0], '0-0099')

        listing = broker.list_containers_iter(100, '', '0-0050', None, '')
        self.assertEquals(len(listing), 50)
        self.assertEquals(listing[0][0], '0-0000')
        self.assertEquals(listing[-1][0], '0-0049')

        listing = broker.list_containers_iter(100, '0-0099', None, None, '')
        self.assertEquals(len(listing), 100)
        self.assertEquals(listing[0][0], '0-0100')
        self.assertEquals(listing[-1][0], '1-0074')

        listing = broker.list_containers_iter(55, '1-0074', None, None, '')
        self.assertEquals(len(listing), 55)
        self.assertEquals(listing[0][0], '1-0075')
        self.assertEquals(listing[-1][0], '2-0004')

        listing = broker.list_containers_iter(10, '', None, '0-01', '')
        self.assertEquals(len(listing), 10)
        self.assertEquals(listing[0][0], '0-0100')
        self.assertEquals(listing[-1][0], '0-0109')

        listing = broker.list_containers_iter(10, '', None, '0-01', '-')
        self.assertEquals(len(listing), 10)
        self.assertEquals(listing[0][0], '0-0100')
        self.assertEquals(listing[-1][0], '0-0109')

        listing = broker.list_containers_iter(10, '', None, '0-', '-')
        self.assertEquals(len(listing), 10)
        self.assertEquals(listing[0][0], '0-0000')
        self.assertEquals(listing[-1][0], '0-0009')

        listing = broker.list_containers_iter(10, '', None, '', '-')
        self.assertEquals(len(listing), 4)
        self.assertEquals([row[0] for row in listing],
                          ['0', '1', '2', '3'])

        listing = broker.list_containers_iter(10, '2-', None, None, '-')
        self.assertEquals(len(listing), 1)
        self.assertEquals([row[0] for row in listing], ['3'])

        listing = broker.list_containers_iter(10, '', None, '2', '-')
        self.assertEquals(len(listing), 1)
        self.assertEquals([row[0] for row in listing], ['2'])

        listing = broker.list_containers_iter(10, '2-0050', None, '2-', '-')
        self.assertEquals(len(listing), 10)
        self.assertEquals(listing[0][0], '2-0051')
        self.assertEquals(listing[1][0], '2-0052')
        self.assertEquals(listing[-1][0], '2-0060')

        listing = broker.list_containers_iter(10, '3-0045', None, '3-', '-')
        self.assertEquals(len(listing), 10)
        self.assertEquals([row[0] for row in listing],
                           ['3-0046', '3-0047', '3-0048', '3-0049', '3-0050',
                            '3-0051', '3-0052', '3-0053', '3-0054', '3-0055'])

        self._create_container('3-0049-')
        listing = broker.list_containers_iter(10, '3-0048', None, None, None)
        self.assertEquals(len(listing), 10)
        self.assertEquals([row[0] for row in listing],
                           ['3-0048-0049', '3-0049', '3-0049-', '3-0049-0049',
                            '3-0050', '3-0050-0049', '3-0051', '3-0051-0049',
                            '3-0052', '3-0052-0049'])

        listing = broker.list_containers_iter(10, '3-0048', None, '3-', '-')
        self.assertEquals(len(listing), 10)
        self.assertEquals([row[0] for row in listing],
                           ['3-0049', '3-0050', '3-0051', '3-0052', '3-0053',
                            '3-0054', '3-0055', '3-0056', '3-0057', '3-0058'])

        listing = broker.list_containers_iter(10, None, None, '3-0049-', '-')
        self.assertEquals(len(listing), 2)
        self.assertEquals([row[0] for row in listing],
                          ['3-0049-', '3-0049-0049'])

    def test_double_check_trailing_delimiter(self):
        # Test swift.common.db.AccountBroker.list_containers_iter for an
        # account that has an odd file with a trailing delimiter
        broker = self._get_broker(account='a')
        broker.initialize(normalize_timestamp('1'))
        self._create_container('a')
        self._create_container('a-')
        self._create_container('a-a')
        self._create_container('a-a-a')
        self._create_container('a-a-b')
        self._create_container('a-b')
        self._create_container('b')
        self._create_container('b-a')
        self._create_container('b-b')
        self._create_container('c')
        listing = broker.list_containers_iter(15, None, None, None, None)
        self.assertEquals(len(listing), 10)
        self.assertEquals([row[0] for row in listing],
                           ['a', 'a-', 'a-a', 'a-a-a', 'a-a-b', 'a-b', 'b',
                            'b-a', 'b-b', 'c'])
        listing = broker.list_containers_iter(15, None, None, '', '-')
        self.assertEquals(len(listing), 3)
        self.assertEquals([row[0] for row in listing],
                          ['a', 'b', 'c'])
        listing = broker.list_containers_iter(15, None, None, 'a-', '-')
        self.assertEquals(len(listing), 3)
        self.assertEquals([row[0] for row in listing],
                          ['a-', 'a-a', 'a-b'])
        listing = broker.list_containers_iter(15, None, None, 'b-', '-')
        self.assertEquals(len(listing), 2)
        self.assertEquals([row[0] for row in listing], ['b-a', 'b-b'])

    def test_delete_db(self):
        broker = self._get_broker(account='a')
        broker.initialize(normalize_timestamp('1'))
        self.assertEqual(broker.db_file, dd._db_file)
        self.assertEqual(os.path.basename(broker.db_file), 'db_file.db')
        broker.initialize(self.initial_ts)
        self.assertTrue(os.path.isdir(self.drive_fullpath))
        self.assertEquals(self.initial_ts, broker.metadata[utils.X_TIMESTAMP])
        self.assertFalse(broker.is_deleted())
        broker.delete_db(normalize_timestamp(time()))
        # Deleting the "db" should be a NOOP
        self.assertFalse(broker.is_deleted())


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
