import asyncio
import random
import time
from datetime import datetime, timedelta

from pymongo.errors import DuplicateKeyError
from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ApplicationHandlerStop, ContextTypes

from kazumi.database import (
    karma_collection,
    karma_votes_collection,
    trivia_sessions_collection,
    groups_collection,
    users_collection,
)
from kazumi.ledger import adjust_user_balance
from kazumi.missions import track_mission
from kazumi.utils import add_xp, ensure_user_exists, format_display_text, format_money, format_time, get_mention, resolve_target, stylize_text


WEEKLY_REWARD = 15000
WEEKLY_PREMIUM_REWARD = 25000
TRIVIA_REWARD = 750
TRIVIA_TTL_SECONDS = 90
BET_MIN = 100
BET_MAX = 500_000
DICE_MIN_BET = 100
DICE_MAX_BET = 500_000
BET_COOLDOWN = 20
DICE_COOLDOWN = 10
KARMA_COOLDOWN_HOURS = 6

_BET_LAST = {}
_DICE_LAST = {}

TRIVIA_QUESTIONS = [
    {
        "q": "What planet is known as the Red Planet?",
        "a": ["mars"],
    },
    {
        "q": "How many days are in a leap year?",
        "a": ["366", "three hundred sixty six"],
    },
    {
        "q": "What is the capital of Japan?",
        "a": ["tokyo"],
    },
    {
        "q": "Which gas do plants absorb from the air?",
        "a": ["carbon dioxide", "co2"],
    },
    {
        "q": "What is 9 x 8?",
        "a": ["72", "seventy two"],
    },
    {
        "q": "Which ocean is the largest?",
        "a": ["pacific", "pacific ocean"],
    },
    {
        "q": "What language is primarily used with React?",
        "a": ["javascript", "typescript", "js", "ts"],
    },
    {
        "q": "How many squares are on a chess board?",
        "a": ["64", "sixty four"],
    },
]
TRIVIA_RECENT_LIMIT = max(1, len(TRIVIA_QUESTIONS) - 1)


def _now():
    return datetime.utcnow()


def _parse_amount(value, user_balance=0, max_bet=BET_MAX):
    from kazumi.utils import parse_money
    parsed = parse_money(value)
    if parsed == "all":
        return min(int(user_balance or 0), int(max_bet))
    if isinstance(parsed, int):
        return parsed
    return None


def _cooldown_left(store, key, seconds):
    current = time.time()
    last = store.get(key, 0)
    left = int(seconds - (current - last))
    if left > 0:
        return left
    store[key] = current
    return 0


def _normalize_answer(text):
    return " ".join(str(text or "").strip().lower().split())


def _trivia_question_key(question):
    return _normalize_answer(question.get("q", ""))


def _select_trivia_question(recent_question_keys):
    """Pick a question the chat has not seen in its current rotation."""
    recent = {str(key) for key in (recent_question_keys or [])}
    choices = [
        question for question in TRIVIA_QUESTIONS
        if _trivia_question_key(question) not in recent
    ]
    return random.choice(choices or TRIVIA_QUESTIONS)


def _is_reply_to_kazumi(message, context):
    replied = getattr(message, "reply_to_message", None)
    if not replied or not replied.from_user:
        return False
    return replied.from_user.id == context.bot.id


async def weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = ensure_user_exists(update.effective_user)
    now = _now()
    last = user.get("last_weekly")
    if last and (now - last) < timedelta(days=7):
        left = timedelta(days=7) - (now - last)
        return await message.reply_text(
            f"\U000023F3 <b>Weekly cooldown.</b> Wait <code>{format_time(left)}</code>.",
            parse_mode=ParseMode.HTML,
        )

    reward = WEEKLY_PREMIUM_REWARD if user.get("is_premium") else WEEKLY_REWARD
    cutoff = now - timedelta(days=7)
    claimed = adjust_user_balance(
        user["user_id"],
        reward,
        "weekly",
        "Claimed weekly reward",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/weekly",
        extra_query={
            "$or": [{"last_weekly": {"$exists": False}}, {"last_weekly": None}, {"last_weekly": {"$lte": cutoff}}],
        },
        extra_set={"last_weekly": now},
        extra_inc={"weekly_claims": 1, "xp": 80},
    )
    if not claimed:
        return await message.reply_text("\U000023F3 <b>Weekly was already claimed.</b>", parse_mode=ParseMode.HTML)
    await message.reply_text(
        f"\U0001F4C6 <b>{stylize_text('Weekly Reward')}</b>\n"
        f"Received: <code>{format_money(reward)}</code>",
        parse_mode=ParseMode.HTML,
    )


async def trivia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await message.reply_text("\U0000274C <b>Trivia is group only.</b>", parse_mode=ParseMode.HTML)

    now = _now()
    active = await asyncio.to_thread(trivia_sessions_collection.find_one, {"chat_id": chat.id, "expires_at": {"$gt": now}})
    if active:
        return await message.reply_text("\U000026A0\ufe0f <b>A trivia question is already active.</b>", parse_mode=ParseMode.HTML)

    group = await asyncio.to_thread(groups_collection.find_one, {"chat_id": chat.id}, {"trivia_recent_questions": 1}) or {}
    question = _select_trivia_question(group.get("trivia_recent_questions"))
    answer = random.choice(question["a"])
    await asyncio.to_thread(
        trivia_sessions_collection.update_one,
        {"chat_id": chat.id},
        {
            "$set": {
                "chat_id": chat.id,
                "question": question["q"],
                "answers": question["a"],
                "answer": answer,
                "reward": TRIVIA_REWARD,
                "created_at": now,
                "expires_at": now + timedelta(seconds=TRIVIA_TTL_SECONDS),
                "started_by": update.effective_user.id,
            }
        },
        upsert=True,
    )
    await asyncio.to_thread(
        groups_collection.update_one,
        {"chat_id": chat.id},
        {
            "$setOnInsert": {"chat_id": chat.id},
            "$push": {
                "trivia_recent_questions": {
                    "$each": [_trivia_question_key(question)],
                    "$slice": -TRIVIA_RECENT_LIMIT,
                }
            },
        },
        upsert=True,
    )
    await message.reply_text(
        f"\U0001F9E0 <b>{stylize_text('Trivia')}</b>\n\n"
        f"{question['q']}\n\n"
        f"\U0001F4B0 Reward: <code>{format_money(TRIVIA_REWARD)}</code>\n"
        f"<i>Type the answer in chat.</i>",
        parse_mode=ParseMode.HTML,
    )


async def trivia_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not message.text or not chat or not user or user.is_bot:
        return
    session = await asyncio.to_thread(trivia_sessions_collection.find_one, {"chat_id": chat.id, "expires_at": {"$gt": _now()}})
    if not session:
        return
    text = _normalize_answer(message.text)
    answers = {_normalize_answer(a) for a in session.get("answers", [])}
    if text not in answers:
        if _is_reply_to_kazumi(message, context):
            raise ApplicationHandlerStop
        return

    await asyncio.to_thread(ensure_user_exists, user)
    deleted = await asyncio.to_thread(trivia_sessions_collection.delete_one, {"_id": session["_id"]})
    if deleted.deleted_count:
        adjust_user_balance(
            user.id,
            int(session.get("reward", TRIVIA_REWARD)),
            "trivia",
            "Answered trivia correctly",
            chat_id=chat.id,
            source="/trivia",
            extra_inc={"game_wins": 1, "xp": 60},
        )
        track_mission(user.id, "play_game")
        await message.reply_text(
            f"\U00002705 <b>Correct!</b> {get_mention(user)} won "
            f"<code>{format_money(int(session.get('reward', TRIVIA_REWARD)))}</code>.",
            parse_mode=ParseMode.HTML,
        )
    raise ApplicationHandlerStop


async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = ensure_user_exists(update.effective_user)
    if not context.args:
        return await message.reply_text(f"\U000026A0\ufe0f <b>Usage:</b> <code>/bet {BET_MIN}</code>", parse_mode=ParseMode.HTML)
    amount = _parse_amount(context.args[0], user.get("balance", 0), BET_MAX)
    if not amount or amount < BET_MIN or amount > BET_MAX:
        return await message.reply_text(
            format_display_text(
                f"⚠️ <b>{stylize_text('Wager Limit')}!</b> Bet range: <code>{format_money(BET_MIN)}</code> - <code>{format_money(BET_MAX)}</code>",
                ParseMode.HTML
            ),
            parse_mode=ParseMode.HTML,
        )
    left = _cooldown_left(_BET_LAST, update.effective_user.id, BET_COOLDOWN)
    if left:
        return await message.reply_text(f"\U000023F3 Wait <code>{left}s</code>.", parse_mode=ParseMode.HTML)

    win = random.random() < 0.47
    delta = amount if win else -amount
    changed = adjust_user_balance(
        user["user_id"],
        delta,
        "bet",
        "Won a bet" if win else "Lost a bet",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/bet",
        require_gte=amount,
        extra_inc={"game_wins": 1 if win else 0},
        meta={"amount": amount, "won": win},
    )
    if not changed:
        return await message.reply_text("\U0001F4C9 Not enough coins.", parse_mode=ParseMode.HTML)
    track_mission(user["user_id"], "play_game")
    result = "\U0001F389 Won" if win else "\U0001F480 Lost"
    await message.reply_text(
        f"\U0001F3B2 <b>{result}</b>\n"
        f"Change: <code>{format_money(delta)}</code>\n"
        f"Balance: <code>{format_money(changed['new_balance'])}</code>",
        parse_mode=ParseMode.HTML,
    )


async def _native_dice(update, context, emoji, label, win_values):
    message = update.effective_message
    user = ensure_user_exists(update.effective_user)
    amount = _parse_amount(context.args[0]) if context.args else None
    if amount is not None and (amount < DICE_MIN_BET or amount > DICE_MAX_BET):
        return await message.reply_text(
            f"\U000026A0\ufe0f Bet range: <code>{format_money(DICE_MIN_BET)}</code> - <code>{format_money(DICE_MAX_BET)}</code>",
            parse_mode=ParseMode.HTML,
        )
    if amount:
        left = _cooldown_left(_DICE_LAST, (update.effective_user.id, emoji), DICE_COOLDOWN)
        if left:
            return await message.reply_text(f"\U000023F3 Wait <code>{left}s</code>.", parse_mode=ParseMode.HTML)
        if user.get("balance", 0) < amount:
            return await message.reply_text("\U0001F4C9 Not enough coins.", parse_mode=ParseMode.HTML)

    dice_msg = await context.bot.send_dice(update.effective_chat.id, emoji=emoji)
    value = dice_msg.dice.value
    await asyncio.sleep(3)

    if not amount:
        return await message.reply_text(
            f"{emoji} <b>{label}</b>\nResult: <code>{value}</code>",
            reply_to_message_id=dice_msg.message_id,
            parse_mode=ParseMode.HTML,
        )

    won = value in win_values
    delta = amount if won else -amount
    changed = adjust_user_balance(
        user["user_id"],
        delta,
        "dice_game",
        f"{label} {'win' if won else 'loss'}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source=f"/{label.lower()}",
        require_gte=amount,
        extra_inc={"game_wins": 1 if won else 0},
        meta={"emoji": emoji, "result": value, "amount": amount, "won": won},
    )
    if not changed:
        return await message.reply_text("\U0001F4C9 Not enough coins.", parse_mode=ParseMode.HTML)
    track_mission(user["user_id"], "play_game")
    outcome_text = "\U00002705 Won" if won else "\U0000274C Lost"
    await message.reply_text(
        f"{emoji} <b>{label}</b> result: <code>{value}</code>\n"
        f"{outcome_text}: <code>{format_money(abs(delta))}</code>",
        reply_to_message_id=dice_msg.message_id,
        parse_mode=ParseMode.HTML,
    )


async def dart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _native_dice(update, context, "\U0001F3AF", "Dart", {5, 6})


async def basket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _native_dice(update, context, "\U0001F3C0", "Basket", {4, 5})


async def bowl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _native_dice(update, context, "\U0001F3B3", "Bowl", {5, 6})


async def _apply_karma(update, target_user, amount):
    message = update.effective_message
    voter = update.effective_user
    chat = update.effective_chat
    if not target_user or target_user.is_bot:
        return "\U000026A0\ufe0f Can not karma that user."
    if voter.id == target_user.id:
        return "\U000026A0\ufe0f Self-karma is not allowed."
    now = _now()
    vote_doc = {
        "chat_id": int(chat.id),
        "voter_id": int(voter.id),
        "target_id": int(target_user.id),
    }
    existing = karma_votes_collection.find_one(vote_doc)
    if existing and existing.get("expires_at") and existing["expires_at"] > now:
        left = existing["expires_at"] - now
        return f"\U000023F3 Karma cooldown: <code>{format_time(left)}</code>."

    ensure_user_exists(target_user)
    vote_doc.update({"value": int(amount), "expires_at": now + timedelta(hours=KARMA_COOLDOWN_HOURS), "created_at": now})
    try:
        karma_votes_collection.replace_one(
            {"chat_id": int(chat.id), "voter_id": int(voter.id), "target_id": int(target_user.id)},
            vote_doc,
            upsert=True,
        )
    except DuplicateKeyError:
        return "\U000023F3 Karma cooldown active."

    updated = karma_collection.find_one_and_update(
        {"chat_id": int(chat.id), "user_id": int(target_user.id)},
        {
            "$inc": {"score": int(amount), "up": 1 if amount > 0 else 0, "down": 1 if amount < 0 else 0},
            "$set": {"name": target_user.first_name, "username": target_user.username.lower() if target_user.username else None},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
        return_document=True,
    )
    users_collection.update_one({"user_id": int(target_user.id)}, {"$inc": {"karma_score": int(amount)}})
    sign = "+" if amount > 0 else ""
    return f"\U0001F31F {get_mention(target_user)} karma {sign}{amount}. Total: <code>{updated.get('score', amount)}</code>"


async def karma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if update.effective_chat.type == ChatType.PRIVATE:
        return await message.reply_text("\U0000274C <b>Karma is group only.</b>", parse_mode=ParseMode.HTML)

    if context.args and context.args[0] in {"+", "++", "-", "--"}:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            return await message.reply_text("\U000026A0\ufe0f Reply to a user with <code>/karma +</code>.", parse_mode=ParseMode.HTML)
        amount = {"+": 1, "++": 2, "-": -1, "--": -2}[context.args[0]]
        text = await _apply_karma(update, message.reply_to_message.from_user, amount)
        return await message.reply_text(text, parse_mode=ParseMode.HTML)

    target_doc = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
        target_doc = ensure_user_exists(target_user)
    elif context.args:
        target_doc, error = await resolve_target(update, context)
        if not target_doc:
            return await message.reply_text(error, parse_mode=ParseMode.HTML)
    else:
        target_doc = ensure_user_exists(update.effective_user)

    row = karma_collection.find_one({"chat_id": int(update.effective_chat.id), "user_id": int(target_doc["user_id"])}) or {}
    await message.reply_text(
        f"\U0001F31F <b>{stylize_text('Karma')}</b>\n"
        f"{get_mention(target_doc)}: <code>{int(row.get('score', 0))}</code>",
        parse_mode=ParseMode.HTML,
    )


async def karma_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text or not update.effective_user or update.effective_user.is_bot:
        return
    if update.effective_chat.type == ChatType.PRIVATE:
        return
    text = message.text.strip()
    if text not in {"+", "++", "-", "--"}:
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return
    amount = {"+": 1, "++": 2, "-": -1, "--": -2}[text]
    reply = await _apply_karma(update, message.reply_to_message.from_user, amount)
    await message.reply_text(reply, parse_mode=ParseMode.HTML)
    raise ApplicationHandlerStop


async def topkarma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if update.effective_chat.type == ChatType.PRIVATE:
        return await message.reply_text("\U0000274C <b>Top karma is group only.</b>", parse_mode=ParseMode.HTML)
    rows = list(karma_collection.find({"chat_id": int(update.effective_chat.id)}).sort("score", -1).limit(10))
    if not rows:
        return await message.reply_text("\U0001F31F No karma yet. Reply with <code>+</code> to start.", parse_mode=ParseMode.HTML)

    lines = [f"\U0001F31F <b>{stylize_text('Top Karma')}</b>\n"]
    for idx, row in enumerate(rows, 1):
        doc = users_collection.find_one({"user_id": int(row["user_id"])}) or {"user_id": row["user_id"], "name": row.get("name", "User")}
        lines.append(f"<code>{idx}.</code> {get_mention(doc)} - <b>{int(row.get('score', 0))}</b>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
