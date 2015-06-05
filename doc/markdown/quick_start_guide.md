# Quick Start Guide

## Contents
* [Overview](#overview)
* [System Setup](#system_setup)
* [SwiftOnFile Setup](#swift_setup)
* [Using SwiftOnFile](#using_swift)
* [What now?](#what_now)

<a name="overview" />
## Overview
SwiftOnFile allows any POSIX compliant filesystem (which supports extended attributes) to be used as the backend to OpenStack Swift (Object Store).

The following guide assumes you have a running [OpenStack Swift SAIO setup][], and you want to extend this setup to try SwiftOnFile as Storage Policy with an XFS partition or GlusterFS volume. This will get you quickly started with a SwiftOnFile deployment on a Fedora or RHEL/CentOS system. 

This guide will not provide detailed information on how to prepare a SAIO setup or how to create a gluster volume (or other FS).This guide assumes you know about these technologies; if you require any help in setting those please refer to the links provided.

<a name="system_setup" />
## System Setup

### Prerequisites on CentOS/RHEL

1. SAIO deployment (this guide uses SAIO on Fedora 20) running Swift 2.0 or newer versions
1. One XFS partition/GlusterFS volume mounted as `/mnt/swiftonfile`

>Note: Each XFS partition/GlusterFS volume will be defined as a separate storage policy. 

### Install SwiftOnfile

1. `cd $HOME; git clone https://github.com/swiftonfile/swiftonfile.git`
1. `cd $HOME/swiftonfile; python setup.py develop; cd $HOME`
 
### Configure SwiftOnFile as Storage Policy

#### Object Server Configuration
An SAIO setup emulates a four node swift setup and should have four object server running. Add another object server for SwiftOnFile DiskFile API implementation by setting the following configurations in the file /etc/swift/object-server/5.conf:

~~~
[DEFAULT]
devices = /mnt/swiftonfile
mount_check = false
bind_port = 6050
max_clients = 1024
workers = 1
disable_fallocate = true

[pipeline:main]
pipeline = object-server

[app:object-server]
use = egg:swiftonfile#object
user = <your-user-name>
log_facility = LOG_LOCAL2
log_level = DEBUG
log_requests = on
disk_chunk_size = 65536
~~~
>Note: The parameter 'devices' tells about the path where your xfs partition or glusterfs volume is mounted. The sub directory under which your xfs partition or glusterfs volume is mounted will be called device name. 

>For example: You have a xfs formated partition /dev/sdb1, and you mounted it under /mnt/swiftonfile/vol, then your device name would be 'vol' & and the parameter 'devices' would contain value '/mnt/swiftonfile'.

#### Setting SwiftOnFile as storage policy
Edit /etc/swift.conf to add swiftonfile as a storage policy:

~~~
[storage-policy:0]
name = gold
default = yes

[storage-policy:1]
name = silver

[storage-policy:2]
name = swiftonfile
~~~
You can also make "swiftonfile" the default storage policy by using the 'default' parameter.

#### Prepare rings
Edit the remakerings script to prepare rings for this new storage policy:

~~~
swift-ring-builder object-2.builder create 1 1 1
swift-ring-builder object-2.builder add r1z1-127.0.0.1:6050/vol 1
swift-ring-builder object-2.builder rebalance
~~~
Execute the remakerings script to prepare new rings files.
In a SAIO setup remakerings scipt is usually situated at ~/bin/remakerings.You can also run above rings builder commands manually.

Notice the mapping between SP index (`2`) defined in `swift.conf` file above and the object ring builder command.

#### Load the new configurations
Restart swift services to reflect new changes:

~~~
swift-init main restart
~~~


<a name="using_swift" />

## Using SwiftOnFile
It is assumed that you are still using 'tempauth' as authentication method, which is default in SAIO deployment.

#### Get the token
~~~
curl -v -H 'X-Auth-User: test:tester' -H "X-Auth-key: testing" -k http://localhost:8080/auth/v1.0
~~~
Use 'X-Auth-Token' & 'X-Storage-Url' returned in above request for all subsequent requests.

#### Create a container
Create a container using the following command:

~~~
curl -v -X PUT -H 'X-Auth-Token: AUTH_XXXX' -H 'X-Storage-Policy: swiftonfile' http://localhost:8080/v1/AUTH_test/mycontainer
~~~

It should return `HTTP/1.1 201 Created` on a successful creation. 

#### Create an object
You can now place an object in the container you have just created:

~~~
echo "Hello World" > mytestfile
curl -v -X PUT -T mytestfile -H 'X-Auth-Token: AUTH_XXXX' http://localhost:8080/v1/AUTH_test/mycontainer/mytestfile
~~~

To confirm that the object has been written correctly, you can compare the
test file with the object you created:

~~~
cat /mnt/swiftonfile/vol/AUTH_test/mycontainer/mytestfile
~~~

#### Request the object
Now you can retreive the object and inspect its contents using the
following commands:

~~~
curl -v -X GET -o newfile -H 'X-Auth-Token: AUTH_XXXX' http://localhost:8080/v1/AUTH_test/mycontainer/mytestfile
cat newfile
~~~

You can also use etag information provided while you do HEAD on object 
and compare it with md5sum of the file on your filesystem. 

<a name="what_now" />
## What now?
You now have a single node SwiftOnFile setup ready, next sane step is a multinode swift and SwiftOnFile setup. It is recomended to have a look at [OpenStack Swift deployment guide][] & [Multiple Server Swift Installation][].If you now consider yourself familiar with a typical 4-5 node swift setup, you are good to extent this setup further and add SwiftOnFile DiskFile implementation as a Storage Policy to it. If you want to use SwiftOnFile on a gluster volume, it would be good to have a seprate gluster cluster. We would love to hear about any deployment scenarios involving SOF.
    
For more information, please visit the following links:
* [OpenStack Swift deployment guide][]
* [Multiple Server Swift Installation][]
* [OpenStack Swift Storage Policy][]
* [GlusterFS Quick Start Guide][]
* [OpenStack Swift API][]

[GlusterFS Quick Start Guide]: http://www.gluster.org/community/documentation/index.php/QuickStart
[OpenStack Swift API]: http://docs.openstack.org/api/openstack-object-storage/1.0/content/
[OpenStack Swift Storage Policy]: http://docs.openstack.org/developer/swift/overview_policies.html
[OpenStack Swift SAIO setup]: http://docs.openstack.org/developer/swift/development_saio.html
[OpenStack Swift deployment guide]: http://docs.openstack.org/developer/swift/deployment_guide.html
[Multiple Server Swift Installation]: http://docs.openstack.org/developer/swift/howto_installmultinode.html
