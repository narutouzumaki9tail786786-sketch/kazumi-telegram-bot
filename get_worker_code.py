import sys, requests
sys.stdout.reconfigure(encoding='utf-8')

ACCOUNT_ID = "3f6a0bf64cc629be4e4cb6dd132e3f28"
TOKEN = "cfoat_Ef3c-0-9iUGvSe26eKuqEwsMkp7KW6uO4dC3MlFMMF4.u5-u2Tew_rDygfD8S1BLEXIrhcZ8bhekUoz3n5QUSmI"
WORKER_NAME = "kazumi-api-proxy"

headers = {"Authorization": f"Bearer {TOKEN}"}

# Get worker script
resp = requests.get(
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/workers/scripts/{WORKER_NAME}",
    headers={**headers, "Accept": "application/javascript"},
    timeout=15
)

print(f"Status: {resp.status_code}")
print(resp.text[:5000])
