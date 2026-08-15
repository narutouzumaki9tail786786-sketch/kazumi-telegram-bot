GAME_EXPIRE_SECONDS = 15 * 60
IDLE_FEE_RATE = 0.05


def idle_fee_amount(bet):
    bet = int(bet or 0)
    if bet <= 0:
        return 0
    return max(1, int(bet * IDLE_FEE_RATE))


def idle_refund_amount(bet):
    bet = int(bet or 0)
    return max(0, bet - idle_fee_amount(bet))


def refund_locked_bet(user_id, bet, *, idle=False, adjust_user_balance, chat_id=None, source="game_expire", meta=None):
    bet = int(bet or 0)
    if bet <= 0:
        return {"refund": 0, "fee": 0}
    fee = idle_fee_amount(bet) if idle else 0
    refund = max(0, bet - fee)
    if refund:
        adjust_user_balance(
            user_id,
            refund,
            "game_refund" if not idle else "game_idle_refund",
            "Game expired refund" if not idle else "Game expired with idle fee",
            chat_id=chat_id,
            source=source,
            meta={**(meta or {}), "bet": bet, "idle_fee": fee},
        )
    return {"refund": refund, "fee": fee}


def expire_minutes(seconds=GAME_EXPIRE_SECONDS):
    return max(1, int(seconds // 60))
