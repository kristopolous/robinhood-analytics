import os
import sys
import sqlite3
import time
import json
from threading import Lock

DefaultDbFile = 'trades.db'

_PROCESSOR = {
  "users"
}

_SCHEMA = {
  'stock' : [
    ('id', 'integer primary key autoincrement'),
    ('ticker', 'text unique'),
    ('name', 'text'),
    ('easyname', 'text'),
    ('industry', 'text'),
    ('sector', 'text'),
    ('description', 'text'),
    ('raw', 'text'),
    ('created_at', 'datetime default current_timestamp')
  ],

  'instruments': [
    ('id', 'integer primary key autoincrement'),
    ('ticker', 'text unique'),
    ('name', 'text'),
    ('description', 'text')
  ],
  'trades': [
    ('id', 'integer primary key autoincrement'),
    ('rbn_id', 'text unique'),
    ('created', 'datetime'),
    ('side', 'text'),
    ('price', 'float'),
    ('quantity', 'float'),
    ('instrument', 'text')
  ],
  # This is supposed to be enough for a candlestick
  'historical': [
    ('id', 'integer primary key autoincrement'),
    ('uuid', 'text'),
    ('ticker', 'text'),
    ('open', 'real'),
    ('close', 'real'),
    ('low', 'real'),
    ('high', 'real'),
    ('begin', 'datetime'),
    #
    # There's a small unit set here:
    # minute, hour, day, week essentially. There's also I believe
    # a 5 and 30 minute constant somewhere.  Regardless, it's
    # not a large set.
    #
    ('duration', 'integer'),
    ('unique', '(begin,ticker,duration)')
  ]
}


user = {}
_dbcount = 0
_lock = Lock()
_log = None


def _checkForTable(what):
  global _SCHEMA
  if what not in _SCHEMA:
    raise Exception(f"Table {what} not found")


def process(res, table, what):
  if table in _PROCESSOR:
    unwrap = False
    if type(res) is not list:
      unwrap = True
      res = [ res ]
     
    for ix, row in enumerate(res):
      if row:
        # The SQLITE3.ROW type is immutable so
        # we need to convert it to a dict in order
        # to get it back to our user
        row = dict(row)
        for k, v in _PROCESSOR[table].items():
          # If a pre/post is defined for this key
          # on this table then we do it
          if v[what]:
            row[k] = v[what](row[k], row)

        res[ix] = row

    if unwrap:
      res = res[0]
  
  return res


def get(table, get_value=False, get_key="id"):
  _checkForTable(table)

  res = run(f"select * from {table} where {get_key}=?", args=(get_value,))

  if res:
    return process(res.fetchone(), table, 'post')
  else:
    return None


def run(query, args=None, with_last=False, db=None):
  global _lock

  """
  if args is None:
  print "%d: %s" % (_dbcount, query)
  else:
  $print "%d: %s (%s)" % (_dbcount, query, ', '.join([str(m) for m in args]))
  """

  _lock.acquire()
  if db is None:
    db = connect()

  try:
    if args is None:
      res = db['c'].execute(query)
    else:
      res = db['c'].execute(query, args)

    db['conn'].commit()
    last = db['c'].lastrowid

    if db['c'].rowcount == 0:
      raise Exception("0 rows")

  except Exception as exc:
    raise exc

  finally:
    _lock.release()

  if with_last:
    return res, last

  return res


def upgrade():
  my_set = __builtins__['set']
  db = connect()

  for table, schema in list(_SCHEMA.items()):
    existing_schema = db['c'].execute(
      'pragma table_info(%s)' %
      table).fetchall()
    existing_column_names = [str(row[1]) for row in existing_schema]

    our_column_names = [row[0] for row in schema]

    # print table, existing_column_names, our_column_names

    to_add = my_set(our_column_names).difference(
      my_set(existing_column_names))

    to_add = filter(lambda x: x != 'unique', to_add)

    # These are the things we should add ... this can be an empty set,
    # that's fine.
    for key in to_add:
      #
      # sqlite doesn't support adding things into positional places (add column after X)
      # they just get tacked on at the end ... which is fine - you'd have to rebuild
      # everything to achieve positional columns - that's not worth it - we just always
      # tack on at the end as a policy in our schema and we'll be fine.
      #
      # However, given all of that, we still need the schema
      #
      our_schema = schema[our_column_names.index(key)][1]
      # print 'alter table %s add column %s %s' % (table, key,
      # our_schema)
      db['c'].execute(
        'alter table %s add column %s %s' %
        (table, key, our_schema))
      db['conn'].commit()

    to_remove = my_set(existing_column_names).difference(
      my_set(our_column_names))

    if len(to_remove) > 0:
      our_schema = ','.join(["%s %s" % (key, klass)
                   for key, klass in schema])
      our_columns = ','.join(our_column_names)

      drop_column_sql = """
      CREATE TEMPORARY TABLE my_backup(%s);
      INSERT INTO my_backup SELECT %s FROM %s;
      DROP TABLE %s;
      CREATE TABLE %s(%s);
      INSERT INTO %s SELECT %s FROM my_backup;
      DROP TABLE my_backup;
      """ % (our_schema, our_columns, table, table, table, our_schema, table, our_columns)

      for sql_line in drop_column_sql.strip().split('\n'):
        db['c'].execute(sql_line)

      db['conn'].commit()

def connect(db_file=None, with_dict=False):
  # A "singleton pattern" or some other fancy $10-world style of maintaining
  # the database connection throughout the execution of the script.
  # Returns the database instance.
  global _dbcount

  if not db_file:
    db_file = DefaultDbFile

  #
  # We need to have one instance per thread, as this is what
  # sqlite's driver dictates ... so we do this based on thread id.
  #
  # We don't have to worry about the different memory sharing models here.
  # Really, just think about it ... it's totally irrelevant.
  #

  instance = {}

  if not os.path.exists(db_file):
    sys.stderr.write("Info: Creating db file %s\n" % db_file)

  conn = sqlite3.connect(db_file)

  if with_dict:
    conn.row_factory = dict_factory

  instance.update({
    'conn': conn,
    'c': conn.cursor()
  })

  if _dbcount == 0:

    for table, schema in list(_SCHEMA.items()):
      dfn = ','.join(["%s %s" % (key, klass) for key, klass in schema])
      create = "CREATE TABLE IF NOT EXISTS {}({})".format(table, dfn)
      instance['c'].execute(create)

    instance['conn'].commit()

  _dbcount += 1

  return instance


def _insert(table, data):
  _checkForTable(table)

  known_keys = [x[0] for x in _SCHEMA[table]]
  insert_keys = list(data.keys() & known_keys)
  shared_keys = insert_keys

  # Make sure that the ordinal is maintained.
  toInsert = [data[key] for key in insert_keys]

  key_string = ','.join(insert_keys)

  value_list = ['?'] * len(insert_keys)
  value_string = ','.join(value_list)

  return [
    'insert into {}({}) values({})'.format(
    table,
    key_string,
    value_string),
    shared_keys,
    toInsert]


def upsert(table, data):
  qstr, key_list, values = _insert(table, data)
  update_list = ["{}=?".format(key) for key in key_list]

  qstr += "on conflict(id) do update set {}".format(','.join(update_list))

  try:
    res, last = run(qstr, values + values, with_last = True)
    return last

  except Exception as exc:
    _log.warning("Unable to upsert a record {} ({})".format(','.join([str(x) for x in values]), exc))


def insert(table, data, silent=False):
  last = False
  qstr, key_list, values = _insert(table, data)
  try:
    res, last = run(qstr, values, with_last=True)

  except Exception as exc:
    if not silent:
      _log.warning("Unable to insert a record {}: {} ({})".format(qstr, json.dumps(values), exc))

  return last

def dict_factory(cursor, row):
  d = {}
  for idx, col in enumerate(cursor.description):
    d[col[0]] = row[idx]
  return d


def set_log(logger):
  global _log
  _log = logger.getChild("db")


