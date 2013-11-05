#!/bin/bash

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

# This program expects to be run by tox in a virtual python environment
# so that it does not pollute the host development system

sudo_env()
{
    sudo bash -c "PATH=$PATH $*"
}

cleanup()
{
        sudo service memcached stop
        sudo_env swift-init main stop
        sudo rm -rf /etc/swift > /dev/null 2>&1
        sudo rm -rf /mnt/gluster-object/test{,2}/* > /dev/null 2>&1
        sudo setfattr -x user.swift.metadata /mnt/gluster-object/test{,2} > /dev/null 2>&1
        gswauth_cleanup
}

gswauth_cleanup()
{
        sudo rm -rf /mnt/gluster-object/gsmetadata/.* > /dev/null 2>&1
        sudo rm -rf /mnt/gluster-object/gsmetadata/* > /dev/null 2>&1
        sudo setfattr -x user.swift.metadata /mnt/gluster-object/gsmetadata > /dev/null 2>&1
}

quit()
{
        echo "$1"
        exit 1
}


fail()
{
        cleanup
	quit "$1"
}

run_generic_tests()
{
    # clean up gsmetadata dir
    gswauth_cleanup

    #swauth-prep
    sudo_env swauth-prep -K gswauthkey || fail "Unable to prep gswauth"
    sudo_env swauth-add-user -K gswauthkey -a test tester testing || fail "Unable to add user test"
    sudo_env swauth-add-user -K gswauthkey -a test2 tester2 testing2 || fail "Unable to add user test2"
    sudo_env swauth-add-user -K gswauthkey test tester3 testing3 || fail "Unable to add user test3"

    nosetests -v --exe \
        --with-xunit \
        --xunit-file functional_tests/gluster-swift-gswauth-generic-functional-TC-report.xml \
        --with-html-output \
        --html-out-file functional_tests/gluster-swift-gswauth-generic-functional-result.html \
        test/functional || fail "Functional tests failed"
    nosetests -v --exe \
        --with-xunit \
        --xunit-file functional_tests/gluster-swift-gswauth-functionalnosetests-TC-report.xml \
        --with-html-output \
        --html-out-file functional_tests/gluster-swift-gswauth-functionalnosetests-result.html \
        test/functionalnosetests || fail "Functional-nose tests failed"
}

### MAIN ###

# Only run if there is no configuration in the system
if [ -x /etc/swift ] ; then
	quit "/etc/swift exists, cannot run functional tests."
fi

# Check the directories exist
DIRS="/mnt/gluster-object /mnt/gluster-object/test /mnt/gluster-object/test2 /mnt/gluster-object/gsmetadata"
for d in $DIRS ; do
	if [ ! -x $d ] ; then
		quit "$d must exist on an XFS or GlusterFS volume"
	fi
done

export SWIFT_TEST_CONFIG_FILE=/etc/swift/test.conf

# Install the configuration files
sudo mkdir /etc/swift > /dev/null 2>&1
sudo cp -r test/functional_auth/gswauth/conf/* /etc/swift || fail "Unable to copy configuration files to /etc/swift"
sudo_env gluster-swift-gen-builders test test2 gsmetadata || fail "Unable to create ring files"

# Start the services
sudo service memcached start || fail "Unable to start memcached"
sudo_env swift-init main start || fail "Unable to start swift"

#swauth-prep
sudo_env swauth-prep -K gswauthkey || fail "Unable to prep gswauth"

mkdir functional_tests > /dev/null 2>&1
nosetests -v --exe \
	--with-xunit \
	--xunit-file functional_tests/gluster-swift-gswauth-functional-TC-report.xml \
    --with-html-output \
    --html-out-file functional_tests/gluster-swift-gswauth-functional-result.html \
    test/functional_auth/gswauth || fail "Functional gswauth test failed"

run_generic_tests

cleanup
exit 0
