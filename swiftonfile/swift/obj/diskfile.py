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
from uuid import uuid4
from eventlet import sleep
from contextlib import contextmanager
from swiftonfile.swift.common.exceptions import AlreadyExistsAsFile, \
    AlreadyExistsAsDir, DiskFileContainerDoesNotExist
from swift.common.utils import tpool_reraise, hash_path, \
    normalize_timestamp, fallocate, Timestamp
from swift.common.exceptions import DiskFileNotExist, DiskFileError, \
    DiskFileNoSpace, DiskFileDeviceUnavailable, DiskFileNotOpen, \
    DiskFileExpired
from swift.common.swob import multi_range_iterator

from swiftonfile.swift.common.exceptions import SwiftOnFileSystemOSError
from swiftonfile.swift.common.fs_utils import do_fstat, do_open, do_close, \
    do_unlink, do_chown, do_fsync, do_fchown, do_stat, do_write, do_read, \
    do_fadvise64, do_rename, do_fdatasync, do_lseek, do_mkdir
from swiftonfile.swift.common.utils import read_metadata, write_metadata, \
    validate_object, create_object_metadata, rmobjdir, dir_is_object, \
    get_object_metadata, write_pickle
from swiftonfile.swift.common.utils import X_CONTENT_TYPE, \
    X_TIMESTAMP, X_TYPE, X_OBJECT_TYPE, FILE, OBJECT, DIR_TYPE, \
    FILE_TYPE, DEFAULT_UID, DEFAULT_GID, DIR_NON_OBJECT, DIR_OBJECT, \
    X_ETAG, X_CONTENT_LENGTH, X_MTIME
from swift.obj.diskfile import DiskFileManager as SwiftDiskFileManager
from swift.obj.diskfile import get_async_dir

# FIXME: Hopefully we'll be able to move to Python 2.7+ where O_CLOEXEC will
# be back ported. See http://www.python.org/dev/peps/pep-0433/
O_CLOEXEC = 0o2000000

MAX_RENAME_ATTEMPTS = 10
MAX_OPEN_ATTEMPTS = 10


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
            except SwiftOnFileSystemOSError as serr:
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
            except SwiftOnFileSystemOSError as serr:
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
        if not ((uid == DEFAULT_UID) and (gid == DEFAULT_GID)):
            # If both UID and GID is -1 (default values), it has no effect.
            # So don't do a chown.
            # Further, at the time of this writing, UID and GID information
            # is not passed to DiskFile.
            do_chown(full_path, uid, gid)
        return True, metadata


def _adjust_metadata(fd, metadata):
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

    # stat.st_mtime does not change after last write(). We set this to later
    # detect if the object was changed from filesystem interface (non Swift)
    statinfo = do_fstat(fd)
    if stat.S_ISREG(statinfo.st_mode):
        metadata[X_MTIME] = normalize_timestamp(statinfo.st_mtime)

    metadata[X_TYPE] = OBJECT
    return metadata


class DiskFileManager(SwiftDiskFileManager):
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
    def get_diskfile(self, device, partition, account, container, obj,
                     policy=None, **kwargs):
        dev_path = self.get_dev_path(device, self.mount_check)
        if not dev_path:
            raise DiskFileDeviceUnavailable()
        return DiskFile(self, dev_path,
                        partition, account, container, obj,
                        policy=policy, **kwargs)

    def pickle_async_update(self, device, account, container, obj, data,
                            timestamp, policy):
        # This method invokes swiftonfile's writepickle method.
        # Is patching just write_pickle and calling parent method better ?
        device_path = self.construct_dev_path(device)
        async_dir = os.path.join(device_path, get_async_dir(policy))
        ohash = hash_path(account, container, obj)
        write_pickle(
            data,
            os.path.join(async_dir, ohash[-3:], ohash + '-' +
                         normalize_timestamp(timestamp)),
            os.path.join(device_path, 'tmp'))
        self.logger.increment('async_pendings')


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
        self._write_entire_chunk(chunk)
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
                if err.errno in (errno.ENOENT, errno.EIO,
                                 errno.EBUSY, errno.ESTALE) \
                        and attempts < MAX_RENAME_ATTEMPTS:
                    # Some versions of GlusterFS had rename() as non-blocking
                    # operation. So we check for STALE and EBUSY. This was
                    # fixed recently: http://review.gluster.org/#/c/13366/
                    # The comment that follows is for ENOENT and EIO...
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
                    raise SwiftOnFileSystemOSError(
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
        metadata = _adjust_metadata(self._fd, metadata)
        df = self._disk_file

        if dir_is_object(metadata):
            tpool_reraise(
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

        tpool_reraise(self._finalize_put, metadata)

        # Avoid the unlink() system call as part of the create context
        # cleanup
        self._tmppath = None

    def commit(self, timestamp):
        """
        Perform any operations necessary to mark the object as durable. For
        replication policy type this is a no-op.

        :param timestamp: object put timestamp, an instance of
                          :class:`~swift.common.utils.Timestamp`
        """
        pass


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
    :param disk_chunk_size: size of reads from disk in bytes
    :param obj_size: size of object on disk
    :param keep_cache_size: maximum object size that will be kept in cache
    :param iter_hook: called when __iter__ returns a chunk
    :param keep_cache: should resulting reads be kept in the buffer cache
    """
    def __init__(self, fd, disk_chunk_size, obj_size,
                 keep_cache_size, iter_hook=None, keep_cache=False):
        # Parameter tracking
        self._fd = fd
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
                    chunk = do_read(self._fd, self._disk_chunk_size)
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
    etc, or object names with multiple consecutive slashes, like a//b,
    are not supported.  The proxy server's constraints filter
    swiftonfile.common.constrains.check_object_creation() should
    reject such requests.

    :param mgr: associated on-disk manager instance
    :param dev_path: device name/account_name for UFO.
    :param account: account name for the object
    :param container: container name for the object
    :param obj: object name for the object
    :param uid: user ID disk object should assume (file or directory)
    :param gid: group ID disk object should assume (file or directory)
    """
    def __init__(self, mgr, dev_path, partition,
                 account=None, container=None, obj=None,
                 policy=None, uid=DEFAULT_UID, gid=DEFAULT_GID, **kwargs):
        # Variables partition and policy is currently unused.
        self._mgr = mgr
        self._device_path = dev_path
        self._uid = int(uid)
        self._gid = int(gid)
        self._is_dir = False
        self._metadata = None
        self._fd = None
        # This fd attribute is not used in PUT path. fd used in PUT path
        # is encapsulated inside DiskFileWriter object.
        self._stat = None
        # Don't store a value for data_file until we know it exists.
        self._data_file = None

        # Account name contains resller_prefix which is retained and not
        # stripped. This to conform to Swift's behavior where account name
        # entry in Account DBs contain resller_prefix.
        self._account = account
        self._container = container

        self._container_path = \
            os.path.join(self._device_path, self._account, self._container)
        obj = obj.strip(os.path.sep)
        obj_path, self._obj = os.path.split(obj)
        if obj_path:
            self._obj_path = obj_path.strip(os.path.sep)
            self._put_datadir = os.path.join(self._container_path,
                                             self._obj_path)
        else:
            self._obj_path = ''
            self._put_datadir = self._container_path

        self._data_file = os.path.join(self._put_datadir, self._obj)
        self._disk_file_open = False

    @property
    def content_type(self):
        if self._metadata is None:
            raise DiskFileNotOpen()
        return self._metadata.get('Content-Type')

    @property
    def timestamp(self):
        if self._metadata is None:
            raise DiskFileNotOpen()
        return Timestamp(self._metadata.get('X-Timestamp'))

    data_timestamp = timestamp

    durable_timestamp = timestamp

    content_type_timestamp = timestamp

    fragments = None

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
            self._fd = do_open(self._data_file, os.O_RDONLY | O_CLOEXEC)
        except SwiftOnFileSystemOSError as err:
            if err.errno in (errno.ENOENT, errno.ENOTDIR):
                # If the file does exist, or some part of the path does not
                # exist, raise the expected DiskFileNotExist
                raise DiskFileNotExist
            raise
        try:
            if not self._stat:
                self._stat = do_fstat(self._fd)
            self._is_dir = stat.S_ISDIR(self._stat.st_mode)
            obj_size = self._stat.st_size

            if not self._metadata:
                self._metadata = read_metadata(self._fd)
            if not validate_object(self._metadata, self._stat):
                self._metadata = create_object_metadata(self._fd, self._stat,
                                                        self._metadata)
            assert self._metadata is not None
            self._filter_metadata()

            if self._is_dir:
                do_close(self._fd)
                obj_size = 0
                self._fd = -1
            else:
                if self._is_object_expired(self._metadata):
                    raise DiskFileExpired(metadata=self._metadata)
            self._obj_size = obj_size
        except (OSError, IOError, DiskFileExpired) as err:
            # Something went wrong. Context manager will not call
            # __exit__. So we close the fd manually here.
            self._close_fd()
            if hasattr(err, 'errno') and err.errno == errno.ENOENT:
                # Handle races: ENOENT can be raised by read_metadata()
                # call in GlusterFS if file gets deleted by another
                # client after do_open() succeeds
                logging.warn("open(%s) succeeded but one of the subsequent "
                             "syscalls failed with ENOENT. Raising "
                             "DiskFileNotExist." % (self._data_file))
                raise DiskFileNotExist
            else:
                # Re-raise the original exception after fd has been closed
                raise

        self._disk_file_open = True
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
        if not self._disk_file_open:
            raise DiskFileNotOpen()
        return self

    def _close_fd(self):
        if self._fd is not None:
            fd, self._fd = self._fd, None
            if fd > -1:
                do_close(fd)

    def __exit__(self, t, v, tb):
        """
        Context exit.

        .. note::

            This method will be invoked by the object server while servicing
            the REST API *before* the object has actually been read. It is the
            responsibility of the implementation to properly handle that.
        """
        self._disk_file_open = False
        self._close_fd()

    def get_metadata(self):
        """
        Provide the metadata for a previously opened object as a dictionary.

        This is invoked by Swift code in the GET path as follows:
        with disk_file.open():
            metadata = disk_file.get_metadata()

        :returns: object's metadata dictionary
        :raises DiskFileNotOpen: if the
            :func:`swift.obj.diskfile.DiskFile.open` method was not previously
            invoked
        """
        if not self._disk_file_open:
            raise DiskFileNotOpen()
        return self._metadata

    def get_datafile_metadata(self):
        if self._metadata is None:
            raise DiskFileNotOpen()
        return self._metadata

    def read_metadata(self):
        """
        Return the metadata for an object without requiring the caller to open
        the object first.

        This method is invoked by Swift code in POST, PUT, HEAD and DELETE path
        metadata = disk_file.read_metadata()

        The operations performed here is very similar to those made in open().
        This is to avoid opening and closing of file (two syscalls over
        network). IOW, this optimization addresses the case where the fd
        returned by open() isn't going to be used i.e the file is not read (GET
        or metadata recalculation)

        :returns: metadata dictionary for an object
        :raises DiskFileError: this implementation will raise the same
                            errors as the `open()` method.
        """
        try:
            self._metadata = read_metadata(self._data_file)
        except (OSError, IOError) as err:
            if err.errno in (errno.ENOENT, errno.ESTALE):
                raise DiskFileNotExist
            raise err

        if self._metadata and self._is_object_expired(self._metadata):
            raise DiskFileExpired(metadata=self._metadata)

        try:
            self._stat = do_stat(self._data_file)
            self._is_dir = stat.S_ISDIR(self._stat.st_mode)
        except (OSError, IOError) as err:
            if err.errno in (errno.ENOENT, errno.ESTALE):
                raise DiskFileNotExist
            raise err

        if not validate_object(self._metadata, self._stat):
            # Metadata is stale/invalid. So open the object for reading
            # to update Etag and other metadata.
            with self.open():
                return self.get_metadata()
        else:
            # Metadata is valid. Don't have to open the file.
            self._filter_metadata()
            return self._metadata

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
        if not self._disk_file_open:
            raise DiskFileNotOpen()
        dr = DiskFileReader(
            self._fd, self._mgr.disk_chunk_size,
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
        # Create /account/container directory structure on mount point root
        try:
            os.makedirs(self._container_path)
        except OSError as err:
            if err.errno != errno.EEXIST:
                raise

        data_file = os.path.join(self._put_datadir, self._obj)

        # Assume the full directory path exists to the file already, and
        # construct the proper name for the temporary file.
        fd = None
        attempts = 1
        while True:
            # To know more about why following temp file naming convention is
            # used, please read this GlusterFS doc:
            # https://github.com/gluster/glusterfs/blob/master/doc/features/dht.md#rename-optimizations  # noqa
            tmpfile = '.' + self._obj + '.' + uuid4().hex
            tmppath = os.path.join(self._put_datadir, tmpfile)
            try:
                fd = do_open(tmppath,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_CLOEXEC)
            except SwiftOnFileSystemOSError as gerr:
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
                    raise DiskFileError('DiskFile.create(): failed to'
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
                    logging.warn("DiskFile.create(): %s ... retrying in"
                                 " 0.1 secs", gerr)
                    attempts += 1
                elif not self._obj_path:
                    # ENOENT
                    # No directory hierarchy and the create failed telling us
                    # the container or volume directory does not exist. This
                    # could be a FUSE issue or some race condition, so let's
                    # sleep a bit and retry.
                    # Handle race:
                    # This can be the issue when memcache has cached that the
                    # container exists. If someone removes the container dir
                    # from filesystem, it's not reflected in memcache. So
                    # swift reports that the container exists and this code
                    # tries to create a file in a directory that does not
                    # exist. However, it's wrong to create the container here.
                    _random_sleep()
                    logging.warn("DiskFile.create(): %s ... retrying in"
                                 " 0.1 secs", gerr)
                    attempts += 1
                    if attempts > 2:
                        # Ideally we would want to return 404 indicating that
                        # the container itself does not exist. Can't be done
                        # though as the caller won't catch DiskFileNotExist.
                        # We raise an exception with a meaningful name for
                        # correctness.
                        logging.warn("Container dir %s does not exist",
                                     self._container_path)
                        raise DiskFileContainerDoesNotExist
                elif attempts > 1:
                    # Got ENOENT after previously making the path. This could
                    # also be a FUSE issue or some race condition, nap and
                    # retry.
                    _random_sleep()
                    logging.warn("DiskFile.create(): %s ... retrying in"
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
            if size is not None and size > 0:
                try:
                    fallocate(fd, size)
                except OSError as err:
                    if err.errno in (errno.ENOSPC, errno.EDQUOT):
                        raise DiskFileNoSpace()
                    raise
            # Ensure it is properly owned before we make it available.
            if not ((self._uid == DEFAULT_UID) and (self._gid == DEFAULT_GID)):
                # If both UID and GID is -1 (default values), it has no effect.
                # So don't do a fchown.
                # Further, at the time of this writing, UID and GID information
                # is not passed to DiskFile.
                do_fchown(fd, self._uid, self._gid)
            dw = DiskFileWriter(fd, tmppath, self)
            # It's now the responsibility of DiskFileWriter to close this fd.
            fd = None
            yield dw
        finally:
            if dw:
                dw.close()
                if dw._tmppath:
                    do_unlink(dw._tmppath)

    def write_metadata(self, metadata):
        """
        Write a block of metadata to an object without requiring the caller to
        open the object first.

        This method is only called in the POST path.

        :param metadata: dictionary of metadata to be associated with the
                         object
        :raises DiskFileError: this implementation will raise the same
                            errors as the `create()` method.
        """
        metadata = self._keep_sys_metadata(metadata)
        data_file = os.path.join(self._put_datadir, self._obj)
        write_metadata(data_file, metadata)

    def _keep_sys_metadata(self, metadata):
        """
        Make sure system metadata is not lost when writing new user metadata

        This method will read the existing metadata and check for system
        metadata. If there are any, it should be appended to the metadata obj
        the user is trying to write.
        """
        # If metadata has been previously fetched, use that.
        # Stale metadata (outdated size/etag) would've been updated when
        # metadata is fetched for the first time.
        orig_metadata = self._metadata or read_metadata(self._data_file)

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
            metadata = self._metadata or read_metadata(self._data_file)
        except (IOError, OSError) as err:
            if err.errno not in (errno.ESTALE, errno.ENOENT):
                raise
        else:
            if metadata and metadata[X_TIMESTAMP] >= timestamp:
                return

        self._unlinkold()

        self._metadata = None
        self._data_file = None
