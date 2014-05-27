[![Build Status](https://travis-ci.org/swiftonfile/swiftonfile.svg?branch=master)](https://travis-ci.org/swiftonfile/swiftonfile)

# Swift-On-File
Swift-on-File, formerly called Gluster-Swift, enables files and directories 
created on a Posix filesystem (that supports xattrs) to be accessed as objects 
via the Swift API. 

The main difference from the default Swift Object Server is that Swift-on-File
stores objects following the same path hirearchy as that object's URL.
For example: for an object with URL: https://swift.example.com/v1/acc/cont/obj,
the default Object Server will store the object following the mapping given by
the Ring and and it final storage location and even filename is unknown to the
user (see [Swift Architecture](https://swiftstack.com/openstack-swift/architecture/) for more info).
In the case of SoF. The object will be stored in the configured Filesystem
volume with the same directory structure 'acc/cont/obj'.

## Roadmap
Swift-On-File is in a transition period. The project was recently renamed from
Gluster-Swift to Swift-on-File to better represent its nature of a Swift backend
that supports multiple Posix Filesystems, not just GlusterFS. It is also
transitioning to become a Swift Storage Policy. While Gluster-Swift had to be
deployed as its own cluster, SoF can be deployed as a storage policy on an
existing Swift cluster. This is a tremendous change to the project as it opens
up new possibilities of how SoF can be used.

Our last stable [release](https://github.com/swiftonfile/swiftonfile/releases)
was targetting the Swift Icehouse release. This was the last release of
Gluster-Swift. The next release will target Juno, with support for storage 
policies.

Besides the work to support Storage Policies we also plan on adding support
for other Filesystems (e.g., NFS) and also for enabling the access of objects
through multiple protocols.
 
To learn more about the history of Gluster-Swift and how Swift-On-File came
to be, you can watch this presentation given at the Atlanta Openstack Summit: 
[Breaking the Mold with Openstack Swift and GlusterFS](http://youtu.be/pSWdzjA8WuA)

## Supported Filesystems:
* XFS
* GlusterFS

# Table of Contents
1. [Quick Start Guide with GlusterFS](doc/markdown/quick_start_guide.md)
1. [Developer Guide](doc/markdown/dev_guide.md)

