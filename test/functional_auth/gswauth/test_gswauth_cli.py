#!/usr/bin/python

# Copyright (c) 2010-2012 OpenStack Foundation
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

import unittest
from nose import SkipTest
import commands
import os
from test import get_config

config = get_config('func_test')

class Utils:

    @classmethod
    def addAccount(self,account_name,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-add-account %s -A %s -U %s -K %s' % (account_name,authurl, user, key))

    @classmethod
    def deleteAccount(self,account_name,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-delete-account %s -A %s -U %s -K %s' % (account_name,authurl, user, key))

    @classmethod
    def listAccounts(self,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-list -A %s -U %s -K %s' % (authurl, user, key))

    @classmethod
    def swauthPrep(self,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-prep -A %s -U %s -K %s' % (authurl, user, key))

    @classmethod
    def addAdminUser(self,account_name,username,password,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-add-user -a %s %s %s -A %s -U %s -K %s'% (account_name,username,password,authurl, user, key))

    @classmethod
    def addUser(self,account_name,username,password,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-add-user %s %s %s -A %s -U %s -K %s'% (account_name,username,password,authurl, user, key))

    @classmethod
    def addResellerAdminUser(self,account_name,username,password,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-add-user -r %s %s %s -A %s -U %s -K %s'% (account_name, username, password, authurl, user, key))

    @classmethod
    def deleteUser(self,account_name,username,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-delete-user %s %s -A %s -U %s -K %s'% (account_name, username, authurl, user, key))

    @classmethod
    def cleanAll(self):
        #TODO:It's a dirty hack,any suggestions?
        commands.getstatusoutput('sudo rm -rf '+os.path.join(config['devices'], config['gsmetadata_volume'], '*'))
        return commands.getstatusoutput('sudo rm -rf '+os.path.join(config['devices'], config['gsmetadata_volume'], '.*'))


class TestSwauthPrep(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        Utils.cleanAll()

    def testSwauthPrep(self):
        (status,output)=Utils.swauthPrep()
        self.assertEqual(status, 0, 'swauth prep failed with valid credentials'+output)

        (status,output)=Utils.swauthPrep(key='')
        self.assertEqual('Usage' in output,True, 'Invalid swauth-prep request accepted(no key provided): '+output)

        (status,output)=Utils.swauthPrep(key='notavalidkey')
        self.assertNotEqual(status, 0, 'Invalid swauth-prep request accepted(wrong key provided):'+output)
        self.assertEqual('gswauth preparation failed: 401 Unauthorized: Invalid user/key provided' in output,True, 'Invalid\
         swauth-prep request accepted: '+output)
        #TODO:More cases for invalid url and admin user


class TestAccount(unittest.TestCase):

    def setUp(self):
        (status,output)=Utils.swauthPrep()
        self.assertEqual(status, 0, 'setup swauth-prep failed'+output)

    def tearDown(self):
        Utils.cleanAll()

    def setTestDeleteAccountEnv(self):
        #add some account
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv failed'+output)

        (status,output)=Utils.addAccount('test2')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv failed'+output)

        #add some user to this account
        (status,output) = Utils.addAdminUser('test2','tester','testing')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

        (status,output) = Utils.addUser('test2','tester2','testing2')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

        (status,output) = Utils.addResellerAdminUser('test2','tester3','testing3')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

    def testAddAccount(self):
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'account creation failed'+output)

        (status,output)=Utils.addAccount('accountvolumedoesnotexist')
        #TODO:decide on expected behavior,currently it creates it
        self.assertEqual(status, 0, 'account creation failed std err was: '+output)

        (status,output)=Utils.addAccount('testnokey',key='')
        #self.assertEqual(status, 0, 'account creation failed std err was: '+output)
        self.assertEqual('Usage:' in output, True, 'Invalid account creation request accepted : '+output)

        (status,output)=Utils.addAccount('testinvalidkey',key='invalidkey')
        #self.assertEqual(status, 0, 'account creation failed std err was: '+output)
        #assert for better error message 403 Forbidden, Invalid user/key would be good to have
        self.assertEqual('Account creation failed: 401 Unauthorized: Invalid user/key provided' in output,True, 'Invalid account creation request accepted: '+output)

        (status,output) = Utils.addUser('test','tester','testing')
        (status,output)=Utils.addAccount('test2',user='test:tester',key='testing')
        self.assertEqual('Account creation failed: 403 Forbidden: Insufficient privileges' in output,True, 'Invalid account creation request accepted: '+output)
        #TODO:more cases?

    def testDeleteAccount(self):
        self.setTestDeleteAccountEnv()

        #valid request to delete an account with no users
        (status,output)=Utils.deleteAccount('test')
        self.assertEqual(status, 0, 'account deletion failed for test account'+output)

        #Invalid request to delete an account with users
        (status,output)=Utils.deleteAccount('test2')
        self.assertNotEqual(status, 0, 'account deletion failed for test2 account'+output)
        self.assertEqual('Delete account failed: 409 Conflict: Account test2 contains active users. Delete all users first.' in output,True,
        'account deletion failed for test account'+output)

        #delete all users in above account and then try again
        (status,output) = Utils.deleteUser('test2','tester')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

        (status,output) = Utils.deleteUser('test2','tester2')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

        (status,output) = Utils.deleteUser('test2','tester3')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

        (status,output) = Utils.addUser('test','tester','testing')
        (status,output) = Utils.deleteAccount('test2',user='test:tester',key='testing')
        self.assertEqual('Delete account failed: 403 Forbidden: Insufficient privileges' in output,True, 'account deletion failed for test2 account'+output)

        (status,output) = Utils.deleteAccount('test2',key='invalidkey')
        self.assertEqual('Delete account failed: 401 Unauthorized: Invalid user/key provided' in output,True, 'account deletion failed for test2 account'+output)

        (status,output)=Utils.deleteAccount('test2')
        self.assertEqual(status, 0, 'account deletion failed for test2 account'+output)

        (status,output)=Utils.deleteAccount('accountdoesnotexist')
        self.assertNotEqual(status, 0, 'account deletion failed for accountdoesnotexist'+output)
        self.assertEqual('Delete account failed: 404 Not Found: Account accountdoesnotexist does not exist' in output,True, 'account deletion failed for test\
         account'+output)
        #TODO:more cases

    def testListAcounts(self):
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'account creation failed'+output)

        (status,output)=Utils.listAccounts()
        self.assertEqual(output,
            '+----------+\n| Accounts |\n+----------+\n|   test   |\n+----------+',
            'swauth-list failed:\n%s' % output)


class TestUser(unittest.TestCase):

    def setUp(self):
        (status,output)=Utils.swauthPrep()
        self.assertEqual(status, 0, 'setup swauth-prep failed'+output)

    def tearDown(self):
        Utils.cleanAll()

    def setTestaddAdminUserEnv(self):
        #add test account
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'setTestaddAdminUserEnv (add test account) failed'+output)

    def setTestDeleteUserEnv(self):
        #add test account
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'setTestaddAdminUserEnv (add test account) failed'+output)

        (status,output) = Utils.addAdminUser('test','testadminuser','testadminuser')
        self.assertEqual(status, 0, 'user addition failed'+output)

        (status,output) = Utils.addUser('test','testuser','testuser')
        self.assertEqual(status, 0, 'user addition failed'+output)

        (status,output) = Utils.addResellerAdminUser('test','testreselleradminuser','testreselleradminuser')
        self.assertEqual(status, 0, 'user addition failed'+output)

    def testaddAdminUser(self):
        #set the env for test
        self.setTestaddAdminUserEnv()

        (status,output) = Utils.addAdminUser('test','testadminuser','testadminuser')
        self.assertEqual(status, 0, 'user addition failed'+output)

        (status,output) = Utils.addUser('test','testuser','testuser')
        self.assertEqual(status, 0, 'user addition failed'+output)

        (status,output) = Utils.addResellerAdminUser('test','testreselleradminuser','testreselleradminuser')
        self.assertEqual(status, 0, 'user addition failed'+output)

        (status,output) = Utils.addAdminUser('test', '', '')
        self.assertEqual('Usage:' in output, True, 'Invalid user creation request accepted: '+output)

        (status,output) = Utils.addAdminUser('test', 'testcli', '')
        self.assertEqual('Usage:' in output, True, 'Invalid user creation request accepted'+output)

        (status,output) = Utils.addAdminUser('test', '', 'testcli')
        self.assertEqual('Usage:' in output, True, 'Invalid user creation request accepted'+output)

        (status,output) = Utils.addAdminUser('accountdoesnotexist', 'testcli', 'testcli')
        #TODO: decide on behavior,below is just place holder, right now it accepts this request and create both user and account
        self.assertEqual(status, 0, 'Invalid user creation request accepted,accountdoesnotexist: '+output)

        (status,output) = Utils.addUser('test','testuser2','testuser2',user='test:testuser',key='testuser')
        self.assertEqual('User creation failed: 403 Forbidden: Insufficient privileges' in output, True, 'user addition failed'+output)

        (status,output) = Utils.addUser('test','testuser2','testuser2',user='test:testadminuser',key='invalidkey')
        self.assertEqual('User creation failed: 401 Unauthorized: Invalid user/key provided' in output, True, 'user addition failed'+output)
        #TODO: more test cases?

    def testDeleteUser(self):
        #set the env for test
        self.setTestDeleteUserEnv()

        (status,output) = Utils.deleteUser('test','testadminuser',user='test:testuser',key='testuser')
        self.assertEqual('Delete user failed: 403 Forbidden: Insufficient privileges' in output, True, 'user deletion failed'+output)

        (status,output) = Utils.deleteUser('test','testuser',key='invalidkey')
        self.assertEqual('Delete user failed: 401 Unauthorized: Invalid user/key provided' in output, True, 'user deletion failed'+output)

        (status,output) = Utils.deleteUser('test','testadminuser')
        self.assertEqual(status, 0, 'valid user deletion failed:'+output)

        (status,output) = Utils.deleteUser('test','testuser')
        self.assertEqual(status, 0, 'valid user deletion failed:'+output)

        (status,output) = Utils.deleteUser('test','testreselleradminuser')
        self.assertEqual(status, 0, 'valid user deletion failed:'+output)

        (status,output) = Utils.deleteUser('test', '')
        self.assertEqual('Usage:' in output, True, 'Invalid user deletion request accepted : '+output)

        (status,output) = Utils.deleteUser('','testcli')
        self.assertEqual('Usage:' in output, True, 'Invalid user deletion request accepted : '+output)

        (status,output) = Utils.deleteUser('test', 'userdoesnotexist')
        self.assertEqual('Delete user failed: 404 Not Found: User userdoesnotexist does not exist' in output, True, 'user deletion failed'+output)

        (status,output) = Utils.deleteUser('accountisnothere', 'testcli')
        self.assertEqual('Delete user failed: 404 Not Found: User testcli does not exist' in output, True, 'user deletion failed'+output)

        #TODO:more testcases?


