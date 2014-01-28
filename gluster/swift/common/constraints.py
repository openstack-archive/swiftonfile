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
try:
    from webob.exc import HTTPBadRequest
except ImportError:
    from swift.common.swob import HTTPBadRequest
import swift.common.constraints
import swift.common.ring as _ring
from gluster.swift.common import Glusterfs, ring

MAX_OBJECT_NAME_COMPONENT_LENGTH = 255
UNSUPPORTED_HEADERS = []


def set_object_name_component_length(len=None):
    global MAX_OBJECT_NAME_COMPONENT_LENGTH

    if len:
        MAX_OBJECT_NAME_COMPONENT_LENGTH = len
    elif hasattr(swift.common.constraints, 'constraints_conf_int'):
        MAX_OBJECT_NAME_COMPONENT_LENGTH = \
            swift.common.constraints.constraints_conf_int(
                'max_object_name_component_length', 255)
    else:
        MAX_OBJECT_NAME_COMPONENT_LENGTH = 255
    return

set_object_name_component_length()


def get_object_name_component_length():
    return MAX_OBJECT_NAME_COMPONENT_LENGTH


def validate_obj_name_component(obj):
    if not obj:
        return 'cannot begin, end, or have contiguous %s\'s' % os.path.sep
    if len(obj) > MAX_OBJECT_NAME_COMPONENT_LENGTH:
        return 'too long (%d)' % len(obj)
    if obj == '.' or obj == '..':
        return 'cannot be . or ..'
    return ''


def validate_headers(req):
    """
    Validate client header requests
    :param req: Http request
    """
    if not Glusterfs._ignore_unsupported_headers:
        for unsupported_header in UNSUPPORTED_HEADERS:
            if unsupported_header in req.headers:
                return '%s headers are not supported' \
                       % ','.join(UNSUPPORTED_HEADERS)
    return ''

# Save the original check object creation
__check_object_creation = swift.common.constraints.check_object_creation
__check_metadata = swift.common.constraints.check_metadata


def gluster_check_metadata(req, target_type, POST=True):
    """
    :param req: HTTP request object
    :param target_type: Value from POST passed to __check_metadata
    :param POST: Only call __check_metadata on POST since Swift only
                 calls check_metadata on POSTs.
    """
    ret = None
    if POST:
        ret = __check_metadata(req, target_type)
    if ret is None:
        bdy = validate_headers(req)
        if bdy:
            ret = HTTPBadRequest(body=bdy,
                                 request=req,
                                 content_type='text/plain')
    return ret


# Define our new one which invokes the original
def gluster_check_object_creation(req, object_name):
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
    ret = __check_object_creation(req, object_name)

    if ret is None:
        for obj in object_name.split(os.path.sep):
            reason = validate_obj_name_component(obj)
            if reason:
                bdy = 'Invalid object name "%s", component "%s" %s' \
                    % (object_name, obj, reason)
                ret = HTTPBadRequest(body=bdy,
                                     request=req,
                                     content_type='text/plain')
    if ret is None:
        ret = gluster_check_metadata(req, 'object', POST=False)

    return ret

# Replace the original checks with ours
swift.common.constraints.check_object_creation = gluster_check_object_creation
swift.common.constraints.check_metadata = gluster_check_metadata

# Replace the original check mount with ours
swift.common.constraints.check_mount = Glusterfs.mount

# Save the original Ring class
__Ring = _ring.Ring

# Replace the original Ring class
_ring.Ring = ring.Ring
