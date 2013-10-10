Swauth
------

An Auth Service for Swift as WSGI Middleware that uses Swift itself as a
backing store. Sphinx-built docs at: <http://gholt.github.com/swauth/>

See also <https://github.com/openstack/keystone> for the standard OpenStack
auth service.


NOTE
----

**Be sure to review the Sphinx-built docs at:
<http://gholt.github.com/swauth/>**


Quick Install
-------------

1) Install Swauth with ``sudo python setup.py install`` or ``sudo python
   setup.py develop`` or via whatever packaging system you may be using.

2) Alter your proxy-server.conf pipeline to have swauth instead of tempauth:

    Was:

        [pipeline:main]
        pipeline = catch_errors cache tempauth proxy-server

    Change To:

        [pipeline:main]
        pipeline = catch_errors cache swauth proxy-server

3) Add to your proxy-server.conf the section for the Swauth WSGI filter:

    [filter:swauth]
    use = egg:swauth#swauth
    set log_name = swauth
    super_admin_key = swauthkey

4) Be sure your proxy server allows account management:

    [app:proxy-server]
    ...
    allow_account_management = true

5) Restart your proxy server ``swift-init proxy reload``

6) Initialize the Swauth backing store in Swift ``swauth-prep -K swauthkey``

7) Add an account/user ``swauth-add-user -A http://127.0.0.1:8080/auth/ -K
   swauthkey -a test tester testing``

8) Ensure it works ``swift -A http://127.0.0.1:8080/auth/v1.0 -U test:tester -K
   testing stat -v``


Web Admin Install
-----------------

1)  If you installed from packages, you'll need to cd to the webadmin directory
    the package installed. This is ``/usr/share/doc/python-swauth/webadmin``
    with the Lucid packages. If you installed from source, you'll need to cd to
    the webadmin directory in the source directory.

2)  Upload the Web Admin files with ``swift -A http://127.0.0.1:8080/auth/v1.0
    -U .super_admin:.super_admin -K swauthkey upload .webadmin .``

3)  Open ``http://127.0.0.1:8080/auth/`` in your browser.
