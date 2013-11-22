# Authentication Services Start Guide

## Contents
* [Keystone](#keystone)
* [Swiftkerbauth](#swiftkerbauth)
* [GSwauth](#gswauth)
 * [Overview](#gswauth_overview)
 * [Quick Install](#gswauth_quick_install)
 * [How to use it](#swauth_use)

<a name="keystone" />
## Keystone
The Standard Openstack authentication service

TBD

<a name="swiftkerbauth" />
## Swiftkerbauth
Kerberos authentication filter for Swift

TBD

<a name="gswauth" />
## GSwauth

<a name="gswauth_overview" />
### Overview
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

<a name="gswauth_quick_install" />
###Quick Install

1. GSwauth is installed by default with Gluster for Swift.

2. Create and start the `gsmetadata` gluster volume
    ```
    gluster volume create gsmetadata `hostname`:`brick`
    gluster volume start gsmetadata
    ```

3. run `gluster-swift-gen-builders` with all volumes that should be
    accessible by gluster-swift, including `gsmetadata`
    ```
    gluster-swift-gen-builders gsmetadata `other volumes`
    ```

4. Change your proxy-server.conf pipeline to have gswauth instead of tempauth:

    Was:
    ```
    [pipeline:main]
    pipeline = catch_errors cache tempauth proxy-server
    ```
    Change To:
    ```
    [pipeline:main]
    pipeline = catch_errors cache gswauth proxy-server
    ```

5. Add to your proxy-server.conf the section for the Swauth WSGI filter:
```
    [filter:gswauth]

    use = egg:gluster_swift#gswauth
    set log_name = gswauth
    super_admin_key = swauthkey
    metadata_volume = gsmetadata
    auth_type = sha1
    auth_type_salt = swauthsalt
```
6. Restart your proxy server ``swift-init proxy reload``

<a name="swauth_use" />
###How to use it
1. Initialize the GSwauth backing store in Gluster-Swift
    ``swauth-prep -K swauthkey``

2. Add an account/user. The account name must match the Glusterfs volume name
   the user will be given access to. In this example we use the volume ``test``
    ``swauth-add-user -A http://127.0.0.1:8080/auth/ -K swauthkey -a test user1 password1``

3. Ensure it works
    ``swift -A http://127.0.0.1:8080/auth/v1.0 -U test:user1 -K password1 stat``

4. Ensure the following fails when an incorrect password is used
    ``swift -A http://127.0.0.1:8080/auth/v1.0 -U test:user1 -K wrongpassword stat``
