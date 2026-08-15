# Copyright (c) 2025 Telegram:- @WTF_Phantom <DevixOP>
# Location: Supaul, Bihar 
#
# All rights reserved.
#
# This code is the intellectual property of @WTF_Phantom.
# You are not allowed to copy, modify, redistribute, or use this
# code for commercial or personal projects without explicit permission.
#
# Allowed:
# - Forking for personal learning
# - Submitting improvements via pull requests
#
# Not Allowed:
# - Claiming this code as your own
# - Re-uploading without credit or permission
# - Selling or using commercially
#
# Contact for permissions:
# Email: king25258069@gmail.com

import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut, NetworkError
from kazumi.utils import SUDO_USERS
from kazumi.database import users_collection, groups_collection


def _target_collection(target_type):
    return users_collection if target_type == "user" else groups_collection


def _target_key(target_type):
    return "user_id" if target_type == "user" else "chat_id"


def _mark_unreachable(target_type, cid, reason):
    col = _target_collection(target_type)
    key = _target_key(target_type)
    col.update_one(
        {key: cid},
        {
            "$set": {
                "bot_blocked": True,
                "broadcast_unreachable_at": datetime.utcnow(),
                "broadcast_unreachable_reason": reason[:120],
            },
            "$inc": {"broadcast_fail_count": 1},
        },
    )


def _mark_reachable(target_type, cid):
    col = _target_collection(target_type)
    key = _target_key(target_type)
    col.update_one(
        {key: cid},
        {
            "$set": {
                "bot_blocked": False,
                "last_broadcast_ok_at": datetime.utcnow(),
            },
            "$unset": {
                "broadcast_unreachable_reason": "",
            },
        },
    )


def _is_unreachable_error(exc):
    text = str(exc).lower()
    markers = (
        "bot was blocked",
        "bot can't initiate conversation",
        "chat not found",
        "user is deactivated",
        "have no rights",
        "not enough rights",
        "kicked",
        "forbidden",
    )
    return any(marker in text for marker in markers)


def _is_pin_permission_error(exc):
    text = str(exc).lower()
    return any(marker in text for marker in ("not enough rights", "have no rights", "pin messages", "not an administrator"))


async def _deliver_reply_broadcast(reply, chat_id, *, clean, pin, bot):
    """Copy/forward one source post and optionally pin the delivered copy."""
    if clean:
        delivered = await reply.copy(chat_id, reply_markup=reply.reply_markup)
    else:
        delivered = await reply.forward(chat_id)

    if not pin:
        return delivered, False

    try:
        await bot.pin_chat_message(
            chat_id=chat_id,
            message_id=delivered.message_id,
            disable_notification=True,
        )
        return delivered, True
    except (BadRequest, Forbidden) as exc:
        if _is_pin_permission_error(exc):
            return delivered, False
        raise


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS: return
    
    args = context.args
    reply = update.message.reply_to_message
    
    if not args and not reply:
        return await update.message.reply_text(
            "📢 <b>𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐌𝐚𝐧𝐚𝐠𝐞𝐫</b>\n\n"
            "<b>Usage:</b>\n"
            "‣ /broadcast -user (Reply to msg)\n"
            "‣ /broadcast -group (Reply to msg)\n\n"
            "<b>Flags:</b>\n"
            "‣ -clean : Copy msg (Use for Buttons)",
            parse_mode=ParseMode.HTML
        )
    
    is_all = "-all" in args
    target_type = "all" if is_all else "user" if "-user" in args else "group" if "-group" in args else None
    if not target_type:
        return await update.message.reply_text("⚠️ Missing flag: <code>-user</code>, <code>-group</code> or <code>-all</code>", parse_mode=ParseMode.HTML)

    is_clean = "-clean" in args
    should_pin = "-pin" in args
    
    msg_text = None
    if not reply:
        clean_args = [a for a in args if a not in ["-user", "-group", "-all", "-clean", "-pin"]]
        if not clean_args: return await update.message.reply_text("⚠️ Give me a message or reply to one.", parse_mode=ParseMode.HTML)
        msg_text = " ".join(clean_args)

    target_types = ["user", "group"] if target_type == "all" else [target_type]
    status_msg = await update.message.reply_text(f"⏳ <b>Broadcasting to {target_type}...</b>", parse_mode=ParseMode.HTML)

    total_sent = 0
    total_attempted = 0
    total_skipped_blocked = 0
    total_newly_blocked = 0
    total_failed = 0
    total_pinned = 0
    total_pin_skipped = 0

    for current_type in target_types:
        col = _target_collection(current_type)
        key = _target_key(current_type)
        skipped_blocked = col.count_documents({"bot_blocked": True})
        total_skipped_blocked += skipped_blocked
        targets = col.find({"bot_blocked": {"$ne": True}, key: {"$exists": True}})
        
        for doc in targets:
            cid = doc.get(key)
            if not cid:
                continue
            total_attempted += 1
            try:
                if reply:
                    _, was_pinned = await _deliver_reply_broadcast(
                        reply,
                        cid,
                        clean=is_clean,
                        pin=should_pin and current_type == "group",
                        bot=context.bot,
                    )
                    if should_pin and current_type == "group":
                        if was_pinned:
                            total_pinned += 1
                        else:
                            total_pin_skipped += 1
                else:
                    await context.bot.send_message(chat_id=cid, text=msg_text, parse_mode=ParseMode.HTML)
                
                total_sent += 1
                _mark_reachable(current_type, cid)
                if current_type == "group":
                    await asyncio.sleep(1.1)
                else:
                    await asyncio.sleep(0.08)
            except RetryAfter as exc:
                await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
                total_failed += 1
            except Forbidden as exc:
                _mark_unreachable(current_type, cid, str(exc))
                total_newly_blocked += 1
            except (BadRequest, TimedOut, NetworkError) as exc:
                if isinstance(exc, BadRequest) and _is_unreachable_error(exc):
                    _mark_unreachable(current_type, cid, str(exc))
                    total_newly_blocked += 1
                else:
                    total_failed += 1
            except Exception:
                total_failed += 1
        
    pin_summary = ""
    if should_pin:
        pin_summary = f"<b>Pinned:</b> <code>{total_pinned}</code>\n<b>Pin skipped:</b> <code>{total_pin_skipped}</code>\n"

    await status_msg.edit_text(
        "✅ <b>Broadcast Complete!</b>\n"
        f"<b>Sent:</b> <code>{total_sent}</code> targets ({target_type})\n"
        f"<b>Attempted:</b> <code>{total_attempted}</code>\n"
        f"<b>Skipped blocked:</b> <code>{total_skipped_blocked}</code>\n"
        f"<b>New blocked:</b> <code>{total_newly_blocked}</code>\n"
        f"<b>Failed:</b> <code>{total_failed}</code>\n"
        f"{pin_summary}\n"
        "<i>Blocked users/groups are safely saved in DB.</i>",
        parse_mode=ParseMode.HTML,
    )


async def pinall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return

    reply = update.message.reply_to_message
    if not reply:
        return await update.message.reply_text(
            "📌 <b>Usage:</b> Reply to a message with <code>/pinall</code>",
            parse_mode=ParseMode.HTML,
        )

    skipped_blocked = users_collection.count_documents({"bot_blocked": True})
    targets = users_collection.find({"bot_blocked": {"$ne": True}, "user_id": {"$exists": True}})
    status_msg = await update.message.reply_text("📌 <b>Pinning message for users...</b>", parse_mode=ParseMode.HTML)
    attempted = sent = pinned = newly_blocked = failed = 0

    for doc in targets:
        cid = doc.get("user_id")
        if not cid:
            continue
        attempted += 1
        try:
            copied = await reply.copy(cid)
            sent += 1
            await context.bot.pin_chat_message(chat_id=cid, message_id=copied.message_id, disable_notification=True)
            pinned += 1
            _mark_reachable("user", cid)
            if pinned % 20 == 0:
                await asyncio.sleep(1)
        except RetryAfter as exc:
            await asyncio.sleep(int(getattr(exc, "retry_after", 3)) + 1)
            failed += 1
        except Forbidden as exc:
            _mark_unreachable("user", cid, str(exc))
            newly_blocked += 1
        except (BadRequest, TimedOut, NetworkError) as exc:
            if isinstance(exc, BadRequest) and _is_unreachable_error(exc):
                _mark_unreachable("user", cid, str(exc))
                newly_blocked += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        "✅ <b>Pin All Complete!</b>\n"
        f"<b>Sent:</b> <code>{sent}</code>\n"
        f"<b>Pinned:</b> <code>{pinned}</code>\n"
        f"<b>Attempted:</b> <code>{attempted}</code>\n"
        f"<b>Skipped blocked:</b> <code>{skipped_blocked}</code>\n"
        f"<b>New blocked:</b> <code>{newly_blocked}</code>\n"
        f"<b>Failed:</b> <code>{failed}</code>",
        parse_mode=ParseMode.HTML,
    )


async def unpinall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in SUDO_USERS:
        return

    targets = users_collection.find({"bot_blocked": {"$ne": True}, "user_id": {"$exists": True}})
    status_msg = await update.message.reply_text("📍 <b>Unpinning latest pinned message for users...</b>", parse_mode=ParseMode.HTML)
    attempted = done = failed = 0

    for doc in targets:
        cid = doc.get("user_id")
        if not cid:
            continue
        attempted += 1
        try:
            await context.bot.unpin_chat_message(chat_id=cid)
            done += 1
            if done % 30 == 0:
                await asyncio.sleep(1)
        except Exception:
            failed += 1

    await status_msg.edit_text(
        "✅ <b>Unpin All Complete!</b>\n"
        f"<b>Done:</b> <code>{done}</code>\n"
        f"<b>Attempted:</b> <code>{attempted}</code>\n"
        f"<b>Failed:</b> <code>{failed}</code>",
        parse_mode=ParseMode.HTML,
    )

