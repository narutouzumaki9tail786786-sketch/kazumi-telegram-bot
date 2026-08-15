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

import random
import html
import unicodedata
from io import BytesIO
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from kazumi.database import groups_collection
from kazumi.utils import get_mention, ensure_user_exists
from kazumi.config import WELCOME_IMG_URL, BOT_NAME, START_IMG_URL, SUPPORT_GROUP, WELCOME_CARD_ENABLED


WELCOME_CARD_SIZE = (1280, 720)
FONT_PATHS = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

FANCY_TEXT_MAP = str.maketrans({
    "Ɗ": "D",
    "ɗ": "d",
    "ᴇ": "e",
    "ᴅ": "d",
    "ꜱ": "s",
    "ꜰ": "f",
    "ᴛ": "t",
    "ʀ": "r",
    "ᴏ": "o",
    "ʏ": "y",
    "ᴇ": "e",
    "ʟ": "l",
    "ɪ": "i",
    "ɴ": "n",
    "ᴍ": "m",
    "ᴡ": "w",
    "ᴄ": "c",
    "ᴘ": "p",
    "ʙ": "b",
    "ʜ": "h",
    "ᴋ": "k",
    "ǫ": "q",
    "ᴀ": "a",
    "ᴠ": "v",
    "ᴢ": "z",
    "ғ": "f",
})


def _load_font(size, bold=False):
    choices = FONT_PATHS if bold else tuple(reversed(FONT_PATHS))
    for path in choices:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _cover_crop(image, size):
    image = ImageOps.exif_transpose(image).convert("RGB")
    src_ratio = image.width / image.height
    dst_ratio = size[0] / size[1]
    if src_ratio > dst_ratio:
        new_width = int(image.height * dst_ratio)
        left = (image.width - new_width) // 2
        image = image.crop((left, 0, left + new_width, image.height))
    else:
        new_height = int(image.width / dst_ratio)
        top = (image.height - new_height) // 2
        image = image.crop((0, top, image.width, top + new_height))
    return image.resize(size, Image.Resampling.LANCZOS)


def _circle_avatar(image, size):
    image = _cover_crop(image, (size, size)).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    image.putalpha(mask)
    return image


def _initial_avatar(name, size):
    avatar = Image.new("RGBA", (size, size), (255, 120, 190, 255))
    draw = ImageDraw.Draw(avatar)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(255, 116, 190, 255))
    initial = _card_safe_text(name, 1, fallback="K").upper()
    font = _load_font(86, bold=True)
    bbox = draw.textbbox((0, 0), initial, font=font)
    draw.text(
        ((size - (bbox[2] - bbox[0])) / 2, (size - (bbox[3] - bbox[1])) / 2 - 8),
        initial,
        font=font,
        fill=(255, 255, 255, 255),
    )
    return avatar


async def _download_image_from_source(context, source):
    if not source:
        return None
    try:
        if str(source).startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(source)
                response.raise_for_status()
                return Image.open(BytesIO(response.content))
        telegram_file = await context.bot.get_file(source)
        data = BytesIO()
        await telegram_file.download_to_memory(out=data)
        data.seek(0)
        return Image.open(data)
    except Exception:
        return None


async def _download_user_avatar(context, user):
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if not photos.total_count:
            return None
        telegram_file = await context.bot.get_file(photos.photos[0][-1].file_id)
        data = BytesIO()
        await telegram_file.download_to_memory(out=data)
        data.seek(0)
        return Image.open(data)
    except Exception:
        return None


def _trim_text(text, max_chars):
    text = " ".join(str(text or "").split())
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "..."


def _card_safe_text(text, max_chars, fallback="PLAYER"):
    normalized = unicodedata.normalize("NFKC", str(text or "")).translate(FANCY_TEXT_MAP)
    cleaned = []
    for char in normalized:
        category = unicodedata.category(char)
        if char.isspace():
            cleaned.append(" ")
        elif category[0] in {"L", "N"}:
            cleaned.append(char)
        elif char in {"-", "_", ".", "~"}:
            cleaned.append(" ")
        elif category[0] in {"M", "S", "C", "P"}:
            continue
    safe = " ".join("".join(cleaned).split())
    return _trim_text(safe or fallback, max_chars)


def _fit_font(text, start_size, min_size, max_width, *, bold=False):
    size = int(start_size)
    while size > int(min_size):
        font = _load_font(size, bold=bold)
        bbox = font.getbbox(str(text or ""))
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return _load_font(min_size, bold=bold)


async def build_welcome_card(context, user, chat):
    if not WELCOME_CARD_ENABLED:
        return None

    background = await _download_image_from_source(context, WELCOME_IMG_URL)
    if background is None:
        return None

    card = _cover_crop(background, WELCOME_CARD_SIZE).convert("RGBA")
    overlay = Image.new("RGBA", WELCOME_CARD_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Soft readability layers over the anime background.
    draw.rectangle((0, 0, 560, 720), fill=(4, 10, 24, 188))
    draw.rectangle((0, 520, 1280, 720), fill=(4, 10, 24, 132))
    draw.rounded_rectangle((54, 92, 520, 610), radius=34, fill=(7, 17, 38, 178), outline=(124, 232, 255, 135), width=2)
    draw.rounded_rectangle((78, 116, 198, 126), radius=5, fill=(255, 105, 190, 255))
    draw.rounded_rectangle((202, 116, 312, 126), radius=5, fill=(90, 240, 210, 255))
    card = Image.alpha_composite(card, overlay)
    draw = ImageDraw.Draw(card)

    avatar_src = await _download_user_avatar(context, user)
    avatar = _circle_avatar(avatar_src, 156) if avatar_src else _initial_avatar(user.first_name, 156)
    ring = Image.new("RGBA", (174, 174), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    ring_draw.ellipse((0, 0, 173, 173), outline=(255, 116, 190, 255), width=7)
    ring_draw.ellipse((8, 8, 165, 165), outline=(107, 246, 255, 220), width=3)
    card.alpha_composite(ring, (88, 166))
    card.alpha_composite(avatar, (97, 175))

    title_font = _load_font(64, bold=True)
    name_font = _load_font(52, bold=True)
    meta_font = _load_font(28, bold=True)
    small_font = _load_font(24, bold=False)
    tag_font = _load_font(20, bold=True)

    user_fallback = getattr(user, "username", None) or getattr(user, "first_name", None) or "PLAYER"
    user_name = _card_safe_text(user.full_name or user.first_name, 18, fallback=user_fallback)
    group_name = _card_safe_text(chat.title or "Kazumi Group", 30, fallback="KAZUMI GROUP")
    name_font = _fit_font(user_name.upper(), 52, 34, 400, bold=True)
    meta_font = _fit_font(group_name.upper(), 28, 20, 405, bold=True)
    draw.text((88, 360), "WELCOME", font=title_font, fill=(255, 255, 255, 255))
    draw.text((88, 430), user_name.upper(), font=name_font, fill=(122, 246, 255, 255))
    draw.text((90, 500), group_name.upper(), font=meta_font, fill=(255, 214, 116, 255))
    draw.text((90, 548), "REGISTER TO START YOUR RPG JOURNEY", font=small_font, fill=(225, 235, 255, 235))

    draw.rounded_rectangle((88, 60, 304, 102), radius=20, fill=(255, 116, 190, 230))
    draw.text((112, 70), "KAZUMI WELCOME", font=tag_font, fill=(255, 255, 255, 255))

    output = BytesIO()
    output.name = "kazumi_welcome_card.png"
    card.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


async def _reply_welcome_photo(message, context, user, chat, caption, reply_markup=None):
    card = await build_welcome_card(context, user, chat)
    try:
        if card:
            return await message.reply_photo(card, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return await message.reply_photo(WELCOME_IMG_URL, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except Exception:
        return await message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable/Disable Welcomes."""
    chat = update.effective_chat
    user = update.effective_user
    args = context.args
    
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("\U0001F37C <b>This command works in grp only baby!</b>", parse_mode=ParseMode.HTML)
    
    member = await chat.get_member(user.id)
    if member.status not in ['administrator', 'creator']:
        return await update.message.reply_text("\U0000274C <b>Admin only!</b>", parse_mode=ParseMode.HTML)

    if not args:
        return await update.message.reply_text("\U000026A0\U0000FE0F <b>Usage:</b> <code>/welcome on</code> or <code>off</code>", parse_mode=ParseMode.HTML)
    
    state = args[0].lower()
    if state in ['on', 'enable', 'yes']:
        groups_collection.update_one({"chat_id": chat.id}, {"$set": {"welcome_enabled": True}}, upsert=True)
        await update.message.reply_text("\U00002705 <b>𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞𝐬 𝐄𝐧𝐚𝐛𝐥𝐞𝐝!</b>", parse_mode=ParseMode.HTML)
    elif state in ['off', 'disable', 'no']:
        groups_collection.update_one({"chat_id": chat.id}, {"$set": {"welcome_enabled": False}}, upsert=True)
        await update.message.reply_text("\U0000274C <b>𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐌𝐞𝐬𝐬𝐚𝐠𝐞𝐬 𝐃𝐢𝐬𝐚𝐛𝐥𝐞𝐝!</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("⚠️ Invalid option. Use <code>on</code> or <code>off</code>.", parse_mode=ParseMode.HTML)

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    
    for member in update.message.new_chat_members:
        # --- 🤖 BOT ADDED TO GROUP ---
        if member.id == context.bot.id:
            adder = update.message.from_user
            ensure_user_exists(adder)
            
            groups_collection.update_one({"chat_id": chat.id}, {"$set": {"welcome_enabled": True, "title": chat.title}}, upsert=True)
            
            txt = (
                f"\U0001F338 <b>𝐀𝐫𝐢𝐠𝐚𝐭𝐨 {get_mention(adder)}!</b>\n\n"
                f"Thanks for adding <b>{html.escape(chat.title)}</b>! \U00002728\n\n"
                f"\U0001F381 <b>First Time Bonus:</b>\n"
                f"Type <code>/claim</code> fast to get 2,000 Coins!\n"
                f"(Only the first person gets it!)"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F4AC 𝐒𝐮𝐩𝐩𝐨𝐫𝐭", url=SUPPORT_GROUP)]])
            
            await _reply_welcome_photo(update.message, context, adder, chat, txt, reply_markup=kb)

        # --- 👤 USER JOINED GROUP ---
        else:
            ensure_user_exists(member)
            group_data = groups_collection.find_one({"chat_id": chat.id})
            
            if group_data and group_data.get("welcome_enabled"):
                greetings = ["Hello", "Hiii", "Welcome", "Kon'nichiwa"]
                greet = random.choice(greetings)
                txt = (
                    f"\U0001F44B <b>{greet} {get_mention(member)}!</b>\n\n"
                    f"Welcome to <b>{html.escape(chat.title)}</b> \U0001F338\n"
                    f"Don't forget to /register!"
                )
                await _reply_welcome_photo(update.message, context, member, chat, txt)
