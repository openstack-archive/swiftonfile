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
import unittest
import gluster.swift.common.constraints
import swift.common.utils
from gluster.swift.common.ring import Ring


class TestRing(unittest.TestCase):
    """ Tests for common.ring """

    def setUp(self):
        swift.common.utils.HASH_PATH_SUFFIX = 'endcap'
        swiftdir = os.path.join(os.getcwd(), "common", "data")
        self.ring = Ring(swiftdir, ring_name='object')

    def test_first_device(self):
        part, node = self.ring.get_nodes('test')
        assert node[0]['device'] == 'test'
        node = self.ring.get_part_nodes(0)
        assert node[0]['device'] == 'test'
        for node in self.ring.get_more_nodes(0):
            assert node['device'] == 'volume_not_in_ring'

    def test_invalid_device(self):
        part, node = self.ring.get_nodes('test2')
        assert node[0]['device'] == 'volume_not_in_ring'
        node = self.ring.get_part_nodes(0)
        assert node[0]['device'] == 'volume_not_in_ring'

    def test_second_device(self):
        part, node = self.ring.get_nodes('iops')
        assert node[0]['device'] == 'iops'
        node = self.ring.get_part_nodes(0)
        assert node[0]['device'] == 'iops'
        for node in self.ring.get_more_nodes(0):
            assert node['device'] == 'volume_not_in_ring'

    def test_second_device_with_reseller_prefix(self):
        part, node = self.ring.get_nodes('AUTH_iops')
        assert node[0]['device'] == 'iops'

    def test_partition_id_for_multiple_accounts(self):
        test_part, test_node = self.ring.get_nodes('test')
        iops_part, iops_node = self.ring.get_nodes('iops')
        self.assertNotEqual(test_part, iops_part)
        self.assertEqual(test_node, self.ring.get_part_nodes(test_part))
        self.assertEqual(iops_node, self.ring.get_part_nodes(iops_part))
        self.assertNotEqual(test_node, self.ring.get_part_nodes(iops_part))
        self.assertNotEqual(iops_node, self.ring.get_part_nodes(test_part))

    def test_invalid_partition(self):
        nodes = self.ring.get_part_nodes(0)
        self.assertEqual(nodes[0]['device'], 'volume_not_in_ring')

    def test_ring_file_enoent(self):
        swiftdir = os.path.join(os.getcwd(), "common", "data")
        try:
            self.ring = Ring(swiftdir, ring_name='obj')
        except OSError as ose:
            if ose.errno == errno.ENOENT:
                pass
            else:
                self.fail('ENOENT expected, %s received.' %ose.errno)
        else:
            self.fail('OSError expected.')
