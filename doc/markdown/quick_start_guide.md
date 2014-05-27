# Quick Start Guide

## Contents
* [Overview](#overview)
* [System Setup](#system_setup)
* [SwiftOnFile Setup](#swift_setup)
* [Using SwiftOnFile](#using_swift)
* [What now?](#what_now)

<a name="overview" />
## Overview
SwiftOnFile allows any POSIX complaint filesystem to be used as the 
backend to the object store OpenStack Swift.

The following guide will get you quickly started with a SwiftOnFile
environment on a Fedora or RHEL/CentOS system.  This guide is a
great way to begin using SwiftOnFile, and can be easily deployed on
a single virtual machine. The final result will be a single SwiftOnFile
node.

> NOTE: In SwiftOnFile a swift account is a mounted FS under path mentioned 
in configuration parameter.It is assumed you have two xattrr supporting FS mounted
under certain paths.We suggest you to start with two xfs formatted FS then you can 
move on to other FS that supports xattr.For setting up gluster volume in particular
you can look here [GlusterFS Quick Start Guide][]

<a name="system_setup" />
## System Setup

### Prerequisites on CentOS/RHEL
On CentOS/RHEL you may need to EPEL repo.Please refer to 
[EPEL][] for more information on how to setup the EPEL repo.

SwiftOnfile requires corresponding OpenStack Swift release packages.There are two 
possible ways to get OpenStack Swift packages.

1. Get & build the OpenStack swift source from github.(This should work for all linux flavors)

	a.) Git clone the required branch (assume icehouse)
	~~~
	git clone -b icehouse-stable https://github.com/openstack/swift.git 
	~~~
	b.)Install the prerequisite 
	~~~
	python-pip install -r requirements.txt
	python-pip install -r test-requirements.txt
	~~~ 
	c.)Install the packages 
	~~~
	python setup.py install
	~~~
	d.) Please refer to the OpenStack swift SAIO guide, 
	if you face any difficulty in doing above.

2. Use the Stable RDO release (Fedora/RHEL/CentOS)

	a.) Please setup corresponding Red Hat RDO release repo (assume icehouse)
	~~~
	yum install -y http://repos.fedorapeople.org/repos/openstack/openstack-icehouse/rdo-release-icehouse-3.noarch.rpm 
	~~~
	b.) Install required rpms:
	~~~
	yum install -y openstack-swift-proxy openstack-swift-account openstack-swift-container\
	openstack-swift-object memcached python-swiftclient python-keystoneclient 
	~~~

### Install SwiftOnFile

1. Install from source

	a.) Git clone the required branch (assume icehouse)
	~~~
        git clone -b icehouse https://github.com/swiftonfile/swiftonfile.git
        ~~~
	b.)Install the prerequisite
	~~~
	python-pip install -r requirements.txt
	python-pip install -r test-requirements.txt
	~~~
	c.)Install the packages
	~~~
	python setup.py install
	~~~

2. Using RPMs

	a.) Download the rpms from [Jenkins CI][]
	
	b.)Install the RPM by executing the following:
	~~~
	yum install -y <path to RPM>
	~~~

### Enabling Swift Service available accross reboots
~~~
chkconfig openstack-swift-proxy on
chkconfig openstack-swift-account on
chkconfig openstack-swift-container on
chkconfig openstack-swift-object on
~~~

#### Fedora 19 Adjustment
Currently SwiftOnFile requires its processes to be run as `root`. You need to
edit the `openstack-swift-*.service` files in
`/etc/systemd/system/multi-user.target.wants` and change the `User` entry value
to `root`.

Then run the following command to reload the configuration:

~~~
systemctl --system daemon-reload
~~~

### Configuration
As with OpenStack Swift, SwiftOnFile uses `/etc/swift` as the
directory containing the configuration files.  You will need to base
the configuration files on the template files provided. On new RPM based
installations, the simplest way is to copy the `*.conf-gluster`
files to `*.conf` files as follows:

~~~
cd /etc/swift
for tmpl in *.conf-gluster ; do cp ${tmpl} ${tmpl%.*}.conf; done
~~~

Else you can base your config files on [test code ][].

#### Generate Ring Files
You now need to generate the ring files, which inform SwiftOnFile
which FS volumes are accessible over the object storage interface.
This is a borrowed legacy from gluster-swift and it will soon change.
This script uses OpenStack Swift ring builder with the fundamental 
assumption that the replication/sync/HA/etc are provided by underlying FS
(gluster in this case).The format is

~~~
gluster-swift-gen-builders [mount-point-name] [mount-point-name...]
~~~

Where *mount-point-name* is the name of the a directory in the path mentioned in
/etc/swift{account,object,container}.conf under the section [DEFAULT]
for parameter 'devices'.For ex: If 'device' parameter has the value '/mnt/FS-objects'
and you mounted two gluster/xfs volumes on /mnt/FS-objects/gfs-vol1 & 
/mnt/FS-objects/gfs-vol2 then the command would look like this:
~~~
gluster-swift-gen-builders gfs-vol1 gfs-vol2
~~~

### Start swift services using the following commands:

~~~
service openstack-swift-object start
service openstack-swift-container start
service openstack-swift-account start
service openstack-swift-proxy start
~~~

Or using
~~~
swift-init main start
~~~

<a name="using_swift" />
## Using SwiftOnFile

### Create a container
Create a container using the following command:

~~~
curl -v -X PUT http://localhost:8080/v1/AUTH_gfs-vol1/mycontainer
~~~

It should return `HTTP/1.1 201 Created` on a successful creation. You can
also confirm that the container has been created by inspecting the FS:

~~~
ls /mnt/FS-object/gfs-vol1
~~~

#### Create an object
You can now place an object in the container you have just created:

~~~
echo "Hello World" > mytestfile
curl -v -X PUT -T mytestfile http://localhost:8080/v1/AUTH_gfs-vol1/mycontainer/mytestfile
~~~

To confirm that the object has been written correctly, you can compare the
test file with the object you created:

~~~
cat /mnt/FS-object/gfs-vol1/mycontainer/mytestfile
~~~

#### Request the object
Now you can retreive the object and inspect its contents using the
following commands:

~~~
curl -v -X GET -o newfile http://localhost:8080/v1/AUTH_gfs-vol1/mycontainer/mytestfile
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
[test code] : https://github.com/swiftonfile/swiftonfile/tree/master/test/functional_auth/tempauth/conf/
