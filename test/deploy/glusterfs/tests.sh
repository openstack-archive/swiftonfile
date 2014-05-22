#!/bin/bash

# Copyright (c) 2014 Red Hat, Inc.
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

# This program expects to be run against a locally deployed swiftonfile
# applicatoin.  This tests also expects three glusterfs volumes to have
# been created: 'test', 'test2', and 'gsmetadata'.

cleanup()
{
    service memcached stop
    swift-init main stop
    if [ -x /etc/swift.bak ] ; then
        rm -rf /etc/swift > /dev/null 2>&1
        mv /etc/swift.bak /etc/swift > /dev/null 2>&1
    fi
    rm -rf /mnt/gluster-object/test{,2}/* > /dev/null 2>&1
    setfattr -x user.swift.metadata /mnt/gluster-object/test{,2} > /dev/null 2>&1
    gswauth_cleanup
}

gswauth_cleanup()
{
    rm -rf /mnt/gluster-object/gsmetadata/.* > /dev/null 2>&1
    rm -rf /mnt/gluster-object/gsmetadata/* > /dev/null 2>&1
    setfattr -x user.swift.metadata /mnt/gluster-object/gsmetadata > /dev/null 2>&1
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
    gswauth-prep -K gswauthkey || fail "Unable to prep gswauth"
    gswauth-add-user -K gswauthkey -a test tester testing || fail "Unable to add user test"
    gswauth-add-user -K gswauthkey -a test2 tester2 testing2 || fail "Unable to add user test2"
    gswauth-add-user -K gswauthkey test tester3 testing3 || fail "Unable to add user test3"

    nosetests -v --exe \
        --with-xunit \
        --xunit-file functional_tests/gluster-swift-gswauth-generic-functional-TC-report.xml \
        test/functional || fail "Functional tests failed"
    nosetests -v --exe \
        --with-xunit \
        --xunit-file functional_tests/gluster-swift-gswauth-functionalnosetests-TC-report.xml \
        test/functionalnosetests || fail "Functional-nose tests failed"
}

### MAIN ###

# Backup the swift directory if it already exists
if [ -x /etc/swift ] ; then
    mv /etc/swift /etc/swift.bak
fi

export SWIFT_TEST_CONFIG_FILE=/etc/swift/test.conf

# Install the configuration files
mkdir /etc/swift > /dev/null 2>&1
cp -r test/deploy/glusterfs/conf/* /etc/swift || fail "Unable to copy configuration files to /etc/swift"
gluster-swift-gen-builders test test2 gsmetadata || fail "Unable to create ring files"

# Start the services
service memcached start || fail "Unable to start memcached"
swift-init main start || fail "Unable to start swift"

#swauth-prep
gswauth-prep -K gswauthkey || fail "Unable to prep gswauth"

mkdir functional_tests > /dev/null 2>&1
nosetests -v --exe \
    --with-xunit \
    --xunit-file functional_tests/gluster-swift-gswauth-functional-TC-report.xml \
    test/functional_auth/gswauth || fail "Functional gswauth test failed"

run_generic_tests

cleanup
exit 0
