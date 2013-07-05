# Developer Guide

## Contributing to the project

## Development Environment Setup
The workflow for Gluster-Swift is largely based upon the 
[OpenStack Gerrit Workflow][].

### Account Setup
Gluster for Swift uses [Gerrit][] as a code review system.  Create an
account in [review.gluster.org][], then generate and upload
an [SSH key][] to the website.  This will allow you to upload
changes to Gerrit.  Follow the the information given
at [GitHub Generating SSH Keys][] if you need help creating your key.

### Download the source
The source for Gluster for Swift is available in Github.  To download
type:

~~~
git clone https://github.com/gluster/gluster-swift.git
cd gluster-swift
~~~

### Git Review
The tool `git review` is a simple tool to automate interaction with Gerrit.
We recommend using this tool to upload, modify, and query changes in Gerrit.
The tool can be installed by running the following command:

~~~
sudo pip install git-review
~~~

Note that while many distros offer a version of `git review`, they don't
necessarily keep it up to date. Pip gives one the latest which
often avoids problems with various Gerrit servers.

We now need to setup `git review` to communicate with review.gluster.org.
First, let's determine our `git review` setup by typing:

~~~
git review -s
~~~

If there is no output, then everything is setup correctly.  If the output
contains the string *We don't know where your gerrit is*, then we need
a setup a remote repo with the name `gerrit`.  We can inspect the current
remote repo's by typing the following command.

~~~
git remote -v
~~~

To add the Gerrit remote repo, type the following:

~~~
git remote add gerrit ssh://<username>@review.gluster.org/gluster-swift
git remote -v
~~~

Now we can confirm that `git review` has been setup by typing the
following and noticing no output is returned:

~~~
git review -s
~~~

### Tox and Nose
Like OpenStack Swift, Gluster for Swift uses `tox` python virtual 
environment for its unit tests.  To install `tox` type:

~~~
pip install tox nose
~~~

## Workflow

### Create a topic branch
It is recommended to create a branch in git when working on a specific topic.
If you are currently on the *master* branch, you can type the following
to create a topic branch:

~~~
git checkout -b TOPIC-BRANCH
~~~

where *TOPIC-BRANCH* is either bug/bug-number (e.g. bug/123456) or
a meaningful name for the topic (e.g. feature_xyz)

### Quality Checking
#### PEP8
To test that the code adheres to the [PEP8][] specification, please
type:

~~~
tox -e pep8
~~~

#### Unit Tests
You can run the unit tests after making your changes.  To run the unit
test suite in `tox` type the following as a non-root user:

~~~
tox -e ENV
~~~

where *ENV* is either `py27` for systems with Python 2.7+, or `py26` for
systems with Python 2.6+.

#### Functional Tests
Fuctional tests are used to test a running Gluster for Swift environment.
**TBD**.

### Commiting changes
After making the changes needed, you can commit your changes by typing:

~~~
git commit -as
~~~

where the commit message should follow the following recommendations:

1. The first line should be a brief message and contain less than 50
characters.
2. Second line blank
3. A line, or multiple line description of the change where each line
contains less than 70 characters.
4. Blank line
5. If this is a bug fix, then it should have a line as follows:
`BUG 12345: <url to bug>`
6. Blank line.

For more information on commit messages, please visit the
[Git Commit Messages][] page in OpenStack.org.

### Uploading to Gerrit
Once you have the changes ready for review, you can submit it to Gerrit
simply by typing:

~~~
git review
~~~

After the change is reviewed, most likely you may have to make some
additional modifications to your change.  To continue the work for
a specific change, you can query Gerrit for the change number by
typing:

~~~
git review -l
~~~

Then download the change to make the new modifications by typing:

~~~
git review -d CHANGE_NUMBER
~~~

where CHANGE_NUMBER is the Gerrit change number.

## Creating Distribution Packages

### Tools Installation
TBD:  For now please follow the installation instructions
on the [GlusterFS Compiling RPMS][] page.

### Building RPMs for Fedora/RHEL/CentOS Systems
Building RPMs.  RPMs will be located in the *build* directory.

`$ bash makerpm.sh`

Building RPM with a specific release value, useful for automatic
Jenkin builds, or keeping track of different versions of the
RPM:

`$ PKG_RELEASE=123 bash makerpm.sh`


[OpenStack Gerrit Workflow]: https://wiki.openstack.org/wiki/Gerrit_Workflow
[Gerrit]: https://code.google.com/p/gerrit/
[review.gluster.org]: http://review.gluster.org
[SSH Key]: http://review.gluster.org/#/settings/ssh-keys
[GitHub Generating SSH Keys]: https://help.github.com/articles/generating-ssh-keys
[PEP8]: http://www.python.org/dev/peps/pep-0008
[Git Commit Messages]: https://wiki.openstack.org/wiki/GitCommitMessages
[GlusterFS Compiling RPMS]: https://forge.gluster.org/glusterfs-core/pages/CompilingRPMS
