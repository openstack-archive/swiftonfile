# Authentication Services Start Guide

## Contents
* [Keystone](#keystone)
    * [Overview](#keystone_overview)
    * [Creation of swift accounts](#keystone_swift_accounts)
    * [Configuration](#keystone_configuration)
    * [Configuring keystone endpoint](#keystone_endpoint)
* [GSwauth](#gswauth)
    * [Overview](#gswauth_overview)
    * [Installing GSwauth](#gswauth_install)
    * [User roles](#gswauth_user_roles)
    * [GSwauth Tools](#gswauth_tools)
    * [Authenticating a user](#gswauth_authenticate)
* [Swiftkerbauth](#swiftkerbauth)
    * [Architecture](swiftkerbauth/architecture.md)
    * [RHEL IPA Server Guide](swiftkerbauth/ipa_server.md)
    * [RHEL IPA Client Guide](swiftkerbauth/ipa_client.md)
    * [Windows AD Server Guide](swiftkerbauth/AD_server.md)
    * [Windows AD Client Guide](swiftkerbauth/AD_client.md)
    * [Swiftkerbauth Guide](swiftkerbauth/swiftkerbauth_guide.md)

## <a name="keystone" />Keystone ##
The Standard Openstack authentication service

### <a name="keystone_overview" />Overview ###
[Keystone](https://wiki.openstack.org/wiki/Keystone) is the identity
service for OpenStack, used for authentication and authorization when
interacting with OpenStack services.

Configuring gluster-swift to authenticate against keystone is thus
very useful because allows users to access a gluster-swift storage
using the same credentials used for all other OpenStack services.

Currently, gluster-swift has a strict mapping of one account to a
GlusterFS volume, and this volume has to be named after the **tenant
id** (aka **project id**) of the user accessing it.

### <a name="keystone_installation" />Installation ###

Keystone authentication is performed using the
[swift.common.middleware.keystone](http://docs.openstack.org/developer/swift/middleware.html#module-swift.common.middleware.keystoneauth)
which is part of swift itself. It depends on keystone python APIs,
contained in the package `python-keystoneclient`.

You can install `python-keystoneclient` from the packages of your
distribution running:

  * on Ubuntu:

        sudo apt-get install python-keystoneclient

  * on Fedora:

        sudo yum install python-keystoneclient

otherwise you can install it via pip:

    sudo pip install python-keystoneclient

### <a name="keystone_swift_accounts />Creation of swift accounts ###

Due to current limitations of gluster-swift, you *must* create one
volume for each Keystone tenant (project), and its name *must* match
the *tenant id* of the tenant.

You can get the tenant id from the output of the command `keystone
tenant-get`, for example:

    # keystone tenant-get demo
    +-------------+----------------------------------+
    |   Property  |              Value               |
    +-------------+----------------------------------+
    | description |                                  |
    |   enabled   |               True               |
    |      id     | a9b091f85e04499eb2282733ff7d183e |
    |     name    |               demo               |
    +-------------+----------------------------------+

will get the tenant id of the tenant `demo`.

Create the volume as usual

    gluster volume create <tenant_id> <hostname>:<brick> ...
    gluster volume start <tenant_id>

Once you have created all the volumes you need you must re-generate
the swift ring:

    gluster-swift-gen-builders <tenant_id> [<tenant_id> ...]

After generation of swift rings you always have to restart the object,
account and container servers.

### <a name="keystone_configuration" />Configuration of the proxy-server ###

You only need to configure the proxy-server in order to enable
keystone authentication. The configuration is no different from what
is done for a standard swift installation (cfr. for instance the
related
[swift documentation](http://docs.openstack.org/developer/swift/overview_auth.html#keystone-auth)),
however we report it for completeness.

In the configuration file of the proxy server (usually
`/etc/swift/proxy-server.conf`) you must modify the main pipeline and
add `authtoken` and `keystoneauth`:

    Was:
~~~
[pipeline:main]
pipeline = catch_errors healthcheck cache ratelimit tempauth proxy-server
~~~
    Change To:
~~~
[pipeline:main]
pipeline = catch_errors healthcheck cache ratelimit authtoken keystoneauth proxy-server
~~~

(note that we also removed `tempauth`, although this is not necessary)

Add configuration for the `authtoken` middleware by adding the following section:

    [filter:authtoken]
    paste.filter_factory = keystone.middleware.auth_token:filter_factory
    auth_host = KEYSTONE_HOSTNAME
    auth_port = 35357
    auth_protocol = http
    auth_uri = http://KEYSTONE_HOSTNAME:5000/
    admin_tenant_name = TENANT_NAME
    admin_user = SWIFT_USERNAME
    admin_password = SWIFT_PASSWORD
    include_service_catalog = False

`SWIFT_USERNAME`, `SWIFT_PASSWORD` and `TENANT_NAME` will be used by
swift to get an admin token from `KEYSTONE_HOSTNAME`, used to
authorize user tokens so they must match an user in keystone with
administrative privileges.

Add configuration for the `keystoneauth` middleware:

    [filter:keystoneauth]
    use = egg:swift#keystoneauth
    # Operator roles is the role which user would be allowed to manage a
    # tenant and be able to create container or give ACL to others.
    operator_roles = Member, admin

Restart the `proxy-server` service.

### <a name="keystone_endpoint" />Configuring keystone endpoint ###

In order to be able to use the `swift` command line you also need to
configure keystone by adding a service and its relative endpoint. Up
to date documentation can be found in the OpenStack documentation, but
we report it here for completeness:

First of all create the swift service of type `object-store`:

    $ keystone service-create --name=swift \
        --type=object-store --description="Swift Service"
    +-------------+---------------------------------+
    |   Property  |              Value               |
    +-------------+----------------------------------+
    | description | Swift Service                    |
    | id          | 272efad2d1234376cbb911c1e5a5a6ed |
    | name        | swift                            |
    | type        | object-store                     |
    +-------------+----------------------------------+

and use the `id` of the service you just created to create the
corresponding endpoint:

    $ keystone endpoint-create \
       --region RegionOne \
       --service-id=<service_id> \
       --publicurl 'http://<swift-host>:8080/v1/AUTH_$(tenant_id)s' \
       --internalurl 'http://<swift-host>:8080/v1/AUTH_$(tenant_id)s' \
       --adminurl 'http://<swift-host>:8080/v1'

Now you should be able to use the swift command line to list the containers of your account with:

    $ swift --os-auth-url http://<keystone-host>:5000/v2.0 \
        -U <tenant-name>:<username> -K <password> list

to create a container

    $ swift --os-auth-url http://<keystone-host>:5000/v2.0 \
        -U <tenant-name>:<username> -K <password> post mycontainer

and upload a file

    $ swift --os-auth-url http://<keystone-host>:5000/v2.0 \
        -U <tenant-name>:<username> -K <password> upload <filename>

## <a name="gswauth" />GSwauth ##

### <a name="gswauth_overview" />Overview ###
An easily deployable GlusterFS aware authentication service based on [Swauth](http://gholt.github.com/swauth/).
GSwauth is a WSGI Middleware that uses Swift itself as a backing store to
maintain its metadata.

This model has the benefit of having the metadata available to all proxy servers
and saving the data to a GlusterFS volume. To protect the metadata, the GlusterFS
volume should only be able to be mounted by the systems running the proxy servers.

Currently, gluster-swift has a strict mapping of one account to a GlusterFS volume.
Future releases, this will be enhanced to support multiple accounts per GlusterFS
volume.

See <http://gholt.github.com/swauth/> for more information on Swauth.

### <a name="gswauth_install" />Installing GSwauth ###

1. GSwauth is installed by default with Gluster-Swift.

1. Create and start the `gsmetadata` gluster volume
~~~
gluster volume create gsmetadata <hostname>:<brick>
gluster volume start gsmetadata
~~~

1. run `gluster-swift-gen-builders` with all volumes that should be
    accessible by gluster-swift, including `gsmetadata`
~~~
gluster-swift-gen-builders gsmetadata <other volumes>
~~~

1. Change your proxy-server.conf pipeline to have gswauth instead of tempauth:

    Was:
~~~
[pipeline:main]
pipeline = catch_errors cache tempauth proxy-server
~~~
    Change To:
~~~
[pipeline:main]
pipeline = catch_errors cache gswauth proxy-server
~~~

1. Add to your proxy-server.conf the section for the GSwauth WSGI filter:
~~~
[filter:gswauth]
use = egg:gluster_swift#gswauth
set log_name = gswauth
super_admin_key = gswauthkey
metadata_volume = gsmetadata
auth_type = sha1
auth_type_salt = swauthsalt
token_life = 86400
max_token_life = 86400
~~~

1. Restart your proxy server ``swift-init proxy reload``

##### Advanced options for GSwauth WSGI filter:

* `default-swift-cluster` - default storage-URL for newly created accounts. When attempting to authenticate with a user for the first time, the return information is the access token and the storage-URL where data for the given account is stored.

* `token_life` - set default token life. The default value is 86400 (24hrs).

* `max_token_life` - The maximum token life. Users can set a token lifetime when requesting a new token with header `x-auth-token-lifetime`. If the passed in value is bigger than the `max_token_life`, then `max_token_life` will be used. 

### <a name="gswauth_user_roles" />User Roles
There are only three user roles in GSwauth:

* A regular user has basically no rights. He needs to be given both read/write priviliges to any container. 
* The `admin` user is a super-user at the account level. This user can create and delete users for the account they are members and have both write and read priviliges to all stored objects in that account.
* The `reseller admin` user is a super-user at the cluster level. This user can create and delete accounts and users and has read/write priviliges to all accounts under that cluster.


| Role/Group | get list of accounts | get Acccount Details (users, etc)| Create Account | Delete Account | Get User Details | Create admin user | Create reseller-admin user | Create regular user | Delete admin user | Delete reseller-admin user | Delete regular user | Set Service Endpoints | Get Account Groups | Modify User |
| ----------------------- |:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| .super_admin (username) |x|x|x|x|x|x|x|x|x|x|x|x|x|x|
| .reseller_admin (group) |x|x|x|x|x|x| |x|x| |x|x|x|x|
| .admin (group)          | |x| | |x|x| |x|x| |x| |x|x|
| regular user (type)     | | | | | | | | | | | | | | |


### <a name="gswauth_tools" />GSwauth Tools
GSwauth provides cli tools to facilitate managing accounts and users. All tools have some options in common:

#### Common Options:
* -A, --admin-url: The URL to the auth
    * Default: `http://127.0.0.1:8080/auth/`
* -U, --admin-user: The user with admin rights to perform action
    * Default: `.super_admin`
* -K, --admin-key: The key for the user with admin rights to perform action
    * no default value
 
#### gswauth-prep:
Prepare the gluster volume where gswauth will save its metadata.

~~~
gswauth-prep [option]
~~~

Example:

~~~
gswauth-prep -A http://10.20.30.40:8080/auth/ -K gswauthkey
~~~

#### gswauth-add-account:
Create account. Currently there's a requirement that an account must map to a gluster volume. The gluster volume must not exist at the time when the account is being created.

~~~
gswauth-add-account [option] <account_name>
~~~

Example:

~~~
gswauth-add-account -K gswauthkey <account_name>
~~~

#### gswauth-add-user:
Create user. If the provided account does not exist, it will be automatically created before creating the user.
Use the `-r` flag to create a reseller admin user and the `-a` flag to create an admin user. To change the password or make the user an admin, just run the same command with the new information.

~~~
gswauth-add-user [option] <account_name> <user> <password>
~~~

Example:

~~~
gswauth-add-user -K gswauthkey -a test ana anapwd
~~~

**Change password examples**

Command to update password/key of regular user:

~~~
gswauth-add-user -U account1:user1 -K old_pass account1 user1 new_pass
~~~

Command to update password/key of account admin:

~~~
gswauth-add-user -U account1:admin -K old_pass -a account1 admin new_pass
~~~

Command to update password/key of reseller_admin:

~~~
gswauth-add-user -U account1:radmin -K old_pass -r account1 radmin new_pass
~~~

#### gswauth-delete-account:
Delete an account. An account cannot be deleted if it still contains users, an error will be returned.

~~~
gswauth-delete-account [option] <account_name>
~~~

Example:

~~~
gswauth-delete-account -K gswauthkey test
~~~

#### gswauth-delete-user:
Delete a user.

~~~
gswauth-delete-user [option] <account_name> <user>
~~~

Example:

~~~
gswauth-delete-user -K gswauthkey test ana
~~~

#### gswauth-set-account-service:
Sets a service URL for an account. Can only be set by a reseller admin.
This command can be used to changed the default storage URL for a given account.
All accounts have the same storage-URL default value, which comes from the `default-swift-cluster` 
option.

~~~
gswauth-set-account-service [options] <account> <service> <name> <value>
~~~

Example:

~~~
gswauth-set-account-service -K gswauthkey test storage local http://newhost:8080/v1/AUTH_test
~~~

#### gswauth-list:
List information about accounts and users

* If `[account]` and `[user]` are omitted, a list of accounts will be output.
* If `[account]` is included but not `[user]`, a list of users within the account will be output.
* If `[account]` and `[user]` are included, a list of groups the user belongs to will be ouptput.
* If the `[user]` is `.groups`, the active groups for the account will be listed.

The default output format is tabular. `-p` changes the output to plain text. `-j` changes the 
output to JSON format. This will print all information about given account or user, including
stored password

~~~
gswauth-list [options] [account] [user]
~~~

Example:

~~~
gswauth-list -K gswauthkey test ana
+----------+
|  Groups  |
+----------+
| test:ana |
|   test   |
|  .admin  |
+----------+
~~~

#### gswauth-cleanup-tokens:
Delete expired tokens. Users also have the option to provide the expected life of tokens, delete all tokens or all tokens for a given account.

Options:

* `-t`, `--token-life`: The expected life of tokens, token objects modified more than this number of
seconds ago will be checked for expiration (default: 86400).
* `--purge`: Purge all tokens for a given account whether the tokens have expired or not.
* `--purge-all`: Purges all tokens for all accounts and users whether the tokens have expired or not.

~~~
gswauth-cleanup-tokens [options]
~~~

Example:

~~~
gswauth-cleanup-tokens -K gswauthkey --purge test
~~~

### <a name="gswauth_authenticate" />Authenticating a user with swift client
There are two methods of accessing data using the swift client. The first (and most simple one) is by providing the user name and password everytime. The swift client takes care of acquiring the token from gswauth. See example below:

~~~
swift -A http://127.0.0.1:8080/auth/v1.0 -U test:ana -K anapwd upload container1 README.md
~~~

The second method is a two-step process, but it allows users to only provide their username and password once. First users must authenticate with a username and password to get a token and the storage URL. Then, users can make the object requests to the storage URL with the given token.

It is important to remember that tokens expires, so the authentication process needs to be repeated every so often.

Authenticate a user with the curl command

~~~
curl -v -H 'X-Storage-User: test:ana' -H 'X-Storage-Pass: anapwd' -k http://localhost:8080/auth/v1.0
...
< X-Auth-Token: AUTH_tk7e68ef4698f14c7f95af07ab7b298610
< X-Storage-Url: http://127.0.0.1:8080/v1/AUTH_test
...
~~~
Now, the user can access the object-storage using the swift client with the given token and storage URL

~~~
bash-4.2$ swift --os-auth-token=AUTH_tk7e68ef4698f14c7f95af07ab7b298610 --os-storage-url=http://127.0.0.1:8080/v1/AUTH_test upload container1 README.md
README.md
bash-4.2$ 
bash-4.2$ swift --os-auth-token=AUTH_tk7e68ef4698f14c7f95af07ab7b298610 --os-storage-url=http://127.0.0.1:8080/v1/AUTH_test list container1
README.md
~~~
**Note:** Reseller admins must always use the second method to acquire a token, in order to be given access to other accounts different than his own. The first method of using the username and password will give them access only to their own accounts.

## <a name="swiftkerbauth" />Swiftkerbauth ##
Kerberos authentication filter

Carsten Clasohm implemented a new authentication filter for swift
that uses Kerberos tickets for single sign on authentication, and
grants administrator permissions based on the users group membership
in a directory service like Red Hat Enterprise Linux Identity Management
or Microsoft Active Directory.
