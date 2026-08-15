import sys
sys.stdout.reconfigure(encoding='utf-8')
from kazumi.database import users_collection, balance_logs_collection
from datetime import datetime

ALPHA_ID = 8419685066

# July 24 00:00 IST = July 23 18:30 UTC (naive)
today_ist_start_utc = datetime(2026, 7, 23, 18, 30, 0)

# Find last bank-related log before today
# Bank changes are logged with category containing 'bank' or meta bank fields
# Also check all logs before today and look at bank field in user doc snapshots

print("=== Searching for bank balance before July 24 ===\n")

# Look for any log with bank scope or bank category before today
bank_logs = list(balance_logs_collection.find({
    "user_id": ALPHA_ID,
    "created_at": {"$lt": today_ist_start_utc},
    "$or": [
        {"category": {"$regex": "bank", "$options": "i"}},
        {"meta.bank_after": {"$exists": True}},
        {"scope": "bank"},
    ]
}).sort("created_at", -1).limit(10))

print(f"Bank-specific logs before today: {len(bank_logs)}")
for log in bank_logs:
    ts = log.get("created_at").strftime("%d %b %Y %I:%M %p") if log.get("created_at") else "?"
    meta = log.get("meta", {})
    bank_before = meta.get("bank_before", "N/A")
    bank_after = meta.get("bank_after", "N/A")
    reason = log.get("reason", "?")
    category = log.get("category", "?")
    print(f"  [{ts}] {category} | bank: {bank_before} -> {bank_after} | {reason}")

print()

# Direct DB check: what is bank right now
user = users_collection.find_one({"user_id": ALPHA_ID})
current_bank = int(user.get("bank", 0))
current_wallet = int(user.get("balance", 0))
print(f"Current state:")
print(f"  Wallet : {current_wallet:,}")
print(f"  Bank   : {current_bank:,}")
print()

# Check ALL logs before today to find last known bank state in meta
all_logs_before = list(balance_logs_collection.find({
    "user_id": ALPHA_ID,
    "created_at": {"$lt": today_ist_start_utc},
    "meta.bank_after": {"$exists": True}
}).sort("created_at", -1).limit(5))

print(f"Logs with bank_after meta before today: {len(all_logs_before)}")
for log in all_logs_before:
    ts = log.get("created_at").strftime("%d %b %Y %I:%M %p") if log.get("created_at") else "?"
    meta = log.get("meta", {})
    print(f"  [{ts}] bank_after: {meta.get('bank_after')}")
