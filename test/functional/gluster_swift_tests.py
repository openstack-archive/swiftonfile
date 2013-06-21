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

""" OpenStack Swift based functional tests for Gluster for Swift"""

from test.functional.tests import config, locale, Base, Utils
from test.functional.swift_test_client import Account, Connection, File, \
    ResponseError


class TestGlusterContainerPathsEnv:
    @classmethod
    def setUp(cls):
        cls.conn = Connection(config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, config.get('account',
                                                   config['username']))
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


class TestGlusterContainerPaths(Base):
    env = TestGlusterContainerPathsEnv
    set_up = False

    def testTraverseContainer(self):
        found_files = []
        found_dirs = []

        def recurse_path(path, count=0):
            if count > 10:
                raise ValueError('too deep recursion')

            for file in self.env.container.files(parms={'path': path}):
                self.assert_(file.startswith(path))
                if file in self.env.dirs:
                    recurse_path(file, count + 1)
                    found_dirs.append(file)
                else:
                    found_files.append(file)

        recurse_path('')
        for file in self.env.stored_files:
                self.assert_(file in found_files)
                self.assert_(file not in found_dirs)


    def testContainerListing(self):
        for format in (None, 'json', 'xml'):
            files = self.env.container.files(parms={'format': format})
            self.assertFalse(len(files) == 0)

            if isinstance(files[0], dict):
                files = [str(x['name']) for x in files]

            self.assertEquals(files, self.env.sorted_objects)

        for format in ('json', 'xml'):
            for file in self.env.container.files(parms={'format': format}):
                self.assert_(int(file['bytes']) >= 0)
                self.assert_('last_modified' in file)
                if file['name'] in self.env.dirs:
                    self.assertEquals(file['content_type'],
                                      'application/directory')
                else:
                    self.assertEquals(file['content_type'],
                            'application/octet-stream')

    def testStructure(self):
        def assert_listing(path, list):
            files = self.env.container.files(parms={'path': path})
            self.assertEquals(sorted(list, cmp=locale.strcoll), files)

        assert_listing('', ['file1', 'dir1', 'dir2', 'file A'])
        assert_listing('dir1', ['dir1/file2', 'dir1/subdir1',
                                'dir1/subdir2', 'dir1/subdir with spaces',
                                'dir1/subdir+with{whatever'])
        assert_listing('dir1/subdir1',
                       ['dir1/subdir1/file4', 'dir1/subdir1/subsubdir2',
                        'dir1/subdir1/file2', 'dir1/subdir1/file3',
                        'dir1/subdir1/subsubdir1'])
        assert_listing('dir1/subdir1/subsubdir1',
                       ['dir1/subdir1/subsubdir1/file7',
                        'dir1/subdir1/subsubdir1/file5',
                        'dir1/subdir1/subsubdir1/file8',
                        'dir1/subdir1/subsubdir1/file6'])
        assert_listing('dir1/subdir1/subsubdir1',
                       ['dir1/subdir1/subsubdir1/file7',
                        'dir1/subdir1/subsubdir1/file5',
                        'dir1/subdir1/subsubdir1/file8',
                        'dir1/subdir1/subsubdir1/file6'])
        assert_listing('dir1/subdir with spaces',
                       ['dir1/subdir with spaces/file B'])

