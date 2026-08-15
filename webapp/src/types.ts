export type TabKey = "home" | "profile" | "history" | "games" | "loans" | "leaderboard" | "shop" | "admin";

export type KazumiUser = {
  id: number;
  name: string;
  username?: string;
  balance: number;
  balanceText: string;
  rank: number;
  status: string;
  kills: number;
  wins: number;
  dailyStreak: number;
  premium: boolean;
  level: number;
  rankTitle: string;
  xp: { total: number; current: number; needed: number };
  inventory: ShopItem[];
  gear: { weapon?: ShopItem | null; armor?: ShopItem | null };
  waifuCount: number;
  achievements: string[];
};

export type Loan = {
  requestId: string;
  status: string;
  direction: "borrowed" | "lent";
  borrowerId: number;
  borrowerName: string;
  lenderId: number;
  lenderName: string;
  amount: number;
  amountText: string;
  paid: number;
  remaining: number;
  remainingText: string;
  createdAt?: string;
};

export type ShopItem = {
  id: string;
  name: string;
  price: number;
  type: "weapon" | "armor" | "flex";
  buff: number;
};

export type LeaderRow = {
  id: number;
  name: string;
  value: number;
  valueText?: string;
};

export type Mission = {
  id: string;
  title: string;
  desc: string;
  target: number;
  count: number;
  completed: boolean;
  reward: number;
  xp: number;
};

export type MissionPayload = {
  date: string;
  today: Mission[];
  completed: number;
  total: number;
  rewardReady: boolean;
  rewardClaimed: boolean;
  fullReward: number;
  fullXp: number;
};

export type CooldownPayload = {
  daily: number;
  spin: number;
  fortune: number;
  bankInterest: number;
  protection: number;
  kill: { used: number; limit: number; remaining: number };
  rob: { used: number; limit: number; remaining: number };
};

export type MemoryFact = {
  key: string;
  value: string;
  source: string;
};

export type MemoryPayload = {
  count: number;
  limit: number;
  facts: MemoryFact[];
};

export type GangPayload = {
  joined: boolean;
  name?: string;
  leaderId?: number;
  members?: number;
  bank?: number;
  bankText?: string;
  wins?: number;
  losses?: number;
  rating?: number;
  pendingWar?: {
    enemy?: string;
    direction?: "incoming" | "outgoing";
    stakeText?: string;
  } | null;
  top?: Array<{ name: string; rating: number; wins: number; members: number; bankText: string }>;
};

export type PremiumPlan = {
  id: string;
  name: string;
  priceText: string;
  amount: number;
  currency: string;
  durationDays?: number | null;
  tagline: string;
  benefits: string[];
};

export type PremiumPayment = {
  paymentId?: string;
  trackId?: string;
  invoiceId?: string;
  plan?: string;
  amount?: number;
  amountText?: string;
  currency?: string;
  status: string;
  paymentUrl?: string;
  createdAt?: string;
  paidAt?: string;
  expiresAt?: string;
} | null;

export type PremiumPayload = {
  active: boolean;
  ownerLink: string;
  plan?: string | null;
  until?: string | null;
  lifetime?: boolean;
  latestPayment?: PremiumPayment;
  plans: PremiumPlan[];
};

export type BalanceHistoryEntry = {
  category: string;
  reason: string;
  direction: "credit" | "debit";
  scope?: "wallet" | "bank";
  scopeLabel?: string;
  amount: number;
  amountText: string;
  oldBalance: number;
  oldBalanceText: string;
  newBalance: number;
  newBalanceText: string;
  oldValue?: number;
  oldValueText?: string;
  newValue?: number;
  newValueText?: string;
  source: string;
  createdAt?: string;
};

export type BalanceHistoryPayload = {
  recent: BalanceHistoryEntry[];
  summary: {
    earned: number;
    earnedText: string;
    spent: number;
    spentText: string;
    net: number;
    netText: string;
    biggestWin: number;
    biggestWinText: string;
    biggestLoss: number;
    biggestLossText: string;
    count: number;
  };
};

export type AdminBriefUser = {
  id: number;
  name: string;
  username?: string;
  balance: number;
  balanceText: string;
  bank: number;
  bankText: string;
  wealth: number;
  wealthText: string;
  status: string;
  premium: boolean;
  leaderboardHidden: boolean;
};

export type AdminBreakdownRow = {
  key: string;
  label: string;
  amount: number;
  amountText: string;
  count: number;
};

export type AdminWindowMetrics = {
  credits: number;
  creditsText: string;
  debits: number;
  debitsText: string;
  net: number;
  netText: string;
  count: number;
};

export type AdminFlag = {
  tone: "danger" | "warn" | "info";
  label: string;
  detail: string;
};

export type AdminAuditEntry = {
  action: string;
  reason: string;
  amount?: number | null;
  amountText?: string | null;
  adminUserId?: number;
  targetUserId?: number;
  createdAt?: string;
  meta?: Record<string, unknown>;
};

export type AdminUserDetail = {
  user: AdminBriefUser & {
    kills: number;
    wins: number;
    dailyStreak: number;
    lastActiveAt?: string | null;
    protectionExpiry?: string | null;
  };
  loans: {
    active: Loan[];
    pending: Loan[];
    owed: number;
    lent: number;
  };
  history: {
    recent: BalanceHistoryEntry[];
    summary: BalanceHistoryPayload["summary"];
  };
  forensics: {
    day1: AdminWindowMetrics;
    day7: AdminWindowMetrics;
    creditCategories: AdminBreakdownRow[];
    debitCategories: AdminBreakdownRow[];
    creditSources: AdminBreakdownRow[];
  };
  flags: AdminFlag[];
  audit: AdminAuditEntry[];
};

export type AdminPayload = {
  canAccess: boolean;
  role: string | null;
  summary: {
    totalUsers: number;
    hiddenUsers: number;
    activeLoans: number;
    pendingLoans: number;
    topVisibleName: string;
    topVisibleBalanceText: string;
  };
  queue: AdminBriefUser[];
};

export type DashboardPayload = {
  ok: boolean;
  user: KazumiUser;
  daily: {
    canClaim: boolean;
    remainingSeconds: number;
    streak: number;
    reward: number;
  };
  missions: MissionPayload;
  cooldowns: CooldownPayload;
  memory: MemoryPayload;
  gang: GangPayload;
  premium: PremiumPayload;
  loans: {
    active: Loan[];
    pending: Loan[];
    owed: number;
    lent: number;
  };
  history: BalanceHistoryPayload;
  leaderboard: {
    rich: LeaderRow[];
    killers: LeaderRow[];
    winners: LeaderRow[];
    debt: LeaderRow[];
  };
  shop: ShopItem[];
  admin?: AdminPayload | null;
  commands: Array<{ name: string; command: string; groupOnly: boolean }>;
};

export type TelegramWebApp = {
  initData: string;
  initDataUnsafe?: { user?: { id: number; first_name?: string; username?: string; photo_url?: string } };
  colorScheme?: "light" | "dark";
  ready: () => void;
  expand: () => void;
  close: () => void;
  HapticFeedback?: {
    impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
    notificationOccurred: (type: "error" | "success" | "warning") => void;
  };
  openTelegramLink?: (url: string) => void;
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void;
  MainButton?: {
    text: string;
    show: () => void;
    hide: () => void;
    onClick: (fn: () => void) => void;
    offClick: (fn: () => void) => void;
  };
};

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}
