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

from urllib import unquote
from urlparse import urlparse
from bs4 import BeautifulSoup as Soup

from google.appengine.api import app_identity, urlfetch, memcache
from google.appengine.ext import db

# Reflecting Google's import ordering
import jinja2
import webapp2

JINJA_ENVIRONMENT = jinja2.Environment(
    loader = jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions = ['jinja2.ext.autoescape'],
    autoescape = True,
    trim_blocks = True
)

class BasePage(webapp2.RequestHandler):

    def is_recursive_request(self):
        user_agent = self.request.headers.get('User-Agent', None)
        is_self = 'AppEngine-Google' in user_agent

        if is_self:
            logging.warning('@BasePage | RECURSIVE REQUEST - user_agent: %s', user_agent)

        return is_self

    def strip_scheme(self, url):
        parsed_url = urlparse(url)
        scheme = "%s://" % parsed_url.scheme
        return parsed_url.geturl().replace(scheme, '', 1)

    def get_secure_url(self):
        if self.request.scheme.startswith('https'):
            return self.request.url
        return None

    def get_scheme(self):
        if self.get_secure_url() is None:
            return 'http://'
        else:
            return 'https://'

class MainPage(BasePage):

    def get(self):
        if self.is_recursive_request():
            return

        input_url = self.request.get('url')
        memcache.set('url', input_url)

        if input_url:
            input_url = self.strip_scheme(unquote(input_url))
            return self.redirect(r'/' + input_url)

        self.response.write(JINJA_ENVIRONMENT.get_template('main.html').render({'secure_url': self.get_secure_url()}))

class MirrorPage(BasePage):

    def get(self, relative_url):
        if self.is_recursive_request():
            return

        assert relative_url

        input_url = memcache.get('url')

        logging.debug("@MirrorPage | relative_url: %s", relative_url)
        logging.debug("@MirrorPage | input_url: %s", input_url)
        logging.debug('@MirrorPage | user_agent: %s', self.request.user_agent)
        logging.debug('@MirrorPage | referer: %s', self.request.referer)

        # check for asset links
        if relative_url not in input_url:
            relative_url = input_url + relative_url
            logging.debug('@MirrorPage | Found asset path: %s', relative_url)

        try:
            html = urlfetch.fetch(input_url).content
        except Exception as err:
            logging.exception('@MirrorPage | ERROR - Could not fetch URL: %s (%s)' % (input_url, err))
            raise err

        soup = Soup(html, 'html.parser')
        app_url = self.get_scheme() + app_identity.get_default_version_hostname() + '/'

        def fix_tag(tag, attr):
            if tag.has_attr(attr):
                if 'https://' in tag[attr]:
                    tag[attr] = tag[attr].replace('https://', app_url)
                    logging.info('@MirrorPage | Updated link: %s', tag[attr])
                elif 'http://' in tag[attr]:
                    tag[attr] = tag[attr].replace('http://', app_url)
                    logging.info('@MirrorPage | Updated link: %s', tag[attr])
                elif tag[attr].startswith('/'):
                    tag[attr] = input_url + tag[attr].strip('/')
                    logging.info('@MirrorPage | Initial asset update: %s', tag[attr])

        for tag in soup.find_all(True):
            fix_tag(tag, 'href')
            fix_tag(tag, 'content')
            fix_tag(tag, 'src')

        self.response.write(soup.prettify())

app = webapp2.WSGIApplication([(r'/', MainPage), (r"/([^/]+).*", MirrorPage)], debug = False)