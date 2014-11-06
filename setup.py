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

from setuptools import setup, find_packages
from gluster.swift import _pkginfo


setup(
    name=_pkginfo.name,
    version=_pkginfo.full_version,
    description='Gluster For Swift',
    license='Apache License (2.0)',
    author='Red Hat, Inc.',
    author_email='gluster-users@gluster.org',
    url='http://launchpad.net/gluster-swift',
    packages=find_packages(exclude=['test', 'bin']),
    test_suite='nose.collector',
    classifiers=[
        'Development Status :: 5 - Production/Stable'
        'Environment :: OpenStack'
        'Intended Audience :: Information Technology'
        'Intended Audience :: System Administrators'
        'License :: OSI Approved :: Apache Software License'
        'Operating System :: POSIX :: Linux'
        'Programming Language :: Python'
        'Programming Language :: Python :: 2'
        'Programming Language :: Python :: 2.6'
        'Programming Language :: Python :: 2.7'
    ],
    install_requires=[],
    scripts=[
        'bin/gluster-swift-gen-builders',
        'bin/gluster-swift-print-metadata',
        'gluster/swift/common/middleware/gswauth/bin/gswauth-add-account',
        'gluster/swift/common/middleware/gswauth/bin/gswauth-add-user',
        'gluster/swift/common/middleware/gswauth/bin/gswauth-cleanup-tokens',
        'gluster/swift/common/middleware/gswauth/bin/gswauth-delete-account',
        'gluster/swift/common/middleware/gswauth/bin/gswauth-delete-user',
        'gluster/swift/common/middleware/gswauth/bin/gswauth-list',
        'gluster/swift/common/middleware/gswauth/bin/gswauth-prep',
        'gluster/swift/common/middleware/gswauth/bin/'
        'gswauth-set-account-service',

    ],
    entry_points={
        'paste.app_factory': [
            'proxy=gluster.swift.proxy.server:app_factory',
            'object=gluster.swift.obj.server:app_factory',
            'container=gluster.swift.container.server:app_factory',
            'account=gluster.swift.account.server:app_factory',
        ],
        'paste.filter_factory': [
            'gswauth=gluster.swift.common.middleware.gswauth.swauth.'
            'middleware:filter_factory',
        ],
    },
)
