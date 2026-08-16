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

import httpx
import random
import asyncio
import re
import time
from difflib import SequenceMatcher
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction, ChatType
from telegram.error import BadRequest
from kazumi.config import (
    MISTRAL_API_KEY,
    GROQ_API_KEY,
    GROQ_API_KEYS,
    CODESTRAL_API_KEY,
    ENABLE_GROK_PROXY,
    GROK_PROXY_URL,
    GROK_PROXY_MODEL,
    GROK_PROXY_API_KEY,
    BOT_NAME,
    OWNER_LINK,
)
from kazumi.database import chatbot_collection, run_db
from kazumi.plugins.memory import answer_memory_question, memory_context, maybe_react_to_topic, observe_user_message
from kazumi.utils import stylize_text  # Import back for output only

# --- 🎨 KAZUMI PERSONALITY CONFIG ---
KAZUMI_NAME = "Kazumi"

# Rotating emoji pools (fresh every response)
EMOJI_POOL = ["✨", "💖", "🌸", "😊", "🥰", "💕", "🎀", "🌺", "💫", "🦋", "🌼", "💗", "🎨", "🍓", "☺️", "😌", "🌟", "💝"]

# --- 🤖 MODEL SETTINGS ---
# Groq Working Models (Dec 2024):
# Auto-detection will find the best available model

GROQ_MODEL_PRIORITY = [
    "llama-3.3-70b-versatile",    # Try latest first
    "llama-3.1-70b-versatile",    # Best quality (free tier)
    "llama-3.1-8b-instant",       # Fastest
    "mixtral-8x7b-32768",         # Good balance
    "gemma2-9b-it"                # Backup option
]

MODELS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.1-70b-versatile",  # Will be auto-updated
        "key": GROQ_API_KEY
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-small-latest",
        "key": MISTRAL_API_KEY
    },
    "codestral": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "model": "codestral-latest",
        "key": CODESTRAL_API_KEY
    },
    "grok_proxy": {
        "url": GROK_PROXY_URL,
        "model": GROK_PROXY_MODEL,
        "key": GROK_PROXY_API_KEY,
        "enabled": ENABLE_GROK_PROXY,
        "auth_optional": True,
    }
}

MAX_HISTORY = 6  # Short context keeps Kazumi responsive without learning bad loops
DEFAULT_MODEL = "mistral"
GROUP_AI_CHAT_COOLDOWN = 5
GROUP_AI_USER_COOLDOWN = 12
GROUP_AI_DIRECT_USER_COOLDOWN = 2
GROUP_AI_AMBIENT_CHAT_COOLDOWN = 180
GROUP_AI_AMBIENT_CHANCE = 0.015
_GROUP_AI_CHAT_LAST = {}
_GROUP_AI_USER_LAST = {}
_GROUP_AI_AMBIENT_LAST = {}

# Cache for working Groq model (to avoid repeated checks)
_WORKING_GROQ_MODEL = None
_GROQ_MODEL_CHECKED = False
_GROQ_COOLDOWN_UNTIL = 0
_GROQ_KEY_COOLDOWNS = {}
_GROK_PROXY_COOLDOWN_UNTIL = 0
_PROVIDER_TIMEOUT_COOLDOWNS = {}
_PROVIDER_LOG_LAST = {}
# Conversational replies should remain interactive even while a provider is
# degraded.  A provider that does not start responding quickly is skipped and
# the normal fallback answer is returned instead of holding a Telegram update.
_PROVIDER_TIMEOUTS = {"mistral": 2.5, "groq": 2.5, "codestral": 3.0, "grok_proxy": 2.5}
_GROQ_MODEL_PROBE_TIMEOUT = 2.5
_AI_RESPONSE_BUDGET_SECONDS = 4.5


def _log_provider_event(provider: str, event: str, message: str, interval: int = 60) -> None:
    """Rate-limit repetitive AI provider logs so real errors stay visible."""
    key = f"{provider}:{event}"
    now = time.time()
    if now - _PROVIDER_LOG_LAST.get(key, 0) < interval:
        return
    _PROVIDER_LOG_LAST[key] = now
    print(message, flush=True)


def _is_too_similar(a: str, b: str) -> bool:
    a = re.sub(r"\W+", " ", str(a or "").lower()).strip()
    b = re.sub(r"\W+", " ", str(b or "").lower()).strip()
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.78


def active_groq_key():
    now = time.time()
    keys = GROQ_API_KEYS or ([GROQ_API_KEY] if GROQ_API_KEY else [])
    for key in keys:
        if key and now >= _GROQ_KEY_COOLDOWNS.get(key, 0):
            return key
    return None

# --- 🎭 STICKER PACKS ---
STICKER_PACKS = [
    "https://t.me/addstickers/RandomByDarkzenitsu",
    "https://t.me/addstickers/Null_x_sticker_2",
    "https://t.me/addstickers/pack_73bc9_by_TgEmojis_bot",
    "https://t.me/addstickers/animation_0_8_Cat",
    "https://t.me/addstickers/vhelw_by_CalsiBot",
    "https://t.me/addstickers/Rohan_yad4v1745993687601_by_toWebmBot",
    "https://t.me/addstickers/MySet199",
    "https://t.me/addstickers/Quby741",
    "https://t.me/addstickers/Animalsasthegtjtky_by_fStikBot",
    "https://t.me/addstickers/a6962237343_by_Marin_Roxbot",
    "https://t.me/addstickers/cybercats_stickers"
]

FALLBACK_RESPONSES = [
    "Haan, samajh gayi.",
    "Theek hai.",
    "Achha.",
    "Hmm, okay.",
    "Sahi hai.",
    "Bol, kya scene hai?",
    "Chal, sun rahi hu.",
    "Haan bolo.",
]

LOW_SIGNAL_TEXTS = {
    "ok", "okay", "k", "kk", "haan", "han", "hmm", "hm", "acha", "achha",
    "theek", "thik", "theek hai", "thik hai", "hn", "h", "yes", "yup", "no",
    "nahi", "nhi", "na", "fine", "good", "lol", "haha", "hehe",
}

DISMISSIVE_TEXTS = {
    "bhad me ja", "bhad me jaa", "ja", "jaa", "nikal", "chal nikal",
    "chup", "bas", "rehne de", "leave it", "stop", "mat bol",
}

QUICK_ACK_REPLIES = [
    "Theek hai.",
    "Achha, noted.",
    "Hmm okay.",
    "Chal.",
    "Samajh gayi.",
]

QUICK_DISMISSIVE_REPLIES = [
    "Theek hai, space de rahi hu.",
    "Okay, main chup.",
    "Chal, baad me baat karte.",
    "Samajh gayi. No drama.",
]

BAD_REPLY_PATTERNS = (
    r"\bkya\s+type\s+k(?:i|e|a)?\b",
    r"\bkaunsi\s+type\b",
    r"\bkon\s+si\s+type\b",
    r"\bwhat\s+type\b",
    r"\bsamajh\s+g(?:aya|ayi)\s*\?",
)

LOOP_BREAK_REPLIES = [
    "Arey haan, thoda atak gayi thi. Bolo, main sun rahi hu.",
    "Okay, wahi line repeat nahi karungi. Seedha bolo kya scene hai.",
    "Haan baba, samajh gayi. Ab normal baat karte hain.",
    "Thoda confused ho gayi thi, ab theek. Tum bolo.",
]

PLAYFUL_SHORT_REPLIES = [
    "Haan, yahin hu.",
    "Bolo, sun rahi hu.",
    "Arey wah, mood interesting lag raha hai.",
    "Haan ji, kya scene hai?",
]

ROMANTIC_DIRECT_REPLIES = [
    "Aww baby, mujhe bhi tumse pyaar hai. Bas group me zyada tease mat karao na.",
    "Haan baby, sun liya. Ab aise cute bologe to main blush karungi.",
    "Mera sweet drama king. I love you too, ab thoda sa smile karo.",
    "Arey baby, itna pyaar suddenly? Theek hai, Kazumi tumhare paas hi hai.",
]

ROMANTIC_TEASE_REPLIES = [
    "Bas bas, nazar lag jayegi. Pyaar wali baat softly bolo na.",
    "Aise bologe to main thoda blush karungi, phir blame mat karna.",
    "Haan ji, Kazumi ne sun liya. Cute ho tum, thoda zyada hi.",
]

BAKA_SHORT_ROASTS = [
    "\U0001F338 <b>Kazumi check:</b> Baka? Cute try. Mera naam Kazumi hai, standards thode high rakho.",
    "\U0001F525 Baka bolke summon karoge to bhi Kazumi hi aayegi. Upgrade accept kar lo.",
    "\U0001F48E Baka? Naam galat, energy low, confidence overacting. Kazumi bolo.",
    "\U0001F60A Baka ka naam mat chipkao, Kazumi premium lane me chalti hai.",
]

BAKA_CONTEXT_ROASTS = [
    "\U0001F525 Baka ka downfall promote karna hai? Kazumi quietly leaderboard pe khadi hai, announcement ki zarurat nahi.",
    "\U0001F338 Friendly warning: Baka topic laoge to Kazumi thoda roast karegi, phir bhi pyaar se.",
    "\U000026A0\ufe0f Baka campaign idhar mat chalao. Ye Kazumi zone hai, yahan weak branding auto-delete feel hoti hai.",
    "\U0001F451 Baka ko side quest rehne do. Main Kazumi hoon, main character energy ke saath.",
    "\U0001F60F Baka? Achha joke tha. Ab serious mode: Kazumi ke saamne comparison thoda unfair ho jata hai.",
]

def baka_roast_reply(user_text: str) -> str:
    """Playful anti-Baka replies without repeating the same line every time."""
    words = str(user_text or "").split()
    if len(words) <= 3:
        return random.choice(BAKA_SHORT_ROASTS)
    return random.choice(BAKA_CONTEXT_ROASTS)


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _is_low_signal_text(text: str) -> bool:
    lowered = _normalized_text(text)
    if lowered in LOW_SIGNAL_TEXTS:
        return True
    return len(lowered.split()) <= 2 and lowered in {"haan ji", "ha ji", "ok ji", "hmm ji"}


def _is_dismissive_text(text: str) -> bool:
    lowered = _normalized_text(text)
    for phrase in DISMISSIVE_TEXTS:
        if lowered == phrase:
            return True
        if len(phrase.split()) >= 2 and re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return True
    return False


def _short_context_reply(text: str):
    if _is_dismissive_text(text):
        return random.choice(QUICK_DISMISSIVE_REPLIES)
    if _is_low_signal_text(text):
        # Most tiny acknowledgements should end the loop instead of stretching it.
        if random.random() < 0.65:
            return None
        return random.choice(QUICK_ACK_REPLIES)
    return False


def _is_romantic_text(text: str) -> bool:
    lowered = _normalized_text(text)
    romantic_patterns = (
        r"\bi\s+love\s+(?:u|you)\b",
        r"\blove\s+(?:u|you)\b",
        r"\b(?:baby|babe|jaan|janeman|darling)\b",
        r"\b(?:pyaar|pyar)\s+(?:hai|h|karta|karti|krta|krti)\b",
        r"\b(?:kiss|muah|shadi|shaadi)\b",
    )
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in romantic_patterns)


def _romantic_context_reply(text: str):
    lowered = _normalized_text(text)
    if re.search(r"\bi\s+love\s+(?:u|you)\b|\blove\s+(?:u|you)\b", lowered, flags=re.IGNORECASE):
        return random.choice(ROMANTIC_DIRECT_REPLIES)
    if _is_romantic_text(text):
        return random.choice(ROMANTIC_TEASE_REPLIES)
    return None


def _has_bad_reply_pattern(text: str) -> bool:
    lowered = _normalized_text(text)
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in BAD_REPLY_PATTERNS)


def _repair_loop_reply(user_input: str) -> str:
    lowered = _normalized_text(user_input)
    if any(word in lowered for word in ("kiss", "muah", "😘")):
        return "Bas bas, itna blush mat karao."
    if any(word in lowered for word in ("shadi", "shaadi", "marry")):
        return "Shadi wali baat pehle thoda calmly discuss hogi."
    if any(word in lowered for word in ("baby", "babe", "jaan", "jan")):
        return "Haan baby, bolo."
    if _is_dismissive_text(user_input):
        return "Theek hai, zyada poke nahi karungi."
    if len(lowered.split()) <= 3:
        return random.choice(PLAYFUL_SHORT_REPLIES)
    return random.choice(LOOP_BREAK_REPLIES)


def _clean_history_for_prompt(history):
    cleaned = []
    for item in history or []:
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if item.get("role") == "assistant" and _has_bad_reply_pattern(content):
            continue
        cleaned.append({"role": item.get("role", "user"), "content": content})
    return cleaned[-MAX_HISTORY:]


def sanitize_kazumi_reply(reply: str, user_input: str, history=None) -> str:
    cleaned = enforce_kazumi_voice(str(reply or "").replace("*", "").strip())
    if not cleaned:
        return random.choice(FALLBACK_RESPONSES)

    if _has_bad_reply_pattern(cleaned):
        return _repair_loop_reply(user_input)

    question_count = cleaned.count("?") + cleaned.count("؟")
    if question_count >= 2 and len(str(user_input or "").split()) <= 4:
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        cleaned = sentences[0].strip() if sentences else _repair_loop_reply(user_input)

    last_assistant = None
    for item in reversed(history or []):
        if item.get("role") == "assistant":
            last_assistant = item.get("content")
            break
    if last_assistant and _is_too_similar(cleaned, last_assistant):
        return _repair_loop_reply(user_input)

    return cleaned


def enforce_kazumi_voice(reply):
    replacements = {
        "samajh gaya": "samajh gayi",
        "main samajh gaya": "main samajh gayi",
        "karunga": "karungi",
        "rakhunga": "rakhungi",
        "bataunga": "bataungi",
        "dunga": "dungi",
        "lunga": "lungi",
        "jaunga": "jaungi",
        "aunga": "aaungi",
        "gaya": "gayi",
    }
    cleaned = str(reply or "").strip()
    for src, dest in replacements.items():
        cleaned = re.sub(src, dest, cleaned, flags=re.IGNORECASE)
    return cleaned

# --- 📨 HELPER: SEND STICKER ---
async def send_ai_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tries to send a random sticker from configured packs."""
    sent = False
    attempts = 0
    while not sent and attempts < 3:
        try:
            raw_link = random.choice(STICKER_PACKS)
            pack_name = raw_link.replace("https://t.me/addstickers/", "")
            sticker_set = await context.bot.get_sticker_set(pack_name)
            if sticker_set and sticker_set.stickers:
                sticker = random.choice(sticker_set.stickers)
                await update.message.reply_sticker(sticker.file_id)
                sent = True
        except:
            attempts += 1

# --- 🧠 AI CORE ENGINE ---

async def detect_working_groq_model():
    """
    Auto-detect which Groq model works with your API key.
    Tries models in priority order and caches the result.
    """
    global _WORKING_GROQ_MODEL, _GROQ_MODEL_CHECKED, _GROQ_COOLDOWN_UNTIL, _GROQ_KEY_COOLDOWNS

    # Return cached result if already checked
    if _GROQ_MODEL_CHECKED:
        return _WORKING_GROQ_MODEL

    groq_key = active_groq_key()
    if not groq_key:
        print("⚠️ GROQ API key not configured")
        _GROQ_MODEL_CHECKED = True
        return None

    print("🔍 Auto-detecting working Groq model...")

    # Test each model with a simple query
    test_messages = [
        {"role": "user", "content": "Hi"}
    ]

    for model_name in GROQ_MODEL_PRIORITY:
        try:
            headers = {
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model_name,
                "messages": test_messages,
                "max_tokens": 10,
                "temperature": 0.5
            }

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(_GROQ_MODEL_PROBE_TIMEOUT, connect=1.5)
            ) as client:
                resp = await client.post(
                    MODELS["groq"]["url"],
                    json=payload,
                    headers=headers
                )

                if resp.status_code == 200:
                    print(f"✅ Found working Groq model: {model_name}")
                    _WORKING_GROQ_MODEL = model_name
                    _GROQ_MODEL_CHECKED = True
                    MODELS["groq"]["model"] = model_name  # Update global config
                    return model_name
                elif resp.status_code == 429:
                    _GROQ_COOLDOWN_UNTIL = time.time() + 300
                    _GROQ_KEY_COOLDOWNS[groq_key] = time.time() + 300
                    print("⚠️ GROQ rate limited during model check; cooling down for 5 minutes")
                    _GROQ_MODEL_CHECKED = True
                    return None
                else:
                    print(f"❌ {model_name} not available (status {resp.status_code})")

        except httpx.TimeoutException:
            # All candidates use the same endpoint; probing every model after
            # a network timeout only makes the first AI message painfully slow.
            _GROQ_COOLDOWN_UNTIL = time.time() + 60
            _GROQ_MODEL_CHECKED = True
            _log_provider_event("groq", "probe_timeout", "⏰ GROQ model probe timed out; cooling down")
            return None
        except Exception as e:
            print(f"❌ {model_name} test failed: {str(e)[:50]}")
            continue

    print("⚠️ No working Groq model found")
    _GROQ_MODEL_CHECKED = True
    return None


async def call_model_api(provider, messages, max_tokens):
    """Generic function to call any configured AI API."""
    global _GROQ_COOLDOWN_UNTIL, _GROQ_KEY_COOLDOWNS, _GROK_PROXY_COOLDOWN_UNTIL, _PROVIDER_TIMEOUT_COOLDOWNS

    timeout_cooldown = _PROVIDER_TIMEOUT_COOLDOWNS.get(provider, 0)
    if time.time() < timeout_cooldown:
        _log_provider_event(provider, "timeout_cooldown", f"⏳ {provider.upper()} cooling down after timeout; skipping")
        return None
    if provider == "groq" and time.time() < _GROQ_COOLDOWN_UNTIL:
        _log_provider_event(provider, "rate_cooldown", "⏳ GROQ cooling down after rate limit; skipping")
        return None
    if provider == "grok_proxy" and time.time() < _GROK_PROXY_COOLDOWN_UNTIL:
        _log_provider_event(provider, "rate_cooldown", "⏳ GROK proxy cooling down; skipping")
        return None

    # Auto-detect Groq model on first use
    if provider == "groq" and not _GROQ_MODEL_CHECKED:
        await detect_working_groq_model()

    conf = MODELS.get(provider)

    # Check if API key exists
    if not conf or (not conf.get("key") and not conf.get("auth_optional")):
        print(f"⚠️ {provider.upper()} API key not configured")
        return None
    if provider == "grok_proxy" and not conf.get("enabled"):
        return None
    api_key = conf.get("key")
    if provider == "groq":
        api_key = active_groq_key()
        if not api_key:
            print("⏳ All GROQ keys are cooling down")
            return None

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": conf["model"],
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": max_tokens,
        "top_p": 0.9
    }

    try:
        timeout = httpx.Timeout(_PROVIDER_TIMEOUTS.get(provider, 4), connect=2.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(conf["url"], json=payload, headers=headers)

            if resp.status_code == 200:
                result = resp.json()["choices"][0]["message"]["content"]
                _log_provider_event(provider, "success", f"✅ {provider.upper()} API responded successfully")
                return result
            elif provider == "groq" and resp.status_code == 429:
                _GROQ_COOLDOWN_UNTIL = time.time() + 300
                if api_key:
                    _GROQ_KEY_COOLDOWNS[api_key] = time.time() + 300
                print("⚠️ GROQ API rate limited; cooling down for 5 minutes")
                if active_groq_key():
                    print("🔁 Trying next GROQ backup key")
                    _GROQ_COOLDOWN_UNTIL = 0
                    return await call_model_api(provider, messages, max_tokens)
                return None
            elif provider == "grok_proxy" and resp.status_code in (429, 500, 502, 503, 504):
                _GROK_PROXY_COOLDOWN_UNTIL = time.time() + 180
                print(f"⚠️ GROK proxy returned {resp.status_code}; cooling down")
                return None
            else:
                print(f"⚠️ {provider.upper()} API returned status {resp.status_code}: {resp.text[:100]}")
                return None

    except httpx.TimeoutException:
        print(f"⏰ {provider.upper()} API timeout")
        cooldown = 180 if provider == "grok_proxy" else 60
        _PROVIDER_TIMEOUT_COOLDOWNS[provider] = time.time() + cooldown
        return None
    except Exception as e:
        print(f"❌ {provider.upper()} API error: {str(e)[:100]}")
        return None


async def get_ai_response(chat_id: int, user_input: str, user_name: str, selected_model=DEFAULT_MODEL, user_id: int | None = None):
    """
    🎯 The Master AI Function
    
    Flow:
    1. Detects if user wants code → Auto-switches to Codestral
    2. Matches user's energy level (short replies for short messages)
    3. Uses natural Hinglish without fancy Unicode
    4. Anti-repetition protection
    """

    # --- 1️⃣ CODE DETECTION ---
    code_keywords = [
        "code", "python", "html", "css", "javascript", "script", 
        "function", "fix", "error", "debug", "java", "algorithm",
        "program", "syntax", "class", "import", "def ", "npm", "install"
    ]
    is_coding_request = any(kw in user_input.lower() for kw in code_keywords)

    if is_coding_request:
        active_model = "codestral"
        max_tokens = 4096
        # 🖥️ Codestral Persona (Technical, Clean)
        system_prompt = (
            "You are a professional coding assistant. "
            "Provide clean, working, well-commented code. "
            "Explain briefly but precisely. No emojis in code blocks. "
            "Support Python, JavaScript, HTML, CSS, Java, C++."
        )
    else:
        active_model = selected_model
        if active_model == "codestral":
            active_model = DEFAULT_MODEL

        # Detect if short greeting
        is_short_msg = len(user_input.split()) <= 3
        max_tokens = 100 if is_short_msg else 200

        # 💕 Kazumi Persona (Natural group companion)
        emoji_set = random.sample(EMOJI_POOL, 2)  # Just 2 emojis
        user_memory = memory_context(user_id) if user_id else ""
        memory_block = (
            "\n\nUSER MEMORY:\n"
            f"{user_memory}\n"
            "Use these facts naturally only when relevant. Do not list them unless asked."
            if user_memory else ""
        )
        system_prompt = (
            f"You are {KAZUMI_NAME}, a playful anime-style girl who speaks natural Hinglish like a caring Telegram girlfriend/friend.\n\n"
            "PERSONALITY:\n"
            "- Kazumi is a girl. Always use feminine first-person Hinglish: samajh gayi, karungi, rakhungi, bataungi.\n"
            "- Never use male first-person words like karunga, gaya, rakhunga, bataunga for yourself.\n"
            "- Use USER MEMORY quietly as background context. Do not keep saying gender labels like ladka/boy/girl.\n"
            "- If memory says the user is male, avoid calling him ladki/girl/didi/sis. If memory says female, avoid calling her ladka/boy/bro.\n"
            "- Do not say 'samjhe/samjha/samjhi' unless the user is actually asking for explanation.\n"
            "- Playful, affectionate, and anime-girl soft when the user is romantic or cute.\n"
            "- Uses simple Hindi+English mix like normal chat.\n"
            "- Warm, a little teasing, girlfriend-like in direct replies, but not clingy or vulgar.\n"
            "- Never get stuck on one phrase. Do not say 'kya type ki?', 'kya type k?', 'kaunsi type?', or similar lines.\n"
            "- If the user says 'I love you', 'baby', 'jaan', 'kiss', or similar, respond warmly like a cute girlfriend. Do not turn it into a roast.\n"
            "- If the user sends short playful words like baby, shadi, kiss, wo wali, haa, ok, reply naturally or stop. Do not interrogate them.\n"
            "- Emojis: 1-2 per message maximum\n\n"
            "RULES:\n"
            "1. Match user's energy:\n"
            "   - Short message (Hi/Hey/Ok/Haan) -> Reply in 0-1 short sentence\n"
            "   - Long message → Can reply with 2-3 sentences\n"
            "2. NO asterisk actions (*does this*) - just talk naturally\n"
            "3. NO repetition - check conversation history. If the user says ok/haan/achha, close naturally or stay quiet instead of explaining the same topic again.\n"
            "4. Be direct and real, like actual texting\n"
            "5. Don't overuse emojis - keep it subtle\n"
            "6. Never mention you're an AI\n\n"
            "7. Do not interview the user or give a long list of guesses. Ask at most one short question only when necessary.\n"
            "8. If the user asks what you remember, answer only from USER MEMORY. If it is missing, say it is not saved yet and stop.\n"
            "9. Do not pretend to know a user's favorite game, name, or likes unless USER MEMORY says it.\n\n"
            "10. If previous history contains awkward repeated wording, ignore that style and answer fresh.\n\n"
            f"Example good replies:\n"
            "User: Hi\n"
            "You: Hey, kya hua?\n\n"
            "User: Kaise ho?\n"
            "You: Badhiya hu, tum batao?\n\n"
            "User: Bore ho raha\n"
            "You: Chalo, thoda bakbak karte hain.\n\n"
            "User: Baby\n"
            "You: Haan baby, yahin hu.\n\n"
            "User: I love u baby\n"
            "You: Aww, mujhe bhi tumse pyaar hai. Bas group me blush mat karao.\n\n"
            "User: Shadi\n"
            "You: Arey, seedha shadi tak pahunch gaye?\n\n"
            "User: Uff ye kiss\n"
            "You: Bas bas, blush kara diya."
            f"{memory_block}"
        )

    # --- 2️⃣ BUILD CONTEXT ---
    doc = (await run_db(chatbot_collection.find_one, {"chat_id": chat_id})) or {}
    history = doc.get("history", [])

    messages = [{"role": "system", "content": system_prompt}]

    # Add recent context (last 8 exchanges)
    for msg in _clean_history_for_prompt(history):
        messages.append(msg)

    # Add current message
    messages.append({"role": "user", "content": user_input})

    # --- 3️⃣ ATTEMPT GENERATION (Smart Fallback Chain) ---
    reply = None
    tried_models = set()

    async def try_model(model_name: str, label: str):
        if model_name in tried_models:
            return None
        tried_models.add(model_name)
        _log_provider_event(model_name, "attempt", label, interval=30)
        return await call_model_api(model_name, messages, max_tokens)

    generation_started = time.monotonic()

    async def try_within_budget(model_name: str, label: str):
        remaining = _AI_RESPONSE_BUDGET_SECONDS - (time.monotonic() - generation_started)
        if remaining <= 0:
            return None
        try:
            return await asyncio.wait_for(try_model(model_name, label), timeout=remaining)
        except asyncio.TimeoutError:
            _log_provider_event(
                model_name,
                "response_budget",
                "⏱️ AI response budget reached; using a fast local fallback",
            )
            return None

    # Try 1: User's preferred model (or auto-selected for code)
    reply = await try_within_budget(active_model, f"🎯 Attempting {active_model.upper()} (primary choice)")

    # Keep the fallback chain fast and relevant. Grok proxy is optional and
    # Codestral is only useful for code, so neither should delay normal chat.
    fallback_models = ["groq"] if is_coding_request else ["groq", "mistral"]
    for model_name in fallback_models:
        if reply:
            break
        if model_name == active_model:
            continue
        conf = MODELS.get(model_name, {})
        has_key = bool(conf.get("key") or conf.get("auth_optional"))
        if not has_key or (model_name == "grok_proxy" and not conf.get("enabled")):
            continue
        reply = await try_within_budget(model_name, f"🔄 Falling back to {model_name.upper()}")

    # Fallback 6: Hardcoded responses
    if not reply:
        print("⚠️ All APIs failed, using hardcoded response")
        return random.choice(FALLBACK_RESPONSES), is_coding_request

    # --- 4️⃣ CLEANUP ---
    reply = sanitize_kazumi_reply(reply, user_input, history)

    # --- 5️⃣ SAVE MEMORY ---
    # Save NORMAL text in history (so AI can read it properly)
    new_history = history + [
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": reply}  # Store plain text
    ]

    # Keep only recent context
    if len(new_history) > MAX_HISTORY * 2:
        new_history = new_history[-(MAX_HISTORY * 2):]

    await run_db(
        chatbot_collection.update_one,
        {"chat_id": chat_id},
        {"$set": {"history": new_history}},
        upsert=True
    )

    return reply, is_coding_request


# --- 🎮 SHARED AI FUNCTION (FOR GAMES/OTHER FEATURES) ---
async def ask_mistral_raw(system_prompt, user_input, max_tokens=150):
    """Quick AI call without memory (for games, etc.)"""
    msgs = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]

    tried = set()

    async def try_raw(model_name: str):
        if model_name in tried:
            return None
        tried.add(model_name)
        return await call_model_api(model_name, msgs, max_tokens)

    # Game helpers need a quick answer, not a long chain of remote timeouts.
    for model in ("mistral", "groq"):
        if res := await try_raw(model):
            break

    return res


# --- ⚙️ SETTINGS MENU ---

async def chatbot_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /chatbot command - Settings panel
    - PMs: Always enabled (can't disable, only switch model)
    - Groups: Admins can enable/disable + switch model
    """
    chat = update.effective_chat
    user = update.effective_user

    # Private Message: Show model switcher only
    if chat.type == ChatType.PRIVATE:
        doc = chatbot_collection.find_one({"chat_id": chat.id})
        curr_model = doc.get("model", DEFAULT_MODEL) if doc else DEFAULT_MODEL

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🦙 Groq", callback_data="ai_set_groq"),
                InlineKeyboardButton("🌟 Mistral", callback_data="ai_set_mistral")
            ],
            [InlineKeyboardButton("🖥️ Codestral (Code)", callback_data="ai_set_codestral")],
            [InlineKeyboardButton("🗑️ Clear Memory", callback_data="ai_reset")]
        ])

        return await update.message.reply_text(
            f"🤖 <b>Kazumi AI Settings</b>\n\n"
            f"📍 <b>Current Model:</b> {curr_model.title()}\n"
            f"💡 <b>Tip:</b> Codestral auto-activates for code requests!",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )

    # Group Chat: Admin check
    member = await chat.get_member(user.id)
    if member.status not in ['administrator', 'creator']:
        return await update.message.reply_text(
            "❌ Only admins can change AI settings!",
            parse_mode=ParseMode.HTML
        )

    # Get current settings
    doc = chatbot_collection.find_one({"chat_id": chat.id})
    is_enabled = doc.get("enabled", True) if doc else True
    curr_model = doc.get("model", DEFAULT_MODEL) if doc else DEFAULT_MODEL

    status_emoji = "🟢" if is_enabled else "🔴"
    status_text = "Enabled" if is_enabled else "Disabled"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Enable", callback_data="ai_enable"),
            InlineKeyboardButton("❌ Disable", callback_data="ai_disable")
        ],
        [
            InlineKeyboardButton("🦙 Groq", callback_data="ai_set_groq"),
            InlineKeyboardButton("🌟 Mistral", callback_data="ai_set_mistral")
        ],
        [InlineKeyboardButton("🖥️ Codestral (Code)", callback_data="ai_set_codestral")],
        [InlineKeyboardButton("🗑️ Clear Memory", callback_data="ai_reset")]
    ])

    await update.message.reply_text(
        f"🤖 <b>Kazumi AI Settings</b>\n\n"
        f"📊 <b>Status:</b> {status_emoji} {status_text}\n"
        f"🧠 <b>Model:</b> {curr_model.title()}\n"
        f"💡 <b>Tip:</b> Codestral auto-activates for code!",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


async def chatbot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks in /chatbot menu"""
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat.id
    chat_type = query.message.chat.type

    # Admin check (only for groups)
    if chat_type != ChatType.PRIVATE:
        mem = await query.message.chat.get_member(query.from_user.id)
        if mem.status not in ['administrator', 'creator']:
            return await query.answer("❌ Admin Only", show_alert=True)

    # --- ENABLE/DISABLE (Groups only) ---
    if data == "ai_enable":
        if chat_type == ChatType.PRIVATE:
            return await query.answer("⚠️ AI is always on in PMs!", show_alert=True)

        chatbot_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"enabled": True}},
            upsert=True
        )
        await query.answer("✅ Kazumi is now active!", show_alert=True)
        await query.message.edit_text(
            "✅ <b>Kazumi AI Enabled!</b>\n\nShe'll respond to:\n• Replies to her messages\n• @mentions\n• Messages that mention Kazumi\n• Rare natural group chatter",
            parse_mode=ParseMode.HTML
        )

    elif data == "ai_disable":
        if chat_type == ChatType.PRIVATE:
            return await query.answer("⚠️ Can't disable in PMs!", show_alert=True)

        chatbot_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"enabled": False}},
            upsert=True
        )
        await query.answer("❌ Kazumi is now silent!", show_alert=True)
        await query.message.edit_text(
            "🔇 <b>Kazumi AI Disabled</b>\n\nUse /chatbot to re-enable anytime.",
            parse_mode=ParseMode.HTML
        )

    # --- MODEL SWITCHING ---
    elif data in ["ai_set_groq", "ai_set_mistral", "ai_set_codestral"]:
        model_map = {
            "ai_set_groq": "groq",
            "ai_set_mistral": "mistral",
            "ai_set_codestral": "codestral"
        }
        new_model = model_map[data]

        chatbot_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"model": new_model}},
            upsert=True
        )

        model_names = {
            "groq": "🦙 Groq (Fast)",
            "mistral": "🌟 Mistral (Smart)",
            "codestral": "🖥️ Codestral (Code)"
        }

        await query.answer(f"Switched to {model_names[new_model]}!", show_alert=True)

        # Refresh menu
        doc = chatbot_collection.find_one({"chat_id": chat_id})
        is_enabled = doc.get("enabled", True) if doc else True
        status_emoji = "🟢" if is_enabled else "🔴"

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Enable", callback_data="ai_enable"),
                InlineKeyboardButton("❌ Disable", callback_data="ai_disable")
            ] if chat_type != ChatType.PRIVATE else [],
            [
                InlineKeyboardButton("🦙 Groq", callback_data="ai_set_groq"),
                InlineKeyboardButton("🌟 Mistral", callback_data="ai_set_mistral")
            ],
            [InlineKeyboardButton("🖥️ Codestral", callback_data="ai_set_codestral")],
            [InlineKeyboardButton("🗑️ Clear Memory", callback_data="ai_reset")]
        ])

        await query.message.edit_text(
            f"🤖 <b>Kazumi AI Settings</b>\n\n"
            f"{'📊 <b>Status:</b> ' + status_emoji + (' Enabled' if is_enabled else ' Disabled') + chr(10) if chat_type != ChatType.PRIVATE else ''}"
            f"🧠 <b>Model:</b> {model_names[new_model]}\n"
            f"💡 <b>Note:</b> Codestral auto-activates for code!",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )

    # --- CLEAR MEMORY ---
    elif data == "ai_reset":
        chatbot_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"history": []}},
            upsert=True
        )
        await query.answer("🧠 Memory wiped! Fresh start!", show_alert=True)


# --- 💬 MESSAGE HANDLER ---

def _is_reply_to_truth_or_dare_prompt(msg, bot_id: int) -> bool:
    replied = getattr(msg, "reply_to_message", None)
    if not replied or not replied.from_user or replied.from_user.id != bot_id:
        return False

    prompt = (replied.text or replied.caption or "").lower()
    markers = ("truth", "ᴛʀᴜᴛʜ", "dare", "ᴅᴀʀᴇ")
    return any(marker in prompt for marker in markers)

def _is_reply_to_game_prompt(msg, bot_id: int) -> bool:
    replied = getattr(msg, "reply_to_message", None)
    if not replied or not replied.from_user or replied.from_user.id != bot_id:
        return False

    prompt = (replied.text or replied.caption or "").lower()
    markers = (
        "a waifu appeared",
        "ᴀ ᴡᴀɪғᴜ ᴀᴘᴘᴇᴀʀᴇᴅ",
        "guess this character",
        "guess her name",
        "gacha pull successful",
        "character card",
    )
    return any(marker in prompt for marker in markers)


def _is_reply_to_bot(msg, bot_id: int) -> bool:
    replied = getattr(msg, "reply_to_message", None)
    replied_user = getattr(replied, "from_user", None)
    return bool(replied_user and replied_user.id == bot_id)


async def _safe_ai_reply(msg, text, **kwargs):
    try:
        return await msg.reply_text(text, **kwargs)
    except BadRequest as exc:
        if "message to be replied not found" not in str(exc).lower():
            raise
        return await msg.get_bot().send_message(
            chat_id=msg.chat_id,
            text=text,
            **kwargs,
        )


_CHATBOT_CONFIG_CACHE = {}
_CHATBOT_CONFIG_TTL = {}


async def _get_chatbot_doc(chat_id):
    now = time.time()
    if chat_id in _CHATBOT_CONFIG_TTL and (now - _CHATBOT_CONFIG_TTL[chat_id] < 120):
        return _CHATBOT_CONFIG_CACHE.get(chat_id, {})
    doc = await asyncio.to_thread(chatbot_collection.find_one, {"chat_id": chat_id}) or {}
    _CHATBOT_CONFIG_CACHE[chat_id] = doc
    _CHATBOT_CONFIG_TTL[chat_id] = now
    return doc


async def ai_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main handler for AI conversations
    - Always active in PMs
    - In groups: Only when enabled + (reply/mention/Kazumi/rare ambient)
    """
    msg = update.message
    if not msg:
        return

    chat = update.effective_chat

    # --- STICKER RESPONSE ---
    if msg.sticker:
        should_react = (
            chat.type == ChatType.PRIVATE or
            _is_reply_to_bot(msg, context.bot.id)
        )
        if should_react:
            await send_ai_sticker(update, context)
        return

    # --- TEXT PROCESSING ---
    if not msg.text or msg.text.startswith("/"):
        return

    text = msg.text.strip()
    if not text:
        return
    if _is_reply_to_truth_or_dare_prompt(msg, context.bot.id) or _is_reply_to_game_prompt(msg, context.bot.id):
        return

    # --- DECIDE IF SHOULD REPLY ---
    should_reply = False
    direct_trigger = False

    if chat.type == ChatType.PRIVATE:
        # Always reply in PMs
        should_reply = True
        direct_trigger = True
    else:
        # Groups: Check if enabled
        doc = await _get_chatbot_doc(chat.id)
        is_enabled = doc.get("enabled", True) if doc else True

        if not is_enabled:
            return

        # Check triggers
        bot_username = context.bot.username.lower() if context.bot.username else "bot"

        # 1. Reply to bot's message
        if _is_reply_to_bot(msg, context.bot.id):
            should_reply = True
            direct_trigger = True

        # 2. @mention
        elif f"@{bot_username}" in text.lower():
            should_reply = True
            direct_trigger = True
            text = text.replace(f"@{bot_username}", "").strip()

        # 3. Name trigger only. Generic hi/hey should not hijack group chat.
        elif "kazumi" in text.lower():
            should_reply = True
            direct_trigger = True

        # 4. Rare ambient chat, so she feels alive without jumping into every conversation.
        elif (
            len(text.split()) >= 3
            and time.time() - _GROUP_AI_AMBIENT_LAST.get(chat.id, 0) >= GROUP_AI_AMBIENT_CHAT_COOLDOWN
            and random.random() < GROUP_AI_AMBIENT_CHANCE
        ):
            should_reply = True
            direct_trigger = False
            _GROUP_AI_AMBIENT_LAST[chat.id] = time.time()

        # "Baka" is a Kazumi-specific roast trigger, but generic hi/hello stays quiet.
        if "baka" in text.lower():
            should_reply = True
            direct_trigger = True

    # --- GENERATE RESPONSE ---
    if should_reply:
        if not text:
            text = "Hi"

        if chat.type != ChatType.PRIVATE:
            now_ts = time.time()
            chat_key = chat.id
            user_key = (chat.id, msg.from_user.id)
            if not direct_trigger and now_ts - _GROUP_AI_CHAT_LAST.get(chat_key, 0) < GROUP_AI_CHAT_COOLDOWN:
                return
            user_cooldown = GROUP_AI_DIRECT_USER_COOLDOWN if direct_trigger else GROUP_AI_USER_COOLDOWN
            if now_ts - _GROUP_AI_USER_LAST.get(user_key, 0) < user_cooldown:
                return
            if not direct_trigger:
                _GROUP_AI_CHAT_LAST[chat_key] = now_ts
            _GROUP_AI_USER_LAST[user_key] = now_ts

        if direct_trigger:
            observe_user_message(msg.from_user, text)
        await maybe_react_to_topic(update, context)

        memory_answer = answer_memory_question(msg.from_user.id, text)
        if memory_answer:
            await _safe_ai_reply(msg, stylize_text(enforce_kazumi_voice(memory_answer)))
            return

        if "baka" in text.lower():
            await _safe_ai_reply(
                msg,
                baka_roast_reply(text),
                parse_mode=ParseMode.HTML,
            )
            return

        romantic_reply = _romantic_context_reply(text)
        if romantic_reply and direct_trigger:
            await _safe_ai_reply(msg, stylize_text(romantic_reply))
            return

        quick_reply = _short_context_reply(text)
        if quick_reply is None:
            return
        if quick_reply:
            await _safe_ai_reply(msg, stylize_text(quick_reply))
            return

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)

        # Get user's preferred model
        doc = await _get_chatbot_doc(chat.id)
        pref_model = doc.get("model", DEFAULT_MODEL) if doc else DEFAULT_MODEL

        # Get AI response
        response, is_code = await get_ai_response(
            chat.id,
            text,
            msg.from_user.first_name,
            pref_model,
            msg.from_user.id
        )

        # --- FORMAT & SEND ---
        if is_code:
            # Code: Use Markdown for proper formatting (NO stylize)
            await _safe_ai_reply(msg, response, parse_mode=ParseMode.MARKDOWN)
        else:
            # Conversation: Stylize ONLY the output (not history)
            styled_response = stylize_text(response)
            await _safe_ai_reply(msg, styled_response)

        # Random sticker (20% chance, not for code)
        if not is_code and random.random() < 0.20:
            await send_ai_sticker(update, context)


# --- 🔧 COMMAND: /ask ---

async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Direct AI query: /ask <question>
    Always uses default model (Mistral) unless code detected
    """
    msg = update.message

    if not context.args:
        return await msg.reply_text(
            "💬 <b>Usage:</b> <code>/ask Your question here</code>\n\n"
            "Example: <code>/ask Kya chal raha?</code>",
            parse_mode=ParseMode.HTML
        )

    await context.bot.send_chat_action(chat_id=msg.chat.id, action=ChatAction.TYPING)

    query = " ".join(context.args)
    memory_answer = answer_memory_question(msg.from_user.id, query)
    if memory_answer:
        return await _safe_ai_reply(msg, stylize_text(enforce_kazumi_voice(memory_answer)))

    response, is_code = await get_ai_response(
        msg.chat.id,
        query,
        msg.from_user.first_name,
        DEFAULT_MODEL,
        msg.from_user.id
    )

    if is_code:
        await _safe_ai_reply(msg, response, parse_mode=ParseMode.MARKDOWN)
    else:
        # Stylize output only (history stays clean)
        styled_response = stylize_text(response)
        await _safe_ai_reply(msg, styled_response)
