# Copyright (c) 2012-2013 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from swift.common.swob import HTTPBadRequest
import swift.common.constraints

SOF_MAX_OBJECT_NAME_LENGTH = 221
# Why 221 ?
# The longest filename supported by XFS in 255.
# http://lxr.free-electrons.com/source/fs/xfs/xfs_types.h#L125
# SoF creates a temp file with following naming convention:
# .OBJECT_NAME.<random-string>
# The random string is 32 character long and and file name has two dots.
# Hence 255 - 32 - 2 = 221
# NOTE: This limitation can be sefely raised by having slashes in really long
# object name. Each segment between slashes ('/') should not exceed 221.


def validate_obj_name_component(obj):
    if not obj:
        return 'cannot begin, end, or have contiguous %s\'s' % os.path.sep
    if len(obj) > SOF_MAX_OBJECT_NAME_LENGTH:
        return 'too long (%d)' % len(obj)
    if obj == '.' or obj == '..':
        return 'cannot be . or ..'
    return ''

# Store Swift's check_object_creation method to be invoked later
swift_check_object_creation = swift.common.constraints.check_object_creation


# Define our new one which invokes the original
def sof_check_object_creation(req, object_name):
    """
    Check to ensure that everything is alright about an object to be created.
    Monkey patches swift.common.constraints.check_object_creation, invoking
    the original, and then adding an additional check for individual object
    name components.

    :param req: HTTP request object
    :param object_name: name of object to be created
    :raises HTTPRequestEntityTooLarge: the object is too large
    :raises HTTPLengthRequered: missing content-length header and not
                                a chunked request
    :raises HTTPBadRequest: missing or bad content-type header, or
                            bad metadata
    """
    # Invoke Swift's method
    ret = swift_check_object_creation(req, object_name)

    # SoF's additional checks
    if ret is None:
        for obj in object_name.split(os.path.sep):
            reason = validate_obj_name_component(obj)
            if reason:
                bdy = 'Invalid object name "%s", component "%s" %s' \
                    % (object_name, obj, reason)
                ret = HTTPBadRequest(body=bdy,
                                     request=req,
                                     content_type='text/plain')
    return ret
