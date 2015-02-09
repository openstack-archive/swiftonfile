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

SOF_MAX_DIR_NAME_LENGTH = 255
# A container is also a directory on the fileystem with the same name. Hence:
SOF_MAX_CONTAINER_NAME_LENGTH = SOF_MAX_DIR_NAME_LENGTH

SOF_MAX_OBJECT_FILENAME_LENGTH = 221
# SOF_MAX_OBJECT_FILENAME_LENGTH is the length of the last segment of object
# name. Each 'segment/component' is separated by a '/'.
# For example: If object name is "abc/def/ghi/jkl", then abc,def,ghi are all
# directories and "jkl" would be the file. This file name cannot exceed
# SOF_MAX_OBJECT_FILENAME_LENGTH.
# Why 221 ?
# The longest filename supported by XFS in 255.
# http://lxr.free-electrons.com/source/fs/xfs/xfs_types.h#L125
# SoF creates a temp file with following naming convention:
# .OBJECT_NAME.<random-string>
# The random string is 32 character long and and file name has two dots.
# Hence 255 - 32 - 2 = 221
# NOTE: Each segment between slashes ('/') should not exceed 255 and the last
# segment should not exceed 221.


def validate_obj_name_component(obj, req, last_component=False):
    if not obj:
        if last_component and req.headers.get('content-type', '_junk').lower()\
                == 'application/directory':
            # Allow directory marker objects if it ends with slash
            pass  # Check further for length of object name , don't return yet
        else:
            return 'cannot begin, end, or have contiguous %s\'s' % os.path.sep
    if not last_component:
        if len(obj) > SOF_MAX_DIR_NAME_LENGTH:
            return 'too long (%d)' % len(obj)
    else:
        if len(obj) > SOF_MAX_OBJECT_FILENAME_LENGTH:
            return 'too long (%d)' % len(obj)
    if obj == '.' or obj == '..':
        return 'cannot be . or ..'
    return ''


def check_object_creation(req, object_name):
    """
    Check to ensure that everything is alright about an object to be created.
    Swift-on-File has extra constraints on object names regarding the
    length of directories and the actual file name created on the Filesystem.

    :param req: HTTP request object
    :param object_name: name of object to be created
    :raises HTTPRequestEntityTooLarge: the object is too large
    :raises HTTPLengthRequered: missing content-length header and not
                                a chunked request
    :raises HTTPBadRequest: missing or bad content-type header, or
                            bad metadata
    """
    # SoF's additional checks
    ret = None
    object_name_components = object_name.split(os.path.sep)
    last_component = False
    for i, obj in enumerate(object_name_components):
        if i == (len(object_name_components) - 1):
            last_component = True
        reason = validate_obj_name_component(obj, req, last_component)
        if reason:
            bdy = 'Invalid object name "%s", component "%s" %s' \
                % (object_name, obj, reason)
            ret = HTTPBadRequest(body=bdy,
                                 request=req,
                                 content_type='text/plain')
    return ret
