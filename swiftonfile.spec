%define _confdir %{_sysconfdir}/swift

%{!?_version:%define _version __PKG_VERSION__}
%{!?_name:%define _name __PKG_NAME__}
%{!?_release:%define _release __PKG_RELEASE__}

Summary  : Enables Swift objects to be accessed as files and files as objects
Name     : %{_name}
Version  : %{_version}
Release  : %{_release}%{?dist}
Group    : Applications/System
URL      : https://github.com/openstack/swiftonfile
Source0  : %{_name}-%{_version}-%{_release}.tar.gz
License  : ASL 2.0
BuildArch: noarch
BuildRequires: python-devel
BuildRequires: python-setuptools
Requires : python
Requires : python-setuptools
Requires : openstack-swift-object = 2.3.0

%description
SwiftOnFile is a Swift Object Server implementation that enables users to
access the same data, both as an object and as a file. Data can be stored
and retrieved through Swift's REST interface or as files from NAS interfaces
including native GlusterFS, GPFS, NFS and CIFS.

%prep
%setup -q -n swiftonfile-%{_version}

# Let RPM handle the dependencies
rm -f requirements.txt test-requirements.txt

%build
%{__python} setup.py build

%install
%{__python} setup.py install -O1 --skip-build --root %{buildroot}

mkdir -p      %{buildroot}/%{_confdir}/
cp -r etc/*   %{buildroot}/%{_confdir}/

# Remove tests
%{__rm} -rf %{buildroot}/%{python_sitelib}/test

%files
%defattr(-,root,root)
%{python_sitelib}/swiftonfile
%{python_sitelib}/swiftonfile-%{_version}*.egg-info
%{_bindir}/swiftonfile-print-metadata

%dir %{_confdir}
%config(noreplace) %{_confdir}/object-server.conf-swiftonfile
%config(noreplace) %{_confdir}/swift.conf-swiftonfile

%clean
rm -rf %{buildroot}

%changelog
* Wed Jul 15 2015 Prashanth Pai <ppai@redhat.com> - 2.3.0-0
- Update spec file to support Kilo release of Swift

* Mon Oct 28 2013 Luis Pabon <lpabon@redhat.com> - 1.10.1-0
- IceHouse Release

* Wed Aug 21 2013 Luis Pabon <lpabon@redhat.com> - 1.8.0-7
- Update RPM spec file to support SRPMS
