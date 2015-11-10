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
import json
import errno
import random
import logging
from hashlib import md5
from eventlet import sleep
import cPickle as pickle
from cStringIO import StringIO
import pickletools
from swiftonfile.swift.common.exceptions import SwiftOnFileSystemIOError
from swift.common.exceptions import DiskFileNoSpace
from swift.common.db import utf8encodekeys
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
X_MTIME = 'X-Object-PUT-Mtime'
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

read_pickled_metadata = False


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


class SafeUnpickler(object):
    """
    Loading a pickled stream is potentially unsafe and exploitable because
    the loading process can import modules/classes (via GLOBAL opcode) and
    run any callable (via REDUCE opcode). As the metadata stored in Swift
    is just a dictionary, we take away these powerful "features", thus
    making the loading process safe. Hence, this is very Swift specific
    and is not a general purpose safe unpickler.
    """

    __slots__ = 'OPCODE_BLACKLIST'
    OPCODE_BLACKLIST = ('GLOBAL', 'REDUCE', 'BUILD', 'OBJ', 'NEWOBJ', 'INST',
                        'EXT1', 'EXT2', 'EXT4')

    @classmethod
    def find_class(self, module, name):
        # Do not allow importing of ANY module. This is really redundant as
        # we block those OPCODEs that results in invocation of this method.
        raise pickle.UnpicklingError('Potentially unsafe pickle')

    @classmethod
    def loads(self, string):
        for opcode in pickletools.genops(string):
            if opcode[0].name in self.OPCODE_BLACKLIST:
                raise pickle.UnpicklingError('Potentially unsafe pickle')
        orig_unpickler = pickle.Unpickler(StringIO(string))
        orig_unpickler.find_global = self.find_class
        return orig_unpickler.load()


pickle.loads = SafeUnpickler.loads


def serialize_metadata(metadata):
    return json.dumps(metadata, separators=(',', ':'))


def deserialize_metadata(metastr):
    """
    Returns dict populated with metadata if deserializing is successful.
    Returns empty dict if deserialzing fails.
    """
    global read_pickled_metadata

    if metastr.startswith('\x80\x02}') and metastr.endswith('.') and \
            read_pickled_metadata:
        # Assert that the serialized metadata is pickled using
        # pickle protocol 2.
        try:
            return pickle.loads(metastr)
        except Exception:
            logging.warning("pickle.loads() failed.", exc_info=True)
            return {}
    elif metastr.startswith('{') and metastr.endswith('}'):
        try:
            metadata = json.loads(metastr)
            utf8encodekeys(metadata)
            return metadata
        except (UnicodeDecodeError, ValueError):
            logging.warning("json.loads() failed.", exc_info=True)
            return {}
    else:
        return {}


def read_metadata(path_or_fd):
    """
    Helper function to read the serialized metadata from a File/Directory.

    :param path_or_fd: File/Directory path or fd from which to read metadata.

    :returns: dictionary of metadata
    """
    metastr = ''
    key = 0
    try:
        while True:
            metastr += do_getxattr(path_or_fd, '%s%s' %
                                   (METADATA_KEY, (key or '')))
            key += 1
            if len(metastr) < MAX_XATTR_SIZE:
                # Prevent further getxattr calls
                break
    except IOError as err:
        if err.errno != errno.ENODATA:
            raise

    if not metastr:
        return {}

    metadata = deserialize_metadata(metastr)
    if not metadata:
        # Empty dict i.e deserializing of metadata has failed, probably
        # because it is invalid or incomplete or corrupt
        clean_metadata(path_or_fd)

    assert isinstance(metadata, dict)
    return metadata


def write_metadata(path_or_fd, metadata):
    """
    Helper function to write serialized metadata for a File/Directory.

    :param path_or_fd: File/Directory path or fd to write the metadata
    :param metadata: dictionary of metadata write
    """
    assert isinstance(metadata, dict)
    metastr = serialize_metadata(metadata)
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
                    '%s, setxattr("%s", %s, metastr)' % (err.strerror,
                                                         path_or_fd, key))
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
                err.errno, '%s, removexattr("%s", %s)' % (err.strerror,
                                                          path_or_fd, key))
        key += 1


def validate_object(metadata, statinfo=None):
    if not metadata:
        return False

    if X_TIMESTAMP not in metadata.keys() or \
       X_CONTENT_TYPE not in metadata.keys() or \
       X_ETAG not in metadata.keys() or \
       X_CONTENT_LENGTH not in metadata.keys() or \
       X_TYPE not in metadata.keys() or \
       X_OBJECT_TYPE not in metadata.keys():
        return False

    if statinfo and stat.S_ISREG(statinfo.st_mode):

        # File length has changed
        if int(metadata[X_CONTENT_LENGTH]) != statinfo.st_size:
            return False

        # File might have changed with length being the same.
        if X_MTIME in metadata and \
                normalize_timestamp(metadata[X_MTIME]) != \
                normalize_timestamp(statinfo.st_mtime):
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
            X_MTIME: 0 if is_dir else normalize_timestamp(stats.st_mtime),
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
            except IOError as err:
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
