#!/usr/bin/env python3
import urllib.request
import hashlib
import time
import configparser
import redis


r = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
    charset="utf-8",
    decode_responses=True
)


def get_config():
  cp = configparser.ConfigParser()
  cp.read('secrets.ini')
  config = dict(cp['config'])

  for i in ['alpha', 'world']:
    val = config.get(i)
    if val:
      config[i] = val.split(',')

  return config


def cache_get(url, force=False, wait_until=False):
    key = "c:{}".format(hashlib.md5(url.encode('utf-8')).hexdigest())
    if not r.exists(key) or force:
        if wait_until:
            time.sleep(wait_until - time.time())

        req = urllib.request.Request(url)

        with urllib.request.urlopen(req) as response:
            r.set(key, response.read(), 60 * 60 * 12)

    return r.get(key)
