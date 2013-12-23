#AD client setup guide

###Contents
* [Setup Overview] (#setup)
* [Configure Network] (#network)
* [Installing AD Client] (#AD-client)

<a name="setup" />
###Setup Overview

This guide talks about adding fedora linux client to windows domain.
The test setup included a client machine with Fedora 19 installed
on it with all the latest packages updated. The crux is to add this linux
machine to Windows Domain. This linux box is expected to act as RHS node and on which swiftkerbauth,
apachekerbauth code would run.

Set hostname (FQDN) to fcclient.winad.com

    # hostnamectl set-hostname "fcclient.winad.com"

    # hostname "fcclient.winad.com"


<a name="network" />
### Configure client

* Deploy Fedora linux 19.

* Update the system with latest packages.

* Configure SELinux security parameters.

* Install & configure samba

* Configure DNS

* Synchronize the time services

* Join Domain

* Install / Configure Kerberos Client


The document assumes the installing Fedora Linux and configuring SELinux
parameters to 'permissive' is known already.

###Install & Configure Samba:
    # yum -y install samba samba-client samba-common samba-winbind
    samba-winbind-clients

    # service start smb

    # ps -aef | grep smb
    # chkconfig smb on

###Synchronize time services
The kerberos authentication and most of the DNS functionality could fail with
clock skew if times are not synchronized.

    # cat /etc/ntp.conf
    server ns1.bos.redhat.com
    server 10.5.26.10

    # service ntpd stop

    # ntpdate 10.16.255.2

    # service ntpd start

    #chkconfig ntpd on

Check if Windows server in the whole environment is also time synchronized with
same source.

    # C:\Users\Administrator>w32tm /query /status | find "Source"

    Source: ns1.xxx.xxx.com

###Configure DNS on client
Improperly resolved hostname is the leading cause in authentication failures.
Best practice is to configure fedora client to use Windows DNS.
'nameserver' below is the IP address of the windows server.
    # cat /etc/resolve.conf
    domain server.winad.com
    search server.winad.com
    nameserver 10.nn.nnn.3

###Set the hostname of the client properly (FQDN)
    # cat /etc/sysconfig/network
    HOSTNAME=fcclient.winad.com


###Install & Configure kerberos client

    # yum -y install krb5-workstation

Edit the /etc/krb5.conf as follows:

    # cat /etc/krb5.conf
    [logging]
    default = FILE:/var/log/krb5libs.log
    kdc = FILE:/var/log/krb5kdc.log
    admin_server = FILE:/var/log/kadmind.log

    [libdefaults]
    default_realm = WINAD.COM
    dns_lookup_realm = false
    dns_lookup_kdc = false
    ticket_lifetime = 24h
    renew_lifetime = 7d
    forwardable = true

    [realms]
        WINAD.COM = {
            kdc = server.winad.com
            admin_server = server.winad.com
        }
    [domain_realm]
        .demo = server.winad.com
        demo = server.winad.com

###Join Domain
Fire command 'system-config-authentication' on client. This should display a
graphical wizard. Below inputs would help configure this wizard.

    - User account data base = winbind
    - winbind domain = winad
    - security model = ads
    - winbind ads realm = winad.com
    - winbind controller = server.winad.com
    - template shell = /bin/bash
    - let the other options be as is to default.
    - Perform Join domain and appy settings and quit. Please note this join should
      not see any errors. This makes the client fedora box to join the windows
      domain.

###Configure the kerberos client
This would bring the users/groups from Windows Active directory to this
fedora client.

Edit /etc/samba/smb.conf file to have below parameters in the global section.

    # cat /etc/samba/smb.conf
    [global]
    workgroup = winad
    realm = winad.com
    server string = Samba Server Version %v
    security = ADS
    allow trusted domains = No
    password server = server.winad.com
    log file = /var/log/samba/log.%m
    max log size = 50
    idmap uid = 10000­19999
    idmap gid = 10000­19999
    template shell = /bin/bash
    winbind separator = +
    winbind use default domain = Yes
    idmap config REFARCH­AD:range = 10000000­19999999
    idmap config REFARCH­AD:backend = rid
    cups options = raw


    # service smb stop

    # service winbind stop

    # tar -cvf /var/tmp/samba-cache-backup.tar /var/lib/samba

    # ls -la /var/tmp/samba-cache-backup.tar

    # rm ­-f /var/lib/samba/*


Verify that no kerberos ticket available and cached.

    # kdestroy

    # klist

Rejoin the domain.

    # net join -S server -U Administrstor

Test that client rejoined the domain.

    # net ads info

Restart smb and winbind service.

    # wbinfo --domain-users

Perform kinit for the domain users prepared on active directory. This is obtain
the kerberos ticket for user 'auth_admin'

    # kinit auth_admin

    # id -Gn auth_admin

###Notes
Obtaining the HTTP service principal & keytab file and installing it with
swiftkerbauth is added to swiftkerbauth_guide

###References
Reference Document for adding Linux box to windows domain :
Integrating Red Hat Enterprise Linux 6
with Active Directory
