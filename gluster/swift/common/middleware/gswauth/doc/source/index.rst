.. Swauth documentation master file, created by
   sphinx-quickstart on Mon Feb 14 19:34:51 2011.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Swauth
======

    Copyright (c) 2010-2012 OpenStack, LLC

    An Auth Service for Swift as WSGI Middleware that uses Swift itself as a
    backing store. Sphinx-built docs at: http://gholt.github.com/swauth/
    Source available at: https://github.com/gholt/swauth

    See also https://github.com/openstack/keystone for the standard OpenStack
    auth service.

Overview
--------

Before discussing how to install Swauth within a Swift system, it might help to understand how Swauth does it work first.

1.  Swauth is middleware installed in the Swift Proxy's WSGI pipeline.

2.  It intercepts requests to ``/auth/`` (by default).

3.  It also uses Swift's `authorize callback <http://swift.openstack.org/development_auth.html>`_ and `acl callback <http://swift.openstack.org/misc.html#module-swift.common.middleware.acl>`_ features to authorize Swift requests.

4.  Swauth will also make various internal calls to the Swift WSGI pipeline it's installed in to manipulate containers and objects within an ``AUTH_.auth`` (by default) Swift account. These containers and objects are what store account and user information.

5.  Instead of #4, Swauth can be configured to call out to another remote Swauth to perform #4 on its behalf (using the swauth_remote config value).

6.  When managing accounts and users with the various ``swauth-`` command line tools, these tools are actually just performing HTTP requests against the ``/auth/`` end point referenced in #2. You can make your own tools that use the same :ref:`API <api_top>`.

7.  In the special case of creating a new account, Swauth will do its usual WSGI-internal requests as per #4 but will also call out to the Swift cluster to create the actual Swift account.

    a. This Swift cluster callout is an account PUT request to the URL defined by the ``swift_default_cluster`` config value.

    b. This callout end point is also saved when the account is created so that it can be given to the users of that account in the future.

    c. Sometimes, due to public/private network routing or firewalling, the URL Swauth should use should be different than the URL Swauth should give the users later. That is why the ``default_swift_cluster`` config value can accept two URLs (first is the one for users, second is the one for Swauth).

    d. Once an account is created, the URL given to users for that account will not change, even if the ``default_swift_cluster`` config value changes. This is so that you can use multiple clusters with the same Swauth system; ``default_swift_cluster`` just points to the one where you want new users to go.

    f. You can change the stored URL for an account if need be with the ``swauth-set-account-service`` command line tool or a POST request (see :ref:`API <api_set_service_endpoints>`).


Install
-------

1) Install Swauth with ``sudo python setup.py install`` or ``sudo python
   setup.py develop`` or via whatever packaging system you may be using.

2) Alter your ``proxy-server.conf`` pipeline to have ``swauth`` instead of ``tempauth``:

    Was::

        [pipeline:main]
        pipeline = catch_errors cache tempauth proxy-server

    Change To::

        [pipeline:main]
        pipeline = catch_errors cache swauth proxy-server

3) Add to your ``proxy-server.conf`` the section for the Swauth WSGI filter::

    [filter:swauth]
    use = egg:swauth#swauth
    set log_name = swauth
    super_admin_key = swauthkey
    default_swift_cluster = <your setting as discussed below>

   The ``default_swift_cluster`` setting can be confusing.

    a. If you're using an all-in-one type configuration where everything will be run on the local host on port 8080, you can omit the ``default_swift_cluster`` completely and it will default to ``local#http://127.0.0.1:8080/v1``.

    b. If you're using a single Swift proxy you can just set the ``default_swift_cluster = cluster_name#https://<public_ip>:<port>/v1`` and that URL will be given to users as well as used by Swauth internally. (Quick note: be sure the ``http`` vs. ``https`` is set right depending on if you're using SSL.)

    c. If you're using multiple Swift proxies behind a load balancer, you'll probably want ``default_swift_cluster = cluster_name#https://<load_balancer_ip>:<port>/v1#http://127.0.0.1:<port>/v1`` so that Swauth gives out the first URL but uses the second URL internally. Remember to double-check the ``http`` vs. ``https`` settings for each of the URLs; they might be different if you're terminating SSL at the load balancer.

   Also see the ``proxy-server.conf-sample`` for more config options, such as the ability to have a remote Swauth in a multiple Swift cluster configuration.

4) Be sure your Swift proxy allows account management in the ``proxy-server.conf``::

    [app:proxy-server]
    ...
    allow_account_management = true

   For greater security, you can leave this off any public proxies and just have one or two private proxies with it turned on.

5) Restart your proxy server ``swift-init proxy reload``

6) Initialize the Swauth backing store in Swift ``swauth-prep -K swauthkey``

7) Add an account/user ``swauth-add-user -A http[s]://<host>:<port>/auth/ -K
   swauthkey -a test tester testing``

8) Ensure it works ``swift -A http[s]://<host>:<port>/auth/v1.0 -U test:tester -K testing stat -v``


If anything goes wrong, it's best to start checking the proxy server logs. The client command line utilities often don't get enough information to help. I will often just ``tail -F`` the appropriate proxy log (``/var/log/syslog`` or however you have it configured) and then run the Swauth command to see exactly what requests are happening to try to determine where things fail.

General note, I find I occasionally just forget to reload the proxies after a config change; so that's the first thing you might try. Or, if you suspect the proxies aren't reloading properly, you might try ``swift-init proxy stop``, ensure all the processes died, then ``swift-init proxy start``.

Also, it's quite common to get the ``/auth/v1.0`` vs. just ``/auth/`` URL paths confused. Usual rule is: Swauth tools use just ``/auth/`` and Swift tools use ``/auth/v1.0``.


Web Admin Install
-----------------

1)  If you installed from packages, you'll need to cd to the webadmin directory
    the package installed. This is ``/usr/share/doc/python-swauth/webadmin``
    with the Lucid packages. If you installed from source, you'll need to cd to
    the webadmin directory in the source directory.

2)  Upload the Web Admin files with ``swift -A http[s]://<host>:<port>/auth/v1.0
    -U .super_admin:.super_admin -K swauthkey upload .webadmin .``

3)  Open ``http[s]://<host>:<port>/auth/`` in your browser.


Contents
--------

.. toctree::
    :maxdepth: 2

    license
    details
    swauth
    middleware
    api
    authtypes


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
