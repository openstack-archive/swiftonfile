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
import random
import logging
from hashlib import md5
from eventlet import sleep
import cPickle as pickle
from swiftonfile.swift.common.exceptions import SwiftOnFileSystemIOError
from swift.common.exceptions import DiskFileNoSpace
from swiftonfile.swift.common.fs_utils import do_stat, \
    do_walk, do_rmdir, do_log_rl, get_filename_from_fd, do_open, \
    do_getxattr, do_setxattr, do_removexattr, do_read, \
    do_close, do_dup, do_lseek, do_fstat, do_fsync, do_rename

X_CONTENT_TYPE = 'Content-Type'
X_CONTENT_LENGTH = 'Content-Length'
X_TIMESTAMP = 'X-Timestamp'
X_TYPE = 'X-Type'
X_ETAG = 'ETag'
X_OBJECT_TYPE = 'X-Object-Type'
DIR_TYPE = 'application/directory'
METADATA_KEY = 'user.swift.metadata'
MAX_XATTR_SIZE = 65536
DIR_NON_OBJECT = 'dir'
DIR_OBJECT = 'marker_dir'
FILE = 'file'
FILE_TYPE = 'application/octet-stream'
OBJECT = 'Object'
DEFAULT_UID = -1
DEFAULT_GID = -1
PICKLE_PROTOCOL = 2
CHUNK_SIZE = 65536


def normalize_timestamp(timestamp):
    """
    Format a timestamp (string or numeric) into a standardized
    xxxxxxxxxx.xxxxx (10.5) format.

    Note that timestamps using values greater than or equal to November 20th,
    2286 at 17:46 UTC will use 11 digits to represent the number of
    seconds.

    :param timestamp: unix timestamp
    :returns: normalized timestamp as a string
    """
    return "%016.05f" % (float(timestamp))


def read_metadata(path_or_fd):
    """
    Helper function to read the pickled metadata from a File/Directory.

    :param path_or_fd: File/Directory path or fd from which to read metadata.

    :returns: dictionary of metadata
    """
    metadata = None
    metadata_s = ''
    key = 0
    while metadata is None:
        try:
            metadata_s += do_getxattr(path_or_fd,
                                      '%s%s' % (METADATA_KEY, (key or '')))
        except IOError as err:
            if err.errno == errno.ENODATA:
                if key > 0:
                    # No errors reading the xattr keys, but since we have not
                    # been able to find enough chunks to get a successful
                    # unpickle operation, we consider the metadata lost, and
                    # drop the existing data so that the internal state can be
                    # recreated.
                    clean_metadata(path_or_fd)
                # We either could not find any metadata key, or we could find
                # some keys, but were not successful in performing the
                # unpickling (missing keys perhaps)? Either way, just report
                # to the caller we have no metadata.
                metadata = {}
            else:
                # Note that we don't touch the keys on errors fetching the
                # data since it could be a transient state.
                raise SwiftOnFileSystemIOError(
                    err.errno, 'getxattr("%s", %s)' % (path_or_fd, key))
        else:
            try:
                # If this key provides all or the remaining part of the pickle
                # data, we don't need to keep searching for more keys. This
                # means if we only need to store data in N xattr key/value
                # pair, we only need to invoke xattr get N times. With large
                # keys sizes we are shooting for N = 1.
                metadata = pickle.loads(metadata_s)
                assert isinstance(metadata, dict)
            except (EOFError, pickle.UnpicklingError):
                # We still are not able recognize this existing data collected
                # as a pickled object. Make sure we loop around to try to get
                # more from another xattr key.
                metadata = None
                key += 1
    return metadata


def write_metadata(path_or_fd, metadata):
    """
    Helper function to write pickled metadata for a File/Directory.

    :param path_or_fd: File/Directory path or fd to write the metadata
    :param metadata: dictionary of metadata write
    """
    assert isinstance(metadata, dict)
    metastr = pickle.dumps(metadata, PICKLE_PROTOCOL)
    key = 0
    while metastr:
        try:
            do_setxattr(path_or_fd,
                        '%s%s' % (METADATA_KEY, key or ''),
                        metastr[:MAX_XATTR_SIZE])
        except IOError as err:
            if err.errno in (errno.ENOSPC, errno.EDQUOT):
                if isinstance(path_or_fd, int):
                    filename = get_filename_from_fd(path_or_fd)
                    do_log_rl("write_metadata(%d, metadata) failed: %s : %s",
                              path_or_fd, err, filename)
                else:
                    do_log_rl("write_metadata(%s, metadata) failed: %s",
                              path_or_fd, err)
                raise DiskFileNoSpace()
            else:
                raise SwiftOnFileSystemIOError(
                    err.errno,
                    'setxattr("%s", %s, metastr)' % (path_or_fd, key))
        metastr = metastr[MAX_XATTR_SIZE:]
        key += 1


def clean_metadata(path_or_fd):
    key = 0
    while True:
        try:
            do_removexattr(path_or_fd, '%s%s' % (METADATA_KEY, (key or '')))
        except IOError as err:
            if err.errno == errno.ENODATA:
                break
            raise SwiftOnFileSystemIOError(
                err.errno, 'removexattr("%s", %s)' % (path_or_fd, key))
        key += 1


def validate_object(metadata):
    if not metadata:
        return False

    if X_TIMESTAMP not in metadata.keys() or \
       X_CONTENT_TYPE not in metadata.keys() or \
       X_ETAG not in metadata.keys() or \
       X_CONTENT_LENGTH not in metadata.keys() or \
       X_TYPE not in metadata.keys() or \
       X_OBJECT_TYPE not in metadata.keys():
        return False

    if metadata[X_TYPE] == OBJECT:
        return True

    logging.warn('validate_object: metadata type is not OBJECT (%r)',
                 metadata[X_TYPE])
    return False


def _read_for_etag(fp):
    etag = md5()
    while True:
        chunk = do_read(fp, CHUNK_SIZE)
        if chunk:
            etag.update(chunk)
            if len(chunk) >= CHUNK_SIZE:
                # It is likely that we have more data to be read from the
                # file. Yield the co-routine cooperatively to avoid
                # consuming the worker during md5sum() calculations on
                # large files.
                sleep()
        else:
            break
    return etag.hexdigest()


def _get_etag(path_or_fd):
    """
    FIXME: It would be great to have a translator that returns the md5sum() of
    the file as an xattr that can be simply fetched.

    Since we don't have that we should yield after each chunk read and
    computed so that we don't consume the worker thread.
    """
    if isinstance(path_or_fd, int):
        # We are given a file descriptor, so this is an invocation from the
        # DiskFile.open() method.
        fd = path_or_fd
        etag = _read_for_etag(do_dup(fd))
        do_lseek(fd, 0, os.SEEK_SET)
    else:
        # We are given a path to the object when the DiskDir.list_objects_iter
        # method invokes us.
        path = path_or_fd
        fd = do_open(path, os.O_RDONLY)
        etag = _read_for_etag(fd)
        do_close(fd)

    return etag


def get_object_metadata(obj_path_or_fd):
    """
    Return metadata of object.
    """
    if isinstance(obj_path_or_fd, int):
        # We are given a file descriptor, so this is an invocation from the
        # DiskFile.open() method.
        stats = do_fstat(obj_path_or_fd)
    else:
        # We are given a path to the object when the DiskDir.list_objects_iter
        # method invokes us.
        stats = do_stat(obj_path_or_fd)

    if not stats:
        metadata = {}
    else:
        is_dir = stat.S_ISDIR(stats.st_mode)
        metadata = {
            X_TYPE: OBJECT,
            X_TIMESTAMP: normalize_timestamp(stats.st_ctime),
            X_CONTENT_TYPE: DIR_TYPE if is_dir else FILE_TYPE,
            X_OBJECT_TYPE: DIR_NON_OBJECT if is_dir else FILE,
            X_CONTENT_LENGTH: 0 if is_dir else stats.st_size,
            X_ETAG: md5().hexdigest() if is_dir else _get_etag(obj_path_or_fd)}
    return metadata


def restore_metadata(path, metadata):
    meta_orig = read_metadata(path)
    if meta_orig:
        meta_new = meta_orig.copy()
        meta_new.update(metadata)
    else:
        meta_new = metadata
    if meta_orig != meta_new:
        write_metadata(path, meta_new)
    return meta_new


def create_object_metadata(obj_path_or_fd):
    # We must accept either a path or a file descriptor as an argument to this
    # method, as the diskfile modules uses a file descriptior and the DiskDir
    # module (for container operations) uses a path.
    metadata = get_object_metadata(obj_path_or_fd)
    return restore_metadata(obj_path_or_fd, metadata)


# The following dir_xxx calls should definitely be replaced
# with a Metadata class to encapsulate their implementation.
# :FIXME: For now we have them as functions, but we should
# move them to a class.
def dir_is_object(metadata):
    """
    Determine if the directory with the path specified
    has been identified as an object
    """
    return metadata.get(X_OBJECT_TYPE, "") == DIR_OBJECT


def rmobjdir(dir_path):
    """
    Removes the directory as long as there are no objects stored in it. This
    works for containers also.
    """
    try:
        do_rmdir(dir_path)
    except OSError as err:
        if err.errno == errno.ENOENT:
            # No such directory exists
            return False
        if err.errno != errno.ENOTEMPTY:
            raise
        # Handle this non-empty directories below.
    else:
        return True

    # We have a directory that is not empty, walk it to see if it is filled
    # with empty sub-directories that are not user created objects
    # (gratuitously created as a result of other object creations).
    for (path, dirs, files) in do_walk(dir_path, topdown=False):
        for directory in dirs:
            fullpath = os.path.join(path, directory)

            try:
                metadata = read_metadata(fullpath)
            except OSError as err:
                if err.errno == errno.ENOENT:
                    # Ignore removal from another entity.
                    continue
                raise
            else:
                if dir_is_object(metadata):
                    # Wait, this is an object created by the caller
                    # We cannot delete
                    return False

            # Directory is not an object created by the caller
            # so we can go ahead and delete it.
            try:
                do_rmdir(fullpath)
            except OSError as err:
                if err.errno == errno.ENOTEMPTY:
                    # Directory is not empty, it might have objects in it
                    return False
                if err.errno == errno.ENOENT:
                    # No such directory exists, already removed, ignore
                    continue
                raise

    try:
        do_rmdir(dir_path)
    except OSError as err:
        if err.errno == errno.ENOTEMPTY:
            # Directory is not empty, race with object creation
            return False
        if err.errno == errno.ENOENT:
            # No such directory exists, already removed, ignore
            return True
        raise
    else:
        return True


def write_pickle(obj, dest, tmp=None, pickle_protocol=0):
    """
    Ensure that a pickle file gets written to disk.  The file is first written
    to a tmp file location in the destination directory path, ensured it is
    synced to disk, then moved to its final destination name.

    This version takes advantage of Gluster's dot-prefix-dot-suffix naming
    where the a file named ".thefile.name.9a7aasv" is hashed to the same
    Gluster node as "thefile.name". This ensures the renaming of a temp file
    once written does not move it to another Gluster node.

    :param obj: python object to be pickled
    :param dest: path of final destination file
    :param tmp: path to tmp to use, defaults to None (ignored)
    :param pickle_protocol: protocol to pickle the obj with, defaults to 0
    """
    dirname = os.path.dirname(dest)
    # Create destination directory
    try:
        os.makedirs(dirname)
    except OSError as err:
        if err.errno != errno.EEXIST:
            raise
    basename = os.path.basename(dest)
    tmpname = '.' + basename + '.' + \
        md5(basename + str(random.random())).hexdigest()
    tmppath = os.path.join(dirname, tmpname)
    with open(tmppath, 'wb') as fo:
        pickle.dump(obj, fo, pickle_protocol)
        # TODO: This flush() method call turns into a flush() system call
        # We'll need to wrap this as well, but we would do this by writing
        # a context manager for our own open() method which returns an object
        # in fo which makes the gluster API call.
        fo.flush()
        do_fsync(fo)
    do_rename(tmppath, dest)
