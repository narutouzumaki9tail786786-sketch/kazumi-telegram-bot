# Kazumi -- Pet System + Dungeon Raids
import random
from datetime import datetime
from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from kazumi.config import XP_PER_GAME_WIN
from kazumi.database import users_collection
from kazumi.utils import add_xp, ensure_user_exists, format_money, get_mention, stylize_text

# ---- Pet System ----
PETS = {
    "dog": {"name": "🐕 ᴅᴏɢ", "cost": 3000, "power": 10},
    "cat": {"name": "🐈 ᴄᴀᴛ", "cost": 3000, "power": 8},
    "wolf": {"name": "🐺 ᴡᴏʟғ", "cost": 8000, "power": 20},
    "eagle": {"name": "🦅 ᴇᴀɢʟᴇ", "cost": 10000, "power": 25},
    "tiger": {"name": "🐯 ᴛɪɢᴇʀ", "cost": 25000, "power": 40},
    "dragon": {"name": "🐉 ᴅʀᴀɢᴏɴ", "cost": 100000, "power": 80},
    "phoenix": {"name": "🔥 ᴘʜᴏᴇɴɪx", "cost": 250000, "power": 120},
}


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return datetime.utcnow()
    return datetime.utcnow()


def _build_pet_record(pid, template, source=None):
    source = source or {}
    return {
        "id": pid,
        "name": source.get("name", template["name"]),
        "power": int(source.get("power", template["power"])),
        "hp": max(0, min(100, int(source.get("hp", 100)))),
        "hunger": max(0, min(100, int(source.get("hunger", 100)))),
        "level": max(1, int(source.get("level", 1))),
        "xp": max(0, int(source.get("xp", 0))),
        "last_fed": _as_datetime(source.get("last_fed")),
    }


def _load_pet_state(user_doc):
    pets = []
    for pet in list(user_doc.get("pets") or []):
        pid = str((pet or {}).get("id") or "").lower()
        if pid in PETS:
            pets.append(_build_pet_record(pid, PETS[pid], pet))

    legacy_pet = user_doc.get("pet")
    if isinstance(legacy_pet, dict):
        pid = str(legacy_pet.get("id") or "").lower()
        if pid in PETS and not any(existing["id"] == pid for existing in pets):
            pets.insert(0, _build_pet_record(pid, PETS[pid], legacy_pet))

    active_pet_id = str(user_doc.get("active_pet_id") or "").lower()
    active_pet = next((pet for pet in pets if pet["id"] == active_pet_id), None)
    if active_pet is None and pets:
        active_pet = pets[0]
        active_pet_id = active_pet["id"]

    return pets, active_pet, active_pet_id


def _save_pet_state(user_id, pets, active_pet_id):
    normalized = []
    for pet in pets:
        pid = str((pet or {}).get("id") or "").lower()
        if pid in PETS:
            normalized.append(_build_pet_record(pid, PETS[pid], pet))

    active_pet = next((pet for pet in normalized if pet["id"] == active_pet_id), None)
    if active_pet is None and normalized:
        active_pet = normalized[0]
        active_pet_id = active_pet["id"]
    elif active_pet is None:
        active_pet_id = None

    users_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "pets": normalized,
                "active_pet_id": active_pet_id,
                "pet": active_pet,
            }
        },
    )
    return active_pet


def _pet_bars(pet):
    last_fed = _as_datetime(pet.get("last_fed"))
    hours = (datetime.utcnow() - last_fed).total_seconds() / 3600
    hunger = max(0, int(pet.get("hunger", 100) - hours * 4))
    hp = max(0, min(100, int(pet.get("hp", 100))))
    hp_bar = "█" * (hp // 10) + "░" * (10 - hp // 10)
    hunger_bar = "█" * (hunger // 10) + "░" * (10 - hunger // 10)
    return hp, hunger, hp_bar, hunger_bar


def _pet_shop_text():
    msg = f"🏠 <b>{stylize_text('Pet Shop')}</b>\n━━━━━━━━━━━━\n\n"
    msg += "ʏᴏᴜ ᴄᴀɴ ᴏᴡɴ ᴍᴜʟᴛɪᴘʟᴇ ᴘᴇᴛs ɴᴏᴡ.\n\n"
    for pid, pet in PETS.items():
        msg += f"<code>/pet adopt {pid}</code> — {pet['name']} ⚡{pet['power']} ({format_money(pet['cost'])})\n"
    return msg


def _pet_overview_text(pets, active_pet):
    hp, hunger, hp_bar, hunger_bar = _pet_bars(active_pet)
    level = active_pet.get("level", 1)
    xp = active_pet.get("xp", 0)

    msg = (
        f"🏠 <b>{stylize_text('Pet Stable')}</b>\n━━━━━━━━━━━━\n\n"
        f"⭐ <b>{stylize_text('Active Pet')}</b>\n"
        f"{active_pet['name']} ʟᴠ.{level}\n\n"
        f"❤️ ʜᴘ: <code>{hp_bar}</code> {hp}%\n"
        f"🍖 ʜᴜɴɢᴇʀ: <code>{hunger_bar}</code> {hunger}%\n"
        f"⚡ ᴘᴏᴡᴇʀ: {active_pet.get('power', 10)}\n"
        f"📈 xᴘ: {xp}/{level * 100}\n\n"
        f"📦 <b>{stylize_text('Owned Pets')}</b>\n"
    )
    for pet in pets:
        marker = "⭐" if pet["id"] == active_pet["id"] else "•"
        msg += f"{marker} <code>{pet['id']}</code> — {pet['name']} ⚡{pet.get('power', 10)}\n"

    msg += (
        "\n"
        "/pet adopt [id] — ʙᴜʏ ɴᴇᴡ ᴘᴇᴛ\n"
        "/pet use [id] — sᴡɪᴛᴄʜ ᴀᴄᴛɪᴠᴇ ᴘᴇᴛ\n"
        "/pet feed — ғᴇᴇᴅ ᴀᴄᴛɪᴠᴇ ᴘᴇᴛ (500)\n"
        "/pet battle @user — ᴘᴇᴛ ғɪɢʜᴛ\n"
        "/pet rename [name] — ʀᴇɴᴀᴍᴇ ᴀᴄᴛɪᴠᴇ ᴘᴇᴛ\n"
        "/pet shop — sᴇᴇ ᴀʟʟ ᴘᴇᴛs"
    )
    return msg


async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = ensure_user_exists(update.effective_user)
    pets, pet, active_pet_id = _load_pet_state(user)

    if not context.args:
        msg = _pet_overview_text(pets, pet) if pet else _pet_shop_text()
        return await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    act = context.args[0].lower()

    if act in {"shop", "list"}:
        base = _pet_shop_text()
        if pet:
            base += f"\n⭐ ᴀᴄᴛɪᴠᴇ: {pet['name']} (<code>{active_pet_id}</code>)"
        return await update.message.reply_text(base, parse_mode=ParseMode.HTML)

    if act == "adopt":
        if len(context.args) < 2:
            return await update.message.reply_text("❌ ᴜsᴇ: <code>/pet adopt dog</code>", parse_mode=ParseMode.HTML)

        pid = context.args[1].lower()
        if pid not in PETS:
            return await update.message.reply_text("❌ ɪɴᴠᴀʟɪᴅ ᴘᴇᴛ!", parse_mode=ParseMode.HTML)
        if any(existing["id"] == pid for existing in pets):
            return await update.message.reply_text("⚠️ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴏᴡɴ ᴛʜɪs ᴘᴇᴛ!", parse_mode=ParseMode.HTML)

        pet_template = PETS[pid]
        if user["balance"] < pet_template["cost"]:
            return await update.message.reply_text("📉 ɴᴏᴛ ᴇɴᴏᴜɢʜ!", parse_mode=ParseMode.HTML)

        new_pet = _build_pet_record(pid, pet_template)
        pets.append(new_pet)
        users_collection.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -pet_template["cost"]}})
        active_pet = _save_pet_state(user["user_id"], pets, active_pet_id or pid)
        suffix = " ⭐ ɴᴏᴡ ᴀᴄᴛɪᴠᴇ!" if active_pet and active_pet["id"] == pid and active_pet_id in {"", None} else ""
        return await update.message.reply_text(
            f"🎉 ᴀᴅᴏᴘᴛᴇᴅ {pet_template['name']}! ɴᴏᴡ ʏᴏᴜ ᴏᴡɴ {len(pets)} ᴘᴇᴛs.{suffix}",
            parse_mode=ParseMode.HTML,
        )

    if act in {"use", "switch", "set"}:
        if not pets:
            return await update.message.reply_text("❌ ɴᴏ ᴘᴇᴛs ʏᴇᴛ!", parse_mode=ParseMode.HTML)
        if len(context.args) < 2:
            return await update.message.reply_text("❌ ᴜsᴇ: <code>/pet use wolf</code>", parse_mode=ParseMode.HTML)
        wanted_id = context.args[1].lower()
        selected = next((owned for owned in pets if owned["id"] == wanted_id), None)
        if not selected:
            return await update.message.reply_text("❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜᴀᴛ ᴘᴇᴛ!", parse_mode=ParseMode.HTML)
        _save_pet_state(user["user_id"], pets, wanted_id)
        return await update.message.reply_text(f"⭐ ᴀᴄᴛɪᴠᴇ ᴘᴇᴛ sᴇᴛ ᴛᴏ {selected['name']}!", parse_mode=ParseMode.HTML)

    if act == "feed":
        if not pet:
            return await update.message.reply_text("❌ ɴᴏ ᴘᴇᴛ!", parse_mode=ParseMode.HTML)
        if user["balance"] < 500:
            return await update.message.reply_text("📉 ɴᴇᴇᴅ 500!", parse_mode=ParseMode.HTML)

        for owned in pets:
            if owned["id"] == pet["id"]:
                owned["hunger"] = 100
                owned["hp"] = min(100, int(owned.get("hp", 100)) + 20)
                owned["last_fed"] = datetime.utcnow()
                pet = owned
                break

        users_collection.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -500}})
        _save_pet_state(user["user_id"], pets, pet["id"])
        return await update.message.reply_text(f"🍖 {pet['name']} ɪs ғᴜʟʟ! ❤️+20", parse_mode=ParseMode.HTML)

    if act == "battle":
        if not pet:
            return await update.message.reply_text("❌ ɴᴏ ᴘᴇᴛ!", parse_mode=ParseMode.HTML)
        if update.effective_chat.type == ChatType.PRIVATE:
            return await update.message.reply_text("❌ ɢʀᴏᴜᴘ ᴏɴʟʏ!", parse_mode=ParseMode.HTML)

        from kazumi.utils import resolve_target

        target, err = await resolve_target(update, context)
        if not target:
            return await update.message.reply_text(err or "⚠️ ᴛᴀɢ sᴏᴍᴇᴏɴᴇ!", parse_mode=ParseMode.HTML)

        _, t_pet, _ = _load_pet_state(target)
        if not t_pet:
            return await update.message.reply_text("❌ ᴛʜᴇʏ ʜᴀᴠᴇ ɴᴏ ᴘᴇᴛ!", parse_mode=ParseMode.HTML)

        my_power = pet.get("power", 10) * random.uniform(0.7, 1.3) * (pet.get("level", 1) * 0.5 + 1)
        t_power = t_pet.get("power", 10) * random.uniform(0.7, 1.3) * (t_pet.get("level", 1) * 0.5 + 1)

        if my_power > t_power:
            reward = random.randint(500, 2000)
            for owned in pets:
                if owned["id"] == pet["id"]:
                    owned["xp"] = int(owned.get("xp", 0)) + 30
                    lvl = int(owned.get("level", 1))
                    if owned["xp"] >= lvl * 100:
                        owned["level"] = lvl + 1
                        owned["power"] = int(owned.get("power", 10)) + 5
                        owned["xp"] = 0
                    pet = owned
                    break
            users_collection.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": reward}})
            _save_pet_state(user["user_id"], pets, pet["id"])
            result = f"🎉 {pet['name']} ᴡᴏɴ! +{format_money(reward)}"
        else:
            for owned in pets:
                if owned["id"] == pet["id"]:
                    owned["hp"] = max(0, int(owned.get("hp", 100)) - 20)
                    pet = owned
                    break
            _save_pet_state(user["user_id"], pets, pet["id"])
            result = f"💀 {t_pet['name']} ᴡᴏɴ! ʏᴏᴜʀ ᴘᴇᴛ -20ʜᴘ"

        return await update.message.reply_text(
            f"⚔️ <b>{stylize_text('Pet Battle')}</b>\n━━━━━━━━━━━━\n\n"
            f"{pet['name']} ⚡{my_power:.0f}\n🆚\n{t_pet['name']} ⚡{t_power:.0f}\n\n{result}",
            parse_mode=ParseMode.HTML,
        )

    if act == "rename" and len(context.args) >= 2:
        if not pet:
            return
        new_name = " ".join(context.args[1:]).strip()[:15]
        if not new_name:
            return await update.message.reply_text("❌ ɢɪᴠᴇ ᴀ ɴᴀᴍᴇ!", parse_mode=ParseMode.HTML)
        emoji = pet["name"].split()[0]
        for owned in pets:
            if owned["id"] == pet["id"]:
                owned["name"] = f"{emoji} {new_name}"
                pet = owned
                break
        _save_pet_state(user["user_id"], pets, pet["id"])
        return await update.message.reply_text(f"✅ ʀᴇɴᴀᴍᴇᴅ ᴛᴏ {emoji} {new_name}!", parse_mode=ParseMode.HTML)


# ---- Dungeon Raid ----
BOSSES = [
    {"name": "🧟 ᴢᴏᴍʙɪᴇ ᴋɪɴɢ", "hp": 500, "reward": 3000},
    {"name": "🐉 ᴅᴀʀᴋ ᴅʀᴀɢᴏɴ", "hp": 1000, "reward": 8000},
    {"name": "👹 ᴅᴇᴍᴏɴ ʟᴏʀᴅ", "hp": 2000, "reward": 15000},
    {"name": "💀 sᴋᴜʟʟ ᴇᴍᴘᴇʀᴏʀ", "hp": 5000, "reward": 30000},
    {"name": "🌑 ᴠᴏɪᴅ ɢᴏᴅ", "hp": 10000, "reward": 60000},
]

active_raids = {}


async def raid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ ɢʀᴏᴜᴘ ᴏɴʟʏ!", parse_mode=ParseMode.HTML)
    user = ensure_user_exists(update.effective_user)
    uid = user["user_id"]

    _, pet, _ = _load_pet_state(user)

    if chat.id in active_raids:
        raid = active_raids[chat.id]
        if uid in raid["attackers"]:
            return await update.message.reply_text("⚠️ ᴀʟʀᴇᴀᴅʏ ᴀᴛᴛᴀᴄᴋɪɴɢ!", parse_mode=ParseMode.HTML)

        dmg = random.randint(50, 200)
        if pet:
            dmg += pet.get("power", 0)

        raid["boss_hp"] -= dmg
        raid["attackers"][uid] = raid["attackers"].get(uid, 0) + dmg

        if raid["boss_hp"] <= 0:
            total_dmg = sum(raid["attackers"].values())
            msg = f"🎉 <b>{stylize_text('Boss Defeated')}!</b>\n━━━━━━━━━━━━\n\n💀 {raid['boss_name']}\n\n"
            for attacker_id, dmg_done in sorted(raid["attackers"].items(), key=lambda item: -item[1]):
                share = int(raid["reward"] * dmg_done / total_dmg)
                users_collection.update_one({"user_id": attacker_id}, {"$inc": {"balance": share}})
                await add_xp(attacker_id, XP_PER_GAME_WIN)
                msg += f"⚔️ <a href='tg://user?id={attacker_id}'>ᴘʟᴀʏᴇʀ</a> — {dmg_done}ᴅᴍɢ → +{format_money(share)}\n"
            del active_raids[chat.id]
            return await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

        return await update.message.reply_text(
            f"⚔️ {get_mention(user)} ᴅᴇᴀʟᴛ <b>{dmg}</b> ᴅᴀᴍᴀɢᴇ!\n"
            f"❤️ ʙᴏss ʜᴘ: <b>{raid['boss_hp']}/{raid['boss_max']}</b>",
            parse_mode=ParseMode.HTML,
        )

    boss = random.choice(BOSSES)
    active_raids[chat.id] = {
        "boss_name": boss["name"],
        "boss_hp": boss["hp"],
        "boss_max": boss["hp"],
        "reward": boss["reward"],
        "attackers": {},
    }

    dmg = random.randint(50, 200)
    if pet:
        dmg += pet.get("power", 0)
    active_raids[chat.id]["boss_hp"] -= dmg
    active_raids[chat.id]["attackers"][uid] = dmg

    return await update.message.reply_text(
        f"⚔️ <b>{stylize_text('Dungeon Raid')}</b>\n━━━━━━━━━━━━\n\n"
        f"💀 ʙᴏss: <b>{boss['name']}</b>\n"
        f"❤️ ʜᴘ: {active_raids[chat.id]['boss_hp']}/{boss['hp']}\n"
        f"💰 ʀᴇᴡᴀʀᴅ: {format_money(boss['reward'])}\n\n"
        f"⚔️ {get_mention(user)} ᴅᴇᴀʟᴛ {dmg} ᴅᴍɢ!\n\n"
        f"<i>ᴛʏᴘᴇ /raid ᴛᴏ ᴀᴛᴛᴀᴄᴋ!</i>",
        parse_mode=ParseMode.HTML,
    )
