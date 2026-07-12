# ============================================================
#  SIFRA7 OTP BOT — FULL VERSION v2
# ============================================================

import asyncio
import logging
import re
import sqlite3
import os
import requests
from datetime import datetime, timedelta

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ============================================================
#  CONFIG
# ============================================================

BOT_TOKEN        = "8733720348:AAEKrQLveSyGBtAZz17WebNRFEz2XDQ8Udc"
ADMIN_ID         = 6572004742
ADMIN_ID2        = 5931349587
ADMIN_IDS        = (ADMIN_ID, ADMIN_ID2)
GROUP_CHAT_ID    = -1003318768422
GROUP_LINK       = "https://t.me/+NhG-CwXI-q0wN2Rk"
SUPPORT_LINK     = "https://t.me/Sifra7"
BOT_USERNAME     = "Sifra7_bot"
REQUIRED_CHANNEL = "@sifra7s"
REQUIRED_GROUP   = "@sifra7ss"
CHANNEL_LINK     = "https://t.me/sifra7s"
MUST_JOIN_LINK   = "https://t.me/sifra7ss"

MIN_WITHDRAWAL   = 0.50
NUMBER_EXPIRY    = 3600
POLL_INTERVAL    = 10
NUMBERS_PER_USER = 3   # 3 numbers assigned at once

# ── API Sources ───────────────────────────────────────────────
APIS_A = [
    # Add your MO API token when ready
    {"url": "http://137.74.1.203/crapi/reseller/mdr.php", "token": ""},
]
APIS_B = [
    {"url": "https://mbcs-ms.com/crapi/mbc/viewstats", "token": "fzLDmdiz7w2WJUMJWFGMyE6Ks35sG0b2etKq4CdQHqs"},
]

# ============================================================
#  LOGGING
# ============================================================

class ColorLog(logging.Formatter):
    G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; M = "\033[35m"; RESET = "\033[0m"
    FORMATS = {
        logging.DEBUG:    G + "%(asctime)s [DEBUG] %(message)s" + RESET,
        logging.INFO:     G + "%(asctime)s [INFO]  %(message)s" + RESET,
        logging.WARNING:  Y + "%(asctime)s [WARN]  %(message)s" + RESET,
        logging.ERROR:    R + "%(asctime)s [ERROR] %(message)s" + RESET,
        logging.CRITICAL: M + "%(asctime)s [CRIT]  %(message)s" + RESET,
    }
    def format(self, record):
        return logging.Formatter(self.FORMATS.get(record.levelno), datefmt="%Y-%m-%d %H:%M:%S").format(record)

handler = logging.StreamHandler()
handler.setFormatter(ColorLog())
logging.basicConfig(handlers=[handler], level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
#  DATABASE
# ============================================================

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sifra7.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id          INTEGER PRIMARY KEY,
        username         TEXT,
        full_name        TEXT,
        is_banned        INTEGER DEFAULT 0,
        balance          REAL    DEFAULT 0.0,
        total_earned     REAL    DEFAULT 0.0,
        total_withdrawn  REAL    DEFAULT 0.0,
        wallet_address   TEXT    DEFAULT NULL,
        bank_name        TEXT    DEFAULT NULL,
        account_number   TEXT    DEFAULT NULL,
        withdraw_method  TEXT    DEFAULT NULL,
        referral_code    TEXT    UNIQUE,
        referred_by      INTEGER DEFAULT NULL,
        referral_paid    INTEGER DEFAULT 0,
        joined_at        TEXT    DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS numbers (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        number      TEXT UNIQUE NOT NULL,
        country     TEXT NOT NULL,
        service     TEXT NOT NULL,
        status      TEXT DEFAULT 'available',
        assigned_to INTEGER DEFAULT NULL,
        assigned_at TEXT DEFAULT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS otps (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        number      TEXT,
        country     TEXT,
        service     TEXT,
        otp_code    TEXT,
        raw_sms     TEXT,
        user_id     INTEGER,
        received_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER,
        amount       REAL,
        method       TEXT,
        wallet       TEXT,
        bank_name    TEXT,
        account_number TEXT,
        status       TEXT DEFAULT 'pending',
        requested_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit(); conn.close()

# ── Settings ──────────────────────────────────────────────────
def get_setting(key, default=None):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = c.fetchone(); conn.close()
    return r["value"] if r else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, str(value)))
    conn.commit(); conn.close()

def get_otp_reward():
    v = get_setting("otp_reward"); return float(v) if v else 0.00005

def get_referral_bonus():
    v = get_setting("referral_bonus"); return float(v) if v else 0.01

# ── User helpers ──────────────────────────────────────────────
import random, string

def gen_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def get_or_create_user(user_id, username, full_name, referred_by=None):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    u = c.fetchone()
    if not u:
        code = gen_referral_code()
        # make sure code is unique
        while True:
            c.execute("SELECT 1 FROM users WHERE referral_code=?", (code,))
            if not c.fetchone(): break
            code = gen_referral_code()
        c.execute(
            "INSERT INTO users (user_id, username, full_name, referral_code, referred_by) VALUES (?,?,?,?,?)",
            (user_id, username, full_name, code, referred_by)
        )
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        u = c.fetchone()
    conn.close()
    return dict(u)

def get_user_full(user_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None

def get_all_users():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM users"); rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]

def get_user_balance(user_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    r = c.fetchone(); conn.close()
    return r["balance"] if r else 0.0

def add_balance(user_id, amount):
    conn = get_conn()
    conn.execute("UPDATE users SET balance=balance+?, total_earned=total_earned+? WHERE user_id=?",
                 (amount, amount, user_id))
    conn.commit(); conn.close()

def deduct_balance(user_id, amount):
    conn = get_conn()
    conn.execute("UPDATE users SET balance=balance-?, total_withdrawn=total_withdrawn+? WHERE user_id=?",
                 (amount, amount, user_id))
    conn.commit(); conn.close()

def ban_user(user_id):
    conn = get_conn()
    conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,)); conn.commit(); conn.close()

def unban_user(user_id):
    conn = get_conn()
    conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,)); conn.commit(); conn.close()

def get_user_by_referral_code(code):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE referral_code=?", (code,))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None

def mark_referral_paid(user_id):
    conn = get_conn()
    conn.execute("UPDATE users SET referral_paid=1 WHERE user_id=?", (user_id,)); conn.commit(); conn.close()

def get_referral_count(user_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM users WHERE referred_by=?", (user_id,))
    r = c.fetchone(); conn.close()
    return r["cnt"] if r else 0

# ── Withdrawal helpers ────────────────────────────────────────
def save_withdrawal(user_id, amount, method, wallet=None, bank_name=None, account_number=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO withdrawals (user_id, amount, method, wallet, bank_name, account_number) VALUES (?,?,?,?,?,?)",
        (user_id, amount, method, wallet, bank_name, account_number)
    )
    conn.commit(); conn.close()

def get_pending_withdrawals():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM withdrawals WHERE status='pending' ORDER BY requested_at DESC")
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]

def get_pending_amount_for_user(user_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT SUM(amount) as total FROM withdrawals WHERE user_id=? AND status='pending'", (user_id,))
    r = c.fetchone(); conn.close()
    return r["total"] or 0.0

def approve_withdrawal(wid):
    conn = get_conn()
    conn.execute("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,)); conn.commit(); conn.close()

def reject_withdrawal(wid):
    conn = get_conn()
    conn.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,)); conn.commit(); conn.close()

# ── Number helpers ────────────────────────────────────────────
user_seen_numbers = {}

def add_number(number, country, service):
    conn = get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO numbers (number, country, service) VALUES (?,?,?)",
                     (number, country, service))
        conn.commit(); return True
    except Exception: return False
    finally: conn.close()

def get_countries_with_count():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT country, COUNT(*) as cnt FROM numbers WHERE status='available' GROUP BY country ORDER BY country")
    rows = c.fetchall(); conn.close()
    return [(r["country"], r["cnt"]) for r in rows]

def get_services_by_country(country):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT DISTINCT service FROM numbers WHERE status='available' AND country=?", (country,))
    rows = c.fetchall(); conn.close()
    return [r["service"] for r in rows]

def assign_numbers(user_id, country, service, count=3):
    """Assign up to `count` numbers to user. Returns list of numbers."""
    import random as _random
    conn = get_conn(); c = conn.cursor()
    # Release previously assigned numbers for this user
    conn.execute(
        "UPDATE numbers SET status='available', assigned_to=NULL, assigned_at=NULL WHERE assigned_to=? AND status='assigned'",
        (user_id,)
    )
    conn.commit()
    seen = user_seen_numbers.get(user_id, set())
    c.execute("SELECT id, number FROM numbers WHERE status='available' AND country=? AND service=?", (country, service))
    all_rows = c.fetchall()
    unseen = [r for r in all_rows if r["number"] not in seen]
    if not unseen:
        user_seen_numbers[user_id] = set()
        unseen = all_rows
    if not unseen:
        conn.close(); return []
    chosen = _random.sample(unseen, min(count, len(unseen)))
    assigned = []
    for row in chosen:
        conn.execute(
            "UPDATE numbers SET status='assigned', assigned_to=?, assigned_at=datetime('now') WHERE id=?",
            (user_id, row["id"])
        )
        if user_id not in user_seen_numbers:
            user_seen_numbers[user_id] = set()
        user_seen_numbers[user_id].add(row["number"])
        assigned.append(row["number"])
    conn.commit(); conn.close()
    return assigned

def get_assigned_numbers(user_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM numbers WHERE assigned_to=? AND status='assigned'", (user_id,))
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]

def get_number_by_value(number):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM numbers WHERE number=?", (number,))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None

def mark_number_used(number):
    conn = get_conn()
    conn.execute("UPDATE numbers SET status='used', assigned_to=NULL WHERE number=?", (number,))
    conn.commit(); conn.close()

def release_expired_numbers():
    conn = get_conn()
    conn.execute(
        """UPDATE numbers SET status='available', assigned_to=NULL, assigned_at=NULL
           WHERE status='assigned' AND assigned_at IS NOT NULL
           AND (strftime('%s','now') - strftime('%s', assigned_at)) > ?""",
        (NUMBER_EXPIRY,)
    )
    conn.commit(); conn.close()

def get_stock_count():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM numbers WHERE status='available'")
    r = c.fetchone(); conn.close()
    return r["cnt"]

def delete_numbers_by_country(country):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM numbers WHERE country=?", (country,))
    count = c.fetchone()["cnt"]
    conn.execute("DELETE FROM numbers WHERE country=?", (country,)); conn.commit(); conn.close()
    return count

def save_otp(number, country, service, otp_code, user_id, raw_sms):
    conn = get_conn()
    conn.execute("INSERT INTO otps (number, country, service, otp_code, user_id, raw_sms) VALUES (?,?,?,?,?,?)",
                 (number, country, service, otp_code, user_id, raw_sms))
    conn.commit(); conn.close()

def get_otp_stats():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM otps")
    total = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM otps WHERE date(received_at)=date('now')")
    today = c.fetchone()["cnt"]
    conn.close()
    return total, today

# ============================================================
#  HELPERS
# ============================================================

def is_admin(user_id): return user_id in ADMIN_IDS

COUNTRY_CODES_BY_PREFIX = {
    "1": ("USA", "🇺🇸"), "52": ("Mexico", "🇲🇽"), "55": ("Brazil", "🇧🇷"),
    "57": ("Colombia", "🇨🇴"), "58": ("Venezuela", "🇻🇪"),
    "7": ("Russia", "🇷🇺"), "33": ("France", "🇫🇷"), "34": ("Spain", "🇪🇸"),
    "39": ("Italy", "🇮🇹"), "44": ("UK", "🇬🇧"), "49": ("Germany", "🇩🇪"),
    "91": ("India", "🇮🇳"), "92": ("Pakistan", "🇵🇰"), "880": ("Bangladesh", "🇧🇩"),
    "86": ("China", "🇨🇳"), "81": ("Japan", "🇯🇵"), "82": ("South Korea", "🇰🇷"),
    "84": ("Vietnam", "🇻🇳"), "66": ("Thailand", "🇹🇭"), "62": ("Indonesia", "🇮🇩"),
    "63": ("Philippines", "🇵🇭"), "95": ("Myanmar", "🇲🇲"),
    "20": ("Egypt", "🇪🇬"), "27": ("South Africa", "🇿🇦"),
    "233": ("Ghana", "🇬🇭"), "234": ("Nigeria", "🇳🇬"), "254": ("Kenya", "🇰🇪"),
    "255": ("Tanzania", "🇹🇿"), "251": ("Ethiopia", "🇪🇹"), "256": ("Uganda", "🇺🇬"),
    "221": ("Senegal", "🇸🇳"), "237": ("Cameroon", "🇨🇲"), "225": ("Ivory Coast", "🇨🇮"),
    "228": ("Togo", "🇹🇬"), "229": ("Benin", "🇧🇯"), "223": ("Mali", "🇲🇱"),
    "224": ("Guinea", "🇬🇳"), "966": ("Saudi Arabia", "🇸🇦"), "971": ("UAE", "🇦🇪"),
    "98": ("Iran", "🇮🇷"), "90": ("Turkey", "🇹🇷"), "380": ("Ukraine", "🇺🇦"),
    "61": ("Australia", "🇦🇺"), "64": ("New Zealand", "🇳🇿"),
}

COUNTRY_INFO = {
    "nigeria": ("🇳🇬", "234"), "ghana": ("🇬🇭", "233"), "kenya": ("🇰🇪", "254"),
    "south africa": ("🇿🇦", "27"), "ethiopia": ("🇪🇹", "251"), "tanzania": ("🇹🇿", "255"),
    "uganda": ("🇺🇬", "256"), "senegal": ("🇸🇳", "221"), "cameroon": ("🇨🇲", "237"),
    "ivory coast": ("🇨🇮", "225"), "togo": ("🇹🇬", "228"), "benin": ("🇧🇯", "229"),
    "mali": ("🇲🇱", "223"), "guinea": ("🇬🇳", "224"),
    "egypt": ("🇪🇬", "20"), "usa": ("🇺🇸", "1"), "uk": ("🇬🇧", "44"),
    "germany": ("🇩🇪", "49"), "france": ("🇫🇷", "33"), "india": ("🇮🇳", "91"),
    "pakistan": ("🇵🇰", "92"), "bangladesh": ("🇧🇩", "880"), "china": ("🇨🇳", "86"),
    "vietnam": ("🇻🇳", "84"), "thailand": ("🇹🇭", "66"), "indonesia": ("🇮🇩", "62"),
    "philippines": ("🇵🇭", "63"), "myanmar": ("🇲🇲", "95"), "russia": ("🇷🇺", "7"),
    "turkey": ("🇹🇷", "90"), "ukraine": ("🇺🇦", "380"), "brazil": ("🇧🇷", "55"),
    "venezuela": ("🇻🇪", "58"), "mexico": ("🇲🇽", "52"), "australia": ("🇦🇺", "61"),
}

SERVICE_ICONS = {
    "WHATSAPP": "📱", "FACEBOOK": "📘", "INSTAGRAM": "📸", "TELEGRAM": "✈️",
    "GOOGLE": "🔍", "TWITTER": "🐦", "TIKTOK": "🎵", "SNAPCHAT": "👻",
    "AMAZON": "📦", "PAYPAL": "💳", "MICROSOFT": "🪟", "APPLE": "🍎",
    "NETFLIX": "🎬", "DISCORD": "🎮", "UBER": "🚗", "LINKEDIN": "💼",
}

def detect_service(cli, message):
    text = (cli + " " + message).lower()
    for svc, kws in {
        "WHATSAPP": ["whatsapp"], "FACEBOOK": ["facebook","fb"],
        "INSTAGRAM": ["instagram"], "TELEGRAM": ["telegram"],
        "GOOGLE": ["google"], "TWITTER": ["twitter","x.com"],
        "TIKTOK": ["tiktok"], "SNAPCHAT": ["snapchat"],
        "AMAZON": ["amazon"], "PAYPAL": ["paypal"],
        "MICROSOFT": ["microsoft"], "APPLE": ["apple"],
        "NETFLIX": ["netflix"], "DISCORD": ["discord"],
        "UBER": ["uber"], "LINKEDIN": ["linkedin"],
    }.items():
        for kw in kws:
            if kw in text: return svc
    return cli.upper() if cli else "SMS"

def get_country_from_number(num):
    clean = re.sub(r"\D", "", str(num))
    for length in (3, 2, 1):
        prefix = clean[:length]
        if prefix in COUNTRY_CODES_BY_PREFIX:
            name, flag = COUNTRY_CODES_BY_PREFIX[prefix]
            return name, flag
    return "Unknown", "🌍"

def get_country_info(country):
    return COUNTRY_INFO.get(country.strip().lower(), ("🌍", "??"))

def mask_number(number):
    """Mask middle digits: 2348012345678 → 234***45678"""
    digits = re.sub(r"\D", "", str(number))
    if len(digits) > 8:
        return digits[:3] + "***" + digits[-5:]
    return digits[:2] + "***" + digits[-3:]

def extract_otp(text):
    dashed = re.search(r'\b(\d{3,4})-(\d{3,4})\b', text)
    if dashed: return dashed.group(1) + "-" + dashed.group(2)
    for p in [r"code[:\s]+(\d{4,9})", r"OTP[:\s]+(\d{4,9})",
              r"is[:\s]+(\d{4,9})", r"\b(\d{4,9})\b"]:
        m = re.search(p, text, re.IGNORECASE)
        if m: return m.group(1)
    return None

# ============================================================
#  MENUS
# ============================================================

def main_menu(user_id):
    keyboard = [
        ["🏢 Numbers", "📊 Status"],
        ["📦 Stock",   "💰 Wallet"],
        ["👥 Referral"],
    ]
    if is_admin(user_id):
        keyboard.append(["⚙️ Admin Panel"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Numbers",    callback_data="adm_add"),
         InlineKeyboardButton("❌ Delete Numbers", callback_data="adm_del")],
        [InlineKeyboardButton("👥 All Users",      callback_data="adm_users"),
         InlineKeyboardButton("📊 Analytics",      callback_data="adm_stats")],
        [InlineKeyboardButton("🚫 Ban User",       callback_data="adm_ban"),
         InlineKeyboardButton("✅ Unban User",     callback_data="adm_unban")],
        [InlineKeyboardButton("📢 Broadcast",      callback_data="adm_broadcast")],
        [InlineKeyboardButton("💵 Set OTP Reward", callback_data="adm_set_reward")],
        [InlineKeyboardButton("🎁 Set Referral Bonus", callback_data="adm_set_ref_bonus")],
        [InlineKeyboardButton("💸 Withdrawals",    callback_data="adm_withdrawals")],
        [InlineKeyboardButton("💰 Add Bonus",      callback_data="adm_add_balance")],
    ])

def number_buttons(country, service):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 View OTP Group",  url=GROUP_LINK),
         InlineKeyboardButton("🔴 Change Numbers",  callback_data=f"change:{country}:{service}")],
        [InlineKeyboardButton("🔴 Change Country",  callback_data="countries")],
        [InlineKeyboardButton("🔙 Back to Menu",    callback_data="back_main")],
    ])

def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel",  url=CHANNEL_LINK)],
        [InlineKeyboardButton("👥 Join Group",    url=MUST_JOIN_LINK)],
        [InlineKeyboardButton("✅ I Have Joined", callback_data="check_join")],
    ])

def withdraw_method_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 TRX Wallet",    callback_data="withdraw_trx")],
        [InlineKeyboardButton("🏦 Naira (Bank)",  callback_data="withdraw_naira")],
        [InlineKeyboardButton("🔙 Back to Wallet", callback_data="back_wallet")],
    ])

# ============================================================
#  MEMBERSHIP CHECK
# ============================================================

async def check_membership(bot, user_id):
    try:
        ch = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if ch.status in ("left","kicked","banned"): return False
    except Exception: return False
    try:
        gr = await bot.get_chat_member(REQUIRED_GROUP, user_id)
        if gr.status in ("left","kicked","banned"): return False
    except Exception: return False
    return True

async def send_join_message(message):
    await message.reply_text(
        "⚠️ You must join our Channel and Group to use this bot.",
        reply_markup=join_keyboard()
    )

# ============================================================
#  API POLLING
# ============================================================

_processed   = {}
_error_count = 0

def fetch_sms_a(api):
    if not api.get("url") or not api.get("token"): return []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        params = {
            "token":    api["token"],
            "fromdate": f"{today} 00:00:00",
            "todate":   f"{today} 23:59:59",
            "records":  200
        }
        resp = requests.get(api["url"], params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if str(data.get("status","")).lower() == "success":
                return [{
                    "dt":      str(s.get("datetime") or ""),
                    "num":     str(s.get("number") or "").strip(),
                    "message": str(s.get("message") or "").strip(),
                    "cli":     str(s.get("cli") or "").strip(),
                    "payout":  "0",
                } for s in data.get("data", [])]
        return []
    except Exception as e:
        logger.error(f"[API-A] error: {e}"); return []

def fetch_sms_b(api):
    if not api.get("url") or not api.get("token"): return []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        params = {
            "token":   api["token"],
            "dt1":     f"{today} 00:00:00",
            "dt2":     f"{today} 23:59:59",
            "records": 200
        }
        resp = requests.get(api["url"], params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if str(data.get("status","")).lower() == "success":
                return [{
                    "dt":      str(s.get("dt") or ""),
                    "num":     str(s.get("num") or "").strip(),
                    "message": str(s.get("message") or "").strip(),
                    "cli":     str(s.get("cli") or "").strip(),
                    "payout":  str(s.get("payout") or "0"),
                } for s in data.get("data", [])]
        return []
    except Exception as e:
        logger.error(f"[API-B] error: {e}"); return []

def fetch_all_sms():
    all_sms = []
    for api in APIS_A: all_sms.extend(fetch_sms_a(api))
    for api in APIS_B: all_sms.extend(fetch_sms_b(api))
    return all_sms

async def process_and_forward(bot, sms):
    num = str(sms.get("num") or "").strip()
    msg = str(sms.get("message") or "").strip()
    cli = str(sms.get("cli") or "").strip()
    try: payout = float(sms.get("payout") or get_otp_reward())
    except Exception: payout = get_otp_reward()
    if payout == 0: payout = get_otp_reward()

    if not num or not msg: return

    otp          = extract_otp(msg)
    country_name, flag = get_country_from_number(num)
    service      = detect_service(cli, msg)
    svc_icon     = SERVICE_ICONS.get(service.upper(), "📨")
    masked       = mask_number(num)
    number_row   = get_number_by_value(num)
    assigned_uid = None
    country      = country_name
    svc          = service

    if number_row and number_row["status"] == "assigned":
        assigned_uid = number_row["assigned_to"]
        country      = number_row["country"] or country_name
        svc          = number_row["service"] or service
        save_otp(num, country, svc, otp, assigned_uid, msg)
        mark_number_used(num)
        user_seen_numbers.pop(assigned_uid, None)
        if otp:
            add_balance(assigned_uid, payout)
            # ── Referral bonus (first OTP only) ──
            db_user = get_user_full(assigned_uid)
            if db_user and db_user.get("referred_by") and not db_user.get("referral_paid"):
                ref_bonus = get_referral_bonus()
                add_balance(db_user["referred_by"], ref_bonus)
                mark_referral_paid(assigned_uid)
                try:
                    await bot.send_message(
                        db_user["referred_by"],
                        f"🎁 <b>Referral Bonus!</b>\n\n"
                        f"Your referral just received their first OTP!\n"
                        f"💰 Bonus: <b>+${ref_bonus:.5f}</b> added to your balance!",
                        parse_mode="HTML"
                    )
                except Exception: pass
    elif number_row:
        country = number_row["country"] or country_name
        svc     = number_row["service"] or service
        save_otp(num, country, svc, otp, None, msg)

    svc_label = f"{SERVICE_ICONS.get(svc.upper(), '📨')} {svc}"

    # ── Private message (full info) ──
    if assigned_uid and otp:
        new_balance = get_user_balance(assigned_uid)
        otp_text    = otp
        private_msg = (
            f"🌍 Country: {country} {flag}\n"
            f"📡 Service: {svc_label}\n"
            f"📞 Number: <code>+{num}</code>\n\n"
            f"🔑 Code: <code>{otp_text}</code>\n\n"
            f"💰 Payout: <b>+${payout:.5f}</b>\n"
            f"💼 Balance: <b>${new_balance:.5f}</b>"
        )
        try:
            from telegram import CopyTextButton as CTB
            private_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(text=otp_text, copy_text=CTB(text=otp_text))],
            ])
        except Exception:
            private_kb = None

        try:
            await bot.send_message(assigned_uid, private_msg, parse_mode="HTML", reply_markup=private_kb)
            logger.info(f"✅ Private → {assigned_uid} | {otp_text} | +${payout:.5f}")
        except Exception as e:
            logger.error(f"Private send failed: {e}")

    # ── Group message (masked number, no reward/balance) ──
    if otp:
        otp_text  = otp
        group_msg = (
            f"🌍 Country: {country} {flag}\n"
            f"📡 Service: {svc_label}\n"
            f"📞 Number: <code>{masked}</code>"
        )
        try:
            from telegram import CopyTextButton as CTB
            group_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(text=otp_text, copy_text=CTB(text=otp_text))],
                [InlineKeyboardButton("‼️ Bot Pnl",     url=f"https://t.me/{BOT_USERNAME}"),
                 InlineKeyboardButton("♻️ All Support", url=SUPPORT_LINK)],
                [InlineKeyboardButton("📣 Channel",      url=CHANNEL_LINK)],
            ])
        except Exception:
            group_msg += f"\n\n<code>{otp_text}</code>"
            group_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("‼️ Bot Pnl",     url=f"https://t.me/{BOT_USERNAME}"),
                 InlineKeyboardButton("♻️ All Support", url=SUPPORT_LINK)],
                [InlineKeyboardButton("📣 Channel",      url=CHANNEL_LINK)],
            ])
        try:
            await bot.send_message(GROUP_CHAT_ID, group_msg, parse_mode="HTML", reply_markup=group_kb)
            logger.info(f"✅ Group | {masked} → {otp_text}")
        except Exception as e:
            logger.error(f"Group send failed: {e}")

async def start_polling(bot):
    global _processed, _error_count
    logger.info("🚀 Polling started — today's OTPs only")
    startup_time = datetime.now()

    existing = fetch_all_sms()
    for sms in existing:
        num = str(sms.get("num") or "").strip()
        msg = str(sms.get("message") or "")
        dt  = str(sms.get("dt") or "")
        try:
            sms_time = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            if sms_time < startup_time:
                _processed[f"{dt}_{num}_{hash(msg)}"] = datetime.now()
        except Exception:
            _processed[f"{dt}_{num}_{hash(msg)}"] = datetime.now()
    logger.info(f"Preloaded {len(existing)} existing SMS — forwarding only NEW ones from now")

    while True:
        try:
            if _error_count > 10:
                logger.warning("Too many errors — pausing 60s")
                await asyncio.sleep(60); _error_count = 0; continue

            messages = fetch_all_sms(); new_count = 0
            for sms in messages:
                if not isinstance(sms, dict): continue
                num = str(sms.get("num") or "").strip()
                msg = str(sms.get("message") or "").strip()
                dt  = str(sms.get("dt") or "")
                if not num or not msg: continue
                key = f"{dt}_{num}_{hash(msg)}"
                if key in _processed: continue
                _processed[key] = datetime.now()
                await process_and_forward(bot, sms)
                new_count += 1

            cutoff = datetime.now() - timedelta(hours=4)
            _processed = {k: v for k, v in _processed.items() if v > cutoff}

            if new_count: logger.info(f"✅ Forwarded {new_count} new SMS")
            else: logger.info("⏭ No new SMS")

            release_expired_numbers(); _error_count = 0
        except Exception as e:
            _error_count += 1; logger.error(f"Polling error ({_error_count}): {e}")
        await asyncio.sleep(POLL_INTERVAL)

# ============================================================
#  COMMAND HANDLERS
# ============================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args
    referred_by = None
    if args:
        ref_user = get_user_by_referral_code(args[0])
        if ref_user and ref_user["user_id"] != user.id:
            referred_by = ref_user["user_id"]

    db_user = get_or_create_user(user.id, user.username or "", user.full_name or "", referred_by)
    if db_user["is_banned"]:
        await update.message.reply_text("🚫 You are banned from this bot."); return
    if not is_admin(user.id):
        joined = await check_membership(ctx.bot, user.id)
        if not joined:
            await send_join_message(update.message); return
    await update.message.reply_text(
        f"⚡ <b>Welcome, {user.first_name}!</b>\n\nChoose an option from the menu below.",
        parse_mode="HTML", reply_markup=main_menu(user.id)
    )

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await show_admin_panel(update.message, ctx)

async def show_admin_panel(message, ctx):
    total, today = get_otp_stats(); stock = get_stock_count()
    reward = get_otp_reward(); ref_bonus = get_referral_bonus()
    await message.reply_text(
        f"⚙️ <b>Admin Panel</b>\n\n"
        f"📦 Stock: <b>{stock}</b>\n"
        f"💵 OTP Reward: <b>${reward:.5f}</b>\n"
        f"🎁 Referral Bonus: <b>${ref_bonus:.5f}</b>\n"
        f"📩 Total OTPs: <b>{total}</b> | Today: <b>{today}</b>",
        parse_mode="HTML", reply_markup=admin_keyboard()
    )

async def cmd_numbers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    countries = get_countries_with_count()
    if not countries:
        await update.message.reply_text("😔 No numbers available right now."); return
    buttons = [
        [InlineKeyboardButton(f"{get_country_info(c)[0]} {c} ({n})", callback_data=f"country:{c}")]
        for c, n in countries
    ]
    await update.message.reply_text("🌍 <b>Select a Country:</b>", parse_mode="HTML",
                                    reply_markup=InlineKeyboardMarkup(buttons))

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    records = get_assigned_numbers(user.id)
    if not records:
        await update.message.reply_text(
            "ℹ️ <b>Status</b>\n\nYou have no numbers assigned.\nGo to 🏢 Numbers to get some.",
            parse_mode="HTML"); return
    text = "📊 <b>Your Assigned Numbers</b>\n\n"
    for r in records:
        flag, _ = get_country_info(r["country"])
        svc_icon = SERVICE_ICONS.get(r["service"].upper(), "📨")
        text += (f"📱 {svc_icon} {r['service']} | {flag} {r['country']}\n"
                 f"📞 <code>+{r['number']}</code> — ✅ Active\n\n")
    await update.message.reply_text(text, parse_mode="HTML",
                                    reply_markup=number_buttons(records[0]["country"], records[0]["service"]))

async def cmd_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    countries = get_countries_with_count(); stock = get_stock_count()
    lines = "\n".join([f"{get_country_info(c)[0]} {c}: <b>{n}</b>" for c, n in countries]) or "None"
    await update.message.reply_text(
        f"📦 <b>Stock Overview</b>\n\n✅ Total available: <b>{stock}</b>\n\n{lines}",
        parse_mode="HTML"
    )

async def cmd_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    db_user = get_user_full(user.id)
    if not db_user:
        await update.message.reply_text("Please /start first."); return
    balance         = db_user.get("balance", 0.0) or 0.0
    total_earned    = db_user.get("total_earned", 0.0) or 0.0
    total_withdrawn = db_user.get("total_withdrawn", 0.0) or 0.0
    pending         = get_pending_amount_for_user(user.id)
    method          = db_user.get("withdraw_method") or "Not set"
    wallet          = db_user.get("wallet_address") or ""
    bank            = db_user.get("bank_name") or ""
    account         = db_user.get("account_number") or ""

    if method == "trx":
        method_line = f"💎 TRX Wallet: <code>{wallet}</code>"
    elif method == "naira":
        method_line = f"🏦 Bank: {bank}\n💳 Account: <code>{account}</code>"
    else:
        method_line = "⚠️ No withdrawal method set"

    await update.message.reply_text(
        f"💰 <b>Your Wallet (USDT)</b>\n"
        f"────────────────\n"
        f"📈 Total earned: <b>${total_earned:.5f}</b>\n"
        f"────────────────\n"
        f"✅ Available: <b>${balance:.5f}</b>\n"
        f"⏳ Pending: <b>${pending:.5f}</b>\n"
        f"💸 Withdrawn: <b>${total_withdrawn:.5f}</b>\n\n"
        f"{method_line}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Withdraw Now",       callback_data="withdraw_now")],
            [InlineKeyboardButton("✏️ Set/Change Method",  callback_data="set_withdraw_method")],
        ])
    )

async def cmd_referral(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    db_user = get_user_full(user.id)
    if not db_user:
        await update.message.reply_text("Please /start first."); return
    code        = db_user.get("referral_code") or ""
    ref_count   = get_referral_count(user.id)
    ref_bonus   = get_referral_bonus()
    ref_link    = f"https://t.me/{BOT_USERNAME}?start={code}"
    await update.message.reply_text(
        f"👥 <b>Your Referral</b>\n\n"
        f"🔗 Your referral link:\n<code>{ref_link}</code>\n\n"
        f"👤 Total referrals: <b>{ref_count}</b>\n"
        f"🎁 Bonus per referral (first OTP): <b>${ref_bonus:.5f}</b>\n\n"
        f"<i>Share your link! You earn ${ref_bonus:.5f} every time a referral receives their first OTP.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share My Link", url=f"https://t.me/share/url?url={ref_link}&text=Join+Sifra7+OTP+Bot+and+earn+money!")],
        ])
    )

# ============================================================
#  CALLBACK HANDLER
# ============================================================

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user    = update.effective_user
    user_id = user.id
    data    = query.data
    await query.answer()

    if data == "check_join":
        joined = await check_membership(ctx.bot, user_id)
        if joined:
            await query.edit_message_text("✅ Verified! Welcome.")
            await ctx.bot.send_message(user_id,
                f"⚡ <b>Welcome, {user.first_name}!</b>\n\nChoose an option:",
                parse_mode="HTML", reply_markup=main_menu(user_id))
        else:
            await query.answer("❌ You haven't joined yet!", show_alert=True)
        return

    if not is_admin(user_id):
        db_user = get_user_full(user_id)
        if db_user and db_user.get("is_banned"):
            await query.answer("🚫 You are banned.", show_alert=True); return
        joined = await check_membership(ctx.bot, user_id)
        if not joined:
            await query.answer("⚠️ Please join first!", show_alert=True); return

    # ── Back to main menu ──
    if data == "back_main":
        ctx.user_data.pop("adm_state", None)
        ctx.user_data.pop("upload_numbers", None)
        ctx.user_data.pop("upload_service", None)
        ctx.user_data.pop("bank_name", None)
        await query.edit_message_text(
    "🏠 <b>Main Menu</b>\n\nChoose an option:",
    parse_mode="HTML"
        )
        await ctx.bot.send_message(
            user_id, "🏠 Back to main menu.",
            reply_markup=main_menu(user_id)
        )
        return

    # ── Numbers flow ──
    if data == "countries":
        countries = get_countries_with_count()
        if not countries:
            await query.edit_message_text("😔 No numbers available right now."); return
        buttons = [
            [InlineKeyboardButton(f"{get_country_info(c)[0]} {c} ({n})", callback_data=f"country:{c}")]
            for c, n in countries
        ]
        buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_main")])
        await query.edit_message_text("🌍 <b>Select a Country:</b>", parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("country:"):"
        country  = data.split(":", 1)[1]
        services = get_services_by_country(country)
        if not services:
            await query.edit_message_text(f"😔 No numbers for {country} right now."); return
        flag, _ = get_country_info(country)
        buttons = [
            [InlineKeyboardButton(f"{SERVICE_ICONS.get(s.upper(),'📨')} {s}", callback_data=f"service:{country}:{s}")]
            for s in services
        ]
        buttons.append([InlineKeyboardButton("🔙 Back to Countries", callback_data="countries")])
        await query.edit_message_text(f"{flag} <b>{country}</b> — Select Service:",
                                      parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("service:"):
        _, country, service = data.split(":", 2)
        numbers = assign_numbers(user_id, country, service, count=3)
        if not numbers:
            await query.edit_message_text(
                f"😔 No numbers available for <b>{service}</b> in <b>{country}</b>.",
                parse_mode="HTML"); return
        flag, _ = get_country_info(country)
        reward  = get_otp_reward()
        svc_icon = SERVICE_ICONS.get(service.upper(), "📨")
        num_lines = "\n".join([f"📞 <code>+{n}</code>" for n in numbers])
        await query.edit_message_text(
            f"✨ <b>Numbers Assigned!</b>\n\n"
            f"📡 Service: {svc_icon} <b>{service}</b>\n"
            f"🌍 Country: {flag} <b>{country}</b>\n\n"
            f"{num_lines}\n\n"
            f"⏳ <i>Waiting for OTP — you'll earn ${reward:.5f} per OTP!</i>",
            parse_mode="HTML", reply_markup=number_buttons(country, service)
        )

    elif data.startswith("change:"):
        _, country, service = data.split(":", 2)
        numbers = assign_numbers(user_id, country, service, count=3)
        if not numbers:
            await query.answer("😔 No more numbers available.", show_alert=True); return
        flag, _ = get_country_info(country)
        reward  = get_otp_reward()
        svc_icon = SERVICE_ICONS.get(service.upper(), "📨")
        num_lines = "\n".join([f"📞 <code>+{n}</code>" for n in numbers])
        await query.edit_message_text(
            f"🔄 <b>New Numbers Assigned!</b>\n\n"
            f"📡 Service: {svc_icon} <b>{service}</b>\n"
            f"🌍 Country: {flag} <b>{country}</b>\n\n"
            f"{num_lines}\n\n"
            f"⏳ <i>Waiting for OTP — you'll earn ${reward:.5f} per OTP!</i>",
            parse_mode="HTML", reply_markup=number_buttons(country, service)
        )

    # ── Wallet ──
    elif data == "set_withdraw_method":
        ctx.user_data.pop("adm_state", None)
        await query.edit_message_text(
            "💳 <b>Select Withdrawal Method:</b>",
            parse_mode="HTML", reply_markup=withdraw_method_keyboard()
        )

    elif data == "withdraw_trx":
        ctx.user_data["adm_state"] = "set_trx_wallet"
        await query.edit_message_text(
            "💎 <b>Send your TRX wallet address:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="set_withdraw_method")]])
        )

    elif data == "withdraw_naira":
        ctx.user_data["adm_state"] = "set_bank_name"
        await query.edit_message_text(
            "🏦 <b>Send your Bank Name:</b>\n\nExample: <code>Access Bank</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="set_withdraw_method")]])
        )

    elif data == "withdraw_now":
        db_user = get_user_full(user_id)
        balance = db_user.get("balance", 0.0) or 0.0 if db_user else 0.0
        method  = db_user.get("withdraw_method") if db_user else None
        if not method:
            await query.edit_message_text(
                "⚠️ Please set a withdrawal method first.",
                parse_mode="HTML", reply_markup=withdraw_method_keyboard()); return
        if balance < MIN_WITHDRAWAL:
            await query.edit_message_text(
                f"❌ Minimum withdrawal is <b>${MIN_WITHDRAWAL:.2f}</b>\n"
                f"Your balance: <b>${balance:.5f}</b>",
                parse_mode="HTML"); return

        if method == "trx":
            wallet = db_user.get("wallet_address") or ""
            summary = f"💎 TRX Wallet: <code>{wallet}</code>"
        else:
            bank    = db_user.get("bank_name") or ""
            account = db_user.get("account_number") or ""
            summary = f"🏦 Bank: {bank}\n💳 Account: <code>{account}</code>"

        await query.edit_message_text(
            f"💸 <b>Confirm Withdrawal</b>\n\n"
            f"Amount: <b>${balance:.5f}</b>\n"
            f"Method: <b>{'TRX' if method == 'trx' else 'Naira'}</b>\n"
            f"{summary}\n\n"
            f"Confirm?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirm",    callback_data="withdraw_confirm")],
                [InlineKeyboardButton("🔙 Back",       callback_data="back_wallet")],
            ])
        )

    elif data == "withdraw_confirm":
        db_user = get_user_full(user_id)
        balance = get_user_balance(user_id)
        method  = db_user.get("withdraw_method") if db_user else None
        ctx.user_data.pop("adm_state", None)
        if not method or balance < MIN_WITHDRAWAL:
            await query.edit_message_text("❌ Cannot process. Check balance and withdrawal method."); return

        wallet  = db_user.get("wallet_address") if method == "trx" else None
        bank    = db_user.get("bank_name") if method == "naira" else None
        account = db_user.get("account_number") if method == "naira" else None

        deduct_balance(user_id, balance)
        save_withdrawal(user_id, balance, method, wallet, bank, account)

        if method == "trx":
            notif_details = f"💎 TRX: <code>{wallet}</code>"
        else:
            notif_details = f"🏦 Bank: {bank}\n💳 Account: <code>{account}</code>"

        notif = (
            f"💸 <b>New Withdrawal Request!</b>\n\n"
            f"👤 User: <code>{user_id}</code> @{user.username or 'N/A'}\n"
            f"💰 Amount: <b>${balance:.5f}</b>\n"
            f"Method: <b>{'TRX' if method == 'trx' else 'Naira'}</b>\n"
            f"{notif_details}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"adm_approve:{user_id}:{balance:.5f}"),
             InlineKeyboardButton("❌ Reject",  callback_data=f"adm_reject:{user_id}")],
        ])
        for admin in ADMIN_IDS:
            try: await ctx.bot.send_message(admin, notif, parse_mode="HTML", reply_markup=kb)
            except Exception: pass

        await query.edit_message_text(
            f"✅ <b>Withdrawal Request Sent!</b>\n\n"
            f"Amount: <b>${balance:.5f}</b>\n"
            f"⏳ Admin will process it shortly.",
            parse_mode="HTML"
        )

    elif data == "back_wallet":
        db_user         = get_user_full(user_id)
        balance         = db_user.get("balance", 0.0) or 0.0 if db_user else 0.0
        total_earned    = db_user.get("total_earned", 0.0) or 0.0 if db_user else 0.0
        total_withdrawn = db_user.get("total_withdrawn", 0.0) or 0.0 if db_user else 0.0
        pending         = get_pending_amount_for_user(user_id)
        method          = db_user.get("withdraw_method") or "Not set" if db_user else "Not set"
        wallet          = db_user.get("wallet_address") or "" if db_user else ""
        bank            = db_user.get("bank_name") or "" if db_user else ""
        account         = db_user.get("account_number") or "" if db_user else ""
        if method == "trx":
            method_line = f"💎 TRX: <code>{wallet}</code>"
        elif method == "naira":
            method_line = f"🏦 {bank} | <code>{account}</code>"
        else:
            method_line = "⚠️ No method set"
        await query.edit_message_text(
            f"💰 <b>Your Wallet (USDT)</b>\n"
            f"────────────────\n"
            f"📈 Total earned: <b>${total_earned:.5f}</b>\n"
            f"✅ Available: <b>${balance:.5f}</b>\n"
            f"⏳ Pending: <b>${pending:.5f}</b>\n"
            f"💸 Withdrawn: <b>${total_withdrawn:.5f}</b>\n\n"
            f"{method_line}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💸 Withdraw Now",      callback_data="withdraw_now")],
                [InlineKeyboardButton("✏️ Set/Change Method", callback_data="set_withdraw_method")],
            ])
        )

    # ── Admin approve/reject withdrawal ──
    elif data.startswith("adm_approve:"):
        if not is_admin(user_id):
            await query.answer("⛔ Admins only!", show_alert=True); return
        _, target_uid, amount_str = data.split(":", 2)
        target_uid = int(target_uid); amount = float(amount_str)
        await query.edit_message_text(
            f"✅ <b>Approved</b>\nUser: <code>{target_uid}</code> | Amount: <b>${amount:.5f}</b>",
            parse_mode="HTML"
        )
        try:
            await ctx.bot.send_message(target_uid,
                f"✅ <b>Withdrawal of ${amount:.5f} approved!</b>\n💸 Payment will be sent shortly.",
                parse_mode="HTML")
        except Exception: pass

    elif data.startswith("adm_reject:"):
        if not is_admin(user_id):
            await query.answer("⛔ Admins only!", show_alert=True); return
        target_uid = int(data.split(":", 1)[1])
        await query.edit_message_text(
            f"❌ <b>Rejected</b>\nUser: <code>{target_uid}</code>", parse_mode="HTML")
        try:
            await ctx.bot.send_message(target_uid,
                "❌ <b>Your withdrawal was rejected.</b>\nContact support.", parse_mode="HTML")
        except Exception: pass

    # ── Back to admin panel ──
    elif data == "back_admin":
        if not is_admin(user_id): return
        ctx.user_data.pop("adm_state", None)
        ctx.user_data.pop("upload_numbers", None)
        ctx.user_data.pop("upload_service", None)
        ctx.user_data.pop("bank_name", None)
        total, today = get_otp_stats(); stock = get_stock_count()
        reward = get_otp_reward(); ref_bonus = get_referral_bonus()
        await query.edit_message_text(
            f"⚙️ <b>Admin Panel</b>\n\n"
            f"📦 Stock: <b>{stock}</b>\n"
            f"💵 OTP Reward: <b>${reward:.5f}</b>\n"
            f"🎁 Referral Bonus: <b>${ref_bonus:.5f}</b>\n"
            f"📩 Total OTPs: <b>{total}</b> | Today: <b>{today}</b>",
            parse_mode="HTML", reply_markup=admin_keyboard()
        )

    # ── Admin panel ──
    elif data == "adm_add":
        if not is_admin(user_id): return
        ctx.user_data["adm_state"] = "awaiting_numbers_file"
        await query.edit_message_text(
            "📂 <b>Send a .txt file</b> with one number per line:\n\n"
            "<code>2348012345678\n2338012345678\n2347081234567</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data.startswith("adm_svc:"):
        # Admin selected service after uploading file
        if not is_admin(user_id): return
        service = data.split(":", 1)[1]
        ctx.user_data["upload_service"] = service
        # Show country selection
        buttons = []
        countries_list = [
            "Nigeria","Ghana","Kenya","South Africa","Ethiopia","Tanzania",
            "Uganda","Senegal","Cameroon","Ivory Coast","Togo","Benin",
            "Mali","Guinea","Egypt","USA","UK","Germany","France","India",
            "Pakistan","Bangladesh","China","Vietnam","Thailand","Indonesia",
            "Philippines","Myanmar","Russia","Turkey","Ukraine","Brazil",
            "Venezuela","Mexico","Australia",
        ]
        row = []
        for i, c in enumerate(countries_list):
            flag, _ = get_country_info(c)
            row.append(InlineKeyboardButton(f"{flag} {c}", callback_data=f"adm_ctry:{c}"))
            if len(row) == 2:
                buttons.append(row); row = []
        if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="back_admin")])
        await query.edit_message_text(
            f"✅ Service: <b>{service}</b>\n\n🌍 <b>Now select Country:</b>",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("adm_ctry:"):
        if not is_admin(user_id): return
        country  = data.split(":", 1)[1]
        service  = ctx.user_data.pop("upload_service", "Unknown")
        numbers  = ctx.user_data.pop("upload_numbers", [])
        added    = 0
        for num in numbers:
            if add_number(num, country, service): added += 1
        ctx.user_data.pop("adm_state", None)
        await query.edit_message_text(
            f"✅ <b>{added}/{len(numbers)} numbers added!</b>\n"
            f"📡 Service: <b>{service}</b>\n"
            f"🌍 Country: <b>{country}</b>\n"
            f"📦 Stock now: <b>{get_stock_count()}</b>",
            parse_mode="HTML"
        )

    elif data == "adm_del":
        if not is_admin(user_id): return
        ctx.user_data["adm_state"] = "del_numbers"
        await query.edit_message_text(
            "🗑 <b>Send country name to delete its numbers:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_users":
        if not is_admin(user_id): return
        users = get_all_users()
        lines = "\n".join([f"• <code>{u['user_id']}</code> @{u['username'] or 'N/A'} — ${u['balance']:.5f}" for u in users[:30]])
        await query.edit_message_text(
            f"👥 <b>Total Users: {len(users)}</b>\n\n{lines}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_stats":
        if not is_admin(user_id): return
        total, today = get_otp_stats(); stock = get_stock_count()
        users = get_all_users(); reward = get_otp_reward(); ref_bonus = get_referral_bonus()
        await query.edit_message_text(
            f"📊 <b>Analytics</b>\n\n"
            f"👥 Users: <b>{len(users)}</b>\n"
            f"📦 Stock: <b>{stock}</b>\n"
            f"📩 Total OTPs: <b>{total}</b> | Today: <b>{today}</b>\n"
            f"💵 OTP Reward: <b>${reward:.5f}</b>\n"
            f"🎁 Referral Bonus: <b>${ref_bonus:.5f}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_ban":
        if not is_admin(user_id): return
        ctx.user_data["adm_state"] = "ban_user"
        await query.edit_message_text(
            "🚫 <b>Send User ID to ban:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_unban":
        if not is_admin(user_id): return
        ctx.user_data["adm_state"] = "unban_user"
        await query.edit_message_text(
            "✅ <b>Send User ID to unban:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_broadcast":
        if not is_admin(user_id): return
        ctx.user_data["adm_state"] = "broadcast"
        await query.edit_message_text(
            "📢 <b>Send the broadcast message now:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_set_reward":
        if not is_admin(user_id): return
        ctx.user_data["adm_state"] = "set_reward"
        await query.edit_message_text(
            f"💵 Current OTP Reward: <b>${get_otp_reward():.5f}</b>\n\nSend new amount (e.g. 0.003):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_set_ref_bonus":
        if not is_admin(user_id): return
        ctx.user_data["adm_state"] = "set_ref_bonus"
        await query.edit_message_text(
            f"🎁 Current Referral Bonus: <b>${get_referral_bonus():.5f}</b>\n\nSend new amount (e.g. 0.01):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_add_balance":
        if not is_admin(user_id): return
        ctx.user_data["adm_state"] = "add_balance"
        await query.edit_message_text(
            "💰 Send: <code>user_id amount</code>\nExample: <code>123456789 0.5</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

    elif data == "adm_withdrawals":
        if not is_admin(user_id): return
        pending = get_pending_withdrawals()
        if not pending:
            await query.edit_message_text("✅ No pending withdrawals."); return
        text = "💸 <b>Pending Withdrawals:</b>\n\n"
        for w in pending[:10]:
            if w["method"] == "trx":
                pay_info = f"💎 TRX: <code>{w['wallet']}</code>"
            else:
                pay_info = f"🏦 {w['bank_name']} | <code>{w['account_number']}</code>"
            text += (f"• User <code>{w['user_id']}</code>\n"
                     f"  Amount: <b>${w['amount']:.5f}</b>\n"
                     f"  {pay_info}\n"
                     f"  Time: {w['requested_at']}\n\n")
        await query.edit_message_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        )

# ============================================================
#  TEXT MESSAGE HANDLER
# ============================================================

async def handle_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    user  = update.effective_user
    text  = update.message.text.strip()
    state = ctx.user_data.get("adm_state")

    if state == "add_numbers":
        ctx.user_data.pop("adm_state", None)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        added = 0
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                if add_number(parts[0], parts[1], parts[2]): added += 1
        await update.message.reply_text(
            f"✅ <b>{added}/{len(lines)} numbers added!</b>\n📦 Stock: <b>{get_stock_count()}</b>",
            parse_mode="HTML"); return True

    elif state == "del_numbers":
        ctx.user_data.pop("adm_state", None)
        count = delete_numbers_by_country(text)
        await update.message.reply_text(f"🗑 Deleted <b>{count}</b> numbers for <b>{text}</b>.", parse_mode="HTML"); return True

    elif state == "ban_user":
        ctx.user_data.pop("adm_state", None)
        try:
            ban_user(int(text))
            await update.message.reply_text(f"🚫 User <code>{text}</code> banned.", parse_mode="HTML")
        except Exception: await update.message.reply_text("❌ Invalid user ID.")
        return True

    elif state == "unban_user":
        ctx.user_data.pop("adm_state", None)
        try:
            unban_user(int(text))
            await update.message.reply_text(f"✅ User <code>{text}</code> unbanned.", parse_mode="HTML")
        except Exception: await update.message.reply_text("❌ Invalid user ID.")
        return True

    elif state == "broadcast":
        ctx.user_data.pop("adm_state", None)
        users = get_all_users(); sent = 0
        for u in users:
            try:
                await ctx.bot.send_message(u["user_id"], f"📢 <b>Broadcast:</b>\n\n{text}", parse_mode="HTML")
                sent += 1
            except Exception: pass
        await update.message.reply_text(f"✅ Broadcast sent to <b>{sent}</b> users.", parse_mode="HTML"); return True

    elif state == "set_reward":
        ctx.user_data.pop("adm_state", None)
        try:
            reward = float(text); set_setting("otp_reward", reward)
            await update.message.reply_text(f"✅ OTP Reward set to <b>${reward:.5f}</b>", parse_mode="HTML")
        except Exception: await update.message.reply_text("❌ Invalid amount.")
        return True

    elif state == "set_ref_bonus":
        ctx.user_data.pop("adm_state", None)
        try:
            bonus = float(text); set_setting("referral_bonus", bonus)
            await update.message.reply_text(f"✅ Referral Bonus set to <b>${bonus:.5f}</b>", parse_mode="HTML")
        except Exception: await update.message.reply_text("❌ Invalid amount.")
        return True

    elif state == "add_balance":
        ctx.user_data.pop("adm_state", None)
        parts = text.split()
        if len(parts) == 2:
            try:
                uid = int(parts[0]); amount = float(parts[1])
                add_balance(uid, amount)
                await update.message.reply_text(
                    f"✅ Added <b>${amount:.5f}</b> to user <code>{uid}</code>", parse_mode="HTML")
                try:
                    await ctx.bot.send_message(uid,
                        f"🎁 <b>Bonus Added!</b>\n\n"
                        f"💰 <b>${amount:.5f}</b> added to your balance!\n"
                        f"💼 New balance: <b>${get_user_balance(uid):.5f}</b>",
                        parse_mode="HTML")
                except Exception: pass
            except Exception: await update.message.reply_text("❌ Error. Usage: user_id amount")
        else: await update.message.reply_text("❌ Usage: user_id amount")
        return True

    # ── Withdrawal method setup (for regular users) ──
    elif state == "set_trx_wallet":
        ctx.user_data.pop("adm_state", None)
        conn = get_conn()
        conn.execute("UPDATE users SET wallet_address=?, withdraw_method='trx' WHERE user_id=?", (text, user.id))
        conn.commit(); conn.close()
        await update.message.reply_text(
            f"✅ <b>TRX wallet saved!</b>\n\n💎 <code>{text}</code>", parse_mode="HTML"); return True

    elif state == "set_bank_name":
        ctx.user_data["adm_state"] = "set_account_number"
        ctx.user_data["bank_name"] = text
        await update.message.reply_text(
            f"✅ Bank: <b>{text}</b>\n\n💳 Now send your <b>Account Number</b>:", parse_mode="HTML"); return True

    elif state == "set_account_number":
        ctx.user_data.pop("adm_state", None)
        bank = ctx.user_data.pop("bank_name", "")
        conn = get_conn()
        conn.execute(
            "UPDATE users SET bank_name=?, account_number=?, withdraw_method='naira' WHERE user_id=?",
            (bank, text, user.id)
        )
        conn.commit(); conn.close()
        await update.message.reply_text(
            f"✅ <b>Bank details saved!</b>\n\n🏦 {bank}\n💳 <code>{text}</code>", parse_mode="HTML"); return True

    return False

async def handle_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    text    = update.message.text
    db_user = get_or_create_user(user.id, user.username or "", user.full_name or "")

    if db_user["is_banned"]:
        await update.message.reply_text("🚫 You are banned."); return

    if not is_admin(user.id):
        joined = await check_membership(ctx.bot, user.id)
        if not joined:
            await send_join_message(update.message); return

    if ctx.user_data.get("adm_state"):
        handled = await handle_admin_text(update, ctx)
        if handled: return

    if text == "🏢 Numbers":    await cmd_numbers(update, ctx)
    elif text == "📊 Status":   await cmd_status(update, ctx)
    elif text == "📦 Stock":    await cmd_stock(update, ctx)
    elif text == "💰 Wallet":   await cmd_wallet(update, ctx)
    elif text == "👥 Referral": await cmd_referral(update, ctx)
    elif text == "⚙️ Admin Panel" and is_admin(user.id):
        await show_admin_panel(update.message, ctx)
    else:
        await update.message.reply_text("❓ Use the menu below.", reply_markup=main_menu(user.id))


# ============================================================
#  DOCUMENT HANDLER (Admin uploads .txt file of numbers)
# ============================================================

async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id): return
    if ctx.user_data.get("adm_state") != "awaiting_numbers_file": return

    doc = update.message.document
    if not doc or not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Please send a <b>.txt</b> file.", parse_mode="HTML")
        return

    file = await ctx.bot.get_file(doc.file_id)
    content = bytes()
    import io
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)
    lines = [l.strip() for l in buf.read().decode("utf-8").splitlines() if l.strip()]

    if not lines:
        await update.message.reply_text("❌ File is empty or invalid."); return

    ctx.user_data["upload_numbers"] = lines
    ctx.user_data["adm_state"] = "awaiting_service"

    # Show service selection
    services = ["WhatsApp","Facebook","Instagram","Telegram","Google",
                "Twitter","TikTok","Snapchat","Amazon","PayPal",
                "Microsoft","Apple","Netflix","Discord","Uber","LinkedIn"]
    buttons = []
    row = []
    for i, s in enumerate(services):
        icon = SERVICE_ICONS.get(s.upper(), "📨")
        row.append(InlineKeyboardButton(f"{icon} {s}", callback_data=f"adm_svc:{s}"))
        if len(row) == 2:
            buttons.append(row); row = []
    if row: buttons.append(row)

    await update.message.reply_text(
        f"✅ <b>{len(lines)} numbers loaded!</b>\n\n📡 <b>Select Service:</b>",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)
    )

# ============================================================
#  ENTRY POINT
# ============================================================

async def post_init(app: Application):
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("start",    "Start the bot"),
        BotCommand("withdraw", "Withdraw your earnings"),
        BotCommand("referral", "Get your referral link"),
    ])
    asyncio.create_task(start_polling(app.bot))

def main():
    init_db()
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("admin",    cmd_admin))
    app.add_handler(CommandHandler("withdraw", cmd_wallet))
    app.add_handler(CommandHandler("referral", cmd_referral))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))
    logger.info("✅ Sifra7 Bot v2 is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
