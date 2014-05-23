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
import stat
import errno
try:
    from random import SystemRandom
    random = SystemRandom()
except ImportError:
    import random
import logging
import time
from collections import defaultdict
from socket import gethostname
from hashlib import md5
from eventlet import sleep
from greenlet import getcurrent
from contextlib import contextmanager
from gluster.swift.common.exceptions import AlreadyExistsAsFile, \
    AlreadyExistsAsDir
from swift.common.utils import TRUE_VALUES, ThreadPool, config_true_value
from swift.common.exceptions import DiskFileNotExist, DiskFileError, \
    DiskFileNoSpace, DiskFileDeviceUnavailable, DiskFileNotOpen, \
    DiskFileExpired
from swift.common.swob import multi_range_iterator

from gluster.swift.common.exceptions import GlusterFileSystemOSError
from gluster.swift.common.Glusterfs import mount
from gluster.swift.common.fs_utils import do_fstat, do_open, do_close, \
    do_unlink, do_chown, do_fsync, do_fchown, do_stat, do_write, do_read, \
    do_fadvise64, do_rename, do_fdatasync, do_lseek, do_mkdir
from gluster.swift.common.utils import read_metadata, write_metadata, \
    validate_object, create_object_metadata, rmobjdir, dir_is_object, \
    get_object_metadata
from gluster.swift.common.utils import X_CONTENT_TYPE, \
    X_TIMESTAMP, X_TYPE, X_OBJECT_TYPE, FILE, OBJECT, DIR_TYPE, \
    FILE_TYPE, DEFAULT_UID, DEFAULT_GID, DIR_NON_OBJECT, DIR_OBJECT, \
    X_ETAG, X_CONTENT_LENGTH
from ConfigParser import ConfigParser, NoSectionError, NoOptionError

# FIXME: Hopefully we'll be able to move to Python 2.7+ where O_CLOEXEC will
# be back ported. See http://www.python.org/dev/peps/pep-0433/
O_CLOEXEC = 02000000

DEFAULT_DISK_CHUNK_SIZE = 65536
DEFAULT_KEEP_CACHE_SIZE = (5 * 1024 * 1024)
DEFAULT_MB_PER_SYNC = 512
# keep these lower-case
DISALLOWED_HEADERS = set('content-length content-type deleted etag'.split())

MAX_RENAME_ATTEMPTS = 10
MAX_OPEN_ATTEMPTS = 10

_cur_pid = str(os.getpid())
_cur_host = str(gethostname())


def _random_sleep():
    sleep(random.uniform(0.5, 0.15))


def make_directory(full_path, uid, gid, metadata=None):
    """
    Make a directory and change the owner ship as specified, and potentially
    creating the object metadata if requested.
    """
    try:
        do_mkdir(full_path)
    except OSError as err:
        if err.errno == errno.ENOENT:
            # Tell the caller some directory of the parent path does not
            # exist.
            return False, metadata
        elif err.errno == errno.EEXIST:
            # Possible race, in that the caller invoked this method when it
            # had previously determined the file did not exist.
            #
            # FIXME: When we are confident, remove this stat() call as it is
            # not necessary.
            try:
                stats = do_stat(full_path)
            except GlusterFileSystemOSError as serr:
                # FIXME: Ideally we'd want to return an appropriate error
                # message and code in the PUT Object REST API response.
                raise DiskFileError("make_directory: mkdir failed"
                                    " because path %s already exists, and"
                                    " a subsequent stat on that same"
                                    " path failed (%s)" % (full_path,
                                                           str(serr)))
            else:
                is_dir = stat.S_ISDIR(stats.st_mode)
                if not is_dir:
                    # FIXME: Ideally we'd want to return an appropriate error
                    # message and code in the PUT Object REST API response.
                    raise AlreadyExistsAsFile("make_directory:"
                                              " mkdir failed on path %s"
                                              " because it already exists"
                                              " but not as a directory"
                                              % (full_path))
            return True, metadata
        elif err.errno == errno.ENOTDIR:
            # FIXME: Ideally we'd want to return an appropriate error
            # message and code in the PUT Object REST API response.
            raise AlreadyExistsAsFile("make_directory:"
                                      " mkdir failed because some "
                                      "part of path %s is not in fact"
                                      " a directory" % (full_path))
        elif err.errno == errno.EIO:
            # Sometimes Fuse will return an EIO error when it does not know
            # how to handle an unexpected, but transient situation. It is
            # possible the directory now exists, stat() it to find out after a
            # short period of time.
            _random_sleep()
            try:
                stats = do_stat(full_path)
            except GlusterFileSystemOSError as serr:
                if serr.errno == errno.ENOENT:
                    errmsg = "make_directory: mkdir failed on" \
                             " path %s (EIO), and a subsequent stat on" \
                             " that same path did not find the file." % (
                                 full_path,)
                else:
                    errmsg = "make_directory: mkdir failed on" \
                             " path %s (%s), and a subsequent stat on" \
                             " that same path failed as well (%s)" % (
                                 full_path, str(err), str(serr))
                raise DiskFileError(errmsg)
            else:
                if not stats:
                    errmsg = "make_directory: mkdir failed on" \
                             " path %s (EIO), and a subsequent stat on" \
                             " that same path did not find the file." % (
                                 full_path,)
                    raise DiskFileError(errmsg)
                else:
                    # The directory at least exists now
                    is_dir = stat.S_ISDIR(stats.st_mode)
                    if is_dir:
                        # Dump the stats to the log with the original exception
                        logging.warn("make_directory: mkdir initially"
                                     " failed on path %s (%s) but a stat()"
                                     " following that succeeded: %r" %
                                     (full_path, str(err), stats))
                        # Assume another entity took care of the proper setup.
                        return True, metadata
                    else:
                        raise DiskFileError("make_directory: mkdir"
                                            " initially failed on path %s (%s)"
                                            " but now we see that it exists"
                                            " but is not a directory (%r)" %
                                            (full_path, str(err), stats))
        else:
            # Some other potentially rare exception occurred that does not
            # currently warrant a special log entry to help diagnose.
            raise DiskFileError("make_directory: mkdir failed on"
                                " path %s (%s)" % (full_path, str(err)))
    else:
        if metadata:
            # We were asked to set the initial metadata for this object.
            metadata_orig = get_object_metadata(full_path)
            metadata_orig.update(metadata)
            write_metadata(full_path, metadata_orig)
            metadata = metadata_orig

        # We created it, so we are reponsible for always setting the proper
        # ownership.
        do_chown(full_path, uid, gid)
        return True, metadata


_fs_conf = ConfigParser()
if _fs_conf.read(os.path.join('/etc/swift', 'fs.conf')):
    try:
        _mkdir_locking = _fs_conf.get('DEFAULT', 'mkdir_locking', "no") \
            in TRUE_VALUES
        logging.warn("The option mkdir_locking has been deprecated and is"
                     " no longer supported")
    except (NoSectionError, NoOptionError):
        pass
    try:
        _use_put_mount = _fs_conf.get('DEFAULT', 'use_put_mount', "no") \
            in TRUE_VALUES
    except (NoSectionError, NoOptionError):
        _use_put_mount = False
else:
    _use_put_mount = False


def _adjust_metadata(metadata):
    # Fix up the metadata to ensure it has a proper value for the
    # Content-Type metadata, as well as an X_TYPE and X_OBJECT_TYPE
    # metadata values.
    content_type = metadata.get(X_CONTENT_TYPE, '')

    if not content_type:
        # FIXME: How can this be that our caller supplied us with metadata
        # that has a content type that evaluates to False?
        #
        # FIXME: If the file exists, we would already know it is a
        # directory. So why are we assuming it is a file object?
        metadata[X_CONTENT_TYPE] = FILE_TYPE
        metadata[X_OBJECT_TYPE] = FILE
    else:
        if content_type.lower() == DIR_TYPE:
            metadata[X_OBJECT_TYPE] = DIR_OBJECT
        else:
            metadata[X_OBJECT_TYPE] = FILE

    metadata[X_TYPE] = OBJECT
    return metadata


class OnDiskManager(object):
    """
    Management class for devices, providing common place for shared parameters
    and methods not provided by the DiskFile class (which primarily services
    the object server REST API layer).

    The `get_diskfile()` method is how this implementation creates a `DiskFile`
    object.

    .. note::

        This class is reference implementation specific and not part of the
        pluggable on-disk backend API.

    :param conf: caller provided configuration object
    :param logger: caller provided logger
    """
    def __init__(self, conf, logger):
        self.logger = logger
        self.disk_chunk_size = int(conf.get('disk_chunk_size',
                                            DEFAULT_DISK_CHUNK_SIZE))
        self.keep_cache_size = int(conf.get('keep_cache_size',
                                            DEFAULT_KEEP_CACHE_SIZE))
        self.bytes_per_sync = int(conf.get('mb_per_sync',
                                           DEFAULT_MB_PER_SYNC)) * 1024 * 1024
        self.devices = conf.get('devices', '/srv/node/')
        self.mount_check = config_true_value(conf.get('mount_check', 'true'))
        threads_per_disk = int(conf.get('threads_per_disk', '0'))
        self.threadpools = defaultdict(
            lambda: ThreadPool(nthreads=threads_per_disk))

    def _get_dev_path(self, device):
        """
        Return the path to a device, checking to see that it is a proper mount
        point based on a configuration parameter.

        :param device: name of target device
        :returns: full path to the device, None if the path to the device is
                  not a proper mount point.
        """
        if self.mount_check and not mount(self.devices, device):
            dev_path = None
        else:
            dev_path = os.path.join(self.devices, device)
        return dev_path

    def get_diskfile(self, device, account, container, obj,
                     **kwargs):
        dev_path = self._get_dev_path(device)
        if not dev_path:
            raise DiskFileDeviceUnavailable()
        return DiskFile(self, dev_path, self.threadpools[device],
                        account, container, obj, **kwargs)


class DiskFileWriter(object):
    """
    Encapsulation of the write context for servicing PUT REST API
    requests. Serves as the context manager object for DiskFile's create()
    method.


    """
    def __init__(self, fd, tmppath, disk_file):
        # Parameter tracking
        self._fd = fd
        self._tmppath = tmppath
        self._disk_file = disk_file

        # Internal attributes
        self._upload_size = 0
        self._last_sync = 0

    def _write_entire_chunk(self, chunk):
        bytes_per_sync = self._disk_file._mgr.bytes_per_sync
        while chunk:
            written = do_write(self._fd, chunk)
            chunk = chunk[written:]
            self._upload_size += written
            # For large files sync every 512MB (by default) written
            diff = self._upload_size - self._last_sync
            if diff >= bytes_per_sync:
                do_fdatasync(self._fd)
                do_fadvise64(self._fd, self._last_sync, diff)
                self._last_sync = self._upload_size

    def close(self):
        """
        Close the file descriptor
        """
        if self._fd:
            do_close(self._fd)
            self._fd = None

    def write(self, chunk):
        """
        Write a chunk of data to disk.

        For this implementation, the data is written into a temporary file.

        :param chunk: the chunk of data to write as a string object

        :returns: the total number of bytes written to an object
        """
        df = self._disk_file
        df._threadpool.run_in_thread(self._write_entire_chunk, chunk)
        return self._upload_size

    def _finalize_put(self, metadata):
        # Write out metadata before fsync() to ensure it is also forced to
        # disk.
        write_metadata(self._fd, metadata)

        # We call fsync() before calling drop_cache() to lower the
        # amount of redundant work the drop cache code will perform on
        # the pages (now that after fsync the pages will be all
        # clean).
        do_fsync(self._fd)
        # From the Department of the Redundancy Department, make sure
        # we call drop_cache() after fsync() to avoid redundant work
        # (pages all clean).
        do_fadvise64(self._fd, self._last_sync, self._upload_size)

        # At this point we know that the object's full directory path
        # exists, so we can just rename it directly without using Swift's
        # swift.common.utils.renamer(), which makes the directory path and
        # adds extra stat() calls.
        df = self._disk_file
        attempts = 1
        while True:
            try:
                do_rename(self._tmppath, df._data_file)
            except OSError as err:
                if err.errno in (errno.ENOENT, errno.EIO) \
                        and attempts < MAX_RENAME_ATTEMPTS:
                    # FIXME: Why either of these two error conditions is
                    # happening is unknown at this point. This might be a
                    # FUSE issue of some sort or a possible race
                    # condition. So let's sleep on it, and double check
                    # the environment after a good nap.
                    _random_sleep()
                    # Tease out why this error occurred. The man page for
                    # rename reads:
                    #   "The link named by tmppath does not exist; or, a
                    #    directory component in data_file does not exist;
                    #    or, tmppath or data_file is an empty string."
                    assert len(self._tmppath) > 0 and len(df._data_file) > 0
                    tpstats = do_stat(self._tmppath)
                    tfstats = do_fstat(self._fd)
                    assert tfstats
                    if not tpstats or tfstats.st_ino != tpstats.st_ino:
                        # Temporary file name conflict
                        raise DiskFileError(
                            'DiskFile.put(): temporary file, %s, was'
                            ' already renamed (targeted for %s)' % (
                                self._tmppath, df._data_file))
                    else:
                        # Data file target name now has a bad path!
                        dfstats = do_stat(df._put_datadir)
                        if not dfstats:
                            raise DiskFileError(
                                'DiskFile.put(): path to object, %s, no'
                                ' longer exists (targeted for %s)' % (
                                    df._put_datadir, df._data_file))
                        else:
                            is_dir = stat.S_ISDIR(dfstats.st_mode)
                            if not is_dir:
                                raise DiskFileError(
                                    'DiskFile.put(): path to object, %s,'
                                    ' no longer a directory (targeted for'
                                    ' %s)' % (self._put_datadir,
                                              df._data_file))
                            else:
                                # Let's retry since everything looks okay
                                logging.warn(
                                    "DiskFile.put(): rename('%s','%s')"
                                    " initially failed (%s) but a"
                                    " stat('%s') following that succeeded:"
                                    " %r" % (
                                        self._tmppath, df._data_file, str(err),
                                        df._put_datadir, dfstats))
                                attempts += 1
                                continue
                else:
                    raise GlusterFileSystemOSError(
                        err.errno, "%s, rename('%s', '%s')" % (
                            err.strerror, self._tmppath, df._data_file))
            else:
                # Success!
                break
        # Close here so the calling context does not have to perform this
        # in a thread.
        self.close()

    def put(self, metadata):
        """
        Finalize writing the file on disk, and renames it from the temp file
        to the real location.  This should be called after the data has been
        written to the temp file.

        :param metadata: dictionary of metadata to be written
        :raises AlreadyExistsAsDir : If there exists a directory of the same
                                     name
        """
        assert self._tmppath is not None
        metadata = _adjust_metadata(metadata)
        df = self._disk_file

        if dir_is_object(metadata):
            df._threadpool.force_run_in_thread(
                df._create_dir_object, df._data_file, metadata)
            return

        if df._is_dir:
            # A pre-existing directory already exists on the file
            # system, perhaps gratuitously created when another
            # object was created, or created externally to Swift
            # REST API servicing (UFO use case).
            raise AlreadyExistsAsDir('DiskFile.put(): file creation failed'
                                     ' since the target, %s, already exists'
                                     ' as a directory' % df._data_file)

        df._threadpool.force_run_in_thread(self._finalize_put, metadata)

        # Avoid the unlink() system call as part of the mkstemp context
        # cleanup
        self.tmppath = None


class DiskFileReader(object):
    """
    Encapsulation of the WSGI read context for servicing GET REST API
    requests. Serves as the context manager object for the
    :class:`swift.obj.diskfile.DiskFile` class's
    :func:`swift.obj.diskfile.DiskFile.reader` method.

    .. note::

        The quarantining behavior of this method is considered implementation
        specific, and is not required of the API.

    .. note::

        The arguments to the constructor are considered implementation
        specific. The API does not define the constructor arguments.

    :param fp: open file descriptor, -1 for a directory object
    :param threadpool: thread pool to use for read operations
    :param disk_chunk_size: size of reads from disk in bytes
    :param obj_size: size of object on disk
    :param keep_cache_size: maximum object size that will be kept in cache
    :param iter_hook: called when __iter__ returns a chunk
    :param keep_cache: should resulting reads be kept in the buffer cache
    """
    def __init__(self, fd, threadpool, disk_chunk_size, obj_size,
                 keep_cache_size, iter_hook=None, keep_cache=False):
        # Parameter tracking
        self._fd = fd
        self._threadpool = threadpool
        self._disk_chunk_size = disk_chunk_size
        self._iter_hook = iter_hook
        if keep_cache:
            # Caller suggests we keep this in cache, only do it if the
            # object's size is less than the maximum.
            self._keep_cache = obj_size < keep_cache_size
        else:
            self._keep_cache = False

        # Internal Attributes
        self._suppress_file_closing = False

    def __iter__(self):
        """Returns an iterator over the data file."""
        try:
            dropped_cache = 0
            bytes_read = 0
            while True:
                if self._fd != -1:
                    chunk = self._threadpool.run_in_thread(
                        do_read, self._fd, self._disk_chunk_size)
                else:
                    chunk = None
                if chunk:
                    bytes_read += len(chunk)
                    diff = bytes_read - dropped_cache
                    if diff > (1024 * 1024):
                        self._drop_cache(dropped_cache, diff)
                        dropped_cache = bytes_read
                    yield chunk
                    if self._iter_hook:
                        self._iter_hook()
                else:
                    diff = bytes_read - dropped_cache
                    if diff > 0:
                        self._drop_cache(dropped_cache, diff)
                    break
        finally:
            if not self._suppress_file_closing:
                self.close()

    def app_iter_range(self, start, stop):
        """Returns an iterator over the data file for range (start, stop)"""
        if start or start == 0:
            do_lseek(self._fd, start, os.SEEK_SET)
        if stop is not None:
            length = stop - start
        else:
            length = None
        try:
            for chunk in self:
                if length is not None:
                    length -= len(chunk)
                    if length < 0:
                        # Chop off the extra:
                        yield chunk[:length]
                        break
                yield chunk
        finally:
            if not self._suppress_file_closing:
                self.close()

    def app_iter_ranges(self, ranges, content_type, boundary, size):
        """Returns an iterator over the data file for a set of ranges"""
        if not ranges:
            yield ''
        else:
            try:
                self._suppress_file_closing = True
                for chunk in multi_range_iterator(
                        ranges, content_type, boundary, size,
                        self.app_iter_range):
                    yield chunk
            finally:
                self._suppress_file_closing = False
                self.close()

    def _drop_cache(self, offset, length):
        """Method for no-oping buffer cache drop method."""
        if not self._keep_cache and self._fd > -1:
            do_fadvise64(self._fd, offset, length)

    def close(self):
        """
        Close the open file handle if present.
        """
        if self._fd is not None:
            fd, self._fd = self._fd, None
            if fd > -1:
                do_close(fd)


class DiskFile(object):
    """
    Manage object files on disk.

    Object names ending or beginning with a '/' as in /a, a/, /a/b/,
    etc, or object names with multiple consecutive slahes, like a//b,
    are not supported.  The proxy server's contraints filter
    gluster.common.constrains.gluster_check_object_creation() should
    reject such requests.

    :param mgr: associated on-disk manager instance
    :param dev_path: device name/account_name for UFO.
    :param threadpool: thread pool in which to do blocking operations
    :param account: account name for the object
    :param container: container name for the object
    :param obj: object name for the object
    :param uid: user ID disk object should assume (file or directory)
    :param gid: group ID disk object should assume (file or directory)
    """
    def __init__(self, mgr, dev_path, threadpool, account, container, obj,
                 uid=DEFAULT_UID, gid=DEFAULT_GID):
        self._mgr = mgr
        self._device_path = dev_path
        self._threadpool = threadpool or ThreadPool(nthreads=0)
        self._uid = int(uid)
        self._gid = int(gid)
        self._is_dir = False
        self._logger = mgr.logger
        self._metadata = None
        self._fd = None
        # Don't store a value for data_file until we know it exists.
        self._data_file = None

        self._container_path = os.path.join(self._device_path, container)
        obj = obj.strip(os.path.sep)
        obj_path, self._obj = os.path.split(obj)
        if obj_path:
            self._obj_path = obj_path.strip(os.path.sep)
            self._datadir = os.path.join(self._container_path, self._obj_path)
        else:
            self._obj_path = ''
            self._datadir = self._container_path

        if _use_put_mount:
            self._put_datadir = os.path.join(
                self._device_path + '_PUT', container, self._obj_path)
        else:
            self._put_datadir = self._datadir
        self._data_file = os.path.join(self._put_datadir, self._obj)

    def open(self):
        """
        Open the object.

        This implementation opens the data file representing the object, reads
        the associated metadata in the extended attributes, additionally
        combining metadata from fast-POST `.meta` files.

        .. note::

            An implementation is allowed to raise any of the following
            exceptions, but is only required to raise `DiskFileNotExist` when
            the object representation does not exist.

        :raises DiskFileNotExist: if the object does not exist
        :raises DiskFileExpired: if the object has expired
        :returns: itself for use as a context manager
        """
        # Writes are always performed to a temporary file
        try:
            fd = do_open(self._data_file, os.O_RDONLY | O_CLOEXEC)
        except GlusterFileSystemOSError as err:
            if err.errno in (errno.ENOENT, errno.ENOTDIR):
                # If the file does exist, or some part of the path does not
                # exist, raise the expected DiskFileNotExist
                raise DiskFileNotExist
            raise
        else:
            stats = do_fstat(fd)
            if not stats:
                return
            self._is_dir = stat.S_ISDIR(stats.st_mode)
            obj_size = stats.st_size

        self._metadata = read_metadata(fd)
        if not validate_object(self._metadata):
            create_object_metadata(fd)
            self._metadata = read_metadata(fd)
        assert self._metadata is not None
        self._filter_metadata()

        if self._is_dir:
            do_close(fd)
            obj_size = 0
            self._fd = -1
        else:
            if self._is_object_expired(self._metadata):
                raise DiskFileExpired(metadata=self._metadata)
            self._fd = fd

        self._obj_size = obj_size
        return self

    def _is_object_expired(self, metadata):
        try:
            x_delete_at = int(metadata['X-Delete-At'])
        except KeyError:
            pass
        except ValueError:
            # x-delete-at key is present but not an integer.
            # TODO: Openstack Swift "quarrantines" the object.
            # We just let it pass
            pass
        else:
            if x_delete_at <= time.time():
                return True
        return False

    def _filter_metadata(self):
        if X_TYPE in self._metadata:
            self._metadata.pop(X_TYPE)
        if X_OBJECT_TYPE in self._metadata:
            self._metadata.pop(X_OBJECT_TYPE)

    def __enter__(self):
        """
        Context enter.

        .. note::

            An implemenation shall raise `DiskFileNotOpen` when has not
            previously invoked the :func:`swift.obj.diskfile.DiskFile.open`
            method.
        """
        if self._metadata is None:
            raise DiskFileNotOpen()
        return self

    def __exit__(self, t, v, tb):
        """
        Context exit.

        .. note::

            This method will be invoked by the object server while servicing
            the REST API *before* the object has actually been read. It is the
            responsibility of the implementation to properly handle that.
        """
        self._metadata = None
        if self._fd is not None:
            fd, self._fd = self._fd, None
            if fd > -1:
                do_close(fd)

    def get_metadata(self):
        """
        Provide the metadata for a previously opened object as a dictionary.

        :returns: object's metadata dictionary
        :raises DiskFileNotOpen: if the
            :func:`swift.obj.diskfile.DiskFile.open` method was not previously
            invoked
        """
        if self._metadata is None:
            raise DiskFileNotOpen()
        return self._metadata

    def read_metadata(self):
        """
        Return the metadata for an object without requiring the caller to open
        the object first.

        :returns: metadata dictionary for an object
        :raises DiskFileError: this implementation will raise the same
                            errors as the `open()` method.
        """
        with self.open():
            return self.get_metadata()

    def reader(self, iter_hook=None, keep_cache=False):
        """
        Return a :class:`swift.common.swob.Response` class compatible
        "`app_iter`" object as defined by
        :class:`swift.obj.diskfile.DiskFileReader`.

        For this implementation, the responsibility of closing the open file
        is passed to the :class:`swift.obj.diskfile.DiskFileReader` object.

        :param iter_hook: called when __iter__ returns a chunk
        :param keep_cache: caller's preference for keeping data read in the
                           OS buffer cache
        :returns: a :class:`swift.obj.diskfile.DiskFileReader` object
        """
        if self._metadata is None:
            raise DiskFileNotOpen()
        dr = DiskFileReader(
            self._fd, self._threadpool, self._mgr.disk_chunk_size,
            self._obj_size, self._mgr.keep_cache_size,
            iter_hook=iter_hook, keep_cache=keep_cache)
        # At this point the reader object is now responsible for closing
        # the file pointer.
        self._fd = None
        return dr

    def _create_dir_object(self, dir_path, metadata=None):
        """
        Create a directory object at the specified path. No check is made to
        see if the directory object already exists, that is left to the caller
        (this avoids a potentially duplicate stat() system call).

        The "dir_path" must be relative to its container, self._container_path.

        The "metadata" object is an optional set of metadata to apply to the
        newly created directory object. If not present, no initial metadata is
        applied.

        The algorithm used is as follows:

          1. An attempt is made to create the directory, assuming the parent
             directory already exists

             * Directory creation races are detected, returning success in
               those cases

          2. If the directory creation fails because some part of the path to
             the directory does not exist, then a search back up the path is
             performed to find the first existing ancestor directory, and then
             the missing parents are successively created, finally creating
             the target directory
        """
        full_path = os.path.join(self._container_path, dir_path)
        cur_path = full_path
        stack = []
        while True:
            md = None if cur_path != full_path else metadata
            ret, newmd = make_directory(cur_path, self._uid, self._gid, md)
            if ret:
                break
            # Some path of the parent did not exist, so loop around and
            # create that, pushing this parent on the stack.
            if os.path.sep not in cur_path:
                raise DiskFileError("DiskFile._create_dir_object(): failed to"
                                    " create directory path while exhausting"
                                    " path elements to create: %s" % full_path)
            cur_path, child = cur_path.rsplit(os.path.sep, 1)
            assert child
            stack.append(child)

        child = stack.pop() if stack else None
        while child:
            cur_path = os.path.join(cur_path, child)
            md = None if cur_path != full_path else metadata
            ret, newmd = make_directory(cur_path, self._uid, self._gid, md)
            if not ret:
                raise DiskFileError("DiskFile._create_dir_object(): failed to"
                                    " create directory path to target, %s,"
                                    " on subpath: %s" % (full_path, cur_path))
            child = stack.pop() if stack else None
        return True, newmd
        # Exists, but as a file
        #raise DiskFileError('DiskFile.put(): directory creation failed'
        #                    ' since the target, %s, already exists as'
        #                    ' a file' % df._data_file)

    @contextmanager
    def create(self, size=None):
        """
        Context manager to create a file. We create a temporary file first, and
        then return a DiskFileWriter object to encapsulate the state.

        For Gluster, we first optimistically create the temporary file using
        the "rsync-friendly" .NAME.random naming. If we find that some path to
        the file does not exist, we then create that path and then create the
        temporary file again. If we get file name conflict, we'll retry using
        different random suffixes 1,000 times before giving up.

        .. note::

            An implementation is not required to perform on-disk
            preallocations even if the parameter is specified. But if it does
            and it fails, it must raise a `DiskFileNoSpace` exception.

        :param size: optional initial size of file to explicitly allocate on
                     disk
        :raises DiskFileNoSpace: if a size is specified and allocation fails
        :raises AlreadyExistsAsFile: if path or part of a path is not a \
                                     directory
        """
        data_file = os.path.join(self._put_datadir, self._obj)

        # Assume the full directory path exists to the file already, and
        # construct the proper name for the temporary file.
        attempts = 1
        cur_thread = str(getcurrent())
        while True:
            postfix = md5(self._obj + _cur_host + _cur_pid + cur_thread
                          + str(random.random())).hexdigest()
            tmpfile = '.' + self._obj + '.' + postfix
            tmppath = os.path.join(self._put_datadir, tmpfile)
            try:
                fd = do_open(tmppath,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_CLOEXEC)
            except GlusterFileSystemOSError as gerr:
                if gerr.errno in (errno.ENOSPC, errno.EDQUOT):
                    # Raise DiskFileNoSpace to be handled by upper layers when
                    # there is no space on disk OR when quota is exceeded
                    raise DiskFileNoSpace()
                if gerr.errno == errno.ENOTDIR:
                    raise AlreadyExistsAsFile('do_open(): failed on %s,'
                                              '  path or part of a'
                                              ' path is not a directory'
                                              % (tmppath))

                if gerr.errno not in (errno.ENOENT, errno.EEXIST, errno.EIO):
                    # FIXME: Other cases we should handle?
                    raise
                if attempts >= MAX_OPEN_ATTEMPTS:
                    # We failed after N attempts to create the temporary
                    # file.
                    raise DiskFileError('DiskFile.mkstemp(): failed to'
                                        ' successfully create a temporary file'
                                        ' without running into a name conflict'
                                        ' after %d of %d attempts for: %s' % (
                                            attempts, MAX_OPEN_ATTEMPTS,
                                            data_file))
                if gerr.errno == errno.EEXIST:
                    # Retry with a different random number.
                    attempts += 1
                elif gerr.errno == errno.EIO:
                    # FIXME: Possible FUSE issue or race condition, let's
                    # sleep on it and retry the operation.
                    _random_sleep()
                    logging.warn("DiskFile.mkstemp(): %s ... retrying in"
                                 " 0.1 secs", gerr)
                    attempts += 1
                elif not self._obj_path:
                    # No directory hierarchy and the create failed telling us
                    # the container or volume directory does not exist. This
                    # could be a FUSE issue or some race condition, so let's
                    # sleep a bit and retry.
                    _random_sleep()
                    logging.warn("DiskFile.mkstemp(): %s ... retrying in"
                                 " 0.1 secs", gerr)
                    attempts += 1
                elif attempts > 1:
                    # Got ENOENT after previously making the path. This could
                    # also be a FUSE issue or some race condition, nap and
                    # retry.
                    _random_sleep()
                    logging.warn("DiskFile.mkstemp(): %s ... retrying in"
                                 " 0.1 secs" % gerr)
                    attempts += 1
                else:
                    # It looks like the path to the object does not already
                    # exist; don't count this as an attempt, though, since
                    # we perform the open() system call optimistically.
                    self._create_dir_object(self._obj_path)
            else:
                break
        dw = None
        try:
            # Ensure it is properly owned before we make it available.
            do_fchown(fd, self._uid, self._gid)
            # NOTE: we do not perform the fallocate() call at all. We ignore
            # it completely since at the time of this writing FUSE does not
            # support it.
            dw = DiskFileWriter(fd, tmppath, self)
            yield dw
        finally:
            dw.close()
            if dw._tmppath:
                do_unlink(dw._tmppath)

    def write_metadata(self, metadata):
        """
        Write a block of metadata to an object without requiring the caller to
        open the object first.

        :param metadata: dictionary of metadata to be associated with the
                         object
        :raises DiskFileError: this implementation will raise the same
                            errors as the `create()` method.
        """
        metadata = self._keep_sys_metadata(metadata)
        data_file = os.path.join(self._put_datadir, self._obj)
        self._threadpool.run_in_thread(
            write_metadata, data_file, metadata)

    def _keep_sys_metadata(self, metadata):
        """
        Make sure system metadata is not lost when writing new user metadata

        This method will read the existing metadata and check for system
        metadata. If there are any, it should be appended to the metadata obj
        the user is trying to write.
        """
        orig_metadata = self.read_metadata()

        sys_keys = [X_CONTENT_TYPE, X_ETAG, 'name', X_CONTENT_LENGTH,
                    X_OBJECT_TYPE, X_TYPE]

        for key in sys_keys:
            if key in orig_metadata:
                metadata[key] = orig_metadata[key]

        if X_OBJECT_TYPE not in orig_metadata:
            if metadata[X_CONTENT_TYPE].lower() == DIR_TYPE:
                metadata[X_OBJECT_TYPE] = DIR_OBJECT
            else:
                metadata[X_OBJECT_TYPE] = FILE

        if X_TYPE not in orig_metadata:
            metadata[X_TYPE] = OBJECT

        return metadata

    def _unlinkold(self):
        if self._is_dir:
            # Marker, or object, directory.
            #
            # Delete from the filesystem only if it contains no objects.
            # If it does contain objects, then just remove the object
            # metadata tag which will make this directory a
            # fake-filesystem-only directory and will be deleted when the
            # container or parent directory is deleted.
            #
            # FIXME: Ideally we should use an atomic metadata update operation
            metadata = read_metadata(self._data_file)
            if dir_is_object(metadata):
                metadata[X_OBJECT_TYPE] = DIR_NON_OBJECT
                write_metadata(self._data_file, metadata)
            rmobjdir(self._data_file)
        else:
            # Delete file object
            do_unlink(self._data_file)

        # Garbage collection of non-object directories.  Now that we
        # deleted the file, determine if the current directory and any
        # parent directory may be deleted.
        dirname = os.path.dirname(self._data_file)
        while dirname and dirname != self._container_path:
            # Try to remove any directories that are not objects.
            if not rmobjdir(dirname):
                # If a directory with objects has been found, we can stop
                # garabe collection
                break
            else:
                dirname = os.path.dirname(dirname)

    def delete(self, timestamp):
        """
        Delete the object.

        This implementation creates a tombstone file using the given
        timestamp, and removes any older versions of the object file. Any
        file that has an older timestamp than timestamp will be deleted.

        .. note::

            An implementation is free to use or ignore the timestamp
            parameter.

        :param timestamp: timestamp to compare with each file
        :raises DiskFileError: this implementation will raise the same
                            errors as the `create()` method.
        """
        try:
            metadata = read_metadata(self._data_file)
        except (IOError, OSError) as err:
            if err.errno != errno.ENOENT:
                raise
        else:
            if metadata[X_TIMESTAMP] >= timestamp:
                return

        self._threadpool.run_in_thread(self._unlinkold)

        self._metadata = None
        self._data_file = None
