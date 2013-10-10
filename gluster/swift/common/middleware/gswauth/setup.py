#!/usr/bin/python
# Copyright (c) 2010-2011 OpenStack, LLC.
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
from setuptools.command.sdist import sdist
import os
import subprocess
try:
    from babel.messages import frontend
except ImportError:
    frontend = None

from swauth import __version__ as version


class local_sdist(sdist):
    """Customized sdist hook - builds the ChangeLog file from VC first"""

    def run(self):
        if os.path.isdir('.bzr'):
            # We're in a bzr branch

            log_cmd = subprocess.Popen(["bzr", "log", "--gnu"],
                                       stdout=subprocess.PIPE)
            changelog = log_cmd.communicate()[0]
            with open("ChangeLog", "w") as changelog_file:
                changelog_file.write(changelog)
        sdist.run(self)


name = 'swauth'


cmdclass = {'sdist': local_sdist}


if frontend:
    cmdclass.update({
        'compile_catalog': frontend.compile_catalog,
        'extract_messages': frontend.extract_messages,
        'init_catalog': frontend.init_catalog,
        'update_catalog': frontend.update_catalog,
    })


setup(
    name=name,
    version=version,
    description='Swauth',
    license='Apache License (2.0)',
    author='OpenStack, LLC.',
    author_email='swauth@brim.net',
    url='https://github.com/gholt/swauth',
    packages=find_packages(exclude=['test_swauth', 'bin']),
    test_suite='nose.collector',
    cmdclass=cmdclass,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Environment :: No Input/Output (Daemon)',
        ],
    install_requires=[],  # removed for better compat
    scripts=[
        'bin/swauth-add-account', 'bin/swauth-add-user',
        'bin/swauth-cleanup-tokens', 'bin/swauth-delete-account',
        'bin/swauth-delete-user', 'bin/swauth-list', 'bin/swauth-prep',
        'bin/swauth-set-account-service',
        ],
    entry_points={
        'paste.filter_factory': [
            'swauth=swauth.middleware:filter_factory',
            ],
        },
    )
