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

""" Tests for common.utils """

import os
import unittest
import errno
import xattr
import cPickle as pickle
import tempfile
import hashlib
import tarfile
import shutil
from collections import defaultdict
from mock import patch
from swift.common.utils import normalize_timestamp
from gluster.swift.common import utils, Glusterfs
from gluster.swift.common.exceptions import GlusterFileSystemOSError

#
# Somewhat hacky way of emulating the operation of xattr calls. They are made
# against a dictionary that stores the xattr key/value pairs.
#
_xattrs = {}
_xattr_op_cnt = defaultdict(int)
_xattr_set_err = {}
_xattr_get_err = {}
_xattr_rem_err = {}


def _xkey(path, key):
    return "%s:%s" % (path, key)


def _setxattr(path, key, value, *args, **kwargs):
    _xattr_op_cnt['set'] += 1
    xkey = _xkey(path, key)
    if xkey in _xattr_set_err:
        e = IOError()
        e.errno = _xattr_set_err[xkey]
        raise e
    global _xattrs
    _xattrs[xkey] = value


def _getxattr(path, key, *args, **kwargs):
    _xattr_op_cnt['get'] += 1
    xkey = _xkey(path, key)
    if xkey in _xattr_get_err:
        e = IOError()
        e.errno = _xattr_get_err[xkey]
        raise e
    global _xattrs
    if xkey in _xattrs:
        ret_val = _xattrs[xkey]
    else:
        e = IOError("Fake IOError")
        e.errno = errno.ENODATA
        raise e
    return ret_val


def _removexattr(path, key, *args, **kwargs):
    _xattr_op_cnt['remove'] += 1
    xkey = _xkey(path, key)
    if xkey in _xattr_rem_err:
        e = IOError()
        e.errno = _xattr_rem_err[xkey]
        raise e
    global _xattrs
    if xkey in _xattrs:
        del _xattrs[xkey]
    else:
        e = IOError("Fake IOError")
        e.errno = errno.ENODATA
        raise e


def _initxattr():
    global _xattrs
    _xattrs = {}
    global _xattr_op_cnt
    _xattr_op_cnt = defaultdict(int)
    global _xattr_set_err, _xattr_get_err, _xattr_rem_err
    _xattr_set_err = {}
    _xattr_get_err = {}
    _xattr_rem_err = {}

    # Save the current methods
    global _xattr_set;    _xattr_set    = xattr.setxattr
    global _xattr_get;    _xattr_get    = xattr.getxattr
    global _xattr_remove; _xattr_remove = xattr.removexattr

    # Monkey patch the calls we use with our internal unit test versions
    xattr.setxattr    = _setxattr
    xattr.getxattr    = _getxattr
    xattr.removexattr = _removexattr


def _destroyxattr():
    # Restore the current methods just in case
    global _xattr_set;    xattr.setxattr    = _xattr_set
    global _xattr_get;    xattr.getxattr    = _xattr_get
    global _xattr_remove; xattr.removexattr = _xattr_remove
    # Destroy the stored values and
    global _xattrs; _xattrs = None


class SimMemcache(object):
    def __init__(self):
        self._d = {}

    def get(self, key):
        return self._d.get(key, None)

    def set(self, key, value):
        self._d[key] = value


def _mock_os_fsync(fd):
    return


class TestUtils(unittest.TestCase):
    """ Tests for common.utils """

    def setUp(self):
        _initxattr()

    def tearDown(self):
        _destroyxattr()

    def test_write_metadata(self):
        path = "/tmp/foo/w"
        orig_d = { 'bar' : 'foo' }
        utils.write_metadata(path, orig_d)
        xkey = _xkey(path, utils.METADATA_KEY)
        assert len(_xattrs.keys()) == 1
        assert xkey in _xattrs
        assert orig_d == pickle.loads(_xattrs[xkey])
        assert _xattr_op_cnt['set'] == 1

    def test_write_metadata_err(self):
        path = "/tmp/foo/w"
        orig_d = { 'bar' : 'foo' }
        xkey = _xkey(path, utils.METADATA_KEY)
        _xattr_set_err[xkey] = errno.EOPNOTSUPP
        try:
            utils.write_metadata(path, orig_d)
        except IOError as e:
            assert e.errno == errno.EOPNOTSUPP
            assert len(_xattrs.keys()) == 0
            assert _xattr_op_cnt['set'] == 1
        else:
            self.fail("Expected an IOError exception on write")

    def test_write_metadata_multiple(self):
        # At 64 KB an xattr key/value pair, this should generate three keys.
        path = "/tmp/foo/w"
        orig_d = { 'bar' : 'x' * 150000 }
        utils.write_metadata(path, orig_d)
        assert len(_xattrs.keys()) == 3, "Expected 3 keys, found %d" % len(_xattrs.keys())
        payload = ''
        for i in range(0,3):
            xkey = _xkey(path, "%s%s" % (utils.METADATA_KEY, i or ''))
            assert xkey in _xattrs
            assert len(_xattrs[xkey]) <= utils.MAX_XATTR_SIZE
            payload += _xattrs[xkey]
        assert orig_d == pickle.loads(payload)
        assert _xattr_op_cnt['set'] == 3, "%r" % _xattr_op_cnt

    def test_clean_metadata(self):
        path = "/tmp/foo/c"
        expected_d = { 'a': 'y' * 150000 }
        expected_p = pickle.dumps(expected_d, utils.PICKLE_PROTOCOL)
        for i in range(0,3):
            xkey = _xkey(path, "%s%s" % (utils.METADATA_KEY, i or ''))
            _xattrs[xkey] = expected_p[:utils.MAX_XATTR_SIZE]
            expected_p = expected_p[utils.MAX_XATTR_SIZE:]
        assert not expected_p
        utils.clean_metadata(path)
        assert _xattr_op_cnt['remove'] == 4, "%r" % _xattr_op_cnt

    def test_clean_metadata_err(self):
        path = "/tmp/foo/c"
        xkey = _xkey(path, utils.METADATA_KEY)
        _xattrs[xkey] = pickle.dumps({ 'a': 'y' }, utils.PICKLE_PROTOCOL)
        _xattr_rem_err[xkey] = errno.EOPNOTSUPP
        try:
            utils.clean_metadata(path)
        except IOError as e:
            assert e.errno == errno.EOPNOTSUPP
            assert _xattr_op_cnt['remove'] == 1, "%r" % _xattr_op_cnt
        else:
            self.fail("Expected an IOError exception on remove")

    def test_read_metadata(self):
        path = "/tmp/foo/r"
        expected_d = { 'a': 'y' }
        xkey = _xkey(path, utils.METADATA_KEY)
        _xattrs[xkey] = pickle.dumps(expected_d, utils.PICKLE_PROTOCOL)
        res_d = utils.read_metadata(path)
        assert res_d == expected_d, "Expected %r, result %r" % (expected_d, res_d)
        assert _xattr_op_cnt['get'] == 1, "%r" % _xattr_op_cnt

    def test_read_metadata_notfound(self):
        path = "/tmp/foo/r"
        res_d = utils.read_metadata(path)
        assert res_d == {}
        assert _xattr_op_cnt['get'] == 1, "%r" % _xattr_op_cnt

    def test_read_metadata_err(self):
        path = "/tmp/foo/r"
        expected_d = { 'a': 'y' }
        xkey = _xkey(path, utils.METADATA_KEY)
        _xattrs[xkey] = pickle.dumps(expected_d, utils.PICKLE_PROTOCOL)
        _xattr_get_err[xkey] = errno.EOPNOTSUPP
        try:
            res_d = utils.read_metadata(path)
        except IOError as e:
            assert e.errno == errno.EOPNOTSUPP
            assert (_xattr_op_cnt['get'] == 1), "%r" % _xattr_op_cnt
        else:
            self.fail("Expected an IOError exception on get")

    def test_read_metadata_multiple(self):
        path = "/tmp/foo/r"
        expected_d = { 'a': 'y' * 150000 }
        expected_p = pickle.dumps(expected_d, utils.PICKLE_PROTOCOL)
        for i in range(0,3):
            xkey = _xkey(path, "%s%s" % (utils.METADATA_KEY, i or ''))
            _xattrs[xkey] = expected_p[:utils.MAX_XATTR_SIZE]
            expected_p = expected_p[utils.MAX_XATTR_SIZE:]
        assert not expected_p
        res_d = utils.read_metadata(path)
        assert res_d == expected_d, "Expected %r, result %r" % (expected_d, res_d)
        assert _xattr_op_cnt['get'] == 3, "%r" % _xattr_op_cnt

    def test_read_metadata_multiple_one_missing(self):
        path = "/tmp/foo/r"
        expected_d = { 'a': 'y' * 150000 }
        expected_p = pickle.dumps(expected_d, utils.PICKLE_PROTOCOL)
        for i in range(0,2):
            xkey = _xkey(path, "%s%s" % (utils.METADATA_KEY, i or ''))
            _xattrs[xkey] = expected_p[:utils.MAX_XATTR_SIZE]
            expected_p = expected_p[utils.MAX_XATTR_SIZE:]
        assert len(expected_p) <= utils.MAX_XATTR_SIZE
        res_d = utils.read_metadata(path)
        assert res_d == {}
        assert _xattr_op_cnt['get'] == 3, "%r" % _xattr_op_cnt
        assert len(_xattrs.keys()) == 0, "Expected 0 keys, found %d" % len(_xattrs.keys())

    def test_restore_metadata_none(self):
        # No initial metadata
        path = "/tmp/foo/i"
        res_d = utils.restore_metadata(path, { 'b': 'y' })
        expected_d = { 'b': 'y' }
        assert res_d == expected_d, "Expected %r, result %r" % (expected_d, res_d)
        assert _xattr_op_cnt['get'] == 1, "%r" % _xattr_op_cnt
        assert _xattr_op_cnt['set'] == 1, "%r" % _xattr_op_cnt

    def test_restore_metadata(self):
        # Initial metadata
        path = "/tmp/foo/i"
        initial_d = { 'a': 'z' }
        xkey = _xkey(path, utils.METADATA_KEY)
        _xattrs[xkey] = pickle.dumps(initial_d, utils.PICKLE_PROTOCOL)
        res_d = utils.restore_metadata(path, { 'b': 'y' })
        expected_d = { 'a': 'z', 'b': 'y' }
        assert res_d == expected_d, "Expected %r, result %r" % (expected_d, res_d)
        assert _xattr_op_cnt['get'] == 1, "%r" % _xattr_op_cnt
        assert _xattr_op_cnt['set'] == 1, "%r" % _xattr_op_cnt

    def test_restore_metadata_nochange(self):
        # Initial metadata but no changes
        path = "/tmp/foo/i"
        initial_d = { 'a': 'z' }
        xkey = _xkey(path, utils.METADATA_KEY)
        _xattrs[xkey] = pickle.dumps(initial_d, utils.PICKLE_PROTOCOL)
        res_d = utils.restore_metadata(path, {})
        expected_d = { 'a': 'z' }
        assert res_d == expected_d, "Expected %r, result %r" % (expected_d, res_d)
        assert _xattr_op_cnt['get'] == 1, "%r" % _xattr_op_cnt
        assert _xattr_op_cnt['set'] == 0, "%r" % _xattr_op_cnt

    def test_add_timestamp_empty(self):
        orig = {}
        res = utils._add_timestamp(orig)
        assert res == {}

    def test_add_timestamp_none(self):
        orig = { 'a': 1, 'b': 2, 'c': 3 }
        exp = { 'a': (1, 0), 'b': (2, 0), 'c': (3, 0) }
        res = utils._add_timestamp(orig)
        assert res == exp

    def test_add_timestamp_mixed(self):
        orig = { 'a': 1, 'b': (2, 1), 'c': 3 }
        exp = { 'a': (1, 0), 'b': (2, 1), 'c': (3, 0) }
        res = utils._add_timestamp(orig)
        assert res == exp

    def test_add_timestamp_all(self):
        orig = { 'a': (1, 0), 'b': (2, 1), 'c': (3, 0) }
        res = utils._add_timestamp(orig)
        assert res == orig

    def test_get_etag_empty(self):
        tf = tempfile.NamedTemporaryFile()
        hd = utils._get_etag(tf.name)
        assert hd == hashlib.md5().hexdigest()

    def test_get_etag(self):
        tf = tempfile.NamedTemporaryFile()
        tf.file.write('123' * utils.CHUNK_SIZE)
        tf.file.flush()
        hd = utils._get_etag(tf.name)
        tf.file.seek(0)
        md5 = hashlib.md5()
        while True:
            chunk = tf.file.read(utils.CHUNK_SIZE)
            if not chunk:
                break
            md5.update(chunk)
        assert hd == md5.hexdigest()

    def test_get_object_metadata_dne(self):
        md = utils.get_object_metadata("/tmp/doesNotEx1st")
        assert md == {}

    def test_get_object_metadata_err(self):
        tf = tempfile.NamedTemporaryFile()
        try:
            md = utils.get_object_metadata(
                os.path.join(tf.name, "doesNotEx1st"))
        except GlusterFileSystemOSError as e:
            assert e.errno != errno.ENOENT
        else:
            self.fail("Expected exception")

    obj_keys = (utils.X_TIMESTAMP, utils.X_CONTENT_TYPE, utils.X_ETAG,
                utils.X_CONTENT_LENGTH, utils.X_TYPE, utils.X_OBJECT_TYPE)

    def test_get_object_metadata_file(self):
        tf = tempfile.NamedTemporaryFile()
        tf.file.write('123'); tf.file.flush()
        md = utils.get_object_metadata(tf.name)
        for key in self.obj_keys:
            assert key in md, "Expected key %s in %r" % (key, md)
        assert md[utils.X_TYPE] == utils.OBJECT
        assert md[utils.X_OBJECT_TYPE] == utils.FILE
        assert md[utils.X_CONTENT_TYPE] == utils.FILE_TYPE
        assert md[utils.X_CONTENT_LENGTH] == os.path.getsize(tf.name)
        assert md[utils.X_TIMESTAMP] == normalize_timestamp(os.path.getctime(tf.name))
        assert md[utils.X_ETAG] == utils._get_etag(tf.name)

    def test_get_object_metadata_dir(self):
        td = tempfile.mkdtemp()
        try:
            md = utils.get_object_metadata(td)
            for key in self.obj_keys:
                assert key in md, "Expected key %s in %r" % (key, md)
            assert md[utils.X_TYPE] == utils.OBJECT
            assert md[utils.X_OBJECT_TYPE] == utils.DIR_NON_OBJECT
            assert md[utils.X_CONTENT_TYPE] == utils.DIR_TYPE
            assert md[utils.X_CONTENT_LENGTH] == 0
            assert md[utils.X_TIMESTAMP] == normalize_timestamp(os.path.getctime(td))
            assert md[utils.X_ETAG] == hashlib.md5().hexdigest()
        finally:
            os.rmdir(td)

    def test_create_object_metadata_file(self):
        tf = tempfile.NamedTemporaryFile()
        tf.file.write('4567'); tf.file.flush()
        r_md = utils.create_object_metadata(tf.name)

        xkey = _xkey(tf.name, utils.METADATA_KEY)
        assert len(_xattrs.keys()) == 1
        assert xkey in _xattrs
        assert _xattr_op_cnt['get'] == 1
        assert _xattr_op_cnt['set'] == 1
        md = pickle.loads(_xattrs[xkey])
        assert r_md == md

        for key in self.obj_keys:
            assert key in md, "Expected key %s in %r" % (key, md)
        assert md[utils.X_TYPE] == utils.OBJECT
        assert md[utils.X_OBJECT_TYPE] == utils.FILE
        assert md[utils.X_CONTENT_TYPE] == utils.FILE_TYPE
        assert md[utils.X_CONTENT_LENGTH] == os.path.getsize(tf.name)
        assert md[utils.X_TIMESTAMP] == normalize_timestamp(os.path.getctime(tf.name))
        assert md[utils.X_ETAG] == utils._get_etag(tf.name)

    def test_create_object_metadata_dir(self):
        td = tempfile.mkdtemp()
        try:
            r_md = utils.create_object_metadata(td)

            xkey = _xkey(td, utils.METADATA_KEY)
            assert len(_xattrs.keys()) == 1
            assert xkey in _xattrs
            assert _xattr_op_cnt['get'] == 1
            assert _xattr_op_cnt['set'] == 1
            md = pickle.loads(_xattrs[xkey])
            assert r_md == md

            for key in self.obj_keys:
                assert key in md, "Expected key %s in %r" % (key, md)
            assert md[utils.X_TYPE] == utils.OBJECT
            assert md[utils.X_OBJECT_TYPE] == utils.DIR_NON_OBJECT
            assert md[utils.X_CONTENT_TYPE] == utils.DIR_TYPE
            assert md[utils.X_CONTENT_LENGTH] == 0
            assert md[utils.X_TIMESTAMP] == normalize_timestamp(os.path.getctime(td))
            assert md[utils.X_ETAG] == hashlib.md5().hexdigest()
        finally:
            os.rmdir(td)

    def test_get_container_metadata(self):
        def _mock_get_container_details(path):
            o_list = [ 'a', 'b', 'c' ]
            o_count = 3
            b_used = 47
            return o_list, o_count, b_used
        orig_gcd = utils.get_container_details
        utils.get_container_details = _mock_get_container_details
        td = tempfile.mkdtemp()
        try:
            exp_md = {
                utils.X_TYPE: (utils.CONTAINER, 0),
                utils.X_TIMESTAMP: (normalize_timestamp(os.path.getctime(td)), 0),
                utils.X_PUT_TIMESTAMP: (normalize_timestamp(os.path.getmtime(td)), 0),
                utils.X_OBJECTS_COUNT: (3, 0),
                utils.X_BYTES_USED: (47, 0),
                }
            md = utils.get_container_metadata(td)
            assert md == exp_md
        finally:
            utils.get_container_details = orig_gcd
            os.rmdir(td)

    def test_get_account_metadata(self):
        def _mock_get_account_details(path):
            c_list = [ '123', 'abc' ]
            c_count = 2
            return c_list, c_count
        orig_gad = utils.get_account_details
        utils.get_account_details = _mock_get_account_details
        td = tempfile.mkdtemp()
        try:
            exp_md = {
                utils.X_TYPE: (utils.ACCOUNT, 0),
                utils.X_TIMESTAMP: (normalize_timestamp(os.path.getctime(td)), 0),
                utils.X_PUT_TIMESTAMP: (normalize_timestamp(os.path.getmtime(td)), 0),
                utils.X_OBJECTS_COUNT: (0, 0),
                utils.X_BYTES_USED: (0, 0),
                utils.X_CONTAINER_COUNT: (2, 0),
                }
            md = utils.get_account_metadata(td)
            assert md == exp_md
        finally:
            utils.get_account_details = orig_gad
            os.rmdir(td)

    cont_keys = [utils.X_TYPE, utils.X_TIMESTAMP, utils.X_PUT_TIMESTAMP,
                 utils.X_OBJECTS_COUNT, utils.X_BYTES_USED]

    def test_create_container_metadata(self):
        td = tempfile.mkdtemp()
        try:
            r_md = utils.create_container_metadata(td)

            xkey = _xkey(td, utils.METADATA_KEY)
            assert len(_xattrs.keys()) == 1
            assert xkey in _xattrs
            assert _xattr_op_cnt['get'] == 1
            assert _xattr_op_cnt['set'] == 1
            md = pickle.loads(_xattrs[xkey])
            assert r_md == md

            for key in self.cont_keys:
                assert key in md, "Expected key %s in %r" % (key, md)
            assert md[utils.X_TYPE] == (utils.CONTAINER, 0)
            assert md[utils.X_TIMESTAMP] == (normalize_timestamp(os.path.getctime(td)), 0)
            assert md[utils.X_PUT_TIMESTAMP] == (normalize_timestamp(os.path.getmtime(td)), 0)
            assert md[utils.X_OBJECTS_COUNT] == (0, 0)
            assert md[utils.X_BYTES_USED] == (0, 0)
        finally:
            os.rmdir(td)

    acct_keys = [val for val in cont_keys]
    acct_keys.append(utils.X_CONTAINER_COUNT)

    def test_create_account_metadata(self):
        td = tempfile.mkdtemp()
        try:
            r_md = utils.create_account_metadata(td)

            xkey = _xkey(td, utils.METADATA_KEY)
            assert len(_xattrs.keys()) == 1
            assert xkey in _xattrs
            assert _xattr_op_cnt['get'] == 1
            assert _xattr_op_cnt['set'] == 1
            md = pickle.loads(_xattrs[xkey])
            assert r_md == md

            for key in self.acct_keys:
                assert key in md, "Expected key %s in %r" % (key, md)
            assert md[utils.X_TYPE] == (utils.ACCOUNT, 0)
            assert md[utils.X_TIMESTAMP] == (normalize_timestamp(os.path.getctime(td)), 0)
            assert md[utils.X_PUT_TIMESTAMP] == (normalize_timestamp(os.path.getmtime(td)), 0)
            assert md[utils.X_OBJECTS_COUNT] == (0, 0)
            assert md[utils.X_BYTES_USED] == (0, 0)
            assert md[utils.X_CONTAINER_COUNT] == (0, 0)
        finally:
            os.rmdir(td)

    def test_get_account_details(self):
        orig_cwd = os.getcwd()
        td = tempfile.mkdtemp()
        try:
            tf = tarfile.open("common/data/account_tree.tar.bz2", "r:bz2")
            os.chdir(td)
            tf.extractall()

            container_list, container_count = utils.get_account_details(td)
            assert container_count == 3
            assert set(container_list) == set(['c1', 'c2', 'c3'])
        finally:
            os.chdir(orig_cwd)
            shutil.rmtree(td)

    def test_get_account_details_notadir(self):
        tf = tempfile.NamedTemporaryFile()
        container_list, container_count = utils.get_account_details(tf.name)
        assert container_count == 0
        assert container_list == []

    def test_get_container_details_notadir(self):
        tf = tempfile.NamedTemporaryFile()
        obj_list, object_count, bytes_used = \
            utils.get_container_details(tf.name)
        assert bytes_used == 0
        assert object_count == 0
        assert obj_list == []

    def test_get_container_details(self):
        orig_cwd = os.getcwd()
        td = tempfile.mkdtemp()
        try:
            tf = tarfile.open("common/data/container_tree.tar.bz2", "r:bz2")
            os.chdir(td)
            tf.extractall()

            obj_list, object_count, bytes_used = \
                utils.get_container_details(td)
            assert bytes_used == 0, repr(bytes_used)
            # Should not include the directories
            assert object_count == 5, repr(object_count)
            assert set(obj_list) == set(['file1', 'file3', 'file2',
                                         'dir1/file1', 'dir1/file2'
                                         ]), repr(obj_list)

            full_dir1 = os.path.join(td, 'dir1')
            full_dir2 = os.path.join(td, 'dir2')
            full_dir3 = os.path.join(td, 'dir3')
            exp_dir_dict = { td:        os.path.getmtime(td),
                             full_dir1: os.path.getmtime(full_dir1),
                             full_dir2: os.path.getmtime(full_dir2),
                             full_dir3: os.path.getmtime(full_dir3),
                             }
        finally:
            os.chdir(orig_cwd)
            shutil.rmtree(td)

    def test_get_container_details_and_size(self):
        orig_cwd = os.getcwd()
        __do_getsize = Glusterfs._do_getsize
        td = tempfile.mkdtemp()
        try:
            Glusterfs._do_getsize = False
            tf = tarfile.open("common/data/container_tree.tar.bz2", "r:bz2")
            os.chdir(td)
            tf.extractall()

            obj_list, object_count, bytes_used = \
                utils.get_container_details(td)
            assert bytes_used == 0, repr(bytes_used)
            assert object_count == 5, repr(object_count)
            assert set(obj_list) == set(['file1', 'file3', 'file2',
                                         'dir1/file1', 'dir1/file2'
                                         ]), repr(obj_list)

            full_dir1 = os.path.join(td, 'dir1')
            full_dir2 = os.path.join(td, 'dir2')
            full_dir3 = os.path.join(td, 'dir3')
            exp_dir_dict = { td:        os.path.getmtime(td),
                             full_dir1: os.path.getmtime(full_dir1),
                             full_dir2: os.path.getmtime(full_dir2),
                             full_dir3: os.path.getmtime(full_dir3),
                             }
        finally:
            Glusterfs._do_getsize = __do_getsize
            os.chdir(orig_cwd)
            shutil.rmtree(td)

    def test_get_container_details_from_fs_do_getsize_true(self):
        orig_cwd = os.getcwd()
        __do_getsize = Glusterfs._do_getsize
        td = tempfile.mkdtemp()
        try:
            tf = tarfile.open("common/data/container_tree.tar.bz2", "r:bz2")
            os.chdir(td)
            tf.extractall()

            Glusterfs._do_getsize = True

            obj_list, object_count, bytes_used = \
                utils.get_container_details(td)
            assert bytes_used == 30, repr(bytes_used)
            assert object_count == 5, repr(object_count)
            assert set(obj_list) == set(['file1', 'file3', 'file2',
                                         'dir1/file1', 'dir1/file2'
                                         ]), repr(obj_list)

            full_dir1 = os.path.join(td, 'dir1')
            full_dir2 = os.path.join(td, 'dir2')
            full_dir3 = os.path.join(td, 'dir3')
            exp_dir_dict = { td:        os.path.getmtime(td),
                             full_dir1: os.path.getmtime(full_dir1),
                             full_dir2: os.path.getmtime(full_dir2),
                             full_dir3: os.path.getmtime(full_dir3),
                             }
        finally:
            Glusterfs._do_getsize = __do_getsize
            os.chdir(orig_cwd)
            shutil.rmtree(td)

    def test_write_pickle(self):
        td = tempfile.mkdtemp()
        try:
            fpp = os.path.join(td, 'pp')
            # FIXME: Remove this patch when coverage.py can handle eventlet
            with patch("os.fsync", _mock_os_fsync):
                utils.write_pickle('pickled peppers', fpp)
            with open(fpp, "rb") as f:
                contents = f.read()
            s = pickle.loads(contents)
            assert s == 'pickled peppers', repr(s)
        finally:
            shutil.rmtree(td)

    def test_write_pickle_ignore_tmp(self):
        tf = tempfile.NamedTemporaryFile()
        td = tempfile.mkdtemp()
        try:
            fpp = os.path.join(td, 'pp')
            # Also test an explicity pickle protocol
            # FIXME: Remove this patch when coverage.py can handle eventlet
            with patch("os.fsync", _mock_os_fsync):
                utils.write_pickle('pickled peppers', fpp, tmp=tf.name,
                                   pickle_protocol=2)
            with open(fpp, "rb") as f:
                contents = f.read()
            s = pickle.loads(contents)
            assert s == 'pickled peppers', repr(s)
            with open(tf.name, "rb") as f:
                contents = f.read()
            assert contents == ''
        finally:
            shutil.rmtree(td)

    def test_check_user_xattr_bad_path(self):
        assert False == utils.check_user_xattr("/tmp/foo/bar/check/user/xattr")

    def test_check_user_xattr_bad_set(self):
        td = tempfile.mkdtemp()
        xkey = _xkey(td, 'user.test.key1')
        _xattr_set_err[xkey] = errno.EOPNOTSUPP
        try:
            assert False == utils.check_user_xattr(td)
        except IOError:
            pass
        else:
            self.fail("Expected IOError")
        finally:
            shutil.rmtree(td)

    def test_check_user_xattr_bad_remove(self):
        td = tempfile.mkdtemp()
        xkey = _xkey(td, 'user.test.key1')
        _xattr_rem_err[xkey] = errno.EOPNOTSUPP
        try:
            utils.check_user_xattr(td)
        except IOError:
            self.fail("Unexpected IOError")
        finally:
            shutil.rmtree(td)

    def test_check_user_xattr(self):
        td = tempfile.mkdtemp()
        try:
            assert utils.check_user_xattr(td)
        finally:
            shutil.rmtree(td)

    def test_validate_container_empty(self):
        ret = utils.validate_container({})
        assert ret == False

    def test_validate_container_missing_keys(self):
        ret = utils.validate_container({ 'foo': 'bar' })
        assert ret == False

    def test_validate_container_bad_type(self):
        md = { utils.X_TYPE: ('bad', 0),
               utils.X_TIMESTAMP: ('na', 0),
               utils.X_PUT_TIMESTAMP: ('na', 0),
               utils.X_OBJECTS_COUNT: ('na', 0),
               utils.X_BYTES_USED: ('na', 0) }
        ret = utils.validate_container(md)
        assert ret == False

    def test_validate_container_good_type(self):
        md = { utils.X_TYPE: (utils.CONTAINER, 0),
               utils.X_TIMESTAMP: ('na', 0),
               utils.X_PUT_TIMESTAMP: ('na', 0),
               utils.X_OBJECTS_COUNT: ('na', 0),
               utils.X_BYTES_USED: ('na', 0) }
        ret = utils.validate_container(md)
        assert ret

    def test_validate_account_empty(self):
        ret = utils.validate_account({})
        assert ret == False

    def test_validate_account_missing_keys(self):
        ret = utils.validate_account({ 'foo': 'bar' })
        assert ret == False

    def test_validate_account_bad_type(self):
        md = { utils.X_TYPE: ('bad', 0),
               utils.X_TIMESTAMP: ('na', 0),
               utils.X_PUT_TIMESTAMP: ('na', 0),
               utils.X_OBJECTS_COUNT: ('na', 0),
               utils.X_BYTES_USED: ('na', 0),
               utils.X_CONTAINER_COUNT: ('na', 0) }
        ret = utils.validate_account(md)
        assert ret == False

    def test_validate_account_good_type(self):
        md = { utils.X_TYPE: (utils.ACCOUNT, 0),
               utils.X_TIMESTAMP: ('na', 0),
               utils.X_PUT_TIMESTAMP: ('na', 0),
               utils.X_OBJECTS_COUNT: ('na', 0),
               utils.X_BYTES_USED: ('na', 0),
               utils.X_CONTAINER_COUNT: ('na', 0) }
        ret = utils.validate_account(md)
        assert ret

    def test_validate_object_empty(self):
        ret = utils.validate_object({})
        assert ret == False

    def test_validate_object_missing_keys(self):
        ret = utils.validate_object({ 'foo': 'bar' })
        assert ret == False

    def test_validate_object_bad_type(self):
        md = { utils.X_TIMESTAMP: 'na',
               utils.X_CONTENT_TYPE: 'na',
               utils.X_ETAG: 'bad',
               utils.X_CONTENT_LENGTH: 'na',
               utils.X_TYPE: 'bad',
               utils.X_OBJECT_TYPE: 'na' }
        ret = utils.validate_object(md)
        assert ret == False

    def test_validate_object_good_type(self):
        md = { utils.X_TIMESTAMP: 'na',
               utils.X_CONTENT_TYPE: 'na',
               utils.X_ETAG: 'bad',
               utils.X_CONTENT_LENGTH: 'na',
               utils.X_TYPE: utils.OBJECT,
               utils.X_OBJECT_TYPE: 'na' }
        ret = utils.validate_object(md)
        assert ret

class TestUtilsDirObjects(unittest.TestCase):
    def setUp(self):
        _initxattr()
        self.dirs = ['dir1',
                'dir1/dir2',
                'dir1/dir2/dir3' ]
        self.files = ['file1',
                'file2',
                'dir1/dir2/file3']
        self.tempdir = tempfile.mkdtemp()
        self.rootdir = os.path.join(self.tempdir, 'a')
        for d in self.dirs:
            os.makedirs(os.path.join(self.rootdir, d))
        for f in self.files:
            open(os.path.join(self.rootdir, f), 'w').close()

    def tearDown(self):
        _destroyxattr()
        shutil.rmtree(self.tempdir)

    def _set_dir_object(self, obj):
        metadata = utils.read_metadata(os.path.join(self.rootdir, obj))
        metadata[utils.X_OBJECT_TYPE] = utils.DIR_OBJECT
        utils.write_metadata(os.path.join(self.rootdir, self.dirs[0]),
                metadata)

    def _clear_dir_object(self, obj):
        metadata = utils.read_metadata(os.path.join(self.rootdir, obj))
        metadata[utils.X_OBJECT_TYPE] = utils.DIR_NON_OBJECT
        utils.write_metadata(os.path.join(self.rootdir, obj),
                metadata)

    def test_rmobjdir_removing_files(self):
        self.assertFalse(utils.rmobjdir(self.rootdir))

        # Remove the files
        for f in self.files:
            os.unlink(os.path.join(self.rootdir, f))

        self.assertTrue(utils.rmobjdir(self.rootdir))

    def test_rmobjdir_removing_dirs(self):
        self.assertFalse(utils.rmobjdir(self.rootdir))

        # Remove the files
        for f in self.files:
            os.unlink(os.path.join(self.rootdir, f))

        self._set_dir_object(self.dirs[0])
        self.assertFalse(utils.rmobjdir(self.rootdir))
        self._clear_dir_object(self.dirs[0])
        self.assertTrue(utils.rmobjdir(self.rootdir))

    def test_rmobjdir_metadata_errors(self):

        def _mock_rm(path):
            print "_mock_rm-metadata_errors(%s)" % path
            if path.endswith("dir3"):
                raise OSError(13, "foo")
            return {}

        _orig_rm = utils.read_metadata
        utils.read_metadata = _mock_rm
        try:
            try:
                utils.rmobjdir(self.rootdir)
            except OSError:
                pass
            else:
                self.fail("Expected OSError")
        finally:
            utils.read_metadata = _orig_rm

    def test_rmobjdir_metadata_enoent(self):

        def _mock_rm(path):
            print "_mock_rm-metadata_enoent(%s)" % path
            shutil.rmtree(path)
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

        # Remove the files
        for f in self.files:
            os.unlink(os.path.join(self.rootdir, f))

        _orig_rm = utils.read_metadata
        utils.read_metadata = _mock_rm
        try:
            try:
                self.assertTrue(utils.rmobjdir(self.rootdir))
            except OSError:
                self.fail("Unexpected OSError")
            else:
                pass
        finally:
            utils.read_metadata = _orig_rm

    def test_rmobjdir_rmdir_enoent(self):

        seen = [0]
        _orig_rm = utils.do_rmdir

        def _mock_rm(path):
            print "_mock_rm-rmdir_enoent(%s)" % path
            if path == self.rootdir and not seen[0]:
                seen[0] = 1
                raise OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY))
            else:
                shutil.rmtree(path)
                raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

        # Remove the files
        for f in self.files:
            os.unlink(os.path.join(self.rootdir, f))

        utils.do_rmdir = _mock_rm
        try:
            try:
                self.assertTrue(utils.rmobjdir(self.rootdir))
            except OSError:
                self.fail("Unexpected OSError")
            else:
                pass
        finally:
            utils.do_rmdir = _orig_rm

    def test_rmobjdir_rmdir_error(self):

        seen = [0]
        _orig_rm = utils.do_rmdir

        def _mock_rm(path):
            print "_mock_rm-rmdir_enoent(%s)" % path
            if path == self.rootdir and not seen[0]:
                seen[0] = 1
                raise OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY))
            else:
                raise OSError(errno.EACCES, os.strerror(errno.EACCES))

        # Remove the files
        for f in self.files:
            os.unlink(os.path.join(self.rootdir, f))

        utils.do_rmdir = _mock_rm
        try:
            try:
                utils.rmobjdir(self.rootdir)
            except OSError:
                pass
            else:
                self.fail("Expected OSError")
        finally:
            utils.do_rmdir = _orig_rm

    def test_rmobjdir_files_left_in_top_dir(self):

        seen = [0]
        _orig_rm = utils.do_rmdir

        def _mock_rm(path):
            print "_mock_rm-files_left_in_top_dir(%s)" % path
            if path == self.rootdir:
                if not seen[0]:
                    seen[0] = 1
                    raise OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY))
                else:
                    return _orig_rm(path)
            else:
                shutil.rmtree(path)
                raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

        # Remove the files, leaving the ones at the root
        for f in self.files:
            if f.startswith('dir'):
                os.unlink(os.path.join(self.rootdir, f))

        utils.do_rmdir = _mock_rm
        try:
            try:
                self.assertFalse(utils.rmobjdir(self.rootdir))
            except OSError:
                self.fail("Unexpected OSError")
            else:
                pass
        finally:
            utils.do_rmdir = _orig_rm

    def test_rmobjdir_error_final_rmdir(self):

        seen = [0]
        _orig_rm = utils.do_rmdir

        def _mock_rm(path):
            print "_mock_rm-files_left_in_top_dir(%s)" % path
            if path == self.rootdir:
                if not seen[0]:
                    seen[0] = 1
                    raise OSError(errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY))
                else:
                    raise OSError(errno.EACCES, os.strerror(errno.EACCES))
            else:
                shutil.rmtree(path)
                raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

        # Remove the files, leaving the ones at the root
        for f in self.files:
            os.unlink(os.path.join(self.rootdir, f))

        utils.do_rmdir = _mock_rm
        try:
            try:
                utils.rmobjdir(self.rootdir)
            except OSError:
                pass
            else:
                self.fail("Expected OSError")
        finally:
            utils.do_rmdir = _orig_rm
