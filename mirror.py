#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2018 Taylor Shuler
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

__author__ = 'Taylor Shuler (gnosoman@gmail.com)'

import logging
import os

from google.appengine.api import app_identity, urlfetch

from jinja2 import Environment, FileSystemLoader

from urllib import unquote
from urlparse import urlparse

# Google imports webapp2 last, so I guess we will too
import webapp2

env = Environment(
    loader = FileSystemLoader(os.path.dirname(__file__))
)

class BasePage(webapp2.RequestHandler):

    def is_recursive_request(self):
        user_agent = self.request.headers.get('User-Agent', None)
        is_self = 'AppEngine-Google' in user_agent

        if is_self:
            logging.warning('@MainPage | RECURSIVE REQUEST - user_agent: %s', user_agent)

        return is_self

    def strip_scheme(self, url):
        parsed_url = urlparse(url)
        scheme = "%s://" % parsed_url.scheme
        return parsed_url.geturl().replace(scheme, '', 1)

    def get_secure_url(self):
        if self.request.scheme.startswith('https'):
            return self.request.url
        return None

class MainPage(BasePage):

    def get(self):
        if self.is_recursive_request():
            return

        input_url = self.request.get('url')

        if input_url:
            input_url = self.strip_scheme(unquote(input_url))
            return self.redirect(r'/' + input_url)

        self.response.out.write(env.get_template("main.html").render({'secure_url': self.get_secure_url()}))

class MirrorPage(BasePage):

    def get(self, relative_url):
        if self.is_recursive_request():
            return

        assert relative_url

        logging.debug('@MirrorPage | relative_url: %s', relative_url)
        logging.debug('@MirrorPage | user_agent: %s; referer: %s', self.request.user_agent, self.request.referer)

        identity = app_identity.get_default_version_hostname();

        #mirror_url = identity + '/' + relative_url
        #logging.debug('@MirrorPage | mirror_url: %s', mirror_url)

        if self.get_secure_url() is None:
            prefix = 'http://'
        else:
            prefix = 'https://'

        mirror_url = prefix + identity + '/' + relative_url
        logging.debug('@MirrorPage | mirror_url: %s', mirror_url)

        try:
            webpage = urlfetch.fetch(prefix + relative_url)
        except Exception as err:
            logging.exception('@MirrorPage | ERROR - Could not fetch URL: %s (%s)' % (mirror_url, err))
            raise err

        self.response.out.write(webpage.content)

app = webapp2.WSGIApplication([(r'/', MainPage), (r"/([^/]+).*", MirrorPage)], debug = True)