#!/usr/bin/env python3
from pyrh import Robinhood
import configparser
import os
import hashlib
import redis, json, urllib
import colorsys


r = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
    charset="utf-8",
    decode_responses=True
)

my_trader = False

torgb = lambda *hsl: [int(255 * n) for n in colorsys.hsv_to_rgb(*hsl)]
getsymbols = lambda: sorted([json.loads(v).get('symbol') for k,v in r.hgetall('inst').items()])

def getquote(what):
  what = what.upper()
  key = 's:{}'.format(what)
  res = r.get(key)
  if not res:
    login()
    my_trader.print_quote(what)

    res = json.dumps(my_trader.get_quote(what))
    r.set(key, res, config.get('cache'))

  return json.loads(res)

def get_config():
  cp = configparser.ConfigParser()
  cp.read('secrets.ini')
  config = dict(cp['config'])

  for i in ['alpha', 'world']:
    val = config.get(i)
    if val:
      config[i] = val.split(',')

  return config

config = get_config()

def login():
  global my_trader
  if my_trader:
    return

  username = config.get('user')
  password = config.get('password')
  device_token = config.get('token')

  try:
    my_trader = Robinhood(username=username, password=password, device_token=device_token)

  except Exception as ex:
    raise ex
    print("Password incorrect. Please check your config")
    sys.exit(1)

def cache_get(url, append = False, force = False, wait_until = False, cache_time = 60 * 60 * 24 * 30):
  if not os.path.exists('cache'):
    os.mkdir('cache')

  fname = hashlib.md5(url.encode('utf-8')).hexdigest()
  cname = "cache/{}".format(fname)
  key = "c:{}".format(fname)

  if not r.exists(key) or force:
    if wait_until and wait_until - time.time() > 0:
      time.sleep(wait_until - time.time())

    if append:
      url += append

    req = urllib.request.Request(url)

    with urllib.request.urlopen(req) as response:
      r.set(key, '1', cache_time)
      with open(cname, 'w') as f:
        data = response.read().decode('utf-8')
        f.write(data)


  if not os.path.isfile(cname) or os.path.getsize(cname) == 0:
    data = r.get(key)
    if len(data) < 3:
      return cache_get(url, append = append, force = True, wait_until = wait_until, cache_time = cache_time)

    with open(cname, 'w') as f:
      f.write(r.get(key))

    r.set(key, '1')

  with open(cname, 'r') as f:
    res = f.read()
    return res

