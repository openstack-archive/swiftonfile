#IPA Client Guide

##Contents
* [Setup Overview] (#setup)
* [Configure Network] (#network)
* [Installing IPA Client] (#ipa-client)

<a name="setup" />
##Setup Overview
We have used a F18 box as IPA client machine and used FreeIPA client.
This document borrows instructions from the following more detailed guide.
[RHEL 6 Identity Management Guide][]


<a name="network" />
## Configure network

Set hostname (FQDN) to client.rhelbox.com
> hostnamectl set-hostname "client.rhelbox.com"
>
> hostname "client.rhelbox.com"

Add following to /etc/sysconfig/network:

    HOSTNAME=client.rhelbox.com

Add the following to /etc/hostname

    client.rhelbox.com

Add the following to /etc/hosts

    192.168.56.110 server.rhelbox.com server
    192.168.56.101 client.rhelbox.com client

Logout and login again and verify hostname :
> hostname --fqdn

Edit */etc/resolv.conf* to add this at beginning of file

    nameserver 192.168.56.110

Warning: NetworkManager changes resolv.conf on restart

Turn off firewall
> service iptables stop
>
> chkconfig iptables off

<a name="ipa-client" />
## Installing IPA Client

Install IPA client packages:

For RHEL:
> yum install ipa-client ipa-admintools

For Fedora:
> yum install freeipa-client freeipa-admintools

Install IPA client and add to domain:
>ipa-client-install --enable-dns-updates

    Discovery was successful!
    Hostname: client.rhelbox.com
    Realm: RHELBOX.COM
    DNS Domain: rhelbox.com
    IPA Server: server.rhelbox.com
    BaseDN: dc=rhelbox,dc=com

    Continue to configure the system with these values? [no]: yes
    User authorized to enroll computers: admin

Check if client is configured correctly:
> kinit admin
>
> getent passwd admin


[RHEL 6 Identity Management Guide]: https://access.redhat.com/site/documentation/en-US/Red_Hat_Enterprise_Linux/6/html/Identity_Management_Guide/
