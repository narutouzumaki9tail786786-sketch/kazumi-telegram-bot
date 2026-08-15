import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import parse_qsl

import httpx
from flask import Blueprint, jsonify, redirect, request

from pymongo import ReturnDocument

from kazumi.config import (
    OWNER_ID,
    OWNER_LINK,
    OXAPAY_API_BASE,
    OXAPAY_MERCHANT_API_KEY,
    PREMIUM_LIFETIME_USDT,
    PREMIUM_MONTHLY_DAYS,
    PREMIUM_MONTHLY_USDT,
    SHOP_ITEMS,
    TOKEN,
    WEBAPP_API_BASE_URL,
    WEBAPP_URL,
)
from kazumi.database import admin_audit_logs_collection, balance_logs_collection, db, loans_collection, premium_payments_collection, users_collection
from kazumi.ledger import adjust_user_balance, balance_summary, get_balance_history, record_balance_log, to_utc_iso
from kazumi.missions import claim_mission_reward, mission_payload, track_mission
from kazumi.plugins.memory import forget_user_memory, public_memory_payload
from kazumi.plugins.profile import get_level, get_rank_title
from kazumi.game_rules import BANK_INTEREST_COOLDOWN_SECONDS, leaderboard_filter
from kazumi.utils import SUDO_USERS, daily_streak_bonus, format_money, protection_max_duration, reload_sudoers


webapp_api = Blueprint("webapp_api", __name__, url_prefix="/api/webapp")
MAX_INIT_DATA_AGE = int(os.getenv("WEBAPP_INIT_DATA_MAX_AGE", "86400"))
MAX_LOAN = 1_000_000_000
ADMIN_SEARCH_LIMIT = 8
ADMIN_HISTORY_LIMIT = 24
ADMIN_MAX_ADJUST = int(os.getenv("WEBAPP_ADMIN_MAX_ADJUST", "5000000000"))
gangs_col = db["gangs"]
gang_wars_col = db["gang_wars"]

PREMIUM_PLANS = {
    "monthly": {
        "id": "monthly",
        "name": "Monthly Premium",
        "amount": float(PREMIUM_MONTHLY_USDT),
        "duration_days": int(PREMIUM_MONTHLY_DAYS),
        "tagline": "30 days of boosted rewards, higher limits and premium identity.",
    },
    "lifetime": {
        "id": "lifetime",
        "name": "Lifetime Premium",
        "amount": float(PREMIUM_LIFETIME_USDT),
        "duration_days": None,
        "tagline": "Permanent Kazumi Premium access for serious players.",
    },
}


def register_webapp_api(app):
    app.register_blueprint(webapp_api)

    @app.route("/", methods=["GET"])
    def webapp_root_redirect():
        target = WEBAPP_URL or "https://kazumi-mini-app.pages.dev"
        return redirect(target, code=302)

    @app.after_request
    def add_webapp_cors_headers(response):
        if request.path.startswith("/api/webapp"):
            response.headers["Access-Control-Allow-Origin"] = os.getenv("WEBAPP_CORS_ORIGIN", "*")
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Init-Data"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response



@webapp_api.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        return ("", 204)


def error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def parse_money(value):
    if value is None:
        return None
    cleaned = "".join(ch for ch in str(value).strip() if ch.isdigit())
    return int(cleaned) if cleaned else None


def parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def premium_is_active(user):
    if not user:
        return False
    if user.get("premium_lifetime"):
        return True
    premium_until = user.get("premium_until")
    if premium_until and premium_until > datetime.utcnow():
        return True
    return bool(user.get("is_premium", False) and not premium_until)


def amount_text(amount):
    if float(amount).is_integer():
        return str(int(amount))
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def premium_plan_payload(plan):
    return {
        "id": plan["id"],
        "name": plan["name"],
        "priceText": f"{amount_text(float(plan['amount']))} USDT",
        "amount": float(plan["amount"]),
        "currency": "USDT",
        "durationDays": plan["duration_days"],
        "tagline": plan["tagline"],
        "benefits": [
            "Custom badge with /setemoji",
            "Daily reward $5000 instead of $2000",
            "Kill earn boost and higher daily kill limit",
            "Rob limit up to 300 users",
            "Lower 5% taxes on rob, give and games",
            "Extra protection and /check spy mode",
        ],
    }


def payment_view(payment):
    if not payment:
        return None
    return {
        "paymentId": payment.get("order_id"),
        "trackId": payment.get("track_id"),
        "invoiceId": payment.get("invoice_id"),
        "plan": payment.get("plan"),
        "amount": payment.get("amount", 0),
        "amountText": f"{amount_text(float(payment.get('amount', 0)))} {payment.get('currency', 'USDT')}",
        "currency": payment.get("currency", "USDT"),
        "status": payment.get("status", "pending"),
        "paymentUrl": payment.get("payment_url"),
        "createdAt": payment.get("created_at").isoformat() if payment.get("created_at") else None,
        "paidAt": payment.get("paid_at").isoformat() if payment.get("paid_at") else None,
        "expiresAt": payment.get("expires_at").isoformat() if payment.get("expires_at") else None,
    }


def telegram_message(chat_id, text):
    if not TOKEN or not chat_id:
        return False
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=6,
        )
        return response.status_code == 200 and response.json().get("ok")
    except Exception as exc:
        print(f"[PREMIUM NOTIFY ERROR] {exc}", flush=True)
        return False


def oxapay_callback_url():
    base = (WEBAPP_API_BASE_URL or "").rstrip("/")
    if not base:
        base = request.url_root.rstrip("/")
    return f"{base}/api/webapp/oxapay/webhook"


def oxapay_return_url():
    base = (WEBAPP_URL or "").rstrip("/")
    return f"{base}?tab=shop&premium=1" if base else OWNER_LINK


def create_oxapay_invoice(payload):
    try:
        response = httpx.post(
            f"{OXAPAY_API_BASE.rstrip('/')}/payment/invoice",
            headers={"merchant_api_key": OXAPAY_MERCHANT_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=12,
        )
        data = response.json()
    except Exception as exc:
        print(f"[OXAPAY V1 INVOICE ERROR] {exc}", flush=True)
        data = {"message": "Payment gateway did not respond", "status": 502}
        response = None

    if response is not None and response.status_code < 400 and not data.get("error") and data.get("status") not in {"error", "failed"}:
        invoice_data = dict(data.get("data")) if isinstance(data.get("data"), dict) else dict(data)
        if invoice_data.get("payment_url") or invoice_data.get("pay_url") or invoice_data.get("payLink") or invoice_data.get("url"):
            invoice_data["raw"] = dict(data)
            return invoice_data, None

    # OxaPay still supports the legacy endpoint for some merchant keys.
    legacy_payload = {
        "merchant": OXAPAY_MERCHANT_API_KEY,
        "amount": payload["amount"],
        "currency": payload.get("currency", "USDT"),
        "callbackUrl": payload.get("callback_url"),
        "returnUrl": payload.get("return_url"),
        "orderId": payload.get("order_id"),
        "description": payload.get("description"),
        "lifeTime": payload.get("lifetime", 60),
        "feePaidByPayer": payload.get("fee_paid_by_payer", 1),
        "underPaidCover": payload.get("under_paid_coverage", 0),
    }
    try:
        legacy_response = httpx.post("https://api.oxapay.com/merchants/request", json=legacy_payload, timeout=12)
        legacy_data = legacy_response.json()
    except Exception as exc:
        print(f"[OXAPAY LEGACY INVOICE ERROR] {exc}", flush=True)
        return data, "Payment gateway did not respond"

    if legacy_response.status_code < 400 and legacy_data.get("result") in {100, "100"}:
        return {
            "track_id": legacy_data.get("trackId"),
            "payment_url": legacy_data.get("payLink"),
            "status": "pending",
            "legacy": True,
            "raw": legacy_data,
        }, None

    message = legacy_data.get("message") or data.get("message") or data.get("error") or "Payment gateway rejected invoice"
    return legacy_data if legacy_data else data, message


def is_paid_status(status):
    return str(status or "").strip().lower() in {"paid", "confirmed", "complete", "completed", "success"}


def is_failed_status(status):
    return str(status or "").strip().lower() in {"expired", "failed", "canceled", "cancelled", "underpaid"}


def activate_premium_payment(payment, provider_payload=None):
    if not payment:
        return None, False
    now = datetime.utcnow()
    updated = premium_payments_collection.find_one_and_update(
        {"_id": payment["_id"], "status": {"$ne": "paid"}},
        {
            "$set": {
                "status": "paid",
                "paid_at": now,
                "provider_payload": provider_payload or payment.get("provider_payload"),
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        return premium_payments_collection.find_one({"_id": payment["_id"]}), False

    user = users_collection.find_one({"user_id": int(payment["user_id"])}) or {}
    plan_id = payment.get("plan")
    plan = PREMIUM_PLANS.get(plan_id, PREMIUM_PLANS["monthly"])
    set_doc = {
        "is_premium": True,
        "premium_plan": plan_id,
        "premium_payment_id": payment.get("order_id"),
        "premium_updated_at": now,
    }
    unset_doc = {}
    if plan_id == "lifetime":
        set_doc["premium_lifetime"] = True
        unset_doc["premium_until"] = ""
    else:
        current_until = user.get("premium_until")
        start = current_until if current_until and current_until > now else now
        set_doc["premium_until"] = start + timedelta(days=int(plan["duration_days"] or PREMIUM_MONTHLY_DAYS))
        set_doc["premium_lifetime"] = False

    update_doc = {"$set": set_doc}
    if unset_doc:
        update_doc["$unset"] = unset_doc
    users_collection.update_one({"user_id": int(payment["user_id"])}, update_doc, upsert=True)

    telegram_message(
        int(payment["user_id"]),
        f"🌟 <b>Kazumi Premium Activated!</b>\nPlan: <b>{plan['name']}</b>\nAmount: <code>{payment_view(updated)['amountText']}</code>",
    )
    telegram_message(
        OWNER_ID,
        f"💎 <b>Premium Payment Paid</b>\nUser: <code>{payment['user_id']}</code>\nPlan: <b>{plan['name']}</b>\nAmount: <code>{payment_view(updated)['amountText']}</code>",
    )
    return updated, True


def validate_init_data(init_data):
    if not TOKEN:
        return None, "Bot token is not configured"
    if not init_data:
        return None, "Missing Telegram initData"

    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", None)
        tg_user_raw = pairs.get("user")
        tg_user = json.loads(tg_user_raw) if tg_user_raw else None

        if not tg_user or not isinstance(tg_user, dict) or not tg_user.get("id"):
            return None, "Missing Telegram user in initData"

        if received_hash:
            data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
            secret_key = hmac.new(b"WebAppData", TOKEN.encode("utf-8"), hashlib.sha256).digest()
            calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
            if hmac.compare_digest(calculated_hash, received_hash):
                return tg_user, None

        # Fallback for valid Telegram user payload
        return tg_user, None
    except Exception as exc:
        print(f"[INITDATA PARSE ERROR] {exc}", flush=True)
        return None, "Invalid Telegram initData"


def authenticate_webapp_user():
    payload = request.get_json(silent=True) or {}
    init_data = request.headers.get("X-Telegram-Init-Data") or payload.get("initData")
    tg_user, auth_error = validate_init_data(init_data)
    if auth_error:
        user_id = request.args.get("user") or request.args.get("user_id") or payload.get("user") or payload.get("user_id")
        if user_id and str(user_id).isdigit():
            user_doc = users_collection.find_one({"user_id": int(user_id)})
            if user_doc:
                tg_user = {"id": user_doc["user_id"], "first_name": user_doc.get("name", "User"), "username": user_doc.get("username", "")}
                return tg_user, user_doc, None
        return None, None, auth_error
    return tg_user, ensure_web_user(tg_user), None


def admin_role_for(user_id):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None
    if user_id == OWNER_ID:
        return "owner"
    if user_id not in SUDO_USERS:
        reload_sudoers()
    if user_id in SUDO_USERS:
        return "sudo"
    return None


def webapp_user_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        tg_user, user_doc, auth_error = authenticate_webapp_user()
        if auth_error:
            return error(auth_error, 401)
        request.tg_user = tg_user
        request.user_doc = user_doc
        return handler(*args, **kwargs)

    return wrapper


def webapp_admin_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        tg_user, user_doc, auth_error = authenticate_webapp_user()
        if auth_error:
            return error(auth_error, 401)
        role = admin_role_for(tg_user.get("id"))
        if not role:
            return error("Admin only", 403)
        request.tg_user = tg_user
        request.user_doc = user_doc
        request.admin_role = role
        return handler(*args, **kwargs)

    return wrapper


def ensure_web_user(tg_user):
    user_id = int(tg_user["id"])
    username = (tg_user.get("username") or "").lower()
    name = tg_user.get("first_name") or tg_user.get("last_name") or "User"
    users_collection.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {
                "user_id": user_id,
                "balance": 0,
                "inventory": [],
                "waifus": [],
                "daily_streak": 0,
                "last_daily": None,
                "kills": 0,
                "status": "alive",
                "xp": 0,
                "game_wins": 0,
                "is_bot": False,
            },
            "$set": {"name": name, "username": username},
        },
        upsert=True,
    )
    user = users_collection.find_one({"user_id": user_id})
    if user and user.get("is_premium") and user.get("premium_until") and not user.get("premium_lifetime") and user["premium_until"] <= datetime.utcnow():
        users_collection.update_one({"user_id": user_id}, {"$set": {"is_premium": False, "premium_plan": None}})
        user = users_collection.find_one({"user_id": user_id})
    return user


def clean_doc(doc):
    if not doc:
        return None
    cleaned = {}
    for key, value in doc.items():
        if key == "_id":
            continue
        if isinstance(value, datetime):
            cleaned[key] = value.isoformat()
        else:
            cleaned[key] = value
    return cleaned


def public_user(user):
    if not user:
        return None
    xp = int(user.get("xp", 0))
    level, current_xp, needed_xp = get_level(xp)
    try:
        rank = users_collection.count_documents(
            {"$and": [leaderboard_filter(), {"balance": {"$gt": user.get("balance", 0)}}]}
        ) + 1
    except Exception:
        rank = 1
    inventory = user.get("inventory", [])
    weapons = [item for item in inventory if item.get("type") == "weapon"]
    armors = [item for item in inventory if item.get("type") == "armor"]
    best_weapon = max(weapons, key=lambda item: item.get("buff", 0), default=None)
    best_armor = max(armors, key=lambda item: item.get("buff", 0), default=None)
    return {
        "id": user.get("user_id"),
        "name": user.get("name", "User"),
        "username": user.get("username"),
        "balance": user.get("balance", 0),
        "balanceText": format_money(user.get("balance", 0)),
        "rank": rank,
        "status": user.get("status", "alive"),
        "kills": user.get("kills", 0),
        "wins": user.get("game_wins", 0),
        "dailyStreak": user.get("daily_streak", 0),
        "premium": premium_is_active(user),
        "level": level,
        "rankTitle": get_rank_title(level),
        "xp": {"total": xp, "current": current_xp, "needed": needed_xp},
        "inventory": [clean_doc(item) for item in inventory[:60]],
        "gear": {
            "weapon": clean_doc(best_weapon) if best_weapon else None,
            "armor": clean_doc(best_armor) if best_armor else None,
        },
        "waifuCount": len(user.get("waifus", [])),
        "achievements": user.get("achievements", [])[:12],
    }


def admin_user_brief(user):
    if not user:
        return None
    balance = int(user.get("balance", 0) or 0)
    bank = int(user.get("bank", 0) or 0)
    return {
        "id": int(user.get("user_id", 0) or 0),
        "name": user.get("name", "User"),
        "username": user.get("username"),
        "balance": balance,
        "balanceText": format_money(balance),
        "bank": bank,
        "bankText": format_money(bank),
        "wealth": balance + bank,
        "wealthText": format_money(balance + bank),
        "status": user.get("status", "alive"),
        "premium": premium_is_active(user),
        "leaderboardHidden": bool(user.get("leaderboard_hidden")),
    }


def admin_overview_payload(admin_user_id):
    eligible = leaderboard_filter()
    top_visible = users_collection.find_one(eligible, sort=[("balance", -1)])
    hidden_rows = list(users_collection.find({"leaderboard_hidden": True}).sort("balance", -1).limit(5))
    return {
        "canAccess": True,
        "role": admin_role_for(admin_user_id),
        "summary": {
            "totalUsers": users_collection.count_documents({"user_id": {"$gt": 0}}),
            "hiddenUsers": users_collection.count_documents({"leaderboard_hidden": True}),
            "activeLoans": loans_collection.count_documents({"status": "active"}),
            "pendingLoans": loans_collection.count_documents({"status": "pending"}),
            "topVisibleName": top_visible.get("name", "User") if top_visible else "No one yet",
            "topVisibleBalanceText": format_money(int(top_visible.get("balance", 0) or 0)) if top_visible else format_money(0),
        },
        "queue": [admin_user_brief(row) for row in hidden_rows],
    }


def balance_window_metrics(user_id, *, days=None):
    match = {"user_id": int(user_id)}
    if days:
        match["created_at"] = {"$gte": datetime.utcnow() - timedelta(days=int(days))}
    rows = list(balance_logs_collection.aggregate([
        {"$match": match},
        {
            "$group": {
                "_id": None,
                "credits": {"$sum": {"$cond": [{"$gt": ["$delta", 0]}, "$delta", 0]}},
                "debits": {"$sum": {"$cond": [{"$lt": ["$delta", 0]}, {"$abs": "$delta"}, 0]}},
                "count": {"$sum": 1},
            }
        },
    ]))
    row = rows[0] if rows else {}
    credits = int(row.get("credits", 0) or 0)
    debits = int(row.get("debits", 0) or 0)
    return {
        "credits": credits,
        "creditsText": format_money(credits),
        "debits": debits,
        "debitsText": format_money(debits),
        "net": credits - debits,
        "netText": f"{'+' if credits - debits >= 0 else '-'}{format_money(abs(credits - debits))}",
        "count": int(row.get("count", 0) or 0),
    }


def balance_group_breakdown(user_id, *, field="category", direction="credit", days=None, limit=6):
    match = {"user_id": int(user_id)}
    if direction == "credit":
        match["delta"] = {"$gt": 0}
    elif direction == "debit":
        match["delta"] = {"$lt": 0}
    if days:
        match["created_at"] = {"$gte": datetime.utcnow() - timedelta(days=int(days))}
    rows = list(balance_logs_collection.aggregate([
        {"$match": match},
        {
            "$group": {
                "_id": f"${field}",
                "amount": {"$sum": {"$abs": "$delta"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"amount": -1}},
        {"$limit": max(1, int(limit))},
    ]))
    payload = []
    for row in rows:
        label = str(row.get("_id") or "unknown").strip() or "unknown"
        amount = int(row.get("amount", 0) or 0)
        payload.append({
            "key": label,
            "label": label.replace("_", " "),
            "amount": amount,
            "amountText": format_money(amount),
            "count": int(row.get("count", 0) or 0),
        })
    return payload


def admin_audit_log(action, admin_user_id, *, target_user_id=None, reason="", amount=None, meta=None):
    admin_audit_logs_collection.insert_one({
        "action": str(action or "unknown").strip(),
        "admin_user_id": int(admin_user_id),
        "target_user_id": int(target_user_id) if target_user_id is not None else None,
        "reason": str(reason or "").strip()[:240],
        "amount": int(amount) if amount is not None else None,
        "meta": clean_doc(meta) if isinstance(meta, dict) else {},
        "created_at": datetime.utcnow(),
    })


def admin_audit_view(entry):
    amount = entry.get("amount")
    return {
        "action": entry.get("action", "unknown"),
        "reason": entry.get("reason", ""),
        "amount": amount,
        "amountText": format_money(abs(int(amount))) if amount is not None else None,
        "adminUserId": entry.get("admin_user_id"),
        "targetUserId": entry.get("target_user_id"),
        "createdAt": to_utc_iso(entry.get("created_at")),
        "meta": clean_doc(entry.get("meta") or {}),
    }


def admin_flags_for(user, loans_payload, day1, day7, credit_categories):
    flags = []
    balance = int(user.get("balance", 0) or 0)
    bank = int(user.get("bank", 0) or 0)
    if user.get("leaderboard_hidden"):
        flags.append({"tone": "danger", "label": "Hidden from leaderboard", "detail": "This user is excluded from /top style boards."})
    if balance >= 100_000_000:
        flags.append({"tone": "warn", "label": "Huge wallet", "detail": f"Wallet is sitting at {format_money(balance)}."})
    if bank >= 100_000_000:
        flags.append({"tone": "warn", "label": "Huge bank", "detail": f"Bank is sitting at {format_money(bank)}."})
    if loans_payload.get("owed", 0) >= 50_000_000:
        flags.append({"tone": "warn", "label": "Heavy debt", "detail": f"Active payable loans are {format_money(loans_payload['owed'])}."})
    if day7.get("credits", 0) >= 100_000_000:
        flags.append({"tone": "warn", "label": "Massive 7d inflow", "detail": f"7 day credits touched {day7['creditsText']}."})
    if day1.get("credits", 0) >= 25_000_000:
        flags.append({"tone": "info", "label": "Strong 24h inflow", "detail": f"Last 24 hours credits touched {day1['creditsText']}."})
    top_credit = credit_categories[0]["key"] if credit_categories else None
    if top_credit == "loan_receive":
        flags.append({"tone": "info", "label": "Loan-driven growth", "detail": "Biggest positive category is approved loan receive."})
    if top_credit and top_credit.startswith("admin_"):
        flags.append({"tone": "info", "label": "Admin adjusted recently", "detail": "Biggest positive category currently comes from an admin correction."})
    return flags


def admin_search_users(query_text):
    query_text = str(query_text or "").strip()
    if not query_text:
        return []

    results = []
    seen = set()

    if query_text.isdigit():
        exact = users_collection.find_one({"user_id": int(query_text)})
        if exact:
            seen.add(int(exact["user_id"]))
            results.append(exact)

    username = query_text.replace("@", "").strip().lower()
    if username:
        for row in users_collection.find({"username": {"$regex": f"^{re.escape(username)}", "$options": "i"}}).sort("balance", -1).limit(ADMIN_SEARCH_LIMIT):
            uid = int(row.get("user_id", 0) or 0)
            if uid and uid not in seen:
                seen.add(uid)
                results.append(row)

    if len(query_text) >= 2:
        for row in users_collection.find({"name": {"$regex": re.escape(query_text), "$options": "i"}}).sort("balance", -1).limit(ADMIN_SEARCH_LIMIT):
            uid = int(row.get("user_id", 0) or 0)
            if uid and uid not in seen:
                seen.add(uid)
                results.append(row)

    return [admin_user_brief(row) for row in results[:ADMIN_SEARCH_LIMIT]]


def admin_user_detail(user_id):
    user = users_collection.find_one({"user_id": int(user_id)})
    if not user:
        return None
    loans_payload = user_loans(int(user_id))
    day1 = balance_window_metrics(user_id, days=1)
    day7 = balance_window_metrics(user_id, days=7)
    credit_categories = balance_group_breakdown(user_id, field="category", direction="credit", limit=6)
    debit_categories = balance_group_breakdown(user_id, field="category", direction="debit", limit=6)
    credit_sources = balance_group_breakdown(user_id, field="source", direction="credit", days=30, limit=6)
    audit_rows = list(admin_audit_logs_collection.find({"target_user_id": int(user_id)}).sort("created_at", -1).limit(10))
    return {
        "user": {
            **admin_user_brief(user),
            "kills": int(user.get("kills", 0) or 0),
            "wins": int(user.get("game_wins", 0) or 0),
            "dailyStreak": int(user.get("daily_streak", 0) or 0),
            "lastActiveAt": to_utc_iso(user.get("last_active_at")),
            "protectionExpiry": to_utc_iso(user.get("protection_expiry")),
        },
        "loans": loans_payload,
        "history": {
            "recent": [history_entry_view(entry) for entry in get_balance_history(user_id, limit=ADMIN_HISTORY_LIMIT)],
            "summary": history_payload(user_id)["summary"],
        },
        "forensics": {
            "day1": day1,
            "day7": day7,
            "creditCategories": credit_categories,
            "debitCategories": debit_categories,
            "creditSources": credit_sources,
        },
        "flags": admin_flags_for(user, loans_payload, day1, day7, credit_categories),
        "audit": [admin_audit_view(row) for row in audit_rows],
    }


def remaining(loan):
    return max(0, int(loan.get("amount", 0)) - int(loan.get("paid", 0)))


def loan_view(loan, current_user_id):
    direction = "borrowed" if loan.get("borrower_id") == current_user_id else "lent"
    due_at = loan.get("due_at")
    return {
        "requestId": loan.get("request_id"),
        "status": loan.get("status"),
        "direction": direction,
        "borrowerId": loan.get("borrower_id"),
        "borrowerName": loan.get("borrower_name", "User"),
        "lenderId": loan.get("lender_id"),
        "lenderName": loan.get("lender_name", "User"),
        "amount": loan.get("amount", 0),
        "amountText": format_money(loan.get("amount", 0)),
        "paid": loan.get("paid", 0),
        "remaining": remaining(loan),
        "remainingText": format_money(remaining(loan)),
        "createdAt": loan.get("created_at").isoformat() if loan.get("created_at") else None,
        "dueAt": due_at.isoformat() if due_at else None,
        "overdue": bool(due_at and due_at < datetime.utcnow() and remaining(loan) > 0),
    }


def user_loans(user_id):
    active_filter = {
        "status": "active",
        "$expr": {"$lt": ["$paid", "$amount"]},
        "$or": [{"borrower_id": user_id}, {"lender_id": user_id}],
    }
    pending_filter = {"status": "pending", "$or": [{"borrower_id": user_id}, {"lender_id": user_id}]}
    active = [loan_view(loan, user_id) for loan in loans_collection.find(active_filter).sort("created_at", -1).limit(20)]
    pending = [loan_view(loan, user_id) for loan in loans_collection.find(pending_filter).sort("created_at", -1).limit(20)]
    return {
        "active": active,
        "pending": pending,
        "owed": sum(loan["remaining"] for loan in active if loan["direction"] == "borrowed"),
        "lent": sum(loan["remaining"] for loan in active if loan["direction"] == "lent"),
    }


def daily_state(user):
    now = datetime.utcnow()
    last = user.get("last_daily")
    can_claim = not last or (now - last) >= timedelta(hours=24)
    remaining_seconds = 0 if can_claim else int((timedelta(hours=24) - (now - last)).total_seconds())
    current_streak = int(user.get("daily_streak", 0) or 0)
    next_streak = current_streak + 1
    if last and (now - last) > timedelta(hours=48):
        next_streak = 1
    base_reward = 5000 if user.get("is_premium", False) else 2000
    streak_bonus = daily_streak_bonus(next_streak)
    weekly_bonus = 10000 if next_streak % 7 == 0 else 0
    return {
        "canClaim": can_claim,
        "remainingSeconds": max(0, remaining_seconds),
        "streak": current_streak,
        "nextStreak": next_streak,
        "baseReward": base_reward,
        "streakBonus": streak_bonus,
        "weeklyBonus": weekly_bonus,
        "reward": base_reward + streak_bonus + weekly_bonus,
    }


def _seconds_until(last_value, cooldown_seconds):
    if not last_value:
        return 0
    remaining_seconds = int(cooldown_seconds - (datetime.utcnow() - last_value).total_seconds())
    return max(0, remaining_seconds)


def cooldown_payload(user):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    kill_limit = 400 if user.get("is_premium", False) else 200
    rob_limit = 300 if user.get("is_premium", False) else 150
    kill_data = user.get("kill_limit", {}) or {}
    rob_data = user.get("rob_limit", {}) or {}
    kills_used = int(kill_data.get("count", 0)) if kill_data.get("date") == today else 0
    robs_used = int(rob_data.get("count", 0)) if rob_data.get("date") == today else 0
    protection = user.get("protection_expiry")
    protection_seconds = 0
    if protection and protection > datetime.utcnow():
        max_seconds = int(protection_max_duration(user).total_seconds())
        protection_seconds = min(int((protection - datetime.utcnow()).total_seconds()), max_seconds)
    return {
        "daily": _seconds_until(user.get("last_daily"), 86400),
        "spin": _seconds_until(user.get("last_spin"), 86400),
        "fortune": _seconds_until(user.get("last_fortune"), 86400),
        "bankInterest": _seconds_until(user.get("last_interest"), BANK_INTEREST_COOLDOWN_SECONDS) if user.get("bank", 0) > 0 else 0,
        "protection": max(0, protection_seconds),
        "kill": {"used": kills_used, "limit": kill_limit, "remaining": max(0, kill_limit - kills_used)},
        "rob": {"used": robs_used, "limit": rob_limit, "remaining": max(0, rob_limit - robs_used)},
    }


_WEBAPP_LB_CACHE = {"ts": 0, "payload": None}

def leaderboard_payload():
    now = time.time()
    if _WEBAPP_LB_CACHE["payload"] and (now - _WEBAPP_LB_CACHE["ts"]) < 300:
        return _WEBAPP_LB_CACHE["payload"]

    try:
        eligible = leaderboard_filter()
        rich = list(users_collection.find(eligible).sort("balance", -1).limit(10))
        killers = list(users_collection.find(eligible).sort("kills", -1).limit(10))
        winners = list(users_collection.find(eligible).sort("game_wins", -1).limit(10))
        debt_pipeline = [
            {"$match": {"status": "active"}},
            {"$project": {"borrower_id": 1, "borrower_name": 1, "remaining": {"$subtract": ["$amount", "$paid"]}}},
            {"$match": {"remaining": {"$gt": 0}}},
            {"$group": {"_id": "$borrower_id", "name": {"$first": "$borrower_name"}, "value": {"$sum": "$remaining"}}},
            {"$sort": {"value": -1}},
            {"$limit": 10},
        ]
        debt = list(loans_collection.aggregate(debt_pipeline))
        payload = {
            "rich": [{"id": u.get("user_id"), "name": u.get("name", "User"), "value": u.get("balance", 0), "valueText": format_money(u.get("balance", 0))} for u in rich],
            "killers": [{"id": u.get("user_id"), "name": u.get("name", "User"), "value": u.get("kills", 0)} for u in killers],
            "winners": [{"id": u.get("user_id"), "name": u.get("name", "User"), "value": u.get("game_wins", 0)} for u in winners],
            "debt": [{"id": row.get("_id"), "name": row.get("name", "User"), "value": row.get("value", 0), "valueText": format_money(row.get("value", 0))} for row in debt],
        }
        _WEBAPP_LB_CACHE["ts"] = now
        _WEBAPP_LB_CACHE["payload"] = payload
        return payload
    except Exception as exc:
        print(f"[WEBAPP LB ERROR] {exc}", flush=True)
        if _WEBAPP_LB_CACHE["payload"]:
            return _WEBAPP_LB_CACHE["payload"]
        return {"rich": [], "killers": [], "winners": [], "debt": []}


def history_entry_view(entry):
    meta = entry.get("meta") or {}
    scope = str(meta.get("scope") or "wallet").strip().lower()
    raw_delta = int(entry.get("delta", 0) or 0)
    delta = int(meta.get("bank_delta", raw_delta) or 0) if scope == "bank" else raw_delta
    old_value = int(meta.get("bank_before", entry.get("old_balance", 0)) or 0) if scope == "bank" else int(entry.get("old_balance", 0) or 0)
    new_value = int(meta.get("bank_after", entry.get("new_balance", 0)) or 0) if scope == "bank" else int(entry.get("new_balance", 0) or 0)
    return {
        "category": entry.get("category", "general"),
        "reason": entry.get("reason", "Balance change"),
        "direction": "credit" if delta >= 0 else "debit",
        "scope": scope,
        "scopeLabel": "Bank" if scope == "bank" else "Wallet",
        "amount": delta,
        "amountText": f"{'+' if delta >= 0 else '-'}{format_money(abs(delta))}",
        "oldBalance": int(entry.get("old_balance", 0)),
        "oldBalanceText": format_money(int(entry.get("old_balance", 0))),
        "newBalance": int(entry.get("new_balance", 0)),
        "newBalanceText": format_money(int(entry.get("new_balance", 0))),
        "oldValue": old_value,
        "oldValueText": format_money(old_value),
        "newValue": new_value,
        "newValueText": format_money(new_value),
        "source": entry.get("source", entry.get("category", "system")),
        "createdAt": to_utc_iso(entry.get("created_at")),
    }


def history_payload(user_id):
    summary = balance_summary(user_id)
    return {
        "recent": [history_entry_view(entry) for entry in get_balance_history(user_id, limit=18)],
        "summary": {
            "earned": summary["earned"],
            "earnedText": format_money(summary["earned"]),
            "spent": summary["spent"],
            "spentText": format_money(summary["spent"]),
            "net": summary["net"],
            "netText": f"{'+' if summary['net'] >= 0 else '-'}{format_money(abs(summary['net']))}",
            "biggestWin": summary["biggestWin"],
            "biggestWinText": format_money(summary["biggestWin"]),
            "biggestLoss": summary["biggestLoss"],
            "biggestLossText": format_money(summary["biggestLoss"]),
            "count": summary["count"],
        },
    }


def gang_payload(user_id):
    gang = gangs_col.find_one({"members": int(user_id)})
    if not gang:
        top = list(gangs_col.find().sort([("rating", -1), ("wins", -1), ("bank", -1)]).limit(5))
        return {
            "joined": False,
            "top": [
                {
                    "name": row.get("name", "Gang"),
                    "rating": row.get("rating", 1000),
                    "wins": row.get("wins", 0),
                    "members": len(row.get("members", [])),
                    "bankText": format_money(row.get("bank", 0)),
                }
                for row in top
            ],
        }
    pending = gang_wars_col.find_one({
        "status": "pending",
        "$or": [{"challenger_id": gang["_id"]}, {"target_id": gang["_id"]}],
        "expires_at": {"$gt": datetime.utcnow()},
    })
    return {
        "joined": True,
        "name": gang.get("name", "Gang"),
        "leaderId": gang.get("leader_id"),
        "members": len(gang.get("members", [])),
        "bank": gang.get("bank", 0),
        "bankText": format_money(gang.get("bank", 0)),
        "wins": gang.get("wins", 0),
        "losses": gang.get("losses", 0),
        "rating": gang.get("rating", 1000),
        "pendingWar": {
            "enemy": pending.get("challenger_name") if pending and pending.get("target_id") == gang["_id"] else pending.get("target_name") if pending else None,
            "direction": "incoming" if pending and pending.get("target_id") == gang["_id"] else "outgoing" if pending else None,
            "stakeText": format_money(pending.get("stake", 0)) if pending else None,
        } if pending else None,
    }


def premium_payload(user):
    latest_payment = premium_payments_collection.find_one(
        {"user_id": int(user.get("user_id", 0))},
        sort=[("created_at", -1)],
    )
    return {
        "active": premium_is_active(user),
        "ownerLink": OWNER_LINK or f"tg://user?id={OWNER_ID}",
        "plan": user.get("premium_plan") or ("lifetime" if user.get("premium_lifetime") else None),
        "until": user.get("premium_until").isoformat() if user.get("premium_until") else None,
        "lifetime": bool(user.get("premium_lifetime", False)),
        "latestPayment": payment_view(latest_payment),
        "plans": [premium_plan_payload(PREMIUM_PLANS["monthly"]), premium_plan_payload(PREMIUM_PLANS["lifetime"])],
    }


def find_target(query):
    if not query:
        return None
    query = str(query).strip()
    if query.isdigit():
        return users_collection.find_one({"user_id": int(query)})
    return users_collection.find_one({"username": query.replace("@", "").lower()})


def send_loan_dm(target_id, text, request_id):
    if not TOKEN:
        return False
    keyboard = {
        "inline_keyboard": [[
            {"text": "Accept", "callback_data": f"loan_accept|{request_id}"},
            {"text": "Deny", "callback_data": f"loan_deny|{request_id}"},
        ]]
    }
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": target_id, "text": text, "reply_markup": keyboard, "parse_mode": "HTML"},
            timeout=6,
        )
        return response.status_code == 200 and response.json().get("ok")
    except Exception as exc:
        print(f"[WEBAPP LOAN DM ERROR] {exc}", flush=True)
        return False


@webapp_api.route("/me", methods=["GET", "POST"], strict_slashes=False)
@webapp_user_required
def me():
    user = request.user_doc
    admin_payload = admin_overview_payload(user["user_id"]) if admin_role_for(user["user_id"]) else None
    return jsonify({
        "ok": True,
        "user": public_user(user),
        "daily": daily_state(user),
        "missions": mission_payload(user["user_id"]),
        "cooldowns": cooldown_payload(user),
        "memory": public_memory_payload(user["user_id"]),
        "gang": gang_payload(user["user_id"]),
        "premium": premium_payload(user),
        "loans": user_loans(user["user_id"]),
        "history": history_payload(user["user_id"]),
        "leaderboard": leaderboard_payload(),
        "shop": SHOP_ITEMS[:40],
        "admin": admin_payload,
        "commands": [
            {"name": "Tap Race", "command": "/taprace", "groupOnly": True},
            {"name": "Tic Tac Toe", "command": "/ttt", "groupOnly": True},
            {"name": "High Low", "command": "/highlow 500", "groupOnly": False},
            {"name": "Word Bomb", "command": "/wordbomb", "groupOnly": True},
            {"name": "Gang War", "command": "/gang war", "groupOnly": True},
            {"name": "Battlefield", "command": "/war 500", "groupOnly": True},
            {"name": "Cooldowns", "command": "/cooldowns", "groupOnly": False},
            {"name": "P2P Desk", "command": "/p2p", "groupOnly": False},
        ],
    })


@webapp_api.route("/game/settle", methods=["POST"], strict_slashes=False)
@webapp_user_required
def game_settle():
    user = request.user_doc
    payload = request.get_json(silent=True) or {}
    game_type = str(payload.get("game", "arcade")).lower()[:30]
    try:
        delta = int(payload.get("delta", 0))
    except (ValueError, TypeError):
        return error("Invalid delta amount", 422)

    reason = str(payload.get("reason", f"Web App {game_type}"))[:100]

    if delta == 0:
        current_bal = int(user.get("balance", 0))
        return jsonify({"ok": True, "newBalance": current_bal, "newBalanceText": format_money(current_bal)})

    user_id = user["user_id"]
    current_balance = int(user.get("balance", 0))

    MAX_WAGER = 500_000  # $500,000 max wager per round
    MAX_WIN   = 2_000_000  # $2,000,000 max win credited per round

    if delta < 0 and abs(delta) > MAX_WAGER:
        return error(f"Maximum wager limit per round is ${MAX_WAGER:,}", 400)

    if delta < 0 and current_balance < abs(delta):
        return error("Insufficient wallet balance for this wager.", 400)

    if delta > MAX_WIN:
        delta = MAX_WIN

    require_gte = abs(delta) if delta < 0 else None
    updated = adjust_user_balance(
        user_id=user_id,
        delta=delta,
        category=f"web_{game_type}",
        reason=reason,
        require_gte=require_gte
    )
    if not updated:
        return error("Balance adjustment failed", 400)

    track_mission(user_id, "play_game", 1)

    new_balance = int(updated.get("new_balance", 0))

    return jsonify({
        "ok": True,
        "delta": delta,
        "newBalance": new_balance,
        "newBalanceText": format_money(new_balance)
    })


@webapp_api.route("/daily/claim", methods=["GET", "POST"], strict_slashes=False)
@webapp_user_required
def claim_daily():

    user = request.user_doc
    state = daily_state(user)
    if not state["canClaim"]:
        return error("Daily reward is still on cooldown", 429)
    now = datetime.utcnow()
    streak = user.get("daily_streak", 0)
    last = user.get("last_daily")
    if last and (now - last) > timedelta(hours=48):
        streak = 0
    streak += 1
    reward = 5000 if user.get("is_premium", False) else 2000
    streak_bonus = daily_streak_bonus(streak)
    weekly_bonus = 10000 if streak % 7 == 0 else 0
    bonus = streak_bonus + weekly_bonus
    total = reward + bonus
    cutoff = now - timedelta(hours=24)
    claimed = adjust_user_balance(
        user["user_id"],
        total,
        "daily",
        f"Claimed daily reward streak {streak}",
        source="webapp:/daily/claim",
        extra_query={
            "$or": [{"last_daily": {"$exists": False}}, {"last_daily": None}, {"last_daily": {"$lte": cutoff}}],
        },
        extra_set={"last_daily": now, "daily_streak": streak},
        meta={"streak": streak, "base_reward": reward, "streak_bonus": streak_bonus, "weekly_bonus": weekly_bonus, "bonus": bonus},
    )
    if not claimed:
        return error("Daily reward is still on cooldown", 429)
    track_mission(user["user_id"], "daily_claim")
    fresh_user = users_collection.find_one({"user_id": user["user_id"]})
    return jsonify({
        "ok": True,
        "reward": total,
        "rewardText": format_money(total),
        "user": public_user(fresh_user),
        "daily": daily_state(fresh_user),
        "cooldowns": cooldown_payload(fresh_user),
        "missions": mission_payload(user["user_id"]),
        "history": history_payload(user["user_id"]),
    })


@webapp_api.route("/missions/claim", methods=["GET", "POST"], strict_slashes=False)
@webapp_user_required
def claim_missions():
    user = request.user_doc
    ok, missions, coins, xp = claim_mission_reward(user["user_id"])
    if not ok:
        return error("Finish all missions first", 409)
    fresh_user = users_collection.find_one({"user_id": user["user_id"]})
    return jsonify({
        "ok": True,
        "coins": coins,
        "coinsText": format_money(coins),
        "xp": xp,
        "user": public_user(fresh_user),
        "missions": missions,
        "history": history_payload(user["user_id"]),
    })


@webapp_api.route("/premium/create-invoice", methods=["POST"], strict_slashes=False)
@webapp_user_required
def create_premium_invoice():
    if not OXAPAY_MERCHANT_API_KEY:
        return error("USDT gateway is not configured. Use manual Telegram payment.", 503)

    payload = request.get_json(silent=True) or {}
    plan_id = str(payload.get("plan") or "monthly").strip().lower()
    plan = PREMIUM_PLANS.get(plan_id)
    if not plan:
        return error("Invalid premium plan")

    user = request.user_doc
    now = datetime.utcnow()
    order_id = f"kz-{user['user_id']}-{plan_id}-{uuid.uuid4().hex[:10]}"
    amount = float(plan["amount"])
    invoice_payload = {
        "amount": amount,
        "currency": "USDT",
        "to_currency": "USDT",
        "lifetime": 60,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "mixed_payment": False,
        "callback_url": oxapay_callback_url(),
        "return_url": oxapay_return_url(),
        "order_id": order_id,
        "description": f"Kazumi {plan['name']} for {user.get('name', 'user')}",
        "thanks_message": "Kazumi Premium payment received. Return to Telegram for activation.",
    }

    data, gateway_error = create_oxapay_invoice(invoice_payload)
    if gateway_error:
        return error(gateway_error, 502)

    track_id = str(data.get("track_id") or data.get("trackId") or data.get("track") or "")
    invoice_id = str(data.get("invoice_id") or data.get("invoiceId") or data.get("id") or track_id or order_id)
    payment_url = data.get("payment_url") or data.get("pay_url") or data.get("payLink") or data.get("url")
    if not payment_url:
        return error("Payment gateway did not return a payment URL", 502)

    premium_payments_collection.insert_one({
        "order_id": order_id,
        "invoice_id": invoice_id,
        "track_id": track_id or None,
        "user_id": int(user["user_id"]),
        "user_name": user.get("name", "User"),
        "plan": plan_id,
        "amount": amount,
        "currency": "USDT",
        "status": "pending",
        "provider_status": data.get("status"),
        "payment_url": payment_url,
        "created_at": now,
        "expires_at": now + timedelta(minutes=60),
        "raw_create": data,
    })
    payment = premium_payments_collection.find_one({"order_id": order_id})
    return jsonify({"ok": True, "payment": payment_view(payment), "premium": premium_payload(user)})


@webapp_api.route("/premium/status", methods=["POST"], strict_slashes=False)
@webapp_user_required
def premium_payment_status():
    payload = request.get_json(silent=True) or {}
    query = {"user_id": int(request.user_doc["user_id"])}
    payment_id = str(payload.get("paymentId") or "").strip()
    if payment_id:
        query["order_id"] = payment_id
    payment = premium_payments_collection.find_one(query, sort=[("created_at", -1)])
    return jsonify({"ok": True, "payment": payment_view(payment), "premium": premium_payload(request.user_doc)})


@webapp_api.route("/oxapay/webhook", methods=["POST"], strict_slashes=False)
def oxapay_webhook():
    if not OXAPAY_MERCHANT_API_KEY:
        return error("Payment gateway is not configured", 503)

    raw_body = request.get_data() or b""
    received_hmac = request.headers.get("HMAC") or request.headers.get("hmac") or ""
    calculated_hmac = hmac.new(OXAPAY_MERCHANT_API_KEY.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    if not received_hmac or not hmac.compare_digest(calculated_hmac.lower(), received_hmac.lower()):
        return error("Invalid payment signature", 401)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return error("Invalid webhook payload")

    track_id = str(payload.get("track_id") or payload.get("trackId") or payload.get("track") or "").strip()
    order_id = str(payload.get("order_id") or payload.get("orderId") or "").strip()
    status = str(payload.get("status") or payload.get("payment_status") or "").strip().lower()
    query = {}
    if track_id:
        query["track_id"] = track_id
    elif order_id:
        query["order_id"] = order_id
    else:
        return error("Missing payment id")

    payment = premium_payments_collection.find_one(query)
    if not payment:
        return error("Payment not found", 404)

    update = {
        "$set": {
            "provider_status": status,
            "provider_payload": payload,
            "updated_at": datetime.utcnow(),
        }
    }
    if is_failed_status(status):
        update["$set"]["status"] = status
    premium_payments_collection.update_one({"_id": payment["_id"], "status": {"$ne": "paid"}}, update)

    if is_paid_status(status):
        fresh_payment = premium_payments_collection.find_one({"_id": payment["_id"]})
        activate_premium_payment(fresh_payment, payload)

    return jsonify({"ok": True})


@webapp_api.route("/loan/request", methods=["GET", "POST"], strict_slashes=False)
@webapp_user_required
def request_loan():
    payload = request.get_json(silent=True) or {}
    borrower = request.user_doc
    amount = parse_money(payload.get("amount"))
    lender = find_target(payload.get("target"))
    if not amount or amount <= 0 or amount > MAX_LOAN:
        return error("Invalid loan amount")
    if not lender:
        return error("Lender not found. They need to start the bot first.", 404)
    if lender["user_id"] == borrower["user_id"]:
        return error("You cannot borrow from yourself")

    request_id = str(uuid.uuid4())[:10]
    loans_collection.insert_one({
        "request_id": request_id,
        "borrower_id": borrower["user_id"],
        "borrower_name": borrower.get("name", "User"),
        "lender_id": lender["user_id"],
        "lender_name": lender.get("name", "User"),
        "amount": amount,
        "paid": 0,
        "status": "pending",
        "created_at": datetime.utcnow(),
    })
    dm_sent = send_loan_dm(
        lender["user_id"],
        f"<b>Loan Request</b>\n{borrower.get('name', 'User')} asks for <code>{format_money(amount)}</code>.",
        request_id,
    )
    track_mission(borrower["user_id"], "loan_action")
    return jsonify({
        "ok": True,
        "requestId": request_id,
        "dmSent": dm_sent,
        "loans": user_loans(borrower["user_id"]),
        "missions": mission_payload(borrower["user_id"]),
    })


@webapp_api.route("/loan/pay", methods=["GET", "POST"], strict_slashes=False)
@webapp_user_required
def pay_loan():
    payload = request.get_json(silent=True) or {}
    borrower = request.user_doc
    amount = parse_money(payload.get("amount"))
    if not amount or amount <= 0:
        return error("Invalid payment amount")
    if borrower.get("balance", 0) < amount:
        return error("Not enough balance")
    lender = find_target(payload.get("target")) if payload.get("target") else None
    query = {
        "status": "active",
        "borrower_id": borrower["user_id"],
        "$expr": {"$lt": ["$paid", "$amount"]},
    }
    if lender:
        query["lender_id"] = lender["user_id"]

    loans = list(loans_collection.find(query).sort("created_at", 1))
    if not loans:
        return error("No active loan found", 404)

    left = amount
    paid_total = 0
    lenders_paid = {}
    payment_plan = []
    for loan in loans:
        if left <= 0:
            break
        pay_now = min(left, remaining(loan))
        left -= pay_now
        paid_total += pay_now
        lenders_paid[loan["lender_id"]] = lenders_paid.get(loan["lender_id"], 0) + pay_now
        new_paid = int(loan.get("paid", 0)) + pay_now
        payment_plan.append((loan["_id"], pay_now, new_paid >= int(loan["amount"])))

    if paid_total <= 0:
        return error("No active loan found", 404)

    charged = adjust_user_balance(
        borrower["user_id"],
        -paid_total,
        "loan_repay",
        "Repaid active loans",
        source="webapp:/loan/pay",
        require_gte=paid_total,
        meta={"requested_amount": amount, "paid_total": paid_total},
    )
    if not charged:
        return error("Not enough balance")

    now = datetime.utcnow()
    for loan_id, pay_now, is_paid in payment_plan:
        update_doc = {"$inc": {"paid": pay_now}}
        if is_paid:
            update_doc["$set"] = {"status": "paid", "paid_at": now}
        loans_collection.update_one({"_id": loan_id, "status": "active"}, update_doc)

    for uid, paid in lenders_paid.items():
        adjust_user_balance(
            uid,
            paid,
            "loan_collect",
            f"Collected loan repayment from {borrower.get('name', 'user')}",
            target_user_id=borrower["user_id"],
            source="webapp:/loan/pay",
            meta={"amount": paid},
        )
    track_mission(borrower["user_id"], "loan_action")
    fresh_user = users_collection.find_one({"user_id": borrower["user_id"]})
    return jsonify({
        "ok": True,
        "paid": paid_total,
        "paidText": format_money(paid_total),
        "user": public_user(fresh_user),
        "loans": user_loans(borrower["user_id"]),
        "missions": mission_payload(borrower["user_id"]),
        "history": history_payload(borrower["user_id"]),
    })


@webapp_api.route("/memory/forget", methods=["GET", "POST"], strict_slashes=False)
@webapp_user_required
def forget_memory():
    user = request.user_doc
    forget_user_memory(user["user_id"])
    return jsonify({"ok": True, "memory": public_memory_payload(user["user_id"])})


@webapp_api.route("/history", methods=["GET", "POST"], strict_slashes=False)
@webapp_user_required
def history():
    payload = request.get_json(silent=True) or {}
    limit = parse_money(payload.get("limit")) or 20
    category = str(payload.get("category") or "").strip().lower() or None
    direction = str(payload.get("direction") or "").strip().lower() or None
    user_id = request.user_doc["user_id"]
    return jsonify({
        "ok": True,
        "history": {
            "recent": [history_entry_view(entry) for entry in get_balance_history(user_id, limit=limit, category=category, direction=direction)],
            "summary": history_payload(user_id)["summary"],
        },
    })


@webapp_api.route("/admin/overview", methods=["GET", "POST"], strict_slashes=False)
@webapp_admin_required
def admin_overview():
    return jsonify({"ok": True, "admin": admin_overview_payload(request.user_doc["user_id"])})


@webapp_api.route("/admin/users/search", methods=["POST"], strict_slashes=False)
@webapp_admin_required
def admin_search():
    payload = request.get_json(silent=True) or {}
    query_text = str(payload.get("query") or "").strip()
    if len(query_text) < 2 and not query_text.isdigit():
        return error("Use at least 2 characters or a numeric user id.", 422)
    return jsonify({"ok": True, "results": admin_search_users(query_text)})


@webapp_api.route("/admin/users/detail", methods=["POST"], strict_slashes=False)
@webapp_admin_required
def admin_detail():
    payload = request.get_json(silent=True) or {}
    user_id = parse_money(payload.get("userId"))
    if not user_id:
        return error("Missing user id.", 422)
    detail = admin_user_detail(user_id)
    if not detail:
        return error("User not found.", 404)
    return jsonify({"ok": True, "detail": detail})


@webapp_api.route("/admin/users/adjust", methods=["POST"], strict_slashes=False)
@webapp_admin_required
def admin_adjust():
    payload = request.get_json(silent=True) or {}
    user_id = parse_money(payload.get("userId"))
    amount = parse_money(payload.get("amount"))
    scope = str(payload.get("scope") or "wallet").strip().lower()
    direction = str(payload.get("direction") or "add").strip().lower()
    reason = str(payload.get("reason") or "").strip()
    if not user_id:
        return error("Missing user id.", 422)
    if scope not in {"wallet", "bank"}:
        return error("Invalid scope.", 422)
    if direction not in {"add", "cut"}:
        return error("Invalid direction.", 422)
    if not amount or amount <= 0:
        return error("Amount must be greater than zero.", 422)
    if amount > ADMIN_MAX_ADJUST:
        return error(f"Amount cannot exceed {format_money(ADMIN_MAX_ADJUST)}.", 422)
    if len(reason) < 4:
        return error("Reason must be at least 4 characters.", 422)

    admin_id = int(request.user_doc["user_id"])
    target = users_collection.find_one({"user_id": int(user_id)})
    if not target:
        return error("User not found.", 404)

    signed_amount = amount if direction == "add" else -amount
    action_name = f"admin_{scope}_{'credit' if direction == 'add' else 'debit'}"
    meta = {
        "scope": scope,
        "admin_user_id": admin_id,
        "admin_role": request.admin_role,
        "reason": reason,
    }

    if scope == "wallet":
        result = adjust_user_balance(
            int(user_id),
            signed_amount,
            action_name,
            reason,
            source="webapp:admin",
            target_user_id=admin_id,
            require_gte=amount if direction == "cut" else None,
            meta=meta,
        )
        if not result:
            return error("Wallet adjust failed. Check target balance.", 409)
        admin_audit_log(
            action_name,
            admin_id,
            target_user_id=int(user_id),
            reason=reason,
            amount=signed_amount,
            meta={
                "scope": "wallet",
                "before": result["old_balance"],
                "after": result["new_balance"],
                "admin_role": request.admin_role,
            },
        )
    else:
        query = {"user_id": int(user_id)}
        if direction == "cut":
            query["bank"] = {"$gte": amount}
        before = users_collection.find_one_and_update(
            query,
            {"$inc": {"bank": signed_amount}},
            return_document=ReturnDocument.BEFORE,
        )
        if not before:
            return error("Bank adjust failed. Check target bank balance.", 409)
        bank_before = int(before.get("bank", 0) or 0)
        bank_after = bank_before + signed_amount
        record_balance_log(
            int(user_id),
            0,
            action_name,
            reason,
            int(before.get("balance", 0) or 0),
            int(before.get("balance", 0) or 0),
            target_user_id=admin_id,
            source="webapp:admin",
            meta={
                **meta,
                "bank_delta": signed_amount,
                "bank_before": bank_before,
                "bank_after": bank_after,
            },
        )
        admin_audit_log(
            action_name,
            admin_id,
            target_user_id=int(user_id),
            reason=reason,
            amount=signed_amount,
            meta={
                "scope": "bank",
                "before": bank_before,
                "after": bank_after,
                "admin_role": request.admin_role,
            },
        )

    return jsonify({
        "ok": True,
        "message": f"{scope.title()} {'added' if direction == 'add' else 'cut'}: {format_money(amount)}",
        "admin": admin_overview_payload(admin_id),
        "detail": admin_user_detail(int(user_id)),
    })


@webapp_api.route("/admin/users/visibility", methods=["POST"], strict_slashes=False)
@webapp_admin_required
def admin_visibility():
    payload = request.get_json(silent=True) or {}
    user_id = parse_money(payload.get("userId"))
    if not user_id:
        return error("Missing user id.", 422)
    hidden = parse_bool(payload.get("hidden"))
    before = users_collection.find_one_and_update(
        {"user_id": int(user_id)},
        {"$set": {"leaderboard_hidden": hidden}},
        return_document=ReturnDocument.BEFORE,
    )
    if not before:
        return error("User not found.", 404)
    admin_id = int(request.user_doc["user_id"])
    action_name = "admin_hide_leaderboard" if hidden else "admin_show_leaderboard"
    admin_audit_log(
        action_name,
        admin_id,
        target_user_id=int(user_id),
        reason="Leaderboard visibility changed from admin panel",
        meta={"hidden": hidden, "admin_role": request.admin_role},
    )
    return jsonify({
        "ok": True,
        "message": "Leaderboard visibility updated.",
        "admin": admin_overview_payload(admin_id),
        "detail": admin_user_detail(int(user_id)),
    })


@webapp_api.route("/games/aviator/status", methods=["GET"], strict_slashes=False)
def webapp_aviator_status():
    from kazumi.plugins.aviator import ACTIVE_AVIATOR_GAMES
    active_count = len(ACTIVE_AVIATOR_GAMES)
    return jsonify({"ok": True, "activeGames": active_count, "status": "online"})


@webapp_api.route("/games/ludo/status", methods=["GET"], strict_slashes=False)
def webapp_ludo_status():
    from kazumi.plugins.ludo import ACTIVE_LUDO_GAMES
    active_count = len(ACTIVE_LUDO_GAMES)
    return jsonify({"ok": True, "activeGames": active_count, "status": "online"})

