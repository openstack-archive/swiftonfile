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

import logging
import os
import errno
import stat
import random
import time
import xattr
from collections import defaultdict
from itertools import repeat
import ctypes
from eventlet import sleep
from swift.common.utils import load_libc_function
from swiftonfile.swift.common.exceptions import SwiftOnFileSystemOSError
from swift.common.exceptions import DiskFileNoSpace


def do_getxattr(path, key):
    return xattr.getxattr(path, key)


def do_setxattr(path, key, value):
    xattr.setxattr(path, key, value)


def do_removexattr(path, key):
    xattr.removexattr(path, key)


def do_walk(*args, **kwargs):
    return os.walk(*args, **kwargs)


def do_write(fd, buf):
    try:
        cnt = os.write(fd, buf)
    except OSError as err:
        filename = get_filename_from_fd(fd)
        if err.errno in (errno.ENOSPC, errno.EDQUOT):
            do_log_rl("do_write(%d, msg[%d]) failed: %s : %s",
                      fd, len(buf), err, filename)
            raise DiskFileNoSpace()
        else:
            raise SwiftOnFileSystemOSError(
                err.errno, '%s, os.write("%s", ...)' % (err.strerror, fd))
    return cnt


def do_read(fd, n):
    try:
        buf = os.read(fd, n)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.read("%s", ...)' % (err.strerror, fd))
    return buf


def do_ismount(path):
    """
    Test whether a path is a mount point.

    This is code hijacked from C Python 2.6.8, adapted to remove the extra
    lstat() system call.
    """
    try:
        s1 = os.lstat(path)
    except os.error as err:
        if err.errno == errno.ENOENT:
            # It doesn't exist -- so not a mount point :-)
            return False
        else:
            raise SwiftOnFileSystemOSError(
                err.errno, '%s, os.lstat("%s")' % (err.strerror, path))

    if stat.S_ISLNK(s1.st_mode):
        # A symlink can never be a mount point
        return False

    try:
        s2 = os.lstat(os.path.join(path, '..'))
    except os.error as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.lstat("%s")' % (err.strerror,
                                               os.path.join(path, '..')))

    dev1 = s1.st_dev
    dev2 = s2.st_dev
    if dev1 != dev2:
        # path/.. on a different device as path
        return True

    ino1 = s1.st_ino
    ino2 = s2.st_ino
    if ino1 == ino2:
        # path/.. is the same i-node as path
        return True

    return False


def do_mkdir(path):
    os.mkdir(path)


def do_rmdir(path):
    try:
        os.rmdir(path)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.rmdir("%s")' % (err.strerror, path))


def do_chown(path, uid, gid):
    try:
        os.chown(path, uid, gid)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.chown("%s", %s, %s)' % (
                err.strerror, path, uid, gid))


def do_fchown(fd, uid, gid):
    try:
        os.fchown(fd, uid, gid)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.fchown(%s, %s, %s)' % (
                err.strerror, fd, uid, gid))


_STAT_ATTEMPTS = 10


def do_stat(path):
    serr = None
    for i in range(0, _STAT_ATTEMPTS):
        try:
            stats = os.stat(path)
        except OSError as err:
            if err.errno == errno.EIO:
                # Retry EIO assuming it is a transient error from FUSE after a
                # short random sleep
                serr = err
                sleep(random.uniform(0.001, 0.005))
                continue
            if err.errno == errno.ENOENT:
                stats = None
            else:
                raise SwiftOnFileSystemOSError(
                    err.errno, '%s, os.stat("%s")[%d attempts]' % (
                        err.strerror, path, i))
        if i > 0:
            logging.warn("fs_utils.do_stat():"
                         " os.stat('%s') retried %d times (%s)",
                         path, i, 'success' if stats else 'failure')
        return stats
    else:
        raise SwiftOnFileSystemOSError(
            serr.errno, '%s, os.stat("%s")[%d attempts]' % (
                serr.strerror, path, _STAT_ATTEMPTS))


def do_fstat(fd):
    try:
        stats = os.fstat(fd)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.fstat(%s)' % (err.strerror, fd))
    return stats


def do_open(path, flags, mode=0o777):
    try:
        fd = os.open(path, flags, mode)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.open("%s", %x, %o)' % (
                err.strerror, path, flags, mode))
    return fd


def do_dup(fd):
    return os.dup(fd)


def do_close(fd):
    try:
        os.close(fd)
    except OSError as err:
        if err.errno in (errno.ENOSPC, errno.EDQUOT):
            filename = get_filename_from_fd(fd)
            do_log_rl("do_close(%d) failed: %s : %s",
                      fd, err, filename)
            raise DiskFileNoSpace()
        else:
            raise SwiftOnFileSystemOSError(
                err.errno, '%s, os.close(%s)' % (err.strerror, fd))


def do_unlink(path, log=True):
    try:
        os.unlink(path)
    except OSError as err:
        if err.errno != errno.ENOENT:
            raise SwiftOnFileSystemOSError(
                err.errno, '%s, os.unlink("%s")' % (err.strerror, path))
        else:
            logging.warn("fs_utils: os.unlink failed on non-existent path: %s",
                         path)


def do_rename(old_path, new_path):
    try:
        os.rename(old_path, new_path)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.rename("%s", "%s")' % (
                err.strerror, old_path, new_path))


def do_fsync(fd):
    try:
        os.fsync(fd)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.fsync("%s")' % (err.strerror, fd))


def do_fdatasync(fd):
    try:
        os.fdatasync(fd)
    except AttributeError:
        do_fsync(fd)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.fdatasync("%s")' % (err.strerror, fd))


_posix_fadvise = None


def do_fadvise64(fd, offset, length):
    global _posix_fadvise
    if _posix_fadvise is None:
        _posix_fadvise = load_libc_function('posix_fadvise64')
    # 4 means "POSIX_FADV_DONTNEED"
    _posix_fadvise(fd, ctypes.c_uint64(offset),
                   ctypes.c_uint64(length), 4)


def do_lseek(fd, pos, how):
    try:
        os.lseek(fd, pos, how)
    except OSError as err:
        raise SwiftOnFileSystemOSError(
            err.errno, '%s, os.lseek("%s")' % (err.strerror, fd))


def get_filename_from_fd(fd, verify=False):
    """
    Given the file descriptor, this method attempts to get the filename as it
    was when opened. This may not give accurate results in following cases:
    - file was renamed/moved/deleted after it was opened
    - file has multiple hardlinks

    :param fd: file descriptor of file opened
    :param verify: If True, performs additional checks using inode number
    """
    filename = None
    if isinstance(fd, int):
        try:
            filename = os.readlink("/proc/self/fd/" + str(fd))
        except OSError:
            pass

    if not verify:
        return filename

    # If verify = True, we compare st_dev and st_ino of file and fd.
    # This involves additional stat and fstat calls. So this is disabled
    # by default.
    if filename and fd:
        s_file = do_stat(filename)
        s_fd = do_fstat(fd)

        if s_file and s_fd:
            if (s_file.st_ino, s_file.st_dev) == (s_fd.st_ino, s_fd.st_dev):
                return filename

    return None


def static_var(varname, value):
    """Decorator function to create pseudo static variables."""
    def decorate(func):
        setattr(func, varname, value)
        return func
    return decorate

# Rate limit to emit log message once a second
_DO_LOG_RL_INTERVAL = 1.0


@static_var("counter", defaultdict(int))
@static_var("last_called", defaultdict(repeat(0.0).next))
def do_log_rl(msg, *args, **kwargs):
    """
    Rate limited logger.

    :param msg: String or message to be logged
    :param log_level: Possible values- error, warning, info, debug, critical
    """
    log_level = kwargs.get('log_level', "error")
    if log_level not in ("error", "warning", "info", "debug", "critical"):
        log_level = "error"

    do_log_rl.counter[msg] += 1  # Increment msg counter
    interval = time.time() - do_log_rl.last_called[msg]

    if interval >= _DO_LOG_RL_INTERVAL:
        # Prefix PID of process and message count to original log msg
        emit_msg = "[PID:" + str(os.getpid()) + "]" \
            + "[RateLimitedLog;Count:" + str(do_log_rl.counter[msg]) + "] " \
            + msg
        # log_level is a param for do_log_rl and not for logging.* methods
        try:
            del kwargs['log_level']
        except KeyError:
            pass

        getattr(logging, log_level)(emit_msg, *args, **kwargs)  # Emit msg
        do_log_rl.counter[msg] = 0  # Reset msg counter when message is emitted
        do_log_rl.last_called[msg] = time.time()  # Reset msg time
