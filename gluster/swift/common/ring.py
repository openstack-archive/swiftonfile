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

import os
import errno
from ConfigParser import ConfigParser
from swift.common.ring import ring
from swift.common.utils import search_tree
from gluster.swift.common.Glusterfs import SWIFT_DIR

reseller_prefix = "AUTH_"
conf_files = search_tree(SWIFT_DIR, "proxy-server*", 'conf')
if conf_files:
    conf_file = conf_files[0]

_conf = ConfigParser()
if conf_files and _conf.read(conf_file):
    if _conf.defaults().get("reseller_prefix", None):
        reseller_prefix = _conf.defaults().get("reseller_prefix")
    else:
        for key, value in _conf._sections.items():
            if value.get("reseller_prefix", None):
                reseller_prefix = value["reseller_prefix"]
                break

if not reseller_prefix.endswith('_'):
    reseller_prefix = reseller_prefix + '_'


class Ring(ring.Ring):

    def __init__(self, serialized_path, reload_time=15, ring_name=None):
        self.false_node = {'zone': 1, 'weight': 100.0, 'ip': '127.0.0.1',
                           'id': 0, 'meta': '', 'device': 'volume_not_in_ring',
                           'port': 6012}
        self.account_list = []

        if ring_name:
            _serialized_path = os.path.join(serialized_path,
                                            ring_name + '.ring.gz')
        else:
            _serialized_path = os.path.join(serialized_path)

        if not os.path.exists(_serialized_path):
            raise OSError(errno.ENOENT, 'No such file or directory',
                          '%s ring file does not exists, aborting '
                          'proxy-server start.' % _serialized_path)

        ring.Ring.__init__(self, serialized_path, reload_time, ring_name)

    def _get_part_nodes(self, part):
        seen_ids = set()

        try:
            account = self.account_list[part]
        except IndexError:
            return [self.false_node]
        else:
            nodes = []
            for dev in self._devs:
                if dev['device'] == account:
                    if dev['id'] not in seen_ids:
                        seen_ids.add(dev['id'])
                        nodes.append(dev)
            if not nodes:
                nodes = [self.false_node]
        return nodes

    def get_part_nodes(self, part):
        """
        Get the nodes that are responsible for the partition. If one
        node is responsible for more than one replica of the same
        partition, it will only appear in the output once.

        :param part: partition to get nodes for
        :returns: list of node dicts

        See :func:`get_nodes` for a description of the node dicts.
        """
        return self._get_part_nodes(part)

    def get_part(self, account, container=None, obj=None):
        """
        Get the partition for an account/container/object.

        :param account: account name
        :param container: container name
        :param obj: object name
        :returns: the partition number
        """
        if account.startswith(reseller_prefix):
            account = account.replace(reseller_prefix, '', 1)

        # Save the account name in the table
        # This makes part be the index of the location of the account
        # in the list
        try:
            part = self.account_list.index(account)
        except ValueError:
            self.account_list.append(account)
            part = self.account_list.index(account)

        return part

    def get_nodes(self, account, container=None, obj=None):
        """
        Get the partition and nodes for an account/container/object.
        If a node is responsible for more than one replica, it will
        only appear in the output once.
        :param account: account name
        :param container: container name
        :param obj: object name
        :returns: a tuple of (partition, list of node dicts)

        Each node dict will have at least the following keys:
        ======  ===============================================================
        id      unique integer identifier amongst devices
        weight  a float of the relative weight of this device as compared to
                others; this indicates how many partitions the builder will try
                to assign to this device
        zone    integer indicating which zone the device is in; a given
                partition will not be assigned to multiple devices within the
                same zone
        ip      the ip address of the device
        port    the tcp port of the device
        device  the device's name on disk (sdb1, for example)
        meta    general use 'extra' field; for example: the online date, the
                hardware description
        ======  ===============================================================
        """
        part = self.get_part(account, container, obj)
        return part, self._get_part_nodes(part)

    def get_more_nodes(self, part):
        """
        Generator to get extra nodes for a partition for hinted handoff.

        :param part: partition to get handoff nodes for
        :returns: generator of node dicts

        See :func:`get_nodes` for a description of the node dicts.
        Should never be called in the swift UFO environment, so yield nothing
        """
        return []
