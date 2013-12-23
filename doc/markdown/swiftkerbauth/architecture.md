# Architecture

The Swift API is HTTP-based. As described in the Swift documentation
[1], clients first make a request to an authentication URL, providing
a username and password. The reply contains a token which is used in
all subsequent requests.

Swift has a chain of filters through which all client requests go. The
filters to use are configured with the pipeline parameter in
/etc/swift/proxy-server.conf:

    [pipeline:main]
    pipeline = healthcheck cache tempauth proxy-server

For the single sign authentication, we added a new filter called
"kerbauth" and put it into the filter pipeline in place of tempauth.

The filter checks the URL for each client request. If it matches the
authentication URL, the client is redirected to a URL on a different
server (on the same machine). The URL is handled by a CGI script, which
is set up to authenticate the client with Kerberos negotiation, retrieve
the user's system groups [2], store them in a memcache ring shared with
the Swift server, and return the authentication token to the client.

When the client provides the token as part of a resource request, the
kerbauth filter checks it against its memcache, grants administrator
rights based on the group membership retrieved from memcache, and
either grants or denies the resource access.

[1] http://docs.openstack.org/api/openstack-object-storage/1.0/content/authentication-object-dev-guide.html

[2] The user data and system groups are usually provided by Red Hat
    Enterprise Linux identity Management or Microsoft Active
    Directory. The script relies on the system configuration to be set
    accordingly (/etc/nsswitch.conf).

*****

## kerbauth.py

The script kerbauth.py began as a copy of the tempauth.py script from
from tempauth middleware. It contains the following modifications, among
others:

In the __init__ method, we read the ext_authentication_url parameter
from /etc/swift/proxy-server.conf. This is the URL that clients are
redirected to when they access either the Swift authentication URL, or
when they request a resource without a valid authentication token.

The configuration in proxy-server.conf looks like this:

    [filter:kerbauth]
    use = egg:swiftkerbauth#kerbauth
    ext_authentication_url = http://client.rhelbox.com/cgi-bin/swift-auth

The authorize method was changed so that global administrator rights
are granted if the user is a member of the auth_reseller_admin
group. Administrator rights for a specific account like vol1 are
granted if the user is a member of the auth_vol1 group. [3]

The denied_response method was changed to return a HTTP redirect to
the external authentication URL if no valid token was provided by the
client.

Most of the handle_get_token method was moved to the external
authentication script. This method now returns a HTTP redirect.

In the __call__ and get_groups method, we removed support for the
HTTP_AUTHORIZATION header, which is only needed when Amazon S3 is
used.

Like tempauth.py, kerbauth.py uses a Swift wrapper to access
memcache. This wrapper converts the key to an MD5 hash and uses the
hash value to determine on which of a pre-defined list of servers to
store the data.

[3] "auth" is the default reseller prefix, and would be different if
    the reseller_prefix parameter in proxy-server.conf was set.

## swift-auth CGI script

swift-auth resides on an Apache server and assumes that Apache is
configured to authenticate the user before this script is
executed. The script retrieves the username from the REMOTE_USER
environment variable, and checks if there already is a token for this
user in the memcache ring. If not, it generates a new one, retrieves
the user's system groups with "id -Gn USERNAME", stores this
information in the memcache ring, and returns the token to the client.

To allow the CGI script to connect to memcache, the SELinux booleans
httpd_can_network_connect and httpd_can_network_memcache had to be
set.

The tempauth filter uses the uuid module to generate token
strings. This module creates and runs temporary files, which leads to
AVC denial messages in /var/log/audit/audit.log when used from an
Apache CGI script. While the module still works, the audit log would
grow quickly. Instead of writing an SELinux policy module to allow or
to silently ignore these accesses, the swift-auth script uses the
"random" module for generating token strings.

Red Hat Enterprise Linux 6 comes with Python 2.6 which only provides
method to list the locally defined user groups. To include groups from
Red Hat Enterprise Linux Identity Management and in the future from
Active Directory, the "id" command is run in a subprocess.
