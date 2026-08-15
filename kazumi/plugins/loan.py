import re
import uuid
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from kazumi.database import loans_collection, users_collection
from kazumi.ledger import adjust_user_balance, transfer_user_balance
from kazumi.utils import ensure_user_exists, format_money, get_mention, resolve_target, stylize_text
from kazumi.missions import track_mission


MAX_LOAN = 1_000_000_000
MAX_ACTIVE_LOAN_EXPOSURE = 1_000_000_000
LOAN_TERM_DAYS = 3
LOAN_OVERDUE_PENALTY_RATE = 0.10
LOAN_MIN_COLLECTION = 100
LOAN_COLLECTION_COOLDOWN = timedelta(hours=12)


def parse_money(value):
    cleaned = re.sub(r"[$,\s_]", "", value.strip())
    return int(cleaned) if cleaned.isdigit() else None


def split_amount_target(args):
    amount = None
    target = None
    numeric = []
    for arg in args:
        parsed = parse_money(arg)
        if parsed is None:
            target = arg
        else:
            numeric.append((arg, parsed))

    if target:
        if numeric:
            amount = numeric[0][1]
        return amount, target

    if len(numeric) == 1:
        return numeric[0][1], None

    if len(numeric) >= 2:
        target_index = None
        for i, (_, value) in enumerate(numeric[:2]):
            if users_collection.find_one({"user_id": value}):
                target_index = i
                break
        if target_index is None:
            for i, (raw, value) in enumerate(numeric[:2]):
                other = numeric[1 - i]
                if len(str(value)) >= 7 and (len(str(other[1])) < 7 or any(ch in other[0] for ch in "$, _")):
                    target_index = i
                    break
        if target_index is not None:
            target = str(numeric[target_index][1])
            amount = numeric[1 - target_index][1]
        else:
            amount = numeric[0][1]
            target = str(numeric[1][1])
    return amount, target


def loan_buttons(request_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Accept", callback_data=f"loan_accept|{request_id}"),
            InlineKeyboardButton("Deny", callback_data=f"loan_deny|{request_id}"),
        ]
    ])


def loan_help_text():
    return (
        f"\U0001F4B3 <b>{stylize_text('Loan System')}</b>\n\n"
        "<b>Ask loan:</b> <code>/loan 500 @user</code>\n"
        "<b>Give loan:</b> <code>/loan give 500 @user</code>\n"
        "<b>Repay:</b> <code>/loan pay 500 @user</code>\n"
        "<b>Repay oldest:</b> <code>/loan pay 500</code>\n"
        "<b>Collect overdue:</b> <code>/loan collect @user</code>\n"
        "<b>Status:</b> <code>/loan status</code>\n"
        "<b>Pending:</b> <code>/loan requests</code>\n"
        "<b>Top debt:</b> <code>/loan top</code>\n\n"
        f"<i>Loans are due in {LOAN_TERM_DAYS} days. Overdue loans can get a 10% penalty and lender vasuli.</i>"
    )


def active_debt_filter(borrower_id=None, lender_id=None):
    query = {"status": "active", "$expr": {"$lt": ["$paid", "$amount"]}}
    if borrower_id is not None:
        query["borrower_id"] = borrower_id
    if lender_id is not None:
        query["lender_id"] = lender_id
    return query


def remaining(loan):
    return max(0, int(loan.get("amount", 0)) - int(loan.get("paid", 0)))


def active_exposure_total(*, borrower_id=None, lender_id=None):
    return sum(remaining(loan) for loan in loans_collection.find(active_debt_filter(borrower_id, lender_id)))


def loan_due_at():
    return datetime.utcnow() + timedelta(days=LOAN_TERM_DAYS)


def is_overdue(loan):
    due_at = loan.get("due_at")
    return bool(due_at and due_at < datetime.utcnow() and remaining(loan) > 0)


def due_label(loan):
    due_at = loan.get("due_at")
    if not due_at:
        return "No due date"
    if due_at < datetime.utcnow():
        return "OVERDUE"
    return due_at.strftime("%d %b")


def collection_cooldown_left(loans):
    last_attempts = [
        loan.get("last_collect_attempt")
        for loan in loans
        if isinstance(loan.get("last_collect_attempt"), datetime)
    ]
    if not last_attempts:
        return None
    ready_at = max(last_attempts) + LOAN_COLLECTION_COOLDOWN
    left = ready_at - datetime.utcnow()
    return left if left.total_seconds() > 0 else None


def short_duration(delta):
    total = max(0, int(delta.total_seconds()))
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{max(1, minutes)}m"


def apply_overdue_penalty(loan):
    if not is_overdue(loan) or loan.get("penalty_applied_at"):
        return 0
    penalty = max(1, int(remaining(loan) * LOAN_OVERDUE_PENALTY_RATE))
    loans_collection.update_one(
        {"_id": loan["_id"], "status": "active", "penalty_applied_at": {"$exists": False}},
        {"$inc": {"amount": penalty}, "$set": {"penalty_applied_at": datetime.utcnow()}},
    )
    return penalty


async def ask_loan(update, context, args):
    borrower = ensure_user_exists(update.effective_user)
    amount, target_arg = split_amount_target(args)
    if amount is None or amount <= 0 or amount > MAX_LOAN:
        return await update.message.reply_text("\U000026A0\ufe0f Usage: <code>/loan 500 @user</code>", parse_mode=ParseMode.HTML)
    if active_exposure_total(borrower_id=borrower["user_id"]) + amount > MAX_ACTIVE_LOAN_EXPOSURE:
        return await update.message.reply_text(
            f"\U0001F6AB Borrow limit reached. Clear some debt first.\nMax active debt: <code>{format_money(MAX_ACTIVE_LOAN_EXPOSURE)}</code>.",
            parse_mode=ParseMode.HTML,
        )

    lender, error = await resolve_target(update, context, specific_arg=target_arg)
    if not lender:
        return await update.message.reply_text(error or "\U000026A0\ufe0f Tag lender.", parse_mode=ParseMode.HTML)
    if lender["user_id"] == borrower["user_id"]:
        return await update.message.reply_text("\U0000274C You cannot borrow from yourself.", parse_mode=ParseMode.HTML)
    if active_exposure_total(lender_id=lender["user_id"]) + amount > MAX_ACTIVE_LOAN_EXPOSURE:
        return await update.message.reply_text(
            f"\U0001F6AB Lender exposure limit reached.\nMax active lending: <code>{format_money(MAX_ACTIVE_LOAN_EXPOSURE)}</code>.",
            parse_mode=ParseMode.HTML,
        )

    request_id = str(uuid.uuid4())[:10]
    loans_collection.insert_one({
        "request_id": request_id,
        "borrower_id": borrower["user_id"],
        "borrower_name": borrower.get("name", "User"),
        "lender_id": lender["user_id"],
        "lender_name": lender.get("name", "User"),
        "amount": amount,
        "paid": 0,
        "status": "pending",
        "created_at": datetime.utcnow(),
    })

    await update.message.reply_text(
        f"\U0001F4B8 <b>{stylize_text('Loan Request')}</b>\n\n"
        f"{get_mention(borrower)} asks {get_mention(lender)} for <code>{format_money(amount)}</code>.\n"
        "<i>Lender must accept.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=loan_buttons(request_id),
    )
    track_mission(borrower["user_id"], "loan_action")


async def give_loan(update, context, args):
    lender = ensure_user_exists(update.effective_user)
    amount, target_arg = split_amount_target(args)
    if amount is None or amount <= 0 or amount > MAX_LOAN:
        return await update.message.reply_text("\U000026A0\ufe0f Usage: <code>/loan give 500 @user</code>", parse_mode=ParseMode.HTML)
    if lender.get("balance", 0) < amount:
        return await update.message.reply_text("\U0001F4C9 Not enough coins to lend.", parse_mode=ParseMode.HTML)
    if active_exposure_total(lender_id=lender["user_id"]) + amount > MAX_ACTIVE_LOAN_EXPOSURE:
        return await update.message.reply_text(
            f"\U0001F6AB Active lending limit reached.\nMax active lending: <code>{format_money(MAX_ACTIVE_LOAN_EXPOSURE)}</code>.",
            parse_mode=ParseMode.HTML,
        )

    borrower, error = await resolve_target(update, context, specific_arg=target_arg)
    if not borrower:
        return await update.message.reply_text(error or "\U000026A0\ufe0f Tag borrower.", parse_mode=ParseMode.HTML)
    if borrower["user_id"] == lender["user_id"]:
        return await update.message.reply_text("\U0000274C You cannot loan yourself.", parse_mode=ParseMode.HTML)
    if active_exposure_total(borrower_id=borrower["user_id"]) + amount > MAX_ACTIVE_LOAN_EXPOSURE:
        return await update.message.reply_text(
            f"\U0001F6AB Borrower debt limit reached.\nMax active debt: <code>{format_money(MAX_ACTIVE_LOAN_EXPOSURE)}</code>.",
            parse_mode=ParseMode.HTML,
        )

    transferred = transfer_user_balance(
        lender["user_id"],
        borrower["user_id"],
        amount,
        debit_category="loan_lend",
        debit_reason=f"Loaned coins to {borrower.get('name', 'user')}",
        credit_category="loan_receive",
        credit_reason=f"Received loan from {lender.get('name', 'user')}",
        refund_category="loan_refund",
        refund_reason=f"Loan delivery to {borrower.get('name', 'user')} failed",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/loan give",
        meta={"amount": amount},
    )
    if not transferred:
        return await update.message.reply_text(
            "\U0001F4C9 Loan could not be delivered. Any deducted coins were refunded.",
            parse_mode=ParseMode.HTML,
        )
    loans_collection.insert_one({
        "request_id": str(uuid.uuid4())[:10],
        "borrower_id": borrower["user_id"],
        "borrower_name": borrower.get("name", "User"),
        "lender_id": lender["user_id"],
        "lender_name": lender.get("name", "User"),
        "amount": amount,
        "paid": 0,
        "status": "active",
        "created_at": datetime.utcnow(),
        "accepted_at": datetime.utcnow(),
        "due_at": loan_due_at(),
    })

    await update.message.reply_text(
        f"\U00002705 <b>{stylize_text('Loan Sent')}</b>\n"
        f"{get_mention(lender)} loaned <code>{format_money(amount)}</code> to {get_mention(borrower)}.",
        parse_mode=ParseMode.HTML,
    )
    track_mission(lender["user_id"], "loan_action")


async def repay_loan(update, context, args):
    borrower = ensure_user_exists(update.effective_user)
    amount, target_arg = split_amount_target(args)
    if amount is None or amount <= 0:
        return await update.message.reply_text("\U000026A0\ufe0f Usage: <code>/loan pay 500 @user</code>", parse_mode=ParseMode.HTML)
    if borrower.get("balance", 0) < amount:
        return await update.message.reply_text("\U0001F4C9 Not enough coins to repay.", parse_mode=ParseMode.HTML)

    lender_id = None
    if target_arg:
        lender, error = await resolve_target(update, context, specific_arg=target_arg)
        if not lender:
            return await update.message.reply_text(error or "\U000026A0\ufe0f Tag lender.", parse_mode=ParseMode.HTML)
        lender_id = lender["user_id"]

    loans = list(loans_collection.find(active_debt_filter(borrower["user_id"], lender_id)).sort("created_at", 1))
    if not loans:
        return await update.message.reply_text("\U00002705 No active loan found.", parse_mode=ParseMode.HTML)

    left = amount
    paid_total = 0
    lenders_paid = {}
    payment_plan = []
    for loan in loans:
        if left <= 0:
            break
        pay_now = min(left, remaining(loan))
        left -= pay_now
        paid_total += pay_now
        lenders_paid[loan["lender_id"]] = lenders_paid.get(loan["lender_id"], 0) + pay_now
        new_paid = int(loan.get("paid", 0)) + pay_now
        payment_plan.append((loan["_id"], pay_now, new_paid >= int(loan["amount"])))

    if paid_total <= 0:
        return await update.message.reply_text("\U00002705 No active loan found.", parse_mode=ParseMode.HTML)

    charged = adjust_user_balance(
        borrower["user_id"],
        -paid_total,
        "loan_repay",
        "Repaid active loans",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        source="/loan pay",
        require_gte=paid_total,
        meta={"requested_amount": amount, "paid_total": paid_total},
    )
    if not charged:
        return await update.message.reply_text("\U0001F4C9 Not enough coins to repay.", parse_mode=ParseMode.HTML)

    now = datetime.utcnow()
    for loan_id, pay_now, is_paid in payment_plan:
        update_doc = {"$inc": {"paid": pay_now}}
        if is_paid:
            update_doc["$set"] = {"status": "paid", "paid_at": now}
        loans_collection.update_one({"_id": loan_id, "status": "active"}, update_doc)

    for uid, paid in lenders_paid.items():
        lender_doc = users_collection.find_one({"user_id": uid}) or {}
        adjust_user_balance(
            uid,
            paid,
            "loan_collect",
            f"Collected loan repayment from {borrower.get('name', 'user')}",
            chat_id=update.effective_chat.id if update.effective_chat else None,
            target_user_id=borrower["user_id"],
            source="/loan pay",
            meta={"amount": paid, "lender_name": lender_doc.get("name")},
        )
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"\U0001F4B8 <b>{stylize_text('Loan Payment Received')}</b>\n"
                    f"{get_mention(borrower)} paid you <code>{format_money(paid)}</code>."
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"\U00002705 <b>{stylize_text('Loan Repaid')}</b>\n"
        f"{get_mention(borrower)} repaid <code>{format_money(paid_total)}</code>.",
        parse_mode=ParseMode.HTML,
    )
    track_mission(borrower["user_id"], "loan_action")


async def loan_status(update, context):
    user = ensure_user_exists(update.effective_user)
    owed = list(loans_collection.find(active_debt_filter(borrower_id=user["user_id"])))
    lent = list(loans_collection.find(active_debt_filter(lender_id=user["user_id"])))
    owe_total = sum(remaining(x) for x in owed)
    lent_total = sum(remaining(x) for x in lent)

    text = (
        f"\U0001F4CA <b>{stylize_text('Loan Status')}</b>\n\n"
        f"\U0001F4C9 <b>You owe:</b> <code>{format_money(owe_total)}</code>\n"
        f"\U0001F4C8 <b>People owe you:</b> <code>{format_money(lent_total)}</code>\n\n"
    )
    if owed:
        text += f"<b>{stylize_text('Payable loans')}:</b>\n"
        for loan in owed[:10]:
            lender = users_collection.find_one({"user_id": loan["lender_id"]}) or {"user_id": loan["lender_id"], "name": loan.get("lender_name", "User")}
            text += f"• {get_mention(lender)} — <code>{format_money(remaining(loan))}</code> left | Due: <b>{due_label(loan)}</b>\n"
        if len(owed) > 10:
            text += f"• +<code>{len(owed) - 10}</code> more smaller loans.\n"
        text += "\n<code>/loan pay 500</code> pays oldest loan first.\n<code>/loan pay 500 @user</code> pays that lender.\n"
    else:
        text += "<i>No active debt. Clean wallet.</i>\n"
    if lent:
        text += f"\n<b>{stylize_text('Your lending')}:</b>\n"
        for loan in lent[:10]:
            borrower = users_collection.find_one({"user_id": loan["borrower_id"]}) or {"user_id": loan["borrower_id"], "name": loan.get("borrower_name", "User")}
            collect_hint = f" — <code>/loan collect {borrower['user_id']}</code>" if is_overdue(loan) else ""
            text += f"• {get_mention(borrower)} owes <code>{format_money(remaining(loan))}</code> | Due: <b>{due_label(loan)}</b>{collect_hint}\n"
        if len(lent) > 10:
            text += f"• +<code>{len(lent) - 10}</code> more lending records.\n"
    pending_count = loans_collection.count_documents({"status": "pending", "$or": [{"borrower_id": user["user_id"]}, {"lender_id": user["user_id"]}]})
    if pending_count:
        text += f"\n\U0001F4E8 Pending requests: <code>{pending_count}</code> — <code>/loan requests</code>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def loan_requests(update, context):
    user = ensure_user_exists(update.effective_user)
    rows = list(loans_collection.find({
        "status": "pending",
        "$or": [{"borrower_id": user["user_id"]}, {"lender_id": user["user_id"]}],
    }).sort("created_at", -1).limit(10))
    if not rows:
        return await update.message.reply_text("\U00002705 No pending loan requests.", parse_mode=ParseMode.HTML)
    text = f"\U0001F4E8 <b>{stylize_text('Pending Loan Requests')}</b>\n\n"
    for loan in rows:
        if loan["borrower_id"] == user["user_id"]:
            other = users_collection.find_one({"user_id": loan["lender_id"]}) or {"user_id": loan["lender_id"], "name": loan.get("lender_name", "User")}
            text += f"• Asked {get_mention(other)} for <code>{format_money(loan['amount'])}</code>\n"
        else:
            other = users_collection.find_one({"user_id": loan["borrower_id"]}) or {"user_id": loan["borrower_id"], "name": loan.get("borrower_name", "User")}
            text += f"• {get_mention(other)} asks you for <code>{format_money(loan['amount'])}</code>\n"
    text += "\n<i>Use the Accept/Deny button on the original request message.</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def collect_loan(update, context, args):
    lender = ensure_user_exists(update.effective_user)
    _, target_arg = split_amount_target(args)
    if not target_arg and args:
        target_arg = args[0]
    if not target_arg:
        return await update.message.reply_text("\U000026A0\ufe0f Usage: <code>/loan collect @user</code>", parse_mode=ParseMode.HTML)

    borrower, error = await resolve_target(update, context, specific_arg=target_arg)
    if not borrower:
        return await update.message.reply_text(error or "\U000026A0\ufe0f Tag borrower.", parse_mode=ParseMode.HTML)

    loans = list(loans_collection.find(active_debt_filter(borrower["user_id"], lender["user_id"])).sort("created_at", 1))
    overdue = [loan for loan in loans if is_overdue(loan)]
    if not overdue:
        return await update.message.reply_text("\U000023F3 No overdue loan found for this user.", parse_mode=ParseMode.HTML)

    cooldown_left = collection_cooldown_left(overdue)
    if cooldown_left:
        return await update.message.reply_text(
            f"\U000023F3 <b>{stylize_text('Vasuli Cooldown')}</b>\n"
            f"You already tried collection from {get_mention(borrower)}.\n"
            f"Try again after <code>{short_duration(cooldown_left)}</code>.",
            parse_mode=ParseMode.HTML,
        )

    penalties = sum(apply_overdue_penalty(loan) for loan in overdue)
    overdue = list(loans_collection.find({
        "_id": {"$in": [loan["_id"] for loan in overdue]},
        "status": "active",
    }).sort("created_at", 1))

    total_due = sum(remaining(loan) for loan in overdue)
    borrower_doc = users_collection.find_one({"user_id": borrower["user_id"]}) or borrower
    wallet = int(borrower_doc.get("balance", 0))
    if wallet <= 0:
        loans_collection.update_many(
            {"_id": {"$in": [loan["_id"] for loan in overdue]}},
            {"$inc": {"default_marks": 1}, "$set": {"last_collect_attempt": datetime.utcnow()}},
        )
        return await update.message.reply_text(
            f"\U0001F4C9 <b>{stylize_text('Vasuli Failed')}</b>\n"
            f"{get_mention(borrower)} has no coins right now. Default mark added.",
            parse_mode=ParseMode.HTML,
        )

    collect_cap = max(LOAN_MIN_COLLECTION, wallet // 2)
    collect_amount = min(total_due, wallet, collect_cap)
    charged = adjust_user_balance(
        borrower["user_id"],
        -collect_amount,
        "loan_forced_collect",
        f"Overdue loan vasuli by {lender.get('name', 'lender')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=lender["user_id"],
        source="/loan collect",
        require_gte=collect_amount,
        meta={"total_due": total_due, "penalties": penalties},
    )
    if not charged:
        return await update.message.reply_text("\U0001F4C9 Borrower balance changed. Try again.", parse_mode=ParseMode.HTML)

    left = collect_amount
    now = datetime.utcnow()
    for loan in overdue:
        if left <= 0:
            break
        pay_now = min(left, remaining(loan))
        left -= pay_now
        new_paid = int(loan.get("paid", 0)) + pay_now
        update_doc = {"$inc": {"paid": pay_now, "collect_count": 1}, "$set": {"last_collect_attempt": now}}
        if new_paid >= int(loan.get("amount", 0)):
            update_doc["$set"].update({"status": "paid", "paid_at": now})
        loans_collection.update_one({"_id": loan["_id"], "status": "active"}, update_doc)

    adjust_user_balance(
        lender["user_id"],
        collect_amount,
        "loan_vasuli",
        f"Collected overdue loan from {borrower.get('name', 'user')}",
        chat_id=update.effective_chat.id if update.effective_chat else None,
        target_user_id=borrower["user_id"],
        source="/loan collect",
        meta={"total_due": total_due, "penalties": penalties},
    )
    try:
        await context.bot.send_message(
            chat_id=borrower["user_id"],
            text=(
                f"\U000026A0\ufe0f <b>{stylize_text('Overdue Loan Collection')}</b>\n"
                f"{get_mention(lender)} collected <code>{format_money(collect_amount)}</code> from your overdue loan."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    penalty_line = f"\n\U0001F4C8 Penalty added: <code>{format_money(penalties)}</code>" if penalties else ""
    remaining_due = max(0, total_due - collect_amount)
    remaining_line = f"\n\U0001F4CC Remaining due: <code>{format_money(remaining_due)}</code>" if remaining_due else "\n\U00002705 Loan cleared."
    await update.message.reply_text(
        f"\U0001F4AA <b>{stylize_text('Loan Vasuli Complete')}</b>\n"
        f"{get_mention(lender)} collected <code>{format_money(collect_amount)}</code> from {get_mention(borrower)}.{penalty_line}{remaining_line}",
        parse_mode=ParseMode.HTML,
    )


async def loan_top(update, context):
    pipeline = [
        {"$match": {"status": "active"}},
        {"$project": {"borrower_id": 1, "borrower_name": 1, "remaining": {"$subtract": ["$amount", "$paid"]}}},
        {"$match": {"remaining": {"$gt": 0}}},
        {"$group": {"_id": "$borrower_id", "name": {"$first": "$borrower_name"}, "debt": {"$sum": "$remaining"}}},
        {"$sort": {"debt": -1}},
        {"$limit": 10},
    ]
    rows = list(loans_collection.aggregate(pipeline))
    if not rows:
        return await update.message.reply_text("\U00002705 No active loans yet.", parse_mode=ParseMode.HTML)

    text = f"\U0001F3E6 <b>{stylize_text('Top Loan Debt')}</b>\n\n"
    for index, row in enumerate(rows, 1):
        user_doc = users_collection.find_one({"user_id": row["_id"]}) or {"user_id": row["_id"], "name": row.get("name", "User")}
        text += f"<code>{index}.</code> {get_mention(user_doc)} - <b>{format_money(row.get('debt', 0))}</b>\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def loan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not context.args:
        return await loan_status(update, context)

    action = context.args[0].lower()
    if action in ("help", "h"):
        return await update.message.reply_text(loan_help_text(), parse_mode=ParseMode.HTML)
    if action in ("status", "me"):
        return await loan_status(update, context)
    if action in ("requests", "pending"):
        return await loan_requests(update, context)
    if action in ("top", "leaderboard", "leaders"):
        return await loan_top(update, context)
    if action in ("collect", "vasuli", "recover"):
        return await collect_loan(update, context, context.args[1:])
    if action in ("give", "lend"):
        return await give_loan(update, context, context.args[1:])
    if action in ("pay", "repay", "return"):
        return await repay_loan(update, context, context.args[1:])
    if action in ("ask", "request", "borrow"):
        return await ask_loan(update, context, context.args[1:])
    return await ask_loan(update, context, context.args)


async def loan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, request_id = query.data.split("|", 1)
    loan = loans_collection.find_one({"request_id": request_id, "status": "pending"})
    if not loan:
        return await query.answer("Loan request expired.", show_alert=True)
    if query.from_user.id != loan["lender_id"]:
        return await query.answer("Only lender can answer this.", show_alert=True)

    if action == "loan_deny":
        loans_collection.update_one({"_id": loan["_id"]}, {"$set": {"status": "denied", "denied_at": datetime.utcnow()}})
        await query.message.edit_text("\U0000274C <b>Loan request denied.</b>", parse_mode=ParseMode.HTML)
        return await query.answer("Denied.")

    lender = users_collection.find_one({"user_id": loan["lender_id"]}) or {}
    if lender.get("balance", 0) < loan["amount"]:
        return await query.answer("Not enough coins to accept.", show_alert=True)
    if active_exposure_total(borrower_id=loan["borrower_id"]) + int(loan["amount"]) > MAX_ACTIVE_LOAN_EXPOSURE:
        return await query.answer("Borrower debt limit reached.", show_alert=True)
    if active_exposure_total(lender_id=loan["lender_id"]) + int(loan["amount"]) > MAX_ACTIVE_LOAN_EXPOSURE:
        return await query.answer("Lender exposure limit reached.", show_alert=True)

    charged = adjust_user_balance(
        loan["lender_id"],
        -loan["amount"],
        "loan_lend",
        f"Approved loan for {loan.get('borrower_name', 'user')}",
        chat_id=query.message.chat_id if query.message else None,
        target_user_id=loan["borrower_id"],
        source="loan_accept",
        require_gte=loan["amount"],
        meta={"request_id": loan["request_id"], "amount": loan["amount"]},
    )
    if not charged:
        return await query.answer("Not enough coins to accept.", show_alert=True)

    activated = loans_collection.update_one(
        {"_id": loan["_id"], "status": "pending"},
        {"$set": {"status": "active", "accepted_at": datetime.utcnow(), "due_at": loan_due_at()}},
    )
    if activated.modified_count == 0:
        adjust_user_balance(
            loan["lender_id"],
            loan["amount"],
            "loan_refund",
            f"Refunded pending loan for {loan.get('borrower_name', 'user')}",
            chat_id=query.message.chat_id if query.message else None,
            target_user_id=loan["borrower_id"],
            source="loan_accept",
            meta={"request_id": loan["request_id"], "amount": loan["amount"]},
        )
        return await query.answer("Loan request already handled.", show_alert=True)

    credited = adjust_user_balance(
        loan["borrower_id"],
        loan["amount"],
        "loan_receive",
        f"Received approved loan from {loan.get('lender_name', 'user')}",
        chat_id=query.message.chat_id if query.message else None,
        target_user_id=loan["lender_id"],
        source="loan_accept",
        meta={"request_id": loan["request_id"], "amount": loan["amount"]},
    )
    if not credited:
        loans_collection.update_one(
            {"_id": loan["_id"], "status": "active"},
            {
                "$set": {
                    "status": "failed",
                    "failed_at": datetime.utcnow(),
                    "failure_reason": "borrower_credit_failed",
                }
            },
        )
        adjust_user_balance(
            loan["lender_id"],
            loan["amount"],
            "loan_refund",
            f"Refunded failed loan for {loan.get('borrower_name', 'user')}",
            chat_id=query.message.chat_id if query.message else None,
            target_user_id=loan["borrower_id"],
            source="loan_accept",
            meta={"request_id": loan["request_id"], "amount": loan["amount"], "delivery_failed": True},
        )
        await query.message.edit_text(
            "\U0000274C <b>Loan delivery failed.</b>\nThe lender's coins were refunded. Please create a new request.",
            parse_mode=ParseMode.HTML,
        )
        return await query.answer("Loan failed; coins refunded.", show_alert=True)

    borrower = users_collection.find_one({"user_id": loan["borrower_id"]}) or {"user_id": loan["borrower_id"], "name": loan["borrower_name"]}
    await query.message.edit_text(
        f"\U00002705 <b>{stylize_text('Loan Approved')}</b>\n"
        f"{get_mention(borrower)} received <code>{format_money(loan['amount'])}</code>.",
        parse_mode=ParseMode.HTML,
    )
    return await query.answer("Loan sent.")
