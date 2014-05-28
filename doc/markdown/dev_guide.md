# Developer Guide

## Development Environment Setup
The workflow for SwiftOnFile is largely based upon the 
Github WorkFlow.

### Account Setup
You can create a free account on github. It would be better to create keys and add your public key to github, else you can provide username/password each time you communicate with github from any remote machine. Follow the the information given at [GitHub Generating SSH Keys][] if you need help creating your key. You have to create a fork of [swiftonfile repo][] for your development work. You can create your fork from the github Web UI.

### Package Requirements
Type the following to install the required packages:

* Ubuntu

~~~
sudo apt-get -y install gcc python-dev python-setuptools libffi-dev \
    git xfsprogs memcached
~~~

* Fedora 19

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

### Clone your fork
You can clone the fork you created using github Web UI. By convention it will be called 'origin'. 
~~~
git clone git@github.com:<username>/swiftonfile.git
cd swiftonfile
~~~

### Add upstream repo
You can add swiftonfile project repo, to get the latest updates from the project. It will be called upstream by convention. 
~~~
git remote add upstream git@github.com:swiftonfile/swiftonfile.git
~~~

You can confirm these setting using 'git remote  -v' it should give you something like this:
~~~
origin git@github.com:<username>/swiftonfile.git (fetch)
origin git@github.com:<username>/swiftonfile.git (push)
upstream git@github.com:swiftonfile/swiftonfile.git (fetch)
upstream git@github.com:swiftonfile/swiftonfile.git (push)
~~~

### Some additional git configs
These are the changes you need to make to the git configuration so you can download and verify someone's work. 

Open your .git/config file in your editor and locate the section for your GitHub remote. It should look something like this:
~~~
[remote "upstream"]
  url = git@github.com:<USERNAME>/swiftonfile.git
  fetch = +refs/heads/*:refs/remotes/upstream/*
~~~
We're going to add a new refspec to this section so that it now looks like this:
~~~
[remote "upstream"]
  url = git@github.com:<USERNAME>/swiftonfile.git
  fetch = +refs/heads/*:refs/remotes/upstream/*
  fetch = +refs/pull/*/head:refs/pull/upstream/*
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
To run the functional tests, the following requirements must be met.

1. `/etc/swift` must not exist.
2. User needs to have `sudo` access
3. `/mnt/gluster-object/test` and `/mnt/gluster-object/test2` directories
must be created on either an XFS or GlusterFS volume.

Once the requirements have been met, you can now run the full functional
tests using the following command:

~~~
tox -e functest
~~~

### Commiting changes
After making the changes needed, you can commit your changes by typing:

~~~
git commit -a
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

> Note: A bug or an enhancement both can be loged in github as an issue.

For more information on commit messages, please visit the
[Git Commit Messages][] page in OpenStack.org.

### Uploading changes to Your Fork
Once you have the changes ready for review, you can submit it to your github fork topic branch.
by typing:

~~~
git push origin TOPIC-BRANCH
~~~

### Creating Pull request
You pushed a commit to a topic branch in your fork, and now you would like it to be merge in the swiftonfile project.

Navigate to your forked repo, locate the change your would like to be merged to swiftonfile and click on the Pull Request button.

Branch selection ==> Switch to your branch

Pull Request ==> Click the Compare & review button

Pull requests can be sent from any branch or commit but it's recommended that a topic branch be used so that follow-up commits can be pushed to update the pull request if necessary.

### Reviewing the pull request
After starting the review, you're presented with a review page where you can get a high-level overview of what exactly has changed between your branch and the repository's master branch. You can review all comments made on commits, identify which files changed, and get a list of contributors to your branch.

After the change is reviewed, you might have to make some
additional modifications to your change. You just need to do changes to your local topic branch, commit it, and push it to same branch on your github fork repo. If the branch is currently being used for a pull request, then the branch changes are automatically tracked by the pull request.

If 'all goes well' your change will be merged to project swiftonfile. What 'all goes well' means, is this:

1.  Travis-CI passes unit-tests.
2.  Jenkins passes functional-tests.
3.  It got +1 by at least 2 reviewers.
4.  A core-reviewer can give this pull request a +2 and merge it to the project repo.

### Download and Verify someone's pull request 
You can fetch all the pull requests using:
~~~
git fetch upstream
# From github.com:swiftonfile/swiftonfile
# * [new ref]         refs/pull/1000/head -> refs/pull/upstream/1000
# * [new ref]         refs/pull/1002/head -> refs/pull/upstream/1002
# * [new ref]         refs/pull/1004/head -> refs/pull/upstream/1004
# * [new ref]         refs/pull/1009/head -> refs/pull/upstream/1009
~~~

You should now be able to check out a pull request in your local repository as follows:
~~~
git checkout -b 999 pull/upstream/999
# Switched to a new branch '999'
~~~

To test this changes you can prepare tox virtual env to run with the change using:
~~~
#tox -e run
~~~
If all the prerequisite for running tox are there you should be able to see the bash prompt, where you can test these changes. 

## Creating Distribution Packages

### Building RPMs for Fedora/RHEL/CentOS Systems
Building RPMs.  RPMs will be located in the *build* directory.

`$ bash makerpm.sh`

Building the RPM with a specific release value is useful for 
automatic Jenkin builds, or keeping track of different versions 
of the RPM:

`$ PKG_RELEASE=123 bash makerpm.sh`

[swiftonfile repo]: https://github.com/swiftonfile/swiftonfile
[GitHub Generating SSH Keys]: https://help.github.com/articles/generating-ssh-keys
[PEP8]: http://www.python.org/dev/peps/pep-0008
[Git Commit Messages]: https://wiki.openstack.org/wiki/GitCommitMessages
[GlusterFS Compiling RPMS]: https://forge.gluster.org/glusterfs-core/pages/CompilingRPMS
[README]: http://repos.fedorapeople.org/repos/openstack/openstack-trunk/README

