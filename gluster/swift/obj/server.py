# Copyright (c) 2012-2014 Red Hat, Inc.
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

import gluster.swift.common.constraints    # noqa
from swift.common.swob import HTTPConflict
from swift.common.utils import public, timing_stats
from gluster.swift.common.exceptions import AlreadyExistsAsFile, \
    AlreadyExistsAsDir
from swift.common.request_helpers import split_and_validate_path

from swift.obj import server

from gluster.swift.obj.diskfile import DiskFileManager


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
        # Common on-disk hierarchy shared across account, container and object
        # servers.
        self._diskfile_mgr = DiskFileManager(conf, self.logger)

    def get_diskfile(self, device, partition, account, container, obj,
                     policy_idx, **kwargs):
        """
        Utility method for instantiating a DiskFile object supporting a given
        REST API.

        An implementation of the object server that wants to use a different
        DiskFile class would simply over-ride this method to provide that
        behavior.
        """
        return self._diskfile_mgr.get_diskfile(
            device, partition, account, container, obj, policy_idx, **kwargs)

    @public
    @timing_stats()
    def PUT(self, request):
        try:
            server.check_object_creation = \
                gluster.swift.common.constraints.sof_check_object_creation
            return server.ObjectController.PUT(self, request)
        except (AlreadyExistsAsFile, AlreadyExistsAsDir):
            device = \
                split_and_validate_path(request, 1, 5, True)
            return HTTPConflict(drive=device, request=request)


def app_factory(global_conf, **local_conf):
    """paste.deploy app factory for creating WSGI object server apps"""
    conf = global_conf.copy()
    conf.update(local_conf)
    return ObjectController(conf)
