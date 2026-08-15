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

import html
import random
import re

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.database import riddles_collection, users_collection
from kazumi.utils import format_money, ensure_user_exists, get_mention
from kazumi.config import RIDDLE_REWARD

FALLBACK_RIDDLES = [
    {"q": "I guard secrets without a mouth, open only when the right symbol arrives. What am I?", "a": "lock", "aliases": ["keyhole"]},
    {"q": "I travel the world while staying in one corner. What am I?", "a": "stamp", "aliases": ["postage stamp"]},
    {"q": "I get sharper the more you use me, but I am not a blade. What am I?", "a": "mind", "aliases": ["brain"]},
    {"q": "I show you the truth, but everything I show is reversed. What am I?", "a": "mirror", "aliases": ["reflection"]},
    {"q": "I can fill a room but take no space. What am I?", "a": "light", "aliases": ["sunlight"]},
    {"q": "I speak without a voice and answer only after you call. What am I?", "a": "echo", "aliases": ["an echo"]},
    {"q": "I have cities but no houses, rivers but no water, and roads but no cars. What am I?", "a": "map", "aliases": ["a map"]},
    {"q": "I become smaller every time I take a bath. What am I?", "a": "soap", "aliases": ["bar of soap"]},
    {"q": "I am bought to eat, but never eaten. What am I?", "a": "plate", "aliases": ["dish"]},
    {"q": "I can be cracked, made, told, and played. What am I?", "a": "joke", "aliases": ["a joke"]},
    {"q": "The more you remove from me, the bigger I become. What am I?", "a": "hole", "aliases": ["a hole"]},
    {"q": "I run all day but never get tired. What am I?", "a": "clock", "aliases": ["watch"]},
    {"q": "I have keys but open no locks. What am I?", "a": "keyboard", "aliases": ["piano"]},
    {"q": "I am always in front of you, but you can never see me. What am I?", "a": "future", "aliases": ["the future"]},
    {"q": "I am strongest when shared, weakest when hidden, and dangerous when false. What am I?", "a": "truth", "aliases": ["the truth"]},
    {"q": "I am always coming, but I never arrive. What am I?", "a": "tomorrow", "aliases": ["future", "the future"]},
    {"q": "I follow you in light, disappear in darkness, and never make a sound. What am I?", "a": "shadow", "aliases": ["your shadow"]},
    {"q": "I have a face and hands, but no body. What am I?", "a": "clock", "aliases": ["watch"]},
    {"q": "I go up but never come down. What am I?", "a": "age", "aliases": ["your age"]},
    {"q": "I am full of holes but still hold water. What am I?", "a": "sponge", "aliases": ["a sponge"]},
    {"q": "I am taken before you get it. What am I?", "a": "photo", "aliases": ["picture", "photograph"]},
    {"q": "I break when you say my name. What am I?", "a": "silence", "aliases": ["quiet"]},
    {"q": "I have branches but no fruit, trunk, or leaves. What am I?", "a": "bank", "aliases": ["a bank"]},
    {"q": "I can be long or short, grown or bought, painted or bare. What am I?", "a": "nail", "aliases": ["fingernail"]},
    {"q": "I am lighter than air, but a hundred people cannot hold me for long. What am I?", "a": "breath", "aliases": ["your breath"]},
    {"q": "I fly without wings and cry without eyes. What am I?", "a": "cloud", "aliases": ["a cloud"]},
    {"q": "I have one eye but cannot see. What am I?", "a": "needle", "aliases": ["a needle"]},
    {"q": "I am a word. Add two letters and I become shorter. What am I?", "a": "short", "aliases": ["the word short"]},
    {"q": "I get wet while drying. What am I?", "a": "towel", "aliases": ["a towel"]},
    {"q": "I have teeth but cannot bite. What am I?", "a": "comb", "aliases": ["a comb"]},
    {"q": "I am not alive, but I grow. I do not have lungs, but I need air. What am I?", "a": "fire", "aliases": ["flame"]},
    {"q": "I am a room with no doors or windows. What am I?", "a": "mushroom", "aliases": ["a mushroom"]},
    {"q": "I am yours, but other people use me more than you do. What am I?", "a": "name", "aliases": ["your name"]},
    {"q": "I have a neck but no head. What am I?", "a": "bottle", "aliases": ["a bottle"]},
    {"q": "I can run but never walk, have a mouth but never talk. What am I?", "a": "river", "aliases": ["a river"]},
    {"q": "I am black when clean and white when dirty. What am I?", "a": "blackboard", "aliases": ["chalkboard"]},
    {"q": "I am always hungry and die if you feed me water. What am I?", "a": "fire", "aliases": ["flame"]},
    {"q": "I have words but never speak. What am I?", "a": "book", "aliases": ["a book"]},
    {"q": "I can be opened but I am not a door, I can be closed but I am not a shop. What am I?", "a": "book", "aliases": ["notebook"]},
    {"q": "I am a crown without a king and roots without a tree. What am I?", "a": "tooth", "aliases": ["a tooth"]},
    {"q": "I am seen once in a minute, twice in a moment, but never in a thousand years. What am I?", "a": "m", "aliases": ["letter m"]},
    {"q": "I am a code that protects your secrets, but I vanish when shared. What am I?", "a": "password", "aliases": ["passcode"]},
    {"q": "I am a ghost in your phone: seen, deleted, and still remembered. What am I?", "a": "notification", "aliases": ["message notification"]},
    {"q": "I can crash without moving and freeze without ice. What am I?", "a": "computer", "aliases": ["pc", "laptop"]},
    {"q": "I have a battery, a screen, and secrets in my pocket. What am I?", "a": "phone", "aliases": ["mobile", "smartphone"]},
    {"q": "I keep your place in a story without reading a single word. What am I?", "a": "bookmark", "aliases": ["book mark"]},
    {"q": "I open to the world, but I am not a door. What am I?", "a": "window", "aliases": ["a window"]},
    {"q": "I fall from clouds but never climb back up. What am I?", "a": "rain", "aliases": ["raindrop", "water"]},
    {"q": "I am cold, white, and melt when held too close. What am I?", "a": "snow", "aliases": ["ice"]},
    {"q": "I point the way but never walk there myself. What am I?", "a": "compass", "aliases": ["a compass"]},
    {"q": "I protect you from rain but hate the wind. What am I?", "a": "umbrella", "aliases": ["an umbrella"]},
    {"q": "I hold ships still without touching land. What am I?", "a": "anchor", "aliases": ["an anchor"]},
    {"q": "I cover your hand but have no hand of my own. What am I?", "a": "glove", "aliases": ["a glove"]},
    {"q": "I connect two sides but never choose one. What am I?", "a": "bridge", "aliases": ["a bridge"]},
    {"q": "I am made of links, but I am not the internet. What am I?", "a": "chain", "aliases": ["a chain"]},
    {"q": "I wake you up by making noise, but I never sleep. What am I?", "a": "alarm", "aliases": ["alarm clock"]},
    {"q": "I roll, I stop, and luck decides my face. What am I?", "a": "dice", "aliases": ["die"]},
    {"q": "I hide a face and reveal a character. What am I?", "a": "mask", "aliases": ["a mask"]},
    {"q": "I write until I slowly disappear. What am I?", "a": "pencil", "aliases": ["lead pencil"]},
    {"q": "I carry a message but never read it. What am I?", "a": "envelope", "aliases": ["letter"]},
    {"q": "I shine at night but borrow my light. What am I?", "a": "moon", "aliases": ["the moon"]},
    {"q": "I am money with two faces and no mouth. What am I?", "a": "coin", "aliases": ["a coin"]},
    {"q": "I go down only when you climb me up. What am I?", "a": "stairs", "aliases": ["staircase", "steps"]},
    {"q": "I make memories visible with one click. What am I?", "a": "camera", "aliases": ["a camera"]},
    {"q": "I power your phone but hate being empty. What am I?", "a": "battery", "aliases": ["a battery"]},
    {"q": "I am a promise that breaks when ignored. What am I?", "a": "deadline", "aliases": ["due date"]},
    {"q": "I have pages but no voice, and I can teach without speaking. What am I?", "a": "book", "aliases": ["textbook"]},
    {"q": "I can be sent without walking and received without hands. What am I?", "a": "message", "aliases": ["text", "dm"]},
    {"q": "I am a small door in a screen that opens a whole app. What am I?", "a": "button", "aliases": ["app button"]},
    {"q": "I count your steps but never take one. What am I?", "a": "pedometer", "aliases": ["step counter"]},
]

_RECENT_RIDDLE_ANSWERS = {}

def _is_reply_to_kazumi(message, context):
    replied = getattr(message, "reply_to_message", None)
    if not replied or not replied.from_user:
        return False
    return replied.from_user.id == context.bot.id

def _normalize_answer(value):
    text = str(value or "").lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = " ".join(text.split())
    for prefix in ("the ", "a ", "an "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text

def _answer_variants(value):
    normalized = _normalize_answer(value)
    if not normalized:
        return set()
    variants = {normalized, normalized.replace(" ", "")}
    words = normalized.split()
    if len(words) > 1:
        variants.add(" ".join(words[-2:]))
        variants.add(words[-1])
    if normalized.endswith("es"):
        variants.add(normalized[:-2])
    if normalized.endswith("s"):
        variants.add(normalized[:-1])
    return {v for v in variants if v}

def _pick_fallback(chat_id):
    recent = set(_RECENT_RIDDLE_ANSWERS.get(chat_id, []))
    choices = [item for item in FALLBACK_RIDDLES if _normalize_answer(item["a"]) not in recent] or FALLBACK_RIDDLES
    return random.choice(choices)

def _remember_answer(chat_id, answer):
    recent = _RECENT_RIDDLE_ANSWERS.setdefault(chat_id, [])
    normalized = _normalize_answer(answer)
    if normalized:
        recent.append(normalized)
    del recent[:-8]

import asyncio

ACTIVE_RIDDLE_CHATS = set()


async def riddle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts a fair riddle from the curated Kazumi bank."""
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE: return await update.message.reply_text("❌ Group Only!", parse_mode=ParseMode.HTML)

    if chat.id in ACTIVE_RIDDLE_CHATS or await asyncio.to_thread(riddles_collection.find_one, {"chat_id": chat.id}):
        ACTIVE_RIDDLE_CHATS.add(chat.id)
        return await update.message.reply_text("⚠️ A riddle is already active! Guess it.", parse_mode=ParseMode.HTML)

    msg = await update.message.reply_text("🧠 <b>Preparing Riddle...</b>", parse_mode=ParseMode.HTML)

    parsed = _pick_fallback(chat.id)

    question = parsed["q"].strip()
    answer = parsed["a"].strip()
    aliases = list(parsed.get("aliases") or [])
    accepted_answers = set()
    accepted_answers.update(_answer_variants(answer))
    for alias in aliases:
        accepted_answers.update(_answer_variants(alias))
    if not accepted_answers:
        return await msg.edit_text("⚠️ AI Error.", parse_mode=ParseMode.HTML)
    _remember_answer(chat.id, answer)

    # Save
    await asyncio.to_thread(riddles_collection.insert_one, {
        "chat_id": chat.id,
        "answer": _normalize_answer(answer),
        "display_answer": answer,
        "accepted_answers": sorted(accepted_answers),
    })
    ACTIVE_RIDDLE_CHATS.add(chat.id)

    await msg.edit_text(
        f"🧩 <b>𝐀𝐈 𝐑𝐢𝐝𝐝𝐥𝐞 𝐂𝐡𝐚𝐥𝐥𝐞𝐧𝐠𝐞!</b>\n\n"
        f"<i>{html.escape(question)}</i>\n\n"
        f"💡 <b>Reward:</b> <code>{format_money(RIDDLE_REWARD)}</code>\n"
        f"👇 <i>Reply with your answer!</i>",
        parse_mode=ParseMode.HTML
    )

async def check_riddle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks user messages for the answer."""
    if not update.message or not update.message.text: return
    chat = update.effective_chat
    if chat.id not in ACTIVE_RIDDLE_CHATS:
        return
    text = update.message.text.strip().lower()

    riddle = await asyncio.to_thread(riddles_collection.find_one, {"chat_id": chat.id})
    if not riddle:
        ACTIVE_RIDDLE_CHATS.discard(chat.id)
        return

    guess_variants = _answer_variants(text)
    accepted_answers = set(riddle.get("accepted_answers") or [riddle.get("answer")])
    if guess_variants & accepted_answers:
        user = update.effective_user
        await asyncio.to_thread(ensure_user_exists, user)
        
        # Winner
        await asyncio.to_thread(users_collection.update_one, {"user_id": user.id}, {"$inc": {"balance": RIDDLE_REWARD}})
        await asyncio.to_thread(riddles_collection.delete_one, {"chat_id": chat.id})
        ACTIVE_RIDDLE_CHATS.discard(chat.id)
        
        await update.message.reply_text(
            f"🎉 <b>𝐂𝐨𝐫𝐫𝐞𝐜𝐭!</b>\n\n"
            f"👤 <b>Winner:</b> {get_mention(user)}\n"
            f"💰 <b>Won:</b> <code>{format_money(RIDDLE_REWARD)}</code>\n"
            f"🔑 <b>Answer:</b> <i>{html.escape(str(riddle.get('display_answer') or riddle.get('answer') or '').title())}</i>",
            parse_mode=ParseMode.HTML
        )
        raise ApplicationHandlerStop

    if _is_reply_to_kazumi(update.message, context):
        raise ApplicationHandlerStop
