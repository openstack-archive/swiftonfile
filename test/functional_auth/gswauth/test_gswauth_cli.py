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
    def swauthPrep(self,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-prep -A %s -U %s -K %s' % (authurl, user, key))

    @classmethod
    def addAccount(self,account_name,suffix=None, authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        if suffix is not None:
            return commands.getstatusoutput('gswauth-add-account %s -s %s -A %s -U %s -K %s' % (account_name, suffix, authurl, user, key))
        else:
            return commands.getstatusoutput('gswauth-add-account %s -A %s -U %s -K %s' % (account_name, authurl, user, key))

    @classmethod
    def deleteAccount(self,account_name,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-delete-account %s -A %s -U %s -K %s' % (account_name, authurl, user, key))

    @classmethod
    def listAccounts(self,listtype=None,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        if listtype is not None:
            return commands.getstatusoutput('gswauth-list %s -A %s -U %s -K %s' % (listtype, authurl, user, key))
        else:
            return commands.getstatusoutput('gswauth-list -A %s -U %s -K %s' % (authurl, user, key))

    @classmethod
    def listUsers(self,account_name,listtype=None,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        if listtype is not None:
            return commands.getstatusoutput('gswauth-list %s %s -A %s -U %s -K %s'% (account_name, listtype, authurl, user, key))
        else:
            return commands.getstatusoutput('gswauth-list %s -A %s -U %s -K %s'% (account_name, authurl, user, key))

    @classmethod
    def addAdminUser(self,account_name,username,password,suffix=None,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        if suffix is not None:
            return commands.getstatusoutput('gswauth-add-user -a %s %s %s -s %s -A %s -U %s -K %s'% (account_name, username, password, suffix, authurl, user, key))
        else:
            return commands.getstatusoutput('gswauth-add-user -a %s %s %s -A %s -U %s -K %s'% (account_name, username, password, authurl, user, key))

    @classmethod
    def addUser(self,account_name,username,password,suffix=None,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        if suffix is not None:
            return commands.getstatusoutput('gswauth-add-user %s %s %s -s %s -A %s -U %s -K %s'% (account_name, username, password, suffix, authurl, user, key))
        else:
            return commands.getstatusoutput('gswauth-add-user %s %s %s -A %s -U %s -K %s'% (account_name, username, password, authurl, user, key))

    @classmethod
    def addResellerAdminUser(self,account_name,username,password,suffix=None,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        if suffix is not None:
            return commands.getstatusoutput('gswauth-add-user -r %s %s %s -s %s -A %s -U %s -K %s'% (account_name, username, password, suffix, authurl, user, key))
        else:
            return commands.getstatusoutput('gswauth-add-user -r %s %s %s -A %s -U %s -K %s'% (account_name, username, password, authurl, user, key))

    @classmethod
    def deleteUser(self,account_name,username,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-delete-user %s %s -A %s -U %s -K %s'% (account_name, username, authurl, user, key))

    @classmethod
    def listUserGroups(self,account_name,username,listtype=None,authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        if listtype is not None:
            return commands.getstatusoutput('gswauth-list %s %s %s -A %s -U %s -K %s'% (account_name, username, listtype, authurl, user, key))
        else:
            return commands.getstatusoutput('gswauth-list %s %s %s -A %s -U %s -K %s'% (account_name, username, listtype, authurl, user, key))

    @classmethod
    def cleanToken(self,option=None,value=None,authurl='http://127.0.0.1:8080/auth/', key=config['admin_key']):
        if option is None and value is None:
            return commands.getstatusoutput('gswauth-cleanup-tokens -A %s -K %s'% (authurl, key))
        elif option is not None and value is None:
            return commands.getstatusoutput('gswauth-cleanup-tokens --%s -A %s -K %s'% (option, authurl, key))
        else:
            return commands.getstatusoutput('gswauth-cleanup-tokens --%s %s -A %s -K %s'% (option, value, authurl, key))

    @classmethod
    def setAccountService(self, account, service, name, value, authurl='http://127.0.0.1:8080/auth/',user=config['admin_user'],key=config['admin_key']):
        return commands.getstatusoutput('gswauth-set-account-service %s %s %s %s -A %s -U %s -K %s'% (account, service, name, value, authurl, user, key))

    @classmethod
    def cleanAll(self):
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
        self.assertEqual('gswauth preparation failed: 401 Unauthorized: Invalid user/key provided' \
                         in output,True, 'Invalid swauth-prep request accepted: '+output)

        (status,output)=Utils.swauthPrep(authurl='http://127.0.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid swauth-prep request accepted(wrong admin-url provided): %s' % output)

        (status,output)=Utils.swauthPrep(authurl='http://127.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid swauth-prep request accepted(wrong admin-url provided): %s' % output)
        #TODO:More cases for invalid url and admin user

    def testAddAccountWithoutSwauthPrep(self):
        #Try to add account without running gswauth-prep
        Utils.cleanAll()
        (status,output)=Utils.addAccount('test')
        self.assertNotEqual(status, 0, 'account added without running gswauth-prep '+output)
        self.assertEqual('Account creation failed: 500 Server Error' \
                         in output,True, 'account added without running gswauth-prep '+output)


class TestAccount(unittest.TestCase):

    def setUp(self):
        (status,output)=Utils.swauthPrep()
        self.assertEqual(status, 0, 'setup swauth-prep failed'+output)

    def tearDown(self):
        Utils.cleanAll()

    def setTestAccUserEnv(self):
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addResellerAdminUser('test','re_admin','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addAdminUser('test','admin','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addUser('test','tester','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)

    def setTest2AccUserEnv(self):
        (status,output)=Utils.addAccount('test2')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addResellerAdminUser('test2','re_admin','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addAdminUser('test2','admin','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addUser('test2','tester','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)

    def testAddAccount(self):
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'account creation failed'+output)

        (status,output)=Utils.addAccount('accountvolumedoesnotexist')
        self.assertEqual(status, 0, 'account creation failed std err was: '+output)

        (status,output)=Utils.addAccount('testnokey',key='')
        self.assertEqual('Usage:' in output, True, 'Invalid account creation request accepted : '+output)

        (status,output)=Utils.addAccount('testinvalidkey',key='invalidkey')
        self.assertEqual('Account creation failed: 401 Unauthorized: Invalid user/key provided' \
                                         in output,True, 'Invalid account creation request accepted: '+output)

        (status,output)=Utils.addAccount('test2', authurl='http://127.0.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid account creation request accepted(wrong admin-url provided): %s' % output)

        (status,output)=Utils.addAccount('test2', authurl='http://127.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid account creation request accepted(wrong admin-url provided): %s' % output)

    def testAddAccountNonSuperAdminUsers(self):
        #set test account with all types of user
        self.setTestAccUserEnv()
        #try to add another account with all type of users
        (status,output)=Utils.addAccount('accbyreselleradmin',user='test:re_admin',key='testing')
        self.assertEqual(status, 0, 'account creation failed with re_admin user: '+output)

        (status,output)=Utils.addAccount('accbyadmin',user='test:admin',key='testing')
        self.assertNotEqual(status, 0, 'account creation success with admin user: '+output)
        self.assertEqual('Account creation failed: 403 Forbidden: Insufficient privileges' in output,True, 'account creation success with admin user: '+output)

        (status,output)=Utils.addAccount('accbyuser',user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 'account creation success with regular user: '+output)
        self.assertEqual('Account creation failed: 403 Forbidden: Insufficient privileges' \
                         in output,True, 'account creation success with regular user: '+output)

    def testDeleteAccount(self):
        #add test account with no users
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'account creation failed for test account'+output)

        #set test2 account with all type of users
        self.setTest2AccUserEnv()

        #valid request to delete an account with no users
        (status,output)=Utils.deleteAccount('test')
        self.assertEqual(status, 0, 'account deletion failed for test account'+output)

        #Invalid request to delete an account with users
        (status,output)=Utils.deleteAccount('test2')
        self.assertNotEqual(status, 0, 'account deletion succeeded for acc with active users'+output)
        self.assertEqual('Delete account failed: 409 Conflict: Account test2 contains active users. Delete all users first.' \
                         in output,True, 'account deletion failed for test account'+output)

        #delete all users in above account and then try again
        (status,output) = Utils.deleteUser('test2','tester')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

        (status,output) = Utils.deleteUser('test2','admin')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

        (status,output) = Utils.deleteUser('test2','re_admin')
        self.assertEqual(status, 0, 'setTestDeleteAccountEnv'+output)

        (status,output)=Utils.deleteAccount('test2')
        self.assertEqual(status, 0, 'account deletion failed for test2 account'+output)

        (status,output)=Utils.deleteAccount('accountdoesnotexist')
        self.assertNotEqual(status, 0, 'account deletion failed for accountdoesnotexist'+output)
        self.assertEqual('Delete account failed: 404 Not Found: Account accountdoesnotexist does not exist' in output,True, 'account deletion failed for test account'+output)

        (status,output)=Utils.deleteAccount('test3', authurl='http://127.0.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid deletion request accepted(wrong admin-url provided): %s' % output)

        (status,output)=Utils.deleteAccount('test3', authurl='http://127.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid deletion request accepted(wrong admin-url provided): %s' % output)

    def testDeleteAccountNonSuperAdminUsers(self):
        #set test account with all types of user
        self.setTestAccUserEnv()

        #try to add another account with all type of users
        Utils.addAccount('accbysuperadminforreadmin')
        (status,output)=Utils.deleteAccount('accbysuperadminforreadmin',user='test:re_admin',key='testing')
        self.assertEqual(status, 0, 'account deletion failed with re_admin user: '+output)

        #TODO:uncomment following case when fix is there
        '''
        Utils.addAccount('accbysuperadminforadmin')
        (status,output)=Utils.deleteAccount('accbysuperadminforadmin',user='test:admin',key='testing')
        self.assertNotEqual(status, 0, 'account deletion success with admin user: '+output)
        self.assertEqual('Delete account failed: 403 Forbidden: Insufficient privileges' \
                         in output,True, 'account deletion success with admin user: '+output)
        '''

        Utils.addAccount('accbysuperadminforuser')
        (status,output)=Utils.deleteAccount('accbysuperadminforuser',user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 'account creation success with regular user: '+output)
        self.assertEqual('Delete account failed: 403 Forbidden: Insufficient privileges' \
                         in output,True, 'account deletion success with regular user: '+output)

    def testListAcounts(self):
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'account creation failed'+output)

        (status,output)=Utils.listAccounts()
        self.assertEqual(output,
            '+----------+\n| Accounts |\n+----------+\n|   test   |\n+----------+',
            'swauth-list failed:\n%s' % output)

        (status,output)=Utils.listAccounts(authurl='http://127.0.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid list request accepted(wrong admin-url provided): %s' % output)

        (status,output)=Utils.listAccounts(authurl='http://127.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid list request accepted(wrong admin-url provided): %s' % output)

        (status,output)=Utils.listAccounts('-j')
        self.assertEqual(output,
            '{"accounts": [{"name": "test"}]}',
            'swauth-list failed for json option:\n%s' % output)

        (status,output)=Utils.listAccounts('-p')
        self.assertEqual(output,
            'test',
            'swauth-list failed for plain-text option:\n%s' % output)

    def testListAcountsNonSuperAdminUsers(self):
        #set test acc with all type of users
        self.setTestAccUserEnv()

        (status,output)=Utils.listAccounts(user='test:re_admin',key='testing')
        self.assertEqual(status, 0, 'account listing failed with re_admin user: '+output)
        self.assertEqual(output,
            '+----------+\n| Accounts |\n+----------+\n|   test   |\n+----------+',
            'swauth-list failed:\n%s' % output)

        (status,output)=Utils.listAccounts(user='test:admin',key='testing')
        self.assertNotEqual(status, 0, 'account listing success with admin user: '+output)
        self.assertEqual('List failed: 403 Forbidden: Insufficient privileges' \
                         in output,True, 'account listing success with admin user: '+output)

        (status,output)=Utils.listAccounts(user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 'account listing success with regular user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'account listing success with regular user: '+output)

class TestUser(unittest.TestCase):

    def setUp(self):
        (status,output)=Utils.swauthPrep()
        self.assertEqual(status, 0, 'setup swauth-prep failed'+output)

    def tearDown(self):
        Utils.cleanAll()

    def setTestAccUserEnv(self):
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addResellerAdminUser('test','re_admin','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addAdminUser('test','admin','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addUser('test','tester','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)

    def setTest2AccUserEnv(self):
        (status,output)=Utils.addAccount('test2')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addResellerAdminUser('test2','re_admin','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addAdminUser('test2','admin','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addUser('test2','tester','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)

    def testaddUser(self):
        #add test acc
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'setTestaddAdminUserEnv (add test account) failed'+output)

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
        self.assertEqual(status, 0, 'User creation request failed, where accountdoesnotexist: '+output)

        (status,output)=Utils.addAdminUser('test', 'admin2', 'adminpwd', authurl='http://127.0.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid add user request accepted(wrong admin-url provided): %s' % output)

        (status,output)=Utils.addAdminUser('test', 'admin2', 'adminpwd', authurl='http://127.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid add user request accepted(wrong admin-url provided): %s' % output)

    def testAddUserNonSuperAdminUsers (self):
        #setup test,testr accounts with all user types
        self.setTestAccUserEnv()
        self.setTest2AccUserEnv()

        #try to add another reseller_admin users with all type of users
        #TODO:Uncomment Following,Possible Bug:403 should be return instead of current 401
        '''
        (status,output)=Utils.addResellerAdminUser('test', 're_adminwithreadmin', 'testing', user='test:re_admin', key='testing')
        self.assertNotEqual(status, 0, 're_admin creation succeeded with re_admin user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin creation succeeded with re_admin user: '+output)

        (status,output)=Utils.addResellerAdminUser('test', 're_adminwithadmin', 'testing', user='test:admin', key='testing')
        self.assertNotEqual(status, 0, 're_admin creation succeeded with admin user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin creation succeeded with admin user: '+output)

        (status,output)=Utils.addResellerAdminUser('test', 're_adminwithuser', 'testing', user='test:tester', key='testing')
        self.assertNotEqual(status, 0, 're_admin creation succeeded with regular user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin creation succeeded with regular user: '+output)

        (status,output)=Utils.addResellerAdminUser('test2', 're_adminwithreadmin', 'testing', user='test:re_admin', key='testing')
        self.assertNotEqual(status, 0, 're_admin creation succeeded with re_admin user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin creation succeeded with re_admin user: '+output)

        (status,output)=Utils.addResellerAdminUser('test2', 're_adminwithadmin', 'testing', user='test:admin', key='testing')
        self.assertNotEqual(status, 0, 're_admin creation succeeded with admin user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin creation succeeded with admin user: '+output)

        (status,output)=Utils.addResellerAdminUser('test2', 're_adminwithuser', 'testing', user='test:tester', key='testing')
        self.assertNotEqual(status, 0, 're_admin creation succeeded with regular user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin creation succeeded with regular user: '+output)

        #update the password with own credential
        (status,output)=Utils.addResellerAdminUser('test', 're_adminwithreadmin', 'testingupdated', user='test:re_admin', key='testing')
        self.assertNotEqual(status, 0, 're_admin update password succeeded with own credentials: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin update password succeeded with own credentials: '+output)
        '''
        #try to add another admin users with all type of users
        (status,output)=Utils.addAdminUser('test', 'adminwithreadmin', 'testing', user='test:re_admin', key='testing')
        self.assertEqual(status, 0, 'admin creation failed with re_admin user: '+output)

        (status,output)=Utils.addAdminUser('test', 'adminwithreadmin', 'testing', user='test:admin', key='testing')
        self.assertEqual(status, 0, 'admin creation failed with admin user: '+output)

        (status,output)=Utils.addAdminUser('test', 'adminwithuser', 'testing', user='test:tester', key='testing')
        self.assertNotEqual(status, 0, 'admin creation succeeded with regular user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'admin creation succeeded with regular user: '+output)

        (status,output)=Utils.addAdminUser('test2', 'adminwithreadminofotheraccount', 'testing', user='test:re_admin', key='testing')
        self.assertEqual(status, 0, 'admin creation failed with re_admin user of other account: '+output)

        (status,output)=Utils.addAdminUser('test2', 'adminwithadminofotheraccount', 'testing', user='test:admin', key='testing')
        self.assertNotEqual(status, 0, 'admin creation succeeded with admin user of other acc: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'admin creation succeeded with admin user of other acc: '+output)

        (status,output)=Utils.addAdminUser('test2', 'adminwithuserfotheraccount', 'testing', user='test:tester', key='testing')
        self.assertNotEqual(status, 0, 'admin creation succeeded with user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'admin creation succeeded with user of other account: '+output)

        #update password of own admin account
        (status,output)=Utils.addAdminUser('test', 'admin', 'testingupdated', user='test:admin', key='testing')
        self.assertEqual(status, 0, 'admin password update failed with own credentials: '+output)
        #undo above password change
        (status,output)=Utils.addAdminUser('test', 'admin', 'testing', user='test:admin', key='testingupdated')
        self.assertEqual(status, 0, 'admin password update failed with own credentials: '+output)

        #try to add another regular users with all type of users
        (status,output)=Utils.addUser('test', 'adduserwithre_admin', 'testing', user='test:re_admin', key='testing')
        self.assertEqual(status, 0, 'regular user creation with re_admin credentials failed: '+output)

        (status,output)=Utils.addUser('test', 'adduserwithadmin', 'testing', user='test:admin', key='testing')
        self.assertEqual(status, 0, 'regular user creation with admin credentials failed: '+output)

        (status,output)=Utils.addUser('test', 'adduserwithuser', 'testing', user='test:tester', key='testing')
        self.assertNotEqual(status, 0, 'regular user creation with regular user credentials succeded: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'regular user creation with regular user credentials succeded: '+output)

        (status,output)=Utils.addUser('test2', 'adduserwithreadminofotheraccount', 'testing', user='test:re_admin', key='testing')
        self.assertEqual(status, 0, 'user creation failed with re_admin user of other account: '+output)

        (status,output)=Utils.addUser('test2', 'adduserwithadminofotheraccount', 'testing', user='test:admin', key='testing')
        self.assertNotEqual(status, 0, 'user creation succeeded with admin user of other acc: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'user creation succeeded with admin user of other acc: '+output)

        (status,output)=Utils.addUser('test2', 'adminwithuserfotheraccount', 'testing', user='test:tester', key='testing')
        self.assertNotEqual(status, 0, 'user creation succeeded with user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'user creation succeeded with user of other account: '+output)

    def testDeleteUser(self):
        #set test acc
        self.setTestAccUserEnv()

        (status,output) = Utils.deleteUser('test','admin')
        self.assertEqual(status, 0, 'valid user deletion failed:'+output)

        (status,output) = Utils.deleteUser('test','tester')
        self.assertEqual(status, 0, 'valid user deletion failed:'+output)

        (status,output) = Utils.deleteUser('test','re_admin')
        self.assertEqual(status, 0, 'valid user deletion failed:'+output)

        (status,output) = Utils.deleteUser('test', '')
        self.assertEqual('Usage:' in output, True, 'Invalid user deletion request accepted : '+output)

        (status,output) = Utils.deleteUser('','testcli')
        self.assertEqual('Usage:' in output, True, 'Invalid user deletion request accepted : '+output)

        (status,output) = Utils.deleteUser('test', 'userdoesnotexist')
        self.assertNotEqual(status, 0, 'Invalid user deletion request accepted,userdoesnotexist:'+output)

        (status,output) = Utils.deleteUser('accountisnothere', 'testcli')
        self.assertNotEqual(status, 0, 'Invalid user deletion request accepted, accountdoesnotexist:'+output)
        #TODO:more testcases?
        (status,output)=Utils.deleteUser('test', 'admin2', authurl='http://127.0.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid delete user request accepted(wrong admin-url provided): %s' % output)

        (status,output)=Utils.deleteUser('test', 'admin2', authurl='http://127.0.1:80/auth/')
        self.assertEqual('Check that the admin_url is valid' in output, True,
            'Invalid delete user request accepted(wrong admin-url provided): %s' % output)

    def testDeleteUserNonSuperAdminUsers(self):
        #set test, test2 acc with all type of users
        self.setTestAccUserEnv()
        self.setTest2AccUserEnv()
        #try to delete reseller_admin users with all type of users
        Utils.addResellerAdminUser('test', 're_admintobedeletedbyotherusers1', 'testing')
        (status,output) = Utils.deleteUser('test', 're_admintobedeletedbyotherusers1',user='test:re_admin',key='testing')
        self.assertNotEqual(status, 0, 're_admin deletion succeeded with re_admin user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin deletion succeeded with re_admin user: '+output)

        Utils.addResellerAdminUser('test', 're_admintobedeletedbyotherusers2', 'testing')
        (status,output) = Utils.deleteUser('test', 're_admintobedeletedbyotherusers2',user='test:admin',key='testing')
        self.assertNotEqual(status, 0, 're_admin deletion succeeded with admin user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin deletion succeeded with admin user: '+output)

        Utils.addResellerAdminUser('test', 're_admintobedeletedbyotherusers3', 'testing')
        (status,output) = Utils.deleteUser('test', 're_admintobedeletedbyotherusers3',user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 're_admin deletion succeeded with regular user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin deletion succeeded with user: '+output)

        Utils.addResellerAdminUser('test2', 're_admintobedeletedbyotheraccountusers1', 'testing')
        (status,output) = Utils.deleteUser('test2', 're_admintobedeletedbyotheraccountusers1',user='test:re_admin',key='testing')
        self.assertNotEqual(status, 0, 're_admin deletion succeeded with re_admin user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin deletion succeeded with re_admin user of other account: '+output)

        Utils.addResellerAdminUser('test2', 're_admintobedeletedbyotheraccountusers2', 'testing')
        (status,output) = Utils.deleteUser('test2', 're_admintobedeletedbyotheraccountusers2',user='test:admin',key='testing')
        self.assertNotEqual(status, 0, 're_admin deletion succeeded with admin user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin deletion succeeded with admin user of other account: '+output)

        Utils.addResellerAdminUser('test2', 're_admintobedeletedbyotheraccountusers3', 'testing')
        (status,output) = Utils.deleteUser('test2', 're_admintobedeletedbyotheraccountusers3',user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 're_admin deletion succeeded with regular user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 're_admin deletion succeeded with user of other account: '+output)

        #delete/de-active own re_admin account
        Utils.addAdminUser('test', 're_admintobedeletedbyitself', 'testing')
        (status,output) = Utils.deleteUser('test', 're_admintobedeletedbyitself',user='test:re_admintobedeletedbyitself',key='testing')
        self.assertEqual(status, 0, 're_admin deletion failed with own credentials : '+output)

        #try to delete admin users with all type of users
        Utils.addAdminUser('test', 'admintobedeletedbyotherusers1', 'testing')
        (status,output) = Utils.deleteUser('test', 'admintobedeletedbyotherusers1',user='test:re_admin',key='testing')
        self.assertEqual(status, 0, 'admin deletion failed with re_admin user: '+output)

        Utils.addAdminUser('test', 'admintobedeletedbyotherusers2', 'testing')
        (status,output) = Utils.deleteUser('test', 'admintobedeletedbyotherusers2',user='test:admin',key='testing')
        self.assertEqual(status, 0, 'admin deletion failed with admin user: '+output)

        Utils.addAdminUser('test', 'admintobedeletedbyotherusers3', 'testing')
        (status,output) = Utils.deleteUser('test', 'admintobedeletedbyotherusers3',user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 'admin deletion succeeded with regular user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'admin deletion succeeded with regular user: '+output)

        Utils.addAdminUser('test2', 'admintobedeletedbyotheraccountusers1', 'testing')
        (status,output) = Utils.deleteUser('test2', 'admintobedeletedbyotheraccountusers1',user='test:re_admin',key='testing')
        self.assertEqual(status, 0, 'admin deletion failed with re_admin user of other account: '+output)

        Utils.addAdminUser('test2', 'admintobedeletedbyotheraccountusers2', 'testing')
        (status,output) = Utils.deleteUser('test2', 'admintobedeletedbyotheraccountusers2',user='test:admin',key='testing')
        self.assertNotEqual(status, 0, 'admin deletion succeeded with admin user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'admin deletion succeeded with admin user of other account: '+output)

        Utils.addAdminUser('test2', 'admintobedeletedbyotheraccountusers3', 'testing')
        (status,output) = Utils.deleteUser('test2', 'admintobedeletedbyotheraccountusers3',user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 'admin deletion succeeded with regular user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'admin deletion succeeded with regular user of other account: '+output)

        #delete/de-active own admin account
        Utils.addAdminUser('test', 'admintobedeletedbyitself', 'testing')
        (status,output) = Utils.deleteUser('test', 'admintobedeletedbyitself',user='test:admintobedeletedbyitself',key='testing')
        self.assertEqual(status, 0, 'admin deletion failed with own credentials : '+output)

        #try to delete another regular users with all type of users
        Utils.addUser('test', 'usertobedeletedbyotherusers1', 'testing')
        (status,output) = Utils.deleteUser('test', 'usertobedeletedbyotherusers1',user='test:re_admin',key='testing')
        self.assertEqual(status, 0, 'user deletion failed with re_admin user: '+output)

        Utils.addUser('test', 'usertobedeletedbyotherusers2', 'testing')
        (status,output) = Utils.deleteUser('test', 'usertobedeletedbyotherusers2',user='test:admin',key='testing')
        self.assertEqual(status, 0, 'user deletion failed with admin user: '+output)

        Utils.addUser('test', 'usertobedeletedbyotherusers3', 'testing')
        (status,output) = Utils.deleteUser('test', 'usertobedeletedbyotherusers3',user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 'user deletion succeeded with regular user: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'user deletion succeeded with regular user: '+output)

        Utils.addUser('test2', 'usertobedeletedbyotheraccountusers1', 'testing')
        (status,output) = Utils.deleteUser('test2', 'usertobedeletedbyotheraccountusers1',user='test:re_admin',key='testing')
        self.assertEqual(status, 0, 'user deletion failed with re_admin user of other account: '+output)

        Utils.addUser('test2', 'usertobedeletedbyotheraccountusers2', 'testing')
        (status,output) = Utils.deleteUser('test2', 'usertobedeletedbyotheraccountusers2',user='test:admin',key='testing')
        self.assertNotEqual(status, 0, 'user deletion succeeded with admin user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'user deletion succeeded with admin user of other account: '+output)

        Utils.addUser('test2', 'usertobedeletedbyotheraccountusers3', 'testing')
        (status,output) = Utils.deleteUser('test2', 'usertobedeletedbyotheraccountusers3',user='test:tester',key='testing')
        self.assertNotEqual(status, 0, 'user deletion succeeded with regular user of other account: '+output)
        self.assertEqual('403 Forbidden' in output,True, 'user deletion succeeded with regular user of other account: '+output)

        #delete/de-active own admin account
        Utils.addAdminUser('test', 'usertobedeletedbyitself', 'testing')
        (status,output) = Utils.deleteUser('test', 'usertobedeletedbyitself',user='test:usertobedeletedbyitself',key='testing')
        self.assertEqual(status, 0, 'user deletion failed with own credentials : '+output)

    def testChangeKey(self):
        # Create account and users
        (status, output) = Utils.addAccount('test')
        self.assertEqual(status, 0, 'Account creation failed: ' + output)

        (status, output) = Utils.addAdminUser('test', 'admin', 'password')
        self.assertEqual(status, 0, 'User addition failed: ' + output)

        (status, output) = Utils.addUser('test', 'user', 'password')
        self.assertEqual(status, 0, 'User addition failed: ' + output)

        (status, output) = Utils.addResellerAdminUser('test', 'radmin', 'password')
        self.assertEqual(status, 0, 'User addition failed: ' + output)

        # Change acccount admin password/key
        (status, output) = Utils.addAdminUser('test', 'admin', 'new_password', user='test:admin', key='password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)

        # Change regular user password/key
        (status, output) = Utils.addUser('test', 'user', 'new_password', user='test:user', key='password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)

        # Change reseller admin password/key
        (status, output) = Utils.addResellerAdminUser('test', 'radmin', 'new_password', user='test:radmin', key='password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)

        # To verify that password was changed for real, re-run the above commands, but with the new password
        # Change acccount admin password/key using the new password
        (status, output) = Utils.addAdminUser('test', 'admin', 'password', user='test:admin', key='new_password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)

        # Change regular user password/key using the new password
        (status, output) = Utils.addUser('test', 'user', 'password', user='test:user', key='new_password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)

        # Change reseller admin password/key using the new password
        (status, output) = Utils.addResellerAdminUser('test', 'radmin', 'password', user='test:radmin', key='new_password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)

        # Make sure that regular user cannot upgrade to admin
        (status, output) = Utils.addAdminUser('test', 'user', 'password', user='test:user', key='password')
        self.assertEqual('User creation failed' in output, True, 'Update key failed: ' + output)

        # Make sure that regular user cannot upgrade to reseller_admin
        (status, output) = Utils.addResellerAdminUser('test', 'user', 'password', user='test:user', key='password')
        self.assertEqual('User creation failed' in output, True, 'Update key failed: ' + output)

        # Make sure admin cannot update himself to reseller_admin
        (status, output) = Utils.addResellerAdminUser('test', 'admin', 'password', user='test:admin', key='password')
        self.assertEqual('User creation failed' in output, True, 'Update key failed: ' + output)

        # Account admin changing regular user password/key
        (status, output) = Utils.addUser('test', 'user', 'new_password', user='test:admin', key='password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)
        # Verify by running the command with new password
        (status, output) = Utils.addUser('test', 'user', 'password', user='test:user', key='new_password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)

        # Reseller admin changing regular user password/key
        (status, output) = Utils.addUser('test', 'user', 'new_password', user='test:radmin', key='password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)
        # Verify by running the command with new password
        (status, output) = Utils.addUser('test', 'user', 'password', user='test:user', key='new_password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)

        # Reseller admin changing account admin password/key
        (status, output) = Utils.addAdminUser('test', 'admin', 'new_password', user='test:radmin', key='password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)
        # Verify by running the command with new password
        (status, output) = Utils.addAdminUser('test', 'admin', 'password', user='test:admin', key='new_password')
        self.assertEqual(status, 0, 'Update key failed: ' + output)


class TestCleanUPToken(unittest.TestCase):

    def setUp(self):
        (status,output)=Utils.swauthPrep()
        self.assertEqual(status, 0, 'setup swauth-prep failed'+output)

    def tearDown(self):
        Utils.cleanAll()

    def setTestAccUserEnv(self):
        (status,output)=Utils.addAccount('test')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addResellerAdminUser('test','re_admin','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addAdminUser('test','admin','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)
        (status,output)=Utils.addUser('test','tester','testing')
        self.assertEqual(status, 0, 'test accUser creation failed env'+output)

    def setTest2AccUserEnv(self):
        (status,output)=Utils.addAccount('test2')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addResellerAdminUser('test2','re_admin','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addAdminUser('test2','admin','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)
        (status,output)=Utils.addUser('test2','tester','testing')
        self.assertEqual(status, 0, 'test2 accUser creation failed env'+output)

    def testCleanUPToken(self):
        self.setTestAccUserEnv()
        self.setTest2AccUserEnv()

        #cleanup various validation
        (status,output)=Utils.cleanToken(key='')
        self.assertNotEqual(status, 0, 'clean up success without key'+output)
        self.assertEqual('Usage:' in output,True, 'clean up success without key: '+output)

        #validate the admin-user option is not working here
        (status,output)=Utils.cleanToken(option='admin-user', value='.super_admin')
        self.assertNotEqual(status, 0, 'clean up success with a username'+output)
        self.assertEqual('Usage:' in output,True, 'clean up success with a username: '+output)

        (status,output)=Utils.cleanToken(key='noavalidsuperadminkey')
        self.assertNotEqual(status, 0, 'clean up success with wrong super_admin key'+output)
        self.assertEqual('401 Unauthorized' in output,True, 'clean up success with wrong super_admin key: '+output)

        #cleanup token with no options
        (status,output)=Utils.cleanToken()
        self.assertEqual(status, 0, 'clean up failed with no option'+output)

        #cleanup token with purge option
        (status,output)=Utils.cleanToken(option='purge', value='test')
        self.assertEqual(status, 0, 'clean up failed with purge option'+output)

        #cleanup token with purge option no valid account name
        #TODO:review following https://bugs.launchpad.net/gluster-swift/+bug/1271555
        (status,output)=Utils.cleanToken(option='purge', value='accountnotvalid')
        self.assertNotEqual(status, 0, 'clean up failed with purge option'+output)

        #cleanup token with purge-all option
        (status,output)=Utils.cleanToken(option='purge-all')
        self.assertEqual(status, 0, 'clean up failed with purge-all option'+output)

        #cleanup token with -v option
        (status,output)=Utils.cleanToken(option='verbose')
        self.assertEqual(status, 0, 'clean up failed with verbose option'+output)
        self.assertEqual('GET .token_0' in output and 'GET .token_f' in output,True,\
                          'clean up success without key: '+output)

        #cleanup token with token-life option
        (status,output)=Utils.cleanToken(option='token-life', value='500')
        self.assertEqual(status, 0, 'clean up failed with token-life option'+output)

        #cleanup token with sleep option
        (status,output)=Utils.cleanToken(option='sleep', value='500')
        self.assertEqual(status, 0, 'clean up failed with sleep option'+output)

        #TODO:revisit below two cases after fix for
        #https://bugs.launchpad.net/gluster-swift/+bug/1271550
        #cleanup token with token-life option non numeric value
        (status,output)=Utils.cleanToken(option='token-life', value='notanumaric')
        self.assertNotEqual(status, 0, 'clean up success with token-life option token-life non numeric value'+output)
        self.assertEqual('ValueError' in output,True, 'clean up \
        success with token-life option non numeric value: '+output)

        #cleanup token with sleep option non numeric value
        (status,output)=Utils.cleanToken(option='sleep', value='notanumeric')
        self.assertNotEqual(status, 0, 'clean up failed with sleep option non numeric value'+output)
        self.assertEqual('ValueError' in output,True, 'clean up \
        success with token-life option non numeric value: '+output)

    def testSetAccountService(self):
        self.setTestAccUserEnv()
        self.setTest2AccUserEnv()

        #set-account-service asset all valid value
        (status,output)=Utils.setAccountService('test', 'storage', 'local', 'http://localhost:8080/v1/AUTH_test')
        self.assertEqual(status, 0, 'set account service fails with valid input'+output)
        (status,output)=Utils.listUsers('test', listtype='--json')
        self.assertEqual('{"services": {"storage": {"default": "local", "local": "http://localhost:8080/v1/AUTH_test"}}' in output,True, \
        'set account service success with valid input'+output)

        #invalid account
        (status,output)=Utils.setAccountService('accountdoesnotexist', 'storage', 'local', 'http://localhost:8080/v1/AUTH_test')
        self.assertNotEqual(status, 0, 'set account service success with invalid accountname'+output)
        self.assertEqual('Service set failed: 404 Not Found' in output,True, 'set account service success with invalid accountname'+output)

        #service name other than storage
        (status,output)=Utils.setAccountService('test', 'st', 'local', 'http://localhost:8080/v1/AUTH_test')
        self.assertEqual(status, 0, 'set account service success with service name other than storage'+output)
        (status,output)=Utils.listUsers('test', listtype='--json')
        self.assertEqual('"st": {"local": "http://localhost:8080/v1/AUTH_test"}}' in output,True, \
        'set account service success with service name other than storage'+output)

        #name other than local
        (status,output)=Utils.setAccountService('test', 'storage', 'notlocal', 'http://localhost:8080/v1/AUTH_test')
        self.assertEqual(status, 0, 'set account service with name other than local failed'+output)
        (status,output)=Utils.listUsers('test', listtype='--json')
        self.assertEqual(' "notlocal": "http://localhost:8080/v1/AUTH_test"}' in output,True, \
        'set account service with name other than local failed'+output)

        #set default to point notlocal
        (status,output)=Utils.setAccountService('test', 'storage', 'default', 'notlocal')
        self.assertEqual(status, 0, 'set account service set default to  local failed'+output)
        (status,output)=Utils.listUsers('test', listtype='--json')
        self.assertEqual(' {"default": "notlocal", "notlocal": "http://localhost:8080/v1/AUTH_test"' in output,True, \
        'set account service set default to local failed'+output)

        #try to set account service with users other than .super_admin
        #reseller_admin
        (status,output)=Utils.setAccountService('test', 'storage', 'local', 'http://localhost:8080/v1/AUTH_test', user='test:re_admin', key='testing')
        self.assertEqual(status, 0, 'set account service fails re_admin user cred'+output)

        #admin user
        (status,output)=Utils.setAccountService('test', 'storage', 'local', 'http://localhost:8080/v1/AUTH_test', user='test:admin', key='testing')
        self.assertNotEqual(status, 0, 'set account service success with admin user cred'+output)
        #self.assertEqual('403 Forbidden' in output,True, 'set account service success with admin user cred'+output)

        #regular user
        (status,output)=Utils.setAccountService('test', 'storage', 'local', 'http://localhost:8080/v1/AUTH_test', user='test:tester', key='testing')
        self.assertNotEqual(status, 0, 'set account service success with regular user cred'+output)
        #self.assertEqual('403 Forbidden' in output,True, 'set account service success with admin user cred'+output)

