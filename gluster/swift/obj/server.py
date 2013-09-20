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

""" Object Server for Gluster for Swift """

# Simply importing this monkey patches the constraint handling to fit our
# needs
import gluster.swift.common.constraints    # noqa

from swift.obj import server

from gluster.swift.obj.diskfile import OnDiskManager


class ObjectController(server.ObjectController):
    """
    Subclass of the object server's ObjectController which replaces the
    container_update method with one that is a no-op (information is simply
    stored on disk and already updated by virtue of performing the file system
    operations directly).
    """
    def setup(self, conf):
        """
        Implementation specific setup. This method is called at the very end
        by the constructor to allow a specific implementation to modify
        existing attributes or add its own attributes.

        :param conf: WSGI configuration parameter
        """
        # FIXME: Gluster currently does not support x-delete-at, as there is
        # no mechanism in GlusterFS itself to expire an object, or an external
        # process that will cull expired objects.
        try:
            self.allowed_headers.remove('x-delete-at')
        except KeyError:
            pass
        # Common on-disk hierarchy shared across account, container and object
        # servers.
        self._ondisk_mgr = OnDiskManager(conf, self.logger)

    def get_diskfile(self, device, partition, account, container, obj,
                     **kwargs):
        """
        Utility method for instantiating a DiskFile object supporting a given
        REST API.

        An implementation of the object server that wants to use a different
        DiskFile class would simply over-ride this method to provide that
        behavior.
        """
        return self._ondisk_mgr.get_diskfile(device, account, container, obj,
                                             **kwargs)

    def container_update(self, *args, **kwargs):
        """
        Update the container when objects are updated.

        For Gluster, this is just a no-op, since a container is just the
        directory holding all the objects (sub-directory hierarchy of files).
        """
        return

    def delete_at_update(self, *args, **kwargs):
        """
        Update the expiring objects container when objects are updated.

        FIXME: Gluster currently does not support delete_at headers.
        """
        return


def app_factory(global_conf, **local_conf):
    """paste.deploy app factory for creating WSGI object server apps"""
    conf = global_conf.copy()
    conf.update(local_conf)
    return ObjectController(conf)
