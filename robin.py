#!/usr/bin/env python3
from pyrh import Robinhood
import urllib
import time
import sys
import json
import os

import db
import lib


def get_archive(stockList):
  global last

  if type(stockList) is str:
    stockList = [stockList]

  ix = 0
  ttl = 3 * len(stockList)

  print("Gathering {} stocks".format(len(stockList)))
  alpha = config.get('alpha')
  if not alpha:
    raise("Hey you need to get an alpha advantage key")

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
        resraw = cache_get(url, 
          force = force, 
          append = '&apikey={}'.format(alpha[ix % len(alpha)]), 
          cache_time = cache_time
        )
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


def getInstrument(url):
  key = url.split('/')[-2]
  res = lib.r.hget('inst', key)

  try:
    res = res.decode("utf-8")
  except BaseException:
    pass

  if not res:
    req = urllib.request.Request(url)

    with urllib.request.urlopen(req) as response:
      res = response.read()

      lib.r.hset('inst', key, res)

  resJson = json.loads(res)

  name = resJson['simple_name']

  if not name:
    name = resJson['name']

    db.insert('instruments', {
      'ticker': resJson['symbol'],
      'name': name
    })

  return res


def historical(stockList=['MSFT']):
  lib.login()

  if type(stockList) is str:
    stockList = [stockList]

  for instrument in stockList:
    data = lib.my_trader.get_historical_quotes(instrument, 'day', 'week')
    duration = 60 * 24
    if data:
      for payload in data.get('results'):
        for row in payload.get('historicals'):
          db.insert('historical', {
            'ticker': instrument,
            'open': row['open_price'],
            'close': row['close_price'],
            'low': row['low_price'],
            'high': row['high_price'],
            'begin': row['begins_at'],
            'duration': duration
          })


def getquote(what):
  key = 's:{}'.format(what)
  res = lib.r.get(key)
  if not res:
    if not lib.my_trader:
      lib.login()
    lib.my_trader.print_quote(what)

    res = json.dumps(lib.my_trader.get_quote(what))
    lib.r.set(key, res, 900)
  return json.loads(res)


def get_history():
  """
  Get your trading history and populates it into the database
  """
  def dividends(data=False):
    print("Dividends")

    if not data:
      tradeList = lib.my_trader.dividends()
    else:
      tradeList = data

    for trade in tradeList['results']:
      db.insert('trades', {
        'side': 'dividend',
        'instrument': trade['instrument'].split('/')[-2],
        'quantity': trade['position'],
        'price': trade['rate'],
        'created': trade['paid_at'],
        'rbn_id': trade['id']
      })

    if tradeList['next']:
      data = lib.my_trader.session.get(tradeList['next'])
      dividends(data.json())


  def trades(data=False):
    print("trades")

    if not data:
      tradeList = lib.my_trader.order_history()
    else:
      tradeList = data

    for trade in tradeList['results']:
      for execution in trade['executions']:

        try:
          db.insert('trades', {
            'side': trade['side'],
            'instrument': trade['instrument'].split('/')[-2],
            'quantity': execution['quantity'],
            'price': execution['price'],
            'created': execution['timestamp'],
            'rbn_id': execution['id']
          })
        except BaseException as ex:
          return

      trade['instrument'] = json.loads(getInstrument(trade['instrument']))

      print(
          "{} {:5s} {:6s}".format(
              trade['created_at'],
              trade['side'],
              trade['instrument']['symbol']))

    if tradeList['next']:
        data = lib.my_trader.session.get(tradeList['next'])
        trades(data.json())

  lib.login()

  trades()
  dividends()


def l():
  """
  Lists the instruments in the portfolio
  """
  symbolList = []

  for k,v in lib.r.hgetall('inst').items():
    v = json.loads(v)
    trades = db.run( 'select count(*) from trades where instrument = ?', (k, )).fetchone()
    if trades[0] > 0:
      name = v.get('simple_name')
      if name is None:
        name = v.get('name')
      symbolList.append("[{:4}] {:<5} ({})".format(trades[0], v.get('symbol'), name))

  print("\n".join(sorted(symbolList)))
  
def hist(ticker):
  """
  Find the performance history for a particular investment
  """

  ticker = ticker.lower()
  uid = False
  symbolList = []
  for k,v in lib.r.hgetall('inst').items():
    v = json.loads(v)
    if v.get('symbol').lower() == ticker:
      uid = k
    symbolList.append(v.get('symbol'))

  if not uid:
    print("woooah, wtf is {}".format(ticker))
    return

  ttl_buy = 0
  avg_buy = 0
  ttl_sell = 0
  shares_sell = 0

  rec = {
    'buy': { 'first': 0, 'low': float("inf"), 'high': 0},
    'sell': {'low': float("inf"), 'high': 0}
  }
  atmax = None
  atmax_avg = 0
  atmax_time = 0

  net_buy = 0
  net_sell = 0

  avg_sell = 0
  money = 0
  shares = 0
  week = 24 * 7 * 3600
  last_week = 0
  max_shares = -float('inf')
  min_shares = 0
  first = None

  trades = list(db.run(
    'select side,price,created,quantity,strftime("%s",created),id as unix from trades where instrument = ? order by created asc', (uid, )
    ).fetchall())

  max_holding = 0
  for row in trades:
    sign = 1
    quant = row[3]

    if row[0] == 'dividend':
      continue
    if row[0] == 'sell':
      sign = -1
    if not first:
      first = row

    shares += sign * quant

    if shares > max_shares:
      atmax = row[5]

    max_shares = max(max_shares, shares)
    min_shares = min(min_shares, shares)

  shares = 0
  if min_shares < 0:
    min_shares *= -1
    max_shares += min_shares
    shares += min_shares

  if max_shares == 0:
    unit = 25.0 / 50
  else:
    unit = 25.0 / max_shares 

  rec['buy']['first'] = first[1]

  for row in trades:
    sign = 1

    if row[0] == 'dividend':
      continue

    side = row[0]
    price = row[1]
    quant = row[3]
    ttl = quant * price
    epoch = int(row[4])
    wk = ''

    if epoch - last_week > week:
      last_week = epoch
      wk = '-----'


    if row[0] == 'sell':
      sign = -1
      if shares > 0:
        avg_buy = ttl_buy / shares

      ttl_buy -= (avg_buy * quant)

      ttl_sell += ttl
      shares_sell += quant

      net_sell += ttl
      rec['sell']['high'] = max(rec['sell']['high'], price)
      rec['sell']['low'] = min(rec['sell']['low'], price)
    else:
      rec['buy']['high'] = max(rec['buy']['high'], price)
      rec['buy']['low'] = min(rec['buy']['low'], price)
      net_buy += ttl
      ttl_buy += ttl

      if shares_sell > 0:
        avg_sell = ttl_sell / shares_sell
        #ttl_sell -= (price * quant)
      else:
        avg_sell = 0
        shares_sell = 0
        ttl_sell = 0

    shares += sign * quant
    money += sign * ttl

    if shares > 0:
      avg_buy = ttl_buy / shares
    else:
      avg_sell = 0
      shares_sell = 0
      ttl_sell = 0
    if shares_sell > 0:
      avg_sell = ttl_sell / shares_sell

    if sign == 1:
      sign = ' '
    else:
      sign = '-'

    if row[5] == atmax:
      atmax_avg = avg_buy
      atmax_time = epoch
      atmax_date = row[2][:10]

    rep=''.join(int(shares * unit) * ['*'])
    margin = 0
    if avg_buy > 0:
      margin =  round(100 * avg_sell/avg_buy)

    if margin == 0:
      margin = ''
    else:
      margin -= 100
    
    print("{} {:<7g} {:<25} {:<5g} {:<10g} {:4} {:4} {:>3} {:5} {} {} ".format(sign, round(shares,3), rep, round(price), round(shares * row[1]), round(row[1]), round(avg_buy), round(avg_sell), margin,  row[2][:10], wk))

  reality = net_sell - net_buy + trades[-1][1] * shares
  buy_low_and_sell_high = round(max_shares * max(rec['buy']['high'],rec['sell']['high']) - max_shares * min(rec['sell']['low'], rec['buy']['low']))
  buy_and_hold = round(max_shares * trades[-1][1] - max_shares * first[1])
  hold_at_max = round(max_shares * trades[-1][1] - max_shares * atmax_avg)  
  duration = (time.time() - int(first[4])) / (365.2475 * 24 * 60 * 60)
  atmax_delta = (time.time() - atmax_time) / (365.2475 * 24 * 60 * 60)

  roi = {
    'blash': 100 * abs(buy_low_and_sell_high / reality - 1),
    'ham': 100 * abs(hold_at_max / reality - 1), 
    'bah': 100 * abs(buy_and_hold / reality - 1)
  }

  print("\n".join([
    "({}) buy: {} | sell {} | diff: {}".format(ticker, round(net_buy), round(net_sell), net_sell - net_buy),
    "records:",
    " buy:  {:8.2f} - {:8.2f}".format(rec['buy']['low'], rec['buy']['high']),
    " sell: {:8.2f} - {:8.2f}".format(rec['sell']['low'], rec['sell']['high']),
    "",
    "if you bought max low and sold high:",
    "{} ({}% / {}%)".format(buy_low_and_sell_high, round(roi['blash']), round(roi['blash']/duration)),
    "",
    "if you held when you had max ({} - {}):".format(atmax_date, max_shares),
    "{} ({}% / {}%)".format(hold_at_max, round(roi['ham']), round(roi['ham']/atmax_delta)),
    "",
    "if you bought max at the beginning ({}):".format(first[2][:10]),
    "{} ({}% / {}%)".format(buy_and_hold, round(roi['bah']), round(roi['bah'] / duration)),
    "",
    "your strategy:",
    "{}".format(round(reality))
  ]))

def positions():
  lib.login()

  positionList = lib.my_trader.positions()
  tickerList = []
  computed = 0

  for position in positionList['results']:
    position['instrument'] = json.loads(
      getInstrument(position['instrument']))
    if float(position['quantity']) > 0:
      symbol = position['instrument']['symbol']
      res = getquote(symbol)
      last_price = res['last_extended_hours_trade_price']
      if last_price is None:
        last_price = res['last_trade_price']

      computed += float(position['quantity']) * float(last_price)

      print("{:30s} {:5s} {:5.2f} {:10}".format(
        position['instrument']['name'][:29], symbol, float(position['quantity']), last_price))

  return {'computed': computed, 'positions': positionList}
