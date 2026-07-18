import os
import sqlite3
import logging
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "tolumoney.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,        -- 'income' or 'expense'
            amount REAL NOT NULL,
            category TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def add_transaction(user_id: int, tx_type: str, amount: float, category: str, note: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (user_id, type, amount, category, note, created_at) VALUES (?,?,?,?,?,?)",
        (user_id, tx_type, amount, category, note, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_balance(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT type, SUM(amount) FROM transactions WHERE user_id=? GROUP BY type",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    income = 0.0
    expense = 0.0
    for tx_type, total in rows:
        if tx_type == "income":
            income = total
        elif tx_type == "expense":
            expense = total
    return income, expense, income - expense


def get_history(user_id: int, limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT type, amount, category, note, created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["/income", "/expense"], ["/balance", "/history"]],
    resize_keyboard=True,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to ToluMoneyBot 💰\n\n"
        "Commands:\n"
        "/income <amount> <category> - log income\n"
        "/expense <amount> <category> - log expense\n"
        "/balance - see your current balance\n"
        "/history - see your last 10 transactions\n",
        reply_markup=MAIN_KEYBOARD,
    )


async def income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_transaction(update, context, "income")


async def expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _log_transaction(update, context, "expense")


async def _log_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, tx_type: str):
    args = context.args
    if not args or len(args) < 1:
        await update.message.reply_text(f"Usage: /{tx_type} <amount> <category (optional)>")
        return

    try:
        amount = float(args[0])
    except ValueError:
        await update.message.reply_text("Amount must be a number. Example: /income 5000 salary")
        return

    category = " ".join(args[1:]) if len(args) > 1 else "uncategorized"
    user_id = update.effective_user.id

    add_transaction(user_id, tx_type, amount, category)
    await update.message.reply_text(f"✅ Logged {tx_type}: {amount} ({category})")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    income_total, expense_total, net = get_balance(user_id)
    await update.message.reply_text(
        f"📊 Balance summary\n\n"
        f"Total income: {income_total:.2f}\n"
        f"Total expense: {expense_total:.2f}\n"
        f"Net balance: {net:.2f}"
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = get_history(user_id)
    if not rows:
        await update.message.reply_text("No transactions yet.")
        return

    lines = ["🧾 Last transactions:\n"]
    for tx_type, amount, category, note, created_at in rows:
        sign = "+" if tx_type == "income" else "-"
        date_str = created_at.split("T")[0]
        lines.append(f"{date_str} | {sign}{amount:.2f} | {category}")

    await update.message.reply_text("\n".join(lines))


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that. Try /start for the menu.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("income", income))
    app.add_handler(CommandHandler("expense", expense))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
