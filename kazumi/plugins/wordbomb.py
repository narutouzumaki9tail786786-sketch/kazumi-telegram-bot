import asyncio
import html
import random
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.utils import ensure_user_exists, format_money, get_mention, stylize_text, add_xp
from kazumi.database import users_collection
from kazumi.config import XP_PER_GAME_WIN
from kazumi.game_rules import FARM_GAME_DAILY_CAP, capped_daily_payout, safe_turn_index
from kazumi.ledger import adjust_user_balance, positive_credit_total_today

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 💣 WORD BOMB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

active_wb = {}  # { chat_id: { game_id, players, player_names, current_idx, syllable, status, timer_task } }

TURN_TIME = 12  # seconds per turn
JOIN_TIME = 30  # seconds to join lobby
FARM_LIMIT_CATEGORIES = ("wordgame_win", "wordbomb_win", "heist_success")

# Common syllables to avoid unfair ones
SYLLABLES = [
    "AN", "IN", "ON", "EN", "AT", "IT", "OR", "AR", "ER", "ANG",
    "ING", "ONG", "ENG", "AND", "END", "OLD", "ALL", "OWN", "OUR",
    "ACK", "ICK", "OCK", "ATE", "ITE", "OOT", "OOL", "OOM", "EEL",
    "EAT", "OAT", "AIL", "AIN", "OAD", "ARE", "EAR", "AIR", "OOR",
    "SH", "CH", "ST", "TR", "PR", "BL", "FL", "GR", "CR", "DR",
    "UN", "RE", "PRE", "OUT", "UP", "OVER", "UNDER", "MAN", "HAND",
    "HEAD", "LAND", "SIDE", "LINE", "LIGHT", "LONG", "RING", "KING",
    "TION", "NESS", "MENT", "LESS", "IGHT", "OUND", "ANCE", "ENCE"
]

DICTIONARY_SAMPLE = set([
    "ANGER", "GANG", "HANG", "SANG", "RANG", "BANG", "FANG", "CLANG",
    "SLANG", "PANG", "TANG", "MANGO", "ANGLE", "ANKLE", "TANGLE",
    "MANGLE", "DANGER", "RANGER", "STRANGER", "CHANGE", "ARRANGE",
    "SING", "RING", "KING", "WING", "STING", "BRING", "SPRING",
    "STRING", "THING", "SWING", "CLING", "FLING", "SLING", "WRING",
    "EATING", "BEATING", "HEATING", "SEATING", "MEETING", "GREETING",
    "START", "STAR", "STARE", "STARING", "STARK", "STARTLE",
    "TRAIN", "TRAIL", "TRAIT", "TRAITOR", "TRAINING", "TRAINER",
    "PRAYER", "PLAYER", "PLAYING", "REPLAY", "DISPLAY", "SPLAY",
    "FRIEND", "BLEND", "BLENDER", "BLEND", "BLESS", "BLESSING",
    "FLUTTER", "FLAT", "FLATTER", "FLATTERY", "FLASH", "FLASHY",
    "GREAT", "GREET", "GREEN", "GREED", "GREEK", "GRAIN", "GRAPE",
    "CRAFT", "CRAVE", "CRAWL", "CRASH", "CRAZY", "CRANK", "CRANE",
    "DRINK", "DRIVE", "DRIVER", "DRIVEN", "DROWN", "DRONE", "DROP",
    "UNDER", "UNDERSTAND", "UNDERTAKE", "UNDERMINE", "UNDERLINE",
    "UNDO", "UNIFY", "UNITE", "UNLIKE", "UNLESS", "UNTIL", "UNTO",
    "REMAIN", "REMARK", "REMIND", "REMOVE", "RENEW", "REPAY",
    "OUTRUN", "OUTDO", "OUTDOOR", "OUTSIDE", "OUTLAW", "OUTPUT",
    "OVERCOME", "OVERFLOW", "OVERLOOK", "OVERRUN", "OVERSIGHT",
    "MANKIND", "MANHOLE", "MANAGE", "MANUAL", "MANNER", "MAGIC",
    "HANDLE", "HANDMADE", "HANDFUL", "HANDY", "HANDBAG", "HANDSOME",
    "HEADACHE", "HEADBAND", "HEADLIGHT", "HEADLINE", "HEADMASTER",
    "LANDLORD", "LANDMARK", "LANDSLIDE", "LANDFILL", "LANDSCAPE",
    "SIDEWALK", "SIDELINE", "SIDEBOARD", "SIDEBAR", "SIDEKICK",
    "RINGMASTER", "RINGWORM", "RINGTONE", "RINGLEADER",
    "KINGDOM", "KINGSIZED", "KINGPIN", "KINGFISHER",
    "NATION", "MENTION", "MOTION", "PORTION", "STATION", "CAUTION",
    "KINDNESS", "DARKNESS", "SADNESS", "MADNESS", "GLADNESS",
    "MOMENT", "MOVEMENT", "PAYMENT", "TREATMENT", "STATEMENT",
    "CARELESS", "ENDLESS", "FEARLESS", "HOPELESS", "HOMELESS",
    "BRIGHT", "FLIGHT", "SLIGHT", "BLIGHT", "PLIGHT", "KNIGHT",
    "GROUND", "SOUND", "FOUND", "WOUND", "HOUND", "BOUND", "ROUND",
    "DISTANCE", "INSTANCE", "SUBSTANCE", "ENTRANCE", "BALANCE",
    "SCIENCE", "PATIENCE", "SILENCE", "VIOLENCE", "SENTENCE",
])

def syllable_in_word(syllable, word):
    return syllable.upper() in word.upper()

def wb_player_mention(game, user_id):
    name = game.get("player_names", {}).get(user_id, "Player")
    return f"<a href='tg://user?id={int(user_id)}'>{html.escape(name)}</a>"

async def wordbomb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a Word Bomb lobby."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ This game is Group only!", parse_mode=ParseMode.HTML)

    if chat.id in active_wb:
        game = active_wb[chat.id]
        if game['status'] == 'lobby':
            return await update.message.reply_text(
                f"⚠️ A Word Bomb lobby is already active! Join it with:\n<code>/wb_join</code>",
                parse_mode=ParseMode.HTML
            )
        return await update.message.reply_text("⚠️ A Word Bomb game is already running!", parse_mode=ParseMode.HTML)

    ensure_user_exists(user)
    game_id = str(uuid.uuid4())[:8]
    active_wb[chat.id] = {
        "game_id": game_id,
        "players": [user.id],
        "player_names": {user.id: user.first_name},
        "current_idx": 0,
        "syllable": None,
        "status": "lobby",
        "timer_task": None,
        "alive": [user.id],
        "chat_id": chat.id
    }

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💣 Join Game!", callback_data=f"wb_join|{game_id}")],
        [InlineKeyboardButton("▶️ Start Now", callback_data=f"wb_start|{game_id}")]
    ])

    await update.message.reply_text(
        f"💣 <b>{stylize_text('WORD BOMB')}</b> 💣\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🎮 {get_mention(user)} started a game!\n"
        f"👥 Players: <b>1</b> (Need 2-6)\n\n"
        f"<b>How to Play:</b>\n"
        f"🔹 Bot gives a syllable (e.g., <b>ANG</b>)\n"
        f"🔹 Type a word containing it in <b>12 seconds!</b>\n"
        f"🔹 Fail → 💥 Bomb explodes → You're OUT!\n"
        f"🔹 Last one standing wins!\n\n"
        f"<i>Click Join or type /wbjoin to join! ({JOIN_TIME}s)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    # Auto-start after JOIN_TIME if enough players
    await asyncio.sleep(JOIN_TIME)
    game = active_wb.get(chat.id)
    if game and game['status'] == 'lobby' and game['game_id'] == game_id:
        if len(game['players']) < 2:
            del active_wb[chat.id]
            await context.bot.send_message(chat.id, "💣 Word Bomb lobby expired. Not enough players!", parse_mode=ParseMode.HTML)
        else:
            await start_wordbomb_round(context.bot, chat.id)

async def wbjoin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Join an active Word Bomb lobby."""
    chat = update.effective_chat
    user = update.effective_user

    game = active_wb.get(chat.id)
    if not game or game['status'] != 'lobby':
        return await update.message.reply_text("❌ No active lobby! Start one with <code>/wordbomb</code>", parse_mode=ParseMode.HTML)

    if user.id in game['players']:
        return await update.message.reply_text("⚠️ You're already in the lobby!", parse_mode=ParseMode.HTML)

    if len(game['players']) >= 6:
        return await update.message.reply_text("❌ Lobby is full! Max <code>6</code> players.", parse_mode=ParseMode.HTML)

    ensure_user_exists(user)
    game['players'].append(user.id)
    game['alive'].append(user.id)
    game['player_names'][user.id] = user.first_name

    player_list = "\n".join([f"• {wb_player_mention(game, p)}" for p in game['players']])
    await update.message.reply_text(
        f"✅ {get_mention(user)} joined the Word Bomb!\n\n"
        f"👥 <b>Players ({len(game['players'])}):</b>\n{player_list}\n\n"
        f"<i>Waiting for more... or click ▶️ Start Now!</i>",
        parse_mode=ParseMode.HTML
    )

async def wb_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle lobby join/start buttons."""
    query = update.callback_query
    user = query.from_user
    data = query.data.split("|")
    action = data[0]
    game_id = data[1]

    chat = query.message.chat
    game = active_wb.get(chat.id)
    if not game or game['game_id'] != game_id:
        return await query.answer("❌ Lobby expired!", show_alert=True)

    if action == "wb_join":
        if user.id in game['players']:
            return await query.answer("⚠️ You're already in!", show_alert=True)
        if len(game['players']) >= 6:
            return await query.answer("❌ Lobby full!", show_alert=True)

        ensure_user_exists(user)
        game['players'].append(user.id)
        game['alive'].append(user.id)
        game['player_names'][user.id] = user.first_name

        player_list = "\n".join([f"• {wb_player_mention(game, p)}" for p in game['players']])
        await query.message.edit_text(
            f"💣 <b>Word Bomb Lobby</b>\n\n"
            f"👥 <b>Players ({len(game['players'])}/6):</b>\n{player_list}\n\n"
            f"<i>Click Join or wait for auto-start!</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=query.message.reply_markup
        )
        return await query.answer(f"✅ Joined! ({len(game['players'])} players)")

    if action == "wb_start":
        if user.id != game['players'][0]:
            return await query.answer("❌ Only the host can start!", show_alert=True)
        if len(game['players']) < 2:
            return await query.answer("❌ Need at least 2 players!", show_alert=True)

        await query.answer("▶️ Starting!")
        await start_wordbomb_round(context.bot, chat.id)

async def start_wordbomb_round(bot, chat_id):
    """Starts/continues a word bomb round."""
    game = active_wb.get(chat_id)
    if not game: return
    turn_index = safe_turn_index(game.get("alive", []), game.get("current_idx", 0))
    if turn_index is None:
        await check_wordbomb_winner(bot, chat_id, game)
        return

    game['status'] = 'playing'
    game['current_idx'] = turn_index
    current_player_id = game['alive'][game['current_idx']]
    player_name = wb_player_mention(game, current_player_id)
    syllable = random.choice(SYLLABLES)
    game['syllable'] = syllable
    round_token = uuid.uuid4().hex
    game["round_token"] = round_token

    alive_names = " | ".join([wb_player_mention(game, p) for p in game['alive']])

    await bot.send_message(
        chat_id,
        f"💣 <b>WORD BOMB!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Alive:</b> {alive_names}\n\n"
        f"💥 <b>{player_name}'s Turn!</b>\n"
        f"📝 Syllable: <b><code>{syllable}</code></b>\n\n"
        f"<i>Type a word containing '<b>{syllable}</b>' in {TURN_TIME}s!</i>",
        parse_mode=ParseMode.HTML
    )

    # Start countdown
    if game.get('timer_task'):
        game['timer_task'].cancel()

    async def timeout_player():
        await asyncio.sleep(TURN_TIME)
        g = active_wb.get(chat_id)
        if (
            not g
            or g.get('status') != 'playing'
            or g.get('round_token') != round_token
            or g.get('syllable') != syllable
        ):
            return  # Round already moved on

        # Player timed out — eliminate
        timeout_index = safe_turn_index(g.get("alive", []), g.get("current_idx", 0))
        if timeout_index is None or g["alive"][timeout_index] != current_player_id:
            return
        eliminated_id = g['alive'][timeout_index]
        eliminated_name = wb_player_mention(g, eliminated_id)
        g['alive'].remove(eliminated_id)
        g["round_token"] = None

        await bot.send_message(
            chat_id,
            f"💥 <b>BOOM!</b> {eliminated_name} ran out of time!\n"
            f"<b>{eliminated_name}</b> is OUT! 💀",
            parse_mode=ParseMode.HTML
        )
        await check_wordbomb_winner(bot, chat_id, g)

    game['timer_task'] = asyncio.create_task(timeout_player())

async def check_word_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Listen for word answers in group chats."""
    chat = update.effective_chat
    game = active_wb.get(chat.id)
    if not game or game['status'] != 'playing': return
    if not update.message or not update.message.text: return

    user = update.effective_user
    turn_index = safe_turn_index(game.get("alive", []), game.get("current_idx", 0))
    if turn_index is None:
        await check_wordbomb_winner(context.bot, chat.id, game)
        return
    current_player_id = game['alive'][turn_index]
    round_token = game.get("round_token")

    # Only current player's answer matters
    if user.id != current_player_id: return

    word = update.message.text.strip().upper()
    if not word.isalpha():
        replied = update.message.reply_to_message
        if replied and replied.from_user and replied.from_user.id == context.bot.id:
            raise ApplicationHandlerStop
        return

    syllable = game['syllable']

    if not syllable_in_word(syllable, word):
        await update.message.reply_text(
            f"❌ <b>{html.escape(word)}</b> doesn't contain <b>{html.escape(syllable)}</b>. Try again!",
            parse_mode=ParseMode.HTML
        )
        raise ApplicationHandlerStop

    # Word is valid!
    if game.get("round_token") != round_token or game.get("status") != "playing":
        return
    game["status"] = "transition"
    game["round_token"] = None
    if game.get('timer_task'):
        game['timer_task'].cancel()

    await update.message.reply_text(
        f"✅ <b>{html.escape(word)}</b> — Good word! 🎉",
        parse_mode=ParseMode.HTML
    )

    # Move to next player
    next_index = safe_turn_index(game.get("alive", []), turn_index + 1)
    if next_index is None:
        await check_wordbomb_winner(context.bot, chat.id, game)
        raise ApplicationHandlerStop
    game['current_idx'] = next_index
    await asyncio.sleep(1.5)
    await start_wordbomb_round(context.bot, chat.id)
    raise ApplicationHandlerStop

async def check_wordbomb_winner(bot, chat_id, game):
    """Check if there's a winner."""
    if len(game['alive']) <= 1:
        game['status'] = 'finished'

        if game['alive']:
            winner_id = game['alive'][0]
            winner_name = wb_player_mention(game, winner_id)
            raw_reward = min(12_000, 2000 * len(game['players']))  # Scale reward with a hard cap
            earned_today = positive_credit_total_today(winner_id, categories=FARM_LIMIT_CATEGORIES)
            reward = capped_daily_payout(raw_reward, earned_today, FARM_GAME_DAILY_CAP)

            if reward > 0:
                adjust_user_balance(
                    winner_id,
                    reward,
                    "wordbomb_win",
                    "Won Word Bomb",
                    chat_id=chat_id,
                    source="/wordbomb",
                    extra_inc={"game_wins": 1},
                    meta={"players": len(game["players"]), "raw_reward": raw_reward},
                )
            else:
                users_collection.update_one({"user_id": winner_id}, {"$inc": {"game_wins": 1}})
            await add_xp(winner_id, XP_PER_GAME_WIN * 2)

            cap_note = "" if reward == raw_reward else "\n⚠️ Daily game earn cap applied."
            await bot.send_message(
                chat_id,
                f"🏆 <b>WORD BOMB — WINNER!</b>\n\n"
                f"💣 <b>{winner_name}</b> is the last one standing!\n"
                f"💰 Won: <code>{format_money(reward)}</code>{cap_note}",
                parse_mode=ParseMode.HTML
            )
        else:
            await bot.send_message(chat_id, "💥 Everyone exploded! No winner!", parse_mode=ParseMode.HTML)

        del active_wb[chat_id]
    else:
        await start_wordbomb_round(bot, chat_id)
