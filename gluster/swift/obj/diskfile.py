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
import fcntl
import errno
import random
import logging
from hashlib import md5
from eventlet import sleep
from contextlib import contextmanager
from swift.common.utils import TRUE_VALUES, drop_buffer_cache, ThreadPool
from swift.common.exceptions import DiskFileNotExist, DiskFileError, \
    DiskFileNoSpace, DiskFileDeviceUnavailable

from gluster.swift.common.exceptions import GlusterFileSystemOSError
from gluster.swift.common.Glusterfs import mount
from gluster.swift.common.fs_utils import do_fstat, do_open, do_close, \
    do_unlink, do_chown, os_path, do_fsync, do_fchown, do_stat
from gluster.swift.common.utils import read_metadata, write_metadata, \
    validate_object, create_object_metadata, rmobjdir, dir_is_object, \
    get_object_metadata
from gluster.swift.common.utils import X_CONTENT_LENGTH, X_CONTENT_TYPE, \
    X_TIMESTAMP, X_TYPE, X_OBJECT_TYPE, FILE, OBJECT, DIR_TYPE, \
    FILE_TYPE, DEFAULT_UID, DEFAULT_GID, DIR_NON_OBJECT, DIR_OBJECT
from ConfigParser import ConfigParser, NoSectionError, NoOptionError

from swift.obj.diskfile import DiskFile as SwiftDiskFile
from swift.obj.diskfile import DiskWriter as SwiftDiskWriter

# FIXME: Hopefully we'll be able to move to Python 2.7+ where O_CLOEXEC will
# be back ported. See http://www.python.org/dev/peps/pep-0433/
O_CLOEXEC = 02000000

DEFAULT_DISK_CHUNK_SIZE = 65536
DEFAULT_BYTES_PER_SYNC = (512 * 1024 * 1024)
# keep these lower-case
DISALLOWED_HEADERS = set('content-length content-type deleted etag'.split())


def _random_sleep():
    sleep(random.uniform(0.5, 0.15))


def _lock_parent(full_path):
    parent_path, _ = full_path.rsplit(os.path.sep, 1)
    try:
        fd = os.open(parent_path, os.O_RDONLY | O_CLOEXEC)
    except OSError as err:
        if err.errno == errno.ENOENT:
            # Cannot lock the parent because it does not exist, let the caller
            # handle this situation.
            return False
        raise
    else:
        while True:
            # Spin sleeping for 1/10th of a second until we get the lock.
            # FIXME: Consider adding a final timeout just abort the operation.
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except IOError as err:
                if err.errno == errno.EAGAIN:
                    _random_sleep()
                else:
                    # Don't leak an open file on an exception
                    os.close(fd)
                    raise
            except Exception:
                # Don't leak an open file for any other exception
                os.close(fd)
                raise
            else:
                break
        return fd


def _make_directory_locked(full_path, uid, gid, metadata=None):
    fd = _lock_parent(full_path)
    if fd is False:
        # Parent does not exist either, pass this situation on to the caller
        # to handle.
        return False, metadata
    try:
        # Check for directory existence
        stats = do_stat(full_path)
        if stats:
            # It now exists, having acquired the lock of its parent directory,
            # but verify it is actually a directory
            is_dir = stat.S_ISDIR(stats.st_mode)
            if not is_dir:
                # It is not a directory!
                raise DiskFileError("_make_directory_locked: non-directory"
                                    " found at path %s when expecting a"
                                    " directory", full_path)
            return True, metadata

        # We know the parent directory exists, and we have it locked, attempt
        # the creation of the target directory.
        return _make_directory_unlocked(full_path, uid, gid, metadata=metadata)
    finally:
        # We're done here, be sure to remove our lock and close our open FD.
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except:
            pass
        os.close(fd)


def _make_directory_unlocked(full_path, uid, gid, metadata=None):
    """
    Make a directory and change the owner ship as specified, and potentially
    creating the object metadata if requested.
    """
    try:
        os.mkdir(full_path)
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
                stats = os.stat(full_path)
            except OSError as serr:
                # FIXME: Ideally we'd want to return an appropriate error
                # message and code in the PUT Object REST API response.
                raise DiskFileError("_make_directory_unlocked: os.mkdir failed"
                                    " because path %s already exists, and"
                                    " a subsequent os.stat on that same"
                                    " path failed (%s)" % (full_path,
                                                           str(serr)))
            else:
                is_dir = stat.S_ISDIR(stats.st_mode)
                if not is_dir:
                    # FIXME: Ideally we'd want to return an appropriate error
                    # message and code in the PUT Object REST API response.
                    raise DiskFileError("_make_directory_unlocked: os.mkdir"
                                        " failed on path %s because it already"
                                        " exists but not as a directory" % (
                                            full_path))
            return True, metadata
        elif err.errno == errno.ENOTDIR:
            # FIXME: Ideally we'd want to return an appropriate error
            # message and code in the PUT Object REST API response.
            raise DiskFileError("_make_directory_unlocked: os.mkdir failed"
                                " because some part of path %s is not in fact"
                                " a directory" % (full_path))
        elif err.errno == errno.EIO:
            # Sometimes Fuse will return an EIO error when it does not know
            # how to handle an unexpected, but transient situation. It is
            # possible the directory now exists, stat() it to find out after a
            # short period of time.
            _random_sleep()
            try:
                stats = os.stat(full_path)
            except OSError as serr:
                if serr.errno == errno.ENOENT:
                    errmsg = "_make_directory_unlocked: os.mkdir failed on" \
                             " path %s (EIO), and a subsequent os.stat on" \
                             " that same path did not find the file." % (
                                 full_path,)
                else:
                    errmsg = "_make_directory_unlocked: os.mkdir failed on" \
                             " path %s (%s), and a subsequent os.stat on" \
                             " that same path failed as well (%s)" % (
                                 full_path, str(err), str(serr))
                raise DiskFileError(errmsg)
            else:
                # The directory at least exists now
                is_dir = stat.S_ISDIR(stats.st_mode)
                if is_dir:
                    # Dump the stats to the log with the original exception.
                    logging.warn("_make_directory_unlocked: os.mkdir initially"
                                 " failed on path %s (%s) but a stat()"
                                 " following that succeeded: %r" % (full_path,
                                                                    str(err),
                                                                    stats))
                    # Assume another entity took care of the proper setup.
                    return True, metadata
                else:
                    raise DiskFileError("_make_directory_unlocked: os.mkdir"
                                        " initially failed on path %s (%s) but"
                                        " now we see that it exists but is not"
                                        " a directory (%r)" % (full_path,
                                                               str(err),
                                                               stats))
        else:
            # Some other potentially rare exception occurred that does not
            # currently warrant a special log entry to help diagnose.
            raise DiskFileError("_make_directory_unlocked: os.mkdir failed on"
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
    except (NoSectionError, NoOptionError):
        _mkdir_locking = False
    try:
        _use_put_mount = _fs_conf.get('DEFAULT', 'use_put_mount', "no") \
            in TRUE_VALUES
    except (NoSectionError, NoOptionError):
        _use_put_mount = False
    try:
        _relaxed_writes = _fs_conf.get('DEFAULT', 'relaxed_writes', "no") \
            in TRUE_VALUES
    except (NoSectionError, NoOptionError):
        _relaxed_writes = False
else:
    _mkdir_locking = False
    _use_put_mount = False
    _relaxed_writes = False

if _mkdir_locking:
    make_directory = _make_directory_locked
else:
    make_directory = _make_directory_unlocked


def _adjust_metadata(metadata):
    # Fix up the metadata to ensure it has a proper value for the
    # Content-Type metadata, as well as an X_TYPE and X_OBJECT_TYPE
    # metadata values.
    content_type = metadata[X_CONTENT_TYPE]
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


class DiskWriter(SwiftDiskWriter):
    """
    Encapsulation of the write context for servicing PUT REST API
    requests. Serves as the context manager object for DiskFile's writer()
    method.

    We just override the put() method for Gluster.
    """
    def put(self, metadata, extension='.data'):
        """
        Finalize writing the file on disk, and renames it from the temp file
        to the real location.  This should be called after the data has been
        written to the temp file.

        :param metadata: dictionary of metadata to be written
        :param extension: extension to be used when making the file
        """
        # Our caller will use '.data' here; we just ignore it since we map the
        # URL directly to the file system.

        assert self.tmppath is not None
        metadata = _adjust_metadata(metadata)
        df = self.disk_file

        if dir_is_object(metadata):
            if not df.data_file:
                # Does not exist, create it
                data_file = os.path.join(df._obj_path, df._obj)
                _, df.metadata = self.threadpool.force_run_in_thread(
                    df._create_dir_object, data_file, metadata)
                df.data_file = os.path.join(df._container_path, data_file)
            elif not df.is_dir:
                # Exists, but as a file
                raise DiskFileError('DiskFile.put(): directory creation failed'
                                    ' since the target, %s, already exists as'
                                    ' a file' % df.data_file)
            return

        if df._is_dir:
            # A pre-existing directory already exists on the file
            # system, perhaps gratuitously created when another
            # object was created, or created externally to Swift
            # REST API servicing (UFO use case).
            raise DiskFileError('DiskFile.put(): file creation failed since'
                                ' the target, %s, already exists as a'
                                ' directory' % df.data_file)

        def finalize_put():
            # Write out metadata before fsync() to ensure it is also forced to
            # disk.
            write_metadata(self.fd, metadata)

            if not _relaxed_writes:
                # We call fsync() before calling drop_cache() to lower the
                # amount of redundant work the drop cache code will perform on
                # the pages (now that after fsync the pages will be all
                # clean).
                do_fsync(self.fd)
                # From the Department of the Redundancy Department, make sure
                # we call drop_cache() after fsync() to avoid redundant work
                # (pages all clean).
                drop_buffer_cache(self.fd, 0, self.upload_size)

            # At this point we know that the object's full directory path
            # exists, so we can just rename it directly without using Swift's
            # swift.common.utils.renamer(), which makes the directory path and
            # adds extra stat() calls.
            data_file = os.path.join(df.put_datadir, df._obj)
            while True:
                try:
                    os.rename(self.tmppath, data_file)
                except OSError as err:
                    if err.errno in (errno.ENOENT, errno.EIO):
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
                        assert len(self.tmppath) > 0 and len(data_file) > 0
                        tpstats = do_stat(self.tmppath)
                        tfstats = do_fstat(self.fd)
                        assert tfstats
                        if not tpstats or tfstats.st_ino != tpstats.st_ino:
                            # Temporary file name conflict
                            raise DiskFileError(
                                'DiskFile.put(): temporary file, %s, was'
                                ' already renamed (targeted for %s)' % (
                                    self.tmppath, data_file))
                        else:
                            # Data file target name now has a bad path!
                            dfstats = do_stat(self.put_datadir)
                            if not dfstats:
                                raise DiskFileError(
                                    'DiskFile.put(): path to object, %s, no'
                                    ' longer exists (targeted for %s)' % (
                                        df.put_datadir,
                                        data_file))
                            else:
                                is_dir = stat.S_ISDIR(dfstats.st_mode)
                                if not is_dir:
                                    raise DiskFileError(
                                        'DiskFile.put(): path to object, %s,'
                                        ' no longer a directory (targeted for'
                                        ' %s)' % (df.put_datadir,
                                                  data_file))
                                else:
                                    # Let's retry since everything looks okay
                                    logging.warn(
                                        "DiskFile.put(): os.rename('%s','%s')"
                                        " initially failed (%s) but a"
                                        " stat('%s') following that succeeded:"
                                        " %r" % (
                                            self.tmppath, data_file,
                                            str(err), df.put_datadir,
                                            dfstats))
                                    continue
                    else:
                        raise GlusterFileSystemOSError(
                            err.errno, "%s, os.rename('%s', '%s')" % (
                                err.strerror, self.tmppath, data_file))
                else:
                    # Success!
                    break
            # Close here so the calling context does not have to perform this
            # in a thread.
            do_close(self.fd)

        self.threadpool.force_run_in_thread(finalize_put)

        # Avoid the unlink() system call as part of the mkstemp context
        # cleanup
        self.tmppath = None

        df.metadata = metadata
        df._filter_metadata()

        # Mark that it actually exists now
        df.data_file = os.path.join(df.datadir, df._obj)


class DiskFile(SwiftDiskFile):
    """
    Manage object files on disk.

    Object names ending or beginning with a '/' as in /a, a/, /a/b/,
    etc, or object names with multiple consecutive slahes, like a//b,
    are not supported.  The proxy server's contraints filter
    gluster.common.constrains.gluster_check_object_creation() should
    reject such requests.

    :param path: path to devices on the node/mount path for UFO.
    :param device: device name/account_name for UFO.
    :param partition: partition on the device the object lives in
    :param account: account name for the object
    :param container: container name for the object
    :param obj: object name for the object
    :param logger: logger object for writing out log file messages
    :param keep_data_fp: if True, don't close the fp, otherwise close it
    :param disk_chunk_Size: size of chunks on file reads
    :param bytes_per_sync: number of bytes between fdatasync calls
    :param iter_hook: called when __iter__ returns a chunk
    :param threadpool: thread pool in which to do blocking operations
    :param obj_dir: ignored
    :param mount_check: check the target device is a mount point and not on the
                        root volume
    :param uid: user ID disk object should assume (file or directory)
    :param gid: group ID disk object should assume (file or directory)
    """

    def __init__(self, path, device, partition, account, container, obj,
                 logger, keep_data_fp=False,
                 disk_chunk_size=DEFAULT_DISK_CHUNK_SIZE,
                 bytes_per_sync=DEFAULT_BYTES_PER_SYNC, iter_hook=None,
                 threadpool=None, obj_dir='objects', mount_check=False,
                 disallowed_metadata_keys=None, uid=DEFAULT_UID,
                 gid=DEFAULT_GID):
        if mount_check and not mount(path, device):
            raise DiskFileDeviceUnavailable()
        self.disk_chunk_size = disk_chunk_size
        self.bytes_per_sync = bytes_per_sync
        self.iter_hook = iter_hook
        self.threadpool = threadpool or ThreadPool(nthreads=0)
        obj = obj.strip(os.path.sep)

        if os.path.sep in obj:
            self._obj_path, self._obj = os.path.split(obj)
        else:
            self._obj_path = ''
            self._obj = obj

        if self._obj_path:
            self.name = os.path.join(container, self._obj_path)
        else:
            self.name = container
        # Absolute path for object directory.
        self.datadir = os.path.join(path, device, self.name)
        self.device_path = os.path.join(path, device)
        self._container_path = os.path.join(path, device, container)
        if _use_put_mount:
            self.put_datadir = os.path.join(self.device_path + '_PUT',
                                            self.name)
        else:
            self.put_datadir = self.datadir
        self._is_dir = False
        self.logger = logger
        self.metadata = {}
        self.meta_file = None
        self.fp = None
        self.iter_etag = None
        self.started_at_0 = False
        self.read_to_eof = False
        self.quarantined_dir = None
        self.keep_cache = False
        self.uid = int(uid)
        self.gid = int(gid)
        self.suppress_file_closing = False

        # Don't store a value for data_file until we know it exists.
        self.data_file = None
        data_file = os.path.join(self.put_datadir, self._obj)

        try:
            stats = do_stat(data_file)
        except OSError as err:
            if err.errno == errno.ENOTDIR:
                return
        else:
            if not stats:
                return

        self.data_file = data_file
        self._is_dir = stat.S_ISDIR(stats.st_mode)

        self.metadata = read_metadata(data_file)
        if not self.metadata:
            create_object_metadata(data_file)
            self.metadata = read_metadata(data_file)

        if not validate_object(self.metadata):
            create_object_metadata(data_file)
            self.metadata = read_metadata(data_file)

        self._filter_metadata()

        if not self._is_dir and keep_data_fp:
            # The caller has an assumption that the "fp" field of this
            # object is an file object if keep_data_fp is set. However,
            # this implementation of the DiskFile object does not need to
            # open the file for internal operations. So if the caller
            # requests it, we'll just open the file for them.
            self.fp = do_open(data_file, 'rb')

    def close(self, verify_file=True):
        """
        Close the file. Will handle quarantining file if necessary.

        :param verify_file: Defaults to True. If false, will not check
                            file to see if it needs quarantining.
        """
        # Marker directory
        if self._is_dir:
            assert not self.fp
            return
        if self.fp:
            do_close(self.fp)
            self.fp = None

    def _filter_metadata(self):
        if X_TYPE in self.metadata:
            self.metadata.pop(X_TYPE)
        if X_OBJECT_TYPE in self.metadata:
            self.metadata.pop(X_OBJECT_TYPE)

    def _create_dir_object(self, dir_path, metadata=None):
        """
        Create a directory object at the specified path. No check is made to
        see if the directory object already exists, that is left to the caller
        (this avoids a potentially duplicate stat() system call).

        The "dir_path" must be relative to its container,
        self._container_path.

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
            ret, newmd = make_directory(cur_path, self.uid, self.gid, md)
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
            ret, newmd = make_directory(cur_path, self.uid, self.gid, md)
            if not ret:
                raise DiskFileError("DiskFile._create_dir_object(): failed to"
                                    " create directory path to target, %s,"
                                    " on subpath: %s" % (full_path, cur_path))
            child = stack.pop() if stack else None
        return True, newmd

    @contextmanager
    def writer(self, size=None):
        """
        Contextmanager to make a temporary file, optionally of a specified
        initial size.

        For Gluster, we first optimistically create the temporary file using
        the "rsync-friendly" .NAME.random naming. If we find that some path to
        the file does not exist, we then create that path and then create the
        temporary file again. If we get file name conflict, we'll retry using
        different random suffixes 1,000 times before giving up.
        """
        data_file = os.path.join(self.put_datadir, self._obj)

        # Assume the full directory path exists to the file already, and
        # construct the proper name for the temporary file.
        for i in range(0, 1000):
            tmpfile = '.' + self._obj + '.' + md5(self._obj +
                      str(random.random())).hexdigest()
            tmppath = os.path.join(self.put_datadir, tmpfile)
            try:
                fd = do_open(tmppath,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_CLOEXEC)
            except GlusterFileSystemOSError as gerr:
                if gerr.errno == errno.ENOSPC:
                    # Raise DiskFileNoSpace to be handled by upper layers
                    raise DiskFileNoSpace()
                if gerr.errno == errno.EEXIST:
                    # Retry with a different random number.
                    continue
                if gerr.errno == errno.EIO:
                    # FIXME: Possible FUSE issue or race condition, let's
                    # sleep on it and retry the operation.
                    _random_sleep()
                    logging.warn("DiskFile.mkstemp(): %s ... retrying in"
                                 " 0.1 secs", gerr)
                    continue
                if gerr.errno != errno.ENOENT:
                    # FIXME: Other cases we should handle?
                    raise
                if not self._obj_path:
                    # No directory hierarchy and the create failed telling us
                    # the container or volume directory does not exist. This
                    # could be a FUSE issue or some race condition, so let's
                    # sleep a bit and retry.
                    _random_sleep()
                    logging.warn("DiskFile.mkstemp(): %s ... retrying in"
                                 " 0.1 secs", gerr)
                    continue
                if i != 0:
                    # Got ENOENT after previously making the path. This could
                    # also be a FUSE issue or some race condition, nap and
                    # retry.
                    _random_sleep()
                    logging.warn("DiskFile.mkstemp(): %s ... retrying in"
                                 " 0.1 secs" % gerr)
                    continue
                # It looks like the path to the object does not already exist
                self._create_dir_object(self._obj_path)
                continue
            else:
                break
        else:
            # We failed after 1,000 attempts to create the temporary file.
            raise DiskFileError('DiskFile.mkstemp(): failed to successfully'
                                ' create a temporary file without running'
                                ' into a name conflict after 1,000 attempts'
                                ' for: %s' % (data_file,))
        dw = None
        try:
            # Ensure it is properly owned before we make it available.
            do_fchown(fd, self.uid, self.gid)
            # NOTE: we do not perform the fallocate() call at all. We ignore
            # it completely.
            dw = DiskWriter(self, fd, tmppath, self.threadpool)
            yield dw
        finally:
            try:
                if dw.fd:
                    do_close(dw.fd)
            except OSError:
                pass
            if dw.tmppath:
                do_unlink(dw.tmppath)

    def put_metadata(self, metadata, tombstone=False):
        """
        Short hand for putting metadata to .meta and .ts files.

        :param metadata: dictionary of metadata to be written
        :param tombstone: whether or not we are writing a tombstone
        """
        if tombstone:
            # We don't write tombstone files. So do nothing.
            return
        assert self.data_file is not None, \
            "put_metadata: no file to put metadata into"
        metadata = _adjust_metadata(metadata)
        self.threadpool.run_in_thread(write_metadata, self.data_file, metadata)
        self.metadata = metadata
        self._filter_metadata()

    def unlinkold(self, timestamp):
        """
        Remove any older versions of the object file.  Any file that has an
        older timestamp than timestamp will be deleted.

        :param timestamp: timestamp to compare with each file
        """
        if not self.metadata or self.metadata[X_TIMESTAMP] >= timestamp:
            return

        assert self.data_file, \
            "Have metadata, %r, but no data_file" % self.metadata

        def _unlinkold():
            if self._is_dir:
                # Marker, or object, directory.
                #
                # Delete from the filesystem only if it contains no objects.
                # If it does contain objects, then just remove the object
                # metadata tag which will make this directory a
                # fake-filesystem-only directory and will be deleted when the
                # container or parent directory is deleted.
                metadata = read_metadata(self.data_file)
                if dir_is_object(metadata):
                    metadata[X_OBJECT_TYPE] = DIR_NON_OBJECT
                    write_metadata(self.data_file, metadata)
                rmobjdir(self.data_file)
            else:
                # Delete file object
                do_unlink(self.data_file)

            # Garbage collection of non-object directories.  Now that we
            # deleted the file, determine if the current directory and any
            # parent directory may be deleted.
            dirname = os.path.dirname(self.data_file)
            while dirname and dirname != self._container_path:
                # Try to remove any directories that are not objects.
                if not rmobjdir(dirname):
                    # If a directory with objects has been found, we can stop
                    # garabe collection
                    break
                else:
                    dirname = os.path.dirname(dirname)

        self.threadpool.run_in_thread(_unlinkold)

        self.metadata = {}
        self.data_file = None

    def get_data_file_size(self):
        """
        Returns the os_path.getsize for the file.  Raises an exception if this
        file does not match the Content-Length stored in the metadata, or if
        self.data_file does not exist.

        :returns: file size as an int
        :raises DiskFileError: on file size mismatch.
        :raises DiskFileNotExist: on file not existing (including deleted)
        """
        #Marker directory.
        if self._is_dir:
            return 0
        try:
            file_size = 0
            if self.data_file:
                def _old_getsize():
                    file_size = os_path.getsize(self.data_file)
                    if X_CONTENT_LENGTH in self.metadata:
                        metadata_size = int(self.metadata[X_CONTENT_LENGTH])
                        if file_size != metadata_size:
                            # FIXME - bit rot detection?
                            self.metadata[X_CONTENT_LENGTH] = file_size
                            write_metadata(self.data_file, self.metadata)
                    return file_size
                file_size = self.threadpool.run_in_thread(_old_getsize)
                return file_size
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise
        raise DiskFileNotExist('Data File does not exist.')
