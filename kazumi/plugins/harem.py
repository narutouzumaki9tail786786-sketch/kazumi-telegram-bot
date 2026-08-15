import asyncio
import html
import random
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes
from kazumi.utils import ensure_user_exists, stylize_text, get_mention
from kazumi.database import gacha_messages_collection, users_collection
from kazumi.ledger import adjust_user_balance
from kazumi.config import GACHA_COST, DATE_COST, MAX_AFFECTION, GACHA_RATES

LEGACY_PLACEHOLDER_IMAGES = {
    "https://files.catbox.moe/gyi5iu.jpg",
    "https://files.catbox.moe/5g37fy.jpg",
}

# Rarity colors and emotes
RARITY_INFO = {
    "mythic": {"emote": "💖", "name": "Mythic", "bonus": 5},
    "legendary": {"emote": "💛", "name": "Legendary", "bonus": 4},
    "epic": {"emote": "💜", "name": "Epic", "bonus": 3},
    "rare": {"emote": "💙", "name": "Rare", "bonus": 2},
    "common": {"emote": "🤍", "name": "Common", "bonus": 1}
}
GROUP_GACHA_DELETE_SECONDS = 600
GROUP_IMAGE_DELETE_NOTICE = "<i>NSFW safety: group image auto-deletes in 10 minutes.</i>"


def _is_group_chat(chat) -> bool:
    return bool(chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


def _with_group_cleanup_notice(caption: str, chat) -> str:
    if _is_group_chat(chat):
        return f"{caption}\n{GROUP_IMAGE_DELETE_NOTICE}"
    return caption

async def fetch_waifu_data(nsfw=False):
    """Fetch a waifu image plus metadata and fall back if the API is unavailable."""
    params = {
        "IncludedTags": "waifu",
        "IsNsfw": "True" if nsfw else "False",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get("https://api.waifu.im/images", params=params, timeout=10.0)
            if resp.status_code == 200:
                items = resp.json().get("items") or []
                if items:
                    item = items[0]
                    tag_names = []
                    for tag in item.get("tags") or []:
                        if isinstance(tag, dict) and tag.get("name"):
                            tag_names.append(str(tag["name"]))
                        elif isinstance(tag, str):
                            tag_names.append(tag)

                    artist = item.get("artist")
                    if isinstance(artist, dict):
                        artist = artist.get("name") or artist.get("artist_id")

                    return {
                        "url": item.get("url"),
                        "source": item.get("source") or item.get("signature") or "Unknown",
                        "artist": artist or "Unknown",
                        "tags": tag_names[:5],
                        "width": item.get("width"),
                        "height": item.get("height"),
                        "is_nsfw": item.get("is_nsfw", nsfw),
                        "dominant_color": item.get("dominant_color"),
                    }
    except Exception as e:
        print(f"Error fetching waifu.im API: {e}")
    
    return {
        "url": None,
        "source": "Fallback",
        "artist": "Unknown",
        "tags": [],
        "width": None,
        "height": None,
        "is_nsfw": nsfw,
        "dominant_color": None,
    }

async def fetch_waifu_image(nsfw=False):
    data = await fetch_waifu_data(nsfw=nsfw)
    return data["url"]

def _mark_gacha_delete_failure(chat_id: int, message_id: int, error: Exception):
    now = datetime.utcnow()
    gacha_messages_collection.update_one(
        {"chat_id": chat_id, "message_id": message_id},
        {
            "$inc": {"delete_attempts": 1},
            "$set": {
                "last_delete_error": str(error)[:300],
                "last_delete_attempt_at": now,
                "next_delete_attempt_at": now + timedelta(minutes=5),
            },
        },
    )


def _cleanup_error_is_final(error: Exception) -> bool:
    text = str(error).lower()
    final_markers = (
        "message to delete not found",
        "message can't be deleted",
        "chat not found",
        "bot was kicked",
        "not enough rights",
        "forbidden",
    )
    return any(marker in text for marker in final_markers)


async def _delete_gacha_message(bot, chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        gacha_messages_collection.delete_one({"chat_id": chat_id, "message_id": message_id})
        return True
    except Exception as exc:
        if _cleanup_error_is_final(exc):
            gacha_messages_collection.delete_one({"chat_id": chat_id, "message_id": message_id})
            return True
        _mark_gacha_delete_failure(chat_id, message_id, exc)
        print(f"[GACHA CLEANUP ERROR] chat={chat_id} message={message_id}: {exc}", flush=True)
        return False


async def _delete_message_after(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = GROUP_GACHA_DELETE_SECONDS):
    try:
        await asyncio.sleep(delay)
        await _delete_gacha_message(context.bot, chat_id, message_id)
    except asyncio.CancelledError:
        return


async def gacha_cleanup_loop(bot, interval: int = 60):
    try:
        while True:
            now = datetime.utcnow()
            rows = list(
                gacha_messages_collection.find(
                    {
                        "expires_at": {"$lte": now},
                        "$or": [
                            {"next_delete_attempt_at": {"$exists": False}},
                            {"next_delete_attempt_at": {"$lte": now}},
                        ],
                    }
                ).limit(50)
            )
            for row in rows:
                await _delete_gacha_message(bot, row["chat_id"], row["message_id"])
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return


def remember_gacha_message(chat_id: int, message_id: int, user_id: int, is_nsfw: bool, kind: str = "gacha"):
    gacha_messages_collection.update_one(
        {"chat_id": chat_id, "message_id": message_id},
        {
            "$set": {
                "chat_id": chat_id,
                "message_id": message_id,
                "user_id": user_id,
                "is_nsfw": bool(is_nsfw),
                "kind": kind,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(seconds=GROUP_GACHA_DELETE_SECONDS),
            }
        },
        upsert=True,
    )


async def _track_group_harem_media(context: ContextTypes.DEFAULT_TYPE, chat, message, user_id: int, is_nsfw: bool, kind: str):
    if not _is_group_chat(chat) or not message:
        return
    remember_gacha_message(chat.id, message.message_id, user_id, is_nsfw, kind=kind)
    asyncio.create_task(_delete_message_after(context, chat.id, message.message_id))

def get_random_rarity():
    """Rolls for rarity based on defined rates."""
    rand = random.random()
    cumulative = 0.0
    for rarity, rate in GACHA_RATES.items():
        cumulative += rate
        if rand <= cumulative:
            return rarity
    return "common"

def generate_waifu_name():
    """Generates a random Japanese-style name."""
    first = ["Aki", "Hina", "Kazu", "Mio", "Rin", "Sakura", "Yuki", "Shiro", "Kuro", "Mai", "Sora", "Nana", "Yui"]
    last = ["ko", "mi", "no", "ka", "na", "ya", "shi", "ki", "ri"]
    return random.choice(first) + random.choice(last)

def _money(amount):
    return f"${int(amount):,}"

def _clean_name(value):
    return html.escape(str(value or "Unknown"))

def _find_harem_member(harem, query):
    query = str(query or "").strip().lower()
    for idx, member in enumerate(harem):
        name = str(member.get("name", "")).lower()
        if name == query:
            return idx, member
    return None, None

def _member_image(member):
    image = member.get("telegram_file_id") or member.get("image")
    if not image:
        return None
    if str(image).strip() in LEGACY_PLACEHOLDER_IMAGES:
        return None
    if member.get("source") in {"Fallback", "Unknown"} and not member.get("width") and not member.get("height"):
        return None
    return image

def _member_caption(member):
    rarity = member.get("rarity", "common")
    r_info = RARITY_INFO.get(rarity, RARITY_INFO["common"])
    tags = ", ".join(member.get("tags") or []) or "waifu"
    size = "unknown"
    if member.get("width") and member.get("height"):
        size = f"{member['width']}x{member['height']}"
    source = str(member.get("source") or "Unknown")
    if len(source) > 70:
        source = source[:67] + "..."

    return (
        f"📖 <b>Character Card</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 <b>Name:</b> {_clean_name(member.get('name'))}\n"
        f"💎 <b>Rarity:</b> {r_info['emote']} <b>{html.escape(r_info['name'])}</b>\n"
        f"💖 <b>Affection:</b> <code>{member.get('affection', 1)}/{MAX_AFFECTION}</code>\n"
        f"🧩 <b>Shards:</b> <code>{member.get('shards', 0)}</code>\n"
        f"🔐 <b>Type:</b> {'NSFW' if member.get('is_nsfw') else 'SFW'}\n"
        f"🏷️ <b>Tags:</b> {html.escape(tags)}\n"
        f"🎨 <b>Artist:</b> {html.escape(str(member.get('artist') or 'Unknown'))}\n"
        f"🖼️ <b>Size:</b> {html.escape(size)}\n"
        f"🔗 <b>Source:</b> {html.escape(source)}"
    )

async def gacha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Roll for a new Harem member."""
    user = update.effective_user
    chat = update.effective_chat
    user_doc = ensure_user_exists(user)
    is_group = _is_group_chat(chat)

    if user_doc.get("balance", 0) < GACHA_COST:
        await update.message.reply_text(f"❌ You need <code>{_money(GACHA_COST)}</code> to pull a Gacha!", parse_mode=ParseMode.HTML)
        return

    msg = await update.message.reply_text(f"🎰 Rolling the Harem Gacha for <code>{_money(GACHA_COST)}</code>...", parse_mode=ParseMode.HTML)

    # Roll logic
    rarity = get_random_rarity()
    r_info = RARITY_INFO[rarity]
    waifu_name = generate_waifu_name()
    waifu_data = await fetch_waifu_data(nsfw=True)
    image_url = waifu_data.get("url")

    # Save to user's harem
    new_harem_member = {
        "id": int(datetime.utcnow().timestamp()),
        "name": waifu_name,
        "rarity": rarity,
        "affection": 1,
        "image": image_url,
        "source": waifu_data.get("source"),
        "artist": waifu_data.get("artist"),
        "tags": waifu_data.get("tags", []),
        "width": waifu_data.get("width"),
        "height": waifu_data.get("height"),
        "is_nsfw": waifu_data.get("is_nsfw", True),
        "shards": 0,
        "pulled_at": datetime.utcnow(),
    }
    duplicate_idx = None
    if image_url:
        duplicate_idx = next(
            (idx for idx, item in enumerate(user_doc.get("harem", [])) if item.get("image") == image_url),
            None
        )
    duplicate_bonus = duplicate_idx is not None
    if duplicate_bonus:
        current = user_doc["harem"][duplicate_idx]
        next_affection = min(MAX_AFFECTION, int(current.get("affection", 1)) + RARITY_INFO[rarity]["bonus"])
        extra_push = None
        extra_inc = {f"harem.{duplicate_idx}.shards": RARITY_INFO[rarity]["bonus"]}
        extra_set = {
            f"harem.{duplicate_idx}.affection": next_affection,
            f"harem.{duplicate_idx}.last_duplicate_at": datetime.utcnow(),
        }
    else:
        next_affection = 1
        extra_push = {"harem": new_harem_member}
        extra_inc = None
        extra_set = None
    
    charged = adjust_user_balance(
        user.id,
        -GACHA_COST,
        "gacha",
        f"Pulled harem member {waifu_name}",
        chat_id=chat.id,
        source="/gacha",
        require_gte=GACHA_COST,
        extra_push=extra_push,
        extra_inc=extra_inc,
        extra_set=extra_set,
        meta={"rarity": rarity, "waifu_name": waifu_name, "duplicate": duplicate_bonus},
    )
    if not charged:
        await msg.edit_text(f"❌ You need <code>{_money(GACHA_COST)}</code> to pull a Gacha!", parse_mode=ParseMode.HTML)
        return

    member_for_caption = dict(new_harem_member)
    member_for_caption["affection"] = next_affection
    caption = (
        f"\U0001F389 <b>Gacha pull successful!</b>\n\n"
        f"{'Duplicate pull converted into shards.' if duplicate_bonus else 'You unlocked a new Harem member.'}\n\n"
        f"{_member_caption(member_for_caption)}\n\n"
        f"Use <code>/date {html.escape(waifu_name)}</code> to increase affection."
    )
    caption = _with_group_cleanup_notice(caption, chat)
    
    if image_url:
        sent = await context.bot.send_photo(
            chat_id=chat.id,
            photo=image_url,
            caption=caption,
            parse_mode=ParseMode.HTML,
            has_spoiler=bool(waifu_data.get("is_nsfw") and is_group)
        )
        sent_file_id = sent.photo[-1].file_id if sent.photo else None
    else:
        sent = await context.bot.send_message(
            chat_id=chat.id,
            text=caption,
            parse_mode=ParseMode.HTML,
        )
        sent_file_id = None
    if sent_file_id:
        if duplicate_bonus:
            users_collection.update_one(
                {"user_id": user.id},
                {"$set": {f"harem.{duplicate_idx}.telegram_file_id": sent_file_id}},
            )
        else:
            users_collection.update_one(
                {"user_id": user.id, "harem.id": new_harem_member["id"]},
                {"$set": {"harem.$.telegram_file_id": sent_file_id}},
            )
    if is_group:
        await _track_group_harem_media(context, chat, sent, user.id, waifu_data.get("is_nsfw"), "gacha")
    await msg.delete()

async def harem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View collected Harem members."""
    user = update.effective_user
    user_doc = ensure_user_exists(user)
    
    harem = user_doc.get("harem", [])
    if not harem:
        await update.message.reply_text("😢 Your harem is empty! Use <code>/gacha</code> to roll for characters.", parse_mode=ParseMode.HTML)
        return

    if context.args:
        return await _send_harem_card(update, context, " ".join(context.args), harem)

    # Sort by affection (descending), then rarity bonus
    harem.sort(key=lambda x: (x.get('affection', 1), RARITY_INFO[x['rarity']]['bonus']), reverse=True)

    text = f"🌸 <b>{html.escape(user.first_name)}'s Harem</b> 🌸\n\n"
    for idx, w in enumerate(harem[:10]): # Show top 10
        r_info = RARITY_INFO[w['rarity']]
        text += f"{idx+1}. {r_info['emote']} <b>{_clean_name(w['name'])}</b> | Affection: 💖 <code>{w.get('affection', 1)}/{MAX_AFFECTION}</code>\n"

    if len(harem) > 10:
        text += f"\n<i>...and {len(harem) - 10} more.</i>"

    text += f"\n\n<i>Use <code>/harem name</code>, <code>/card name</code>, or <code>/date name</code>.</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def _send_harem_card(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, harem):
    _, member = _find_harem_member(harem, query)
    if not member:
        await update.message.reply_text(
            f"❌ Character <b>{html.escape(str(query).title())}</b> not found in your harem.",
            parse_mode=ParseMode.HTML,
        )
        return

    chat = update.effective_chat
    user = update.effective_user
    caption = _with_group_cleanup_notice(_member_caption(member), chat)
    image = _member_image(member)
    if image:
        sent = await update.message.reply_photo(
            photo=image,
            caption=caption,
            parse_mode=ParseMode.HTML,
            has_spoiler=bool(member.get("is_nsfw")),
        )
        await _track_group_harem_media(context, chat, sent, user.id, member.get("is_nsfw"), "harem_card")
    else:
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)

async def card_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_doc = ensure_user_exists(update.effective_user)
    if not context.args:
        return await update.message.reply_text("📖 Usage: <code>/card character_name</code>", parse_mode=ParseMode.HTML)
    await _send_harem_card(update, context, " ".join(context.args), user_doc.get("harem", []))

async def date_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Increase affection with a Harem member."""
    user = update.effective_user
    user_doc = ensure_user_exists(user)

    if not context.args:
        await update.message.reply_text("❌ Specify a character to date! Usage: <code>/date name</code>", parse_mode=ParseMode.HTML)
        return

    target_name = " ".join(context.args).lower()
    harem = user_doc.get("harem", [])
    
    # Find character
    target_idx = None
    for idx, w in enumerate(harem):
        if w['name'].lower() == target_name:
            target_idx = idx
            break

    if target_idx is None:
        await update.message.reply_text(f"❌ You don't have <b>{html.escape(target_name.title())}</b> in your harem.", parse_mode=ParseMode.HTML)
        return

    waifu = harem[target_idx]
    current_affection = waifu.get('affection', 1)

    if current_affection >= MAX_AFFECTION:
        await update.message.reply_text(f"💖 <b>{_clean_name(waifu['name'])}</b> is already at MAX Affection! Use <code>/special {html.escape(waifu['name'])}</code> in PMs.", parse_mode=ParseMode.HTML)
        return

    if user_doc.get("balance", 0) < DATE_COST:
        await update.message.reply_text(f"❌ You need <code>{_money(DATE_COST)}</code> to go on a date!", parse_mode=ParseMode.HTML)
        return

    updated = adjust_user_balance(
        user.id,
        -DATE_COST,
        "date",
        f"Dated {waifu['name']}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/date",
        require_gte=DATE_COST,
        extra_set={f"harem.{target_idx}.affection": current_affection + 1},
        meta={"waifu_name": waifu["name"], "affection": current_affection + 1},
    )
    if not updated:
        await update.message.reply_text(f"❌ You need <code>{_money(DATE_COST)}</code> to go on a date!", parse_mode=ParseMode.HTML)
        return

    caption = (
        f"\U0001F496 <b>Date complete!</b>\n\n"
        f"You took <b>{_clean_name(waifu['name'])}</b> on a romantic date for <code>{_money(DATE_COST)}</code>.\n"
        f"Affection increased to <code>{current_affection + 1}/{MAX_AFFECTION}</code>."
    )
    caption = _with_group_cleanup_notice(caption, update.effective_chat)
    image = _member_image(waifu)
    if image:
        try:
            sent = await update.message.reply_photo(
                photo=image,
                caption=caption,
                parse_mode=ParseMode.HTML,
                has_spoiler=bool(waifu.get("is_nsfw")),
            )
            await _track_group_harem_media(context, update.effective_chat, sent, user.id, waifu.get("is_nsfw"), "date")
            return
        except TelegramError:
            pass
    await update.message.reply_text(caption, parse_mode=ParseMode.HTML)

async def special_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unlock NSFW reward for max affection (PM only)."""
    user = update.effective_user
    chat = update.effective_chat
    user_doc = ensure_user_exists(user)

    if chat.type != ChatType.PRIVATE:
        # Delete message to keep group clean, warn user
        try: await update.message.delete()
        except: pass
        
        warn_msg = await context.bot.send_message(
            chat_id=chat.id, 
            text=f"⚠️ {get_mention(user)}, the <code>/special</code> command is strictly <b>NSFW</b> and can only be used in private messages with me. Send me a DM!",
            parse_mode=ParseMode.HTML
        )
        asyncio.create_task(_delete_message_after(context, chat.id, warn_msg.message_id, delay=60))
        return

    if not context.args:
        await update.message.reply_text("❌ Specify a max affection character! Usage: <code>/special name</code>", parse_mode=ParseMode.HTML)
        return

    target_name = " ".join(context.args).lower()
    harem = user_doc.get("harem", [])
    
    target_waifu = None
    for w in harem:
        if w['name'].lower() == target_name:
            target_waifu = w
            break

    if not target_waifu:
        await update.message.reply_text("❌ Character not found in your harem.", parse_mode=ParseMode.HTML)
        return

    if target_waifu.get('affection', 1) < MAX_AFFECTION:
        await update.message.reply_text(f"❌ <b>{_clean_name(target_waifu['name'])}</b> does not trust you enough yet. Reach Affection Level <code>{MAX_AFFECTION}</code> first!", parse_mode=ParseMode.HTML)
        return

    msg = await update.message.reply_text("😏 Preparing your special reward...", parse_mode=ParseMode.HTML)
    
    # Fetch NSFW image
    nsfw_url = await fetch_waifu_image(nsfw=True)
    
    caption = f"🤫 Here is your special reward for maxing out <b>{_clean_name(target_waifu['name'])}</b>'s affection! 💖\n\n<i>This is only visible in PMs for your safety.</i>"
    
    # Send photo with spoiler flag for safety
    try:
        await context.bot.send_photo(
            chat_id=chat.id,
            photo=nsfw_url,
            caption=caption,
            parse_mode=ParseMode.HTML,
            has_spoiler=True
        )
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"⚠️ Failed to load reward: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
