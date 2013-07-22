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

""" Object Server for Gluster Swift UFO """

# Simply importing this monkey patches the constraint handling to fit our
# needs
import gluster.swift.common.constraints    # noqa
import gluster.swift.common.utils          # noqa

from swift.obj import server
from gluster.swift.common.DiskFile import Gluster_DiskFile

# Monkey patch the object server module to use Gluster's DiskFile definition
server.DiskFile = Gluster_DiskFile


class ObjectController(server.ObjectController):
    """
    Subclass of the object server's ObjectController which replaces the
    container_update method with one that is a no-op (information is simply
    stored on disk and already updated by virtue of performing the file system
    operations directly).
    """

    def container_update(self, op, account, container, obj, request,
                         headers_out, objdevice):
        """
        Update the container when objects are updated.

        For Gluster, this is just a no-op, since a container is just the
        directory holding all the objects (sub-directory hierarchy of files).

        :param op: operation performed (ex: 'PUT', or 'DELETE')
        :param account: account name for the object
        :param container: container name for the object
        :param obj: object name
        :param request: the original request object driving the update
        :param headers_out: dictionary of headers to send in the container
                            request(s)
        :param objdevice: device name that the object is in
        """
        return


def app_factory(global_conf, **local_conf):
    """paste.deploy app factory for creating WSGI object server apps"""
    conf = global_conf.copy()
    conf.update(local_conf)
    return ObjectController(conf)
