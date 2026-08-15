import React, { useEffect, useMemo, useRef, useState } from "react";

import { AnimatePresence, motion } from "framer-motion";
import gsap from "gsap";
import {
  AlertTriangle,
  BadgeDollarSign,
  Banknote,
  Bot,
  Brain,
  ChevronRight,
  Clock3,
  Crown,
  Gamepad2,
  HeartPulse,
  Home,
  Landmark,
  LayoutDashboard,
  Loader2,
  Medal,
  Package,
  Search,
  Shield,
  Sparkles,
  Swords,
  Trophy,
  Trash2,
  UserRound,
  WalletCards,
  ArrowLeft
} from "lucide-react";
import { apiPost, demoPayload, initData, loadDashboard, tg, urlUser } from "./api";
import type { AdminAuditEntry, AdminBreakdownRow, AdminBriefUser, AdminPayload, AdminUserDetail, BalanceHistoryPayload, CooldownPayload, DashboardPayload, GangPayload, LeaderRow, Loan, MemoryPayload, MissionPayload, PremiumPayload, PremiumPayment, ShopItem, TabKey } from "./types";

const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME || "KazumiRpgBot";

const tabs: Array<{ key: TabKey; label: string; icon: typeof Home; adminOnly?: boolean }> = [
  { key: "home", label: "Home", icon: LayoutDashboard },
  { key: "leaderboard", label: "Top", icon: Trophy },
  { key: "profile", label: "Profile", icon: UserRound },
  { key: "history", label: "History", icon: BadgeDollarSign },
  { key: "games", label: "Arcade", icon: Gamepad2 },
  { key: "loans", label: "Loans", icon: Landmark },
  { key: "shop", label: "Shop", icon: Package },
  { key: "admin", label: "Admin", icon: Shield, adminOnly: true }
];

function money(value: number) {
  return `$${value.toLocaleString()}`;
}

function duration(totalSeconds: number) {
  if (totalSeconds <= 0) return "Ready";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (hours >= 24) {
    const days = Math.floor(hours / 24);
    const restHours = hours % 24;
    return `${days}d ${restHours}h`;
  }
  return `${hours}h ${minutes}m`;
}

function historyTime(value?: string) {
  if (!value) return "Just now";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Just now";
  return parsed.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function openBot(command?: string) {
  const payload = command ? `?start=${encodeURIComponent(command.replace("/", ""))}` : "";
  const url = `https://t.me/${BOT_USERNAME}${payload}`;
  tg?.openTelegramLink ? tg.openTelegramLink(url) : window.open(url, "_blank");
}

function openExternal(url: string) {
  if (url.startsWith("https://t.me/") && tg?.openTelegramLink) {
    tg.openTelegramLink(url);
    return;
  }
  if (tg?.openLink) {
    tg.openLink(url);
    return;
  }
  window.open(url, "_blank");
}

function initialTab(): TabKey {
  const params = new URLSearchParams(window.location.search);
  const hash = window.location.hash.replace("#", "").toLowerCase();
  if (hash === "premium" || hash === "shop" || hash === "plans") return "shop";
  if (hash === "aviator" || hash === "ludo" || hash === "mines" || hash === "spin" || hash === "color" || params.get("game")) return "games";
  const tab = params.get("tab") as TabKey | null;
  if (tab && tabs.some((item) => item.key === tab)) return tab;
  if (params.get("premium")) return "shop";
  return "home";
}


function wantsPremiumOpen() {
  const params = new URLSearchParams(window.location.search);
  const hash = window.location.hash.replace("#", "").toLowerCase();
  return hash === "premium" || hash === "plans" || params.get("premium") === "1" || params.get("open") === "premium";
}

function NeonField() {
  useEffect(() => {
    const canvas = document.getElementById("kazumi-field") as HTMLCanvasElement | null;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const particles = Array.from({ length: 80 }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: Math.random() * 2 + 1,
      color: ["#3ee7ff", "#ff5ccd", "#f7d774", "#7cff9b"][Math.floor(Math.random() * 4)],
      vx: (Math.random() - 0.5) * 0.6,
      vy: (Math.random() - 0.5) * 0.6,
    }));

    const resize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", resize);

    const render = () => {
      ctx.clearRect(0, 0, width, height);
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.shadowBlur = 10;
        ctx.shadowColor = p.color;
        ctx.fill();
      });
      animId = requestAnimationFrame(render);
    };
    render();

    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(animId);
    };
  }, []);

  return <canvas id="kazumi-field" className="neon-field" aria-hidden="true" />;
}

function StatCard({ label, value, icon: Icon, tone = "cyan" }: { label: string; value: string; icon: typeof WalletCards; tone?: string }) {
  return (
    <motion.div className={`stat-card tone-${tone}`} whileHover={{ y: -4, scale: 1.01 }}>
      <Icon size={20} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </motion.div>
  );
}

function HeroLeaderboard({ rows }: { rows: LeaderRow[] }) {
  const safeRows = rows || [];
  return (
    <div className="hero-leader-track">
      {safeRows.slice(0, 3).map((row, index) => (
        <div className="hero-leader-pill" key={row.id || index}>
          <span className={`pill-badge top-${index + 1}`}>#{index + 1}</span>
          <strong className="pill-name">{row.name}</strong>
          <span className="pill-val">{row.valueText || money(row.value)}</span>
        </div>
      ))}
    </div>
  );
}

function MissionPanel({ missions, onClaim }: { missions: MissionPayload; onClaim: () => void }) {
  const safeMissions = missions || { completed: 0, total: 3, rewardReady: false, rewardClaimed: false, today: [] };
  const pct = Math.round((safeMissions.completed / Math.max(safeMissions.total, 1)) * 100);

  return (
    <div className="mission-shell">
      <div className="mission-header">
        <div>
          <h3>{safeMissions.completed}/{safeMissions.total} Missions Cleared</h3>
          <p>Complete all daily targets to trigger full wallet & XP payout.</p>
        </div>
        <button className="claim-btn" onClick={onClaim} disabled={!safeMissions.rewardReady || safeMissions.rewardClaimed}>
          {safeMissions.rewardClaimed ? "Claimed" : safeMissions.rewardReady ? "Claim All Rewards" : "In Progress"}
        </button>
      </div>
      <div className="mission-progress">
        <div className="mission-progress-bar" style={{ width: `${pct}%` }} />
      </div>
      <div className="mission-list">
        {(safeMissions.today || []).map((item) => (
          <div className={`mission-row ${item.completed ? "done" : ""}`} key={item.id}>
            <div>
              <strong>{item.title}</strong>
              <p>{item.desc}</p>
            </div>
            <div className="mission-meta">
              <span>{item.count}/{item.target}</span>
              <b>+{money(item.reward)}</b>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


function GangPanel({ gang }: { gang: GangPayload }) {
  if (!gang.joined) {
    return (
      <div className="gang-empty">
        <Shield size={36} />
        <p>You are not in a gang yet. Create or join a gang via bot commands to join War Room.</p>
        <button onClick={() => openBot("/gang")}>Open Gang Console</button>
      </div>
    );
  }

  return (
    <div className="gang-card">
      <div className="gang-head">
        <div>
          <h3>{gang.name || "My Gang"}</h3>
          <p>Boss ID: {gang.leaderId}</p>
        </div>
        <span className="gang-badge">Rating {gang.rating || 0}</span>
      </div>
      <div className="gang-stats">
        <div><span>Vault</span><strong>{gang.bankText || "$0"}</strong></div>
        <div><span>Members</span><strong>{gang.members || 1}</strong></div>
      </div>
    </div>
  );
}

function CooldownPanel({ cooldowns }: { cooldowns: CooldownPayload }) {
  const items = [
    { label: "Daily Claim", ready: cooldowns.daily <= 0, val: duration(cooldowns.daily) },
    { label: "Lucky Spin", ready: cooldowns.spin <= 0, val: duration(cooldowns.spin) },
    { label: "Fortune Cookie", ready: cooldowns.fortune <= 0, val: duration(cooldowns.fortune) },
    { label: "Bank Interest", ready: cooldowns.bankInterest <= 0, val: duration(cooldowns.bankInterest) },
    { label: "Shield Active", ready: cooldowns.protection > 0, val: cooldowns.protection > 0 ? duration(cooldowns.protection) : "No Shield" },
    { label: "Daily Kills", ready: true, val: `${cooldowns.kill.used}/${cooldowns.kill.limit}` },
    { label: "Daily Robs", ready: true, val: `${cooldowns.rob.used}/${cooldowns.rob.limit}` }
  ];

  return (
    <div className="cooldown-grid">
      {items.map((c, i) => (
        <div className={`cd-chip ${c.ready ? "ready" : "waiting"}`} key={i}>
          <span>{c.label}</span>
          <strong>{c.val}</strong>
        </div>
      ))}
    </div>
  );
}

function MemoryPanel({ memory, onForget }: { memory: MemoryPayload; onForget: (key: string) => void }) {
  return (
    <div className="memory-shell">
      <div className="memory-head">
        <div>
          <h3>{memory.count}/{memory.limit} Memory Tokens Recorded</h3>
          <p>Kazumi retains key facts from your chat history to personalize AI interactions.</p>
        </div>
        <button className="ghost-danger" onClick={() => onForget("all")} disabled={!memory.count}>
          <Trash2 size={16} /> Clear Memory
        </button>
      </div>
      <div className="memory-list">
        {memory.facts.length ? memory.facts.map((fact, index) => (
          <div className="memory-row" key={`${fact.key}-${index}`}>
            <span className="memory-key">{fact.key}</span>
            <strong className="memory-val">{fact.value}</strong>
            <small className="memory-src">{fact.source}</small>
          </div>
        )) : <p className="muted">No personalized memory facts stored yet.</p>}
      </div>
    </div>
  );
}

function ShopTile({ item }: { item: ShopItem }) {
  return (
    <div className="shop-tile">
      <div className="shop-icon"><Package size={22} /></div>
      <div className="shop-copy">
        <strong>{item.name}</strong>
        <span>+{item.buff} {item.type} power</span>
        <b>{money(item.price)}</b>
      </div>
    </div>
  );
}

function LoanRow({ loan }: { loan: Loan }) {
  return (
    <div className="loan-row">
      <div>
        <strong>{loan.direction === "borrowed" ? `From ${loan.lenderName}` : `To ${loan.borrowerName}`}</strong>
        <p>Remaining: {loan.remainingText}</p>
      </div>
      <span className={`loan-status ${loan.status}`}>{loan.status}</span>
    </div>
  );
}

function LeaderList({ rows, mode = "money" }: { rows: LeaderRow[]; mode?: "money" | "number" }) {
  return (
    <div className="leader-list">
      {rows.map((row, index) => (
        <div className="leader-row" key={row.id}>
          <span className={`leader-rank ${index < 3 ? `top-${index + 1}` : ""}`}>#{index + 1}</span>
          <span className="leader-name">{row.name}</span>
          <strong>{mode === "money" ? row.valueText || money(row.value) : row.value.toLocaleString()}</strong>
        </div>
      ))}
    </div>
  );
}

function PremiumPanel({ premium, demoMode, onRefresh }: { premium: PremiumPayload; demoMode: boolean; onRefresh: () => void }) {
  return (
    <div className="premium-shell">
      <div className="premium-head">
        <Crown size={32} color="#f7d774" />
        <div>
          <h3>Kazumi VIP Pass</h3>
          <p>{premium.active ? "Your VIP Pass is currently active!" : "Unlock 2x Daily Rewards, Custom Badges, and Zero Bank Fees."}</p>
        </div>
      </div>
      <div className="premium-features">
        <div>⚡ 2x Daily Coins & XP</div>
        <div>🛡️ Auto-Shield Protection</div>
        <div>👑 Custom Telegram Emoji Badges</div>
        <div>💎 Priority AI Chat Responses</div>
      </div>
      <button className="btn-launch" onClick={() => openBot("/premium")}>
        {premium.active ? "Manage VIP Membership" : "Upgrade to VIP ($10,000)"}
      </button>
    </div>
  );
}

function HistoryPanel({ history }: { history: BalanceHistoryPayload }) {
  return (
    <div className="history-shell">
      <div className="history-list">
        {history.recent.length ? history.recent.map((entry, index) => (
          <div className={`history-row ${entry.direction}`} key={`${entry.createdAt || entry.reason}-${index}`}>
            <div className="history-copy">
              <div className="history-topline">
                <strong>{entry.reason}</strong>
                <b>{entry.amountText}</b>
              </div>
              <div className="history-meta">
                <span>{entry.category.replace(/_/g, " ")}</span>
                <span>{entry.oldValueText || entry.oldBalanceText}{" -> "}{entry.newValueText || entry.newBalanceText}</span>
                <span>{historyTime(entry.createdAt)}</span>
              </div>
            </div>
          </div>
        )) : <p className="muted">No wallet history yet. Play, claim, repay, or trade to start the ledger.</p>}
      </div>
    </div>
  );
}

function AdminUserCard({ user, onPick }: { user: AdminBriefUser; onPick: (userId: number) => void }) {
  return (
    <button className="admin-user-card" onClick={() => onPick(user.id)}>
      <div>
        <strong>{user.name}</strong>
        <span>{user.username ? `@${user.username}` : `ID ${user.id}`}</span>
      </div>
      <div className="admin-user-values">
        <b>{user.balanceText}</b>
        <small>{user.bankText} bank</small>
      </div>
    </button>
  );
}

function AdminBreakdownList({ title, rows }: { title: string; rows: AdminBreakdownRow[] }) {
  return (
    <div className="admin-breakdown">
      <div className="admin-breakdown-head">
        <strong>{title}</strong>
      </div>
      {rows.length ? rows.map((row) => (
        <div className="admin-breakdown-row" key={`${title}-${row.key}`}>
          <span>{row.label}</span>
          <b>{row.amountText}</b>
        </div>
      )) : <p className="muted">No data yet.</p>}
    </div>
  );
}

function AdminAuditList({ rows }: { rows: AdminAuditEntry[] }) {
  return (
    <div className="admin-audit-list">
      {rows.length ? rows.map((row, index) => (
        <div className="admin-audit-row" key={`${row.action}-${row.createdAt || index}`}>
          <div>
            <strong>{row.action.replace(/_/g, " ")}</strong>
            <span>{row.reason || "No reason added"}</span>
          </div>
          <small>{historyTime(row.createdAt)}</small>
        </div>
      )) : <p className="muted">No admin actions logged for this user yet.</p>}
    </div>
  );
}

function CyberSpinWheelCanvas({ degree }: { degree: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const currentDegreeRef = useRef<number>(0);
  const startDegreeRef = useRef<number>(0);
  const targetDegreeRef = useRef<number>(0);
  const startTimeRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const size = 280;
    canvas.width = size;
    canvas.height = size;
    const cx = size / 2;
    const cy = size / 2;
    const outerRadius = size / 2 - 12;
    const innerRadius = 36;

    const slices = [
      { label: "2X MULT", color: "#3ee7ff", textColor: "#070914" },
      { label: "0X LOSS", color: "#ef4444", textColor: "#ffffff" },
      { label: "5X MULT", color: "#7cff9b", textColor: "#070914" },
      { label: "NO WIN", color: "#64748b", textColor: "#ffffff" },
      { label: "10X JACKPOT", color: "#f7d774", textColor: "#070914" },
      { label: "0X LOSS", color: "#ef4444", textColor: "#ffffff" },
    ];

    const sliceAngle = (Math.PI * 2) / slices.length;
    let animId: number;

    const drawFrame = (deg: number) => {
      ctx.clearRect(0, 0, size, size);
      const rotationRad = (deg * Math.PI) / 180;

      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(rotationRad);

      slices.forEach((slice, i) => {
        const startAngle = i * sliceAngle;
        const endAngle = startAngle + sliceAngle;

        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.arc(0, 0, outerRadius, startAngle, endAngle);
        ctx.closePath();
        ctx.fillStyle = slice.color;
        ctx.fill();
        ctx.strokeStyle = "rgba(7, 9, 20, 0.4)";
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.save();
        const midAngle = startAngle + sliceAngle / 2;
        ctx.rotate(midAngle);
        ctx.textAlign = "right";
        ctx.fillStyle = slice.textColor;
        ctx.font = "bold 13px system-ui, sans-serif";
        ctx.fillText(slice.label, outerRadius - 18, 5);
        ctx.restore();
      });

      ctx.restore();

      // Outer Neon Ring
      ctx.beginPath();
      ctx.arc(cx, cy, outerRadius, 0, Math.PI * 2);
      ctx.lineWidth = 6;
      ctx.strokeStyle = "#3ee7ff";
      ctx.shadowBlur = 14;
      ctx.shadowColor = "#3ee7ff";
      ctx.stroke();
      ctx.shadowBlur = 0;

      // LED Bulbs
      for (let i = 0; i < 12; i++) {
        const angle = (i * Math.PI * 2) / 12;
        const bx = cx + Math.cos(angle) * (outerRadius + 2);
        const by = cy + Math.sin(angle) * (outerRadius + 2);
        ctx.beginPath();
        ctx.arc(bx, by, 3, 0, Math.PI * 2);
        ctx.fillStyle = i % 2 === 0 ? "#ff5ccd" : "#f7d774";
        ctx.shadowBlur = 8;
        ctx.shadowColor = ctx.fillStyle;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      // Center Metallic Hub
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius, 0, Math.PI * 2);
      ctx.fillStyle = "#070914";
      ctx.fill();
      ctx.lineWidth = 3;
      ctx.strokeStyle = "#f7d774";
      ctx.stroke();

      ctx.font = "20px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("💎", cx, cy);
    };

    if (degree !== targetDegreeRef.current) {
      startDegreeRef.current = currentDegreeRef.current;
      targetDegreeRef.current = degree;
      startTimeRef.current = performance.now();
    }

    const duration = 3000;

    const animate = (now: number) => {
      if (!startTimeRef.current) {
        drawFrame(currentDegreeRef.current);
        return;
      }

      const elapsed = now - startTimeRef.current;
      const progress = Math.min(1, elapsed / duration);
      const ease = 1 - Math.pow(1 - progress, 3); // ease-out cubic

      const currentDeg = startDegreeRef.current + (targetDegreeRef.current - startDegreeRef.current) * ease;
      currentDegreeRef.current = currentDeg;
      drawFrame(currentDeg);

      if (progress < 1) {
        animId = requestAnimationFrame(animate);
      }
    };

    animId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [degree]);

  return (
    <div className="cyber-wheel-wrapper">
      <div className="wheel-pointer-pin">▼</div>
      <canvas ref={canvasRef} className="cyber-wheel-canvas" />
    </div>
  );
}

function ArcadeView({ userBalance, isDirectMode = false, onBalanceChange }: { userBalance: number; isDirectMode?: boolean; onBalanceChange?: (newBal: number) => void }) {


  const [selectedGame, setSelectedGame] = useState<"aviator" | "ludo" | "mines" | "spin" | "color">(() => {
    const params = new URLSearchParams(window.location.search);
    const hash = window.location.hash.replace("#", "").toLowerCase();
    if (hash === "aviator" || params.get("game") === "aviator") return "aviator";
    if (hash === "ludo" || params.get("game") === "ludo") return "ludo";
    if (hash === "mines" || params.get("game") === "mines") return "mines";
    if (hash === "spin" || params.get("game") === "spin") return "spin";
    if (hash === "color" || params.get("game") === "color") return "color";
    return "aviator";
  });

  const [bet, setBet] = useState<number>(() => {
    const params = new URLSearchParams(window.location.search);
    const b = parseInt(params.get("bet") || "1000", 10);
    return isNaN(b) ? 1000 : b;
  });

  // Aviator Canvas Flight State
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [avState, setAvState] = useState<"idle" | "flying" | "cashed" | "crashed">("idle");
  const [avMult, setAvMult] = useState<number>(1.00);
  const [avHistory, setAvHistory] = useState<number[]>([1.85, 4.20, 1.12, 12.50, 2.10, 3.45]);

  // Real Ludo State
  const [ludoDice, setLudoDice] = useState<number>(6);
  const [ludoP1Pawns, setLudoP1Pawns] = useState<number[]>([0, 0, 0, 0]); // 0 to 57
  const [ludoP2Pawns, setLudoP2Pawns] = useState<number[]>([0, 0, 0, 0]);
  const [ludoTurn, setLudoTurn] = useState<1 | 2>(1);
  const [ludoStatus, setLudoStatus] = useState<string>("Tap Roll Dice to move pawns!");

  // Real Mines Grid State
  const [mineCount, setMineCount] = useState<number>(3);
  const [minesGrid, setMinesGrid] = useState<Array<{ id: number; isMine: boolean; revealed: boolean }>>([]);
  const [minesActive, setMinesActive] = useState(false);
  const [minesMult, setMinesMult] = useState(1.00);
  const [minesGems, setMinesGems] = useState(0);

  // Spin Wheel State
  const [spinDegree, setSpinDegree] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [spinWinText, setSpinWinText] = useState<string | null>(null);

  // Color Prediction State
  const [colorChoice, setColorChoice] = useState<"red" | "green" | "violet">("red");
  const [colorSpinning, setColorSpinning] = useState(false);
  const [colorResult, setColorResult] = useState<string | null>(null);
  const [colorHistory, setColorHistory] = useState<string[]>(["red", "green", "red", "violet", "green", "red"]);

  // Aviator Real-time Canvas Rendering
  useEffect(() => {
    if (selectedGame !== "aviator") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = (canvas.width = canvas.parentElement?.clientWidth || 340);
    let height = (canvas.height = 240);

    let currMult = 1.00;
    let animId: number;
    let startTime = Date.now();

    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      // Draw Grid Background Lines
      ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
      ctx.lineWidth = 1;
      for (let x = 0; x < width; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += 40) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      if (avState === "flying") {
        const elapsed = (Date.now() - startTime) / 1000;
        currMult = Math.round((1.00 + elapsed * 0.45) * 100) / 100;
        setAvMult(currMult);

        const crashPoint = avCrashRef.current;
        if (currMult >= crashPoint) {
          avStreakRef.current = -1; // Loss streak -> triggers Recovery Bait next round
          setAvState("crashed");
          setAvHistory((prev) => [crashPoint, ...prev.slice(0, 5)]);
          return;
        }

        // Draw Ascending Curve Trail
        const progress = Math.min(1, (currMult - 1) / (crashPoint + 2));
        const planeX = 30 + progress * (width - 70);
        const planeY = height - 30 - Math.pow(progress, 1.4) * (height - 60);

        ctx.beginPath();
        ctx.moveTo(30, height - 30);
        ctx.quadraticCurveTo(width * 0.4, height - 30, planeX, planeY);
        ctx.strokeStyle = "#ff5ccd";
        ctx.lineWidth = 4;
        ctx.shadowBlur = 15;
        ctx.shadowColor = "#ff5ccd";
        ctx.stroke();

        // Draw Jet Rocket Icon
        ctx.font = "26px sans-serif";
        ctx.fillText("🚀", planeX - 12, planeY + 8);
      } else {
        // Static baseline
        ctx.beginPath();
        ctx.moveTo(30, height - 30);
        ctx.lineTo(width - 30, height - 30);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.font = "26px sans-serif";
        ctx.fillText("🚀", 30, height - 20);
      }

      if (avState === "flying") {
        animId = requestAnimationFrame(draw);
      }
    };

    draw();
    return () => cancelAnimationFrame(animId);
  }, [avState, selectedGame]);

  const settleBalance = async (game: string, delta: number, reason: string) => {
    try {
      if (!initData) return;
      const res = await apiPost<{ ok: boolean; newBalance: number }>("/api/webapp/game/settle", { game, delta, reason });
      if (res.ok && typeof res.newBalance === "number" && onBalanceChange) {
        onBalanceChange(res.newBalance);
      }
    } catch (err) {
      console.error("Game settlement error:", err);
    }
  };

  // ── Aviator Smart Engagement & Retention Engine ──
  const avCrashRef = useRef<number>(2.0);
  const avPlayCountRef = useRef<number>(0); // total session rounds
  const avStreakRef = useRef<number>(0);    // >0 = win streak, <0 = loss streak

  const startAviator = () => {
    if (userBalance < bet) {
      alert("Insufficient Balance!");
      return;
    }

    avPlayCountRef.current += 1;
    const playCount = avPlayCountRef.current;
    const streak = avStreakRef.current;
    const r = Math.random();
    let cp: number;

    if (playCount <= 3) {
      // 🎣 PHASE 1: Hook New Player (First 3 Rounds)
      // 85% chance of high multipliers (3.0x - 18.0x) so user wins & gets hooked!
      if (r < 0.85) {
        cp = 3.00 + Math.random() * 15.0; // 3.00x to 18.00x
      } else {
        cp = 1.80 + Math.random() * 1.0;  // 1.80x to 2.80x
      }
    } else if (streak >= 2) {
      // 💣 PHASE 2: Greed Trap (Player won 2+ rounds in a row)
      // 70% chance of early crash (1.05x - 1.85x) to take back winnings when player bets bigger!
      if (r < 0.70) {
        cp = 1.05 + Math.random() * 0.80; // 1.05x to 1.85x (Early Crash!)
      } else {
        cp = 2.50 + Math.random() * 4.0;  // 2.50x to 6.50x
      }
    } else if (streak < 0) {
      // 🪤 PHASE 3: Recovery Bait (Player just lost)
      // 80% chance of a high 3.5x - 12.0x flight to encourage "just one more bet!"
      if (r < 0.80) {
        cp = 3.50 + Math.random() * 8.5;  // 3.50x to 12.00x
      } else {
        cp = 1.40 + Math.random() * 1.0;  // 1.40x to 2.40x
      }
    } else {
      // 🎲 PHASE 4: Dynamic Casino Distribution
      if (r < 0.35) {
        cp = 1.10 + Math.random() * 0.85; // 1.10x to 1.95x
      } else if (r < 0.75) {
        cp = 2.00 + Math.random() * 3.5;  // 2.00x to 5.50x
      } else {
        cp = 5.50 + Math.random() * 14.5; // 5.50x to 20.00x (Jackpot)
      }
    }

    avCrashRef.current = Math.round(cp * 100) / 100;
    settleBalance("aviator", -bet, "Aviator Flight Wager");
    setAvMult(1.00);
    setAvState("flying");
  };

  const cashoutAviator = () => {
    if (avState === "flying") {
      setAvState("cashed");
      const winAmount = Math.round(bet * avMult);
      setAvHistory((prev) => [avMult, ...prev.slice(0, 5)]);
      // Update streak: successful cashout increases win streak
      avStreakRef.current = Math.max(1, avStreakRef.current + 1);
      settleBalance("aviator", winAmount, `Aviator Cashout (${avMult.toFixed(2)}x)`);
    }
  };

  // Roll Ludo Dice
  const rollLudo = () => {
    const dice = Math.floor(Math.random() * 6) + 1;
    setLudoDice(dice);

    if (ludoTurn === 1) {
      setLudoP1Pawns((prev) => {
        const next = [...prev];
        for (let i = 0; i < 4; i++) {
          if (next[i] + dice <= 57) {
            next[i] += dice;
            break;
          }
        }
        return next;
      });
      setLudoTurn(2);
      setLudoStatus(`🔴 Player 1 rolled ${dice}! Opponent's turn.`);
    } else {
      setLudoP2Pawns((prev) => {
        const next = [...prev];
        for (let i = 0; i < 4; i++) {
          if (next[i] + dice <= 57) {
            next[i] += dice;
            break;
          }
        }
        return next;
      });
      setLudoTurn(1);
      setLudoStatus(`🟡 Bot rolled ${dice}! Your turn.`);
    }
  };

  const startMines = () => {
    if (userBalance < bet) {
      alert("Insufficient Balance!");
      return;
    }
    settleBalance("mines", -bet, "Mines Wager");
    const grid = [];
    const mineIndices = new Set<number>();
    while (mineIndices.size < mineCount) {
      mineIndices.add(Math.floor(Math.random() * 25));
    }
    for (let i = 0; i < 25; i++) {
      grid.push({ id: i, isMine: mineIndices.has(i), revealed: false });
    }
    setMinesGrid(grid);
    setMinesActive(true);
    setMinesMult(1.00);
    setMinesGems(0);
  };

  const clickTile = (id: number) => {
    if (!minesActive) return;
    const tile = minesGrid[id];
    if (!tile || tile.revealed) return;

    const newGrid = minesGrid.map((t) => (t.id === id ? { ...t, revealed: true } : t));
    setMinesGrid(newGrid);

    if (tile.isMine) {
      setMinesActive(false);
      // Reveal all tiles upon hit. Bet was already deducted on startMines!
      setMinesGrid(newGrid.map((t) => (t.isMine ? { ...t, revealed: true } : t)));
    } else {
      const newGems = minesGems + 1;
      const step = mineCount === 1 ? 0.05 : mineCount === 3 ? 0.18 : mineCount === 5 ? 0.32 : 0.85;
      const newMult = Math.round((minesMult + step) * 100) / 100;
      setMinesGems(newGems);
      setMinesMult(newMult);
    }
  };

  const autoPickTile = () => {
    if (!minesActive) return;
    const unrevealed = minesGrid.filter((t) => !t.revealed);
    if (unrevealed.length === 0) return;
    const randomTile = unrevealed[Math.floor(Math.random() * unrevealed.length)];
    clickTile(randomTile.id);
  };

  const cashoutMines = () => {
    if (minesActive && minesGems > 0) {
      setMinesActive(false);
      const winAmount = Math.round(bet * minesMult);
      // Reveal remaining gems
      setMinesGrid((prev) => prev.map((t) => ({ ...t, revealed: true })));
      settleBalance("mines", winAmount, `Mines Cashout (${minesMult.toFixed(2)}x)`);
    }
  };

  // Spin Wheel with real Win/Loss Slices & Confetti Victory Popup
  const [spinVictoryModal, setSpinVictoryModal] = useState<{ isWin: boolean; title: string; text: string } | null>(null);

  const triggerSpin = () => {
    if (spinning) return;
    if (userBalance < bet) {
      alert("Insufficient Balance!");
      return;
    }
    settleBalance("spin", -bet, "Spin Wheel Wager");
    setSpinning(true);
    setSpinWinText(null);
    setSpinVictoryModal(null);

    const slices = [
      { label: "2X MULT", mult: 2, isWin: true },
      { label: "0X LOSS", mult: 0, isWin: false },
      { label: "5X MULT", mult: 5, isWin: true },
      { label: "NO WIN", mult: 0, isWin: false },
      { label: "10X JACKPOT", mult: 10, isWin: true },
      { label: "0X LOSS", mult: 0, isWin: false },
    ];

    const idx = Math.floor(Math.random() * slices.length);
    const targetSliceDeg = idx * 60 + 30; // Center of target slice
    const currentRot = spinDegree % 360;
    const spins = 5 * 360; // 5 full revolutions
    const needed = (360 - targetSliceDeg + 270) % 360;
    const newDegree = spinDegree + spins + ((needed - currentRot + 360) % 360);

    setSpinDegree(newDegree);

    setTimeout(() => {
      setSpinning(false);
      const outcome = slices[idx];

      if (outcome.isWin) {
        const winCoins = Math.round(bet * outcome.mult);
        setSpinWinText(`🎉 WON ${outcome.label} (+${money(winCoins)})`);
        setSpinVictoryModal({
          isWin: true,
          title: "🎉 BIG WINNER! 🎉",
          text: `You landed on ${outcome.label} and won +${money(winCoins)} Coins!`
        });
        settleBalance("spin", winCoins, `Spin Wheel Win (${outcome.label})`);
      } else {
        setSpinWinText(`💥 ${outcome.label} (-${money(bet)})`);
        setSpinVictoryModal({
          isWin: false,
          title: "💥 HARD LUCK! 💥",
          text: `You landed on ${outcome.label} and lost -${money(bet)} Coins.`
        });
      }
    }, 3200);
  };

  // Color Bet
  const playColor = () => {
    if (colorSpinning) return;
    if (userBalance < bet) {
      alert("Insufficient Balance!");
      return;
    }
    settleBalance("color", -bet, "Color Bet Wager");
    setColorSpinning(true);
    setColorResult(null);

    setTimeout(() => {
      setColorSpinning(false);
      const colors = ["red", "green", "violet"];
      const outcome = colors[Math.floor(Math.random() * colors.length)] as "red" | "green" | "violet";
      setColorHistory((prev) => [outcome, ...prev.slice(0, 5)]);
      if (outcome === colorChoice) {
        const mult = colorChoice === "violet" ? 4.5 : 2;
        const winAmount = Math.round(bet * mult);
        setColorResult(`🎉 WINNER! Result was ${outcome.toUpperCase()} (+${money(winAmount)})`);
        settleBalance("color", winAmount, `Color Bet Win (${outcome.toUpperCase()})`);
      } else {
        setColorResult(`💥 LOSS! Result was ${outcome.toUpperCase()} (-${money(bet)})`);
      }
    }, 2000);
  };


  return (
    <div className={`arcade-arena ${isDirectMode ? "direct-fullscreen" : ""}`}>
      {/* Top Header Bar for Direct Mode */}
      {isDirectMode && (
        <div className="arena-topbar">
          <button className="back-btn" onClick={() => (window.location.href = window.location.pathname)}>
            <ArrowLeft size={18} /> Exit Arena
          </button>
          <div className="arena-user-balance">
            <span>Balance:</span>
            <strong>${userBalance.toLocaleString()}</strong>
          </div>
        </div>
      )}

      {/* Game Selector Tabs */}
      <div className="arcade-selector">
        <button className={selectedGame === "aviator" ? "active" : ""} onClick={() => setSelectedGame("aviator")}>🚀 Aviator</button>
        <button className={selectedGame === "ludo" ? "active" : ""} onClick={() => setSelectedGame("ludo")}>🎲 Real Ludo</button>
        <button className={selectedGame === "mines" ? "active" : ""} onClick={() => setSelectedGame("mines")}>💎 Mines</button>
        <button className={selectedGame === "spin" ? "active" : ""} onClick={() => setSelectedGame("spin")}>🎰 Spin Wheel</button>
        <button className={selectedGame === "color" ? "active" : ""} onClick={() => setSelectedGame("color")}>🔴🟢 Color Bet</button>
      </div>

      {/* Stake Selector */}
      <div className="arcade-bet-bar">
        <div className="bet-input-wrap">
          <span>💰 Wager:</span>
          <input
            type="number"
            className="bet-num-input"
            value={bet}
            onChange={(e) => setBet(Math.min(500000, Math.max(100, parseInt(e.target.value) || 100)))}
          />
        </div>
        <div className="bet-quick-btns">
          <button className="chip" onClick={() => setBet((b) => Math.max(100, Math.floor(b / 2)))}>½</button>
          <button className="chip" onClick={() => setBet((b) => Math.min(500000, b * 2))}>2×</button>
          <button className="chip" onClick={() => setBet(userBalance > 0 ? Math.min(userBalance, 500000) : 10000)}>MAX</button>
        </div>
        <div className="bet-chips">
          {[500, 1000, 5000, 25000, 100000].map((val) => (
            <button key={val} className={bet === val ? "chip active" : "chip"} onClick={() => setBet(val)}>
              ${val >= 1000 ? `${val / 1000}K` : val}
            </button>
          ))}
        </div>
      </div>

      {/* 🚀 REAL AVIATOR GRAPHICAL CANVAS GAME */}
      {selectedGame === "aviator" && (
        <div className="game-stage aviator-stage">
          <div className="av-history-bar">
            {avHistory.map((h, i) => (
              <span key={i} className={h >= 2.0 ? "high" : "low"}>{h.toFixed(2)}x</span>
            ))}
          </div>
          <div className="stage-header">
            <h3>🚀 Aviator Flight</h3>
            <span className="mult-badge">{avMult.toFixed(2)}x</span>
          </div>
          <div className="canvas-wrapper">
            <canvas ref={canvasRef} className="aviator-canvas" />
            {avState === "crashed" && <div className="av-overlay crash">💥 FLEW AWAY AT {avMult.toFixed(2)}x</div>}
            {avState === "cashed" && <div className="av-overlay win">🎉 CASHED OUT +${Math.round(bet * avMult).toLocaleString()}</div>}
          </div>
          <div className="stage-actions">
            {avState === "idle" && <button className="btn-launch" onClick={startAviator}>🚀 START FLIGHT (${bet.toLocaleString()})</button>}
            {avState === "flying" && <button className="btn-cashout" onClick={cashoutAviator}>💰 CASHOUT (${Math.round(bet * avMult).toLocaleString()})</button>}
            {(avState === "cashed" || avState === "crashed") && <button className="btn-launch" onClick={startAviator}>🔄 FLY AGAIN</button>}
          </div>
        </div>
      )}

      {/* 🎲 REAL 4-COLOR LUDO BOARD ARENA */}
      {selectedGame === "ludo" && (
        <div className="game-stage ludo-stage">
          <div className="stage-header">
            <h3>🎲 Kazumi 4-Color Ludo Board</h3>
            <span>{ludoStatus}</span>
          </div>
          <div className="real-ludo-board">
            {/* 4 Quadrants */}
            <div className="ludo-quad red">
              <span>🔴 Red Quarter</span>
              <div className="pawns-box">{ludoP1Pawns.map((p, i) => <span key={i} className="pawn red">🔴</span>)}</div>
            </div>
            <div className="ludo-quad green">
              <span>🟢 Green Quarter</span>
              <div className="pawns-box"><span className="pawn green">🟢</span></div>
            </div>
            <div className="ludo-quad yellow">
              <span>🟡 Yellow Quarter</span>
              <div className="pawns-box">{ludoP2Pawns.map((p, i) => <span key={i} className="pawn yellow">🟡</span>)}</div>
            </div>
            <div className="ludo-quad blue">
              <span>🔵 Blue Quarter</span>
              <div className="pawns-box"><span className="pawn blue">🔵</span></div>
            </div>
            {/* Center Home */}
            <div className="ludo-center-home">
              <span>🏡 HOME</span>
              <div className="dice-box">🎲 {ludoDice}</div>
            </div>
          </div>
          <div className="stage-actions">
            <button className="btn-launch" onClick={rollLudo}>🎲 ROLL DICE ({ludoTurn === 1 ? "P1 TURN" : "BOT TURN"})</button>
          </div>
        </div>
      )}

      {/* 💎 REAL 5x5 MINESWEEPER ARENA (STAKE UPGRADE) */}
      {selectedGame === "mines" && (
        <div className="game-stage mines-stage" style={{ position: "relative" }}>
          <div className="stage-header">
            <h3>💎 Minesweeper Arena</h3>
            <span>Multiplier: <strong style={{ color: "#3ee7ff" }}>{minesMult.toFixed(2)}x</strong> | Gems: <strong style={{ color: "#7cff9b" }}>{minesGems}</strong></span>
          </div>

          {/* Mine Count Selector Bar */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", marginBottom: "14px", background: "rgba(255,255,255,0.04)", padding: "8px 12px", borderRadius: "12px" }}>
            <span style={{ fontSize: "12px", color: "#94a3b8", fontWeight: "700" }}>💣 MINES:</span>
            <div style={{ display: "flex", gap: "6px" }}>
              {[1, 3, 5, 10].map((count) => (
                <button
                  key={count}
                  className={`chip ${mineCount === count ? "active" : ""}`}
                  onClick={() => !minesActive && setMineCount(count)}
                  disabled={minesActive}
                  style={{ padding: "4px 10px", fontSize: "12px" }}
                >
                  {count} {count === 1 ? "Mine" : "Mines"}
                </button>
              ))}
            </div>
          </div>

          {!minesActive ? (
            <div className="stage-actions">
              <button className="btn-launch" onClick={startMines}>💎 START MINES (${bet.toLocaleString()})</button>
            </div>
          ) : (
            <div className="mines-active-box">
              <div className="mines-grid-5x5">
                {minesGrid.map((tile) => (
                  <button
                    key={tile.id}
                    className={`tile ${tile.revealed ? (tile.isMine ? "mine" : "gem") : ""}`}
                    onClick={() => clickTile(tile.id)}
                  >
                    {tile.revealed ? (tile.isMine ? "💣" : "💎") : "❓"}
                  </button>
                ))}
              </div>
              <div className="stage-actions" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                <button className="btn-launch" onClick={autoPickTile} style={{ background: "linear-gradient(135deg, #a855f7, #6366f1)" }}>
                  🎲 AUTOPICK
                </button>
                <button className="btn-cashout" onClick={cashoutMines} disabled={minesGems === 0}>
                  💰 CASHOUT (${Math.round(bet * minesMult).toLocaleString()})
                </button>
              </div>
            </div>
          )}
        </div>
      )}



      {/* 🎰 REAL LUCKY SPIN WHEEL */}
      {selectedGame === "spin" && (
        <div className="game-stage spin-stage" style={{ position: "relative" }}>
          <div className="stage-header">
            <h3>🎰 Mega Lucky Spin Wheel</h3>
            <span>{spinWinText ? spinWinText : "Spin to win big!"}</span>
          </div>
          <CyberSpinWheelCanvas degree={spinDegree} />
          <div className="stage-actions">
            <button className="btn-launch" onClick={triggerSpin} disabled={spinning}>
              {spinning ? "🎰 SPINNING..." : "🎰 SPIN WHEEL"}
            </button>
          </div>

          {spinVictoryModal && (
            <motion.div
              className={`victory-modal-overlay ${spinVictoryModal.isWin ? "win" : "loss"}`}
              initial={{ scale: 0.7, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              style={{
                position: "absolute",
                inset: 0,
                background: "rgba(7, 9, 20, 0.92)",
                backdropFilter: "blur(12px)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 99,
                padding: "20px",
                borderRadius: "16px"
              }}
            >
              <div className="victory-modal-card" style={{ textAlign: "center", background: "#0d1127", padding: "24px", borderRadius: "18px", border: spinVictoryModal.isWin ? "2px solid #7cff9b" : "2px solid #ef4444", boxShadow: spinVictoryModal.isWin ? "0 0 30px rgba(124, 255, 155, 0.4)" : "0 0 30px rgba(239, 68, 68, 0.4)" }}>
                <h2 style={{ color: spinVictoryModal.isWin ? "#7cff9b" : "#ef4444", margin: "0 0 8px 0", fontSize: "20px" }}>{spinVictoryModal.title}</h2>
                <p style={{ color: "#e2e8f0", fontSize: "15px", marginBottom: "16px" }}>{spinVictoryModal.text}</p>
                <button className="btn-launch" onClick={() => setSpinVictoryModal(null)} style={{ margin: "0 auto", padding: "10px 24px", fontSize: "14px" }}>
                  CONTINUE PLAYING
                </button>
              </div>
            </motion.div>
          )}
        </div>
      )}


      {/* 🔴🟢 REAL COLOR PREDICTION ARENA */}
      {selectedGame === "color" && (
        <div className="game-stage color-stage">
          <div className="color-hist-row">
            <span>Past Results:</span>
            {colorHistory.map((c, i) => (
              <span key={i} className={`color-dot ${c}`}>{c === "red" ? "🔴" : c === "green" ? "🟢" : "🟣"}</span>
            ))}
          </div>
          <div className="stage-header">
            <h3>🔴🟢 Color Prediction</h3>
            <span>{colorResult || "Pick a color!"}</span>
          </div>
          <div className="color-selector">
            <button className={colorChoice === "red" ? "color-btn red active" : "color-btn red"} onClick={() => setColorChoice("red")}>🔴 RED (2x)</button>
            <button className={colorChoice === "green" ? "color-btn green active" : "color-btn green"} onClick={() => setColorChoice("green")}>🟢 GREEN (2x)</button>
            <button className={colorChoice === "violet" ? "color-btn violet active" : "color-btn violet"} onClick={() => setColorChoice("violet")}>🟣 VIOLET (4.5x)</button>
          </div>
          <div className="stage-actions">
            <button className="btn-launch" onClick={playColor} disabled={colorSpinning}>
              {colorSpinning ? "🎰 SPINNING..." : `🎰 PLACE BET ON ${colorChoice.toUpperCase()}`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>(() => initialTab());
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [loanTarget, setLoanTarget] = useState("");
  const [loanAmount, setLoanAmount] = useState("");
  const [payTarget, setPayTarget] = useState("");
  const [payAmount, setPayAmount] = useState("");
  const [adminQuery, setAdminQuery] = useState("");
  const [adminResults, setAdminResults] = useState<AdminBriefUser[]>([]);
  const [adminDetail, setAdminDetail] = useState<AdminUserDetail | null>(null);
  const [adminScope, setAdminScope] = useState<"wallet" | "bank">("wallet");
  const [adminDirection, setAdminDirection] = useState<"add" | "cut">("add");
  const [adminAmount, setAdminAmount] = useState("");
  const [adminReason, setAdminReason] = useState("");
  const [adminBusy, setAdminBusy] = useState(false);
  const premiumRef = useRef<HTMLDivElement | null>(null);

  const demoMode = !initData && !urlUser;

  const isDirectGameMode = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    const hash = window.location.hash.replace("#", "").toLowerCase();
    return Boolean(params.get("game") || ["aviator", "ludo", "mines", "spin", "color"].includes(hash));
  }, []);

  async function refresh() {
    setLoading(true);
    setNotice("");
    try {
      const payload = demoMode ? demoPayload : await loadDashboard();
      setData(payload);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unable to load dashboard";
      if (msg.toLowerCase().includes("fetch") || msg.toLowerCase().includes("network")) {
        console.warn("[KAZUMI SYNC FALLBACK]", msg);
      } else {
        setNotice(msg);
      }
      setData(demoPayload);
    } finally {
      setLoading(false);
    }
  }

  async function claimDaily() {
    try {
      if (demoMode) {
        setNotice("Claimed daily reward in demo mode!");
        return;
      }
      const res = await apiPost<{ ok: boolean; message: string }>("/api/webapp/daily/claim");
      setNotice(res.message || "Daily reward claimed!");
      refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to claim daily reward");
    }
  }

  async function claimPlanReward() {
    try {
      if (demoMode) {
        setNotice("Claimed mission plan reward in demo mode!");
        return;
      }
      const res = await apiPost<{ ok: boolean; message: string }>("/api/webapp/missions/claim");
      setNotice(res.message || "Mission rewards claimed!");
      refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to claim mission reward");
    }
  }

  async function loadAdminDetail(userId: number) {
    if (!adminAvailable) return;
    setAdminBusy(true);
    try {
      const payload = await apiPost<{ ok: boolean; detail: AdminUserDetail }>("/api/webapp/admin/users/detail", { userId });
      setAdminDetail(payload.detail);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "User detail failed");
    } finally {
      setAdminBusy(false);
    }
  }

  async function searchAdminUsers() {
    if (!adminAvailable) return;
    if (adminQuery.trim().length < 2 && !/^\d+$/.test(adminQuery.trim())) {
      setNotice("Search by 2+ letters or full numeric user ID.");
      return;
    }
    setAdminBusy(true);
    try {
      const payload = await apiPost<{ ok: boolean; results: AdminBriefUser[] }>("/api/webapp/admin/users/search", { query: adminQuery });
      setAdminResults(payload.results);
      if (!payload.results.length) {
        setNotice("No matching user found.");
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Search failed");
    } finally {
      setAdminBusy(false);
    }
  }

  async function applyAdminAdjustment() {
    if (!adminAvailable || !adminDetail) return;
    if (!adminAmount.trim() || !adminReason.trim()) {
      setNotice("Amount and reason are both required.");
      return;
    }
    setAdminBusy(true);
    try {
      const payload = await apiPost<{ ok: boolean; message: string; admin: AdminPayload; detail: AdminUserDetail }>("/api/webapp/admin/users/adjust", {
        userId: adminDetail.user.id,
        scope: adminScope,
        direction: adminDirection,
        amount: adminAmount,
        reason: adminReason,
      });
      setData((current) => current && { ...current, admin: payload.admin });
      setAdminDetail(payload.detail);
      setAdminAmount("");
      setAdminReason("");
      setNotice(payload.message);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Adjust failed");
    } finally {
      setAdminBusy(false);
    }
  }

  async function toggleLeaderboardHidden() {
    if (!adminAvailable || !adminDetail) return;
    setAdminBusy(true);
    try {
      const payload = await apiPost<{ ok: boolean; message: string; admin: AdminPayload; detail: AdminUserDetail }>("/api/webapp/admin/users/visibility", {
        userId: adminDetail.user.id,
        hidden: !adminDetail.user.leaderboardHidden,
      });
      setData((current) => current && { ...current, admin: payload.admin });
      setAdminDetail(payload.detail);
      setNotice(payload.message);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Visibility toggle failed");
    } finally {
      setAdminBusy(false);
    }
  }

  async function forgetMemory(key: string) {
    try {
      if (demoMode) {
        setNotice(`Forgot memory key ${key} in demo mode!`);
        return;
      }
      await apiPost("/api/webapp/memory/forget", { key });
      setNotice(`Forgot memory key ${key}!`);
      refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to forget memory");
    }
  }

  async function requestLoan() {
    if (!loanAmount) return;
    try {
      if (demoMode) {
        setNotice("Requested loan in demo mode!");
        return;
      }
      await apiPost("/api/webapp/loans/request", { target: loanTarget, amount: loanAmount });
      setNotice("Loan request sent!");
      setLoanTarget("");
      setLoanAmount("");
      refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Loan request failed");
    }
  }

  async function payLoan() {
    if (!payAmount) return;
    try {
      if (demoMode) {
        setNotice("Repaid loan in demo mode!");
        return;
      }
      await apiPost("/api/webapp/loans/pay", { target: payTarget, amount: payAmount });
      setNotice("Loan repayment successful!");
      setPayTarget("");
      setPayAmount("");
      refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Loan repayment failed");
    }
  }

  useEffect(() => {
    refresh();
  }, []);


  const user = data?.user || demoPayload.user;

  const updateUserBalance = (newBal: number) => {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        user: {
          ...prev.user,
          balance: newBal,
          balanceText: money(newBal),
        },
      };
    });
  };

  if (isDirectGameMode) {
    // Wait until real balance is loaded from API before showing the game
    // Without this, demoPayload.balance (826,767) is used → false "Insufficient Balance" errors
    if (loading || !data) {
      return (
        <div className="direct-fullscreen-stage" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
          <NeonField />
          <div style={{ textAlign: "center", color: "#fff", zIndex: 10, position: "relative" }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🎮</div>
            <div style={{ fontSize: 18, fontWeight: 700, letterSpacing: 2 }}>Loading your balance...</div>
            <div style={{ marginTop: 12, opacity: 0.6, fontSize: 13 }}>Syncing with Kazumi servers</div>
          </div>
        </div>
      );
    }
    return (
      <div className="direct-fullscreen-stage">
        <NeonField />
        <ArcadeView userBalance={user.balance} isDirectMode={true} onBalanceChange={updateUserBalance} />
      </div>
    );
  }

  const leaderboard = data?.leaderboard || demoPayload.leaderboard;
  const admin = data?.admin || null;
  const adminAvailable = Boolean(admin?.canAccess) && !demoMode;
  const visibleTabs = tabs.filter((tab) => !tab.adminOnly || adminAvailable);
  const xpPct = Math.min(100, Math.round((user.xp.current / Math.max(user.xp.needed, 1)) * 100));

  const activeLoans = data?.loans?.active || [];
  const pendingLoans = data?.loans?.pending || [];

  const tabContent = {
    home: (
      <div className="grid two">
        <Section title="Today's Plan" action={data?.missions?.rewardReady ? "Reward ready" : "Daily loop"}>
          <MissionPanel missions={data?.missions || demoPayload.missions} onClaim={claimPlanReward} />
        </Section>
        <Section title="Gang War Room" action={data?.gang?.joined ? "Strategic" : "Recruit"}>
          <GangPanel gang={data?.gang || demoPayload.gang} />
        </Section>
        <Section title="Command Center" action={demoMode ? "Demo mode" : "Live"}>
          <div className="stat-grid">
            <StatCard label="Wallet" value={user.balanceText} icon={WalletCards} tone="cyan" />
            <StatCard label="Rank" value={`#${user.rank}`} icon={Trophy} tone="gold" />
            <StatCard label="Streak" value={`${user.dailyStreak}d`} icon={Sparkles} tone="pink" />
            <StatCard label="Wins" value={String(user.wins)} icon={Swords} tone="green" />
          </div>
          <div className="daily-panel">
            <div>
              <span>Daily Reward</span>
              <strong>{money(data?.daily?.reward || demoPayload.daily.reward)}</strong>
            </div>
            <button onClick={claimDaily} disabled={!data?.daily?.canClaim && !demoMode}>
              {data?.daily?.canClaim || demoMode ? "Claim" : "Cooldown"}
            </button>
          </div>
        </Section>
        <Section title="Current Loadout" action={user.premium ? "Premium" : "Standard"}>
          <div className="loadout">
            <div><Shield size={18} /> <span>{user.status}</span></div>
            <div><Swords size={18} /> <span>{user.gear.weapon?.name || "No weapon"}</span></div>
            <div><HeartPulse size={18} /> <span>{user.gear.armor?.name || "No armor"}</span></div>
            <div><Crown size={18} /> <span>{user.waifuCount} waifus</span></div>
          </div>
        </Section>
        <Section title="Cooldown Planner" action="Next actions">
          <CooldownPanel cooldowns={data?.cooldowns || demoPayload.cooldowns} />
        </Section>
      </div>
    ),
    games: (
      <Section title="Kazumi Master Arcade Deck" action="Interactive Mini App">
        <ArcadeView userBalance={user.balance} onBalanceChange={updateUserBalance} />
      </Section>
    ),

    profile: (
      <div className="grid two">
        <Section title="Profile Core" action={user.rankTitle}>
          <div className="profile-core">
            <div className="avatar-ring">{user.name.slice(0, 1).toUpperCase()}</div>
            <div>
              <h3>{user.name}</h3>
              <p>@{user.username || "telegram"}</p>
            </div>
          </div>
          <div className="xp-track"><span style={{ width: `${xpPct}%` }} /></div>
          <p className="muted">Level {user.level} · {user.xp.current}/{user.xp.needed} XP</p>
        </Section>
        <Section title="Battle Record">
          <div className="stat-grid compact">
            <StatCard label="Kills" value={String(user.kills)} icon={Swords} tone="pink" />
            <StatCard label="Wins" value={String(user.wins)} icon={Medal} tone="green" />
            <StatCard label="Balance" value={user.balanceText} icon={Banknote} tone="gold" />
            <StatCard label="Badges" value={String(user.achievements.length)} icon={Crown} tone="cyan" />
          </div>
        </Section>
        <Section title="Memory Control" action="Personalized chat">
          <MemoryPanel memory={data?.memory || demoPayload.memory} onForget={forgetMemory} />
        </Section>
        <Section title="Cooldowns" action="Limits">
          <CooldownPanel cooldowns={data?.cooldowns || demoPayload.cooldowns} />
        </Section>
      </div>
    ),
    history: (
      <div className="grid two">
        <Section title="Balance Log" action="Today">
          <HistoryPanel history={data?.history || demoPayload.history} />
        </Section>
        <Section title="Next Best Moves" action="Retention loop">
          <div className="leader-list">
            <div className="leader-row">
              <span className="leader-rank">1</span>
              <span className="leader-name">Claim daily, then clear missions</span>
              <strong>{money((data?.daily?.reward || demoPayload.daily.reward) + (data?.missions?.fullReward || demoPayload.missions.fullReward))}</strong>
            </div>
            <div className="leader-row">
              <span className="leader-rank">2</span>
              <span className="leader-name">Repay loans to reduce debt pressure</span>
              <strong>{money(data?.loans?.owed || 0)}</strong>
            </div>
          </div>
        </Section>
      </div>
    ),
    loans: (
      <div className="grid two">
        <Section title="Loan Console" action={`Owe ${money(data?.loans?.owed || 0)}`}>
          <div className="form-grid">
            <input value={loanTarget} onChange={(event) => setLoanTarget(event.target.value)} placeholder="@user or ID" />
            <input value={loanAmount} onChange={(event) => setLoanAmount(event.target.value)} placeholder="Amount" inputMode="numeric" />
            <button onClick={requestLoan}>Ask Loan</button>
          </div>
          <div className="form-grid">
            <input value={payTarget} onChange={(event) => setPayTarget(event.target.value)} placeholder="Lender optional" />
            <input value={payAmount} onChange={(event) => setPayAmount(event.target.value)} placeholder="Repay amount" inputMode="numeric" />
            <button onClick={payLoan}>Repay</button>
          </div>
        </Section>
        <Section title="Active Debts" action={`${pendingLoans.length} pending`}>
          <div className="loan-list">
            {activeLoans.length ? activeLoans.map((loan) => <LoanRow loan={loan} key={loan.requestId} />) : <p className="muted">No active loans.</p>}
          </div>
        </Section>
      </div>
    ),
    leaderboard: (
      <div className="grid two">
        <Section title="Richest" action="Live first"><LeaderList rows={leaderboard.rich} /></Section>
        <Section title="Top Killers"><LeaderList rows={leaderboard.killers} mode="number" /></Section>
        <Section title="Game Winners"><LeaderList rows={leaderboard.winners} mode="number" /></Section>
        <Section title="Loan Debt"><LeaderList rows={leaderboard.debt} /></Section>
      </div>
    ),
    shop: (
      <div className="grid two">
        <div ref={premiumRef} className="premium-anchor">
          <Section title="Premium Plan" action={data?.premium?.active ? "Active" : "Buy"}>
            <PremiumPanel premium={data?.premium || demoPayload.premium} demoMode={demoMode} onRefresh={refresh} />
          </Section>
        </div>
        <Section title="Market Preview" action={`${data?.shop?.length || 0} items`}>
          <div className="shop-grid">
            {(data?.shop || []).slice(0, 18).map((item) => <ShopTile item={item} key={item.id} />)}
          </div>
        </Section>
      </div>
    ),
    admin: (
      <div className="grid two">
        <Section title="Admin Radar" action={admin?.role || "sudo"}>
          <div className="stat-grid compact">
            <StatCard label="Users" value={String(admin?.summary?.totalUsers || 0)} icon={UserRound} tone="cyan" />
            <StatCard label="Hidden" value={String(admin?.summary?.hiddenUsers || 0)} icon={Shield} tone="pink" />
            <StatCard label="Active Loans" value={String(admin?.summary?.activeLoans || 0)} icon={Landmark} tone="gold" />
            <StatCard label="Pending" value={String(admin?.summary?.pendingLoans || 0)} icon={Clock3} tone="green" />
          </div>
          <div className="admin-highlight" style={{ marginTop: 12 }}>
            <span>Top visible wallet</span>
            <strong>{admin?.summary?.topVisibleName || "No one yet"} • {admin?.summary?.topVisibleBalanceText || "$0"}</strong>
          </div>
          <div className="admin-queue" style={{ marginTop: 12 }}>
            {(admin?.queue || []).length ? (admin?.queue || []).map((row) => (
              <AdminUserCard key={row.id} user={row} onPick={loadAdminDetail} />
            )) : <p className="muted">No hidden users in the queue right now.</p>}
          </div>
        </Section>
        <Section title="Search Target" action="ID / username / name">
          <div className="admin-search">
            <input value={adminQuery} onChange={(event) => setAdminQuery(event.target.value)} placeholder="@user, name, or numeric ID" />
            <button onClick={searchAdminUsers} disabled={adminBusy}><Search size={16} /> Search</button>
          </div>
          <div className="admin-queue" style={{ marginTop: 12 }}>
            {adminResults.length ? adminResults.map((row) => (
              <AdminUserCard key={`search-${row.id}`} user={row} onPick={loadAdminDetail} />
            )) : <p className="muted">Search results will land here. Pick one to open forensic view.</p>}
          </div>
        </Section>
        <Section title="Money Forensics" action={adminDetail ? adminDetail.user.name : "Pick a user"}>
          {adminDetail ? (
            <div className="admin-detail-shell">
              <div className="admin-target-head">
                <div>
                  <h3>{adminDetail.user.name}</h3>
                  <p>{adminDetail.user.username ? `@${adminDetail.user.username}` : `ID ${adminDetail.user.id}`}</p>
                </div>
                <span className={adminDetail.user.leaderboardHidden ? "admin-badge danger" : "admin-badge"}>
                  {adminDetail.user.leaderboardHidden ? "Hidden" : "Visible"}
                </span>
              </div>
              <div className="stat-grid compact">
                <StatCard label="Wallet" value={adminDetail.user.balanceText} icon={WalletCards} tone="cyan" />
                <StatCard label="Bank" value={adminDetail.user.bankText} icon={Banknote} tone="gold" />
                <StatCard label="Wealth" value={adminDetail.user.wealthText} icon={BadgeDollarSign} tone="pink" />
                <StatCard label="Debt" value={money(adminDetail.loans.owed)} icon={Landmark} tone="green" />
              </div>
              <div className="admin-signal-grid" style={{ marginTop: 12 }}>
                <div className="admin-signal-card">
                  <span>24h Net</span>
                  <strong>{adminDetail.forensics.day1.netText}</strong>
                </div>
                <div className="admin-signal-card">
                  <span>7d Net</span>
                  <strong>{adminDetail.forensics.day7.netText}</strong>
                </div>
              </div>
              <div className="admin-flags" style={{ marginTop: 12 }}>
                {adminDetail.flags.length ? adminDetail.flags.map((flag, index) => (
                  <div className={`admin-flag ${flag.tone}`} key={`${flag.label}-${index}`}>
                    <AlertTriangle size={14} />
                    <div>
                      <strong>{flag.label}</strong>
                      <span>{flag.detail}</span>
                    </div>
                  </div>
                )) : <p className="muted">No major risk flags on the current snapshot.</p>}
              </div>
              <div className="admin-breakdown-grid" style={{ marginTop: 12 }}>
                <AdminBreakdownList title="Credit Categories" rows={adminDetail.forensics.creditCategories} />
                <AdminBreakdownList title="Credit Sources" rows={adminDetail.forensics.creditSources} />
                <AdminBreakdownList title="Debit Categories" rows={adminDetail.forensics.debitCategories} />
              </div>
              <div className="history-list compact" style={{ marginTop: 12 }}>
                {adminDetail.history.recent.length ? adminDetail.history.recent.slice(0, 8).map((entry, index) => (
                  <div className={`history-row ${entry.direction}`} key={`${entry.createdAt || entry.reason}-${index}`}>
                    <div className="history-copy">
                      <div className="history-topline">
                        <strong>{entry.reason}</strong>
                        <b>{entry.amountText}</b>
                      </div>
                      <div className="history-meta">
                        <span>{entry.scopeLabel || "Wallet"} • {entry.category.replace(/_/g, " ")}</span>
                        <span>{entry.oldValueText || entry.oldBalanceText}{" -> "}{entry.newValueText || entry.newBalanceText}</span>
                        <span>{historyTime(entry.createdAt)}</span>
                      </div>
                    </div>
                  </div>
                )) : <p className="muted">No history rows yet.</p>}
              </div>
              <AdminAuditList rows={adminDetail.audit} />
            </div>
          ) : <p className="muted">Pick a hidden user from queue or search any player to see wallet source, loans, flow, and admin audit log.</p>}
        </Section>
        <Section title="Admin Controls" action="Audit logged">
          {adminDetail ? (
            <div className="admin-control-shell">
              <div className="admin-toggle-group" role="group" aria-label="Adjust scope">
                <button className={adminScope === "wallet" ? "active" : ""} onClick={() => setAdminScope("wallet")}>Wallet</button>
                <button className={adminScope === "bank" ? "active" : ""} onClick={() => setAdminScope("bank")}>Bank</button>
              </div>
              <div className="admin-toggle-group" role="group" aria-label="Adjust direction" style={{ marginTop: 8 }}>
                <button className={adminDirection === "add" ? "active" : ""} onClick={() => setAdminDirection("add")}>Add Coins</button>
                <button className={adminDirection === "cut" ? "active" : ""} onClick={() => setAdminDirection("cut")}>Cut Coins</button>
              </div>
              <div className="form-grid" style={{ marginTop: 12 }}>
                <input value={adminAmount} onChange={(event) => setAdminAmount(event.target.value)} placeholder="Amount" inputMode="numeric" />
                <input value={adminReason} onChange={(event) => setAdminReason(event.target.value)} placeholder="Reason for audit trail" />
              </div>
              <div className="admin-control-actions" style={{ marginTop: 12 }}>
                <button onClick={applyAdminAdjustment} disabled={adminBusy}>Apply Adjustment</button>
                <button className="ghost" onClick={toggleLeaderboardHidden} disabled={adminBusy}>
                  {adminDetail.user.leaderboardHidden ? "Show On Leaderboard" : "Hide From Leaderboard"}
                </button>
              </div>
              <p className="muted" style={{ marginTop: 8 }}>Every change is tied to your Telegram admin ID and stored in admin_audit_logs.</p>
            </div>
          ) : <p className="muted">Load a target user first to unlock wallet, bank, and leaderboard controls.</p>}
        </Section>
      </div>
    )
  };



  return (
    <div className="app-shell">
      <NeonField />
      <div className="app-glow" />
      <header className="hero">
        <div className="hero-copy">
          <div className="brand-lockup">
            <span className="hero-mark">✿</span>
            <div>
              <h1>Kazumi Command Center</h1>
              <p>Wallet, games, loans, profile and streaks in one Telegram cockpit.</p>
            </div>
          </div>
          <div className="hero-actions">
            <button onClick={() => openBot()}><Bot size={18} /> Open Bot <ChevronRight size={16} /></button>
            <button className="ghost" onClick={refresh}>{loading ? <Loader2 className="spin" size={18} /> : <Sparkles size={18} />} Sync</button>
          </div>
        </div>
        <motion.div className="hero-orbit" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
          <span>{user.balanceText}</span>
          <strong>Lv.{user.level}</strong>
          <small>{user.status}</small>
        </motion.div>
      </header>

      <section className="instant-leaderboard" aria-label="Top leaderboard preview">
        <HeroLeaderboard rows={leaderboard.rich} />
      </section>

      {notice ? <div className="notice">{notice}</div> : null}

      <nav className="tabbar">
        {visibleTabs.map(({ key, label, icon: Icon }) => (
          <button className={activeTab === key ? "active" : ""} key={key} onClick={() => setActiveTab(key)}>
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <main>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 18, filter: "blur(8px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -12, filter: "blur(8px)" }}
            transition={{ duration: 0.28 }}
          >
            {loading && !data ? <div className="loading"><Loader2 className="spin" /> Syncing Kazumi...</div> : tabContent[activeTab]}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );

}

function Section({ title, action, children }: { title: string; action?: string; children: React.ReactNode }) {
  return (
    <section className="section-shell">
      <div className="section-head">
        <h2>{title}</h2>
        {action && <span>{action}</span>}
      </div>
      {children}
    </section>
  );
}

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error: string }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: "" };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error?.message || "Render error" };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("Kazumi App Error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "40px 20px", textAlign: "center", color: "#fff", background: "#070914", minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          <h2 style={{ color: "#ff5ccd", marginBottom: "12px" }}>✿ Kazumi Command Center</h2>
          <p style={{ color: "#94a3b8", marginBottom: "20px" }}>Cockpit auto-recovered from a rendering glitch.</p>
          <p style={{ color: "#f87171", fontSize: "12px", fontFamily: "monospace", marginBottom: "24px", maxWidth: "90%", overflowWrap: "break-word" }}>{this.state.error}</p>
          <button
            onClick={() => { this.setState({ hasError: false }); window.location.reload(); }}
            style={{ padding: "12px 24px", borderRadius: "12px", background: "linear-gradient(135deg, #ff5ccd, #3ee7ff)", color: "#fff", fontWeight: 700, border: "none", cursor: "pointer" }}
          >
            Reload Cockpit 🔄
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function AppWithBoundary() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}

