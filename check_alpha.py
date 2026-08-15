import sys
sys.stdout.reconfigure(encoding='utf-8')
from kazumi.database import users_collection, balance_logs_collection
from datetime import datetime, timezone

# Search ALPHA user by name
users = list(users_collection.find({"name": {"$regex": "ALPHA", "$options": "i"}}))
print(f"Found {len(users)} users matching ALPHA:")
for u in users:
    uid = u.get("user_id")
    name = u.get("name", "?")
    uname = u.get("username", "")
    bal = u.get("balance", 0)
    bank = u.get("bank", 0)
    print(f"  ID: {uid} | Name: {name} | @{uname} | Wallet: {bal:,} | Bank: {bank:,}")

print()

# Also search by username containing alpha
users2 = list(users_collection.find({"username": {"$regex": "alpha", "$options": "i"}}))
print(f"Found {len(users2)} users with 'alpha' in username:")
for u in users2:
    uid = u.get("user_id")
    name = u.get("name", "?")
    uname = u.get("username", "")
    bal = u.get("balance", 0)
    bank = u.get("bank", 0)
    print(f"  ID: {uid} | Name: {name} | @{uname} | Wallet: {bal:,} | Bank: {bank:,}")
