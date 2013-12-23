#Windows Active Directory & Domain Controller Server Guide

###Contents
* [Setup Overview] (#Setup)
* [Installing Active Directory Services] (#AD-server)
* [Configuring DNS] (#DNS)
* [Adding Users and Groups] (#users-groups)


<a name="Setup" />
###Setup Overview

The setup includes a server machine installed with Windows 2008 R2 Server, with
Domain Controller, Active Directory services & DNS server installed alongwith.
The steps to install windows operating system and above servers can be found
on MicroSoft Documentation. This windows Active Directory server would act as an
authentication server in the whole setup. This would provide the access control
and permissions for users on certain data objects.


Windows 2008 R2 deployment:

http://technet.microsoft.com/en-us/library/dd283085.aspx


Configuring Active Directory, Domain Services, DNS server:

http://technet.microsoft.com/en-us/library/cc770946.aspx


<a name="AD-server" />
###Installing AD Server

Administrators need to follow simple instructions in Server Manager on Windows
2008, and should add Active Directory Domain Services & DNS server. It is
recommended to use static IP for DNS server.  Preferred Hostname(FQDN) for
Windows server could be of format hostname 'server.winad.com' where
'winad.com' is a domain name.

Following tips would help prepare a test setup neatly.

    - Select Active Directory Domain services wizard in Server Manager
    - Move on to install it with all the pre-requisits, e.g. .NET framework etc.
    - Configure Active directory after installtion via exapanding the 'Roles'
      section in the server manager.
    - Create a new Domain in the New Forest.
    - Type the FQDN, winad.com
    - Set Forest functional level Windows 2008 R2.
    - Selct additional options for this domain controller as DNS server.
    - Leave the log locations to default provided by wizard.
    - Set the Administrator Password carefully.
    - Thats it. You are done configuring active directory.


<a name="dns" />
###Configuring DNS

This section explains configuring the DNS server installed on Windows 2008 R2
server. You must know know about

    - Forward lookup zone

    - Reverse lookup zone

    - Zone type

A forward lookup zone is simply a way to resolve hostnames to IP address.
A reverse lookup zone is to lookup DNS hostname of the host IP.

Following tips would help configure the Zones on DNS server.

    - Create a Forward lookup zone.
    - Create it a primary zone.
    - Add the Clients using their ip addresses and FQDN to this forward lookup
      zones.
    - This would add type 'A' record for that host on DNS server.
    - Similarly create a Reverser lookup zone.
    - Add clients 'PTR' record to this zone via browsing through the forward
      zones clients.

The above setup can be tested on client once it joins the domain using 'dig'
command as mentioned below.


On client:

    # dig fcclient.winad.com
    This should yield you a Answer section mentioning its IP address.

    Reverse lookup can be tested using

    # 'dig -t ptr 101.56.168.192.in-addr.arpa.'
    The answer section should state the FQDN of the client.

    Repeat the above steps on client for Windows AD server as well.


<a name="users-groups" />
###Adding users and groups

Adding groups and users to the Windows domain is easy task.

    - Start -> Administrative Tools -> Active Directory Users & Computers
    - Expand the domain name which was prepared earlier. e.g winad.com
    - Add groups with appropreate access rights.
    - Add users to the group with appropreate permissions.
    - Make sure you set password for users prepared on AD server.
