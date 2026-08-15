import type { DashboardPayload } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "https://3.107.191.151.sslip.io";
const DEV_INIT_DATA = import.meta.env.VITE_DEV_INIT_DATA || "";

export const tg = window.Telegram?.WebApp;
const unsafeUser = tg?.initDataUnsafe?.user;
const fallbackInitData = unsafeUser ? `user=${encodeURIComponent(JSON.stringify(unsafeUser))}` : "";
export const initData = tg?.initData || fallbackInitData || DEV_INIT_DATA;

export const urlParams = new URLSearchParams(window.location.search);
export const urlUser = urlParams.get("user") || urlParams.get("user_id") || (unsafeUser?.id ? String(unsafeUser.id) : "");

export async function apiPost<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const queryStr = urlUser ? `${path.includes("?") ? "&" : "?"}user=${urlUser}` : "";
  const response = await fetch(`${API_BASE}${path}${queryStr}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData
    },
    body: JSON.stringify({ initData, user: urlUser, ...body })
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload as T;
}

export function loadDashboard() {
  return apiPost<DashboardPayload>("/api/webapp/me");
}

export const demoPayload: DashboardPayload = {
  ok: true,
  user: {
    id: 7642098344,
    name: "Kazumi Pilot",
    username: "demo",
    balance: 826767,
    balanceText: "$826,767",
    rank: 7,
    status: "alive",
    kills: 18,
    wins: 42,
    dailyStreak: 9,
    premium: true,
    level: 21,
    rankTitle: "Premium Duelist",
    xp: { total: 14200, current: 740, needed: 1600 },
    inventory: [
      { id: "katana", name: "Katana", price: 75000, type: "weapon", buff: 0.35 },
      { id: "vibranium", name: "Vibranium", price: 1500000, type: "armor", buff: 0.5 },
      { id: "ps5", name: "PS5 Pro", price: 15000, type: "flex", buff: 0 }
    ],
    gear: {
      weapon: { id: "katana", name: "Katana", price: 75000, type: "weapon", buff: 0.35 },
      armor: { id: "vibranium", name: "Vibranium", price: 1500000, type: "armor", buff: 0.5 }
    },
    waifuCount: 13,
    achievements: ["first_blood", "gambler", "lover"]
  },
  daily: { canClaim: true, remainingSeconds: 0, streak: 9, reward: 5000 },
  cooldowns: {
    daily: 0,
    spin: 4200,
    fortune: 0,
    bankInterest: 8100,
    protection: 172800,
    kill: { used: 18, limit: 400, remaining: 382 },
    rob: { used: 6, limit: 300, remaining: 294 }
  },
  memory: {
    count: 4,
    limit: 25,
    facts: [
      { key: "name", value: "Kazumi Pilot", source: "manual" },
      { key: "likes", value: "tic tac toe", source: "auto" },
      { key: "interest", value: "anime and waifu content", source: "auto" },
      { key: "language_style", value: "Hinglish casual", source: "auto" }
    ]
  },
  missions: {
    date: "demo",
    completed: 3,
    total: 6,
    rewardReady: false,
    rewardClaimed: false,
    fullReward: 7500,
    fullXp: 120,
    today: [
      { id: "daily_claim", title: "Claim daily reward", desc: "Start your streak.", target: 1, count: 1, completed: true, reward: 1200, xp: 20 },
      { id: "play_game", title: "Play one game", desc: "Join any Kazumi game.", target: 1, count: 1, completed: true, reward: 1500, xp: 25 },
      { id: "group_challenge", title: "Start a group challenge", desc: "Fuel your group.", target: 1, count: 0, completed: false, reward: 1500, xp: 25 },
      { id: "taprace", title: "Join a Tap Race", desc: "Start or play /taprace in a group.", target: 1, count: 1, completed: true, reward: 1000, xp: 15 },
      { id: "loan_action", title: "Use the loan system", desc: "Ask or repay a loan.", target: 1, count: 0, completed: false, reward: 1300, xp: 20 },
      { id: "chat_xp", title: "Keep chat active", desc: "Send 10 group messages.", target: 10, count: 4, completed: false, reward: 2000, xp: 35 }
    ]
  },
  gang: {
    joined: true,
    name: "Abyss Syndicate",
    members: 12,
    bank: 540000,
    bankText: "$540,000",
    wins: 18,
    losses: 4,
    rating: 1285,
    pendingWar: null
  },
  premium: {
    active: true,
    ownerLink: "https://t.me/OgAbdulX",
    plan: "lifetime",
    until: null,
    lifetime: true,
    latestPayment: { status: "paid", plan: "lifetime", amountText: "35 USDT" },
    plans: [
      {
        id: "monthly",
        name: "Monthly Premium",
        priceText: "5 USDT",
        amount: 5,
        currency: "USDT",
        durationDays: 30,
        tagline: "30 days of boosted rewards, bigger limits and premium identity.",
        benefits: [
          "Custom badge with /setemoji",
          "Daily reward $5000 instead of $2000",
          "Higher kill and rob limits",
          "Lower 5% taxes on rob, give and games",
          "Extra protection and /check spy mode"
        ]
      },
      {
        id: "lifetime",
        name: "Lifetime Premium",
        priceText: "35 USDT",
        amount: 35,
        currency: "USDT",
        durationDays: null,
        tagline: "Permanent Kazumi Premium access for serious players.",
        benefits: [
          "Custom badge with /setemoji",
          "Daily reward $5000 instead of $2000",
          "Higher kill and rob limits",
          "Lower 5% taxes on rob, give and games",
          "Extra protection and /check spy mode"
        ]
      }
    ]
  },
  loans: {
    active: [
      {
        requestId: "demo-1",
        status: "active",
        direction: "borrowed",
        borrowerId: 7642098344,
        borrowerName: "Kazumi Pilot",
        lenderId: 1002,
        lenderName: "Abyss Nagi",
        amount: 250000,
        amountText: "$250,000",
        paid: 75000,
        remaining: 175000,
        remainingText: "$175,000"
      }
    ],
    pending: [],
    owed: 175000,
    lent: 90000
  },
  history: {
    recent: [
      {
        category: "daily",
        reason: "Claimed daily reward streak 9",
        direction: "credit",
        amount: 5000,
        amountText: "+$5,000",
        oldBalance: 821767,
        oldBalanceText: "$821,767",
        newBalance: 826767,
        newBalanceText: "$826,767",
        source: "/daily",
        createdAt: "2026-05-12T02:00:00.000Z"
      },
      {
        category: "loan_repay",
        reason: "Repaid active loans",
        direction: "debit",
        amount: -12000,
        amountText: "-$12,000",
        oldBalance: 833767,
        oldBalanceText: "$833,767",
        newBalance: 821767,
        newBalanceText: "$821,767",
        source: "/loan pay",
        createdAt: "2026-05-12T01:20:00.000Z"
      },
      {
        category: "kill",
        reason: "Killed Thunder",
        direction: "credit",
        amount: 8600,
        amountText: "+$8,600",
        oldBalance: 825167,
        oldBalanceText: "$825,167",
        newBalance: 833767,
        newBalanceText: "$833,767",
        source: "/kill",
        createdAt: "2026-05-12T00:50:00.000Z"
      }
    ],
    summary: {
      earned: 13600,
      earnedText: "$13,600",
      spent: 12000,
      spentText: "$12,000",
      net: 1600,
      netText: "+$1,600",
      biggestWin: 8600,
      biggestWinText: "$8,600",
      biggestLoss: 12000,
      biggestLossText: "$12,000",
      count: 3
    }
  },
  leaderboard: {
    rich: [
      { id: 1, name: "Nagi", value: 926767, valueText: "$926,767" },
      { id: 2, name: "Raj", value: 826767, valueText: "$826,767" },
      { id: 3, name: "Kazumi Pilot", value: 560000, valueText: "$560,000" }
    ],
    killers: [
      { id: 4, name: "Phantom", value: 301 },
      { id: 5, name: "Thunder", value: 178 },
      { id: 6, name: "Rai", value: 95 }
    ],
    winners: [
      { id: 7, name: "Abyss", value: 88 },
      { id: 8, name: "Felix", value: 63 },
      { id: 9, name: "Kazumi Pilot", value: 42 }
    ],
    debt: [
      { id: 10, name: "OG Abdul", value: 13500, valueText: "$13,500" },
      { id: 11, name: "Kazumi Pilot", value: 5000, valueText: "$5,000" }
    ]
  },
  shop: [
    { id: "knife", name: "Knife", price: 3500, type: "weapon", buff: 0.05 },
    { id: "riot", name: "Riot Shield", price: 40000, type: "armor", buff: 0.15 },
    { id: "rolex", name: "Rolex", price: 100000, type: "flex", buff: 0 }
  ],
  commands: [
    { name: "Tap Race", command: "/taprace", groupOnly: true },
    { name: "Tic Tac Toe", command: "/ttt", groupOnly: true },
    { name: "High Low", command: "/highlow 500", groupOnly: false },
    { name: "Word Bomb", command: "/wordbomb", groupOnly: true },
    { name: "P2P Desk", command: "/p2p", groupOnly: false }
  ]
};
