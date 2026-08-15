import random
import asyncio
import uuid
from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.utils import ensure_user_exists, get_mention, format_money, stylize_text, pick_rotating_media
from kazumi.database import users_collection
from kazumi.config import KISS_GIFS
from kazumi.game_rules import FARM_GAME_DAILY_CAP, capped_daily_payout, validate_bet
from kazumi.game_timeouts import refund_locked_bet
from kazumi.ledger import adjust_user_balance, positive_credit_total_today

TRUTHS = [
    "Last time when u were bullied and why so?", 
    "What is your biggest fear?", 
    "Who is your secret crush?", 
    "Have you ever lied to your best friend?", 
    "What is your most embarrassing moment?",
    "What is the most childish thing you still do?"
]

DARES = [
    "Send the first 3 apps on your home screen.", 
    "Send a voice note saying 'Kazumi is the boss'.", 
    "Change your profile picture to a monkey for 10 minutes.", 
    "Text your crush and say 'I love you'.", 
    "Send your recent emoji history."
]

PUZZLES = [
    {"q": "Sab mujhe dekh sakte h, par main khud ko nahi dekh sakta. Kaun hu main?", "a": "aaina"}, 
    {"q": "Ek room mein 4 kone hain, har kone mein 1 billi baithi hai. Har billi ke samne 3 billiyan hain. Room mein total kitni billiyan hain?", "a": "4"},
    {"q": "Aisi kaun si cheez hai jise aage se bhagwan ne banaya hai aur piche se insaan ne?", "a": "bailgadi"},
    {"q": "Wo kya hai jo saal mein 1 baar aata hai, mahine mein 2 baar, hafte mein 4 baar aur din mein 6 baar aata hai?", "a": "odd numbers"}
]

async def truth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"💬 <b>{stylize_text('Truth')}</b>\n━━━━━━━━━━━━\n\n{random.choice(TRUTHS)}", parse_mode=ParseMode.HTML)

async def dare_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔥 <b>{stylize_text('Dare')}</b>\n━━━━━━━━━━━━\n\n{random.choice(DARES)}", parse_mode=ParseMode.HTML)

async def crush_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("👀 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴄʜᴇᴄᴋ ᴛʜᴇɪʀ ᴄʀᴜsʜ.", parse_mode=ParseMode.HTML)
    target = update.message.reply_to_message.from_user
    crushes = ["Anime", "No one 😭", "Themselves 🗿", "Money 💰", "Food 🍕", "Gojo Satoru", "Sleeping"]
    await update.message.reply_text(f"😍 {target.first_name}'s crush is: <b>{random.choice(crushes)}</b>", parse_mode=ParseMode.HTML)

async def love_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("❤️ ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ!", parse_mode=ParseMode.HTML)
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    pct = random.randint(0, 100)
    msg = f"❤️ <b>{stylize_text('Love Calculator')}</b>\n━━━━━━━━━━━━\n\n{user.first_name} & {target.first_name}\nLᴏᴠᴇ Pᴇʀᴄᴇɴᴛᴀɢᴇ: <b>{pct}%</b>"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def look_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("👀 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ.", parse_mode=ParseMode.HTML)
    target = update.message.reply_to_message.from_user
    looks = ["Gorgeous ✨", "Ugly AF 👹", "Average 😐", "Model Tier 👑", "Cute 🥺", "Needs a paper bag 🛍️"]
    await update.message.reply_text(f"👀 {target.first_name} ʟᴏᴏᴋs ʟɪᴋᴇ: <b>{random.choice(looks)}</b>", parse_mode=ParseMode.HTML)

async def brain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("🧠 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ.", parse_mode=ParseMode.HTML)
    target = update.message.reply_to_message.from_user
    brains = ["Einstein 🧠⚡", "Empty 🥥", "Monkey Brain 🐒", "Big Brain 🌌", "Peanut 🥜"]
    await update.message.reply_text(f"🧠 {target.first_name}'s ʙʀᴀɪɴ sɪᴢᴇ: <b>{random.choice(brains)}</b>", parse_mode=ParseMode.HTML)

async def stupid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("🤪 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ.", parse_mode=ParseMode.HTML)
    target = update.message.reply_to_message.from_user
    pct = random.randint(0, 100)
    await update.message.reply_text(f"🤪 {target.first_name} ɪs <b>{pct}% sᴛᴜᴘɪᴅ</b>!", parse_mode=ParseMode.HTML)

# Text-based actions (Can be upgraded to GIFs later)
async def murder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("🔪 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ ᴛᴏ ᴍᴜʀᴅᴇʀ ᴛʜᴇᴍ!", parse_mode=ParseMode.HTML)
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    await update.message.reply_text(f"🔪 {get_mention(user)} <b>ᴍᴜʀᴅᴇʀᴇᴅ</b> <a href='tg://user?id={target.id}'>{target.first_name}</a>! 🩸", parse_mode=ParseMode.HTML)

async def bite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("🧛 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ!", parse_mode=ParseMode.HTML)
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    await update.message.reply_text(f"🧛 {get_mention(user)} <b>ʙɪᴛ</b> <a href='tg://user?id={target.id}'>{target.first_name}</a>! 🩸", parse_mode=ParseMode.HTML)

async def kiss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("😘 ʀᴇᴘʟʏ ᴛᴏ sᴏᴍᴇᴏɴᴇ!", parse_mode=ParseMode.HTML)
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    caption = f"😘 {get_mention(user)} <b>ᴋɪssᴇᴅ</b> <a href='tg://user?id={target.id}'>{target.first_name}</a>! 💋"
    try:
        await update.message.reply_animation(
            animation=pick_rotating_media("action:kiss", KISS_GIFS),
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        print(f"Kiss GIF Error: {exc}", flush=True)
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)

# Group Info Commands
async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ ɢʀᴏᴜᴘ ᴏɴʟʏ!", parse_mode=ParseMode.HTML)
    try:
        admins = await update.effective_chat.get_administrators()
        owner = next((admin for admin in admins if admin.status == "creator"), None)
        if owner:
            await update.message.reply_text(f"👑 <b>ɢʀᴏᴜᴘ ᴏᴡɴᴇʀ:</b> {get_mention(owner.user)}", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("👑 ᴏᴡɴᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ (ᴍɪɢʜᴛ ʙᴇ ᴀɴᴏɴʏᴍᴏᴜs).", parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text("❌ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ʀɪɢʜᴛs ᴛᴏ ᴄʜᴇᴄᴋ.", parse_mode=ParseMode.HTML)

async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ ɢʀᴏᴜᴘ ᴏɴʟʏ!", parse_mode=ParseMode.HTML)
    try:
        admins = await update.effective_chat.get_administrators()
        msg = f"🛡️ <b>{stylize_text('Admins')}</b>\n━━━━━━━━━━━━\n\n"
        for i, admin in enumerate(admins, 1):
            msg += f"• {get_mention(admin.user)}\n"
        msg += f"\n👥 ᴛᴏᴛᴀʟ: {len(admins)}"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except:
        await update.message.reply_text("❌ ɴᴇᴇᴅ ᴀᴅᴍɪɴ ʀɪɢʜᴛs ᴛᴏ ᴄʜᴇᴄᴋ.", parse_mode=ParseMode.HTML)

# Minigames
active_puzzles = {}
active_words = {}
WORDGAME_MIN_BET = 100
WORDGAME_MAX_BET = 500_000
WORDGAME_TTL_SECONDS = 90
FARM_LIMIT_CATEGORIES = ("wordgame_win", "wordbomb_win", "heist_success")


async def expire_wordgame(context, chat_id, token):
    await asyncio.sleep(WORDGAME_TTL_SECONDS)
    game = active_words.get(chat_id)
    if not game or game.get("token") != token:
        return
    active_words.pop(chat_id, None)
    result = refund_locked_bet(
        game["starter"],
        game["bet"],
        idle=True,
        adjust_user_balance=adjust_user_balance,
        chat_id=chat_id,
        source="/wordgame timeout",
        meta={"token": token},
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"⏳ <b>{stylize_text('Word Game Expired')}</b>\n"
            f"Answer: <code>{game['word'].upper()}</code>\n"
            f"Refunded: <code>{format_money(result['refund'])}</code> | "
            f"Idle fee: <code>{format_money(result['fee'])}</code>"
        ),
        parse_mode=ParseMode.HTML,
    )

async def puzzle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.id in active_puzzles:
        return await update.message.reply_text("⚠️ ᴀ ᴘᴜᴢᴢʟᴇ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!", parse_mode=ParseMode.HTML)
    
    p = random.choice(PUZZLES)
    active_puzzles[chat.id] = p['a']
    
    await update.message.reply_text(f"🧠 <b>{stylize_text('Puzzle')}</b>\n━━━━━━━━━━━━\n\n{p['q']}\n\n<i>ʀᴇᴘʟʏ ᴡɪᴛʜ ᴛʜᴇ ᴀɴsᴡᴇʀ! (Reward: 500)</i>", parse_mode=ParseMode.HTML)

WORDS = ["anime", "manga", "otaku", "naruto", "goku", "luffy", "sakura", "bleach", "pokemon"]

async def wordgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE: return await update.message.reply_text("❌ ɢʀᴏᴜᴘ ᴏɴʟʏ!")
    
    if not context.args:
        return await update.message.reply_text("⚠️ <code>/wordgame [bet]</code>", parse_mode=ParseMode.HTML)
    
    try: bet = int(context.args[0])
    except: return await update.message.reply_text("⚠️ ɪɴᴠᴀʟɪᴅ ʙᴇᴛ.")
    
    user = ensure_user_exists(update.effective_user)
    bet_error = validate_bet(
        bet,
        balance=user.get("balance", 0),
        minimum=WORDGAME_MIN_BET,
        maximum=WORDGAME_MAX_BET,
    )
    if bet_error:
        return await update.message.reply_text(
            f"⚠️ {bet_error}\n<code>/wordgame {WORDGAME_MIN_BET}</code>",
            parse_mode=ParseMode.HTML,
        )
    
    if chat.id in active_words:
        return await update.message.reply_text("⚠️ ᴀ ɢᴀᴍᴇ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴄᴛɪᴠᴇ!")

    earned_today = positive_credit_total_today(user["user_id"], categories=FARM_LIMIT_CATEGORIES)
    max_prize = capped_daily_payout(bet * 2, earned_today, FARM_GAME_DAILY_CAP)
    if max_prize < bet * 2:
        return await update.message.reply_text(
            "⚠️ <b>Daily game earn limit reached.</b>\n"
            f"Limit: <code>{format_money(FARM_GAME_DAILY_CAP)}</code> per day for Wordgame, Word Bomb and Heist.",
            parse_mode=ParseMode.HTML,
        )
    
    word = random.choice(WORDS)
    scrambled = list(word)
    random.shuffle(scrambled)
    scrambled_word = "".join(scrambled)
    
    token = uuid.uuid4().hex
    charged = adjust_user_balance(
        user["user_id"],
        -bet,
        "wordgame_bet",
        "Started word game",
        chat_id=chat.id,
        source="/wordgame",
        require_gte=bet,
        meta={"token": token},
    )
    if not charged:
        return await update.message.reply_text("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴs!")
    active_words[chat.id] = {
        "word": word,
        "bet": bet,
        "starter": user["user_id"],
        "token": token,
    }

    try:
        await update.message.reply_text(
            f"📝 <b>{stylize_text('Word Game')}</b>\n━━━━━━━━━━━━\n\n"
            f"🔀 Uɴsᴄʀᴀᴍʙʟᴇ: <b>{scrambled_word.upper()}</b>\n"
            f"💰 Pʀɪᴢᴇ: <code>{format_money(bet * 2)}</code>\n\n"
            f"<i>Tʏᴘᴇ ᴛʜᴇ ᴄᴏʀʀᴇᴄᴛ ᴡᴏʀᴅ ᴛᴏ ᴡɪɴ!</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        active_words.pop(chat.id, None)
        refund_locked_bet(
            user["user_id"],
            bet,
            adjust_user_balance=adjust_user_balance,
            chat_id=chat.id,
            source="/wordgame send failure",
            meta={"token": token},
        )
        raise
    context.application.create_task(expire_wordgame(context, chat.id, token))

async def check_minigames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat = update.effective_chat
    text = update.message.text.strip().lower()
    user = update.effective_user
    replied = update.message.reply_to_message
    replied_to_kazumi = bool(replied and replied.from_user and replied.from_user.id == context.bot.id)
    
    # Check puzzle
    if chat.id in active_puzzles:
        if text == active_puzzles[chat.id].lower():
            del active_puzzles[chat.id]
            users_collection.update_one({"user_id": user.id}, {"$inc": {"balance": 500}})
            await update.message.reply_text(f"🎉 {get_mention(user)} <b>sᴏʟᴠᴇᴅ ᴛʜᴇ ᴘᴜᴢᴢʟᴇ!</b> +500 ᴄᴏɪɴs", parse_mode=ParseMode.HTML)
            raise ApplicationHandlerStop
        if replied_to_kazumi:
            raise ApplicationHandlerStop

    # Check wordgame
    if chat.id in active_words:
        game = active_words.get(chat.id)
        if not game:
            return
        if text == game['word']:
            claimed = active_words.pop(chat.id, None)
            if not claimed or claimed.get("token") != game.get("token"):
                return
            earned_today = positive_credit_total_today(user.id, categories=FARM_LIMIT_CATEGORIES)
            prize = capped_daily_payout(game['bet'] * 2, earned_today, FARM_GAME_DAILY_CAP)
            if prize <= 0:
                await update.message.reply_text(
                    f"🎉 {get_mention(user)} <b>ᴜɴsᴄʀᴀᴍʙʟᴇᴅ ɪᴛ!</b>\n"
                    "⚠️ Daily game earn limit reached, no extra coins added.",
                    parse_mode=ParseMode.HTML,
                )
                raise ApplicationHandlerStop
            ensure_user_exists(user)
            adjust_user_balance(
                user.id,
                prize,
                "wordgame_win",
                "Won word game",
                chat_id=chat.id,
                source="/wordgame",
                extra_inc={"game_wins": 1},
                meta={"starter": game["starter"], "bet": game["bet"]},
            )
            await update.message.reply_text(f"🎉 {get_mention(user)} <b>ᴜɴsᴄʀᴀᴍʙʟᴇᴅ ɪᴛ!</b> +<code>{format_money(prize)}</code>", parse_mode=ParseMode.HTML)
            raise ApplicationHandlerStop
        if replied_to_kazumi:
            raise ApplicationHandlerStop
