""" Gluster for Swift """


class PkgInfo(object):
    def __init__(self, canonical_version, name, final):
        self.canonical_version = canonical_version
        self.name = name
        self.final = final

    def save_config(self, filename):
        """
        Creates a file with the package configuration which can be sourced by
        a bash script.
        """
        with open(filename, 'w') as fd:
            fd.write("PKG_NAME=%s\n" % self.name)
            fd.write("PKG_VERSION=%s\n" % self.canonical_version)

    @property
    def pretty_version(self):
        if self.final:
            return self.canonical_version
        else:
            return '%s-dev' % (self.canonical_version,)


###
### Change the Package version here
###
_pkginfo = PkgInfo('1.8.0', 'glusterfs-openstack-swift', False)
__version__ = _pkginfo.pretty_version
__canonical_version__ = _pkginfo.canonical_version
