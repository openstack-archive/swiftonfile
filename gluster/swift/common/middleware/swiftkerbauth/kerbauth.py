# Copyright (c) 2013 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import errno
from time import time, ctime
from traceback import format_exc
from eventlet import Timeout
from urllib import unquote

from swift.common.swob import Request, Response
from swift.common.swob import HTTPBadRequest, HTTPForbidden, HTTPNotFound, \
    HTTPSeeOther, HTTPUnauthorized, HTTPServerError

from swift.common.middleware.acl import clean_acl, parse_acl, referrer_allowed
from swift.common.utils import cache_from_env, get_logger,  \
    split_path, config_true_value
from gluster.swift.common.middleware.swiftkerbauth.kerbauth_utils import \
    get_auth_data, generate_token, \
    set_auth_data, run_kinit, get_groups_from_username


class KerbAuth(object):
    """
    Test authentication and authorization system.

    Add to your pipeline in proxy-server.conf, such as::

        [pipeline:main]
        pipeline = catch_errors cache kerbauth proxy-server

    Set account auto creation to true in proxy-server.conf::

        [app:proxy-server]
        account_autocreate = true

    And add a kerbauth filter section, such as::

        [filter:kerbauth]
        use = egg:swiftkerbauth#kerbauth

    See the proxy-server.conf-sample for more information.

    :param app: The next WSGI app in the pipeline
    :param conf: The dict of configuration values
    """

    def __init__(self, app, conf):
        self.app = app
        self.conf = conf
        self.logger = get_logger(conf, log_route='kerbauth')
        self.log_headers = config_true_value(conf.get('log_headers', 'f'))
        self.reseller_prefix = conf.get('reseller_prefix', 'AUTH').strip()
        if self.reseller_prefix and self.reseller_prefix[-1] != '_':
            self.reseller_prefix += '_'
        self.logger.set_statsd_prefix('kerbauth.%s' % (
            self.reseller_prefix if self.reseller_prefix else 'NONE',))
        self.auth_prefix = conf.get('auth_prefix', '/auth/')
        if not self.auth_prefix or not self.auth_prefix.strip('/'):
            self.logger.warning('Rewriting invalid auth prefix "%s" to '
                                '"/auth/" (Non-empty auth prefix path '
                                'is required)' % self.auth_prefix)
            self.auth_prefix = '/auth/'
        if self.auth_prefix[0] != '/':
            self.auth_prefix = '/' + self.auth_prefix
        if self.auth_prefix[-1] != '/':
            self.auth_prefix += '/'
        self.token_life = int(conf.get('token_life', 86400))
        self.auth_method = conf.get('auth_method', 'passive')
        self.debug_headers = config_true_value(
            conf.get('debug_headers', 'yes'))
        self.realm_name = conf.get('realm_name', None)
        self.allow_overrides = config_true_value(
            conf.get('allow_overrides', 't'))
        self.storage_url_scheme = conf.get('storage_url_scheme', 'default')
        self.ext_authentication_url = conf.get('ext_authentication_url')
        if not self.ext_authentication_url:
            raise RuntimeError("Missing filter parameter ext_authentication_"
                               "url in /etc/swift/proxy-server.conf")

    def __call__(self, env, start_response):
        """
        Accepts a standard WSGI application call, authenticating the request
        and installing callback hooks for authorization and ACL header
        validation. For an authenticated request, REMOTE_USER will be set to a
        comma separated list of the user's groups.

        If the request matches the self.auth_prefix, the request will be
        routed through the internal auth request handler (self.handle).
        This is to handle granting tokens, etc.
        """
        if self.allow_overrides and env.get('swift.authorize_override', False):
            return self.app(env, start_response)
        if env.get('PATH_INFO', '').startswith(self.auth_prefix):
            return self.handle(env, start_response)
        token = env.get('HTTP_X_AUTH_TOKEN', env.get('HTTP_X_STORAGE_TOKEN'))
        if token and token.startswith(self.reseller_prefix):
            groups = self.get_groups(env, token)
            if groups:
                user = groups and groups.split(',', 1)[0] or ''
                trans_id = env.get('swift.trans_id')
                self.logger.debug('User: %s uses token %s (trans_id %s)' %
                                  (user, token, trans_id))
                env['REMOTE_USER'] = groups
                env['swift.authorize'] = self.authorize
                env['swift.clean_acl'] = clean_acl
                if '.reseller_admin' in groups:
                    env['reseller_request'] = True
            else:
                # Invalid token (may be expired)
                if self.auth_method == "active":
                    return HTTPSeeOther(
                        location=self.ext_authentication_url)(env,
                                                              start_response)
                elif self.auth_method == "passive":
                    self.logger.increment('unauthorized')
                    return HTTPUnauthorized()(env, start_response)
        else:
            # With a non-empty reseller_prefix, I would like to be called
            # back for anonymous access to accounts I know I'm the
            # definitive auth for.
            try:
                version, rest = split_path(env.get('PATH_INFO', ''),
                                           1, 2, True)
            except ValueError:
                version, rest = None, None
                self.logger.increment('errors')
            # Not my token, not my account, I can't authorize this request,
            # deny all is a good idea if not already set...
            if 'swift.authorize' not in env:
                env['swift.authorize'] = self.denied_response

        return self.app(env, start_response)

    def get_groups(self, env, token):
        """
        Get groups for the given token.

        :param env: The current WSGI environment dictionary.
        :param token: Token to validate and return a group string for.

        :returns: None if the token is invalid or a string containing a comma
                  separated list of groups the authenticated user is a member
                  of. The first group in the list is also considered a unique
                  identifier for that user.
        """
        groups = None
        memcache_client = cache_from_env(env)
        if not memcache_client:
            raise Exception('Memcache required')
        memcache_token_key = '%s/token/%s' % (self.reseller_prefix, token)
        cached_auth_data = memcache_client.get(memcache_token_key)
        if cached_auth_data:
            expires, groups = cached_auth_data
            if expires < time():
                groups = None

        return groups

    def authorize(self, req):
        """
        Returns None if the request is authorized to continue or a standard
        WSGI response callable if not.

        Assumes that user groups are all lower case, which is true when Red Hat
        Enterprise Linux Identity Management is used.
        """
        try:
            version, account, container, obj = req.split_path(1, 4, True)
        except ValueError:
            self.logger.increment('errors')
            return HTTPNotFound(request=req)

        if not account or not account.startswith(self.reseller_prefix):
            self.logger.debug("Account name: %s doesn't start with "
                              "reseller_prefix: %s."
                              % (account, self.reseller_prefix))
            return self.denied_response(req)

        user_groups = (req.remote_user or '').split(',')
        account_user = user_groups[1] if len(user_groups) > 1 else None
        # If the user is in the reseller_admin group for our prefix, he gets
        # full access to all accounts we manage. For the default reseller
        # prefix, the group name is auth_reseller_admin.
        admin_group = ("%sreseller_admin" % self.reseller_prefix).lower()
        if admin_group in user_groups and \
                account != self.reseller_prefix and \
                account[len(self.reseller_prefix)] != '.':
            req.environ['swift_owner'] = True
            return None

        # The "account" is part of the request URL, and already contains the
        # reseller prefix, like in "/v1/AUTH_vol1/pictures/pic1.png".
        if account.lower() in user_groups and \
                (req.method not in ('DELETE', 'PUT') or container):
            # If the user is admin for the account and is not trying to do an
            # account DELETE or PUT...
            req.environ['swift_owner'] = True
            self.logger.debug("User %s has admin authorizing."
                              % account_user)
            return None

        if (req.environ.get('swift_sync_key')
                and (req.environ['swift_sync_key'] ==
                     req.headers.get('x-container-sync-key', None))
                and 'x-timestamp' in req.headers):
            self.logger.debug("Allow request with container sync-key: %s."
                              % req.environ['swift_sync_key'])
            return None

        if req.method == 'OPTIONS':
            #allow OPTIONS requests to proceed as normal
            self.logger.debug("Allow OPTIONS request.")
            return None

        referrers, groups = parse_acl(getattr(req, 'acl', None))

        if referrer_allowed(req.referer, referrers):
            if obj or '.rlistings' in groups:
                self.logger.debug("Allow authorizing %s via referer ACL."
                                  % req.referer)
                return None

        for user_group in user_groups:
            if user_group in groups:
                self.logger.debug("User %s allowed in ACL: %s authorizing."
                                  % (account_user, user_group))
                return None

        return self.denied_response(req)

    def denied_response(self, req):
        """
        Returns a standard WSGI response callable with the status of 403 or 401
        depending on whether the REMOTE_USER is set or not.
        """
        if req.remote_user:
            self.logger.increment('forbidden')
            return HTTPForbidden(request=req)
        else:
            if self.auth_method == "active":
                return HTTPSeeOther(location=self.ext_authentication_url)
            elif self.auth_method == "passive":
                self.logger.increment('unauthorized')
                return HTTPUnauthorized(request=req)

    def handle(self, env, start_response):
        """
        WSGI entry point for auth requests (ones that match the
        self.auth_prefix).
        Wraps env in swob.Request object and passes it down.

        :param env: WSGI environment dictionary
        :param start_response: WSGI callable
        """
        try:
            req = Request(env)
            if self.auth_prefix:
                req.path_info_pop()
            req.bytes_transferred = '-'
            req.client_disconnect = False
            if 'x-storage-token' in req.headers and \
                    'x-auth-token' not in req.headers:
                req.headers['x-auth-token'] = req.headers['x-storage-token']
            return self.handle_request(req)(env, start_response)
        except (Exception, Timeout):
            print "EXCEPTION IN handle: %s: %s" % (format_exc(), env)
            self.logger.increment('errors')
            start_response('500 Server Error',
                           [('Content-Type', 'text/plain')])
            return ['Internal server error.\n']

    def handle_request(self, req):
        """
        Entry point for auth requests (ones that match the self.auth_prefix).
        Should return a WSGI-style callable (such as webob.Response).

        :param req: swob.Request object
        """
        req.start_time = time()
        handler = None
        try:
            version, account, user, _junk = req.split_path(1, 4, True)
        except ValueError:
            self.logger.increment('errors')
            return HTTPNotFound(request=req)
        if version in ('v1', 'v1.0', 'auth'):
            if req.method == 'GET':
                handler = self.handle_get_token
        if not handler:
            self.logger.increment('errors')
            req.response = HTTPBadRequest(request=req)
        else:
            req.response = handler(req)
        return req.response

    def handle_get_token(self, req):
        """
        Handles the various `request for token and service end point(s)` calls.
        There are various formats to support the various auth servers in the
        past.

        "Active Mode" usage:
            All formats require GSS (Kerberos) authentication.

            GET <auth-prefix>/v1/<act>/auth
            GET <auth-prefix>/auth
            GET <auth-prefix>/v1.0

            On successful authentication, the response will have X-Auth-Token
            and X-Storage-Token set to the token to use with Swift.

        "Passive Mode" usage::

            GET <auth-prefix>/v1/<act>/auth
                X-Auth-User: <act>:<usr>  or  X-Storage-User: <usr>
                X-Auth-Key: <key>         or  X-Storage-Pass: <key>
            GET <auth-prefix>/auth
                X-Auth-User: <act>:<usr>  or  X-Storage-User: <act>:<usr>
                X-Auth-Key: <key>         or  X-Storage-Pass: <key>
            GET <auth-prefix>/v1.0
                X-Auth-User: <act>:<usr>  or  X-Storage-User: <act>:<usr>
                X-Auth-Key: <key>         or  X-Storage-Pass: <key>

            Values should be url encoded, "act%3Ausr" instead of "act:usr" for
            example; however, for backwards compatibility the colon may be
            included unencoded.

            On successful authentication, the response will have X-Auth-Token
            and X-Storage-Token set to the token to use with Swift and
            X-Storage-URL set to the URL to the default Swift cluster to use.

        :param req: The swob.Request to process.
        :returns: swob.Response, 2xx on success with data set as explained
                  above.
        """
        # Validate the request info
        try:
            pathsegs = split_path(req.path_info, 1, 3, True)
        except ValueError:
            self.logger.increment('errors')
            return HTTPNotFound(request=req)
        if not ((pathsegs[0] == 'v1' and pathsegs[2] == 'auth')
                or pathsegs[0] in ('auth', 'v1.0')):
                    return HTTPBadRequest(request=req)

        # Client is inside the domain
        if self.auth_method == "active":
            return HTTPSeeOther(location=self.ext_authentication_url)

        # Client is outside the domain
        elif self.auth_method == "passive":
            account, user, key = None, None, None
            # Extract user, account and key from request
            if pathsegs[0] == 'v1' and pathsegs[2] == 'auth':
                account = pathsegs[1]
                user = req.headers.get('x-storage-user')
                if not user:
                    user = unquote(req.headers.get('x-auth-user', ''))
                    if user:
                        if ':' not in user:
                            return HTTPUnauthorized(request=req)
                        else:
                            account2, user = user.split(':', 1)
                            if account != account2:
                                return HTTPUnauthorized(request=req)
                key = req.headers.get('x-storage-pass')
                if not key:
                    key = unquote(req.headers.get('x-auth-key', ''))
            elif pathsegs[0] in ('auth', 'v1.0'):
                user = unquote(req.headers.get('x-auth-user', ''))
                if not user:
                    user = req.headers.get('x-storage-user')
                if user:
                    if ':' not in user:
                        return HTTPUnauthorized(request=req)
                    else:
                        account, user = user.split(':', 1)
                key = unquote(req.headers.get('x-auth-key', ''))
                if not key:
                    key = req.headers.get('x-storage-pass')

            if not (account or user or key):
                # If all are not given, client may be part of the domain
                return HTTPSeeOther(location=self.ext_authentication_url)
            elif None in (key, user, account):
                # If only one or two of them is given, but not all
                return HTTPUnauthorized(request=req)

            # Run kinit on the user
            if self.realm_name and "@" not in user:
                user = user + "@" + self.realm_name
            try:
                ret = run_kinit(user, key)
            except OSError as e:
                if e.errno == errno.ENOENT:
                    return HTTPServerError("kinit command not found\n")
            if ret != 0:
                self.logger.warning("Failed: kinit %s", user)
                if ret == -1:
                    self.logger.warning("Failed: kinit: Password has probably "
                                        "expired.")
                    return HTTPServerError("Kinit is taking too long.\n")
                return HTTPUnauthorized(request=req)
            self.logger.debug("kinit succeeded")

            if "@" in user:
                user = user.split("@")[0]

            # Check if user really belongs to the account
            groups_list = get_groups_from_username(user).strip().split(",")
            user_group = ("%s%s" % (self.reseller_prefix, account)).lower()
            reseller_admin_group = \
                ("%sreseller_admin" % self.reseller_prefix).lower()
            if user_group not in groups_list:
                # Check if user is reseller_admin. If not, return Unauthorized.
                # On AD/IdM server, auth_reseller_admin is a separate group
                if reseller_admin_group not in groups_list:
                    return HTTPUnauthorized(request=req)

            mc = cache_from_env(req.environ)
            if not mc:
                raise Exception('Memcache required')
            token, expires, groups = get_auth_data(mc, user)
            if not token:
                token = generate_token()
                expires = time() + self.token_life
                groups = get_groups_from_username(user)
                set_auth_data(mc, user, token, expires, groups)

            headers = {'X-Auth-Token': token,
                       'X-Storage-Token': token}

            if self.debug_headers:
                headers.update({'X-Debug-Remote-User': user,
                                'X-Debug-Groups:': groups,
                                'X-Debug-Token-Life': self.token_life,
                                'X-Debug-Token-Expires': ctime(expires)})

            resp = Response(request=req, headers=headers)
            resp.headers['X-Storage-Url'] = \
                '%s/v1/%s%s' % (resp.host_url, self.reseller_prefix, account)
            return resp


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def auth_filter(app):
        return KerbAuth(app, conf)
    return auth_filter
