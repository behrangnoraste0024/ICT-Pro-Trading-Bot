import ccxt

exchange = ccxt.binance()

print(exchange.session)

r = exchange.session.get(
    "https://api.binance.com/api/v3/time",
    timeout=10
)

print(r.status_code)
print(r.text)