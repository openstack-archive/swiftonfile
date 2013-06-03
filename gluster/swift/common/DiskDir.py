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
import errno

from gluster.swift.common.fs_utils import dir_empty, rmdirs, mkdirs, os_path
from gluster.swift.common.utils import validate_account, validate_container, \
    get_container_details, get_account_details, create_container_metadata, \
    create_account_metadata, DEFAULT_GID, get_container_metadata, \
    get_account_metadata, DEFAULT_UID, validate_object, \
    create_object_metadata, read_metadata, write_metadata, X_CONTENT_TYPE, \
    X_CONTENT_LENGTH, X_TIMESTAMP, X_PUT_TIMESTAMP, X_ETAG, X_OBJECTS_COUNT, \
    X_BYTES_USED, X_CONTAINER_COUNT, DIR_TYPE
from gluster.swift.common import Glusterfs


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
      4.
    be those that start with the prefix.
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
    def is_deleted(self):
        return not os_path.exists(self.datadir)


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
                 uid=DEFAULT_UID, gid=DEFAULT_GID):
        self.root = path
        if container:
            self.container = container
        else:
            self.container = None
        if self.container:
            self.datadir = os.path.join(path, drive, self.container)
        else:
            self.datadir = os.path.join(path, drive)
        self.account = account
        assert logger is not None
        self.logger = logger
        self.metadata = {}
        self.container_info = None
        self.uid = int(uid)
        self.gid = int(gid)
        # Create a dummy db_file in Glusterfs.RUN_DIR
        global _db_file
        if not _db_file:
            _db_file = os.path.join(Glusterfs.RUN_DIR, 'db_file.db')
            if not os.path.exists(_db_file):
                file(_db_file, 'w+')
        self.db_file = _db_file
        self.dir_exists = os_path.exists(self.datadir)
        if self.dir_exists:
            self.metadata = _read_metadata(self.datadir)
        else:
            return
        if self.container:
            if not self.metadata:
                create_container_metadata(self.datadir)
                self.metadata = _read_metadata(self.datadir)
            else:
                if not validate_container(self.metadata):
                    create_container_metadata(self.datadir)
                    self.metadata = _read_metadata(self.datadir)
        else:
            if not self.metadata:
                create_account_metadata(self.datadir)
                self.metadata = _read_metadata(self.datadir)
            else:
                if not validate_account(self.metadata):
                    create_account_metadata(self.datadir)
                    self.metadata = _read_metadata(self.datadir)

    def empty(self):
        return dir_empty(self.datadir)

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

        objects = self.update_object_count()
        if objects:
            objects.sort()
        else:
            return container_list

        if objects and end_marker:
            objects = filter_end_marker(objects, end_marker)

        if objects:
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
            metadata = read_metadata(obj_path)
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
                    if e.errno != errno.ENOENT:
                        raise
            if Glusterfs.OBJECT_ONLY and metadata \
                    and metadata[X_CONTENT_TYPE] == DIR_TYPE:
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

    def update_object_count(self):
        objects, object_count, bytes_used = get_container_details(self.datadir)

        if X_OBJECTS_COUNT not in self.metadata \
                or int(self.metadata[X_OBJECTS_COUNT][0]) != object_count \
                or X_BYTES_USED not in self.metadata \
                or int(self.metadata[X_BYTES_USED][0]) != bytes_used:
            self.metadata[X_OBJECTS_COUNT] = (object_count, 0)
            self.metadata[X_BYTES_USED] = (bytes_used, 0)
            write_metadata(self.datadir, self.metadata)

        return objects

    def update_container_count(self):
        containers, container_count = get_account_details(self.datadir)

        if X_CONTAINER_COUNT not in self.metadata \
                or int(self.metadata[X_CONTAINER_COUNT][0]) != container_count:
            self.metadata[X_CONTAINER_COUNT] = (container_count, 0)
            write_metadata(self.datadir, self.metadata)

        return containers

    def get_info(self, include_metadata=False):
        """
        Get global data for the container.
        :returns: dict with keys: account, container, object_count, bytes_used,
                      hash, id, created_at, put_timestamp, delete_timestamp,
                      reported_put_timestamp, reported_delete_timestamp,
                      reported_object_count, and reported_bytes_used.
                  If include_metadata is set, metadata is included as a key
                  pointing to a dict of tuples of the metadata
        """
        if not Glusterfs.OBJECT_ONLY:
            # If we are not configured for object only environments, we should
            # update the object counts in case they changed behind our back.
            self.update_object_count()
        else:
            # FIXME: to facilitate testing, we need to update all the time
            self.update_object_count()

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
        if include_metadata:
            data['metadata'] = self.metadata
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
        if not self.dir_exists:
            mkdirs(self.datadir)
            # If we create it, ensure we own it.
            os.chown(self.datadir, self.uid, self.gid)
        metadata = get_container_metadata(self.datadir)
        metadata[X_TIMESTAMP] = timestamp
        write_metadata(self.datadir, metadata)
        self.metadata = metadata
        self.dir_exists = True

    def update_put_timestamp(self, timestamp):
        """
        Create the container if it doesn't exist and update the timestamp
        """
        if not os_path.exists(self.datadir):
            self.initialize(timestamp)
        else:
            self.metadata[X_PUT_TIMESTAMP] = timestamp
            write_metadata(self.datadir, self.metadata)

    def delete_object(self, name, timestamp):
        # NOOP - should never be called since object file removal occurs
        # within a directory implicitly.
        pass

    def delete_db(self, timestamp):
        """
        Delete the container

        :param timestamp: delete timestamp
        """
        if dir_empty(self.datadir):
            rmdirs(self.datadir)

    def update_metadata(self, metadata):
        assert self.metadata, "Valid container/account metadata should have" \
            " been created by now"
        if metadata:
            new_metadata = self.metadata.copy()
            new_metadata.update(metadata)
            if new_metadata != self.metadata:
                write_metadata(self.datadir, new_metadata)
                self.metadata = new_metadata

    def set_x_container_sync_points(self, sync_point1, sync_point2):
        self.metadata['x_container_sync_point1'] = sync_point1
        self.metadata['x_container_sync_point2'] = sync_point2


class DiskAccount(DiskDir):
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

    def __init__(self, root, drive, account, logger):
        super(DiskAccount, self).__init__(root, drive, account, None, logger)
        assert self.dir_exists

    def is_status_deleted(self):
        """Only returns true if the status field is set to DELETED."""
        return False

    def initialize(self, timestamp):
        """
        Create and write metatdata to directory/account.
        :param metadata: Metadata to write.
        """
        metadata = get_account_metadata(self.datadir)
        metadata[X_TIMESTAMP] = timestamp
        write_metadata(self.datadir, metadata)
        self.metadata = metadata

    def delete_db(self, timestamp):
        """
        Mark the account as deleted

        :param timestamp: delete timestamp
        """
        # NOOP - Accounts map to gluster volumes, and so they cannot be
        # deleted.
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

    def list_containers_iter(self, limit, marker, end_marker,
                             prefix, delimiter):
        """
        Return tuple of name, object_count, bytes_used, 0(is_subdir).
        Used by account server.
        """
        if delimiter and not prefix:
            prefix = ''

        account_list = []
        containers = self.update_container_count()
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
                    # FIXME - total hack to get port unit test cases
                    # working for now.
                    if e.errno != errno.ENOENT:
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

    def get_info(self, include_metadata=False):
        """
        Get global data for the account.
        :returns: dict with keys: account, created_at, put_timestamp,
                  delete_timestamp, container_count, object_count,
                  bytes_used, hash, id
        """
        if not Glusterfs.OBJECT_ONLY:
            # If we are not configured for object only environments, we should
            # update the container counts in case they changed behind our back.
            self.update_container_count()
        else:
            # FIXME: to facilitate testing, we need to update all the time
            self.update_container_count()

        data = {'account': self.account, 'created_at': '1',
                'put_timestamp': '1', 'delete_timestamp': '1',
                'container_count': self.metadata.get(
                    X_CONTAINER_COUNT, (0, 0))[0],
                'object_count': self.metadata.get(X_OBJECTS_COUNT, (0, 0))[0],
                'bytes_used': self.metadata.get(X_BYTES_USED, (0, 0))[0],
                'hash': '', 'id': ''}

        if include_metadata:
            data['metadata'] = self.metadata
        return data
