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
import errno

from gluster.swift.common.fs_utils import dir_empty, mkdirs, do_chown, \
    do_exists, do_touch
from gluster.swift.common.utils import validate_account, validate_container, \
    get_container_details, get_account_details, create_container_metadata, \
    create_account_metadata, DEFAULT_GID, get_container_metadata, \
    get_account_metadata, DEFAULT_UID, validate_object, \
    create_object_metadata, read_metadata, write_metadata, X_CONTENT_TYPE, \
    X_CONTENT_LENGTH, X_TIMESTAMP, X_PUT_TIMESTAMP, X_ETAG, X_OBJECTS_COUNT, \
    X_BYTES_USED, X_CONTAINER_COUNT, DIR_TYPE, rmobjdir, dir_is_object
from gluster.swift.common import Glusterfs
from gluster.swift.common.exceptions import FileOrDirNotFoundError, \
    GlusterFileSystemIOError
from swift.common.constraints import MAX_META_COUNT, MAX_META_OVERALL_SIZE
from swift.common.swob import HTTPBadRequest


DATADIR = 'containers'

# Create a dummy db_file in Glusterfs.RUN_DIR
_db_file = ""


def _read_metadata(dd):
    """ Filter read metadata so that it always returns a tuple that includes
        some kind of timestamp. With 1.4.8 of the Swift integration the
        timestamps were not stored. Here we fabricate timestamps for volumes
        where the existing data has no timestamp (that is, stored data is not
        a tuple), allowing us a measure of backward compatibility.

        FIXME: At this time it does not appear that the timestamps on each
        metadata are used for much, so this should not hurt anything.
    """
    metadata_i = read_metadata(dd)
    metadata = {}
    timestamp = 0
    for key, value in metadata_i.iteritems():
        if not isinstance(value, tuple):
            value = (value, timestamp)
        metadata[key] = value
    return metadata


def filter_prefix(objects, prefix):
    """
    Accept a sorted list of strings, returning all strings starting with the
    given prefix.
    """
    found = False
    for object_name in objects:
        if object_name.startswith(prefix):
            yield object_name
            found = True
        else:
            # Since the list is assumed to be sorted, once we find an object
            # name that does not start with the prefix we know we won't find
            # any others, so we exit early.
            if found:
                break


def filter_delimiter(objects, delimiter, prefix, marker, path=None):
    """
    Accept a sorted list of strings, returning strings that:
      1. begin with "prefix" (empty string matches all)
      2. does not match the "path" argument
      3. does not contain the delimiter in the given prefix length
    """
    assert delimiter
    assert prefix is not None
    skip_name = None
    for object_name in objects:
        if prefix and not object_name.startswith(prefix):
            break
        if path is not None:
            if object_name == path:
                continue
            if skip_name:
                if object_name < skip_name:
                    continue
                else:
                    skip_name = None
            end = object_name.find(delimiter, len(prefix))
            if end >= 0 and (len(object_name) > (end + 1)):
                skip_name = object_name[:end] + chr(ord(delimiter) + 1)
                continue
        else:
            if skip_name:
                if object_name < skip_name:
                    continue
                else:
                    skip_name = None
            end = object_name.find(delimiter, len(prefix))
            if end > 0:
                dir_name = object_name[:end + 1]
                if dir_name != marker:
                    yield dir_name
                skip_name = object_name[:end] + chr(ord(delimiter) + 1)
                continue
        yield object_name


def filter_marker(objects, marker):
    """
    Accept sorted list of strings, return all strings whose value is strictly
    greater than the given marker value.
    """
    for object_name in objects:
        if object_name > marker:
            yield object_name


def filter_prefix_as_marker(objects, prefix):
    """
    Accept sorted list of strings, return all strings whose value is greater
    than or equal to the given prefix value.
    """
    for object_name in objects:
        if object_name >= prefix:
            yield object_name


def filter_end_marker(objects, end_marker):
    """
    Accept a list of strings, sorted, and return all the strings that are
    strictly less than the given end_marker string. We perform this as a
    generator to avoid creating potentially large intermediate object lists.
    """
    for object_name in objects:
        if object_name < end_marker:
            yield object_name
        else:
            break


class DiskCommon(object):
    """
    Common fields and methods shared between DiskDir and DiskAccount classes.
    """
    def __init__(self, root, drive, account, logger, pending_timeout=None,
                 stale_reads_ok=False):
        # WARNING: The following four fields are referenced as fields by our
        # callers outside of this module, do not remove.
        # Create a dummy db_file in Glusterfs.RUN_DIR
        global _db_file
        if not _db_file:
            _db_file = os.path.join(Glusterfs.RUN_DIR, 'db_file.db')
            if not do_exists(_db_file):
                do_touch(_db_file)
        self.db_file = _db_file
        self.metadata = {}
        self.pending_timeout = pending_timeout or 10
        self.stale_reads_ok = stale_reads_ok
        # The following fields are common
        self.root = root
        assert logger is not None
        self.logger = logger
        self.account = account
        self.datadir = os.path.join(root, drive)
        self._dir_exists = None

    def _dir_exists_read_metadata(self):
        self._dir_exists = do_exists(self.datadir)
        if self._dir_exists:
            try:
                self.metadata = _read_metadata(self.datadir)
            except GlusterFileSystemIOError as err:
                if err.errno in (errno.ENOENT, errno.ESTALE):
                    return False
                raise
        return self._dir_exists

    def is_deleted(self):
        # The intention of this method is to check the file system to see if
        # the directory actually exists.
        return not do_exists(self.datadir)

    def empty(self):
        # If it does not exist, then it is empty.  A value of True is
        # what is expected by OpenStack Swift when the directory does
        # not exist.  Check swift/common/db.py:ContainerBroker.empty()
        # and swift/container/server.py:ContainerController.DELETE()
        # for more information
        try:
            return dir_empty(self.datadir)
        except FileOrDirNotFoundError:
            return True

    def validate_metadata(self, metadata):
        """
        Validates that metadata falls within acceptable limits.

        :param metadata: to be validated
        :raises: HTTPBadRequest if MAX_META_COUNT or MAX_META_OVERALL_SIZE
                 is exceeded
        """
        meta_count = 0
        meta_size = 0
        for key, (value, timestamp) in metadata.iteritems():
            key = key.lower()
            if value != '' and (key.startswith('x-account-meta') or
                                key.startswith('x-container-meta')):
                prefix = 'x-account-meta-'
                if key.startswith('x-container-meta-'):
                    prefix = 'x-container-meta-'
                key = key[len(prefix):]
                meta_count = meta_count + 1
                meta_size = meta_size + len(key) + len(value)
        if meta_count > MAX_META_COUNT:
            raise HTTPBadRequest('Too many metadata items; max %d'
                                 % MAX_META_COUNT)
        if meta_size > MAX_META_OVERALL_SIZE:
            raise HTTPBadRequest('Total metadata too large; max %d'
                                 % MAX_META_OVERALL_SIZE)

    def update_metadata(self, metadata, validate_metadata=False):
        assert self.metadata, "Valid container/account metadata should have " \
            "been created by now"
        if metadata:
            new_metadata = self.metadata.copy()
            new_metadata.update(metadata)
            if validate_metadata:
                self.validate_metadata(new_metadata)
            if new_metadata != self.metadata:
                write_metadata(self.datadir, new_metadata)
                self.metadata = new_metadata


class DiskDir(DiskCommon):
    """
    Manage object files on disk.

    :param path: path to devices on the node
    :param drive: gluster volume drive name
    :param account: account name for the object
    :param container: container name for the object
    :param logger: account or container server logging object
    :param uid: user ID container object should assume
    :param gid: group ID container object should assume

    Usage pattern from container/server.py (Havana, 1.8.0+):
        DELETE:
            if auto-create and obj and not .db_file:
                # Creates container
                .initialize()
            if not .db_file:
                # Container does not exist
                return 404
            if obj:
                # Should be a NOOP
                .delete_object()
            else:
                if not .empty()
                    # Gluster's definition of empty should mean only
                    # sub-directories exist in Object-Only mode
                    return conflict
                .get_info()['put_timestamp'] and not .is_deleted()
                # Deletes container
                .delete_db()
                if not .is_deleted():
                    return conflict
                account_update():
                    .get_info()
        PUT:
            if obj:
                if auto-create cont and not .db_file
                    # Creates container
                    .initialize()
                if not .db_file
                    return 404
                .put_object()
            else:
                if not .db_file:
                    # Creates container
                    .initialize()
                else:
                    # Update container timestamp
                    .is_deleted()
                    .update_put_timestamp()
                    if .is_deleted()
                        return conflict
                if metadata:
                    if .metadata
                        .set_x_container_sync_points()
                    .update_metadata()
                account_update():
                    .get_info()
        HEAD:
            .pending_timeout
            .stale_reads_ok
            if .is_deleted():
                return 404
            .get_info()
            .metadata
        GET:
            .pending_timeout
            .stale_reads_ok
            if .is_deleted():
                return 404
            .get_info()
            .metadata
            .list_objects_iter()
        POST:
            if .is_deleted():
                return 404
            .metadata
            .set_x_container_sync_points()
            .update_metadata()
    """

    def __init__(self, path, drive, account, container, logger,
                 uid=DEFAULT_UID, gid=DEFAULT_GID, **kwargs):
        super(DiskDir, self).__init__(path, drive, account, logger, **kwargs)

        self.uid = int(uid)
        self.gid = int(gid)

        self.container = container
        self.datadir = os.path.join(self.datadir, self.container)

        if not self._dir_exists_read_metadata():
            return

        if not self.metadata:
            create_container_metadata(self.datadir)
            self.metadata = _read_metadata(self.datadir)
        else:
            if not validate_container(self.metadata):
                create_container_metadata(self.datadir)
                self.metadata = _read_metadata(self.datadir)

    def list_objects_iter(self, limit, marker, end_marker,
                          prefix, delimiter, path=None):
        """
        Returns tuple of name, created_at, size, content_type, etag.
        """
        assert limit >= 0
        assert not delimiter or (len(delimiter) == 1 and ord(delimiter) <= 254)

        if path is not None:
            if path:
                prefix = path = path.rstrip('/') + '/'
            else:
                prefix = path
            delimiter = '/'
        elif delimiter and not prefix:
            prefix = ''

        container_list = []

        objects = self._update_object_count()
        if objects:
            objects.sort()
        else:
            return container_list

        if end_marker:
            objects = filter_end_marker(objects, end_marker)

        if marker and marker >= prefix:
            objects = filter_marker(objects, marker)
        elif prefix:
            objects = filter_prefix_as_marker(objects, prefix)

        if prefix is None:
            # No prefix, we don't need to apply the other arguments, we just
            # return what we have.
            pass
        else:
            # We have a non-None (for all intents and purposes it is a string)
            # prefix.
            if not delimiter:
                if not prefix:
                    # We have nothing more to do
                    pass
                else:
                    objects = filter_prefix(objects, prefix)
            else:
                objects = filter_delimiter(objects, delimiter, prefix, marker,
                                           path)

        count = 0
        for obj in objects:
            obj_path = os.path.join(self.datadir, obj)
            try:
                metadata = read_metadata(obj_path)
            except GlusterFileSystemIOError as err:
                if err.errno in (errno.ENOENT, errno.ESTALE):
                    # obj might have been deleted by another process
                    # since the objects list was originally built
                    continue
                else:
                    raise err
            if not metadata or not validate_object(metadata):
                if delimiter == '/' and obj_path[-1] == delimiter:
                    clean_obj_path = obj_path[:-1]
                else:
                    clean_obj_path = obj_path
                try:
                    metadata = create_object_metadata(clean_obj_path)
                except OSError as e:
                    # FIXME - total hack to get upstream swift ported unit
                    # test cases working for now.
                    if e.errno not in (errno.ENOENT, errno.ESTALE):
                        raise
            if not Glusterfs._implicit_dir_objects and metadata \
                    and metadata[X_CONTENT_TYPE] == DIR_TYPE \
                    and not dir_is_object(metadata):
                continue
            list_item = []
            list_item.append(obj)
            if metadata:
                list_item.append(metadata[X_TIMESTAMP])
                list_item.append(int(metadata[X_CONTENT_LENGTH]))
                list_item.append(metadata[X_CONTENT_TYPE])
                list_item.append(metadata[X_ETAG])
            container_list.append(list_item)
            count += 1
            if count >= limit:
                break

        return container_list

    def _update_object_count(self):
        objects, object_count, bytes_used = get_container_details(self.datadir)

        if X_OBJECTS_COUNT not in self.metadata \
                or int(self.metadata[X_OBJECTS_COUNT][0]) != object_count \
                or X_BYTES_USED not in self.metadata \
                or int(self.metadata[X_BYTES_USED][0]) != bytes_used:
            self.metadata[X_OBJECTS_COUNT] = (object_count, 0)
            self.metadata[X_BYTES_USED] = (bytes_used, 0)
            write_metadata(self.datadir, self.metadata)

        return objects

    def get_info(self):
        """
        Get global data for the container.
        :returns: dict with keys: account, container, object_count, bytes_used,
                      hash, id, created_at, put_timestamp, delete_timestamp,
                      reported_put_timestamp, reported_delete_timestamp,
                      reported_object_count, and reported_bytes_used.
        """
        if self._dir_exists and Glusterfs._container_update_object_count:
            self._update_object_count()

        data = {'account': self.account, 'container': self.container,
                'object_count': self.metadata.get(
                    X_OBJECTS_COUNT, ('0', 0))[0],
                'bytes_used': self.metadata.get(X_BYTES_USED, ('0', 0))[0],
                'hash': '', 'id': '', 'created_at': '1',
                'put_timestamp': self.metadata.get(
                    X_PUT_TIMESTAMP, ('0', 0))[0],
                'delete_timestamp': '1',
                'reported_put_timestamp': '1',
                'reported_delete_timestamp': '1',
                'reported_object_count': '1', 'reported_bytes_used': '1',
                'x_container_sync_point1': self.metadata.get(
                    'x_container_sync_point1', -1),
                'x_container_sync_point2': self.metadata.get(
                    'x_container_sync_point2', -1),
                }
        return data

    def put_object(self, name, timestamp, size, content_type, etag, deleted=0):
        # NOOP - should never be called since object file creation occurs
        # within a directory implicitly.
        pass

    def initialize(self, timestamp):
        """
        Create and write metatdata to directory/container.
        :param metadata: Metadata to write.
        """
        if not self._dir_exists:
            mkdirs(self.datadir)
            # If we create it, ensure we own it.
            do_chown(self.datadir, self.uid, self.gid)
        metadata = get_container_metadata(self.datadir)
        metadata[X_TIMESTAMP] = (timestamp, 0)
        write_metadata(self.datadir, metadata)
        self.metadata = metadata
        self._dir_exists = True

    def update_put_timestamp(self, timestamp):
        """
        Update the PUT timestamp for the container.

        If the container does not exist, create it using a PUT timestamp of
        the given value.

        If the container does exist, update the PUT timestamp only if it is
        later than the existing value.
        """
        if not do_exists(self.datadir):
            self.initialize(timestamp)
        else:
            if timestamp > self.metadata[X_PUT_TIMESTAMP]:
                self.metadata[X_PUT_TIMESTAMP] = (timestamp, 0)
                write_metadata(self.datadir, self.metadata)

    def delete_object(self, name, timestamp):
        # NOOP - should never be called since object file removal occurs
        # within a directory implicitly.
        return

    def delete_db(self, timestamp):
        """
        Delete the container (directory) if empty.

        :param timestamp: delete timestamp
        """
        # Let's check and see if it has directories that
        # where created by the code, but not by the
        # caller as objects
        rmobjdir(self.datadir)

    def set_x_container_sync_points(self, sync_point1, sync_point2):
        self.metadata['x_container_sync_point1'] = sync_point1
        self.metadata['x_container_sync_point2'] = sync_point2


class DiskAccount(DiskCommon):
    """
    Usage pattern from account/server.py (Havana, 1.8.0+):
        DELETE:
            .is_deleted()
            .delete_db()
        PUT:
            container:
                .pending_timeout
                .db_file
                .initialize()
                .is_deleted()
                .put_container()
            account:
                .db_file
                .initialize()
                .is_status_deleted()
                .is_deleted()
                .update_put_timestamp()
                .is_deleted() ???
                .update_metadata()
        HEAD:
            .pending_timeout
            .stale_reads_ok
            .is_deleted()
            .get_info()
            .metadata
        GET:
            .pending_timeout
            .stale_reads_ok
            .is_deleted()
            .get_info()
            .metadata
            .list_containers_iter()
        POST:
            .is_deleted()
            .update_metadata()
    """

    def __init__(self, root, drive, account, logger, **kwargs):
        super(DiskAccount, self).__init__(root, drive, account, logger,
                                          **kwargs)

        # Since accounts should always exist (given an account maps to a
        # gluster volume directly, and the mount has already been checked at
        # the beginning of the REST API handling), just assert that that
        # assumption still holds.
        assert self._dir_exists_read_metadata()
        assert self._dir_exists

        if not self.metadata or not validate_account(self.metadata):
            create_account_metadata(self.datadir)
            self.metadata = _read_metadata(self.datadir)

    def is_status_deleted(self):
        """
        Only returns true if the status field is set to DELETED.
        """
        # This function should always return False. Accounts are not created
        # and deleted, they exist if a Gluster volume can be mounted. There is
        # no way to delete accounts, so this could never return True.
        return False

    def initialize(self, timestamp):
        """
        Create and write metatdata to directory/account.
        :param metadata: Metadata to write.
        """
        metadata = get_account_metadata(self.datadir)
        metadata[X_TIMESTAMP] = (timestamp, 0)
        write_metadata(self.datadir, metadata)
        self.metadata = metadata

    def update_put_timestamp(self, timestamp):
        # Since accounts always exists at this point, just update the account
        # PUT timestamp if this given timestamp is later than what we already
        # know.
        assert self._dir_exists

        if timestamp > self.metadata[X_PUT_TIMESTAMP][0]:
            self.metadata[X_PUT_TIMESTAMP] = (timestamp, 0)
            write_metadata(self.datadir, self.metadata)

    def delete_db(self, timestamp):
        """
        Mark the account as deleted

        :param timestamp: delete timestamp
        """
        # Deleting an account is a no-op, since accounts are one-to-one
        # mappings to gluster volumes.
        #
        # FIXME: This means the caller will end up returning a success status
        # code for an operation that really should not be allowed. Instead, we
        # should modify the account server to not allow the DELETE method, and
        # should probably modify the proxy account controller to not allow the
        # DELETE method as well.
        return

    def put_container(self, container, put_timestamp, del_timestamp,
                      object_count, bytes_used):
        """
        Create a container with the given attributes.

        :param name: name of the container to create
        :param put_timestamp: put_timestamp of the container to create
        :param delete_timestamp: delete_timestamp of the container to create
        :param object_count: number of objects in the container
        :param bytes_used: number of bytes used by the container
        """
        # NOOP - should never be called since container directory creation
        # occurs from within the account directory implicitly.
        return

    def _update_container_count(self):
        containers, container_count = get_account_details(self.datadir)

        if X_CONTAINER_COUNT not in self.metadata \
                or int(self.metadata[X_CONTAINER_COUNT][0]) != container_count:
            self.metadata[X_CONTAINER_COUNT] = (container_count, 0)
            write_metadata(self.datadir, self.metadata)

        return containers

    def list_containers_iter(self, limit, marker, end_marker,
                             prefix, delimiter):
        """
        Return tuple of name, object_count, bytes_used, 0(is_subdir).
        Used by account server.
        """
        if delimiter and not prefix:
            prefix = ''

        account_list = []
        containers = self._update_container_count()
        if containers:
            containers.sort()
        else:
            return account_list

        if containers and end_marker:
            containers = filter_end_marker(containers, end_marker)

        if containers:
            if marker and marker >= prefix:
                containers = filter_marker(containers, marker)
            elif prefix:
                containers = filter_prefix_as_marker(containers, prefix)

        if prefix is None:
            # No prefix, we don't need to apply the other arguments, we just
            # return what we have.
            pass
        else:
            # We have a non-None (for all intents and purposes it is a string)
            # prefix.
            if not delimiter:
                if not prefix:
                    # We have nothing more to do
                    pass
                else:
                    containers = filter_prefix(containers, prefix)
            else:
                containers = filter_delimiter(containers, delimiter, prefix,
                                              marker)

        count = 0
        for cont in containers:
            list_item = []
            metadata = None
            list_item.append(cont)
            cont_path = os.path.join(self.datadir, cont)
            metadata = _read_metadata(cont_path)
            if not metadata or not validate_container(metadata):
                try:
                    metadata = create_container_metadata(cont_path)
                except OSError as e:
                    # FIXME - total hack to get upstream swift ported unit
                    # test cases working for now.
                    if e.errno not in (errno.ENOENT, errno.ESTALE):
                        raise
            if metadata:
                list_item.append(metadata[X_OBJECTS_COUNT][0])
                list_item.append(metadata[X_BYTES_USED][0])
                list_item.append(0)
            account_list.append(list_item)
            count += 1
            if count >= limit:
                break

        return account_list

    def get_info(self):
        """
        Get global data for the account.
        :returns: dict with keys: account, created_at, put_timestamp,
                  delete_timestamp, container_count, object_count,
                  bytes_used, hash, id
        """
        if Glusterfs._account_update_container_count:
            self._update_container_count()

        data = {'account': self.account, 'created_at': '1',
                'put_timestamp': '1', 'delete_timestamp': '1',
                'container_count': self.metadata.get(
                    X_CONTAINER_COUNT, (0, 0))[0],
                'object_count': self.metadata.get(X_OBJECTS_COUNT, (0, 0))[0],
                'bytes_used': self.metadata.get(X_BYTES_USED, (0, 0))[0],
                'hash': '', 'id': ''}
        return data
