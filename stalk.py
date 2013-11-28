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
    def __init__(self, url, fn, config, delete=None):
        self.url = url
        self.fn = config['path'] + '/' + fn
        self.config = config
        self.delete = [d.encode() for d in delete] if delete is not None else None

        head_result = requests.head(url)
        self.has_content_length = head_result.headers.get('Content-Length') is not None
        self.has_last_modified = head_result.headers.get('Last-Modified') is not None

        if self.has_last_modified and not exists(fn + ".lastmod"):
            with open(self.fn + '.lastmod', 'w') as f:
                f.write(head_result.headers['Last-Modified'])

        elif self.has_content_length and not exists(fn + ".length"):
            with open(self.fn + '.length', 'w') as f:
                f.write(head_result.headers['Content-Length'])

        if not exists(self.fn + ".saved"):
            with open(self.fn + '.saved', 'wb') as f:
                data = requests.get(self.url).content
                if self.delete:
                    data = self.delete_lines(data.split(b'\n'), self.delete)
                f.write(data)

    def update(self, data=None):
        if data is None:
            try:
                response = requests.get(self.url)
            except Exception as e:
                logger.error(e)
                return

            if response.status_code != 200:
                logger.error("[%s] %s %s" % (self.url, response.status_code, response.reason))
                logger.error("[%s] Skipping for now." % (self.url))
                return
            data = response.content

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

    def delete_lines(self, lines, deletes):
        o = []
        for line in lines:
            found = False

            for d in deletes:
                if d in line:
                    logger.debug("Removed line: '%s'" % line.decode())
                    found = True
                    break

            if found:
                continue
            o.append(line)

        return b'\n'.join(o)

    def stalk(self):
        if self.delete is not None:
            try:
                x = requests.get(self.url)
            except Exception as e:
                logger.error(e)
                return

            if x.status_code != 200:
                logger.warn("[%s] %s %s" % (self.url, x.status_code, x.reason))
                logger.warn("[%s] Skipping for now." % (self.url))
                return

            old = None
            with open(self.fn + '.saved', 'rb') as f:
                old = sha1(f.read())
            
            data = self.delete_lines(x.content.split(b'\n'), self.delete)
            new = sha1(data)
            if old != new:
                logger.info("[%s] SHA1 change detected after deletes!" % self.url)
                self.update(data)
            else:
                logger.info("[%s] No change in SHA1." % self.url)

        elif self.has_last_modified:
            try:
                x = requests.head(self.url)
            except Exception as e:
                logger.error(e)
                return

            if x.status_code != 200:
                logger.warn("[%s] %s %s" % (self.url, x.status_code, x.reason))
                logger.warn("[%s] Skipping for now." % (self.url))
                return

            new = parse_date(x.headers['Last-Modified'])
            old = None
            with open(self.fn + '.lastmod') as f:
                old = parse_date(f.read())

            if old != new:
                logger.info("[%s] Last modified change detected!" % self.url)
                self.update()
            else:
                logger.info("[%s] No change in last modified." % self.url)

        elif self.has_content_length:
            try:
                x = requests.head(self.url)
            except Exception as e:
                logger.error(e)
                return

            if x.status_code != 200:
                logger.warn("[%s] %s %s" % (self.url, x.status_code, x.reason))
                logger.warn("[%s] Skipping for now." % (self.url))
                return

            old = None
            with open(self.fn + '.length') as f:
                old = f.read()

            if x.headers['Content-Length'] != old:
                logger.info("[%s] Content length change detected! (%s, %s)" % (
                    self.url, old, x.headers['Content-Length']))
                self.update()
            else:
                logger.info("[%s] No change in content length." % self.url)

        else:
            try:
                x = requests.get(self.url)
            except Exception as e:
                logger.error(e)
                return

            if x.status_code != 200:
                logger.warn("[%s] %s %s" % (self.url, x.status_code, x.reason))
                logger.warn("[%s] Skipping for now." % (self.url))
                return

            old = None
            with open(self.fn + '.saved', 'rb') as f:
                old = sha1(f.read())
            new = sha1(x.content)
            if old != new:
                logger.info("[%s] SHA1 change detected!" % self.url)
                self.update(x.content)
            else:
                logger.info("[%s] No change in SHA1." % self.url)

if __name__ == "__main__":
    import sys
    cfg = json.load(open(sys.argv[1]))
    stalkers = []
    for target in cfg['targets']:
        stalkers.append(Stalker(target['url'], target['fn'], cfg, target.get('delete')))

    try:
        while True:
            for stalker in stalkers:
                stalker.stalk()
            logger.info("Sleeping for %s seconds." % cfg['sleep'])
            sleep(cfg['sleep'])
    except KeyboardInterrupt:
        sys.exit(0)

