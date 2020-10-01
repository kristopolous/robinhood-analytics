#!/usr/bin/env python3
import sys
import logging
import atexit

import readline
import os
import robin
import db
import pathlib

db.upgrade()

FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)
logger = logging.getLogger(__name__)
db.set_log(logger)
readline.parse_and_bind('tab: complete')
histfile = os.path.join(os.path.expanduser("~"), ".robby-hist")
pathlib.Path(histfile).touch()
atexit.register(readline.write_history_file, histfile)
readline.read_history_file(histfile)
readline.set_history_length(1000)

while True:
  try:
    cmd = input('> ').split(' ') 
  except Exception as ex:
    print(ex) 
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
      raise ex

