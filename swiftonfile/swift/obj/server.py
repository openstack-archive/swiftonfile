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

from swift.common.swob import HTTPConflict, HTTPNotImplemented, HeaderKeyDict
from swift.common.utils import public, timing_stats, replication, csv_append
from swift.common.request_helpers import get_name_and_placement
from swiftonfile.swift.common.exceptions import AlreadyExistsAsFile, \
    AlreadyExistsAsDir
from swift.common.request_helpers import split_and_validate_path
from swift.common.ring import Ring

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
    Subclass of the object server's ObjectController.
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
        self.swift_dir = conf.get('swift_dir', '/etc/swift')
        self.container_ring = None

    def get_container_ring(self):
        """Get the container ring.  Load it, if it hasn't been yet."""
        if not self.container_ring:
            self.container_ring = Ring(self.swift_dir, ring_name='container')
        return self.container_ring

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

    @public
    @replication
    @timing_stats(sample_rate=0.1)
    def REPLICATE(self, request):
        """
        In Swift, this method handles REPLICATE requests for the Swift
        Object Server.  This is used by the object replicator to get hashes
        for directories.

        Swiftonfile does not support this as it expects the underlying
        filesystem to take care of replication. Also, swiftonfile has no
        notion of hashes for directories.
        """
        return HTTPNotImplemented(request=request)

    @public
    @replication
    @timing_stats(sample_rate=0.1)
    def REPLICATION(self, request):
        return HTTPNotImplemented(request=request)

    def _sof_container_update(self, request, resp):
        """
        SOF specific metadata is set in DiskFile.open()._filter_metadata()
        This method internally invokes Swift's container_update() method.
        """
        device, partition, account, container, obj, policy_idx = \
            get_name_and_placement(request, 5, 5, True)

        # The container_update() method requires certain container
        # specific headers. The proxy object controller appends these
        # headers for PUT backend request but not for HEAD/GET requests.
        # Thus, we populate the required information in request
        # and then invoke container_update()
        container_partition, container_nodes = \
            self.get_container_ring().get_nodes(account, container)
        request.headers['X-Container-Partition'] = container_partition
        for node in container_nodes:
            request.headers['X-Container-Host'] = csv_append(
                request.headers.get('X-Container-Host'),
                '%(ip)s:%(port)s' % node)
            request.headers['X-Container-Device'] = csv_append(
                request.headers.get('X-Container-Device'), node['device'])

        self.container_update(
            'PUT', account, container, obj, request,
            HeaderKeyDict({
                'x-size': resp.headers['Content-Length'],
                'x-content-type': resp.headers['Content-Type'],
                'x-timestamp': resp.headers['X-Timestamp'],
                'x-etag': resp.headers['ETag']}),
            device, policy_idx)

    @public
    @timing_stats(sample_rate=0.8)
    def HEAD(self, request):
        # Call Swift's HEAD method
        resp = server.ObjectController.HEAD(self, request)

        if 'X-Object-Sysmeta-Update-Container' in resp.headers:
            self._sof_container_update(request, resp)
            resp.headers.pop('X-Object-Sysmeta-Update-Container')

        return resp

    @public
    @timing_stats()
    def GET(self, request):
        # Call Swift's GET method
        resp = server.ObjectController.GET(self, request)

        if 'X-Object-Sysmeta-Update-Container' in resp.headers:
            self._sof_container_update(request, resp)
            resp.headers.pop('X-Object-Sysmeta-Update-Container')

        return resp


def app_factory(global_conf, **local_conf):
    """paste.deploy app factory for creating WSGI object server apps"""
    conf = global_conf.copy()
    conf.update(local_conf)
    return ObjectController(conf)
