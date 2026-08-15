# Copyright (c) 2025 Telegram:- @WTF_Phantom <DevixOP>
# Location: Supaul, Bihar 

import random
from datetime import datetime, timedelta
import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.config import WAIFU_PROPOSE_COST
from kazumi.database import users_collection
from kazumi.plugins.chatbot import ask_mistral_raw
from kazumi.utils import apply_custom_emojis, ensure_user_exists, format_money, get_mention, resolve_target, stylize_text

API_URL = "https://api.waifu.pics"
SFW_ACTIONS = [
    "kick", "happy", "wink", "poke", "dance", "cringe", "kill", "waifu", "neko", 
    "shinobu", "bully", "cuddle", "cry", "hug", "awoo", "lick", "pat", "smug", 
    "bonk", "yeet", "blush", "smile", "wave", "highfive", "handhold", "nom", 
    "bite", "glomp", "slap", "kiss", "spank", "smack", "stare", "tickle", "feed"
]


async def waifu_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0].replace("/", "")
    if cmd not in SFW_ACTIONS:
        return

    target, _ = await resolve_target(update, context)
    user = update.effective_user

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{API_URL}/sfw/{cmd if cmd in ['kick', 'happy', 'wink', 'poke', 'dance', 'cringe', 'kill', 'waifu', 'neko', 'shinobu', 'bully', 'cuddle', 'cry', 'hug', 'awoo', 'lick', 'pat', 'smug', 'bonk', 'yeet', 'blush', 'smile', 'wave', 'highfive', 'handhold', 'nom', 'bite', 'glomp', 'slap'] else 'hug'}")
            url = resp.json().get('url')
    except Exception:
        url = "https://media.giphy.com/media/pSpmPXdHQWZrcuJRq3/giphy.gif"

    s_link = get_mention(user)
    t_link = get_mention(target) if target else "the air"

    caption = f"{s_link} {cmd}s {t_link}!"
    if cmd == "kill":
        caption = f"{s_link} murdered {t_link} 💀"
    elif cmd == "kiss":
        caption = f"{s_link} kissed {t_link} 💋"
    elif cmd == "slap":
        caption = f"{s_link} slapped {t_link} hard! 🖐️"
    elif cmd == "bite":
        caption = f"{s_link} bit {t_link}! 🦷"

    await update.message.reply_animation(animation=url, caption=apply_custom_emojis(caption), parse_mode=ParseMode.HTML)


async def wpropose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Propose to a Waifu (Uses Gold)."""
    user = ensure_user_exists(update.effective_user)

    if user['balance'] < WAIFU_PROPOSE_COST:
        return await update.message.reply_text(apply_custom_emojis(f"❌ <b>Poor!</b> Need {format_money(WAIFU_PROPOSE_COST)}."), parse_mode=ParseMode.HTML)

    users_collection.update_one({"user_id": user['user_id']}, {"$inc": {"balance": -WAIFU_PROPOSE_COST}})

    success = random.random() < 0.3

    if success:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get("https://api.waifu.im/search?tags=waifu")
                img_url = r.json()['images'][0]['url']
        except Exception:
            img_url = "https://media.giphy.com/media/pSpmPXdHQWZrcuJRq3/giphy.gif"

        waifu_data = {"name": "Celestial Queen", "rarity": "Celestial", "date": datetime.utcnow()}
        users_collection.update_one({"user_id": user['user_id']}, {"$push": {"waifus": waifu_data}})

        await update.message.reply_photo(img_url, caption=apply_custom_emojis("💍 <b>YES!</b>\n\nYou married a <b>CELESTIAL WAIFU</b>!"), parse_mode=ParseMode.HTML)
    else:
        prompt = "Roast a user named 'Player' who got rejected by an anime girl. Hinglish."
        roast = await ask_mistral_raw("Savage Roaster", prompt)
        fail_gifs = ["https://media.giphy.com/media/pSpmPXdHQWZrcuJRq3/giphy.gif"]

        await update.message.reply_animation(
            random.choice(fail_gifs),
            caption=apply_custom_emojis(f"💔 <b>REJECTED!</b>\n\n🗣️ <i>{stylize_text(roast or 'Lol loser.')}</i>"),
            parse_mode=ParseMode.HTML
        )


async def wmarry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    last = user.get("last_wmarry")
    if last and (datetime.utcnow() - last) < timedelta(hours=2):
        return await update.message.reply_text(apply_custom_emojis("⏳ <b>Cooldown!</b> Wait."), parse_mode=ParseMode.HTML)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.waifu.pics/sfw/waifu")
            url = r.json()['url']
    except Exception:
        url = "https://media.giphy.com/media/pSpmPXdHQWZrcuJRq3/giphy.gif"

    waifu_data = {"name": "Random Waifu", "rarity": "Rare", "date": datetime.utcnow()}
    users_collection.update_one({"user_id": user['user_id']}, {"$push": {"waifus": waifu_data}, "$set": {"last_wmarry": datetime.utcnow()}})
    await update.message.reply_photo(url, caption=apply_custom_emojis("✨ You married a new Waifu!"), parse_mode=ParseMode.HTML)
