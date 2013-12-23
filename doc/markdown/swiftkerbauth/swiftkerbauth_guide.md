#swiftkerbauth

* [Installing Kerberos module for Apache on IPA client] (#httpd-kerb-install)
* [Creating HTTP Service Principal on IPA server] (#http-principal)
* [Installing and configuring swiftkerbauth on IPA client] (#install-swiftkerbauth)
* [Using swiftkerbauth] (#use-swiftkerbauth)

<a name="httpd-kerb-install" />
## Installing Kerberos module for Apache on IPA client

Install httpd server with kerberos module:
> yum install httpd mod_auth_kerb
>
> service httpd restart

Check if auth_kerb_module is loaded :
> httpd -M | grep kerb

Change httpd log level to debug by adding/changing the following in
*/etc/httpd/conf/httpd.conf* file

    LogLevel debug

httpd logs are at */var/log/httpd/error_log* for troubleshooting

If SELinux is enabled, allow Apache to connect to memcache and
activate the changes by running
>setsebool -P httpd_can_network_connect 1
>
>setsebool -P httpd_can_network_memcache 1

*****

<a name="http-principal" />
## Creating HTTP Service Principal on IPA server

Add a HTTP Kerberos service principal :
> ipa service-add HTTP/client.rhelbox.com@RHELBOX.COM

Retrieve the HTTP service principal to a keytab file:
> ipa-getkeytab -s server.rhelbox.com -p HTTP/client.rhelbox.com@RHELBOX.COM -k /tmp/http.keytab

Copy keytab file to client:
> scp /tmp/http.keytab root@192.168.56.101:/etc/httpd/conf/http.keytab

## Creating HTTP Service Principal on Windows AD server

Add a HTTP Kerberos service principal:
> c:\>ktpass.exe -princ HTTP/fcclient.winad.com@WINAD.COM -mapuser
> auth_admin@WINAD.COM -pass Redhat*123 -out c:\HTTP.keytab

Use winscp to copy HTTP.ketab file to /etc/httpd/conf/http.keytab

*****

<a name="install-swiftkerbauth" />
##Installing and configuring swiftkerbauth on IPA client

Prerequisites for installing swiftkerbauth
* swift (havana)
* gluster-swift (optional)

You can install swiftkerbauth using one of these three ways:

Installing swiftkerbauth from source:
> python setup.py install

Installing swiftkerbauth using pip:
> pip install swiftkerbauth

Installing swiftkerbauth from RPMs:
> ./makerpm.sh
>
> rpm -ivh dist/swiftkerbauth-1.0.0-1.noarch.rpm

Edit */etc/httpd/conf.d/swift-auth.conf* and change KrbServiceName, KrbAuthRealms and Krb5KeyTab parameters accordingly.
More detail on configuring kerberos for apache can be found at:
[auth_kerb_module Configuration][]

Make /etc/httpd/conf/http.keytab readable by any user :
> chmod 644 /etc/httpd/conf/http.keytab

And preferably change owner of keytab file to apache :
> chown apache:apache /etc/httpd/conf/http.keytab

Reload httpd
> service httpd reload

Make authentication script executable:
> chmod +x /var/www/cgi-bin/swift-auth

*****

<a name="#use-swiftkerbauth" />
##Using swiftkerbauth

### Adding kerbauth filter in swift pipeline

Edit */etc/swift/proxy-server.conf* and add a new filter section as follows:

    [filter:kerbauth]
    use = egg:swiftkerbauth#kerbauth
    ext_authentication_url = http://client.rhelbox.com/cgi-bin/swift-auth

Add kerbauth to pipeline

    [pipeline:main]
    pipeline = catch_errors healthcheck proxy-logging cache proxy-logging kerbauth proxy-server

If the Swift server is not one of your Gluster nodes, edit
*/etc/swift/fs.conf* and change the following lines in the DEFAULT
section:

    mount_ip = RHS_NODE_HOSTNAME
    remote_cluster = yes

Restart swift to activate kerbauth filer
> swift-init main restart


###Examples

####Authenticate user and get Kerberos ticket

> kinit auth_admin

NOTE: curl ignores user specified in -u option. All further curl commands
will use the currently authenticated auth_admin user.

####Get an authentication token:
> curl -v -u : --negotiate --location-trusted http://client.rhelbox.com:8080/auth/v1.0

    * About to connect() to client.rhelbox.com port 8080 (#0)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 8080 (#0)
    > GET /auth/v1.0 HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com:8080
    > Accept: */*
    >
    < HTTP/1.1 303 See Other
    < Content-Type: text/html; charset=UTF-8
    < Location: http://client.rhelbox.com/cgi-bin/swift-auth
    < Content-Length: 0
    < X-Trans-Id: txecd415aae89b4320b6145-0052417ea5
    < Date: Tue, 24 Sep 2013 11:59:33 GMT
    <
    * Connection #0 to host client.rhelbox.com left intact
    * Issue another request to this URL: 'http://client.rhelbox.com/cgi-bin/swift-auth'
    * About to connect() to client.rhelbox.com port 80 (#1)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 80 (#1)
    > GET /cgi-bin/swift-auth HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com
    > Accept: */*
    >
    < HTTP/1.1 401 Unauthorized
    < Date: Tue, 24 Sep 2013 11:59:33 GMT
    < Server: Apache/2.4.6 (Fedora) mod_auth_kerb/5.4
    < WWW-Authenticate: Negotiate
    < WWW-Authenticate: Basic realm="Swift Authentication"
    < Content-Length: 381
    < Content-Type: text/html; charset=iso-8859-1
    <
    * Ignoring the response-body
    * Connection #1 to host client.rhelbox.com left intact
    * Issue another request to this URL: 'http://client.rhelbox.com/cgi-bin/swift-auth'
    * Re-using existing connection! (#1) with host (nil)
    * Connected to (nil) (192.168.56.101) port 80 (#1)
    * Server auth using GSS-Negotiate with user ''
    > GET /cgi-bin/swift-auth HTTP/1.1
    > Authorization: Negotiate YIICYgYJKoZIhvcSAQICAQBuggJRMIICTaADAgEFoQMCAQ6iBwMFACAAAACjggFgYYIBXDCCAVigAwIBBaENGwtSSEVMQk9YLkNPTaIlMCOgAwIBA6EcMBobBEhUVFAbEmNsaWVudC5yaGVsYm94LmNvbaOCARkwggEVoAMCARKhAwIBAaKCAQcEggEDx9SH2R90RO4eAkhsNKow/DYfjv1rWhgxNRqj/My3yslASSgefls48VdDNHVVWqr1Kd6mB/9BIoumpA+of+KSAg2QfPtcWiVFj5n5Fa8fyCHyQPvV8c92KzUdrBPc8OVn0aldFp0I4P1MsYZbnddDRSH3kjVA5oSucHF59DhZWiGJV/F6sVimBSeoTBHQD38Cs5RhyDHNyUad9v3gZERVGCJXC76i7+yyaoIDA+N9s0hasHajhTnjs3XQBYfZFwp8lWl3Ub+sOtPO1Ng7mFlSAYXCM6ljlKTEaxRwaYoXUC1EoIqEOG/8pC9SJThS2M1G7MW1c5xm4lksNss72OH4gtPns6SB0zCB0KADAgESooHIBIHFrLtai5U8ajEWo1J9B26PnIUqLd+uA0KPd2Y2FjrH6rx4xT8qG2p8i36SVGubvwBVmfQ7lSJcXt6wUvb43qyPs/fMiSY7QxHxt7/btMgxQl6JWMagvXMhCNXnhEHNNaTdBcG5KFERDGeo0txaAD1bzZ4mnxCQmoqusGzZ6wdDw6+5wq1tK/hQTQUgk2NwxfXAg2J5K02/3fKjFR2h7zewI1pEyhhpeONRkkRETcyojkK2EbVzZ8kc3RsuwzFYsJ+9u5Qj3E4=
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com
    > Accept: */*
    >
    < HTTP/1.1 200 OK
    < Date: Tue, 24 Sep 2013 11:59:33 GMT
    < Server: Apache/2.4.6 (Fedora) mod_auth_kerb/5.4
    < WWW-Authenticate: Negotiate YIGZBgkqhkiG9xIBAgICAG+BiTCBhqADAgEFoQMCAQ+iejB4oAMCARKicQRveeZTV/QRJSIOoOWPbZkEmtdug9V5ZcMGXWqAJvCAnrvw9gHbklMyLl8f8jU2e0wU3ehtchLEL4dVeAYgKsnUgw4wGhHu59AZBwSbHRKSpv3I6gWEZqC4NAEuZJFW9ipdUHOiclBQniVXXCsRF/5Y
    < X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a
    < X-Debug-Remote-User: auth_admin
    < X-Debug-Groups: auth_admin,auth_reseller_admin
    < X-Debug-Token-Life: 86400s
    < X-Debug-Token-Expires: Wed Sep 25 17:29:33 2013
    < Content-Length: 0
    < Content-Type: text/html; charset=UTF-8
    <
    * Connection #1 to host (nil) left intact
    * Closing connection #0
    * Closing connection #1

The header *X-Auth-Token* in response contains the token *AUTH_tk083b8abc92f4a514f34224a181ed568a*.

####PUT a container
>curl -v -X PUT -H 'X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a' http://client.rhelbox.com:8080/v1/AUTH_myvolume/c1

    * About to connect() to client.rhelbox.com port 8080 (#0)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 8080 (#0)
    > PUT /v1/AUTH_myvolume/c1 HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com:8080
    > Accept: */*
    > X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a
    >
    < HTTP/1.1 201 Created
    < Content-Length: 0
    < Content-Type: text/html; charset=UTF-8
    < X-Trans-Id: txc420b0ebf9714445900e8-0052418863
    < Date: Tue, 24 Sep 2013 12:41:07 GMT
    <
    * Connection #0 to host client.rhelbox.com left intact
    * Closing connection #0

####GET a container listing
> curl -v -X GET -H 'X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a' http://client.rhelbox.com:8080/v1/AUTH_myvolume

    * About to connect() to client.rhelbox.com port 8080 (#0)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 8080 (#0)
    > GET /v1/AUTH_myvolume HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com:8080
    > Accept: */*
    > X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a
    >
    < HTTP/1.1 200 OK
    < Content-Length: 3
    < X-Account-Container-Count: 0
    < Accept-Ranges: bytes
    < X-Account-Object-Count: 0
    < X-Bytes-Used: 0
    < X-Timestamp: 1379997117.09468
    < X-Object-Count: 0
    < X-Account-Bytes-Used: 0
    < X-Type: Account
    < Content-Type: text/plain; charset=utf-8
    < X-Container-Count: 0
    < X-Trans-Id: tx89826736a1ab4d6aae6e3-00524188dc
    < Date: Tue, 24 Sep 2013 12:43:08 GMT
    <
    c1
    * Connection #0 to host client.rhelbox.com left intact
    * Closing connection #0

####PUT an object in container
> curl -v -X PUT -H 'X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a' http://client.rhelbox.com:8080/v1/AUTH_myvolume/c1/object1 -d'Hello world'

    * About to connect() to client.rhelbox.com port 8080 (#0)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 8080 (#0)
    > PUT /v1/AUTH_myvolume/c1/object1 HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com:8080
    > Accept: */*
    > X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a
    > Content-Length: 11
    > Content-Type: application/x-www-form-urlencoded
    >
    * upload completely sent off: 11 out of 11 bytes
    < HTTP/1.1 201 Created
    < Last-Modified: Wed, 25 Sep 2013 06:08:00 GMT
    < Content-Length: 0
    < Etag: 3e25960a79dbc69b674cd4ec67a72c62
    < Content-Type: text/html; charset=UTF-8
    < X-Trans-Id: tx01f1b5a430cf4af3897be-0052427dc0
    < Date: Wed, 25 Sep 2013 06:08:01 GMT
    <
    * Connection #0 to host client.rhelbox.com left intact
    * Closing connection #0

####Give permission to jsmith to list and download objects from c1 container
> curl -v -X POST -H 'X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a' -H 'X-Container-Read: jsmith' http://client.rhelbox.com:8080/v1/AUTH_myvolume/c1

    * About to connect() to client.rhelbox.com port 8080 (#0)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 8080 (#0)
    > POST /v1/AUTH_myvolume/c1 HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com:8080
    > Accept: */*
    > X-Auth-Token: AUTH_tk083b8abc92f4a514f34224a181ed568a
    > X-Container-Read: jsmith
    >
    < HTTP/1.1 204 No Content
    < Content-Length: 0
    < Content-Type: text/html; charset=UTF-8
    < X-Trans-Id: txcedea3e2557d463eb591d-0052427f60
    < Date: Wed, 25 Sep 2013 06:14:56 GMT
    <
    * Connection #0 to host client.rhelbox.com left intact
    * Closing connection #0

####Access container as jsmith

> kinit jsmith

Get token for jsmith
> curl -v -u : --negotiate --location-trusted http://client.rhelbox.com:8080/auth/v1.0

    * About to connect() to client.rhelbox.com port 8080 (#0)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 8080 (#0)
    > GET /auth/v1.0 HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com:8080
    > Accept: */*
    >
    < HTTP/1.1 303 See Other
    < Content-Type: text/html; charset=UTF-8
    < Location: http://client.rhelbox.com/cgi-bin/swift-auth
    < Content-Length: 0
    < X-Trans-Id: txf51e1bf7f8c5496f8cc93-005242800b
    < Date: Wed, 25 Sep 2013 06:17:47 GMT
    <
    * Connection #0 to host client.rhelbox.com left intact
    * Issue another request to this URL: 'http://client.rhelbox.com/cgi-bin/swift-auth'
    * About to connect() to client.rhelbox.com port 80 (#1)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 80 (#1)
    > GET /cgi-bin/swift-auth HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com
    > Accept: */*
    >
    < HTTP/1.1 401 Unauthorized
    < Date: Wed, 25 Sep 2013 06:17:47 GMT
    < Server: Apache/2.4.6 (Fedora) mod_auth_kerb/5.4
    < WWW-Authenticate: Negotiate
    < WWW-Authenticate: Basic realm="Swift Authentication"
    < Content-Length: 381
    < Content-Type: text/html; charset=iso-8859-1
    <
    * Ignoring the response-body
    * Connection #1 to host client.rhelbox.com left intact
    * Issue another request to this URL: 'http://client.rhelbox.com/cgi-bin/swift-auth'
    * Re-using existing connection! (#1) with host (nil)
    * Connected to (nil) (192.168.56.101) port 80 (#1)
    * Server auth using GSS-Negotiate with user ''
    > GET /cgi-bin/swift-auth HTTP/1.1
    > Authorization: Negotiate YIICWAYJKoZIhvcSAQICAQBuggJHMIICQ6ADAgEFoQMCAQ6iBwMFACAAAACjggFbYYIBVzCCAVOgAwIBBaENGwtSSEVMQk9YLkNPTaIlMCOgAwIBA6EcMBobBEhUVFAbEmNsaWVudC5yaGVsYm94LmNvbaOCARQwggEQoAMCARKhAwIBAaKCAQIEgf/+3OaXYCSEjcsjU3t3lOLcYG84GBP9Kj9YTHc7yVMlcam4ivCwMqCkzxgvNo2E3a5KSWyFwngeX4b/QFbCKPXA4sfBibZRkeMk5gr2f0MLI3gWEAIYq7bJLre04bnkD2F0MzijPJrOLIx1KmFe08UGWCEmnG2uj07lvIR1RwV/7dMM4J1B+KKvDVKA0LxahwPIpx8oOON2yMGcstrBAHBBk5pmpt1Gg9Lh7xdNPsjP0IfI5Q0zkGCRBKpvpXymP1lQpQXlHbqkdBYOmG4+p/R+vIosO4ui1G6GWE9t71h3AqW61CcCj3/oOjZsG56k8HMSNk/+3mfUTP86nzLRGkekgc4wgcugAwIBEqKBwwSBwPsG9nGloEnOsA1abP4R1/yUDcikjjwKiacvZ+cu7bWEzu3L376k08U8C2YIClyUJy3Grt68LxhnfZ65VCZ5J5IOLiXOJnHBIoJ1L4GMYp4EgZzHvI7R3U3DApMzNWZwc1MsSF5UGhmLwxSevDLetJHjgKzKNteRyVN/8CFgjSBEjGSN1Qgy1RZHuQR9d3JHPczONZ4+ZgStfy+I1m2IUIgW3+4JGFVafHiBQVwSWRNfdXFgI3wBz7slntd7r3qMWA==
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com
    > Accept: */*
    >
    < HTTP/1.1 200 OK
    < Date: Wed, 25 Sep 2013 06:17:47 GMT
    < Server: Apache/2.4.6 (Fedora) mod_auth_kerb/5.4
    < WWW-Authenticate: Negotiate YIGYBgkqhkiG9xIBAgICAG+BiDCBhaADAgEFoQMCAQ+ieTB3oAMCARKicARuH2YpjFrtgIhGr5nO7gh/21EvGH9tayRo5A3pw5pxD1B1036ePLG/x98OdMrSflse5s8ttz8FmvRphCFJa8kfYtnWULgoFLF2F2a1zBdSo2oCA0R05YFwArNhkg6ou5o7wWZkERHK33CKlhudSj8=
    < X-Auth-Token: AUTH_tkb5a20eb8207a819e76619431c8410447
    < X-Debug-Remote-User: jsmith
    < X-Debug-Groups: jsmith
    < X-Debug-Token-Life: 86400s
    < X-Debug-Token-Expires: Thu Sep 26 11:47:47 2013
    < Content-Length: 0
    < Content-Type: text/html; charset=UTF-8
    <
    * Connection #1 to host (nil) left intact
    * Closing connection #0
    * Closing connection #1

List the container using authentication token for jsmith:
> curl -v -X GET -H 'X-Auth-Token: AUTH_tkb5a20eb8207a819e76619431c8410447' http://client.rhelbox.com:8080/v1/AUTH_myvolume/c1

    * About to connect() to client.rhelbox.com port 8080 (#0)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 8080 (#0)
    > GET /v1/AUTH_myvolume/c1 HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com:8080
    > Accept: */*
    > X-Auth-Token: AUTH_tkb5a20eb8207a819e76619431c8410447
    >
    < HTTP/1.1 200 OK
    < Content-Length: 8
    < X-Container-Object-Count: 0
    < Accept-Ranges: bytes
    < X-Timestamp: 1
    < X-Container-Bytes-Used: 0
    < Content-Type: text/plain; charset=utf-8
    < X-Trans-Id: tx575215929c654d9f9f284-00524280a4
    < Date: Wed, 25 Sep 2013 06:20:20 GMT
    <
    object1
    * Connection #0 to host client.rhelbox.com left intact
    * Closing connection #0

Downloading the object as jsmith:
> curl -v -X GET -H 'X-Auth-Token: AUTH_tkb5a20eb8207a819e76619431c8410447' http://client.rhelbox.com:8080/v1/AUTH_myvolume/c1/object1

    * About to connect() to client.rhelbox.com port 8080 (#0)
    *   Trying 192.168.56.101...
    * connected
    * Connected to client.rhelbox.com (192.168.56.101) port 8080 (#0)
    > GET /v1/AUTH_myvolume/c1/object1 HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: client.rhelbox.com:8080
    > Accept: */*
    > X-Auth-Token: AUTH_tkb5a20eb8207a819e76619431c8410447
    >
    < HTTP/1.1 200 OK
    < Content-Length: 11
    < Accept-Ranges: bytes
    < Last-Modified: Wed, 25 Sep 2013 06:08:00 GMT
    < Etag: 3e25960a79dbc69b674cd4ec67a72c62
    < X-Timestamp: 1380089280.98829
    < Content-Type: application/x-www-form-urlencoded
    < X-Trans-Id: tx19b5cc3847854f40a6ca8-00524281aa
    < Date: Wed, 25 Sep 2013 06:24:42 GMT
    <
    * Connection #0 to host client.rhelbox.com left intact
    Hello world* Closing connection #0

For curl to follow the redirect, you need to specify additional
options. With these, and with a current Kerberos ticket, you should
get the Kerberos user's cached authentication token, or a new one if
the previous token has expired.

> curl -v -u : --negotiate --location-trusted -X GET http://client.rhelbox.com:8080/v1/AUTH_myvolume/c1/object1

The --negotiate option is for curl to perform Kerberos authentication and
--location-trusted is for curl to follow the redirect.

[auth_kerb_module Configuration]: http://modauthkerb.sourceforge.net/configure.html
