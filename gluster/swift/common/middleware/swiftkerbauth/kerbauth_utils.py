# Copyright (c) 2013 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
import random
import grp
import signal
from subprocess import Popen, PIPE
from time import time
from gluster.swift.common.middleware.swiftkerbauth \
    import TOKEN_LIFE, RESELLER_PREFIX


def get_remote_user(env):
    """Retrieve REMOTE_USER set by Apache from environment."""
    remote_user = env.get('REMOTE_USER', "")
    matches = re.match('([^@]+)@.*', remote_user)
    if not matches:
        raise RuntimeError("Malformed REMOTE_USER \"%s\"" % remote_user)
    return matches.group(1)


def get_auth_data(mc, username):
    """
    Returns the token, expiry time and groups for the user if it already exists
    on memcache. Returns None otherwise.

    :param mc: MemcacheRing object
    :param username: swift user
    """
    token, expires, groups = None, None, None
    memcache_user_key = '%s/user/%s' % (RESELLER_PREFIX, username)
    candidate_token = mc.get(memcache_user_key)
    if candidate_token:
        memcache_token_key = '%s/token/%s' % (RESELLER_PREFIX, candidate_token)
        cached_auth_data = mc.get(memcache_token_key)
        if cached_auth_data:
            expires, groups = cached_auth_data
            if expires > time():
                token = candidate_token
            else:
                expires, groups = None, None
    return (token, expires, groups)


def set_auth_data(mc, username, token, expires, groups):
    """
    Stores the following key value pairs on Memcache:
        (token, expires+groups)
        (user, token)
    """
    auth_data = (expires, groups)
    memcache_token_key = "%s/token/%s" % (RESELLER_PREFIX, token)
    mc.set(memcache_token_key, auth_data, time=TOKEN_LIFE)

    # Record the token with the user info for future use.
    memcache_user_key = '%s/user/%s' % (RESELLER_PREFIX, username)
    mc.set(memcache_user_key, token, time=TOKEN_LIFE)


def generate_token():
    """Generates a random token."""
    # We don't use uuid.uuid4() here because importing the uuid module
    # causes (harmless) SELinux denials in the audit log on RHEL 6. If this
    # is a security concern, a custom SELinux policy module could be
    # written to not log those denials.
    r = random.SystemRandom()
    token = '%stk%s' % \
            (RESELLER_PREFIX,
             ''.join(r.choice('abcdef0123456789') for x in range(32)))
    return token


def get_groups_from_username(username):
    """Return a set of groups to which the user belongs to."""
    # Retrieve the numerical group IDs. We cannot list the group names
    # because group names from Active Directory may contain spaces, and
    # we wouldn't be able to split the list of group names into its
    # elements.
    p = Popen(['id', '-G', username], stdout=PIPE)
    if p.wait() != 0:
        raise RuntimeError("Failure running id -G for %s" % username)
    (p_stdout, p_stderr) = p.communicate()

    # Convert the group numbers into group names.
    groups = []
    for gid in p_stdout.strip().split(" "):
        groups.append(grp.getgrgid(int(gid))[0])

    # The first element of the list is considered a unique identifier
    # for the user. We add the username to accomplish this.
    if username in groups:
        groups.remove(username)
    groups = [username] + groups
    groups = ','.join(groups)
    return groups


def run_kinit(username, password):
    """Runs kinit command as a child process and returns the status code."""
    kinit = Popen(['kinit', username],
                  stdin=PIPE, stdout=PIPE, stderr=PIPE)
    kinit.stdin.write('%s\n' % password)

    # The following code handles a corner case where the Kerberos password
    # has expired and a prompt is displayed to enter new password. Ideally,
    # we would want to read from stdout but these are blocked reads. This is
    # a hack to kill the process if it's taking too long!

    class Alarm(Exception):
        pass

    def signal_handler(signum, frame):
        raise Alarm
    # Set the signal handler and a 1-second alarm
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(1)
    try:
        kinit.wait()  # Wait for the child to exit
        signal.alarm(0)  # Reset the alarm
        return kinit.returncode  # Exit status of child on graceful exit
    except Alarm:
        # Taking too long, kill and return error
        kinit.kill()
        return -1
