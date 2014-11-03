# Copyright (c) 2014 Red Hat, Inc.
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
import time

from swift.common.manager import Manager
from swift.common.internal_client import InternalClient

from test.functional.tests import Base, config, Utils
from test.functional.swift_test_client import Account, Connection, \
    ResponseError


class TestObjectExpirerEnv:
    @classmethod
    def setUp(cls):
        cls.conn = Connection(config)
        cls.conn.authenticate()
        cls.account = Account(cls.conn,
                              config.get('account',
                              config['username']))
        cls.account.delete_containers()
        cls.container = cls.account.container(Utils.create_name())
        if not cls.container.create():
            raise ResponseError(cls.conn.response)
        cls.file_size = 8
        cls.root_dir = os.path.join('/mnt/gluster-object',
                                cls.account.conn.storage_url.split('/')[2].split('_')[1])
        cls.client = InternalClient('/etc/swift/object-expirer.conf',
                                     'Test Object Expirer', 1)
        cls.expirer = Manager(['object-expirer'])


class TestObjectExpirer(Base):
    env = TestObjectExpirerEnv
    set_up = False

    def test_object_expiry_X_Delete_At_PUT(self):
        obj = self.env.container.file(Utils.create_name())
        x_delete_at = str(int(time.time()) + 2)
        obj.write_random(self.env.file_size,
                         hdrs={'X-Delete-At': x_delete_at})

        # Object is not expired. Should still be accessible.
        obj.read()
        self.assert_status(200)

        # Ensure X-Delete-At is saved as object metadata.
        self.assertEqual(x_delete_at, str(obj.info()['x_delete_at']))

        # Wait for object to be expired.
        time.sleep(3)

        # Object has expired. Should no longer be accessible.
        self.assertRaises(ResponseError, obj.read)
        self.assert_status(404)

        # Object should still be present on filesystem.
        self.assertTrue(os.path.isfile(os.path.join(self.env.root_dir,
                                                    self.env.container.name,
                                                    obj.name)))

        # But, GET on container should list the expired object.
        result = self.env.container.files()
        self.assertTrue(obj.name in self.env.container.files())

        # Check existence of corresponding tracker object in gsexpiring
        # account.
        enteredLoop = False
        for c in self.env.client.iter_containers("gsexpiring"):
            for o in self.env.client.iter_objects("gsexpiring", c['name']):
                enteredLoop = True
                l = o['name'].split('/')
                self.assertTrue(l[0].endswith('AUTH_' + self.env.account.name))
                self.assertEqual(l[1], self.env.container.name)
                self.assertEqual(l[2], obj.name)
        if not enteredLoop:
            self.fail("Tracker object not found.")

        # Run expirer daemon once.
        self.env.expirer.once()

        # Ensure object is physically deleted from filesystem.
        self.assertFalse(os.path.exists(os.path.join(self.env.root_dir,
                                                     self.env.container.name,
                                                     obj.name)))

        # Ensure tracker object is consumed.
        try:
            self.env.client.iter_containers("gsexpiring").next()
        except StopIteration:
            pass
        else:
            self.fail("Tracker object persists!")

        # GET on container should no longer list the object.
        self.assertFalse(obj.name in self.env.container.files())

    def test_object_expiry_X_Delete_After_PUT(self):
        obj = self.env.container.file(Utils.create_name())
        obj.write_random(self.env.file_size,
                         hdrs={'X-Delete-After': 2})

        # Object is not expired. Should still be accessible.
        obj.read()
        self.assert_status(200)

        # Ensure X-Delete-At is saved as object metadata.
        self.assertTrue(str(obj.info()['x_delete_at']))

        # Wait for object to be expired.
        time.sleep(3)

        # Object has expired. Should no longer be accessible.
        self.assertRaises(ResponseError, obj.read)
        self.assert_status(404)

        # Object should still be present on filesystem.
        self.assertTrue(os.path.isfile(os.path.join(self.env.root_dir,
                                                    self.env.container.name,
                                                    obj.name)))

        # But, GET on container should list the expired object.
        result = self.env.container.files()
        self.assertTrue(obj.name in self.env.container.files())

        # Check existence of corresponding tracker object in gsexpiring
        # account.
        enteredLoop = False
        for c in self.env.client.iter_containers("gsexpiring"):
            for o in self.env.client.iter_objects("gsexpiring", c['name']):
                enteredLoop = True
                l = o['name'].split('/')
                self.assertTrue(l[0].endswith('AUTH_' + self.env.account.name))
                self.assertEqual(l[1], self.env.container.name)
                self.assertEqual(l[2], obj.name)
        if not enteredLoop:
            self.fail("Tracker object not found.")

        # Run expirer daemon once.
        self.env.expirer.once()

        # Ensure object is physically deleted from filesystem.
        self.assertFalse(os.path.exists(os.path.join(self.env.root_dir,
                                                     self.env.container.name,
                                                     obj.name)))

        # Ensure tracker object is consumed.
        try:
            self.env.client.iter_containers("gsexpiring").next()
        except StopIteration:
            pass
        else:
            self.fail("Tracker object persists!")

        # GET on container should no longer list the object.
        self.assertFalse(obj.name in self.env.container.files())


    def test_object_expiry_X_Delete_At_POST(self):

        # Create normal object
        obj = self.env.container.file(Utils.create_name())
        obj.write_random(self.env.file_size)
        obj.read()
        self.assert_status(200)

        # Send POST on that object and set it to be expired.
        x_delete_at = str(int(time.time()) + 2)
        obj.sync_metadata(metadata={'X-Delete-At': x_delete_at},
                          cfg={'x_delete_at': x_delete_at})

        # Ensure X-Delete-At is saved as object metadata.
        self.assertEqual(x_delete_at, str(obj.info()['x_delete_at']))

        # Object is not expired. Should still be accessible.
        obj.read()
        self.assert_status(200)

        # Wait for object to be expired.
        time.sleep(3)

        # Object has expired. Should no longer be accessible.
        self.assertRaises(ResponseError, obj.read)
        self.assert_status(404)

        # Object should still be present on filesystem.
        self.assertTrue(os.path.isfile(os.path.join(self.env.root_dir,
                                                    self.env.container.name,
                                                    obj.name)))

        # But, GET on container should list the expired object.
        result = self.env.container.files()
        self.assertTrue(obj.name in self.env.container.files())

        # Check existence of corresponding tracker object in gsexpiring
        # account.

        enteredLoop = False
        for c in self.env.client.iter_containers("gsexpiring"):
            for o in self.env.client.iter_objects("gsexpiring", c['name']):
                enteredLoop = True
                l = o['name'].split('/')
                self.assertTrue(l[0].endswith('AUTH_' + self.env.account.name))
                self.assertEqual(l[1], self.env.container.name)
                self.assertEqual(l[2], obj.name)
        if not enteredLoop:
            self.fail("Tracker object not found.")

        # Run expirer daemon once.
        self.env.expirer.once()
        time.sleep(3)

        # Ensure object is physically deleted from filesystem.
        self.assertFalse(os.path.exists(os.path.join(self.env.root_dir,
                                                     self.env.container.name,
                                                     obj.name)))

        # Ensure tracker object is consumed.
        try:
            self.env.client.iter_containers("gsexpiring").next()
        except StopIteration:
            pass
        else:
            self.fail("Tracker object persists!")

        # GET on container should no longer list the object.
        self.assertFalse(obj.name in self.env.container.files())


    def test_object_expiry_X_Delete_After_POST(self):

        # Create normal object
        obj = self.env.container.file(Utils.create_name())
        obj.write_random(self.env.file_size)
        obj.read()
        self.assert_status(200)

        # Send POST on that object and set it to be expired.
        obj.sync_metadata(metadata={'X-Delete-After': 2},
                          cfg={'x_delete_after': 2})

        # Ensure X-Delete-At is saved as object metadata.
        self.assertTrue(str(obj.info()['x_delete_at']))

        # Object is not expired. Should still be accessible.
        obj.read()
        self.assert_status(200)

        # Wait for object to be expired.
        time.sleep(3)

        # Object has expired. Should no longer be accessible.
        self.assertRaises(ResponseError, obj.read)
        self.assert_status(404)

        # Object should still be present on filesystem.
        self.assertTrue(os.path.isfile(os.path.join(self.env.root_dir,
                                                    self.env.container.name,
                                                    obj.name)))

        # But, GET on container should list the expired object.
        result = self.env.container.files()
        self.assertTrue(obj.name in self.env.container.files())

        # Check existence of corresponding tracker object in gsexpiring
        # account.

        enteredLoop = False
        for c in self.env.client.iter_containers("gsexpiring"):
            for o in self.env.client.iter_objects("gsexpiring", c['name']):
                enteredLoop = True
                l = o['name'].split('/')
                self.assertTrue(l[0].endswith('AUTH_' + self.env.account.name))
                self.assertEqual(l[1], self.env.container.name)
                self.assertEqual(l[2], obj.name)
        if not enteredLoop:
            self.fail("Tracker object not found.")

        # Run expirer daemon once.
        self.env.expirer.once()
        time.sleep(3)

        # Ensure object is physically deleted from filesystem.
        self.assertFalse(os.path.exists(os.path.join(self.env.root_dir,
                                                     self.env.container.name,
                                                     obj.name)))

        # Ensure tracker object is consumed.
        try:
            self.env.client.iter_containers("gsexpiring").next()
        except StopIteration:
            pass
        else:
            self.fail("Tracker object persists!")

        # GET on container should no longer list the object.
        self.assertFalse(obj.name in self.env.container.files())


    def test_object_expiry_err(self):
        obj = self.env.container.file(Utils.create_name())

        # X-Delete-At is invalid or is in the past
        for i in (-2, 'abc', str(int(time.time()) - 2), 5.8):
            self.assertRaises(ResponseError,
                              obj.write_random,
                              self.env.file_size,
                              hdrs={'X-Delete-At': i})
            self.assert_status(400)

        # X-Delete-After is invalid.
        for i in (-2, 'abc', 3.7):
            self.assertRaises(ResponseError,
                              obj.write_random,
                              self.env.file_size,
                              hdrs={'X-Delete-After': i})
            self.assert_status(400)


