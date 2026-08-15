# Copyright (c) 2025 Telegram:- @WTF_Phantom <DevixOP>
# Location: Supaul, Bihar 
#
# All rights reserved.
#
# This code is the intellectual property of @WTF_Phantom.
# You are not allowed to copy, modify, redistribute, or use this
# code for commercial or personal projects without explicit permission.
# Contact for permissions:
# Email: king25258069@gmail.com

from pymongo import ASCENDING, MongoClient
import asyncio
import certifi
import os
from kazumi.config import BALANCE_LOG_RETENTION_DAYS, MONGO_URI


async def run_db(func, *args, **kwargs):
    """Run a blocking PyMongo call in a thread pool to avoid blocking the event loop.

    Usage:
        doc = await run_db(collection.find_one, {"user_id": 123})
        await run_db(collection.update_one, {"user_id": 123}, {"$set": {"name": "x"}})
    """
    return await asyncio.to_thread(func, *args, **kwargs)

# Initialize Connection with Enterprise Connection Pooling
KazumiMongo = MongoClient(
    MONGO_URI,
    tlsCAFile=certifi.where(),
    maxPoolSize=50,
    minPoolSize=2,
    maxIdleTimeMS=30000,
    connectTimeoutMS=10000,
    socketTimeoutMS=45000,
    serverSelectionTimeoutMS=10000,
    retryWrites=True,
    retryReads=True,
)
db = KazumiMongo[os.environ.get("DB_NAME", "kazumi_db")]

# --- DEFINING COLLECTIONS ---
users_collection = db["users"]       # Stores balance, inventory, waifus, stats
groups_collection = db["groups"]     # Tracks group settings (welcome, claim status)
sudoers_collection = db["sudoers"]   # Stores admin IDs
chatbot_collection = db["chatbot"]   # Stores AI chat history per group/user
riddles_collection = db["riddles"]   # Stores active riddles and answers
couples_collection = db["couples"]   # Stores daily couple of the day
loans_collection = db["loans"]       # Tracks pending and active player loans
missions_collection = db["missions"] # Tracks daily mission progress
user_memories_collection = db["user_memories"] # Stores capped personal memory facts
balance_logs_collection = db["balance_logs"] # Stores wallet history / transaction logs
admin_audit_logs_collection = db["admin_audit_logs"] # Stores admin-only audit trail for panel actions
premium_payments_collection = db["premium_payments"] # Tracks OxaPay/manual premium orders
waifu_drops_collection = db["waifu_drops"] # Active timed waifu drops, survives bot restarts
gacha_messages_collection = db["gacha_messages"] # Group gacha cards waiting for auto-delete
afk_collection = db["afk"]         # Users who marked themselves away
trivia_sessions_collection = db["trivia_sessions"] # Active group trivia questions
karma_collection = db["karma"]     # Group reputation totals
karma_votes_collection = db["karma_votes"] # Karma vote cooldown records
stars_purchases_collection = db["stars_purchases"] # Audit log for every Telegram Stars purchase
active_games_collection = db["active_games"]       # Active in-chat games state persistence & restart recovery


def ensure_indexes():
    """Create useful indexes without failing startup if Mongo rejects one."""
    index_specs = [
        (users_collection, [("user_id", ASCENDING)], {"unique": True}),
        (users_collection, [("username", ASCENDING)], {}),
        (users_collection, [("balance", -1)], {}),
        (users_collection, [("kills", -1)], {}),
        (users_collection, [("game_wins", -1)], {}),
        (users_collection, [("last_active_at", ASCENDING)], {}),
        (users_collection, [("protection_expiry", ASCENDING)], {}),
        (groups_collection, [("chat_id", ASCENDING)], {"unique": True}),
        (groups_collection, [("last_active_at", ASCENDING)], {}),
        (sudoers_collection, [("user_id", ASCENDING)], {"unique": True}),
        (loans_collection, [("request_id", ASCENDING)], {"unique": True}),
        (loans_collection, [("borrower_id", ASCENDING), ("status", ASCENDING)], {}),
        (loans_collection, [("lender_id", ASCENDING), ("status", ASCENDING)], {}),
        (missions_collection, [("user_id", ASCENDING), ("date", ASCENDING)], {"unique": True}),
        (user_memories_collection, [("user_id", ASCENDING)], {"unique": True}),
        (balance_logs_collection, [("user_id", ASCENDING), ("created_at", ASCENDING)], {}),
        (balance_logs_collection, [("category", ASCENDING), ("created_at", ASCENDING)], {}),
        (balance_logs_collection, [("target_user_id", ASCENDING), ("created_at", ASCENDING)], {}),
        (admin_audit_logs_collection, [("target_user_id", ASCENDING), ("created_at", ASCENDING)], {}),
        (admin_audit_logs_collection, [("admin_user_id", ASCENDING), ("created_at", ASCENDING)], {}),
        (admin_audit_logs_collection, [("action", ASCENDING), ("created_at", ASCENDING)], {}),
        (premium_payments_collection, [("order_id", ASCENDING)], {"unique": True}),
        (premium_payments_collection, [("track_id", ASCENDING)], {"unique": True, "partialFilterExpression": {"track_id": {"$type": "string"}}}),
        (premium_payments_collection, [("user_id", ASCENDING), ("created_at", ASCENDING)], {}),
        (premium_payments_collection, [("status", ASCENDING), ("created_at", ASCENDING)], {}),
        (waifu_drops_collection, [("chat_id", ASCENDING), ("message_id", ASCENDING)], {"unique": True}),
        (waifu_drops_collection, [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),
        (gacha_messages_collection, [("chat_id", ASCENDING), ("message_id", ASCENDING)], {"unique": True}),
        (gacha_messages_collection, [("expires_at", ASCENDING)], {}),
        (afk_collection, [("user_id", ASCENDING)], {"unique": True}),
        (afk_collection, [("username", ASCENDING)], {}),
        (afk_collection, [("since", ASCENDING)], {}),
        (trivia_sessions_collection, [("chat_id", ASCENDING)], {"unique": True}),
        (trivia_sessions_collection, [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),
        (karma_collection, [("chat_id", ASCENDING), ("user_id", ASCENDING)], {"unique": True}),
        (karma_collection, [("chat_id", ASCENDING), ("score", ASCENDING)], {}),
        (karma_votes_collection, [("chat_id", ASCENDING), ("voter_id", ASCENDING), ("target_id", ASCENDING)], {"unique": True}),
        (karma_votes_collection, [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),
        (db["gangs"], [("name_lc", ASCENDING)], {"unique": True, "partialFilterExpression": {"name_lc": {"$type": "string"}}}),
        (db["gangs"], [("members", ASCENDING)], {}),
        (db["gang_wars"], [("status", ASCENDING), ("expires_at", ASCENDING)], {}),
        (db["gang_wars"], [("challenger_id", ASCENDING), ("status", ASCENDING)], {}),
        (db["gang_wars"], [("target_id", ASCENDING), ("status", ASCENDING)], {}),
        (db["stars_purchases"], [("user_id", ASCENDING), ("purchased_at", ASCENDING)], {}),
        (db["stars_purchases"], [("payload", ASCENDING), ("purchased_at", ASCENDING)], {}),
        (
            db["stars_purchases"],
            [("telegram_payment_charge_id", ASCENDING)],
            {
                "unique": True,
                "partialFilterExpression": {"telegram_payment_charge_id": {"$type": "string"}},
            },
        ),
        (db["active_games"], [("user_id", ASCENDING)], {}),
        (db["active_games"], [("game_key", ASCENDING)], {"unique": True, "partialFilterExpression": {"game_key": {"$type": "string"}}}),
        (db["active_games"], [("created_at", ASCENDING)], {"expireAfterSeconds": 600}),  # Auto-purge games after 10 mins
    ]
    if BALANCE_LOG_RETENTION_DAYS:
        index_specs.append(
            (
                balance_logs_collection,
                [("created_at", ASCENDING)],
                {
                    "name": "balance_logs_retention",
                    "expireAfterSeconds": BALANCE_LOG_RETENTION_DAYS * 24 * 60 * 60,
                },
            )
        )
    for collection, keys, options in index_specs:
        try:
            collection.create_index(keys, background=True, **options)
        except Exception as exc:
            print(f"[DB INDEX WARNING] {collection.name} {keys}: {exc}", flush=True)
