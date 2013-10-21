#!/bin/sh -x

# For Fedora/RHEL ONLY

if [ $EUID -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
fi

# Stop Apache service
service httpd stop

# Remove swift wsgi files
rm -rf /var/www/swift

# Remove swift httpd config file
rm -f /etc/httpd/conf.d/swift_wsgi.conf

echo -e "DONE.\nYou can now restart Swift."
