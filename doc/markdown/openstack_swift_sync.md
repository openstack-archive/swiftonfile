# Syncing Gluster-Swift with Swift

## Create a release
Create a release in launchpad.net so that we can place the latest swift source for download.  We'll place the source here, and it will allow tox in gluster-swift to download the latest code.

## Upload swift release

* Clone the git swift repo
* Go to the release tag or just use the latest
* Type the following to package the swift code:

```
$ python setup.py sdist
$ ls dist
```

* Take the file in the `dist` directory and upload it to the new release we created it on launchpad.net.
* Alternatively, if we are syncing with a Swift version which is already released, we can get the tar.gz file from Swift launchpad page and upload the same to gluster-swift launchpad.

## Setup Tox
Now that the swift source is availabe on launchpad.net, copy its link location and update tox.ini in gluster-swift with the new link.

## Update tests
This part is a little more complicated and now we need to *merge* the latest tests with ours.

[meld](http://meldmerge.org/) is a great tool to make this work easier. The 3-way comparison feature of meld comes handy to compare 3 version of same file from:

* Latest swift (say v1.13)
* Previous swift (say v1.12)
* gluster-swift (v1.12)

Files that need to be merged:

* Update unit tests

```
$ export SWIFTDIR=../swift
$ meld $SWIFTDIR/tox.ini tox.ini
$ meld $SWIFTDIR/test-requirements.txt tools/test-requires
$ meld $SWIFTDIR/requirements.txt tools/requirements.txt
$ meld $SWIFTDIR/test/unit/proxy/test_servers.py test/unit/proxy/test_server.py
$ cp $SWIFTDIR/test/unit/proxy/controllers/*.py test/unit/proxy/controllers
$ meld $SWIFTDIR/test/unit/__init__.py test/unit/__init__.py
```

* Update all the functional tests
First check if there are any new files in the swift functional test directory.  If there are, copy them over.

* Remember to `git add` any new files

* Now merge the existing ones:

```
for i in $SWIFTDIR/test/functional/*.py ; do
    meld $i test/functional/`basename $i`
done
```

## Update the version
If needed, update the version now in `gluster/swift/__init__.py`.

## Upload the patch
Upload the patch to Gerrit.

## Update the release in launchpad.net
Upload the gluster-swift*.tar.gz built by Jenkins to launchpad.net once the fix has been commited to the main branch.

