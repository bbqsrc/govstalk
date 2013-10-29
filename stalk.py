"""
This file is part of Govstalk.
Copyright (c) 2013  Brendan Molloy

Govstalk is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Govstalk is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Govstalk.  If not, see <http://www.gnu.org/licenses/>.
"""

import requests
import hashlib
import json
import datetime
import logging
import tornado.log

from email.utils import parsedate
from os.path import exists
from bbqutils.email import sendmail, create_email
from subprocess import Popen, PIPE
from time import sleep

logger = logging.getLogger()
ch = logging.StreamHandler()
ch.setFormatter(tornado.log.LogFormatter())
logger.addHandler(ch)
logger.setLevel(logging.INFO)

def sha1(data):
    m = hashlib.sha1()
    m.update(data)
    return m.hexdigest()


def parse_date(text):
    return datetime.datetime(*parsedate(text)[:6])



class Stalker:
    def __init__(self, url, fn, config):
        self.url = url
        self.fn = config['path'] + '/' + fn
        self.config = config

        head_result = requests.head(url)
        self.has_content_length = head_result.headers.get('Content-Length') is not None
        self.has_last_modified = head_result.headers.get('Last-Modified') is not None

        if self.has_content_length and not exists(fn + ".length"):
            with open(self.fn + '.length', 'w') as f:
                f.write(head_result.headers['Content-Length'])

        elif self.has_last_modified and not exists(fn + ".lastmod"):
            with open(self.fn + '.lastmod', 'w') as f:
                f.write(head_result.headers['Last-Modified'])

        if not exists(self.fn + ".saved"):
            with open(self.fn + '.saved', 'wb') as f:
                f.write(requests.get(self.url).content)

    def update(self, data=None):
        if data is None:
            data = requests.get(self.url).text

        proc = Popen(['diff', '-u', self.fn + '.saved', '-'], stdin=PIPE, stdout=PIPE)
        proc.stdin.write(data)
        result = proc.communicate()[0]

        with open(self.fn + '.saved', 'wb') as f:
            f.write(data)

        with open(self.fn + '.lastdiff', 'wb') as f:
            f.write(result)

        self.send_email(result)

    def send_email(self, content):
        sendmail(create_email(
            frm=self.config['from'],
            to=self.config['to'],
            subject="Website Update: %s" % self.url,
            text="URL: %s\n\n%s" % (self.url, content.decode())
        ))
        logger.info("[%s] Email sent." % self.url)

    def stalk(self):
        if self.has_content_length:
            x = requests.head(self.url)
            old = None
            with open(self.fn + '.length') as f:
                old = f.read()

            if x.headers['Content-Length'] != old:
                logger.info("[%s] Content length change detected!" % self.url)
                self.update()
            else:
                logger.info("[%s] No change in content length." % self.url)

        elif self.has_last_modified:
            x = requests.head(self.url)

            new = parse_date(x.headers['Last-Modified'])
            old = None
            with open(self.fn + '.lastmod') as f:
                old = parse_date(f.read())

            if old != new:
                logger.info("[%s] Last modified change detected!" % self.url)
                self.update()
            else:
                logger.info("[%s] No change in last modified." % self.url)

        else:
            x = requests.get(self.url).content
            old = None
            with open(self.fn + '.saved', 'rb') as f:
                old = sha1(f.read())
            new = sha1(x)
            if old != new:
                logger.info("[%s] SHA1 change detected!" % self.url)
                self.update(x)
            else:
                logger.info("[%s] No change in SHA1." % self.url)

if __name__ == "__main__":
    import sys
    cfg = json.load(open(sys.argv[1]))
    stalkers = []
    for target in cfg['targets']:
        stalkers.append(Stalker(target['url'], target['fn'], cfg))

    try:
        while True:
            for stalker in stalkers:
                stalker.stalk()
            sleep(cfg['sleep'])
    except KeyboardInterrupt:
        sys.exit(0)

