# Quick Start Guide

## Contents
* [Overview](#overview)
* [System Setup](#system_setup)
* [SwiftOnFile Setup](#swift_setup)
* [Using SwiftOnFile](#using_swift)
* [What now?](#what_now)

<a name="overview" />
## Overview
SwiftOnFile allows any POSIX complaint filesystem to be used as the backend to the object store OpenStack Swift.

The following guide assumes you have a running [OpenStack Swift SAIO setup][], and you want to extend this setup to try SwiftOnFile as Storage Policy on a XFS/gluster volume. This   will get you quickly started with a SwiftOnFile environment on a Fedora or RHEL/CentOS system. 

This guide will not go on detail on how to prepare a Swift SAIO setup or how to create a gluster volume (or other FS).This guide assumes you know about these technologies, if you require any help in setting those please refer to the link provided.

<a name="system_setup" />
## System Setup

### Prerequisites on CentOS/RHEL

1. OpenStack SAIO deployment on Fedora20 onwards 
2. One xfs/glusterfs volume - named vol

>Note: Swift SAIO deployment should contain Storage Policy code changes. Initialy Storage Policy feature was developed seprately in openstack swift feature/ec branch, and it is now merged in master branch. The latest OpenStack Swift2.0 release also contain storage policy code.

Each xfs/glusterfs volume will be defined as a separate storage policy. 

### Install SwiftOnfile
1. Before you begin swiftonfile setup please ensure you have OpenStack Swift SAIO setup up & running. Please refer to the SAIO guide for this.
2. cd ~; git clone https://github.com/swiftonfile/swiftonfile.git
3. cd ~/swiftonfile;python setup.py develop;cd ~

### Configure SwiftOnFile as Storage Policy

#### Object Server Configuration
A SAIO setup mimic a four node swift setup and should have four object server running.Add another object server for SwiftOnFile by setting the following configurations in the file /etc/swift/object-server/5.conf:

~~~
[DEFAULT]
devices = /mnt/xfsvols/
mount_check = false
bind_port = 6050
max_clients = 1024
workers = 1
disable_fallocate = true

[pipeline:main]
pipeline = object-server

[app:object-server]
use = egg:gluster_swift#object
user = root
log_facility = LOG_LOCAL2
log_level = DEBUG
log_requests = on
disk_chunk_size = 65536
~~~
>Note: The parameter 'devices' tells about the path where your xfs/glusterfs volume is mounted. The sub directory under which your volume is mounted will be called volume name. For ex: You have a xfs formated partition /dev/sdb1, and you mounted it under /mnt/xfsvols/vol, then your volume name would be 'vol'& and the parameter 'devices' would contain value '/mnt/xfsvols'.

#### Setting SwiftOnFile as storage policy
Edit /etc/swift.conf to add swiftonfile as a storage policy:

~~~
[storage-policy:0]
name = swift
default = yes

[storage-policy:1]
name = swiftonfile-test
~~~
You can also make "swiftonfile-test" the default storage policy by using the 'default' parameter.

#### Prepare rings
Edit the remakerings script to prepare rings for this new storage policy:

~~~
swift-ring-builder object-1.builder create 1 1 1
swift-ring-builder object-1.builder add r1z1-127.0.0.1:6050/vol 1
swift-ring-builder object-1.builder rebalance
~~~
Execute the remakerings script to prepare new rings files.
In a SAIO setup remakerings scipt is usually situated at ~/bin/remakerings.It you can also run above rings builder commands manually.

Notice the mapping between SP index (1) defined in conf file above and the object ring builder command.

#### Load the new configurations
Restart swift services to reflect new changes:

~~~
swift-init all restart
~~~


<a name="using_swift" />

#### Running functional tests
TBD

## Using SwiftOnFile
It is assumed that you are still using 'tempauth' as authnetication method, which is default in SAIO deployment.

#### Get the token
~~~
curl -v -H 'X-Auth-User: test:tester' -H "X-Auth-key: testing" -k http://localhost:8080/auth/v1.0
~~~
Use 'X-Auth-Token' & 'X-Storage-Url' returned in above request for all sucequent request.

#### Create a container
Create a container using the following command:

~~~
curl -v -X PUT -H 'X-Auth-Token: AUTH_XXXX' -H 'X-Storage-Policy: swiftonfile-test' http://localhost:8080/v1/AUTH_test/mycontainer
~~~

It should return `HTTP/1.1 201 Created` on a successful creation. 

#### Create an object
You can now place an object in the container you have just created:

~~~
echo "Hello World" > mytestfile
curl -v -X PUT -T mytestfile 'X-Auth-Token: AUTH_XXXX' http://localhost:8080/v1/AUTH_test/mycontainer/mytestfile
~~~

To confirm that the object has been written correctly, you can compare the
test file with the object you created:

~~~
cat /mnt/xfsvols/vol/test/mycontainer/mytestfile
~~~

#### Request the object
Now you can retreive the object and inspect its contents using the
following commands:

~~~
curl -v -X GET -o newfile http://localhost:8080/v1/AUTH_test/mycontainer/mytestfile
cat newfile
~~~

You can also use etag information provided while you do HEAD on object 
and compare it with md5sum of the file on your FS. 

<a name="what_now" />
## What now?
For more information, please visit the following links:

* [Authentication Services Start Guide][]
* [GlusterFS Quick Start Guide][]
* [OpenStack Swift API][]

[GlusterFS Quick Start Guide]: http://www.gluster.org/community/documentation/index.php/QuickStart
[OpenStack Swift API]: http://docs.openstack.org/api/openstack-object-storage/1.0/content/
[Jenkins]: http://jenkins-ci.org
[Authentication Services Start Guide]: auth_guide.md
[EPEL]: https://fedoraproject.org/wiki/EPEL
[Jenkins CI]: http://build.gluster.org/job/swiftonfile-builds/lastSuccessfulBuild/artifact/build/
[test code]: https://github.com/swiftonfile/swiftonfile/tree/master/test/functional_auth/tempauth/conf/
[OpenStack Swift SAIO setup]: http://docs.openstack.org/developer/swift/development_saio.html
