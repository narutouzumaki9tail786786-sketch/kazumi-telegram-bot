import sys, requests
sys.stdout.reconfigure(encoding='utf-8')
from kazumi.database import users_collection, balance_logs_collection
from datetime import datetime

ALPHA_ID = 8419685066

BANK_YESTERDAY = 1_674_653_509
BANK_70PCT = int(BANK_YESTERDAY * 0.70)  # 1,172,257,456

user = users_collection.find_one({"user_id": ALPHA_ID})
current_bank = int(user.get("bank", 0))

print(f"Kal ka bank     : {BANK_YESTERDAY:,}")
print(f"30% cut         : {BANK_YESTERDAY - BANK_70PCT:,}")
print(f"70% return      : {BANK_70PCT:,}")
print(f"Current bank    : {current_bank:,}")
print()

# Set bank to 70% of yesterday
users_collection.update_one(
    {"user_id": ALPHA_ID},
    {"$set": {"bank": BANK_70PCT}}
)

# Log the action
balance_logs_collection.insert_one({
    "user_id": ALPHA_ID,
    "delta": BANK_70PCT - current_bank,
    "direction": "credit",
    "category": "admin_rebalance",
    "reason": "Bank restored to 70% of pre-audit balance (Jul 24 audit — 30% cut applied)",
    "old_balance": current_bank,
    "new_balance": BANK_70PCT,
    "source": "admin_audit",
    "meta": {
        "scope": "bank",
        "bank_before": current_bank,
        "bank_after": BANK_70PCT,
        "yesterday_bank": BANK_YESTERDAY,
        "pct_returned": 70,
        "audit_date": "2026-07-24"
    },
    "created_at": datetime.utcnow()
})

# Confirm
user_after = users_collection.find_one({"user_id": ALPHA_ID})
final_wallet = int(user_after.get("balance", 0))
final_bank = int(user_after.get("bank", 0))

print("=== DONE ===")
print(f"Name    : {user_after.get('name')}")
print(f"Wallet  : {final_wallet:,}  (unchanged)")
print(f"Bank    : {current_bank:,}  -->  {final_bank:,}")

# Send DM to ALPHA
BOT_TOKEN = "8541210855:AAH7k-O1hQ5S5a4MpGaHrxB192OlbRm5IiI"
msg = (
    "<b>Bank Balance Update — Kazumi Admin</b>\n\n"
    "As part of the <b>July 24 Economy Audit</b>, your bank has been restored:\n\n"
    f"<b>Bank Returned:</b> <code>${final_bank:,}</code>\n"
    f"<i>(70% of your pre-audit bank balance of ${BANK_YESTERDAY:,})</i>\n\n"
    "<i>— Kazumi Admin Team</i>"
)
resp = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    data={"chat_id": ALPHA_ID, "text": msg, "parse_mode": "HTML"},
    timeout=15
)
r = resp.json()
print()
if r.get("ok"):
    print("DM sent to ALPHA!")
else:
    print(f"DM failed: {r.get('description', str(r))}")
