#!/bin/bash

# Simple script to create RPMs for G4S

cleanup()
{
	rm -rf ${RPMBUILDDIR} > /dev/null 2>&1
	rm -f ${PKGCONFIG} > /dev/null 2>&1
}

fail()
{
	cleanup
	echo $1
	exit $2
}

create_dir()
{
	if [ ! -d "$1" ] ; then
		mkdir -p "$1"
		if [ $? -ne 0 ] ; then
			fail "Unable to create dir $1" $?
		fi
	fi
}

gittotar()
{
	# Only archives committed changes
	git archive --format=tar --prefix=${SRCTAR_DIR}/ HEAD | gzip -c > ${SRCTAR}
	if [ $? -ne 0 -o \! -s ${SRCTAR} ] ; then
		fail "Unable to create git archive" $?
	fi
}

prep()
{
	rm -rf ${RPMBUILDDIR} > /dev/null 2>&1
	create_dir ${RPMBUILDDIR}

	# Create a tar file out of the current committed changes
	gittotar

}

create_rpm()
{
	# Create the rpm
	# _topdir Notifies rpmbuild the location of the root directory
	#         containing the RPM information
	# _release Allows Jenkins to setup the version using the
	#          build number
	rpmbuild --define "_topdir ${RPMBUILDDIR}" \
		--define "_release ${PKG_RELEASE}" \
		--define "_version ${PKG_VERSION}" \
		--define "_name ${PKG_NAME}" \
		-ta ${SRCTAR}
	if [ $? -ne 0 ] ; then
		fail "Unable to create rpm" $?
	fi

	# Move the rpms to the root directory
	mv ${RPMBUILDDIR_RPMS}/noarch/*rpm ${BUILDDIR}
	if [ $? -ne 0 ] ; then
		fail "Unable to move rpm to ${BUILDDIR}" $?
	fi

	echo "RPMS are now available in ${BUILDDIR}"
}

################## MAIN #####################

# Create a config file with the package information
PKGCONFIG=${PWD}/pkgconfig.in
env python pkgconfig.py
if [ ! -f "${PKGCONFIG}" ] ; then
	fail "Unable to create package information file ${PKGCONFIG}" 1
fi

# Get PKG_NAME and PKG_VERSION
. ${PKGCONFIG}
if [ -z "${PKG_NAME}" ] ; then
	fail "Unable to read the package name from the file created by pkgconfig.py" 1
fi
if [ -z "${PKG_VERSION}" ] ; then
	fail "Unable to read the package version from the file created by pkgconfig.py" 1
fi

#
# This can be set by JENKINS builds
# If the environment variable PKG_RELEASE
# has not been set, then we set it locally to
# a default value
#
if [ -z "$PKG_RELEASE" ] ; then
	PKG_RELEASE=0
fi


BUILDDIR=$PWD/build
RPMBUILDDIR=${BUILDDIR}/rpmbuild
RPMBUILDDIR_RPMS=${RPMBUILDDIR}/RPMS
SRCNAME=${PKG_NAME}-${PKG_VERSION}-${PKG_RELEASE}
SRCTAR_DIR=${PKG_NAME}-${PKG_VERSION}
SRCTAR=${RPMBUILDDIR}/${SRCNAME}.tar.gz

prep
create_rpm
cleanup
