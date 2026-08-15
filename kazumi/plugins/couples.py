import random
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatType
from kazumi.utils import ensure_user_exists, get_mention, stylize_text, pick_rotating_media
from kazumi.database import users_collection, couples_collection
from kazumi.config import COUPLE_GIFS, COUPLE_PHOTOS

async def couples_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Picks 1 random 'Couple' for the group (Changes every time)."""
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ Group Only!", parse_mode=ParseMode.HTML)

    # Pick 1 new couple every time
    try:
        # We need 2 unique users
        pipeline = [
            {"$match": {"seen_groups": chat.id}},
            {"$sample": {"size": 2}}
        ]
        results = list(users_collection.aggregate(pipeline))
        
        if len(results) < 2:
            return await update.message.reply_text("😔 Not enough members seen in this group!", parse_mode=ParseMode.HTML)
        
        p1, p2 = results[0], results[1]
            
    except Exception as e:
        print(f"Couples Error: {e}")
        return

    # Prepare caption
    caption = (
        f"❤️ <b>{stylize_text('COUPLE MATCHMAKING')}</b> ❤️\n\n"
        f"💞 {get_mention(p1)}  💖  {get_mention(p2)}\n\n"
        f"Love Is In The Air ❤️\n\n"
        f"<i>~ From Kazumi With Love 💋</i>"
    )
    
    # Randomize media choice
    media_pool = COUPLE_GIFS + COUPLE_PHOTOS
    choice = pick_rotating_media(f"couple:{chat.id}", media_pool)
    
    try:
        if choice in COUPLE_PHOTOS:
            await update.message.reply_photo(photo=choice, caption=caption, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_animation(animation=choice, caption=caption, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Media Error: {e}")
        await update.message.reply_text(caption, parse_mode=ParseMode.HTML)

def get_progress_bar(percent):
    filled = int(percent / 10)
    bar = "❤️" * filled + "🖤" * (10 - filled)
    return bar

def get_ship_comment(percent):
    if percent < 10: return "💀 Run away!"
    if percent < 30: return "💔 No chemistry."
    if percent < 50: return "😐 Just friends."
    if percent < 70: return "👀 Something's there..."
    if percent < 90: return "💖 Cute couple!"
    return "🔥 Perfect Match!"

async def ship_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deterministic random love calculator."""
    from kazumi.utils import resolve_target
    
    chat = update.effective_chat
    user = update.effective_user
    
    user1_doc = ensure_user_exists(user)
    
    target, error = await resolve_target(update, context)
    if not target:
        return await update.message.reply_text(error or "Usage: /ship @user", parse_mode=ParseMode.HTML)
    
    if target['user_id'] == user.id:
        return await update.message.reply_text("🤦 Self love is great, but try shipping with someone else!")

    # Deterministic percentage based on IDs
    # This ensures the percentage is same for the same pair today
    today = datetime.utcnow().strftime("%Y-%m-%d")
    seed_str = f"{min(user.id, target['user_id'])}_{max(user.id, target['user_id'])}_{today}"
    random.seed(seed_str)
    percent = random.randint(0, 100)
    random.seed() # Reset seed

    bar = get_progress_bar(percent)
    comment = get_ship_comment(percent)
    
    await update.message.reply_text(
        f"🚢 <b>{stylize_text('SHIPPING')}</b>\n\n"
        f"👩‍❤️‍👨 {get_mention(user1_doc)} + {get_mention(target)}\n\n"
        f"💘 <b>Love Score:</b> {percent}%\n"
        f"<code>{bar}</code>\n"
        f"💭 {comment}",
        parse_mode=ParseMode.HTML
    )
