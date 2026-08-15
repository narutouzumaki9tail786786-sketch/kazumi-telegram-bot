import sys
sys.stdout.reconfigure(encoding='utf-8')
from kazumi.database import users_collection, balance_logs_collection
from kazumi.ledger import adjust_user_balance
from datetime import datetime, timezone

ALPHA_ID = 8419685066

# Yesterday's closing balance (last entry before July 24 IST midnight)
today_ist_start_utc = datetime(2026, 7, 23, 18, 30, 0)

last_before_today = balance_logs_collection.find_one(
    {"user_id": ALPHA_ID, "created_at": {"$lt": today_ist_start_utc}},
    sort=[("created_at", -1)]
)

balance_yesterday = last_before_today.get("new_balance", 0) if last_before_today else 0
balance_70pct = int(balance_yesterday * 0.70)

print(f"Kal ki closing balance : {balance_yesterday:,}")
print(f"70% of yesterday       : {balance_70pct:,}")
print()

# Current balance
user = users_collection.find_one({"user_id": ALPHA_ID})
current_bal = int(user.get("balance", 0))
print(f"Current wallet balance : {current_bal:,}")
print()

# Calculate the delta needed to set wallet to balance_70pct
# We directly set via $set to avoid precision issues with huge numbers
users_collection.update_one(
    {"user_id": ALPHA_ID},
    {"$set": {"balance": balance_70pct}}
)

# Log the admin action
balance_logs_collection.insert_one({
    "user_id": ALPHA_ID,
    "delta": balance_70pct - current_bal,
    "direction": "debit",
    "category": "admin_rebalance",
    "reason": "Aviator bug earnings removed. Wallet set to 70% of pre-bug balance (Jul 24 audit)",
    "old_balance": current_bal,
    "new_balance": balance_70pct,
    "chat_id": None,
    "target_user_id": None,
    "source": "admin_audit",
    "meta": {
        "yesterday_balance": balance_yesterday,
        "pct_returned": 70,
        "audit_date": "2026-07-24"
    },
    "created_at": datetime.utcnow()
})

# Confirm
user_after = users_collection.find_one({"user_id": ALPHA_ID})
final_bal = int(user_after.get("balance", 0))
final_bank = int(user_after.get("bank", 0))

print("=== ACTION COMPLETE ===")
print(f"Name      : {user_after.get('name')}")
print(f"Wallet    : {current_bal:,}  -->  {final_bal:,}")
print(f"Bank      : {final_bank:,} (unchanged)")
print(f"Audit note: Bug aviator earnings removed. 70% of kal ka balance ({balance_yesterday:,}) return kiya.")
