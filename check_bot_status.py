import sys, requests
sys.stdout.reconfigure(encoding='utf-8')

BOT_TOKEN = "8541210855:AAH7k-O1hQ5S5a4MpGaHrxB192OlbRm5IiI"

resp = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo", timeout=10)
r = resp.json()
wh = r.get("result", {})
url = wh.get("url", "")
pending = wh.get("pending_update_count", 0)
last_err = wh.get("last_error_message", "None")

print("=== BOT MODE CHECK ===")
if url:
    print(f"Mode        : WEBHOOK")
    print(f"Webhook URL : {url}")
else:
    print(f"Mode        : POLLING (webhook empty)")

print(f"Pending     : {pending} updates")
print(f"Last error  : {last_err}")
