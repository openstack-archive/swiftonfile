#IPA Server Guide

##Contents
* [Setup Overview] (#setup)
* [Configure Network] (#network)
* [Installing IPA Server] (#ipa-server)
* [Configuring DNS] (#dns)
* [Adding Users and Groups] (#users-groups)


<a name="setup" />
##Setup Overview
We have used a RHEL 6.4 box as IPA and DNS server. This document borrows
instructions from the following more detailed guide.
[RHEL 6 Identity Management Guide][]


<a name="network" />
## Configure network

Change hostname (FQDN) to server.rhelbox.com
> hostname "server.rhelbox.com"

Add following to */etc/sysconfig/network* file

    HOSTNAME=server.rhelbox.com

Add the following to */etc/hosts* file

    192.168.56.110 server.rhelbox.com server
    192.168.56.101 client.rhelbox.com client

Logout and login again and verify new hostname
> hostname --fqdn

Turn off firewall
> service iptables stop
>
> chkconfig iptables off


<a name="ipa-server" />
## Installing IPA Server

Install IPA server packages and DNS dependencies
> yum install ipa-server bind bind-dyndb-ldap

Run the following interactive setup to install IPA server with DNS
> ipa-server-install --setup-dns

    The IPA Master Server will be configured with:
    Hostname:      server.rhelbox.com
    IP address:    192.168.56.110
    Domain name:   rhelbox.com
    Realm name:    RHELBOX.COM

    BIND DNS server will be configured to serve IPA domain with:
    Forwarders:    No forwarders
    Reverse zone:  56.168.192.in-addr.arpa.

The installation may take some time.

Check if IPA is installed correctly :
> kinit admin
>
> ipa user-find admin


<a name="dns" />
## Configuring DNS

Edit */etc/resolv.conf* to add this at beginning of file :

    nameserver 192.168.56.110

Warning: NetworkManager changes resolv.conf on restart

Add a DNS A record and PTR record for the client under rhelbox.com zone
> ipa dnsrecord-add rhelbox.com client --a-rec=192.168.56.101 --a-create-reverse

Check if DNS resolution is working by running :

> dig server.rhelbox.com

    ;; ANSWER SECTION:
    server.rhelbox.com. 1200    IN  A   192.168.56.110

> dig client.rhelbox.com

    ;; ANSWER SECTION:
    client.rhelbox.com. 86400   IN  A   192.168.56.101

Check if reverse resolution works :

> dig -t ptr 101.56.168.192.in-addr.arpa.

    ;; ANSWER SECTION:
    101.56.168.192.in-addr.arpa. 86400 IN   PTR client.rhelbox.com.


> dig -t ptr 110.56.168.192.in-addr.arpa.

    ;; ANSWER SECTION:
    110.56.168.192.in-addr.arpa. 86400 IN   PTR server.rhelbox.com.


<a name="users-groups" />
## Adding users and groups

The following convention is to be followed in creating group names:

    <reseller-prefix>\_<volume-name>

    <reseller-prefix>\_<account-name>

As of now, account=volume=group

For example:

    AUTH\_test

Create *auth_reseller_admin* user group
> ipa group-add auth_reseller_admin --desc="Full access to all Swift accounts"

Create *auth_rhs_test* user group
> ipa group-add auth_rhs_test --desc="Full access to rhs_test account"

Create user *auth_admin* user as member of *auth_reseller_admin* user group
> ipa user-add auth_admin --first=Auth --last=Admin --password
>
> ipa group-add-member auth_reseller_admin --users=auth_admin

Create user *rhs_test_admin* as member of *auth_rhs_test* user group
> ipa user-add rhs_test_admin --first=RHS --last=Admin --password
>
> ipa group-add-member auth_rhs_test --users=rhs_test_admin

Create user *jsmith* with no relevant group membership
> ipa user-add rhs_test_admin --first=RHS --last=Admin --password

You can verify users have been added by running
>ipa user-find admin

NOTE: Every user has to change password on first login.

[RHEL 6 Identity Management Guide]: https://access.redhat.com/site/documentation/en-US/Red_Hat_Enterprise_Linux/6/html/Identity_Management_Guide/
