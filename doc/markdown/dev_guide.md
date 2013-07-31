# Developer Guide

## Development Environment Setup
The workflow for Gluster-Swift is largely based upon the 
[OpenStack Gerrit Workflow][].

### Account Setup
Gluster for Swift uses [Gerrit][] as a code review system.  Create an
account in [review.gluster.org][], then generate and upload
an [SSH key][] to the website.  This will allow you to upload
changes to Gerrit.  Follow the the information given
at [GitHub Generating SSH Keys][] if you need help creating your key.

### Package Requirements

#### Fedora 19
On Fedora 19 systems, type:

~~~
sudo yum install gcc python-devel python-setuptools libffi-devel git rpm-build
~~~

### Git Setup
If this is your first time using git, you will need to setup the
following configuration:

~~~
git config --global user.name "Firstname Lastname"
git config --global user.email "your_email@youremail.com"
~~~

### Download the Source
The source for Gluster for Swift is available in Github. To download
type:

~~~
git clone https://github.com/gluster/gluster-swift.git
cd gluster-swift
~~~

### Git Review
Before installing pip, make sure you have pip installed. Install the
python `pip` tool by executing the following command:

~~~
sudo easy_install pip
~~~

The tool `git review` is a simple tool to automate interaction with Gerrit.
It is recommended to use this tool to upload, modify, and query changes in Gerrit.
The tool can be installed by running the following command:

~~~
sudo pip install git-review
~~~

While many Linux distributions offer a version of `git review`, 
they do not necessarily keep it up to date. Pip provides the latest version
of the application which avoids problems with various versions of Gerrit.

You now need to setup `git review` to communicate with review.gluster.org.
First, determine your `git review` setup by typing:

~~~
git review -s
~~~

If there is no output, then everything is setup correctly.  If the output
contains the string *We don't know where your gerrit is*, then you need to
setup a remote repo with the name `gerrit`.  You can inspect the current
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
To test that the code adheres to the Python [PEP8][] specification, 
please type:

~~~
tox -e pep8
~~~

#### Unit Tests
Once you have made your changes, you can test the quality of the code
by executing the automated unit tests as follows:

~~~
tox -e ENV
~~~

where *ENV* is either `py27` for systems with Python 2.7+, or `py26` for
systems with Python 2.6+.

If new functionality has been added, it is highly recommended that
one or more tests be added to the automated unit test suite. Unit
tests are available under the `test/unit` directory.

#### Functional Tests
The automated functional tests only run on RPM based systems
like Fedora/CentOS, etc.  To run the functional tests, the following 
requirements must be met.

1. `/etc/swift` must not exist.
1. User needs to have `sudo` access; no password necessary
1. `/mnt/gluster-object/test` and `/mn/gluster-object/test2` directories
must be created on either an XFS or GlusterFS volume.
1. glusterfs-openstack-swift RPM must not be installed on the system

Once the requirements have been met, you can now run the full functional
tests using the following command:

~~~
tools/functional_tests.sh
~~~

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
by typing:

~~~
git review
~~~

After the change is reviewed, you might have to make some
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

If you need to create a new patch for a change and include your update(s)
to your last commit type:

~~~
git commit -as --amend
~~~

Now that you have finished updating your change, you need to re-upload
to Gerrit using the following command:

~~~
git review
~~~

## Creating Distribution Packages

### Building RPMs for Fedora/RHEL/CentOS Systems
Building RPMs.  RPMs will be located in the *build* directory.

`$ bash makerpm.sh`

Building the RPM with a specific release value is useful for 
automatic Jenkin builds, or keeping track of different versions 
of the RPM:

`$ PKG_RELEASE=123 bash makerpm.sh`


[OpenStack Gerrit Workflow]: https://wiki.openstack.org/wiki/Gerrit_Workflow
[Gerrit]: https://code.google.com/p/gerrit/
[review.gluster.org]: http://review.gluster.org
[SSH Key]: http://review.gluster.org/#/settings/ssh-keys
[GitHub Generating SSH Keys]: https://help.github.com/articles/generating-ssh-keys
[PEP8]: http://www.python.org/dev/peps/pep-0008
[Git Commit Messages]: https://wiki.openstack.org/wiki/GitCommitMessages
[GlusterFS Compiling RPMS]: https://forge.gluster.org/glusterfs-core/pages/CompilingRPMS
