import random
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.ledger import adjust_user_balance
from kazumi.utils import format_display_text, format_money, stylize_text

ACTIVE_BOSS_RAIDS = {}
BOSS_SPAWN_COOLDOWN = {}  # chat_id -> timestamp
USER_ATTACK_COOLDOWN = {}  # (chat_id, user_id) -> timestamp

BOSS_SPAWN_COOLDOWN_SEC = 300  # 5 minutes group spawn cooldown
ATTACK_COOLDOWN_SEC = 4        # 4 seconds per user attack cooldown


async def boss_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        return await update.message.reply_text(
            format_display_text("🏰 <b>Boss Raids can only be spawned in group chats!</b>", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    boss = ACTIVE_BOSS_RAIDS.get(chat.id)
    if boss:
        return await update.message.reply_text(
            format_display_text(
                f"👹 <b>{stylize_text(boss['name'])}</b>\n"
                f"❤️ <b>HP:</b> <code>{max_hp_str(boss)}</code>\n"
                f"⚔️ <b>Attackers:</b> {len(boss['attackers'])}\n\n"
                "Run <code>/attack</code> or tap Attack Boss button below!",
                ParseMode.HTML,
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ ATTACK BOSS", callback_data=f"raid_atk|{chat.id}")]])
        )

    # Check spawn cooldown for chat
    last_spawn = BOSS_SPAWN_COOLDOWN.get(chat.id, 0)
    now = time.time()
    if now - last_spawn < BOSS_SPAWN_COOLDOWN_SEC:
        rem = int(BOSS_SPAWN_COOLDOWN_SEC - (now - last_spawn))
        mins, secs = divmod(rem, 60)
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
        return await update.message.reply_text(
            format_display_text(f"⏳ <b>A World Boss was recently summoned here!</b>\nPlease wait <code>{time_str}</code> before spawning a new World Boss.", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )

    # Spawn new Boss Raid
    max_hp = random.randint(3000, 8000)
    b_name = random.choice(["Inferno Dragon 🐉", "Demon Lord Kazuma 👺", "Shadow Titan 🗿", "Void Empress 👑"])
    prize_pool = random.randint(25000, 75000)

    boss_state = {
        "name": b_name,
        "max_hp": max_hp,
        "hp": max_hp,
        "prize_pool": prize_pool,
        "attackers": {},  # user_id -> total_damage
        "chat_id": chat.id,
    }
    ACTIVE_BOSS_RAIDS[chat.id] = boss_state
    BOSS_SPAWN_COOLDOWN[chat.id] = now

    text = (
        f"🚨 <b>{stylize_text('WORLD BOSS SPAWNED!')}</b> 🚨\n\n"
        f"👹 <b>Boss:</b> {b_name}\n"
        f"❤️ <b>HP:</b> <code>{max_hp}/{max_hp}</code>\n"
        f"💰 <b>Bounty Pool:</b> <code>{format_money(prize_pool)}</code>!\n\n"
        "⚔️ <i>Group members unite! Type /attack or tap Attack below!</i>"
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ ATTACK BOSS", callback_data=f"raid_atk|{chat.id}")]])
    await update.message.reply_text(format_display_text(text, ParseMode.HTML), parse_mode=ParseMode.HTML, reply_markup=markup)


async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    boss = ACTIVE_BOSS_RAIDS.get(chat.id)
    if not boss:
        return await update.message.reply_text(
            format_display_text("❌ No active Boss Raid in this chat! Run /boss to summon one.", ParseMode.HTML),
            parse_mode=ParseMode.HTML,
        )

    key = (chat.id, user.id)
    now = time.time()
    last_atk = USER_ATTACK_COOLDOWN.get(key, 0)
    if now - last_atk < ATTACK_COOLDOWN_SEC:
        rem = round(ATTACK_COOLDOWN_SEC - (now - last_atk), 1)
        return await update.message.reply_text(
            format_display_text(f"⏳ <i>Cooling down! Wait <b>{rem}s</b> before attacking again.</i>", ParseMode.HTML),
            parse_mode=ParseMode.HTML
        )

    USER_ATTACK_COOLDOWN[key] = now
    await perform_attack(context, chat.id, user, update.message, is_callback=False)


async def boss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = (query.data or "").split("|")
    if len(data) != 2 or data[0] != "raid_atk":
        return

    chat_id = int(data[1])
    boss = ACTIVE_BOSS_RAIDS.get(chat_id)
    if not boss:
        return await query.answer("❌ Boss already defeated!", show_alert=True)

    user = query.from_user
    key = (chat_id, user.id)
    now = time.time()
    last_atk = USER_ATTACK_COOLDOWN.get(key, 0)
    if now - last_atk < ATTACK_COOLDOWN_SEC:
        rem = round(ATTACK_COOLDOWN_SEC - (now - last_atk), 1)
        return await query.answer(f"⏳ Wait {rem}s before attacking again!", show_alert=True)

    USER_ATTACK_COOLDOWN[key] = now
    await perform_attack(context, chat_id, user, query.message, is_callback=True, query=query)


async def perform_attack(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, message, is_callback=False, query=None):
    boss = ACTIVE_BOSS_RAIDS.get(chat_id)
    if not boss:
        if query:
            await query.answer("❌ Boss already defeated!", show_alert=True)
        return

    dmg = random.randint(150, 450)
    boss["hp"] -= dmg
    boss["attackers"][user.id] = boss["attackers"].get(user.id, 0) + dmg

    if boss["hp"] <= 0:
        # Defeated!
        ACTIVE_BOSS_RAIDS.pop(chat_id, None)
        total_dmg = sum(boss["attackers"].values())
        prize_pool = boss["prize_pool"]

        rewards_summary = []
        for u_id, u_dmg in boss["attackers"].items():
            share = int((u_dmg / total_dmg) * prize_pool)
            adjust_user_balance(u_id, share, category="raid_reward", reason="Defeated World Boss", chat_id=chat_id)
            rewards_summary.append(f"• User <code>{u_id}</code>: <code>{format_money(share)}</code> ({u_dmg} dmg)")

        victory_text = (
            f"🎉 <b>{stylize_text('BOSS DEFEATED!')}</b>\n\n"
            f"👹 <b>{boss['name']}</b> has fallen!\n"
            f"⚔️ <b>Final Blow:</b> {user.mention_html()} ({dmg} dmg)\n"
            f"💰 <b>Total Bounty Distributed:</b> <code>{format_money(prize_pool)}</code>!\n\n"
            "<b>Top Participants:</b>\n" + "\n".join(rewards_summary[:5])
        )
        if query:
            await query.answer("🎉 CRITICAL HIT! YOU DEFEATED THE BOSS!", show_alert=True)
            try:
                await message.edit_text(format_display_text(victory_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
            except Exception:
                await message.reply_text(format_display_text(victory_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
        else:
            try:
                await message.reply_text(format_display_text(victory_text, ParseMode.HTML), parse_mode=ParseMode.HTML)
            except Exception:
                pass
    else:
        status_text = (
            f"👹 <b>{stylize_text(boss['name'])}</b>\n"
            f"❤️ <b>HP:</b> <code>{max_hp_str(boss)}</code>\n"
            f"⚔️ <b>Last Attack:</b> {user.mention_html()} (<code>{dmg}</code> dmg)\n"
            f"⚔️ <b>Total Attackers:</b> {len(boss['attackers'])}\n\n"
            "Tap Attack Boss button below or type /attack to fight!"
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ ATTACK BOSS", callback_data=f"raid_atk|{chat_id}")]])

        if query:
            await query.answer(f"⚔️ Dealt {dmg} damage!", show_alert=False)
            try:
                await message.edit_text(format_display_text(status_text, ParseMode.HTML), parse_mode=ParseMode.HTML, reply_markup=markup)
            except Exception:
                pass
        else:
            try:
                await message.reply_text(format_display_text(f"⚔️ {user.mention_html()} dealt <code>{dmg}</code> damage!\n❤️ Boss HP: <code>{max_hp_str(boss)}</code>", ParseMode.HTML), parse_mode=ParseMode.HTML)
            except Exception:
                pass


def max_hp_str(boss):
    return f"{max(0, boss['hp'])}/{boss['max_hp']}"

