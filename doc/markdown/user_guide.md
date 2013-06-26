# User Guide

## Installation

### GlusterFS Installation
First, we need to install GlusterFS on the system by following the
instructions on [GlusterFS QuickStart Guide][].

### Fedora/RHEL/CentOS
Gluster for Swift depends on OpenStack Swift Grizzly, which can be
obtained by using [RedHat's RDO][] packages as follows:

~~~
yum install -y http://rdo.fedorapeople.org/openstack/openstack-grizzly/rdo-release-grizzly.rpm
~~~

### Download
Gluster for Swift uses [Jenkins][] for continuous integration and
creation of distribution builds.  Download the latest RPM builds
from one of the links below:  

* RHEL/CentOS 6: [Download](http://build.gluster.org/job/gluster-swift-builds-cent6/lastSuccessfulBuild/artifact/build/) 
* Fedora 18+: [Download](http://build.gluster.org/job/gluster-swift-builds-f18/lastSuccessfulBuild/artifact/build/)

Install the downloaded RPM using the following command:

~~~
yum install -y RPMFILE
~~~

where *RPMFILE* is the RPM file downloaded from Jenkins.

## Configuration
TBD

## Server Control
Command to start the servers (TBD)

~~~
swift-init main start
~~~

Command to stop the servers (TBD)

~~~
swift-init main stop
~~~

Command to gracefully reload the servers

~~~
swift-init main reload
~~~

### Mounting your volumes
TBD

Once this is done, you can access GlusterFS volumes via the Swift API where
accounts are mounted volumes, containers are top-level directories,
and objects are files and sub-directories of container directories.



[GlusterFS QuickStart Guide]: http://www.gluster.org/community/documentation/index.php/QuickStart
[RedHat's RDO]: http://openstack.redhat.com/Quickstart
[Jenkins]: http://jenkins-ci.org
