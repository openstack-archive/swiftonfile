# Developer Guide

## Development Environment Setup
The workflow for SwiftOnFile is largely based upon the [OpenStack Gerrit Workflow][].

## Account Setup
Please follow the guidelines at [OpenStack Gerrit Workflow][] to do the following:
1. Create a Launchpad account.
2. Create a Gerrit account.
3. Upload SSH Keys to Gerrit.
4. Install git-review tool.

### Package Requirements
Type the following to install the required packages:

* Ubuntu

~~~
sudo apt-get -y install gcc python-dev python-setuptools libffi-dev \
    git xfsprogs memcached
~~~

* Fedora

~~~
sudo yum install gcc python-devel python-setuptools libffi-devel \
    git rpm-build xfsprogs memcached
~~~

### Git Setup
If this is your first time using git, you will need to setup the
following configuration:

~~~
git config --global user.name "Firstname Lastname"
git config --global user.email "your_email@youremail.com"
~~~

### Clone the source
You can clone the swiftonfile repo from Gerrit:
~~~
git clone ssh://<your-gerrit-username>@review.openstack.org:29418/stackforge/swiftonfile
~~~

Alternatively, if you just want to clone the source for trying things out,
without setting up lp or Gerrit account or SSH keys, you can clone from the
github mirror.
~~~
git clone git://github.com/stackforge/swiftonfile
~~~

### Git Review
Before installing git-review, make sure you have pip installed. Install the
python `pip` tool by executing the following command:

~~~
sudo easy_install pip
~~~

The tool `git review` is a simple tool to automate interaction with Gerrit.
It is recommended to use this tool to upload, modify, and query changes in Gerrit.
The tool can be installed by running the following command:

~~~
sudo pip install --upgrade git-review
~~~

While many Linux distributions offer a version of `git review`,
they do not necessarily keep it up to date. Pip provides the latest version
of the application which avoids problems with various versions of Gerrit.

The following command will setup an additional remote named 'gerrit' and
also installs the gerrit Change-Id commit hook.
~~~
git review -s
~~~

If there is no output, then everything is setup correctly.  If the output
contains the string *We don't know where your gerrit is*, then you need to
manually setup a remote repo with the name `gerrit`.
~~~
git remote add gerrit ssh://<your-gerrit-username>@review.openstack.org:29418/stackforge/swiftonfile
git remote -v
~~~

### Tox and Nose
Like OpenStack Swift, SwiftOnFile uses `tox` python virtual 
environment for its unit tests.  To install `tox` type:

~~~
sudo pip install --upgrade tox nose
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

##### Executing the tests
To run the functional tests, run the command:

~~~
tox -e functest
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
5. If this is a bug fix or enhancement, then it should have a line as follows:
`Issue #<IssueNo>`
6. It may contain any external URL references like a launchpad blueprint.
7. Blank line.

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

If 'all goes well' your change will be merged to project swiftonfile. What 'all goes well' means, is this:

1. Jenkins passes unit tests and functional tests.
2. Two core reviewers give +2.

[OpenStack Gerrit Workflow]: https://wiki.openstack.org/wiki/Gerrit_Workflow
[SSH key]: http://review.openstack.org/#/settings/ssh-keys
[PEP8]: http://www.python.org/dev/peps/pep-0008
[Git Commit Messages]: https://wiki.openstack.org/wiki/GitCommitMessages
