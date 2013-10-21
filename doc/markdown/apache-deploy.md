## Deploying Apache as front end for Openstack Swift in Fedora/RHEL

NOTE: This guide is for manual deployment. A shell script to automate the following
is present in extras/apache-deploy.

### Architecture
Swift can be configured to work both using an integral web front-end and
using a full-fledged Web Server such as the Apache2 (HTTPD) web server. The
integral web front-end is a wsgi mini "Web Server" which opens up its own
socket and serves http requests directly. The incoming requests accepted
by the integral web front-end are then forwarded to a wsgi application
(the core swift) for further handling, possibly via wsgi middleware
sub-components.

    client<-->'integral web front-end'<-->middleware<-->'core swift'

To gain full advantage of Apache2, Swift can alternatively be configured to
work as a request processor of the Apache2 server. This alternative deployment
scenario uses mod_wsgi of Apache2 to forward requests to the swift wsgi
application and middleware.

    client<-->'Apache2 with mod_wsgi'<-->middleware<-->'core swift'

The integral web front-end offers simplicity and requires minimal config.
It is also the web front-end most commonly used with Swift. Additionally, the
integral web front-end includes support for receiving chunked transfer
encoding from a client, presently not supported by Apache2 in the operation
mode described here.

### Steps

Installing Apache with mod_wsgi module:

    yum install httpd mod_wsgi

Create a directory for Apache wsgi files:

    mkdir /var/www/swift

Create a wsgi file for each service under /var/www/swift

#### /var/www/swift/proxy-server.wsgi
    from swift.common.wsgi import init_request_processor
    application, conf, logger, log_name = \
        init_request_processor('/etc/swift/proxy-server.conf','proxy-server')

#### /var/www/swift/account-server.wsgi
    from swift.common.wsgi import init_request_processor
    application, conf, logger, log_name = \
        init_request_processor('/etc/swift/account-server.conf','account-server')

#### /var/www/swift/container-server.wsgi
    from swift.common.wsgi import init_request_processor
    application, conf, logger, log_name = \
        init_request_processor('/etc/swift/container-server.conf','container-server')

#### /var/www/swift/object-server.wsgi
    from swift.common.wsgi import init_request_processor
    application, conf, logger, log_name = \
        init_request_processor('/etc/swift/object-server.conf','object-server')


Create */etc/httpd/conf.d/swift_wsgi.conf* configuration file that will define
port and Virtual Host per each local service.

    WSGISocketPrefix /var/run/wsgi
    
    #Proxy Service
    Listen 8080
    <VirtualHost *:8080>
        ServerName proxy-server
        LimitRequestBody 5368709122
        WSGIDaemonProcess proxy-server processes=5 threads=1 user=swift
        WSGIProcessGroup proxy-server
        WSGIScriptAlias / /var/www/swift/proxy-server.wsgi
        LimitRequestFields 200
        ErrorLog /var/log/httpd/proxy-server.log
        LogLevel debug
        CustomLog /var/log/httpd/proxy.log combined
    </VirtualHost>
    
    #Object Service
    Listen 6010
    <VirtualHost *:6010>
        ServerName object-server
        WSGIDaemonProcess object-server processes=5 threads=1 user=swift
        WSGIProcessGroup object-server
        WSGIScriptAlias / /var/www/swift/object-server.wsgi
        LimitRequestFields 200
        ErrorLog /var/log/httpd/object-server.log
        LogLevel debug
        CustomLog /var/log/httpd/access.log combined
    </VirtualHost>
    
    #Container Service
    Listen 6011
    <VirtualHost *:6011>
        ServerName container-server
        WSGIDaemonProcess container-server processes=5 threads=1 user=swift
        WSGIProcessGroup container-server
        WSGIScriptAlias / /var/www/swift/container-server.wsgi
        LimitRequestFields 200
        ErrorLog /var/log/httpd/container-server.log
        LogLevel debug
        CustomLog /var/log/httpd/access.log combined
    </VirtualHost>
    
    #Account Service
    Listen 6012
    <VirtualHost *:6012>
        ServerName account-server
        WSGIDaemonProcess account-server processes=5 threads=1 user=swift
        WSGIProcessGroup account-server
        WSGIScriptAlias / /var/www/swift/account-server.wsgi
        LimitRequestFields 200
        ErrorLog /var/log/httpd/account-server.log
        LogLevel debug
        CustomLog /var/log/httpd/access.log combined
    </VirtualHost>

(Re)Start Apache server:

    service httpd stop
    service httpd start

### Troubleshooting

* Make sure you have set SElinux to Permissive or Disabled by editing
  */etc/sysconfig/selinux*. You will need to reboot your system for the
  changed value to take effect. On restart, you can confirm this by running:

        getenforce

* Make sure conf files in /etc/swift are accessible by swift user:

        chown swift:swift /etc/swift/*

* Make sure the directory */var/lib/swift* exists should you see the following
  error in /var/log/httpd/error_log

        [Fri Oct 20 02:05:25.617290 2013] [:alert] [pid 3491] (2)No such file or
        directory: mod_wsgi (pid=3491): Unable to change working directory to
        '/var/lib/swift'

* Make sure the port numbers in */etc/httpd/conf.d/swift_wsgi.conf* and
  */etc/swift/*conf* files are same.

* For errors in logs like the following:

        13)Permission denied: mod_wsgi (pid=26962): Unable to connect to WSGI
        daemon process '<process-name>' on '/etc/httpd/logs/wsgi.26957.0.1.sock'
        after multiple attempts.

  Refer: https://code.google.com/p/modwsgi/wiki/ConfigurationIssues#Location_Of_UNIX_Sockets

* If your swift deployment uses some authentication mechanism that uses
  HTTP_AUTHORIZATION variable, you need to turn on WSGIPassAuthorization as
  described here:

  https://code.google.com/p/modwsgi/wiki/ConfigurationDirectives#WSGIPassAuthorization

#### Issue with gluster-swift
Unlike vanilla swift that runs as *swift* user, gluster-swift runs all four
swift servers as *root* user.

But mod_wsgi does not allow invoking wsgi applications as root:
https://code.google.com/p/modwsgi/wiki/ConfigurationDirectives#WSGIDaemonProcess

A workaround is to mount gluster volume as root beforehand:

    mount -t glusterfs localhost:myvolume /mnt/gluster-object/myvolume


### More information

* There is a Ubuntu specific guide to deploy Apache with Openstack Swift here:
  http://docs.openstack.org/developer/swift/apache_deployment_guide.html

* Example apache configuration from swift source can be found here:
  https://github.com/openstack/swift/tree/master/examples
