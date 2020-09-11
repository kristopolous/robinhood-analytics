#!/usr/bin/env python3
import sys
import logging

import robin
import db

db.upgrade()

FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)
db.set_log(logger)

while True:
  print("> ", end="")

  try:
    cmd = input().split(' ')
  except:
    sys.exit(0)

  if cmd[0] == 'help':
    help(robin)
  elif cmd[0] == 'q':
    sys.exit(0)
  elif cmd[0]:
    try:
      eval("robin." + cmd[0])(*cmd[1:])
    except Exception as ex:
      print("Woops: {}".format(ex))
