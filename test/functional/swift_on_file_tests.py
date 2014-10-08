# Copyright (c) 2013 Red Hat, Inc.
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

""" OpenStack Swift based functional tests for Swift on File"""

import os
import re
import hashlib
from shutil import rmtree

from test.functional.tests import Base, Utils
from test.functional.swift_test_client import Account, Connection, \
    ResponseError
import test.functional as tf


class TestSwiftOnFileEnv:
    @classmethod
    def setUp(cls):
        cls.conn = Connection(tf.config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, tf.config.get('account',
                                                      tf.config['username']))
        cls.root_dir = os.path.join('/mnt/swiftonfile/test')
        cls.account.delete_containers()

        cls.file_size = 8
        cls.container = cls.account.container(Utils.create_name())
        if not cls.container.create():
            raise ResponseError(cls.conn.response)

        cls.dirs = [
            'dir1',
            'dir2',
            'dir1/subdir1',
            'dir1/subdir2',
            'dir1/subdir1/subsubdir1',
            'dir1/subdir1/subsubdir2',
            'dir1/subdir with spaces',
            'dir1/subdir+with{whatever',
        ]

        cls.files = [
            'file1',
            'file A',
            'dir1/file2',
            'dir1/subdir1/file2',
            'dir1/subdir1/file3',
            'dir1/subdir1/file4',
            'dir1/subdir1/subsubdir1/file5',
            'dir1/subdir1/subsubdir1/file6',
            'dir1/subdir1/subsubdir1/file7',
            'dir1/subdir1/subsubdir1/file8',
            'dir1/subdir1/subsubdir2/file9',
            'dir1/subdir1/subsubdir2/file0',
            'dir1/subdir with spaces/file B',
            'dir1/subdir+with{whatever/file D',
        ]

        stored_files = set()
        for d in cls.dirs:
            file = cls.container.file(d)
            file.write(hdrs={'Content-Type': 'application/directory'})
        for f in cls.files:
            file = cls.container.file(f)
            file.write_random(cls.file_size, hdrs={'Content-Type':
                              'application/octet-stream'})
            stored_files.add(f)
        cls.stored_files = sorted(stored_files)
        cls.sorted_objects = sorted(set(cls.dirs + cls.files))


class TestSwiftOnFile(Base):
    env = TestSwiftOnFileEnv
    set_up = False

    @classmethod
    def tearDownClass(self):
        self.env.account.delete_containers()
        for account_dir in os.listdir(self.env.root_dir):
            rmtree(os.path.join(self.env.root_dir, account_dir))

    def testObjectsFromMountPoint(self):
        found_files = []
        found_dirs = []

        def recurse_path(path, count=0):
            if count > 10:
                raise ValueError('too deep recursion')
            self.assert_(os.path.exists(path))
            for file in os.listdir(path):
                if os.path.isdir(os.path.join(path, file)):
                    recurse_path(os.path.join(path, file), count + 1)
                    found_dirs.append(file)
                elif os.path.isfile(os.path.join(path, file)):
                    filename = os.path.join(os.path.relpath(path, os.path.join(
                        self.env.root_dir, 'AUTH_' + self.env.account.name,
                        self.env.container.name)), file)
                    if re.match('^[\.]', filename):
                        filename = filename[2:]
                    found_files.append(filename)
                else:
                    pass  # Just a Place holder

        recurse_path(os.path.join(self.env.root_dir,
                                  'AUTH_' + self.env.account.name,
                                  self.env.container.name))
        for file in self.env.stored_files:
                self.assert_(file in found_files)
                self.assert_(file not in found_dirs)

    def testObjectContentFromMountPoint(self):
        file_name = Utils.create_name()
        file_item = self.env.container.file(file_name)
        file_item.write_random()
        self.assert_status(201)
        file_info = file_item.info()
        fhOnMountPoint = open(os.path.join(
                              self.env.root_dir,
                              'AUTH_' + self.env.account.name,
                              self.env.container.name,
                              file_name), 'r')
        data_read_from_mountP = fhOnMountPoint.read()
        md5_returned = hashlib.md5(data_read_from_mountP).hexdigest()
        self.assertEquals(md5_returned, file_info['etag'])
        fhOnMountPoint.close()

    def test_GET_on_file_created_over_mountpoint(self):
        file_name = Utils.create_name()

        # Create a file over mountpoint
        file_path = os.path.join(self.env.root_dir,
                                 'AUTH_' + self.env.account.name,
                                 self.env.container.name, file_name)

        data = "I'm whatever Gotham needs me to be."
        data_hash = hashlib.md5(data).hexdigest()

        with open(file_path, 'w') as f:
            f.write(data)

        # Access the file over Swift as an object
        object_item = self.env.container.file(file_name)
        self.assert_(data == object_item.read())
        self.assert_status(200)

        # Confirm that Etag is present in response headers
        self.assert_(data_hash == object_item.info()['etag'])
        self.assert_status(200)

    def testObjectNameConstraints(self):
        valid_object_names = ["a/b/c/d",
                              '/'.join(("1@3%&*0-", "};+=]|")),
                              '/'.join(('a' * 20, 'b' * 20, 'c' * 20))]
        for object_name in valid_object_names:
            file_item = self.env.container.file(object_name)
            file_item.write_random()
            self.assert_status(201)

        invalid_object_names = ["a/./b",
                                "a/b/../d",
                                "a//b",
                                "a/c//",
                                '/'.join(('a' * 256, 'b' * 255, 'c' * 221)),
                                '/'.join(('a' * 255, 'b' * 255, 'c' * 222))]

        for object_name in invalid_object_names:
            file_item = self.env.container.file(object_name)
            self.assertRaises(ResponseError, file_item.write) # 503 or 400
