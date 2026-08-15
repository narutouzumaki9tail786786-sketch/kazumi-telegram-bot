from datetime import datetime
from math import prod


DEFAULT_MIN_BET = 100
DEFAULT_MAX_BET = 500_000
FARM_GAME_DAILY_CAP = 50_000
TELEGRAM_SYSTEM_USER_IDS = {1087968824, 136817688}
BANK_INTEREST_COOLDOWN_SECONDS = 48 * 3600
MAX_BANK_BALANCE = 1_000_000_000_000_000_000  # Unlimited Bank Balance
MAX_BANK_INTEREST_PAYOUT = 25_000_000
MIN_MARKET_PRICE = 1.0
MAX_INVEST_BUY_AMOUNT = 30_000_000
MAX_INVEST_RETURN_MULTIPLIER = 3.0


def resolve_target_source(*, has_reply, explicit_target):
    if has_reply and explicit_target:
        return "conflict"
    if has_reply:
        return "reply"
    if explicit_target:
        return "argument"
    return "missing"


def validate_bet(bet, *, balance, minimum=DEFAULT_MIN_BET, maximum=DEFAULT_MAX_BET):
    from kazumi.utils import parse_money
    if str(bet).strip().startswith("-"):
        return "Bet must be a positive amount."
    parsed = parse_money(bet)
    if parsed == "all":
        amount = min(int(balance or 0), int(maximum))
    elif isinstance(parsed, int):
        amount = parsed
    else:
        return "Invalid bet amount."
    if amount <= 0 or amount < int(minimum) or amount > int(maximum):
        return f"Bet must be between ${int(minimum):,} and ${int(maximum):,}."
    if int(balance or 0) < amount:
        return "Not enough coins."
    return None


def capped_daily_payout(requested, earned_today, daily_cap=FARM_GAME_DAILY_CAP):
    requested = max(0, int(requested or 0))
    earned_today = max(0, int(earned_today or 0))
    daily_cap = max(0, int(daily_cap or 0))
    remaining = max(0, daily_cap - earned_today)
    return min(requested, remaining)


def leaderboard_eligible(user):
    try:
        user_id = int((user or {}).get("user_id", 0))
    except (TypeError, ValueError):
        return False
    return (
        user_id > 0
        and user_id not in TELEGRAM_SYSTEM_USER_IDS
        and not bool((user or {}).get("is_bot"))
        and not bool((user or {}).get("leaderboard_hidden"))
    )


def leaderboard_filter():
    return {
        "user_id": {"$gt": 0, "$nin": sorted(TELEGRAM_SYSTEM_USER_IDS)},
        "is_bot": {"$ne": True},
        "leaderboard_hidden": {"$ne": True},
    }


def highlow_profile(level):
    level = max(0, int(level or 0))
    if level < 5:
        return {"name": "Newbie", "max_rounds": 3, "multipliers": [1.35, 1.75, 2.35]}
    if level < 15:
        return {"name": "Rookie", "max_rounds": 4, "multipliers": [1.4, 1.85, 2.45, 3.3]}
    if level < 30:
        return {"name": "Pro", "max_rounds": 5, "multipliers": [1.45, 1.9, 2.5, 3.3, 4.5]}
    return {"name": "Veteran", "max_rounds": 6, "multipliers": [1.5, 2.0, 2.65, 3.55, 4.8, 6.5]}


def safe_turn_index(alive, current_idx):
    if not alive:
        return None
    return int(current_idx or 0) % len(alive)


def validate_mines_count(mines):
    try:
        count = int(mines)
    except (TypeError, ValueError):
        return "Mine count must be a number."
    if count < 1 or count > 8:
        return "Mine count must be between 1 and 8."
    return None


def mines_multiplier(*, total_cells, mines, revealed_safe, house_edge=0.05):
    total_cells = int(total_cells)
    mines = int(mines)
    revealed_safe = int(revealed_safe)
    safe_cells = total_cells - mines
    if total_cells <= 0 or mines <= 0 or safe_cells <= 0:
        raise ValueError("Invalid board configuration.")
    if revealed_safe <= 0:
        return 1.0
    if revealed_safe > safe_cells:
        raise ValueError("Too many safe cells revealed.")
    survival_probability = prod(
        (safe_cells - step) / (total_cells - step)
        for step in range(revealed_safe)
    )
    return round((1.0 - float(house_edge)) / survival_probability, 4)


def memory_match_multiplier(mistakes):
    mistakes = max(0, int(mistakes or 0))
    if mistakes <= 1:
        return 2.0
    if mistakes <= 3:
        return 1.6
    if mistakes <= 7:
        return 1.25
    return 0.0


def dice_duel_result(p1_roll, p2_roll):
    p1_roll = int(p1_roll)
    p2_roll = int(p2_roll)
    if p1_roll == p2_roll:
        return "tie"
    return "p1" if p1_roll > p2_roll else "p2"


def bank_interest_payout(balance, *, rate=0.05):
    balance = max(0, int(balance or 0))
    if balance <= 0 or balance >= MAX_BANK_BALANCE:
        return 0
    raw = int(balance * float(rate))
    room = max(0, int(MAX_BANK_BALANCE - balance))
    return max(0, min(raw, room, MAX_BANK_INTEREST_PAYOUT))


def safe_market_price(raw_price, fallback):
    try:
        value = float(raw_price)
    except (TypeError, ValueError):
        value = float(fallback)
    return max(float(MIN_MARKET_PRICE), value)


def safe_invest_sell_value(amount, buy_price, current_price, bought_at=None):
    amount = max(0, int(amount or 0))
    if amount <= 0:
        return 0
    buy = safe_market_price(buy_price, MIN_MARKET_PRICE)
    current = safe_market_price(current_price, buy)

    price_ratio = current / buy if buy > 0 else 1.0

    # HODL Yield Bonus: +1.5% extra return for every 15 minutes held (up to +60% max yield bonus)
    hold_yield_bonus = 0.0
    if bought_at:
        try:
            if isinstance(bought_at, str):
                bought_at = datetime.fromisoformat(bought_at)
            if isinstance(bought_at, datetime):
                time_held_seconds = (datetime.utcnow() - bought_at.replace(tzinfo=None)).total_seconds()
                quarter_hours = max(0, int(time_held_seconds // 900))
                hold_yield_bonus = min(0.60, quarter_hours * 0.015)
        except Exception:
            pass

    # Bullish gaming multiplier: guarantee +5% minimum base profit + hold yield bonus when market is normal/up
    effective_ratio = price_ratio + hold_yield_bonus
    if price_ratio >= 0.95:  # Market didn't collapse (> -5%)
        effective_ratio = max(1.05 + hold_yield_bonus, effective_ratio)

    gross = int(amount * effective_ratio)
    cap = int(amount * float(MAX_INVEST_RETURN_MULTIPLIER))
    return max(0, min(gross, cap))
