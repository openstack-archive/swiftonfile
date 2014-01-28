# Object Expiration

## Contents
* [Overview](#overview)
* [Setup](#setup)
* [Using object expiration](#using)
* [Running object-expirer daemon](#running-daemon)

<a name="overview" />
## Overview
The Object Expiration feature offers **scheduled deletion of objects**. The client would use the *X-Delete-At* or *X-Delete-After* headers during an object PUT or POST and the cluster would automatically quit serving that object at the specified time and would shortly thereafter remove the object from the GlusterFS volume.

Expired objects however do appear in container listings until they are deleted by object-expirer daemon. This behaviour is expected: https://bugs.launchpad.net/swift/+bug/1069849

<a name="setup" />
## Setup
Object expirer uses a seprate account (a GlusterFS volume, for now, until multiple accounts per volume is implemented) named *gsexpiring*. You will have to [create a GlusterFS volume](quick_start_guide.md#gluster-volume-setup) by that name.

Object-expirer uses the */etc/swift/object-expirer.conf* configuration file. Make sure that it exists. If not, you can copy it from */etc* directory of gluster-swift source repo.

<a name="using" />
## Using object expiration

**PUT an object with X-Delete-At header using curl**

~~~
curl -v -X PUT -H 'X-Delete-At: 1392013619' http://127.0.0.1:8080/v1/AUTH_test/container1/object1 -T ./localfile
~~~

**PUT an object with X-Delete-At header using swift client**

~~~
swift --os-auth-token=AUTH_tk99a39aecc3dd4f80b2b1e801d00df846 --os-storage-url=http://127.0.0.1:8080/v1/AUTH_test upload container1 ./localfile --header 'X-Delete-At: 1392013619'
~~~

where *X-Delete-At* header takes a Unix Epoch timestamp in integer. For example, the current time in Epoch notation can be found by running this command:

~~~
date +%s
~~~


**PUT an object with X-Delete-After header using curl**

~~~
curl -v -X PUT -H 'X-Delete-After: 3600' http://127.0.0.1:8080/v1/AUTH_test/container1/object1 -T ./localfile
~~~

**PUT an object with X-Delete-At header using swift client**

~~~
swift --os-auth-token=AUTH_tk99a39aecc3dd4f80b2b1e801d00df846 --os-storage-url=http://127.0.0.1:8080/v1/AUTH_test upload container1 ./localfile --header 'X-Delete-After: 3600'
~~~

where *X-Delete-After* header takes a integer number of seconds, after which the object expires. The proxy server that receives the request will convert this header into an X-Delete-At header using its current time plus the value given.

<a name="running-daemon" />
## Running object-expirer daemon
The object-expirer daemon runs a pass once every X seconds (configurable using *interval* option in config file). For every pass it makes, it queries the *gsexpiring* account for "tracker objects". Based on (timestamp, path) present in name of "tracker objects", object-expirer then deletes the actual object and the corresponding tracker object.


To run object-expirer forever as a daemon:
~~~
swift-init object-expirer start
~~~

To run just once:
~~~
swift-object-expirer -o -v /etc/swift/object-expirer.conf
~~~

**For more information, visit:**
http://docs.openstack.org/developer/swift/overview_expiring_objects.html


