#!/usr/bin/env python3
import redis
import time
import sys
import json
import sys
import configparser
import pdb
import logging

from pprint import pprint

from p import robin
from p import lib
from p import db

config = configparser.ConfigParser()
config.read('secrets.ini')

lib.upgrade()

"""
if len(sys.argv) < 2:
    print("Login username required")
    sys.exit(0)
robin.login(sys.argv[1])
"""

FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)
db.set_log(logger)

robin.config = config['config']
"""
robin.login(
    username=config['config']['user'], 
    password=config['config']['password'],
    device_token=config['config']['token']
)

"""

while True:
    print("> ", end="")
    cmd = input().split(' ')
    if cmd[0] == 'q':
      sys.exit(0)
    if cmd[0]:
      eval("robin." + cmd[0])(*cmd[1:])
