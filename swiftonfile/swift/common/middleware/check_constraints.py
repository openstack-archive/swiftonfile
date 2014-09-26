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

"""
``constraints`` is a middleware which will check storage policies
specific constraints on PUT requests.

The ``sof_constraints`` middleware should be added to the pipeline in your
``/etc/swift/proxy-server.conf`` file, and a mapping of storage policies
using the swiftonfile object server should be listed in the 'policies'
variable in the filter section.

The swiftonfile constraints contains additional checks to make sure object
names conform with POSIX filesystems file and directory naming limitations

For example::

    [pipeline:main]
    pipeline = catch_errors sof_constraints cache proxy-server

    [filter:sof_constraints]
    use = egg:swift#sof_constraints
    policies=2,3
"""

from urllib import unquote
from swift.common.utils import get_logger
from swift.common.swob import Request
from swift.proxy.controllers.base import get_container_info
from swiftonfile.swift.common.constraints import check_object_creation \
    as sof_check_object_creation


class CheckConstraintsMiddleware(object):

    def __init__(self, app, conf):
        self.app = app
        self.logger = get_logger(conf, log_route='constraints')
        self.swift_dir = conf.get('swift_dir', '/etc/swift')
        self.policies = conf.get('policies', '')

    def __call__(self, env, start_response):
        request = Request(env)

        if request.method == 'PUT':
            try:
                version, account, container, obj = \
                    request.split_path(1, 4, True)
            except ValueError:
                return self.app(env, start_response)

            if obj is not None:
                obj = unquote(obj)
            else:
                return self.app(env, start_response)

            container_info = get_container_info(
                env, self.app)
            policy_idx = container_info['storage_policy']
            if policy_idx in self.policies:
                error_response = sof_check_object_creation(request, obj)
                if error_response:
                    self.logger.warn("returning error: %s", error_response)
                    return error_response(env, start_response)

        return self.app(env, start_response)


def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def check_constraints_filter(app):
        return CheckConstraintsMiddleware(app, conf)

    return check_constraints_filter
