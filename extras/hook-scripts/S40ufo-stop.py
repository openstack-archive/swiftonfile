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


from optparse import OptionParser

if __name__ == '__main__':
    # check if swift is installed
    try:
        from gluster.swift.common.Glusterfs import get_mnt_point, unmount
    except ImportError:
        import sys
        sys.exit("Openstack Swift does not appear to be installed properly")

    op = OptionParser(usage="%prog [options...]")
    op.add_option('--volname', dest='vol', type=str)
    op.add_option('--last', dest='last', type=str)
    (opts, args) = op.parse_args()

    mnt_point = get_mnt_point(opts.vol)
    if mnt_point:
        unmount(mnt_point)
    else:
        sys.exit("get_mnt_point returned none for mount point")
