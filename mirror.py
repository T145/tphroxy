#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2008-2014 Brett Slatkin, 2018 Taylor Shuler
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

__author__ = 'Brett Slatkin (bslatkin@gmail.com)'
__modify__ = 'Taylor Shuler (gnosoman@gmail.com)'

import logging
import urllib
import webapp2

from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template

from transform_content import transform_content

DEBUG = True
EXPIRATION_DELTA_SECONDS = 3600

IGNORE_HEADERS = frozenset([  # Ignore hop-by-hop headers
    'set-cookie',
    'expires',
    'cache-control',
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailers',
    'transfer-encoding',
    'upgrade'
])

TRANSFORMED_CONTENT_TYPES = frozenset(['text/html', 'text/css'])


class MirroredContent(object):

    def __init__(self, original_address, translated_address, status, headers, data, base_url):
        self.original_address = original_address
        self.translated_address = translated_address
        self.status = status
        self.headers = headers
        self.data = data
        self.base_url = base_url

    @staticmethod
    def fetch(base_url, translated_address, mirrored_url):

        logging.debug("Fetching '%s'", mirrored_url)
        try:
            response = urlfetch.fetch(mirrored_url)
        except Exception as err:
            logging.exception("Could not fetch URL: %s (%s)" % (mirrored_url, err))
            return None

        adjusted_headers = {}
        for (key, value) in response.headers.iteritems():
            adjusted_key = key.lower()
            if adjusted_key not in IGNORE_HEADERS:
                adjusted_headers[adjusted_key] = value

        content = response.content
        page_content_type = adjusted_headers.get('content-type', '')

        for content_type in TRANSFORMED_CONTENT_TYPES:
            # startswith() because there could be a 'charset=UTF-8' in the header.
            if page_content_type.startswith(content_type):
                content = transform_content(base_url, mirrored_url, content)
                break

        new_content = MirroredContent(
            base_url = base_url,
            original_address = mirrored_url,
            translated_address = translated_address,
            status = response.status_code,
            headers = adjusted_headers,
            data = content)

        return new_content


class BaseHandler(webapp2.RequestHandler):

    def get_relative_url(self):
        slash = self.request.url.find(r"/", len(self.request.scheme + '://'))
        if slash == -1:
            return r"/"
        logging.debug('@BaseHandler | slash: %s', slash)
        logging.debug('@BaseHandler | request.scheme: %s', self.request.scheme)
        logging.debug('@BaseHandler | request.url: %s', self.request.url)
        logging.debug('@BaseHandler | get_relative_url: %s', self.request.url[slash:])
        return self.request.url[slash:]

    def is_recursive_request(self):
        if 'AppEngine-Google' in self.request.headers.get('User-Agent', ''):
            logging.warning('Ignoring recursive request by user-agent=%r; ignoring')
            self.error(404)
            return True
        return False


class HomeHandler(BaseHandler):

    def get(self):
        if self.is_recursive_request():
            return

        # Handle the input form to redirect the user to a relative url
        form_url = self.request.get('url')
        if form_url:  # Accept URLs that still have a leading 'http(s)://'
            inputted_url = urllib.unquote(form_url)
            if inputted_url.startswith('http'):
                inputted_url = inputted_url.replace('://', '_', 1)
            else:
                inputted_url = 'http_' + inputted_url
            return self.redirect(r"/" + inputted_url)

        # Do this dictionary construction here, to decouple presentation from how we store data.
        secure_url = None
        if self.request.scheme == 'http':
            secure_url = 'https://%s%s' % (self.request.host, self.request.path_qs)
        context = {'secure_url': secure_url}
        self.response.out.write(template.render('main.html', context))


class MirrorHandler(BaseHandler):

    def get(self, base_url):
        if self.is_recursive_request():
            return

        assert base_url

        # Log the user-agent and referrer, to see who is linking to us.
        logging.debug('@MirrorHandler | user_agent: "%s"; referer: "%s"', self.request.user_agent, self.request.referer)
        logging.debug('@MirrorHandler | base_url: "%s"; request.url: "%s"', base_url, self.request.url)

        translated_address = self.get_relative_url()[1:]  # remove leading /
        if translated_address.startswith('http'):
            (scheme, url) = translated_address.split('_', 1)
            mirrored_url = '%s://%s' % (scheme, url)
        else:
            mirrored_url = 'http://%s' % translated_address

        content = MirroredContent.fetch(base_url, translated_address, mirrored_url)

        for (key, value) in content.headers.iteritems():
            self.response.headers[key] = value
        if not DEBUG:
            self.response.headers['cache-control'] = 'max-age=%d' % EXPIRATION_DELTA_SECONDS

        self.response.out.write(content.data)


app = webapp2.WSGIApplication([(r"/", HomeHandler), (r"/([^/]+).*", MirrorHandler)], debug=DEBUG)