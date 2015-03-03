import os
import ctypes
import operator
from ctypes.util import find_library

__all__ = ['linkat']


class Linkat(object):

    __slots__ = '_c_linkat'

    def __init__(self):
        libc = ctypes.CDLL(find_library('c'), use_errno=True)

        try:
            c_linkat = libc.linkat
        except AttributeError:
            self._c_linkat = None
            return

        c_linkat.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_char_p, ctypes.c_int]
        c_linkat.restype = ctypes.c_int

        def errcheck(result, func, arguments):
            if result == -1:
                errno = ctypes.set_errno(0)
                raise OSError(errno, 'linkat: %s' % os.strerror(errno))
            else:
                return result

        c_linkat.errcheck = errcheck

        self._c_linkat = c_linkat

    @property
    def available(self):
        return self._c_linkat is not None

    def __call__(self, olddirfd, oldpath, newdirfd, newpath, flags):
        """man 2 linkat"""
        if not self.available:
            raise EnvironmentError('linkat not available')

        if not isinstance(flags, (int, long)):
            c_flags = reduce(operator.or_, flags, 0)
        else:
            c_flags = flags

        c_olddirfd = getattr(olddirfd, 'fileno', lambda: olddirfd)()
        c_newdirfd = getattr(newdirfd, 'fileno', lambda: newdirfd)()

        return self._c_linkat(c_olddirfd, oldpath, c_newdirfd,
                              newpath, c_flags)

linkat = Linkat()
del Linkat
