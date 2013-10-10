.. _api_top:

----------
Swauth API
----------

Overview
========

Swauth has its own internal versioned REST API for adding, removing,
and editing accounts.  This document explains the v2 API.

Authentication
--------------

Each REST request against the swauth API requires the inclusion of a
specific authorization user and key to be passed in a specific HTTP
header.  These headers are defined as ``X-Auth-Admin-User`` and
``X-Auth-Admin-Key``.

Typically, these values are ``.super_admin`` (the site super admin
user) with the key being specified in the swauth middleware
configuration as ``super_admin_key``.

This could also be a reseller admin with the appropriate rights to
perform actions on reseller accounts.

Endpoints
---------

The swauth API endpoint is presented on the proxy servers, in the
"/auth" namespace.  In addition, the API is versioned, and the version
documented is version 2.  API versions subdivide the auth namespace by
version, specified as a version identifier like "v2".

The auth endpoint described herein is therefore located at "/auth/v2/"
as presented by the proxy servers.

Bear in mind that in order for the auth management API to be
presented, it must be enabled in the proxy server config by setting
``allow_account_managment`` to ``true`` in the ``[app:proxy-server]``
stanza of your proxy-server.conf.

Responses
---------

Responses from the auth APIs are returned as a JSON structure.
Example return values in this document are edited for readability.


Reseller/Admin Services
=======================

Operations can be performed against the endpoint itself to perform
general administrative operations.  Currently, the only operations
that can be performed is a GET operation to get reseller or site admin
information.

Get Admin Info
--------------

A GET request at the swauth endpoint will return reseller information
for the account specified in the ``X-Auth-Admin-User`` header.
Currently, the information returned is limited to a list of accounts
for the reseller or site admin.

Valid return codes:
  * 200: Success
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key
  * 5xx: Internal error

Example Request::

    GET /auth/<api version>/ HTTP/1.1
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey

Example Curl Request::

    curl -D - https://<endpoint>/auth/v2/ \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey"

Example Result::

    HTTP/1.1 200 OK

    { "accounts":
      [
        { "name": "account1" },
        { "name": "account2" },
        { "name": "account3" }
      ]
    }


Account Services
================

There are API request to get account details, create, and delete
accounts, mapping logically to the REST verbs GET, PUT, and DELETE.
These actions are performed against an account URI, in the following
general request structure::

    METHOD /auth/<version>/<account> HTTP/1.1

The methods that can be used are detailed below.

Get Account Details
-------------------

Account details can be retrieved by performing a GET request against
an account URI.  On success, a JSON dictionary will be returned
containing the keys `account_id`, `services`, and `users`.  The
`account_id` is the value used when creating service accounts.  The
`services` value is a dict that represents valid storage cluster
endpoints, and which endpoint is the default.  The 'users' value is a
list of dicts, each dict representing a user and currently only
containing the single key 'name'.

Valid Responses:
  * 200: Success
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key
  * 5xx: Internal error

Example Request::

    GET /auth/<api version>/<account> HTTP/1.1
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey

Example Curl Request::

    curl -D - https://<endpoint>/auth/v2/<account> \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey"

Example Response::

    HTTP/1.1 200 OK

    { "services":
      { "storage":
        { "default": "local",
          "local": "https://<storage endpoint>/v1/<account_id>" },
      },
      "account_id": "<account_id>",
      "users": [ { "name": "user1" },
                 { "name": "user2" } ]
    }

Create Account
--------------

An account can be created with a PUT request against a non-existent
account.  By default, a newly created UUID4 will be used with the
reseller prefix as the account ID used when creating corresponding
service accounts.  However, you can provide an X-Account-Suffix header
to replace the UUDI4 part.

Valid return codes:
  * 200: Success
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key
  * 5xx: Internal error

Example Request::

    GET /auth/<api version>/<new_account> HTTP/1.1
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey

Example Curl Request::

    curl -D - https://<endpoint>/auth/v2/<new_account> \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey"

Example Response::

    HTTP/1.1 201 Created


Delete Account
--------------

An account can be deleted with a DELETE request against an existing
account.

Valid Responses:
  * 204: Success
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key
  * 404: Account not found
  * 5xx: Internal error

Example Request::

    DELETE /auth/<api version>/<account> HTTP/1.1
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey

Example Curl Request::

    curl -XDELETE -D - https://<endpoint>/auth/v2/<account> \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey"

Example Response::

    HTTP/1.1 204 No Content


User Services
=============

Each account in swauth contains zero or more users.  These users can
be determined with the 'Get Account Details' API request against an
account.

Users in an account can be created, modified, and detailed as
described below by apply the appropriate REST verbs to a user URI, in
the following general request structure::

    METHOD /auth/<version>/<account>/<user> HTTP/1.1

The methods that can be used are detailed below.

Get User Details
----------------

User details can be retrieved by performing a GET request against
a user URI.  On success, a JSON dictionary will be returned as
described::

    {"groups": [  # List of groups the user is a member of
	{"name": "<act>:<usr>"},
	    # The first group is a unique user identifier
	{"name": "<account>"},
	    # The second group is the auth account name
	{"name": "<additional-group>"}
	    # There may be additional groups, .admin being a
	    # special group indicating an account admin and
	    # .reseller_admin indicating a reseller admin.
     ],
     "auth": "<auth-type>:<key>"
     # The auth-type and key for the user; currently only
     # plaintext and sha1 are implemented as auth types.
    }

For example::

    {"groups": [{"name": "test:tester"}, {"name": "test"},
                {"name": ".admin"}],
     "auth": "plaintext:testing"}

Valid Responses:
  * 200: Success
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key
  * 404: Unknown account
  * 5xx: Internal error

Example Request::

    GET /auth/<api version>/<account>/<user> HTTP/1.1
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey

Example Curl Request::

    curl -D - https://<endpoint>/auth/v2/<account>/<user> \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey"

Example Response::

    HTTP/1.1 200 Ok

    { "groups": [ { "name": "<account>:<user>" },
                  { "name": "<user>" },
                  { "name": ".admin" } ],
      "auth" : "plaintext:password" }


Create User
-----------

A user can be created with a PUT request against a non-existent
user URI.  The new user's password must be set using the
``X-Auth-User-Key`` header.  The user name MUST NOT start with a
period ('.').  This requirement is enforced by the API, and will
result in a 400 error.

Optional Headers:

 * ``X-Auth-User-Admin: true``: create the user as an account admin
 * ``X-Auth-User-Reseller-Admin: true``: create the user as a reseller
   admin

Reseller admin accounts can only be created by the site admin, while
regular accounts (or account admin accounts) can be created by an
account admin, an appropriate reseller admin, or the site admin.

Note that PUT requests are idempotent, and the PUT request serves as
both a request and modify action.

Valid Responses:
  * 200: Success
  * 400: Invalid request (missing required headers)
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key, or insufficient priv
  * 404: Unknown account
  * 5xx: Internal error

Example Request::

    PUT /auth/<api version>/<account>/<user> HTTP/1.1
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey
    X-Auth-User-Admin: true
    X-Auth-User-Key: secret

Example Curl Request::

    curl -XPUT -D - https://<endpoint>/auth/v2/<account>/<user> \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey" \
    -H "X-Auth-User-Admin: true" \
    -H "X-Auth-User-Key: secret"

Example Response::

    HTTP/1.1 201 Created

Delete User
-----------

A user can be deleted by performing a DELETE request against a user
URI.  This action can only be performed by an account admin,
appropriate reseller admin, or site admin.

Valid Responses:
  * 200: Success
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key, or insufficient priv
  * 404: Unknown account or user
  * 5xx: Internal error

Example Request::

    DELETE /auth/<api version>/<account>/<user> HTTP/1.1
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey

Example Curl Request::

    curl -XDELETE -D - https://<endpoint>/auth/v2/<account>/<user> \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey"

Example Response::

    HTTP/1.1 204 No Content


Other Services
==============

There are several other swauth functions that can be performed, mostly
done via "pseudo-user" accounts.  These are well-known user names that
are unable to be actually provisioned.  These pseudo-users are
described below.

.. _api_set_service_endpoints:

Set Service Endpoints
---------------------

Service endpoint information can be retrived using the _`Get Account
Details` API method.

This function allows setting values within this section for
the <account>, allowing the addition of new service end points
or updating existing ones by performing a POST to the URI
corresponding to the pseudo-user ".services".

The body of the POST request should contain a JSON dict with
the following format::

    {"service_name": {"end_point_name": "end_point_value"}}

There can be multiple services and multiple end points in the
same call.

Any new services or end points will be added to the existing
set of services and end points. Any existing services with the
same service name will be merged with the new end points. Any
existing end points with the same end point name will have
their values updated.

The updated services dictionary will be returned on success.

Valid Responses:

  * 200: Success
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key
  * 404: Account not found
  * 5xx: Internal error

Example Request::

    POST /auth/<api version>/<account>/.services HTTP/1.0
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey
 
    {"storage": { "local": "<new endpoint>" }}

Example Curl Request::

    curl -XPOST -D - https://<endpoint>/auth/v2/<account>/.services \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey" --data-binary \
    '{ "storage": { "local": "<new endpoint>" }}'

Example Response::

    HTTP/1.1 200 OK

    {"storage": {"default": "local", "local": "<new endpoint>" }}

Get Account Groups
------------------
    
Individual user group information can be retrieved using the `Get User Details`_ API method.

This function allows retrieving all group information for all users in
an existing account.  This can be achieved using a GET action against
a user URI with the pseudo-user ".groups".

The JSON dictionary returned will be a "groups" dictionary similar to
that documented in the `Get User Details`_ method, but representing
the summary of all groups utilized by all active users in the account.

Valid Responses:
  * 200: Success
  * 403: Invalid X-Auth-Admin-User/X-Auth-Admin-Key
  * 404: Account not found
  * 5xx: Internal error

Example Request::

    GET /auth/<api version>/<account>/.groups
    X-Auth-Admin-User: .super_admin
    X-Auth-Admin-Key: swauthkey

Example Curl Request::

    curl -D - https://<endpoint>/auth/v2/<account>/.groups \
    -H "X-Auth-Admin-User: .super_admin" \
    -H "X-Auth-Admin-Key: swauthkey"
    
Example Response::

    HTTP/1.1 200 OK

    { "groups": [ { "name": ".admin" },
                  { "name": "<account>" },
                  { "name": "<account>:user1" },
                  { "name": "<account>:user2" } ] }

