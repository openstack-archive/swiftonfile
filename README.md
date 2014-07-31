[![Build Status](https://travis-ci.org/swiftonfile/swiftonfile.svg?branch=master)](https://travis-ci.org/swiftonfile/swiftonfile)

# Swift-on-File
Swift-on-File, formerly called Gluster-Swift, is a Swift Object Server
implementation that enables objects created using the Swift API to be accessed
as files on a Posix filesystem.

The main difference from the default Swift Object Server is that Swift-on-File
stores objects following the same path hierarchy as that object's URL.
On a vanilla openstack swift the object server will store the object following
the mapping given by the Ring and its final storage location and filename are
unknown to the user. In the case of Sof, the object will be stored in the
configured filesystem volume with the same directory structure as the object's
URL.

For example, an object with URL: https://swift.example.com/v1/acc/cont/obj,
would be stored in the following way:
* Swift: /mnt/sdb1/2/node/sdb2/objects/981/f79/f566bd022b9285b05e665fd7b843bf79/1401254393.89313.data
* SoF: /mnt/gluster-vol/acc/cont/obj

## Roadmap
Swift-On-File is in a transition period. The project was recently renamed from
Gluster-Swift to Swift-on-File to better represent its nature of a Swift backend
that supports multiple Posix Filesystems, not just GlusterFS. It is also
transitioning to become a Swift Storage Policy. While Gluster-Swift had to be
deployed as its own cluster, SoF can be deployed as a storage policy on an
existing Swift cluster. This is a tremendous change to the project as it opens
up new possibilities of how SoF can be used, such as, enabling the ability to
consume and migrate existing file storage (e.g., NFS) on a swift cluster.

Our last stable [release](https://github.com/swiftonfile/swiftonfile/releases)
was targetting the Swift Icehouse release. This was the last release of
Gluster-Swift. The next release will target Juno, with support for storage 
policies.

Besides the work to support Storage Policies we also plan on adding support
for other Filesystems (e.g., NFS) and also for enabling the access of objects
through multiple protocols.
 
To learn more about the history of Gluster-Swift and how Swift-On-File came
to be, you can watch this presentation given at the Atlanta Openstack Summit: 
[Breaking the Mold with Openstack Swift and GlusterFS](http://youtu.be/pSWdzjA8WuA).
Presentation slides can be found [here](http://lpabon.github.io/openstack-summit-2014).

## Supported Filesystems:
* XFS
* GlusterFS

## Get involved:
Join us in contributing to the project. Feel free to file bugs, help with documentation
or work directly on the code. You can communicate with us using GitHub [issues](https://github.com/swiftonfile/swiftonfile/issues) or find
us in the #swiftonfile channel on Freenode.

# Guides to get started:
1. [Quick Start Guide with XFS/GlusterFS](doc/markdown/quick_start_guide.md)
1. [Developer Guide](doc/markdown/dev_guide.md)

