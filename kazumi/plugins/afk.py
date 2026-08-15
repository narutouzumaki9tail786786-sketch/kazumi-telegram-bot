import time
import html
import random
from datetime import datetime

from telegram import MessageEntity, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from kazumi.database import afk_collection, run_db
from kazumi.utils import apply_custom_emojis, custom_emoji_html, ensure_user_exists, get_mention, stylize_text


AFK_NOTICE_COOLDOWN = 90
MAX_AFK_NOTICES_PER_MESSAGE = 3
_AFK_NOTICE_LAST = {}

AFK_SET_LINES = (
    "Kazumi will guard your spot. Come back before the chat gets too dramatic.",
    "Away mode on. I will pretend you are doing something important.",
    "I know you are reading... fine, I will cover for you.",
)
AFK_NOTICE_LINES = (
    "is away from keyboard right now.",
    "is with their crush right now.",
    "left chat on pause for a bit.",
)
AFK_BACK_LINES = (
    "Welcome back, {mention}. Did the outside world lose already?",
    "Ara, {mention} returned. Chat can breathe again.",
    "Welcome back, {mention}. I kept your place warm.",
)


def _html_text(text):
    return apply_custom_emojis(str(text or ""))


def _utf16_to_py_index(text, utf16_offset):
    units = 0
    for idx, char in enumerate(text):
        if units >= utf16_offset:
            return idx
        units += 2 if ord(char) > 0xFFFF else 1
    return len(text)


def _reason_from_message(message, args):
    fallback = " ".join(args).strip() or "No reason"
    raw_text = message.text or ""
    if not raw_text or not args:
        safe = html.escape(fallback[:160])
        return fallback[:160], _html_text(safe)

    parts = raw_text.split(maxsplit=1)
    if len(parts) < 2:
        safe = html.escape(fallback[:160])
        return fallback[:160], _html_text(safe)

    reason = parts[1].strip()[:160] or "No reason"
    start = raw_text.find(reason, len(parts[0]))
    if start < 0:
        safe = html.escape(reason)
        return reason, _html_text(safe)

    end = start + len(reason)
    custom_spans = []
    for entity in message.entities or []:
        if entity.type != MessageEntity.CUSTOM_EMOJI or not getattr(entity, "custom_emoji_id", None):
            continue
        entity_start = _utf16_to_py_index(raw_text, entity.offset)
        entity_end = _utf16_to_py_index(raw_text, entity.offset + entity.length)
        if entity_start >= end or entity_end <= start:
            continue
        custom_spans.append((max(entity_start, start) - start, min(entity_end, end) - start, entity.custom_emoji_id))

    custom_spans.sort()
    reason_text = raw_text[start:end]
    output = []
    cursor = 0
    for span_start, span_end, emoji_id in custom_spans:
        if span_start < cursor:
            continue
        output.append(html.escape(reason_text[cursor:span_start]))
        output.append(custom_emoji_html(emoji_id, reason_text[span_start:span_end]))
        cursor = span_end
    output.append(html.escape(reason_text[cursor:]))
    return reason, _html_text("".join(output))


def _duration_text(since):
    if not since:
        return "a while"
    seconds = max(1, int((datetime.utcnow() - since).total_seconds()))
    if seconds < 60:
        return f"{seconds} seconds"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def _cooldown_ok(chat_id, user_id):
    key = (int(chat_id), int(user_id))
    now = time.time()
    if now - _AFK_NOTICE_LAST.get(key, 0) < AFK_NOTICE_COOLDOWN:
        return False
    _AFK_NOTICE_LAST[key] = now
    return True


async def afk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user or user.is_bot:
        return

    ensure_user_exists(user)
    reason, reason_html = _reason_from_message(message, context.args)
    afk_collection.update_one(
        {"user_id": int(user.id)},
        {
            "$set": {
                "user_id": int(user.id),
                "username": user.username.lower() if user.username else None,
                "name": user.first_name,
                "reason": reason,
                "reason_html": reason_html,
                "since": datetime.utcnow(),
            }
        },
        upsert=True,
    )
    await message.reply_text(
        _html_text(
        f"\U0001F319 <b>{get_mention(user)} is now Away From Keyboard!</b>\n"
        f"<i>{html.escape(random.choice(AFK_SET_LINES))}</i>\n"
        f"<b>Reason:</b> {reason_html}"
        ),
        parse_mode=ParseMode.HTML,
    )


def _entity_targets(message, sender_id):
    targets = {}
    usernames = set()

    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user = message.reply_to_message.from_user
        if not replied_user.is_bot and replied_user.id != sender_id:
            targets[int(replied_user.id)] = None

    parsed = {}
    if message.text:
        try:
            parsed.update(message.parse_entities([MessageEntity.MENTION, MessageEntity.TEXT_MENTION]))
        except Exception:
            pass
    if message.caption:
        try:
            parsed.update(message.parse_caption_entities([MessageEntity.MENTION, MessageEntity.TEXT_MENTION]))
        except Exception:
            pass

    for entity, text in parsed.items():
        if entity.type == MessageEntity.TEXT_MENTION and entity.user:
            if not entity.user.is_bot and entity.user.id != sender_id:
                targets[int(entity.user.id)] = None
        elif entity.type == MessageEntity.MENTION:
            username = str(text or "").lstrip("@").lower().strip()
            if username:
                usernames.add(username)

    if usernames:
        for doc in afk_collection.find({"username": {"$in": list(usernames)}}):
            if int(doc.get("user_id", 0)) != int(sender_id):
                targets[int(doc["user_id"])] = doc

    return targets


async def afk_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or user.is_bot or not chat:
        return
    if message.text and message.text.startswith("/"):
        return

    sender_id = int(user.id)
    sender_afk = await run_db(afk_collection.find_one, {"user_id": sender_id})
    if sender_afk:
        await run_db(afk_collection.delete_one, {"user_id": sender_id})
        welcome = random.choice(AFK_BACK_LINES).format(mention=get_mention(user))
        await message.reply_text(
            _html_text(
            f"\U00002705 <b>{stylize_text('Welcome back')}</b>\n"
            f"{welcome}\n"
            f"You were AFK for <code>{_duration_text(sender_afk.get('since'))}</code>."
            ),
            parse_mode=ParseMode.HTML,
        )

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    target_ids = _entity_targets(message, sender_id)
    if not target_ids:
        return

    notices = []
    for target_id, cached_doc in target_ids.items():
        if len(notices) >= MAX_AFK_NOTICES_PER_MESSAGE:
            break
        doc = cached_doc or await run_db(afk_collection.find_one, {"user_id": int(target_id)})
        if not doc or not _cooldown_ok(chat.id, target_id):
            continue
        reason_html = doc.get("reason_html") or _html_text(html.escape(doc.get("reason") or "No reason"))
        notices.append(
            f"{get_mention(doc)} {html.escape(random.choice(AFK_NOTICE_LINES))}\n"
            f"<b>AFK for:</b> <code>{_duration_text(doc.get('since'))}</code>\n"
            f"<b>Reason:</b> {reason_html}"
        )

    if notices:
        await message.reply_text(
            _html_text("\U0001F319 <b>{}</b>\n".format(stylize_text("AFK Notice")) + "\n\n".join(notices)),
            parse_mode=ParseMode.HTML,
        )
