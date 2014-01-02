# Authentication Services Start Guide

## Contents
* [Keystone](#keystone)
* [Swiftkerbauth](#swiftkerbauth)
* [GSwauth](#gswauth)
    * [Overview](#gswauth_overview)
    * [Installing GSwauth](#gswauth_install)
    * [User roles](#gswauth_user_roles)
    * [GSwauth Tools](#gswauth_tools)
    * [Authenticating a user](#gswauth_authenticate)

## <a name="keystone" />Keystone ##
The Standard Openstack authentication service

TBD

## <a name="swiftkerbauth" />Swiftkerbauth ##
Kerberos authentication filter for Swift

TBD

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

### <a name="gswauth_authenticate" />Authenticating a user
Accessing data through swift is a two-step process, first users must authenticate with a username and password to get a token and the storage URL. Then, users can make the object requests to the storage URL with the given token. 

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
