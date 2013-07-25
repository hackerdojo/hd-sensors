#!/usr/bin/env python

from datetime import datetime
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util, template
import logging
import pprint
import urllib
import re
import json


class IndexHandler(webapp.RequestHandler):
    def get(self):
        self.response.out.write(template.render('templates/index.html', locals()))

#class LogHandler(webapp.RequestHandler):
#    def get(self, pagename, site = PB_WIKI):
#        skip_cache = self.request.get('cache') == '0'
#        version = os.environ['CURRENT_VERSION_ID']
#        shouldRedirect = False
#
#        redirect_urls = {
#          # From: To
#          'give': 'Give',
#          'auction': 'Auction',
#          'Assemble': 'Give',
#          'Mobile%20Device%20Lab': 'MobileDeviceLab',
#          'kickstarter': 'http://www.kickstarter.com/projects/384590180/an-events-space-and-a-design-studio-for-hacker-doj',
#          'Kickstarter': 'http://www.kickstarter.com/projects/384590180/an-events-space-and-a-design-studio-for-hacker-doj',
#          'KICKSTARTER': 'http://www.kickstarter.com/projects/384590180/an-events-space-and-a-design-studio-for-hacker-doj',
#          'key': 'http://signup.hackerdojo.com/key',
#        }
#        if pagename in redirect_urls:
#            url = redirect_urls[pagename]
#            self.redirect(url, permanent=True)
#        else:
#            if CDN_ENABLED:
#                cdn = CDN_HOSTNAME
#            try:
#                pageKey = 'page:%s' % pagename.lower()
#                if not(pagename):
#                    pagename = 'FrontPage'
#                page = _request(PB_API_URL % (site, pagename), cache_ttl=604800, force=skip_cache)
#                # fetch a page where a lowercase version may exist
#                if not(page and "name" in page):
#                  if memcache.get(pageKey):
#                    pagename = memcache.get(pageKey)
#                    page = _request(PB_API_URL % (site, pagename), cache_ttl=604800, force=skip_cache)
#                    shouldRedirect = True
#                # Convert quasi-camel-case to spaced words
#                title = re.sub('([a-z]|[A-Z])([A-Z])', r'\1 \2', pagename)
#                if page and "name" in page:
#                  fiveDays = 432000
#                  memcache.set(pageKey, pagename, fiveDays)
#                  if shouldRedirect:
#                    self.redirect(pagename, permanent=True)
#                  else:
#                    self.response.out.write(template.render('templates/content.html', locals()))
#                else:
#                  raise LookupError
#            except LookupError:
#                self.response.out.write(template.render('templates/404.html', locals()))
#                self.response.set_status(404)



app = webapp.WSGIApplication([
#    ('/api/log', LogHandler),
    ('/', IndexHandler)],
    debug=True)
