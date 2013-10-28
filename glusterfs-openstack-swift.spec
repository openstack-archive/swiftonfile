############################################################################################################
# Command to build rpms.#
# $ rpmbuild -ta %{name}-%{version}-%{release}.tar.gz #
############################################################################################################
# Setting up the environment. #
#  * Create a directory %{name}-%{version} under $HOME/rpmbuild/SOURCES #
#  * Copy the contents of gluster directory into $HOME/rpmbuild/SOURCES/%{name}-%{version} #
#  * tar zcvf %{name}-%{version}-%{release}.tar.gz $HOME/rpmbuild/SOURCES/%{name}-%{version} %{name}.spec #
# For more information refer #
# http://fedoraproject.org/wiki/How_to_create_an_RPM_package #
############################################################################################################

%if ! (0%{?fedora} > 12 || 0%{?rhel} > 5)
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%endif

%define _confdir %{_sysconfdir}/swift

# The following values are provided by passing the following arguments
# to rpmbuild.  For example:
# 	--define "_version 1.0" --define "_release 1" --define "_name g4s"
#
%{!?_version:%define _version __PKG_VERSION__}
%{!?_name:%define _name __PKG_NAME__}
%{!?_release:%define _release __PKG_RELEASE__}

Summary  : GlusterFS Integration with OpenStack Object Storage (Swift).
Name     : %{_name}
Version  : %{_version}
Release  : %{_release}%{?dist}
Group    : Application/File
Vendor   : Red Hat, Inc.
Source0  : %{_name}-%{_version}-%{_release}.tar.gz
Packager : gluster-users@gluster.org
License  : Apache
BuildArch: noarch
BuildRequires: python
BuildRequires: python-setuptools
Requires : memcached
Requires : openssl
Requires : python
Requires : openstack-swift = 1.10.0
Requires : openstack-swift-account = 1.10.0
Requires : openstack-swift-container = 1.10.0
Requires : openstack-swift-object = 1.10.0
Requires : openstack-swift-proxy = 1.10.0
Obsoletes: glusterfs-swift-plugin
Obsoletes: glusterfs-swift
Obsoletes: glusterfs-ufo
Obsoletes: glusterfs-swift-container
Obsoletes: glusterfs-swift-object
Obsoletes: glusterfs-swift-proxy
Obsoletes: glusterfs-swift-account

%description
Gluster-For-Swift (G4S, pronounced "gee-force") integrates GlusterFS as an
alternative back end for OpenStack Object Storage (Swift) leveraging the
existing front end OpenStack Swift code. Gluster volumes are used to store
objects in files, containers are maintained as top-level directories of volumes,
where accounts are mapped one-to-one to gluster volumes.

%prep
%setup -q

%build
%{__python} setup.py build

%install
rm -rf %{buildroot}

%{__python} setup.py install -O1 --skip-build --root %{buildroot}

mkdir -p      %{buildroot}/%{_confdir}/
cp -r etc/*   %{buildroot}/%{_confdir}/

mkdir -p                             %{buildroot}/%{_bindir}/
cp bin/gluster-swift-gen-builders    %{buildroot}/%{_bindir}/
cp bin/gluster-swift-print-metadata  %{buildroot}/%{_bindir}/

# Remove tests
%{__rm} -rf %{buildroot}/%{python_sitelib}/test

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root)
%{python_sitelib}/gluster
%{python_sitelib}/gluster_swift-%{version}-*.egg-info
%{_bindir}/gluster-swift-gen-builders
%{_bindir}/gluster-swift-print-metadata
%dir %{_confdir}
%config %{_confdir}/account-server.conf-gluster
%config %{_confdir}/container-server.conf-gluster
%config %{_confdir}/object-server.conf-gluster
%config %{_confdir}/swift.conf-gluster
%config %{_confdir}/proxy-server.conf-gluster
%config %{_confdir}/fs.conf-gluster

%changelog
* Mon Oct 28 2013 Luis Pabon <lpabon@redhat.com> - 1.10.0-0
- Havana Release

* Wed Aug 21 2013 Luis Pabon <lpabon@redhat.com> - 1.8.0-7
- Update RPM spec file to support SRPMS
