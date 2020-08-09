#!/usr/bin/env python3
import db
import hashlib
import json
import logging
import math
import os
import re
import redis
import requests
import sys
import time
import lib
import urllib
import urllib.request

r = redis.Redis(host='localhost', port=6379, db=0,charset="utf-8", decode_responses=True)

config = lib.get_config()
world_key = config.get('world') 
world_key_ix = 0
alpha_key = config.get('alpha')

with open('ticker-list.txt') as f:
  ticker_list = f.read().split('\n')

print("\n".join(ticker_list))
sys.exit(0)

last = time.time()
delay = math.ceil(12)

def seteasy(row): 
  ix = 0
  special = {'RYAAY': 'RyanAir'}
  EXTRA = ',?( ?&? Co.,?| &| and| Technologies|),? (inc.?|p\.?l\.?c\.?|Incorporated|Ltd\.|N.V.|AG|Holdings|Group|US|ETF|Limited|Corporation|Group|Company|Consolidated|Aktiengesellschaft|Companies|Co.|S\.?A\.?|SE|\(publ\)|NV|A\/S|Corp\.|Series [A-E]|(Common|Plc) New|Registered|Industries|L\.?P\.?|Class [A-F]\.?|\([a-z]*\)|AD[RS]|Subordinate|American Depositary Shares|Sponsored|Common Stock|Holding|Communications|International|Technologies)$'
  PRE = '^(The) '
  if row['ticker'] in special:
    row['easyname'] = special[row['ticker']]

  elif row['ticker'] in ['AIG', 'TIF', 'NWS', 'FTC']:
    row['easyname'] = re.sub(',? Inc.', '', row['name'], flags=re.IGNORECASE)

  else:
    row['easyname'] = re.sub('([a-z])([A-Z])', r'\1&shy;\2', row['name'])
    while True:
      reductum = re.sub(PRE, '', 
        re.sub(EXTRA, '', row['easyname'], flags=re.IGNORECASE), flags=re.IGNORECASE
      )
      if reductum == row['easyname']:
        break
      row['easyname'] = reductum
      ix += 1
 
  if row.get('industry'):
    row['industry'] = re.sub('REITS', 'Real Estate', row['industry'], flags=re.IGNORECASE)
    row['industry'] = re.sub('(^.+) - (.+)', r'\2 \1', row['industry'])
    row['industry'] = re.sub('(integrated|defensive|application)', '', row['industry'],  flags=re.IGNORECASE)

  #print('{} {:30s} | {}'.format(ix, row['easyname'], row['name']))
  return row

def ticker2name(ticker):
  res = db.run('select * from stock where ticker="{}"'.format(ticker), with_dict=True).fetchone()
  name = None

  if res is not None:
    name = res['name']

  if name is None:
    res = {'ticker': ticker}

    payload_raw = cache_get('https://financialmodelingprep.com/api/v3/company/profile/{}'.format(ticker)).strip()
    payload = json.loads(payload_raw)

    if payload_raw == '{ }':
      # First we accept our legacy redis
      res['name'] = r.hget('name', ticker)

      # if that doesn't work then we'll try to get it on the interwebs
      if not res['name']:
        global world_key_ix
        raw = cache_get('https://api.worldtradingdata.com/api/v1/stock?symbol={}'.format(ticker), append='&api_token={}'.format(world_key[world_key_ix]))
        world_key_ix = (world_key_ix + 1) % len(world_key)
        data = json.loads(raw)

        try:
          print(raw)
          res['name'] = data['data'][0]['name']

        except Exception as ex:
          print(ticker, data)

    else:
      res['raw'] = payload_raw
      for x in ['description', 'sector', 'industry']:
        res[x] = payload['profile'][x]

      res['name'] = payload['profile']['companyName']

    res = seteasy(res)
    db.insert('stock', res)

  # so by now we should have a "res" with the right info, I hope....
  if not res.get('easyname') or True:
    res = seteasy(res)
    update = {'easyname': res['easyname']}
    if res.get('industry'):
      update['industry'] = res['industry']
    db.update('stock', {'ticker': ticker}, res)
  
  return [ticker, res.get('easyname'), res.get('industry')]

get_names = lambda nameList: [ ticker2name(x) for x in nameList ]

def cache_get(url, append = False, force = False, wait_until = False, cache_time = 60 * 60 * 24 * 30):
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
  


def historical(instrumentList = ['MSFT']):
  for instrument in instrumentList:
    try:
      data = my_trader.get_historical_quotes(instrument, 'day', 'week')
    except:
      login(force=True)
      return historical(instrumentList)

    duration = 60 * 24
    if data:
      for row in data['historicals']:
        db.insert('historical', {
          'ticker': instrument,
          'open': row['open_price'],
          'close': row['close_price'],
          'low': row['low_price'],
          'high': row['high_price'],
          'begin': row['begins_at'],
          'duration': duration
        })



nodate = lambda what: [[x[0], x[1]] for x in db.run(what).fetchall()]

def get_dates(fields = '*'):
  end = "and close > 0.1 group by ticker"
  return {
    'yesterday': nodate(f"SELECT {fields},max(begin) FROM historical GROUP BY ticker ORDER BY begin DESC"),
    'week': nodate(f"SELECT {fields},min(begin) FROM historical WHERE begin > strftime('%Y-%m-%d', 'now', '-7 day') group by ticker"),
    'month': nodate(f"""SELECT {fields},min(begin) FROM historical WHERE 
      begin > strftime('%Y-%m-%d', 'now', '-1 month') and
      begin < strftime('%Y-%m-%d', 'now', '-21 day') {end}"""),
    'year': nodate(f"""SELECT {fields},min(begin) FROM historical WHERE 
      begin > strftime('%Y-%m-%d', 'now', '-1 year') and
      begin < strftime('%Y-%m-%d', 'now', '-11 month') {end}"""),
    'decade': nodate(f"""SELECT {fields},min(begin) FROM historical WHERE 
      begin > strftime('%Y-%m-%d', 'now', '-10 year') and
      begin < strftime('%Y-%m-%d', 'now', '-9 year') {end}""")
  }


def get_archive(stockList):
  global last
  ix = 0
  ttl = 3 * len(stockList)

  print("Gathering {} stocks".format(len(stockList)))
  for name,duration in [('MONTHLY', 365.25/12), ('DAILY', 1), ('WEEKLY',7)]:
    duration *= (60 * 24) 
    for stock in stockList:
      stock = stock.upper()
      print("{:6.3f} {} {} ".format(100 * ix / ttl, name, stock))

      force = False
      while True:
        ix += 1
        url = "https://www.alphavantage.co/query?function=TIME_SERIES_{}_ADJUSTED&symbol={}".format(name, stock)
        cache_time = max(60 * 60 * 24, duration / 2)
        resraw = cache_get(url, force = force, append = '&apikey={}'.format(alpha_key[ix % len(alpha_key)]), wait_until = last + delay, cache_time = cache_time)
        last = time.time()

        resjson = json.loads(resraw)
        if "Note" in resjson or 'Error Message' in resjson:
          force = True

        else:
          break

      for k,v in resjson.items():
        if k == 'Meta Data':
          continue

        for date,row in v.items():
          db.insert('historical', {
            'ticker': stock,
            'open': row['1. open'],
            'high': row['2. high'],
            'low': row['3. low'],
            'close': row['4. close'],
            'begin': date,
            'duration': duration
          })
