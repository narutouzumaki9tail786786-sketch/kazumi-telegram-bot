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

import os
import time

# Load .env FIRST (before any os.getenv calls)
try:
    from dotenv import load_dotenv
    # Let the repo .env file win over stale PM2 environment values.
    load_dotenv(override=True)
except ImportError:
    pass

# Track Uptime
START_TIME = time.time()

# Env Variables
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Keep transaction history useful without allowing it to fill Atlas again.
# Set to 0 to explicitly disable expiry.
BALANCE_LOG_RETENTION_DAYS = max(0, int(os.getenv("BALANCE_LOG_RETENTION_DAYS", "60")))

# --- AI KEYS ---
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").replace("\n", ",").split(",") if k.strip()]
if GROQ_API_KEY and GROQ_API_KEY not in GROQ_API_KEYS:
    GROQ_API_KEYS.insert(0, GROQ_API_KEY)
# Codestral usually uses the same Mistral Key, but we allow a separate one just in case
CODESTRAL_API_KEY = os.getenv("CODESTRAL_API_KEY", MISTRAL_API_KEY)
ENABLE_GROK_PROXY = os.getenv("ENABLE_GROK_PROXY", "false").lower() in {"1", "true", "yes", "on"}
GROK_PROXY_URL = os.getenv("GROK_PROXY_URL", "https://grok-api-red.vercel.app/chat/completions")
GROK_PROXY_MODEL = os.getenv("GROK_PROXY_MODEL", "grok-4.1-fast")
GROK_PROXY_API_KEY = os.getenv("GROK_PROXY_API_KEY", "")

PORT = int(os.environ.get("PORT", 5010))

# Updater Config
UPSTREAM_REPO = os.getenv("UPSTREAM_REPO", "")
GIT_TOKEN = os.getenv("GIT_TOKEN", "")

# Images & Links
START_IMG_URL = os.getenv("START_IMG_URL", "AgACAgQAAxkBAAN3agEXmgmdqC2FRsF6kwbvvRcNAAGoAAKfEWsbngIJUDlOjjJGHRIQAQADAgADeQADOwQ")

# Custom Kazumi Premium Emojis Pack (Telegram Custom Emoji IDs)
KAZUMI_CUSTOM_EMOJIS = [
    "6131703531784117214",
    "6129907178892435243",
    "6131714299267130383",
    "6132018425901359092",
    "6129719497411533061",
    "6129623814130114608",
    "6129591150903828318",
    "6131843118221238138",
]
HELP_IMG_URL = os.getenv("HELP_IMG_URL", "AgACAgUAAxkBAAICC2oCYhw9zeeNXNpxDTH7N3PRiwABtgAC9hRrGwTsGFR8kkcGbHdCkQEAAwIAA3kAAzsE") 
WELCOME_IMG_URL = os.getenv("WELCOME_IMG_URL", "AgACAgUAAxkBAAICCmoCYhwY0Gyxj0DQW6xkvZmTKlIxAAL1FGsbBOwYVIHaXsX9VYF6AQADAgADeQADOwQ") 
WELCOME_CARD_ENABLED = os.getenv("WELCOME_CARD_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "https://t.me/YourSupportGroup")
SUPPORT_CHANNEL = os.getenv("SUPPORT_CHANNEL", "https://t.me/YourUpdateChannel")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
WEBAPP_API_BASE_URL = os.getenv("WEBAPP_API_BASE_URL", "https://3.107.191.151.sslip.io")
OWNER_LINK = os.getenv("OWNER_LINK", "https://t.me/OgAbdulX")

# Premium payments
OXAPAY_MERCHANT_API_KEY = os.getenv("OXAPAY_MERCHANT_API_KEY", "")
OXAPAY_API_BASE = os.getenv("OXAPAY_API_BASE", "https://api.oxapay.com/v1")
PREMIUM_MONTHLY_USDT = float(os.getenv("PREMIUM_MONTHLY_USDT", "5"))
PREMIUM_LIFETIME_USDT = float(os.getenv("PREMIUM_LIFETIME_USDT", "35"))
PREMIUM_MONTHLY_DAYS = int(os.getenv("PREMIUM_MONTHLY_DAYS", "30"))

# IDs
try: LOGGER_ID = int(os.getenv("LOGGER_ID", "0").strip())
except: LOGGER_ID = 0
try: OWNER_ID = int(os.getenv("OWNER_ID", "7642098344").strip())
except: OWNER_ID = 0
SUDO_IDS_STR = os.getenv("SUDO_IDS", "")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🌸 BOT IDENTITY — Kazumi 2026
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_NAME = "🌸 ᴋᴀᴢᴜᴍɪ ×͜࿐"
BOT_VERSION = "2.0"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 💰 ECONOMY CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REVIVE_COST = 500
PROTECT_1D_COST = 1000
PROTECT_2D_COST = 1800
REGISTER_BONUS = 5000
CLAIM_BONUS = 2000
RIDDLE_REWARD = 1000
DIVORCE_COST = 2000
WAIFU_PROPOSE_COST = 5000
TAX_RATE = 0.10
MARRIED_TAX_RATE = 0.05
AUTO_REVIVE_HOURS = 6
AUTO_REVIVE_BONUS = 200
MIN_CLAIM_MEMBERS = 100

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📈 XP & LEVEL SYSTEM (NEW!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
XP_PER_MESSAGE = 5
XP_PER_KILL = 50
XP_PER_ROB = 30
XP_PER_GAME_WIN = 40
XP_PER_DAILY = 20
XP_PER_RIDDLE = 60
LEVEL_UP_BASE = 100       # XP needed for level 1
LEVEL_UP_MULTIPLIER = 1.5 # Each level needs 1.5x more XP
LEVEL_COIN_REWARD = 500   # Coins per level up

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🎮 GAME CONSTANTS (NEW!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLACKJACK_MIN_BET = 100
BLACKJACK_MAX_BET = 500_000
RPS_MIN_BET = 50
RPS_MAX_BET = 500_000
COINFLIP_MIN_BET = 50
COINFLIP_MAX_BET = 500_000
GUESS_REWARD = 2000
GUESS_MAX_TRIES = 6
RUSSIAN_ROULETTE_BET = 1000
HEIST_MIN_PLAYERS = 2
HEIST_MAX_PLAYERS = 10
HEIST_BASE_REWARD = 5000
HEIST_JOIN_TIME = 60          # Seconds to join
BOUNTY_MIN_AMOUNT = 1000
BOUNTY_MAX_AMOUNT = 500000
TOURNAMENT_ENTRY_FEE = 500
TOURNAMENT_MIN_PLAYERS = 4

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🌸 HAREM GACHA CONSTANTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GACHA_COST = 5000
DATE_COST = 1500
MAX_AFFECTION = 10
GACHA_RATES = {
    "mythic": 0.01,    # 1%
    "legendary": 0.05, # 5%
    "epic": 0.15,      # 15%
    "rare": 0.30,      # 30%
    "common": 0.49     # 49%
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 👋 SLAP GIF (paste your GIF file_id here)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SLAP_GIFS = [
    "CgACAgQAAxkBAAMlagAB_uMqVz7H48CFPPE7_Sa7UYYaAALXGwACngIJUNqsVufMK7fcOwQ",
    "CgACAgQAAxkBAAMpagEAAebYC1FxFSCAGtv-898DCejiAALYGwACngIJUOjo6moBwy5vOwQ",
    "CgACAgQAAxkBAAMsagEAAevnzhKPVp8gqcm4Fqd9DHsoAALZGwACngIJUAJ6VRU14l2gOwQ",
    "CgACAgQAAxkBAAMvagEAAe6ev8gK6uQrZktpCIFpCB0dAALaGwACngIJUAivIqhY5DYdOwQ",
]

PUNCH_GIFS = [
    "CgACAgQAAxkBAAMyagECgbtEdaHboJ659d908_4MwWIAAtsbAAKeAglQL8ini-JFrw47BA",
    "CgACAgQAAxkBAAMzagEChdqrw992bFVLVzeL6UcmOCoAAtwbAAKeAglQoKHZdEqTqnw7BA",
    "CgACAgQAAxkBAAM0agECjHgkLyaJD8vgsEZWq2bUGY8AAt0bAAKeAglQKVAfHOc0tak7BA",
    "CgACAgQAAxkBAAM1agECliU699qBYRQBGZPDOvbL3y4AAt4bAAKeAglQE-jPOMf8R9U7BA",
    "CgACAgQAAxkBAAM2agECoBPTpHMZrUI9JFFiG73t9VMAAt8bAAKeAglQBMRnmL8wWDU7BA",
]

HUG_GIFS = [
    "CgACAgQAAxkBAANBagED8egt3TNERB26ztKwvofnXQUAAuAbAAKeAglQAmhuJ7qO5ns7BA",
    "CgACAgQAAxkBAANCagED9jmxts8ohjKGpg2uk-UwGZ0AAuEbAAKeAglQSxckdYiShcM7BA",
    "CgACAgQAAxkBAANDagED_cOTX0LKklgPAAG9NsIgdD58AALiGwACngIJUETuRhI-68U-OwQ",
    "CgACAgQAAxkBAANEagEEBkrkCaXN5rr88YAkOBO98pIAAuMbAAKeAglQzTZqEkUxohQ7BA",
]

KISS_GIFS = [
    "CgACAgQAAxkBAAOtagG0UfDTDcPIF2u9eOtKw8DkqBkAAoUfAAKeAhFQl0IlNcBl9xo7BA",
    "CgACAgQAAxkBAAOvagG0pIlhRwygI0Ql2HOeyz193JMAAoYfAAKeAhFQ1XAbfMxNhv87BA",
    "CgACAgQAAxkBAAOwagG0pfiGi-yWBffG3ct1NvYam3gAAocfAAKeAhFQQTmvepoXoaA7BA",
    "CgACAgQAAxkBAAOxagG0pbmlDULhJFX3_0uP5nuTx-8AAogfAAKeAhFQ2l4Wd-symJY7BA",
    "CgACAgQAAxkBAAOyagG0ps43acQD2bfI7pFEH8YgCbIAAokfAAKeAhFQx1BWNAABktQYOwQ",
    "CgACAgQAAxkBAAOzagG0pilisH9irxGZBwsHkZu4Q7cAAoofAAKeAhFQzoz3Te0_3Hg7BA",
    "CgACAgQAAxkBAAO0agG0p3fWnqFkOB8XJyoZizRQtdEAAosfAAKeAhFQW5wJEkP-6Ck7BA",
]

COUPLE_GIFS = [
    "CgACAgUAAxkBAAICNGoCx8Ys2AkbWG64qZ8HCs5eHWFrAAJBKgACBOwYVKj0L1G9Lea9OwQ",
    "CgACAgUAAxkBAAICNWoCx8e_m1Fmpi6ByOitJmP3a54WAAJCKgACBOwYVJ1Nu8uKQI6vOwQ",
    "CgACAgUAAxkBAAICNmoCx8d_ydekr78wciIVIAOvv5EHAAJDKgACBOwYVAfkabzhEbTjOwQ",
    "CgACAgUAAxkBAAICN2oCx8jhtJ1NwoxvFhHsITjIymTUAAJEKgACBOwYVDhzRQXa2DXFOwQ",
]

COUPLE_PHOTOS = [
    "AgACAgUAAxkBAAICOGoCx8jubevNe_5fvM5uO9cwa5FAAALcFWsbBOwYVJYD5zKKHN4wAQADAgADeAADOwQ",
    "AgACAgUAAxkBAAICOWoCx8ifDq9OZN7lfHYMh7jbriApAALbFWsbBOwYVFapZKLJGHFvAQADAgADeAADOwQ",
]
COUPLE_PHOTO = COUPLE_PHOTOS[0]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🏅 ACHIEVEMENTS (NEW!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACHIEVEMENTS = {
    "first_blood": {"name": "🩸 First Blood", "desc": "Get your first kill", "condition": "kills >= 1", "reward": 500},
    "serial_killer": {"name": "🔪 Serial Killer", "desc": "Get 50 kills", "condition": "kills >= 50", "reward": 5000},
    "mass_murderer": {"name": "💀 Mass Murderer", "desc": "Get 200 kills", "condition": "kills >= 200", "reward": 20000},
    "rich_kid": {"name": "💰 Rich Kid", "desc": "Earn 100,000 coins", "condition": "balance >= 100000", "reward": 2000},
    "millionaire": {"name": "🤑 Millionaire", "desc": "Earn 1,000,000 coins", "condition": "balance >= 1000000", "reward": 10000},
    "billionaire": {"name": "🏦 Billionaire", "desc": "Earn 1,000,000,000 coins", "condition": "balance >= 1000000000", "reward": 100000},
    "lover": {"name": "💍 Lover", "desc": "Get married", "condition": "has_partner", "reward": 1000},
    "waifu_collector": {"name": "🌸 Waifu Collector", "desc": "Collect 10 waifus", "condition": "waifus >= 10", "reward": 3000},
    "waifu_master": {"name": "👑 Waifu Master", "desc": "Collect 50 waifus", "condition": "waifus >= 50", "reward": 15000},
    "shopaholic": {"name": "🛒 Shopaholic", "desc": "Buy 10 items", "condition": "inventory >= 10", "reward": 2000},
    "streak_master": {"name": "🔥 Streak Master", "desc": "30-day daily streak", "condition": "daily_streak >= 30", "reward": 25000},
    "gambler": {"name": "🎰 Gambler", "desc": "Win 20 gambling games", "condition": "game_wins >= 20", "reward": 5000},
    "high_roller": {"name": "🎲 High Roller", "desc": "Win 100 gambling games", "condition": "game_wins >= 100", "reward": 25000},
    "survivor": {"name": "🛡️ Survivor", "desc": "Survive 10 Russian Roulette games", "condition": "rr_wins >= 10", "reward": 5000},
    "heist_master": {"name": "🏛️ Heist Master", "desc": "Complete 5 heists", "condition": "heists >= 5", "reward": 10000},
    "bounty_hunter": {"name": "🎯 Bounty Hunter", "desc": "Claim 5 bounties", "condition": "bounties_claimed >= 5", "reward": 8000},
    "level_10": {"name": "⭐ Rising Star", "desc": "Reach Level 10", "condition": "level >= 10", "reward": 5000},
    "level_25": {"name": "🌟 Veteran", "desc": "Reach Level 25", "condition": "level >= 25", "reward": 15000},
    "level_50": {"name": "💎 Legend", "desc": "Reach Level 50", "condition": "level >= 50", "reward": 50000},
    "level_100": {"name": "🏆 God", "desc": "Reach Level 100", "condition": "level >= 100", "reward": 200000},
}

# --- 🛒 SHOP ITEMS (60+ Items) ---
SHOP_ITEMS = [
    # WEAPONS (Damage Buff)
    {"id": "stick", "name": "🪵 Stick", "price": 500, "type": "weapon", "buff": 0.01},
    {"id": "brick", "name": "🧱 Brick", "price": 1000, "type": "weapon", "buff": 0.02},
    {"id": "slingshot", "name": "🪃 Slingshot", "price": 2000, "type": "weapon", "buff": 0.03},
    {"id": "knife", "name": "🔪 Knife", "price": 3500, "type": "weapon", "buff": 0.05},
    {"id": "bat", "name": "🏏 Bat", "price": 5000, "type": "weapon", "buff": 0.08},
    {"id": "axe", "name": "🪓 Axe", "price": 7500, "type": "weapon", "buff": 0.10},
    {"id": "hammer", "name": "🔨 Hammer", "price": 10000, "type": "weapon", "buff": 0.12},
    {"id": "chainsaw", "name": "🪚 Chainsaw", "price": 15000, "type": "weapon", "buff": 0.15},
    {"id": "pistol", "name": "🔫 Pistol", "price": 25000, "type": "weapon", "buff": 0.20},
    {"id": "shotgun", "name": "🧨 Shotgun", "price": 40000, "type": "weapon", "buff": 0.25},
    {"id": "uzi", "name": "🔫 Uzi", "price": 55000, "type": "weapon", "buff": 0.30},
    {"id": "katana", "name": "⚔️ Katana", "price": 75000, "type": "weapon", "buff": 0.35},
    {"id": "ak47", "name": "💥 AK-47", "price": 100000, "type": "weapon", "buff": 0.40},
    {"id": "minigun", "name": "🔥 Minigun", "price": 150000, "type": "weapon", "buff": 0.45},
    {"id": "sniper", "name": "🎯 Sniper", "price": 200000, "type": "weapon", "buff": 0.50},
    {"id": "rpg", "name": "🚀 RPG", "price": 300000, "type": "weapon", "buff": 0.55},
    {"id": "tank", "name": "🚜 Tank", "price": 500000, "type": "weapon", "buff": 0.58},
    {"id": "laser", "name": "⚡ Laser", "price": 800000, "type": "weapon", "buff": 0.59},
    {"id": "deathnote", "name": "📓 Death Note", "price": 5000000, "type": "weapon", "buff": 0.60}, # Max Dmg

    # ARMOR (Block Chance)
    {"id": "paper", "name": "📰 Newspaper", "price": 500, "type": "armor", "buff": 0.01},
    {"id": "cardboard", "name": "📦 Cardboard", "price": 1000, "type": "armor", "buff": 0.02},
    {"id": "cloth", "name": "👕 Cloth", "price": 2500, "type": "armor", "buff": 0.05},
    {"id": "leather", "name": "🧥 Leather", "price": 8000, "type": "armor", "buff": 0.08},
    {"id": "chain", "name": "⛓️ Chain", "price": 20000, "type": "armor", "buff": 0.10},
    {"id": "riot", "name": "🛡️ Riot Shield", "price": 40000, "type": "armor", "buff": 0.15},
    {"id": "swat", "name": "👮 SWAT", "price": 60000, "type": "armor", "buff": 0.20},
    {"id": "iron", "name": "🦾 Iron Suit", "price": 100000, "type": "armor", "buff": 0.25},
    {"id": "diamond", "name": "💎 Diamond", "price": 200000, "type": "armor", "buff": 0.30},
    {"id": "obsidian", "name": "⚫ Obsidian", "price": 400000, "type": "armor", "buff": 0.35},
    {"id": "nano", "name": "🧬 Nano Suit", "price": 700000, "type": "armor", "buff": 0.40},
    {"id": "vibranium", "name": "🛡️ Vibranium", "price": 1500000, "type": "armor", "buff": 0.50},
    {"id": "force", "name": "🔮 Forcefield", "price": 3000000, "type": "armor", "buff": 0.55},
    {"id": "plot", "name": "🎬 Plot Armor", "price": 10000000, "type": "armor", "buff": 0.60}, # Max Block

    # FLEX
    {"id": "cookie", "name": "🍪 Cookie", "price": 100, "type": "flex", "buff": 0},
    {"id": "coffee", "name": "☕ Starbucks", "price": 300, "type": "flex", "buff": 0},
    {"id": "rose", "name": "🌹 Rose", "price": 500, "type": "flex", "buff": 0},
    {"id": "sushi", "name": "🍣 Sushi Platter", "price": 2000, "type": "flex", "buff": 0},
    {"id": "vodka", "name": "🍾 Vodka", "price": 5000, "type": "flex", "buff": 0},
    {"id": "ring", "name": "💍 Gold Ring", "price": 10000, "type": "flex", "buff": 0},
    {"id": "ps5", "name": "🎮 PS5 Pro", "price": 15000, "type": "flex", "buff": 0},
    {"id": "iphone", "name": "📱 iPhone 16 Pro", "price": 25000, "type": "flex", "buff": 0},
    {"id": "macbook", "name": "💻 MacBook M3", "price": 50000, "type": "flex", "buff": 0},
    {"id": "gucci", "name": "👜 Gucci Bag", "price": 75000, "type": "flex", "buff": 0},
    {"id": "rolex", "name": "⌚ Rolex", "price": 100000, "type": "flex", "buff": 0},
    {"id": "diamond_ring", "name": "💎 Solitaire", "price": 250000, "type": "flex", "buff": 0},
    {"id": "tesla", "name": "🚗 Tesla", "price": 400000, "type": "flex", "buff": 0},
    {"id": "lambo", "name": "🏎️ Lambo", "price": 800000, "type": "flex", "buff": 0},
    {"id": "heli", "name": "🚁 Helicopter", "price": 1500000, "type": "flex", "buff": 0},
    {"id": "yacht", "name": "🛳️ Super Yacht", "price": 3000000, "type": "flex", "buff": 0},
    {"id": "mansion", "name": "🏰 Mansion", "price": 5000000, "type": "flex", "buff": 0},
    {"id": "jet", "name": "✈️ Private Jet", "price": 10000000, "type": "flex", "buff": 0},
    {"id": "island", "name": "🏝️ Island", "price": 50000000, "type": "flex", "buff": 0},
    {"id": "moon", "name": "🌑 The Moon", "price": 100000000, "type": "flex", "buff": 0},
    {"id": "mars", "name": "🪐 Mars", "price": 500000000, "type": "flex", "buff": 0},
    {"id": "sun", "name": "☀️ The Sun", "price": 1000000000, "type": "flex", "buff": 0},
    {"id": "galaxy", "name": "🌌 Milky Way", "price": 5000000000, "type": "flex", "buff": 0},
    {"id": "blackhole", "name": "🕳️ Black Hole", "price": 9999999999, "type": "flex", "buff": 0},
]
SHOP_ITEMS.extend([
    {"id": "neon_crown", "name": "Neon Crown", "price": 7500000000, "type": "flex", "buff": 0},
    {"id": "anime_empire", "name": "Anime Empire", "price": 12000000000, "type": "flex", "buff": 0},
    {"id": "kazumi_palace", "name": "Kazumi Palace", "price": 25000000000, "type": "flex", "buff": 0},
    {"id": "starlight_throne", "name": "Starlight Throne", "price": 50000000000, "type": "flex", "buff": 0},
    {"id": "void_pass", "name": "Void VIP Pass", "price": 75000000000, "type": "flex", "buff": 0},
    {"id": "cosmic_title", "name": "Cosmic Title Deed", "price": 100000000000, "type": "flex", "buff": 0},
])

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://kazumi-mini-app.pages.dev")
DEFAULT_MAX_BET = 500_000  # Balanced Medium Wager Limit per round ($500,000 coins)



