# See http://code.google.com/p/python-nose/issues/detail?id=373
# The code below enables nosetests to work with i18n _() blocks

import __builtin__
import sys
import os
from ConfigParser import MissingSectionHeaderError
from StringIO import StringIO

setattr(__builtin__, '_', lambda x: x)
