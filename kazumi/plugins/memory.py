import html
import random
import re
import time
from datetime import datetime

from telegram import ReactionTypeEmoji, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from kazumi.database import user_memories_collection
from kazumi.utils import stylize_text


MAX_FACTS = 25
MAX_VALUE_LEN = 160
REACTION_COOLDOWN = 75
AUTO_MEMORY_KEYS = {"name", "nickname", "gender", "pronouns", "likes", "dislikes"}
_LAST_REACTION = {}

TOPIC_REACTIONS = [
    (("win", "won", "winner", "gg", "op", "pro", "jeet", "tournament"), "\U0001F525"),
    (("love", "janeman", "baby", "crush", "kiss", "marry", "pyaar", "pyar"), "\u2764"),
    (("sad", "cry", "rona", "dukhi", "broken", "miss", "alone"), "\U0001F622"),
    (("haha", "lol", "lmao", "funny", "meme", "haso", "hassi"), "\U0001F923"),
    (("money", "cash", "loan", "coins", "rich", "gareeb", "balance"), "\U0001F4AF"),
    (("code", "python", "error", "bug", "html", "css", "javascript"), "\U0001F468\u200d\U0001F4BB"),
    (("thanks", "thank you", "ty", "shukriya"), "\U0001F64F"),
    (("war", "kill", "gang", "fight", "battle", "raid"), "\U0001F525"),
    (("anime", "waifu", "cute", "kazumi"), "\U0001F970"),
]

ROMAN_HINDI_HINTS = {
    "hai", "kya", "kaise", "mera", "mujhe", "tum", "bhai", "bro", "karna",
    "acha", "theek", "nahi", "haan", "mat", "kyu", "bata", "dekh"
}

GENDER_ALIASES = {
    "boy": "male/boy",
    "ladka": "male/boy",
    "male": "male/boy",
    "man": "male/boy",
    "guy": "male/boy",
    "girl": "female/girl",
    "ladki": "female/girl",
    "female": "female/girl",
    "woman": "female/girl",
}

MEMORY_QUESTION_GROUPS = {
    "name": (
        "mera naam",
        "mera nam",
        "my name",
        "naam kya",
        "naam kia",
        "name kya",
        "name kia",
        "naam bata",
        "naam batao",
        "name bata",
        "name batao",
        "what is my name",
        "whats my name",
        "who am i",
        "main kaun",
        "mai kaun",
        "and mine",
    ),
    "gender": (
        "mera gender",
        "my gender",
        "main ladka",
        "mai ladka",
        "i am boy",
        "am i boy",
        "main ladki",
        "mai ladki",
        "i am girl",
        "am i girl",
    ),
    "game": ("konsa game", "kaunsa game", "favorite game", "favourite game", "game pasand"),
    "likes": ("mujhe kya pasand", "what do i like", "kya pasand"),
    "about": ("mere bare", "mere baare", "about me", "kya yaad", "what do you remember"),
}


def _clip(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip(" .,!?:;-")
    return value[:MAX_VALUE_LEN]


def _today():
    return datetime.utcnow()


def _fact_doc(key, value, source="auto", confidence=0.75):
    return {
        "key": key,
        "value": _clip(value),
        "source": source,
        "confidence": confidence,
        "updated_at": _today(),
        "last_used": _today(),
    }


def _clean_fact_value(key, value):
    value = _clip(value)
    if key in {"name", "nickname"}:
        value = re.split(
            r"\s+(?:hai|he|is|hu|hun|hoon|im|i'm|i\s+am|aur|and|but|lekin|because|kyunki|creator|owner|of|from|babe|baby|jaan|jan|darling)\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
    if key in {"likes", "dislikes"}:
        value = re.split(r"\s+(?:hai|he|but|lekin|because|kyunki)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return _clip(value)


def _is_bad_name_value(value):
    lowered = str(value or "").lower().strip()
    if not lowered:
        return True
    if _looks_like_question(lowered):
        return True
    if len(lowered) > 32:
        return True
    if len(re.findall(r"[a-zA-Z0-9]", lowered)) < 2:
        return True
    blocked_exact = {
        "hai", "he", "h", "hu", "hun", "hoon", "me", "main", "mai",
        "kia h", "kya h", "ky h", "kia hai", "kya hai", "list me",
        "same", "same colour", "babes", "baby", "babe", "bata", "batao",
        "same colour ka h jee",
    }
    if lowered in blocked_exact:
        return True
    blocked_fragments = (
        "naam", "name", "creator", "kazumi", "baka", "bot", "same colour",
        "shameless", "bhul gaya", "pasand", "need a friend", "bata",
        "batao", "yaad", "bol do", "bolo",
    )
    return any(fragment in lowered for fragment in blocked_fragments)


def _normalize_fact_value(key, value):
    value = _clean_fact_value(key, value)
    if key in {"name", "nickname"}:
        value = re.sub(r"[\"'`]+", "", value).strip()
        words = value.split()
        if len(words) > 3:
            value = " ".join(words[:3])
        if _is_bad_name_value(value):
            return ""
    if key == "gender":
        return GENDER_ALIASES.get(value.lower(), value)
    return value


def _is_bad_preference_value(value):
    lowered = str(value or "").lower().strip()
    if not lowered:
        return True
    if _looks_like_question(lowered):
        return True
    blocked_exact = {
        "u", "you", "you baby", "u baby", "baby", "babe", "jaan", "jan",
        "darling", "love", "pyaar", "pyar", "kiss", "muah", "shadi", "shaadi",
        "kazumi", "bot", "reply", "loan", "scene",
    }
    if lowered in blocked_exact:
        return True
    blocked_fragments = (
        "love u", "love you", "i love", "main pyaar", "mai pyaar",
        "tumse pyaar", "tujhse pyaar", "reply", "bol diya",
    )
    return any(fragment in lowered for fragment in blocked_fragments)


def _looks_like_question(text):
    lowered = str(text or "").lower()
    question_words = ("?", "kya", "kia", "kiya", "kaunsa", "konsa", "kon sa", "which", "what", "kaun")
    if any(word in lowered for word in question_words):
        return True
    if re.search(r"\b(?:naam|nam|name)\s+(?:bata|batao|bol|bolo|yaad)\b", lowered):
        return True
    if re.search(r"\b(?:bata|batao|bol|bolo)\b.*\b(?:naam|nam|name)\b", lowered):
        return True
    return False


def _has_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def _load(user_id):
    return user_memories_collection.find_one({"user_id": int(user_id)}) or {"user_id": int(user_id), "facts": []}


def save_memory_fact(user_id, key, value, source="auto", confidence=0.75):
    if source == "auto" and key not in AUTO_MEMORY_KEYS:
        return False
    value = _normalize_fact_value(key, value)
    if not value or len(value) < 2:
        return False
    if source == "auto" and key in {"likes", "dislikes"} and _is_bad_preference_value(value):
        return False

    doc = _load(user_id)
    facts = [fact for fact in doc.get("facts", []) if fact.get("value")]
    replaced = False
    unique_key = key if key in {"name", "nickname", "gender", "pronouns", "language_style"} else f"{key}:{value.lower()}"

    for fact in facts:
        existing_key = fact.get("unique_key") or fact.get("key")
        same_value = str(fact.get("value", "")).lower() == value.lower()
        if existing_key == unique_key or (fact.get("key") == key and same_value):
            fact.update(_fact_doc(key, value, source, confidence))
            fact["unique_key"] = unique_key
            replaced = True
            break

    if not replaced:
        fact = _fact_doc(key, value, source, confidence)
        fact["unique_key"] = unique_key
        facts.append(fact)

    facts = sorted(facts, key=lambda item: item.get("updated_at", datetime.min), reverse=True)[:MAX_FACTS]
    user_memories_collection.update_one(
        {"user_id": int(user_id)},
        {"$set": {"facts": facts, "updated_at": _today()}, "$setOnInsert": {"created_at": _today()}},
        upsert=True,
    )
    return True


def extract_memory_facts(text):
    text = _clip(text)
    if not text or len(text) < 5:
        return []

    lowered = text.lower()
    facts = []
    if _looks_like_question(text):
        return facts

    patterns = [
        ("name", r"(?:\bmera\s+na?am\s*(?:hai|he|is|=|:)?|\bmy\s+name\s+is\b|\bcall\s+me\b|\bmujhe\s+naam\s+se\s+bulao)\s+([^,.!?]{2,40})"),
        ("nickname", r"(?:nickname|nick name|mujhe)\s+([^,.!?]{2,30})\s+(?:bula|bolo|bolna)"),
        ("gender", r"(?:main|mai|me|i am|i'm|im)\s+(?:a\s+)?(boy|ladka|male|man|guy|girl|ladki|female|woman)\b"),
        ("gender", r"(?:mera gender|my gender)\s*(?:is|hai|=|:)?\s*(boy|ladka|male|man|girl|ladki|female|woman)\b"),
        ("pronouns", r"(?:my pronouns|pronouns)\s*(?:are|is|=|:)?\s*([^,.!?]{2,30})"),
        ("likes", r"(?:mujhe|i)\s+(?:like|pasand)\s+([^,.!?]{2,70})"),
        ("likes", r"(?:mujhe|me|mereko)\s+([^,.!?]{2,70}?)\s+(?:pasand|acha lagta|accha lagta|achha lagta)(?:\s+hai|\s+h)?"),
        ("likes", r"(?:my favorite|my favourite|mera favorite|mera favourite|meri favorite|meri favourite)\s+(?:game|cheez|thing)?\s*(?:is|hai|=|:)?\s*([^,.!?]{2,70})"),
        ("likes", r"(?:i play|main khelta hu|main khelti hu|mai khelta hu|mai khelti hu)\s+([^,.!?]{2,70})"),
        ("dislikes", r"(?:mujhe|i)\s+(?:hate|dislike|pasand nahi)\s+([^,.!?]{2,70})"),
        ("dislikes", r"(?:mujhe|me|mereko)\s+([^,.!?]{2,70}?)\s+(?:pasand nahi|acha nahi lagta|accha nahi lagta|achha nahi lagta)(?:\s+hai|\s+h)?"),
    ]
    for key, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _normalize_fact_value(key, match.group(1))
            if value:
                facts.append((key, value, 0.85))

    return facts[:4]


def observe_user_message(user, text):
    if not user or not text or text.startswith("/"):
        return 0
    saved = 0
    for key, value, confidence in extract_memory_facts(text):
        if save_memory_fact(user.id, key, value, "auto", confidence):
            saved += 1
    return saved


def memory_context(user_id, limit=8):
    doc = _load(user_id)
    facts = doc.get("facts", [])[:limit]
    if not facts:
        return ""
    lines = [f"- {fact.get('key')}: {fact.get('value')}" for fact in facts if fact.get("value")]
    return "\n".join(lines)


def public_memory_payload(user_id):
    doc = _load(user_id)
    facts = doc.get("facts", [])[:MAX_FACTS]
    return {
        "count": len(facts),
        "limit": MAX_FACTS,
        "facts": [
            {
                "key": fact.get("key", "note"),
                "value": fact.get("value", ""),
                "source": fact.get("source", "auto"),
            }
            for fact in facts
            if fact.get("value")
        ],
    }


def _facts_by_key(user_id, *keys):
    wanted = set(keys)
    doc = _load(user_id)
    return [fact for fact in doc.get("facts", []) if fact.get("key") in wanted and fact.get("value")]


def answer_memory_question(user_id, text):
    lowered = str(text or "").lower()
    is_question = _looks_like_question(lowered) or any(
        phrase in lowered for phrase in ("yaad hai", "remember", "mere bare", "mere baare", "about me")
    )
    if not is_question:
        return None

    if _has_any(lowered, MEMORY_QUESTION_GROUPS["name"]):
        facts = _facts_by_key(user_id, "name", "nickname")
        if facts:
            return f"Tumhara naam {facts[0]['value']} yaad hai."
        return "Abhi tumhara naam saved nahi hai. Bas bolo: mera naam Abdul hai."

    if _has_any(lowered, MEMORY_QUESTION_GROUPS["gender"]):
        facts = _facts_by_key(user_id, "gender", "pronouns")
        if facts:
            return f"Yaad hai, tum {facts[0]['value']} ho."
        return "Abhi ye saved nahi hai. Chaho to /remember gender male se save kar sakte ho."

    if _has_any(lowered, MEMORY_QUESTION_GROUPS["game"]):
        facts = _facts_by_key(user_id, "likes", "interest")
        game_likes = [
            fact["value"] for fact in facts
            if fact.get("key") == "likes" and any(word in str(fact["value"]).lower() for word in ("game", "ttt", "tic tac toe", "blackjack", "rps", "wordbomb", "taprace", "highlow"))
        ]
        game_interests = [
            fact["value"] for fact in facts
            if any(word in str(fact["value"]).lower() for word in ("game", "ttt", "tic tac toe", "blackjack", "rps", "wordbomb", "taprace", "highlow"))
        ]
        game_values = game_likes or game_interests
        if game_values:
            return f"Haan, tumhe {game_values[0]} pasand hai."
        return "Abhi favorite game saved nahi hai. Clear bol do, main yaad rakh lungi."

    if _has_any(lowered, MEMORY_QUESTION_GROUPS["likes"]):
        facts = _facts_by_key(user_id, "likes", "interest")
        if facts:
            values = ", ".join(fact["value"] for fact in facts[:3])
            return f"Mujhe yaad hai tumhe {values} pasand hai."
        return "Abhi tumhari pasand saved nahi hai. Ek clear line bol do, main yaad rakh lungi."

    if _has_any(lowered, MEMORY_QUESTION_GROUPS["about"]):
        payload = public_memory_payload(user_id)
        facts = payload["facts"][:5]
        if facts:
            lines = [f"{fact['key']}: {fact['value']}" for fact in facts]
            return "Tumhare baare me mujhe ye yaad hai: " + "; ".join(lines)
        return "Abhi tumhare baare me kuch personal saved nahi hai. Main sirf clear useful baatein yaad rakhti hu."

    return None


def forget_user_memory(user_id):
    user_memories_collection.delete_one({"user_id": int(user_id)})


def _parse_manual_fact(args):
    raw = _clip(" ".join(args))
    if not raw:
        return None, None
    if ":" in raw:
        key, value = raw.split(":", 1)
        return _clip(key).lower().replace(" ", "_") or "note", _clip(value)
    if "=" in raw:
        key, value = raw.split("=", 1)
        return _clip(key).lower().replace(" ", "_") or "note", _clip(value)
    parts = raw.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() in {"name", "nickname", "gender", "pronouns", "likes", "dislikes", "style", "note"}:
        key = "language_style" if parts[0].lower() == "style" else parts[0].lower()
        return key, _clip(parts[1])
    return "note", raw


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text(
            "\U0001F9E0 <b>Usage:</b> <code>/remember name Abdul</code>\n"
            "<code>/remember likes anime games</code>\n"
            "<code>/memory</code> shows what Kazumi remembers.\n"
            "<i>Auto-memory only saves clear personal facts now.</i>",
            parse_mode=ParseMode.HTML,
        )
    key, value = _parse_manual_fact(context.args)
    if not value:
        return await update.message.reply_text("\U000026A0\ufe0f Give me something useful to remember.", parse_mode=ParseMode.HTML)
    save_memory_fact(update.effective_user.id, key, value, "manual", 1.0)
    await update.message.reply_text(
        f"\U0001F9E0 <b>Saved:</b> <code>{html.escape(key)}</code> = {html.escape(value)}",
        parse_mode=ParseMode.HTML,
    )


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = public_memory_payload(update.effective_user.id)
    if not payload["facts"]:
        return await update.message.reply_text(
            "\U0001F9E0 <b>Kazumi memory is empty.</b>\nUse <code>/remember name Abdul</code> or say a clear personal fact.",
            parse_mode=ParseMode.HTML,
        )
    rows = [
        f"<code>{idx}.</code> <b>{html.escape(fact['key'])}</b>: {html.escape(fact['value'])}"
        for idx, fact in enumerate(payload["facts"], 1)
    ]
    await update.message.reply_text(
        f"\U0001F9E0 <b>{stylize_text('Kazumi Memory')}</b>\n"
        f"<i>{payload['count']}/{payload['limit']} facts saved. Use /forgetme to clear.</i>\n\n"
        + "\n".join(rows),
        parse_mode=ParseMode.HTML,
    )


async def forgetme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    forget_user_memory(update.effective_user.id)
    await update.message.reply_text("\U0001F9F9 <b>Done.</b> Kazumi forgot your saved personal memory.", parse_mode=ParseMode.HTML)


def detect_topic_reaction(text):
    if not text:
        return None
    lowered = text.lower()
    for keywords, emoji in TOPIC_REACTIONS:
        if any(keyword in lowered for keyword in keywords):
            return emoji
    return None


async def maybe_react_to_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or msg.text.startswith("/"):
        return

    emoji = detect_topic_reaction(msg.text)
    if not emoji:
        return

    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    key = (chat.id, user.id)
    now = time.time()
    if now - _LAST_REACTION.get(key, 0) < REACTION_COOLDOWN:
        return

    chance = 0.28 if chat.type == ChatType.PRIVATE else 0.14
    if random.random() > chance:
        return

    try:
        await context.bot.set_message_reaction(
            chat_id=chat.id,
            message_id=msg.message_id,
            reaction=[ReactionTypeEmoji(emoji)],
            is_big=False,
        )
        _LAST_REACTION[key] = now
    except TelegramError:
        pass
