#!/bin/sh -x

# For Fedora/RHEL ONLY

if [ $EUID -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
fi

# Stop Apache and Swift services if running
swift-init main stop
service httpd stop

# Install Apache and mod_wsgi
yum install httpd mod_wsgi

# Create a directory for Apache wsgi files
mkdir -p /var/www/swift

# Create a directory for swift which it'll use as home
mkdir -p /var/lib/swift

# Copy wsgi files for each of the four swift services
cp ./conf/*wsgi /var/www/swift/

# Copy swift httpd config file
cp ./conf/swift_wsgi.conf /etc/httpd/conf.d/

# Change owner of conf files to swift
chown swift:swift /etc/swift/*

# Check if SElinux is set to permissive/disabled
selinux_mode=$(getenforce)
if [ $selinux_mode == "Enforcing" ]; then
    echo "SElinux is set to Enforcing. Change it to Permissive or Disabled \
by editing /etc/sysconfig/selinux"
    echo "You will need to reboot your system for the changed value to take \
effect."
    exit 1
fi

echo "Successfully configured Apache as frontend for Swift."
echo "Make sure GlusterFS volume is mounted at /mnt/swiftonfile/<vol-name> \
before starting httpd"
