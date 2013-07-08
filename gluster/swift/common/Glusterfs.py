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
import fcntl
import time
import errno
import logging
import urllib

from ConfigParser import ConfigParser, NoSectionError, NoOptionError
from swift.common.utils import TRUE_VALUES, search_tree
from gluster.swift.common.fs_utils import do_ismount
from gluster.swift.common.exceptions import GlusterfsException, \
    FailureToMountError

#
# Read the fs.conf file once at startup (module load)
#
_fs_conf = ConfigParser()
MOUNT_IP = 'localhost'
OBJECT_ONLY = True
RUN_DIR = '/var/run/swift'
SWIFT_DIR = '/etc/swift'
_do_getsize = False
_allow_mount_per_server = False

if _fs_conf.read(os.path.join(SWIFT_DIR, 'fs.conf')):
    try:
        MOUNT_IP = _fs_conf.get('DEFAULT', 'mount_ip', MOUNT_IP)
    except (NoSectionError, NoOptionError):
        pass
    try:
        OBJECT_ONLY = _fs_conf.get('DEFAULT',
                                   'object_only',
                                   "yes") in TRUE_VALUES
    except (NoSectionError, NoOptionError):
        pass
    try:
        RUN_DIR = _fs_conf.get('DEFAULT', 'run_dir', RUN_DIR)
    except (NoSectionError, NoOptionError):
        pass

    try:
        _do_getsize = _fs_conf.get('DEFAULT',
                                   'accurate_size_in_listing',
                                   "no") in TRUE_VALUES
    except (NoSectionError, NoOptionError):
        pass

    try:
        _allow_mount_per_server = _fs_conf.get('DEFAULT',
                                               'allow_mount_per_server',
                                               _allow_mount_per_server
                                               ) in TRUE_VALUES
    except (NoSectionError, NoOptionError):
        pass

NAME = 'glusterfs'


def _busy_wait(full_mount_path):
    # Iterate for definite number of time over a given
    # interval for successful mount
    for i in range(0, 5):
        if os.path.ismount(full_mount_path):
            return True
        time.sleep(2)
    logging.error('Busy wait for mount timed out for mount %s',
                  full_mount_path)
    return False


def _get_unique_id():
    # Each individual server will attempt to get a free lock file
    # sequentially numbered, storing the pid of the holder of that
    # file, That number represents the numbered mount point to use
    # for its operations.
    if not _allow_mount_per_server:
        return 0
    try:
        os.mkdir(RUN_DIR)
    except OSError as err:
        if err.errno == errno.EEXIST:
            pass
    unique_id = 0
    lock_file_template = os.path.join(RUN_DIR,
                                      'swift.object-server-%03d.lock')
    for i in range(1, 201):
        lock_file = lock_file_template % i
        fd = os.open(lock_file, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError as ex:
            os.close(fd)
            if ex.errno in (errno.EACCES, errno.EAGAIN):
                # This means that some other process has it locked, so they
                # own the lock.
                continue
            raise
        except:
            os.close(fd)
            raise
        else:
            # We got the lock, write our PID into it, but don't close the
            # file, it will be closed when our process exists
            os.lseek(fd, 0, os.SEEK_SET)
            pid = str(os.getpid()) + '\n'
            os.write(fd, pid)
            unique_id = i
            break
    return unique_id


_unique_id = None


def _get_drive_mount_point_name(drive):
    """
    Get the GlusterFS mount point name to use for this worker for the target
    drive name.

    If unique is False, then we just map the drive directly to the mount point
    name. If unique is True, then we determine a unique mount point name that
    maps to our server PID.
    """
    if not _allow_mount_per_server:
        # One-to-one mapping of drive to mount point name
        mount_point = drive
    else:
        global _unique_id
        if _unique_id is None:
            _unique_id = _get_unique_id()
        mount_point = ("%s_%03d" % (drive, _unique_id)) \
            if _unique_id else drive
    return mount_point


def mount(root, drive):
    """
    Verify that the path to the device is a mount point and mounted.  This
    allows us to fast fail on drives that have been unmounted because of
    issues, and also prevents us for accidentally filling up the root
    partition.

    This method effectively replaces the swift.common.constraints.check_mount
    method in behavior, adding the ability to auto-mount the volume, which is
    dubious (FIXME).

    :param root:  base path where the devices are mounted
    :param drive: drive name to be checked
    :returns: True if it is a valid mounted device, False otherwise
    """
    if not (urllib.quote_plus(drive) == drive):
        return False

    mount_point = _get_drive_mount_point_name(drive)
    full_mount_path = os.path.join(root, mount_point)
    if do_ismount(full_mount_path):
        # Don't bother checking volume if it is already a mount point. Allows
        # us to use local file systems for unit tests and some functional test
        # environments to isolate behaviors from GlusterFS itself.
        return True

    # FIXME: Possible thundering herd problem here

    el = _get_export_list()
    for export in el:
        if drive == export:
            break
    else:
        logging.error('No export found in %r matching drive, %s', el, drive)
        return False

    try:
        os.makedirs(full_mount_path)
    except OSError as err:
        if err.errno == errno.EEXIST:
            pass
        else:
            logging.exception('Could not create mount path hierarchy:'
                              ' %s' % full_mount_path)
            return False

    mnt_cmd = 'mount -t glusterfs %s:%s %s' % (MOUNT_IP, export,
                                               full_mount_path)

    if _allow_mount_per_server:
        if os.system(mnt_cmd):
            logging.exception('Mount failed %s' % (mnt_cmd))
        return True

    lck_file = os.path.join(RUN_DIR, '%s.lock' % mount_point)

    try:
        os.mkdir(RUN_DIR)
    except OSError as err:
        if err.errno == errno.EEXIST:
            pass
        else:
            logging.exception('Could not create RUN_DIR: %s' % full_mount_path)
            return False

    fd = os.open(lck_file, os.O_CREAT | os.O_RDWR)
    with os.fdopen(fd, 'r+b') as f:
        try:
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError as ex:
            if ex.errno in (errno.EACCES, errno.EAGAIN):
                # This means that some other process is mounting the
                # filesystem, so wait for the mount process to complete
                return _busy_wait(full_mount_path)
        if os.system(mnt_cmd) or not _busy_wait(full_mount_path):
            logging.error('Mount failed %s', mnt_cmd)
            return False
    return True


def unmount(full_mount_path):
    # FIXME: Possible thundering herd problem here

    umnt_cmd = 'umount %s 2>> /dev/null' % full_mount_path
    if os.system(umnt_cmd):
        raise FailureToMountError(
            'Unable to unmount %s' % (full_mount_path))


def _get_export_list():
    cmnd = 'gluster --remote-host=%s volume info' % MOUNT_IP

    export_list = []

    if os.system(cmnd + ' >> /dev/null'):
        logging.error('Getting volume info failed, make sure to have'
                      ' passwordless ssh on %s', MOUNT_IP)
    else:
        fp = os.popen(cmnd)
        while True:
            item = fp.readline()
            if not item:
                break
            item = item.strip('\n').strip(' ')
            if item.lower().startswith('volume name:'):
                export_list.append(item.split(':')[1].strip(' '))

    return export_list


def get_mnt_point(vol_name, conf_dir=SWIFT_DIR, conf_file="object-server*"):
    """
    Read the object-server's configuration file and return
    the device value.

    :param vol_name: target GlusterFS volume name
    :param conf_dir: Swift configuration directory root
    :param conf_file: configuration file name for which to search
    :returns full path to given target volume name
    :raises GlusterfsException if unable to fetch mount point root from
            configuration files
    """
    mnt_dir = ''
    conf_files = search_tree(conf_dir, conf_file, '.conf')
    if not conf_files:
        raise GlusterfsException("Config file, %s, in directory, %s, "
                                 "not found" % (conf_file, conf_dir))
    _conf = ConfigParser()
    if _conf.read(conf_files[0]):
        mnt_dir = _conf.get('DEFAULT', 'devices', '')
        return os.path.join(mnt_dir, vol_name)
    else:
        raise GlusterfsException("Config file, %s, is empty" % conf_files[0])
