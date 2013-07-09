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
import stat
import errno
import random
from hashlib import md5
from contextlib import contextmanager
from swift.common.utils import renamer
from swift.common.exceptions import DiskFileNotExist, DiskFileError
from gluster.swift.common.exceptions import AlreadyExistsAsDir
from gluster.swift.common.fs_utils import mkdirs, do_open, do_close, \
    do_unlink, do_chown, os_path, do_fsync, do_fchown, do_stat
from gluster.swift.common.utils import read_metadata, write_metadata, \
    validate_object, create_object_metadata, rmobjdir, dir_is_object
from gluster.swift.common.utils import X_CONTENT_LENGTH, X_CONTENT_TYPE, \
    X_TIMESTAMP, X_TYPE, X_OBJECT_TYPE, FILE, OBJECT, DIR_TYPE, \
    FILE_TYPE, DEFAULT_UID, DEFAULT_GID, DIR_NON_OBJECT, DIR_OBJECT

from swift.obj.server import DiskFile


DEFAULT_DISK_CHUNK_SIZE = 65536
# keep these lower-case
DISALLOWED_HEADERS = set('content-length content-type deleted etag'.split())


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


class Gluster_DiskFile(DiskFile):
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
    :param uid: user ID disk object should assume (file or directory)
    :param gid: group ID disk object should assume (file or directory)
    """

    def __init__(self, path, device, partition, account, container, obj,
                 logger, keep_data_fp=False,
                 disk_chunk_size=DEFAULT_DISK_CHUNK_SIZE,
                 uid=DEFAULT_UID, gid=DEFAULT_GID, iter_hook=None):
        self.disk_chunk_size = disk_chunk_size
        self.iter_hook = iter_hook
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
        self._is_dir = False
        self.tmppath = None
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
        data_file = os.path.join(self.datadir, self._obj)

        try:
            stats = do_stat(data_file)
        except OSError as ose:
            if ose.errno == errno.ENOENT or ose.errno == errno.ENOTDIR:
                return
            else:
                raise

        self.data_file = data_file
        self._is_dir = stat.S_ISDIR(stats.st_mode)

        self.metadata = read_metadata(data_file)
        if not self.metadata:
            create_object_metadata(data_file)
            self.metadata = read_metadata(data_file)

        if not validate_object(self.metadata):
            create_object_metadata(data_file)
            self.metadata = read_metadata(data_file)

        self.filter_metadata()

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
        #Marker directory
        if self._is_dir:
            return
        if self.fp:
            do_close(self.fp)
            self.fp = None

    def is_deleted(self):
        """
        Check if the file is deleted.

        :returns: True if the file doesn't exist or has been flagged as
                  deleted.
        """
        return not self.data_file

    def _create_dir_object(self, dir_path):
        stats = None
        try:
            stats = do_stat(dir_path)
        except OSError:
            pass

        if not stats:
            mkdirs(dir_path)
            do_chown(dir_path, self.uid, self.gid)
            create_object_metadata(dir_path)
        elif not stat.S_ISDIR(stats.st_mode):
            raise DiskFileError("Cannot overwrite "
                                "file %s with a directory" % dir_path)

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
        write_metadata(self.data_file, metadata)
        self.metadata = metadata
        self.filter_metadata()

    def put(self, fd, metadata, extension='.data'):
        """
        Finalize writing the file on disk, and renames it from the temp file
        to the real location.  This should be called after the data has been
        written to the temp file.

        :param fd: file descriptor of the temp file
        :param metadata: dictionary of metadata to be written
        :param extension: extension to be used when making the file
        """
        # Our caller will use '.data' here; we just ignore it since we map the
        # URL directly to the file system.

        metadata = _adjust_metadata(metadata)

        if dir_is_object(metadata):
            if not self.data_file:
                self.data_file = os.path.join(self.datadir, self._obj)
                self._create_dir_object(self.data_file)
            self.put_metadata(metadata)
            return

        # Check if directory already exists.
        if self._is_dir:
            # A pre-existing directory already exists on the file
            # system, perhaps gratuitously created when another
            # object was created, or created externally to Swift
            # REST API servicing (UFO use case).
            msg = 'File object exists as a directory: %s' % self.data_file
            raise AlreadyExistsAsDir(msg)

        write_metadata(self.tmppath, metadata)
        if X_CONTENT_LENGTH in metadata:
            self.drop_cache(fd, 0, int(metadata[X_CONTENT_LENGTH]))
        do_fsync(fd)
        if self._obj_path:
            dir_objs = self._obj_path.split('/')
            assert len(dir_objs) >= 1
            tmp_path = self._container_path
            for dir_name in dir_objs:
                tmp_path = os.path.join(tmp_path, dir_name)
                self._create_dir_object(tmp_path)

        do_fchown(fd, self.uid, self.gid)
        newpath = os.path.join(self.datadir, self._obj)
        renamer(self.tmppath, newpath)
        self.metadata = metadata
        self.data_file = newpath
        self.filter_metadata()
        return

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

        if self._is_dir:
            # Marker, or object, directory.
            #
            # Delete from the filesystem only if it contains
            # no objects.  If it does contain objects, then just
            # remove the object metadata tag which will make this directory a
            # fake-filesystem-only directory and will be deleted
            # when the container or parent directory is deleted.
            metadata = read_metadata(self.data_file)
            if dir_is_object(metadata):
                metadata[X_OBJECT_TYPE] = DIR_NON_OBJECT
                write_metadata(self.data_file, metadata)
            rmobjdir(self.data_file)

        else:
            # Delete file object
            do_unlink(self.data_file)

        # Garbage collection of non-object directories.
        # Now that we deleted the file, determine
        # if the current directory and any parent
        # directory may be deleted.
        dirname = os.path.dirname(self.data_file)
        while dirname and dirname != self._container_path:
            # Try to remove any directories that are not
            # objects.
            if not rmobjdir(dirname):
                # If a directory with objects has been
                # found, we can stop garabe collection
                break
            else:
                dirname = os.path.dirname(dirname)

        self.metadata = {}
        self.data_file = None

    def get_data_file_size(self):
        """
        Returns the os_path.getsize for the file.  Raises an exception if this
        file does not match the Content-Length stored in the metadata. Or if
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
                file_size = os_path.getsize(self.data_file)
                if X_CONTENT_LENGTH in self.metadata:
                    metadata_size = int(self.metadata[X_CONTENT_LENGTH])
                    if file_size != metadata_size:
                        self.metadata[X_CONTENT_LENGTH] = file_size
                        write_metadata(self.data_file, self.metadata)

                return file_size
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise
        raise DiskFileNotExist('Data File does not exist.')

    def filter_metadata(self):
        if X_TYPE in self.metadata:
            self.metadata.pop(X_TYPE)
        if X_OBJECT_TYPE in self.metadata:
            self.metadata.pop(X_OBJECT_TYPE)

    @contextmanager
    def mkstemp(self):
        """Contextmanager to make a temporary file."""

        # Creating intermidiate directories and corresponding metadata.
        # For optimization, check if the subdirectory already exists,
        # if exists, then it means that it also has its metadata.
        # Not checking for container, since the container should already
        # exist for the call to come here.
        if not os_path.exists(self.datadir):
            path = self._container_path
            subdir_list = self._obj_path.split(os.path.sep)
            for i in range(len(subdir_list)):
                path = os.path.join(path, subdir_list[i])
                if not os_path.exists(path):
                    self._create_dir_object(path)

        tmpfile = '.' + self._obj + '.' + md5(self._obj +
                  str(random.random())).hexdigest()

        self.tmppath = os.path.join(self.datadir, tmpfile)
        fd = do_open(self.tmppath, os.O_RDWR | os.O_CREAT | os.O_EXCL)
        try:
            yield fd
        finally:
            try:
                do_close(fd)
            except OSError:
                pass
            tmppath, self.tmppath = self.tmppath, None
            do_unlink(tmppath)
