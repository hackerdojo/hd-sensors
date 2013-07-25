#!/usr/bin/env python

from datetime import datetime
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util, template
from google.appengine.ext import db
import logging
import pprint
import urllib
import re
import json



class AlarmEvent(db.Model):
  event = db.StringProperty(required=True)
  zone = db.StringProperty(required=True)
  created = db.DateTimeProperty(auto_now_add=True)

class IndexHandler(webapp.RequestHandler):
    def get(self):
        alarmevents = AlarmEvent.all().fetch(100)
        self.response.out.write(template.render('templates/index.html', locals()))

class LogHandler(webapp.RequestHandler):
    def get(self):
        event = self.request.get('event')
        zone = self.request.get('zone')
        ae = AlarmEvent(event=event, zone=zone)
        ae.put()
        self.response.set_status(200)

    def post(self):
        event = self.request.get('event')
        zone = self.request.get('zone')
        ae = AlarmEvent(event=event, zone=zone)
        ae.put()
        self.response.set_status(200)



app = webapp.WSGIApplication([
    ('/api/log', LogHandler),
    ('/', IndexHandler)],
    debug=True)
