import requests

print("Session...")

s = requests.Session()

r = s.get(
    "https://api.binance.com/api/v3/time",
    timeout=10
)

print(r.status_code)
print(r.text)