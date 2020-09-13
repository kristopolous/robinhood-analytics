
def getquote(what):
  key = 's:{}'.format(what)
  res = lib.r.get(key)
  if not res:
    lib.login()
    lib.my_trader.print_quote(what)

    res = json.dumps(lib.my_trader.get_quote(what))
    lib.r.set(key, res, 900)
  return json.loads(res)

