import asyncio
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pymongo import ReturnDocument

from kazumi.database import balance_logs_collection, users_collection


UTC = timezone.utc
try:
    HISTORY_TIMEZONE = ZoneInfo(os.getenv("BOT_TIMEZONE", "Asia/Kolkata"))
except ZoneInfoNotFoundError:
    HISTORY_TIMEZONE = UTC


def _utc_now_naive():
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc_aware(value):
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_utc_iso(value):
    stamp = _as_utc_aware(value)
    if not stamp:
        return None
    return stamp.isoformat().replace("+00:00", "Z")


def format_history_time(value):
    stamp = _as_utc_aware(value)
    if not stamp:
        return "just now"
    return stamp.astimezone(HISTORY_TIMEZONE).strftime("%d %b %I:%M %p")


def _local_day_utc_start(now=None):
    stamp = _as_utc_aware(now) if now is not None else datetime.now(UTC)
    local = stamp.astimezone(HISTORY_TIMEZONE)
    local_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(UTC).replace(tzinfo=None)


def _normalize_text(value, fallback=""):
    text = str(value or fallback).strip()
    return text[:240]


def _serialize_meta(meta):
    if not isinstance(meta, dict):
        return {}
    cleaned = {}
    for key, value in meta.items():
        if isinstance(value, datetime):
            cleaned[key] = value.isoformat()
        elif isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned


def record_balance_log(
    user_id,
    delta,
    category,
    reason,
    old_balance,
    new_balance,
    *,
    chat_id=None,
    target_user_id=None,
    source=None,
    meta=None,
):
    entry = {
        "user_id": int(user_id),
        "delta": int(delta),
        "direction": "credit" if int(delta) >= 0 else "debit",
        "category": _normalize_text(category, "general").lower(),
        "reason": _normalize_text(reason, "Balance change"),
        "old_balance": int(old_balance),
        "new_balance": int(new_balance),
        "chat_id": int(chat_id) if chat_id is not None else None,
        "target_user_id": int(target_user_id) if target_user_id is not None else None,
        "source": _normalize_text(source or category, "system"),
        "meta": _serialize_meta(meta),
        "created_at": _utc_now_naive(),
    }
    balance_logs_collection.insert_one(entry)
    return entry


def adjust_user_balance(
    user_id,
    delta,
    category,
    reason,
    *,
    chat_id=None,
    target_user_id=None,
    source=None,
    meta=None,
    require_gte=None,
    extra_query=None,
    extra_inc=None,
    extra_set=None,
    extra_push=None,
    extra_pull=None,
):
    query = {"user_id": int(user_id)}
    if require_gte is not None:
        query["balance"] = {"$gte": int(require_gte)}
    if extra_query:
        query.update(extra_query)

    update = {}
    inc_doc = dict(extra_inc or {})
    if int(delta) != 0:
        inc_doc["balance"] = inc_doc.get("balance", 0) + int(delta)
    if inc_doc:
        update["$inc"] = inc_doc
    if extra_set:
        update["$set"] = dict(extra_set)
    if extra_push:
        update["$push"] = dict(extra_push)
    if extra_pull:
        update["$pull"] = dict(extra_pull)
    if not update:
        return None

    before = users_collection.find_one_and_update(
        query,
        update,
        return_document=ReturnDocument.BEFORE,
    )
    if not before:
        return None

    old_balance = int(before.get("balance", 0))
    new_balance = old_balance + int(delta)
    try:
        from kazumi.utils import invalidate_user_cache
        invalidate_user_cache(before["user_id"])
    except Exception:
        pass

    entry = record_balance_log(
        before["user_id"],
        delta,
        category,
        reason,
        old_balance,
        new_balance,
        chat_id=chat_id,
        target_user_id=target_user_id,
        source=source,
        meta=meta,
    )
    return {"user": before, "old_balance": old_balance, "new_balance": new_balance, "entry": entry}


def transfer_user_balance(
    sender_id,
    receiver_id,
    amount,
    *,
    debit_category,
    debit_reason,
    credit_category,
    credit_reason,
    refund_category="transfer_refund",
    refund_reason="Transfer delivery failed",
    chat_id=None,
    source=None,
    meta=None,
):
    amount = int(amount)
    if amount <= 0:
        return None

    debit = adjust_user_balance(
        sender_id,
        -amount,
        debit_category,
        debit_reason,
        chat_id=chat_id,
        target_user_id=receiver_id,
        source=source,
        meta=meta,
        require_gte=amount,
    )
    if not debit:
        return None

    credit = adjust_user_balance(
        receiver_id,
        amount,
        credit_category,
        credit_reason,
        chat_id=chat_id,
        target_user_id=sender_id,
        source=source,
        meta=meta,
    )
    if credit:
        return {"debit": debit, "credit": credit}

    refund_meta = dict(meta or {})
    refund_meta["delivery_failed"] = True
    adjust_user_balance(
        sender_id,
        amount,
        refund_category,
        refund_reason,
        chat_id=chat_id,
        target_user_id=receiver_id,
        source=source,
        meta=refund_meta,
    )
    return None


def get_balance_history(user_id, *, limit=20, category=None, direction=None):
    query = {"user_id": int(user_id)}
    if category:
        query["category"] = str(category).strip().lower()
    if direction in {"credit", "debit"}:
        query["direction"] = direction
    return list(balance_logs_collection.find(query).sort("created_at", -1).limit(max(1, min(int(limit), 100))))


def balance_summary(user_id):
    start = _local_day_utc_start()
    rows = list(
        balance_logs_collection.find({"user_id": int(user_id), "created_at": {"$gte": start}})
        .sort("created_at", -1)
        .limit(500)
    )
    earned = sum(int(row.get("delta", 0)) for row in rows if int(row.get("delta", 0)) > 0)
    spent = sum(abs(int(row.get("delta", 0))) for row in rows if int(row.get("delta", 0)) < 0)
    biggest_win = max([int(row.get("delta", 0)) for row in rows if int(row.get("delta", 0)) > 0], default=0)
    biggest_loss = max([abs(int(row.get("delta", 0))) for row in rows if int(row.get("delta", 0)) < 0], default=0)
    return {
        "earned": earned,
        "spent": spent,
        "net": earned - spent,
        "biggestWin": biggest_win,
        "biggestLoss": biggest_loss,
        "count": len(rows),
    }


def positive_credit_total_today(user_id, *, categories):
    category_list = [str(category).strip().lower() for category in categories if str(category).strip()]
    if not category_list:
        return 0
    start = _local_day_utc_start()
    rows = balance_logs_collection.aggregate([
        {
            "$match": {
                "user_id": int(user_id),
                "category": {"$in": category_list},
                "delta": {"$gt": 0},
                "created_at": {"$gte": start},
            }
        },
        {"$group": {"_id": None, "total": {"$sum": "$delta"}}},
    ])
    row = next(iter(rows), None)
    return int((row or {}).get("total", 0))


async def async_adjust_user_balance(user_id, delta, category, reason, **kwargs):
    """Non-blocking version of adjust_user_balance — runs DB I/O in a thread."""
    return await asyncio.to_thread(
        adjust_user_balance, user_id, delta, category, reason, **kwargs
    )
