#!/usr/bin/env python3
import urllib.request
import json
import time
import hashlib

from . import db
from . import lib

import configparser
config = configparser.ConfigParser()
config.read('secrets.ini')

key = config['config']['alpha']
last = time.time()


def historical(stockList):
    global last
    for stock in stockList:
        url = "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={}&apikey={}".format(
            stock, key)
        resraw = lib.cache_get(url, wait_until=last + 20)
        last = time.time()

        resjson = json.loads(resraw)
        if "Note" in resjson:
            resraw = lib.cache_get(url, force=True, wait_until=last + 20)
            last = time.time()
            resjson = json.loads(resraw)

        if 'Time Series (Daily)' not in resjson:
            print(resraw)
            return

        duration = 60 * 24
        for date, row in resjson['Time Series (Daily)'].items():
            db.insert('historical', {
                'ticker': stock,
                'open': row['1. open'],
                'high': row['2. high'],
                'low': row['3. low'],
                'close': row['4. close'],
                'begin': date,
                'duration': duration
            })
