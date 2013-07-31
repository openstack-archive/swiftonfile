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


class GlusterFileSystemOSError(OSError):
    pass


class GlusterFileSystemIOError(IOError):
    pass


class GlusterfsException(Exception):
    pass


class FailureToMountError(GlusterfsException):
    pass


class FileOrDirNotFoundError(GlusterfsException):
    pass


class NotDirectoryError(GlusterfsException):
    pass


class AlreadyExistsAsDir(GlusterfsException):
    pass


class AlreadyExistsAsFile(GlusterfsException):
    pass


class DiskFileNoSpace(GlusterfsException):
    pass
