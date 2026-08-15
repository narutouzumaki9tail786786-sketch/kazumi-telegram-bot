import sys, requests
sys.stdout.reconfigure(encoding='utf-8')

BOT_TOKEN = "8541210855:AAH7k-O1hQ5S5a4MpGaHrxB192OlbRm5IiI"
WORKER_URL = "https://kazumi-webhook-relay.abdulstoreapi.workers.dev"
WEBHOOK_FULL_URL = f"{WORKER_URL}/webhook/{BOT_TOKEN}"

print(f"Setting webhook to: {WEBHOOK_FULL_URL}")

# Delete old webhook first
r = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
    data={"drop_pending_updates": True},
    timeout=10
).json()
print(f"Delete old: {r.get('description', r)}")

# Set new webhook
r2 = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    data={
        "url": WEBHOOK_FULL_URL,
        "drop_pending_updates": True,
        "max_connections": 100,
        "allowed_updates": '["message","callback_query","chat_member","my_chat_member","inline_query","chosen_inline_result","pre_checkout_query","shipping_query"]'
    },
    timeout=10
).json()
print(f"Set new: {r2.get('description', r2)}")

if r2.get("ok"):
    print(f"\n✅ WEBHOOK SET SUCCESSFULLY!")
    print(f"URL: {WEBHOOK_FULL_URL}")
else:
    print(f"\n❌ Failed: {r2}")

# Verify
r3 = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo", timeout=10).json()
wh = r3.get("result", {})
print(f"\n=== Verification ===")
print(f"URL     : {wh.get('url')}")
print(f"Pending : {wh.get('pending_update_count')}")
print(f"Error   : {wh.get('last_error_message', 'None')}")
