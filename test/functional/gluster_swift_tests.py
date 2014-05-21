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

import random
import time
import os,sys,re,hashlib
from nose import SkipTest

from test.functional.tests import config, locale, Base, Base2, Utils, \
    TestFileEnv
from test.functional.swift_test_client import Account, Connection, File, \
    ResponseError

web_front_end = config.get('web_front_end', 'integral')

class TestFile(Base):
    env = TestFileEnv
    set_up = False

    def testObjectManifest(self):
        if (web_front_end == 'apache2'):
            raise SkipTest()
        data = File.random_data(10000)
        parts = random.randrange(2,10)
        charsEachPart = len(data)/parts
        for i in range(parts+1):
            if i==0 :
                file = self.env.container.file('objectmanifest')
                hdrs={}
                hdrs['Content-Length']='0'
                hdrs['X-Object-Manifest']=str(self.env.container.name)+'/objectmanifest'
                self.assert_(file.write('',hdrs=hdrs))
                self.assert_(file.name in self.env.container.files())
                self.assert_(file.read() == '')
            elif i==parts :
                file = self.env.container.file('objectmanifest'+'-'+str(i))
                segment=data[ (i-1)*charsEachPart :]
                self.assertTrue(file.write(segment))
            else :
                file = self.env.container.file('objectmanifest'+'-'+str(i))
                segment=data[ (i-1)*charsEachPart : i*charsEachPart]
                self.assertTrue(file.write(segment))
        #matching the manifest file content with orignal data, as etag won't match
        file = self.env.container.file('objectmanifest')
        data_read = file.read()
        self.assertEquals(data,data_read)

    def test_PUT_large_object(self):
        file_item = self.env.container.file(Utils.create_name())
        data = File.random_data(1024 * 1024 * 2)
        self.assertTrue(file_item.write(data))
        self.assert_status(201)
        self.assertTrue(data == file_item.read())
        self.assert_status(200)

    def testInvalidHeadersPUT(self):
        #TODO: Although we now support x-delete-at and x-delete-after,
        #retained this test case as we may add some other header to
        #unsupported list in future
        raise SkipTest()
        file = self.env.container.file(Utils.create_name())
        self.assertRaises(ResponseError,
                          file.write_random,
                          self.env.file_size,
                          hdrs={'X-Delete-At': '9876545321'})
        self.assert_status(400)
        self.assertRaises(ResponseError,
                          file.write_random,
                          self.env.file_size,
                          hdrs={'X-Delete-After': '60'})
        self.assert_status(400)

    def testInvalidHeadersPOST(self):
        #TODO: Although we now support x-delete-at and x-delete-after,
        #retained this test case as we may add some other header to
        #unsupported list in future
        raise SkipTest()
        file = self.env.container.file(Utils.create_name())
        file.write_random(self.env.file_size)
        headers = file.make_headers(cfg={})
        headers.update({ 'X-Delete-At' : '987654321'})
        # Need to call conn.make_request instead of file.sync_metadata
        # because sync_metadata calls make_headers.  make_headers()
        # overwrites any headers in file.metadata as 'user' metadata
        # by appending 'X-Object-Meta-' to any of the headers
        # in file.metadata.
        file.conn.make_request('POST', file.path, hdrs=headers, cfg={})
        self.assertEqual(400, file.conn.response.status)

        headers = file.make_headers(cfg={})
        headers.update({ 'X-Delete-After' : '60'})
        file.conn.make_request('POST', file.path, hdrs=headers, cfg={})
        self.assertEqual(400, file.conn.response.status)


class TestFileUTF8(Base2, TestFile):
    set_up = False


class TestContainerPathsEnv:
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


class TestContainerPaths(Base):
    env = TestContainerPathsEnv
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


class TestObjectVersioningEnv:
    @classmethod
    def setUp(cls):
        cls.conn = Connection(config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, config.get('account',
                                                   config['username']))
        cls.account.delete_containers()
        cls.containers = {}
        #create two containers one for object other for versions of objects
        for i in range(2):
            hdrs={}
            if i==0:
                hdrs={'X-Versions-Location':'versions'}
                cont = cls.containers['object'] = cls.account.container('object')
            else:
                cont = cls.containers['versions'] = cls.account.container('versions')
            if not cont.create(hdrs=hdrs):
                raise ResponseError(cls.conn.response)
                cls.containers.append(cont)


class TestObjectVersioning(Base):
    env = TestObjectVersioningEnv
    set_up = False

    def testObjectVersioning(self):
        versions = random.randrange(2,10)
        dataArr=[]
        #create versions
        for i in range(versions):
            data = File.random_data(10000*(i+1))
            file = self.env.containers['object'].file('object')
            self.assertTrue(file.write(data))
            dataArr.append(data)
        cont = self.env.containers['versions']
        info = cont.info()
        self.assertEquals(info['object_count'], versions-1)
        #match the current version of object with data in arr and delete it
        for i in range(versions):
            data = dataArr[-(i+1)]
            file = self.env.containers['object'].file('object')
            self.assertEquals(data,file.read())
            self.assert_(file.delete())
            self.assert_status(204)


class TestMultiProtocolAccessEnv:
    @classmethod
    def setUp(cls):
        cls.conn = Connection(config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn, config.get('account',
                                                   config['username']))
	cls.root_dir = os.path.join('/mnt/gluster-object',cls.account.conn.storage_url.split('/')[2].split('_')[1])
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


class TestMultiProtocolAccess(Base):
    env = TestMultiProtocolAccessEnv
    set_up = False

    def testObjectsFromMountPoint(self):
        found_files = []
        found_dirs = []

        def recurse_path(path, count=0):
            if count > 10:
                raise ValueError('too deep recursion')
            self.assert_(os.path.exists(path))
            for file in os.listdir(path):
                if os.path.isdir(os.path.join(path,file)):
                    recurse_path(os.path.join(path,file), count + 1)
                    found_dirs.append(file)
                elif os.path.isfile(os.path.join(path,file)):
                    filename=os.path.join(os.path.relpath(path,os.path.join(self.env.root_dir,self.env.container.name)),file)
                    if re.match('^[\.]',filename):
                        filename=filename[2:]
                    found_files.append(filename)
                else:
                    pass #Just a Place holder

        recurse_path(os.path.join(self.env.root_dir,self.env.container.name))
        for file in self.env.stored_files:
                self.assert_(file in found_files)
                self.assert_(file not in found_dirs)

    def testObjectContentFromMountPoint(self):
        file_name = Utils.create_name()
        file_item = self.env.container.file(file_name)
        data = file_item.write_random()
        self.assert_status(201)
        file_info = file_item.info()
        fhOnMountPoint = open(os.path.join(self.env.root_dir,self.env.container.name,file_name),'r')
        data_read_from_mountP = fhOnMountPoint.read()
        md5_returned = hashlib.md5(data_read_from_mountP).hexdigest()
        self.assertEquals(md5_returned,file_info['etag'])
        fhOnMountPoint.close()
