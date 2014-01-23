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

import os
import errno
import unittest
from time import time
from mock import patch, Mock
from test.unit import FakeMemcache
from swift.common.swob import Request, Response
from gluster.swift.common.middleware.swiftkerbauth import kerbauth as auth

EXT_AUTHENTICATION_URL = "127.0.0.1"
REDIRECT_STATUS = 303  # HTTPSeeOther


def my_filter_factory(global_conf, **local_conf):
    if 'ext_authentication_url' not in global_conf:
        global_conf['ext_authentication_url'] = EXT_AUTHENTICATION_URL
    conf = global_conf.copy()
    conf.update(local_conf)

    def auth_filter(app):
        return auth.KerbAuth(app, conf)
    return auth_filter

# Monkey patching filter_factory to always pass ext_authentication_url
# as a parameter. Absence of ext_authentication_url raises a RuntimeError


def patch_filter_factory():
    auth.filter_factory = my_filter_factory


def unpatch_filter_factory():
    reload(auth)


class FakeApp(object):

    def __init__(self, status_headers_body_iter=None, acl=None, sync_key=None):
        self.calls = 0
        self.status_headers_body_iter = status_headers_body_iter
        if not self.status_headers_body_iter:
            self.status_headers_body_iter = iter([('404 Not Found', {}, '')])
        self.acl = acl
        self.sync_key = sync_key

    def __call__(self, env, start_response):
        self.calls += 1
        self.request = Request.blank('', environ=env)
        if self.acl:
            self.request.acl = self.acl
        if self.sync_key:
            self.request.environ['swift_sync_key'] = self.sync_key
        if 'swift.authorize' in env:
            resp = env['swift.authorize'](self.request)
            if resp:
                return resp(env, start_response)
        status, headers, body = self.status_headers_body_iter.next()
        return Response(status=status, headers=headers,
                        body=body)(env, start_response)


class TestKerbAuth(unittest.TestCase):

    # Patch auth.filter_factory()
    patch_filter_factory()

    def setUp(self):
        self.test_auth = \
            auth.filter_factory({'auth_method': 'active'})(FakeApp())
        self.test_auth_passive = \
            auth.filter_factory({'auth_method': 'passive'})(FakeApp())

    def _make_request(self, path, **kwargs):
        req = Request.blank(path, **kwargs)
        req.environ['swift.cache'] = FakeMemcache()
        return req

    def test_no_ext_authentication_url(self):
        app = FakeApp()
        try:
            # Use original auth.filter_factory and NOT monkey patched version
            unpatch_filter_factory()
            auth.filter_factory({})(app)
        except RuntimeError as e:
            # Restore monkey patched version
            patch_filter_factory()
            self.assertTrue(e.args[0].startswith("Missing filter parameter "
                                                 "ext_authentication_url"))

    def test_reseller_prefix_init(self):
        app = FakeApp()
        ath = auth.filter_factory({})(app)
        self.assertEquals(ath.reseller_prefix, 'AUTH_')
        ath = auth.filter_factory({'reseller_prefix': 'TEST'})(app)
        self.assertEquals(ath.reseller_prefix, 'TEST_')
        ath = auth.filter_factory({'reseller_prefix': 'TEST_'})(app)
        self.assertEquals(ath.reseller_prefix, 'TEST_')

    def test_auth_prefix_init(self):
        app = FakeApp()
        ath = auth.filter_factory({})(app)
        self.assertEquals(ath.auth_prefix, '/auth/')
        ath = auth.filter_factory({'auth_prefix': ''})(app)
        self.assertEquals(ath.auth_prefix, '/auth/')
        ath = auth.filter_factory({'auth_prefix': '/'})(app)
        self.assertEquals(ath.auth_prefix, '/auth/')
        ath = auth.filter_factory({'auth_prefix': '/test/'})(app)
        self.assertEquals(ath.auth_prefix, '/test/')
        ath = auth.filter_factory({'auth_prefix': '/test'})(app)
        self.assertEquals(ath.auth_prefix, '/test/')
        ath = auth.filter_factory({'auth_prefix': 'test/'})(app)
        self.assertEquals(ath.auth_prefix, '/test/')
        ath = auth.filter_factory({'auth_prefix': 'test'})(app)
        self.assertEquals(ath.auth_prefix, '/test/')

    def test_top_level_redirect(self):
        req = self._make_request('/')
        resp = req.get_response(self.test_auth)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)
        self.assertEquals(req.environ['swift.authorize'],
                          self.test_auth.denied_response)

    def test_passive_top_level_deny(self):
        req = self._make_request('/')
        resp = req.get_response(self.test_auth_passive)
        self.assertEquals(resp.status_int, 401)
        self.assertEquals(req.environ['swift.authorize'],
                          self.test_auth_passive.denied_response)

    def test_passive_deny_invalid_token(self):
        req = self._make_request('/v1/AUTH_account',
                                 headers={'X-Auth-Token': 'AUTH_t'})
        resp = req.get_response(self.test_auth_passive)
        self.assertEquals(resp.status_int, 401)

    def test_override_asked_for_and_allowed(self):
        self.test_auth = \
            auth.filter_factory({'allow_overrides': 'true'})(FakeApp())
        req = self._make_request('/v1/AUTH_account',
                                 environ={'swift.authorize_override': True})
        resp = req.get_response(self.test_auth)
        self.assertEquals(resp.status_int, 404)
        self.assertTrue('swift.authorize' not in req.environ)

    def test_override_default_allowed(self):
        req = self._make_request('/v1/AUTH_account',
                                 environ={'swift.authorize_override': True})
        resp = req.get_response(self.test_auth)
        self.assertEquals(resp.status_int, 404)
        self.assertTrue('swift.authorize' not in req.environ)

    def test_options_call(self):
        req = self._make_request('/v1/AUTH_cfa/c/o',
                                 environ={'REQUEST_METHOD': 'OPTIONS'})
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp, None)

    def test_auth_deny_non_reseller_prefix_no_override(self):
        fake_authorize = lambda x: Response(status='500 Fake')
        req = self._make_request('/v1/BLAH_account',
                                 headers={'X-Auth-Token': 'BLAH_t'},
                                 environ={'swift.authorize': fake_authorize}
                                 )
        resp = req.get_response(self.test_auth)
        self.assertEquals(resp.status_int, 500)
        self.assertEquals(req.environ['swift.authorize'], fake_authorize)

    def test_authorize_acl_group_access(self):
        req = self._make_request('/v1/AUTH_cfa')
        req.remote_user = 'act:usr,act'
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, 403)
        req = self._make_request('/v1/AUTH_cfa')
        req.remote_user = 'act:usr,act'
        req.acl = 'act'
        self.assertEquals(self.test_auth.authorize(req), None)
        req = self._make_request('/v1/AUTH_cfa')
        req.remote_user = 'act:usr,act'
        req.acl = 'act:usr'
        self.assertEquals(self.test_auth.authorize(req), None)
        req = self._make_request('/v1/AUTH_cfa')
        req.remote_user = 'act:usr,act'

    def test_deny_cross_reseller(self):
        # Tests that cross-reseller is denied, even if ACLs/group names match
        req = self._make_request('/v1/OTHER_cfa')
        req.remote_user = 'act:usr,act,AUTH_cfa'
        req.acl = 'act'
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, 403)

    def test_authorize_acl_referer_after_user_groups(self):
        req = self._make_request('/v1/AUTH_cfa/c')
        req.remote_user = 'act:usr'
        req.acl = '.r:*,act:usr'
        self.assertEquals(self.test_auth.authorize(req), None)

    def test_detect_reseller_request(self):
        req = self._make_request('/v1/AUTH_admin',
                                 headers={'X-Auth-Token': 'AUTH_t'})
        cache_key = 'AUTH_/token/AUTH_t'
        cache_entry = (time() + 3600, '.reseller_admin')
        req.environ['swift.cache'].set(cache_key, cache_entry)
        req.get_response(self.test_auth)
        self.assertTrue(req.environ.get('reseller_request', False))

    def test_regular_is_not_owner(self):
        orig_authorize = self.test_auth.authorize
        owner_values = []

        def mitm_authorize(req):
            rv = orig_authorize(req)
            owner_values.append(req.environ.get('swift_owner', False))
            return rv

        self.test_auth.authorize = mitm_authorize

        req = self._make_request(
            '/v1/AUTH_cfa/c',
            headers={'X-Auth-Token': 'AUTH_t'})
        req.remote_user = 'act:usr'
        self.test_auth.authorize(req)
        self.assertEquals(owner_values, [False])

    def test_no_memcache(self):
        env = {'swift.cache': None}
        try:
            self.test_auth.get_groups(env, None)
        except Exception as e:
            self.assertTrue(e.args[0].startswith("Memcache required"))

    def test_handle_request(self):
        req = self._make_request('/auth/v1.0')
        resp = self.test_auth.handle_request(req)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)

    def test_handle_request_bad_request(self):
        req = self._make_request('////')
        resp = self.test_auth.handle_request(req)
        self.assertEquals(resp.status_int, 404)

    def test_handle_request_no_handler(self):
        req = self._make_request('/blah/blah/blah/blah')
        resp = self.test_auth.handle_request(req)
        self.assertEquals(resp.status_int, 400)

    def test_handle_get_token_bad_request(self):
        req = self._make_request('/blah/blah')
        resp = self.test_auth.handle_get_token(req)
        self.assertEquals(resp.status_int, 400)
        req = self._make_request('/////')
        resp = self.test_auth.handle_get_token(req)
        self.assertEquals(resp.status_int, 404)

    def test_passive_handle_get_token_no_user_or_key(self):
        #No user and key
        req = self._make_request('/auth/v1.0')
        resp = self.test_auth_passive.handle_get_token(req)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)
        #User given but no key
        req = self._make_request('/auth/v1.0',
                                 headers={'X-Auth-User': 'test:user'})
        resp = self.test_auth_passive.handle_get_token(req)
        self.assertEquals(resp.status_int, 401)

    def test_passive_handle_get_token_account_in_req_path(self):
        req = self._make_request('/v1/test/auth',
                                 headers={'X-Auth-User': 'test:user',
                                          'X-Auth-Key': 'password'})
        _mock_run_kinit = Mock(return_value=0)
        _mock_get_groups = Mock(return_value="user,auth_test")
        with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.run_kinit', _mock_run_kinit):
            with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.get_groups_from_username',
                       _mock_get_groups):
                resp = self.test_auth_passive.handle_get_token(req)
        _mock_run_kinit.assert_called_once_with('user', 'password')
        self.assertEquals(_mock_get_groups.call_count, 2)
        self.assertEquals(resp.status_int, 200)
        self.assertTrue(resp.headers['X-Auth-Token'] is not None)
        self.assertTrue(resp.headers['X-Storage-Token'] is not None)
        self.assertTrue(resp.headers['X-Storage-Url'] is not None)

    def test_passive_handle_get_token_user_invalid_or_no__account(self):
        #X-Auth-User not in acc:user format
        req = self._make_request('/auth/v1.0',
                                 headers={'X-Auth-User': 'user'})
        resp = self.test_auth_passive.handle_get_token(req)
        self.assertEquals(resp.status_int, 401)
        req = self._make_request('/v1/test/auth',
                                 headers={'X-Auth-User': 'user'})
        resp = self.test_auth_passive.handle_get_token(req)
        self.assertEquals(resp.status_int, 401)
        # Account name mismatch
        req = self._make_request('/v1/test/auth',
                                 headers={'X-Auth-User': 'wrongacc:user'})
        resp = self.test_auth_passive.handle_get_token(req)
        self.assertEquals(resp.status_int, 401)

    def test_passive_handle_get_token_no_kinit(self):
        req = self._make_request('/auth/v1.0',
                                 headers={'X-Auth-User': 'test:user',
                                          'X-Auth-Key': 'password'})
        _mock_run_kinit = Mock(side_effect=OSError(errno.ENOENT,
                                                   os.strerror(errno.ENOENT)))
        with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.run_kinit', _mock_run_kinit):
            resp = self.test_auth_passive.handle_get_token(req)
        self.assertEquals(resp.status_int, 500)
        self.assertTrue("kinit command not found" in resp.body)
        _mock_run_kinit.assert_called_once_with('user', 'password')

    def test_passive_handle_get_token_kinit_fail(self):
        req = self._make_request('/auth/v1.0',
                                 headers={'X-Auth-User': 'test:user',
                                          'X-Auth-Key': 'password'})
        _mock_run_kinit = Mock(return_value=1)
        with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.run_kinit', _mock_run_kinit):
            resp = self.test_auth_passive.handle_get_token(req)
        self.assertEquals(resp.status_int, 401)
        _mock_run_kinit.assert_called_once_with('user', 'password')

    def test_passive_handle_get_token_kinit_success_token_not_present(self):
        req = self._make_request('/auth/v1.0',
                                 headers={'X-Auth-User': 'test:user',
                                          'X-Auth-Key': 'password'})
        _mock_run_kinit = Mock(return_value=0)
        _mock_get_groups = Mock(return_value="user,auth_test")
        with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.run_kinit', _mock_run_kinit):
            with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.get_groups_from_username',
                       _mock_get_groups):
                resp = self.test_auth_passive.handle_get_token(req)
        _mock_run_kinit.assert_called_once_with('user', 'password')
        self.assertEquals(_mock_get_groups.call_count, 2)
        self.assertEquals(resp.status_int, 200)
        self.assertTrue(resp.headers['X-Auth-Token'] is not None)
        self.assertTrue(resp.headers['X-Storage-Token'] is not None)
        self.assertTrue(resp.headers['X-Storage-Url'] is not None)

    def test_passive_handle_get_token_kinit_realm_and_memcache(self):
        req = self._make_request('/auth/v1.0',
                                 headers={'X-Auth-User': 'test:user',
                                          'X-Auth-Key': 'password'})
        req.environ['swift.cache'] = None
        _auth_passive = \
            auth.filter_factory({'auth_method': 'passive',
                                'realm_name': 'EXAMPLE.COM'})(FakeApp())
        _mock_run_kinit = Mock(return_value=0)
        _mock_get_groups = Mock(return_value="user,auth_test")
        with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.run_kinit', _mock_run_kinit):
            with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.get_groups_from_username',
                       _mock_get_groups):
                    try:
                        _auth_passive.handle_get_token(req)
                    except Exception as e:
                        self.assertTrue(e.args[0].startswith("Memcache "
                                                             "required"))
                    else:
                        self.fail("Expected Exception - Memcache required")
        _mock_run_kinit.assert_called_once_with('user@EXAMPLE.COM', 'password')
        _mock_get_groups.assert_called_once_with('user')

    def test_passive_handle_get_token_user_in_any__account(self):
        req = self._make_request('/auth/v1.0',
                                 headers={'X-Auth-User': 'test:user',
                                          'X-Auth-Key': 'password'})
        _mock_run_kinit = Mock(return_value=0)
        _mock_get_groups = Mock(return_value="user,auth_blah")
        with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.run_kinit', _mock_run_kinit):
            with patch('gluster.swift.common.middleware.swiftkerbauth.kerbauth.get_groups_from_username',
                       _mock_get_groups):
                resp = self.test_auth_passive.handle_get_token(req)
                self.assertEquals(resp.status_int, 401)
        _mock_run_kinit.assert_called_once_with('user', 'password')
        _mock_get_groups.assert_called_once_with('user')

    def test_handle(self):
        req = self._make_request('/auth/v1.0')
        resp = req.get_response(self.test_auth)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)

    def test_authorize_invalid_req(self):
        req = self._make_request('/')
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, 404)

    def test_authorize_set_swift_owner(self):
        req = self._make_request('/v1/AUTH_test/c1/o1')
        req.remote_user = 'test,auth_reseller_admin'
        resp = self.test_auth.authorize(req)
        self.assertEquals(req.environ['swift_owner'], True)
        self.assertTrue(resp is None)
        req = self._make_request('/v1/AUTH_test/c1/o1')
        req.remote_user = 'test,auth_test'
        resp = self.test_auth.authorize(req)
        self.assertEquals(req.environ['swift_owner'], True)
        self.assertTrue(resp is None)

    def test_authorize_swift_sync_key(self):
        req = self._make_request(
            '/v1/AUTH_cfa/c/o',
            environ={'swift_sync_key': 'secret'},
            headers={'x-container-sync-key': 'secret',
                     'x-timestamp': '123.456'})
        resp = self.test_auth.authorize(req)
        self.assertTrue(resp is None)

    def test_authorize_acl_referrer_access(self):
        req = self._make_request('/v1/AUTH_cfa/c')
        req.remote_user = 'act:usr,act'
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, 403)
        req = self._make_request('/v1/AUTH_cfa/c')
        req.remote_user = 'act:usr,act'
        req.acl = '.r:*,.rlistings'
        self.assertEquals(self.test_auth.authorize(req), None)
        req = self._make_request('/v1/AUTH_cfa/c')
        req.remote_user = 'act:usr,act'
        req.acl = '.r:*'  # No listings allowed
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, 403)
        req = self._make_request('/v1/AUTH_cfa/c')
        req.remote_user = 'act:usr,act'
        req.acl = '.r:.example.com,.rlistings'
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, 403)
        req = self._make_request('/v1/AUTH_cfa/c')
        req.remote_user = 'act:usr,act'
        req.referer = 'http://www.example.com/index.html'
        req.acl = '.r:.example.com,.rlistings'
        self.assertEquals(self.test_auth.authorize(req), None)
        req = self._make_request('/v1/AUTH_cfa/c')
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)
        req = self._make_request('/v1/AUTH_cfa/c')
        req.acl = '.r:*,.rlistings'
        self.assertEquals(self.test_auth.authorize(req), None)
        req = self._make_request('/v1/AUTH_cfa/c')
        req.acl = '.r:*'  # No listings allowed
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)
        req = self._make_request('/v1/AUTH_cfa/c')
        req.acl = '.r:.example.com,.rlistings'
        resp = self.test_auth.authorize(req)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)
        req = self._make_request('/v1/AUTH_cfa/c')
        req.referer = 'http://www.example.com/index.html'
        req.acl = '.r:.example.com,.rlistings'
        self.assertEquals(self.test_auth.authorize(req), None)

    def test_handle_x_storage_token(self):
        req = self._make_request(
            '/auth/v1.0',
            headers={'x-storage-token': 'blahblah', })
        resp = req.get_response(self.test_auth)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)

    def test_invalid_token(self):
        req = self._make_request('/k1/test')
        req.environ['HTTP_X_AUTH_TOKEN'] = 'AUTH_blahblahblah'
        resp = req.get_response(self.test_auth)
        self.assertEquals(resp.status_int, REDIRECT_STATUS)

if __name__ == '__main__':
    unittest.main()
