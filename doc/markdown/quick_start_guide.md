# Quick Start Guide

## Contents
* [Overview](#overview)
* [System Setup](#system_setup)
* [Gluster For Swift Setup](#swift_setup)
* [Using Gluster for Swift](#using_swift)
* [What now?](#what_now)

<a name="overview" />
## Overview
Gluster-swift allows GlusterFS to be used as the backend to the object
store OpenStack Swift.

The following guide will get you quickly started with a gluster-swift
environment on a Fedora or RHEL/CentOS system.  This guide is a
great way to begin using gluster-swift, and can be easily deployed on
a single virtual machine. The final result will be a single gluster-swift
node.

> NOTE: In Gluster-Swift, accounts must be GlusterFS volumes.

<a name="system_setup" />
## System Setup

### Prerequisites on CentOS/RHEL
On CentOS/RHEL you will need to setup GlusterFS and EPEL repos.

#### GlusterFS CentOS/RHEL Repo

* CentOS

~~~
wget -O /etc/yum.repos.d/glusterfs-epel.repo \
  http://download.gluster.org/pub/gluster/glusterfs/LATEST/CentOS/glusterfs-epel.repo
~~~

* RHEL

~~~
wget -O /etc/yum.repos.d/glusterfs-epel.repo \
  http://download.gluster.org/pub/gluster/glusterfs/LATEST/RHEL/glusterfs-epel.repo
~~~

#### EPEL CentOS/RHEL Repo
Please refer to [EPEL][] for more information on how to setup the EPEL repo.

### Required Package Installation
Install and start the required packages on your system to create a GlusterFS volume.

~~~
yum install glusterfs glusterfs-server glusterfs-fuse memcached xfsprogs
~~~

#### Start services

Type the following to start `memcached` and `glusterfs` services:

~~~
service memcached start
service glusterd start
~~~

Type the following to start the services automatically on system startup:

~~~
chkconfig memcached on
chkconfig glusterd on
~~~

### Gluster Volume Setup
Now you need to determine whether you are going to use a partition or a loopback device
for storage.

#### Partition Storage Setup
If you are using a separate disk partition, please execute the following instructions
to create a GlusterFS brick:

~~~
mkfs.xfs -i size=512 /dev/<disk partition>
mkdir -p /export/brick
~~~

Add the following line to `/etc/fstab` to mount the storage automatically on system
startup:

~~~
/dev/<disk partition>   /export/brick   xfs   inode64,noatime,nodiratime 0 0
~~~

Now type the following to mount the storage:

~~~
mount -a
~~~

#### Loopback Storage Setup
If you do not have a separate partition, please execute the following instructions
to create a disk image as a file:

~~~
truncate -s 5GB /srv/swift-disk
mkfs.xfs -i size=512 /srv/swift-disk
mkdir -p /export/brick
~~~

Add the following line to `/etc/fstab` to mount the storage automatically on system
startup:

~~~
/srv/swift-disk /export/brick   xfs   loop,inode64,noatime,nodiratime 0 0
~~~

Now type the following to mount the storage:

~~~
mount -a
~~~

### Create a GlusterFS Volume
You now need to create a GlusterFS volume

~~~
mkdir /export/brick/b1
gluster volume create myvolume `hostname`:/export/brick/b1
gluster volume start myvolume
~~~

<a name="swift_setup" />
## Gluster-Swift Setup

### Repository Setup on RHEL/CentOS
Gluster-Swift requires OpenStack Swift's Havana release, which
may not be available on some older operating systems. For RHEL/CentOS
systems, please setup Red Hat RDO's repo by executing the following command:

~~~
yum install -y http://rdo.fedorapeople.org/rdo-release.rpm
~~~

### Download
Download the latest Havana release RPMs from [launchpad.net downloads][]:

### Install
Install the RPM by executing the following:

~~~
yum install -y <path to RPM>
~~~

### Enabling gluster-swift accross reboots
Type the following to make sure gluster-swift is enabled at
system startup:

~~~
chkconfig openstack-swift-proxy on
chkconfig openstack-swift-account on
chkconfig openstack-swift-container on
chkconfig openstack-swift-object on
~~~

#### Fedora 19 Adjustment
Currently gluster-swift requires its processes to be run as `root`. You need to
edit the `openstack-swift-*.service` files in
`/etc/systemd/system/multi-user.target.wants` and change the `User` entry value
to `root`.

Then run the following command to reload the configuration:

~~~
systemctl --system daemon-reload
~~~

### Configuration
As with OpenStack Swift, gluster-swift uses `/etc/swift` as the
directory containing the configuration files.  You will need to base
the configuration files on the template files provided.  On new
installations, the simplest way is to copy the `*.conf-gluster`
files to `*.conf` files as follows:

~~~
cd /etc/swift
for tmpl in *.conf-gluster ; do cp ${tmpl} ${tmpl%.*}.conf; done
~~~

#### Generate Ring Files
You now need to generate the ring files, which inform gluster-swift
which GlusterFS volumes are accessible over the object
storage interface. The format is

~~~
gluster-swift-gen-builders [VOLUME] [VOLUME...]
~~~

Where *VOLUME* is the name of the GlusterFS volume which you would
like to access over gluster-swift.

Let's now expose the GlusterFS volume called `myvolume` you created above
by executing the following command:

~~~
cd /etc/swift
/usr/bin/gluster-swift-gen-builders myvolume
~~~

### Start gluster-swift
Use the following commands to start gluster-swift:

~~~
service openstack-swift-object start
service openstack-swift-container start
service openstack-swift-account start
service openstack-swift-proxy start
~~~

<a name="using_swift" />
## Using gluster-swift

### Create a container
Create a container using the following command:

~~~
curl -v -X PUT http://localhost:8080/v1/AUTH_myvolume/mycontainer
~~~

It should return `HTTP/1.1 201 Created` on a successful creation. You can
also confirm that the container has been created by inspecting the GlusterFS
volume:

~~~
ls /mnt/gluster-object/myvolume
~~~

#### Create an object
You can now place an object in the container you have just created:

~~~
echo "Hello World" > mytestfile
curl -v -X PUT -T mytestfile http://localhost:8080/v1/AUTH_myvolume/mycontainer/mytestfile
~~~

To confirm that the object has been written correctly, you can compare the
test file with the object you created:

~~~
cat /mnt/gluster-object/myvolume/mycontainer/mytestfile
~~~

#### Request the object
Now you can retreive the object and inspect its contents using the
following commands:

~~~
curl -v -X GET -o newfile http://localhost:8080/v1/AUTH_myvolume/mycontainer/mytestfile
cat newfile
~~~

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
[launchpad.net downloads]: http://launchpad.net/gluster-swift/havana/1.10.0-2

