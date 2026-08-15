# 🌸 Kazumi — Premium SaaS Telegram RPG Bot & Mini App (2026)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue?style=for-the-badge&logo=python" alt="Python Version">
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react" alt="React">
  <img src="https://img.shields.io/badge/Telegram_Bot_API-v20%2B-26A5E4?style=for-the-badge&logo=telegram" alt="Telegram API">
  <img src="https://img.shields.io/badge/Database-MongoDB_Atlas-47A248?style=for-the-badge&logo=mongodb" alt="MongoDB">
  <img src="https://img.shields.io/badge/Cloudflare-Workers_%26_Pages-F38020?style=for-the-badge&logo=cloudflare" alt="Cloudflare">
  <img src="https://img.shields.io/badge/Status-Production_Live-brightgreen?style=for-the-badge" alt="Status">
</p>

**Kazumi** is a state-of-the-art, high-concurrency Telegram RPG, economy, mini-games, AI assistant, and interactive Web Mini App platform. Built with modern async Python (`python-telegram-bot` v20+), Flask REST API, Cloudflare Edge proxies, and a React/Vite web application.

---

## 🌟 System Architecture

```
                                  ┌────────────────────────┐
                                  │     Telegram Users     │
                                  └───────────┬────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     │                                                 │
                     ▼                                                 ▼
        ┌─────────────────────────┐                       ┌─────────────────────────┐
        │  Telegram Bot Interface │                       │  Telegram Web Mini App  │
        │  (Commands & Inline)    │                       │  (React 18 / Vite UI)   │
        └────────────┬────────────┘                       └────────────┬────────────┘
                     │                                                 │
                     ▼                                                 ▼
        ┌─────────────────────────┐                       ┌─────────────────────────┐
        │  Cloudflare Worker      │                       │  Cloudflare Pages       │
        │  (kazumi-webhook-relay) │                       │  (kazumi-mini-app)      │
        └────────────┬────────────┘                       └────────────┬────────────┘
                     │                                                 │
                     └────────────────────────┬────────────────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │  Cloud VPS Backend      │
                                 │  (Flask API + PTB v20)  │
                                 └────────────┬────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │  MongoDB Atlas Cluster  │
                                 └─────────────────────────┘
```

---

## 🔥 Key Features

### 💰 Economy & RPG Core
- **Multi-tier Wallet & Bank System**: Real-time coin tracking, interest accrued, daily rewards (`/daily`), weekly bonuses (`/weekly`), and transaction ledger history.
- **PVP Combat & Stealing**: `/kill` mechanics, `/rob` with risk algorithms, `/protect` shields with expiration timers, and `/revive` medical recovery.
- **Bounties & Heists**: Cooperative group heists with join lobbies, automated target bounty rewards (`/bounty`), and tournament arenas.
- **Gang Wars V2**: Create gangs, stake-based gang challenges (`/gang war`), global gang leaderboards, and territory rankings.
- **Waifu & Harem Gacha**: Gacha rolls (`/gacha`), affection points (`/date`), rarity tiers (Common to Mythic), and custom collection cards.

### 🎮 Web & In-Chat Mini Games
- **Web Mini Arcade**: 
  - 🚀 **Aviator**: Real-time multiplier graph with auto-cashout safety.
  - 🎲 **Ludo Duel**: Interactive 3D board mechanics.
  - 💎 **Mines**: Customizable grid minesweeper.
  - 🎰 **Spin Wheel**: 3D lucky wheel with tier rewards.
  - 🔴🟢 **Color Bet**: Real-time color prediction.
- **In-Chat Games**: Connect 4 (`/c4`), Tic-Tac-Toe (`/ttt`), Tap Race (`/taprace`), Word Bomb (`/wordbomb`), Blackjack (`/blackjack`), RPS (`/rps`), High-Low (`/highlow`), and Russian Roulette.

### 🧠 AI & Persona Engine
- **Multi-Model Intelligence**: Automated fallback pipeline across Mistral AI, Groq LLMs, and Codestral.
- **Personalized Memory**: Persistent user facts and context storage (`/remember`, `/memory`, `/forgetme`).
- **AI Art & Speech Generation**: On-demand image creation (`/draw`) and Text-to-Speech synthesis (`/speak`).

### 📱 Telegram Web Mini App (TMA)
- **Fluid Visual Interface**: Modern glassmorphism UI built with React 18, Vite, Framer Motion, and Tailwind-grade vanilla styling.
- **Haptic & Sound Feedback**: Integrated Telegram Haptic Engine and ambient game audio effects.
- **HMAC SHA-256 Authentication**: Secure server-side validation of Telegram `initData` payload signatures.

---

## 🛠️ Environment Configuration

Create a `.env` file in the root directory before launching:

```env
# ── Telegram Bot Credentials ──
BOT_TOKEN=8541210855:AAH7k-O1h...
OWNER_ID=7642098344
SUDO_IDS=7642098344
LOGGER_ID=-100xxxxxxxxxx

# ── Database ──
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority

# ── AI Model API Keys ──
MISTRAL_API_KEY=your_mistral_key_here
GROQ_API_KEY=your_groq_key_here
CODESTRAL_API_KEY=your_codestral_key_here

# ── Server & Webhook Configuration ──
PORT=5010
WEBHOOK_URL=https://kazumi-webhook-relay.abdulstoreapi.workers.dev
WEBAPP_URL=https://kazumi-mini-app.pages.dev
WEBAPP_API_BASE_URL=https://kazumi-api-proxy.abdulstoreapi.workers.dev

# ── Payment Gateway (OxaPay) ──
OXAPAY_MERCHANT_API_KEY=your_oxapay_key
PREMIUM_MONTHLY_USDT=5
PREMIUM_LIFETIME_USDT=35

# ── Media Assets & Support ──
START_IMG_URL=https://ibb.co/...
HELP_IMG_URL=https://ibb.co/...
WELCOME_IMG_URL=https://ibb.co/...
SUPPORT_GROUP=https://t.me/YourSupportGroup
SUPPORT_CHANNEL=https://t.me/YourUpdateChannel
OWNER_LINK=https://t.me/OgAbdulX
```

---

## 🚀 Deployment Guide

### 1. Backend VPS Setup (PM2)

```bash
# Clone Repository
git clone https://github.com/OGAbdulOfficial/kazumi-telegram-bot.git
cd kazumi-telegram-bot

# Set up Python Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

# Install Dependencies
pip install -r requirements.txt

# Start via PM2
pm2 start main.py --name kazumi-bot --interpreter .venv/bin/python
pm2 save
```

### 2. Cloudflare Worker Setup (Webhook Proxy)

The webhook worker acts as an HTTPS proxy forwarding updates from Telegram to your VPS backend via `nip.io`:

```bash
cd cf-webhook-worker

# Deploy Worker
npx wrangler deploy
```

Set the resulting worker domain as `WEBHOOK_URL` in `.env`.

### 3. Frontend Web App Deployment (Cloudflare Pages)

```bash
cd webapp

# Install dependencies
npm install

# Build static assets
npm run build

# Deploy to Cloudflare Pages
npx wrangler pages deploy dist --project-name kazumi-mini-app
```

---

## 🎮 Command Reference

| Command | Description | Category |
|---|---|---|
| `/start` | Open Main Interactive Menu | Core |
| `/profile` | Display RPG Stats & Inventory Card | Core |
| `/bal` | Check Wallet & Bank Balances | Economy |
| `/bank` | Access Banking & Savings | Economy |
| `/daily` | Claim Daily Login Reward | Economy |
| `/loan` | Request or Repay Community Loans | Economy |
| `/shop` | Open Item Marketplace | Economy |
| `/kill` | Initiate PVP Attack on User | Combat |
| `/rob` | Attempt Coin Robbery | Combat |
| `/protect` | Purchase Active Protection Shield | Combat |
| `/heist` | Join Active Cooperative Group Heist | RPG |
| `/bounty` | Place or Claim User Bounties | RPG |
| `/gang` | Manage Gang, War Challenges & Ranking | RPG |
| `/wav` | Launch Web Aviator Mini App | Web Game |
| `/wludo` | Launch Web Ludo Mini App | Web Game |
| `/wmines` | Launch Web Mines Mini App | Web Game |
| `/wspin` | Launch Web Lucky Wheel Mini App | Web Game |
| `/wcolor` | Launch Web Color Bet Mini App | Web Game |
| `/chatbot` | Toggle AI Persona Chat | AI |
| `/draw` | Generate AI Image from Prompt | AI |
| `/speak` | Synthesize Voice Audio Message | AI |
| `/settings` | Group Administration & Protection | Admin |
| `/sudo` | Master Control Panel | Admin |

---

## 🔐 Security & Data Integrity

- **HMAC Validation**: All Web Mini App API requests are signed and verified server-side using Telegram Bot Token HMAC SHA-256 signatures (`webapp_api.py`).
- **Wager & Win Caps**: Hard-coded safety limits prevent economy inflation ($500,000 maximum bet, $2,000,000 maximum payout per game).
- **Environment Isolation**: API credentials and database connection strings are kept strict in `.env` and never committed.
- **Atomic Operations**: All MongoDB coin transactions use atomic increment/decrement operators (`$inc`, `$set`) to eliminate race conditions.

---

## 📄 License & Attribution

Copyright © 2026 Kazumi Team. All rights reserved.

Created by **@OGAbdulOfficial** (`@WTF_Phantom`). Preserved for authorized usage.
