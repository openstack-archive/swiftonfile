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

from swift.common.swob import HTTPConflict
from swift.common.utils import public, timing_stats
from swift.common.request_helpers import get_name_and_placement
from swiftonfile.swift.common.exceptions import AlreadyExistsAsFile, \
    AlreadyExistsAsDir
from swift.common.request_helpers import split_and_validate_path

from swift.obj import server

from swiftonfile.swift.obj.diskfile import DiskFileManager
from swiftonfile.swift.common.constraints import check_object_creation


class SwiftOnFileDiskFileRouter(object):
    """
    Replacement for Swift's DiskFileRouter object.
    Always returns SwiftOnFile's DiskFileManager implementation.
    """
    def __init__(self, *args, **kwargs):
        self.manager_cls = DiskFileManager(*args, **kwargs)

    def __getitem__(self, policy):
        return self.manager_cls


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
        # Replaces Swift's DiskFileRouter object reference with ours.
        self._diskfile_router = SwiftOnFileDiskFileRouter(conf, self.logger)

    @public
    @timing_stats()
    def PUT(self, request):
        try:
            device, partition, account, container, obj, policy = \
                get_name_and_placement(request, 5, 5, True)

            # check swiftonfile constraints first
            error_response = check_object_creation(request, obj)
            if error_response:
                return error_response

            # now call swift's PUT method
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
