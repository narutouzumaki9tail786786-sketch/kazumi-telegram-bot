import sys
sys.stdout.reconfigure(encoding='utf-8')
from kazumi.database import users_collection, balance_logs_collection

ALPHA_ID = 8419685066

# Get ALL logs, sort newest first, look for big DEBIT entries (cuts)
logs = list(balance_logs_collection.find({"user_id": ALPHA_ID}).sort("created_at", -1))
print(f"Total logs: {len(logs)}\n")

print("=== ALL DEBIT (CUT) ENTRIES ===")
total_cut = 0
for log in logs:
    delta = log.get("delta", 0)
    if delta < 0:
        ts = log.get("created_at")
        ts_str = ts.strftime("%d %b %Y  %I:%M %p") if ts else "?"
        old_b = log.get("old_balance", 0)
        new_b = log.get("new_balance", 0)
        category = log.get("category", "?")
        reason = log.get("reason", "?")
        total_cut += abs(delta)
        print(f"[{ts_str}]  CUT: -{abs(delta):,}")
        print(f"   {old_b:,} -> {new_b:,}  |  {category}  |  {reason}")
        print()

print(f"Total cut so far (from logs): {total_cut:,}")
print()

# Also show big credits (aviator wins)
print("=== TOP 10 BIGGEST CREDITS (wins) ===")
credits = sorted([l for l in logs if l.get("delta", 0) > 0], key=lambda x: -x.get("delta", 0))[:10]
for log in credits:
    ts = log.get("created_at")
    ts_str = ts.strftime("%d %b %Y  %I:%M %p") if ts else "?"
    delta = log.get("delta", 0)
    old_b = log.get("old_balance", 0)
    new_b = log.get("new_balance", 0)
    category = log.get("category", "?")
    reason = log.get("reason", "?")
    print(f"[{ts_str}]  +{delta:,}  |  {category}  |  {reason}")
    print(f"   {old_b:,} -> {new_b:,}")
    print()
