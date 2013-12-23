#!/usr/bin/env python
# Copyright (c) 2013 Red Hat, Inc.
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

from swift.common.utils import readconf, config_true_value

config_file = {}
try:
    config_file = readconf("/etc/swift/proxy-server.conf",
                           section_name="filter:cache")
except SystemExit:
    pass

MEMCACHE_SERVERS = config_file.get('memcache_servers', None)

config_file = {}

try:
    config_file = readconf("/etc/swift/proxy-server.conf",
                           section_name="filter:kerbauth")
except SystemExit:
    pass

TOKEN_LIFE = int(config_file.get('token_life', 86400))
RESELLER_PREFIX = config_file.get('reseller_prefix', "AUTH_")
DEBUG_HEADERS = config_true_value(config_file.get('debug_headers', 'yes'))
