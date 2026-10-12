"""
SHOP BOT  •  aiogram 3.x  •  SQLite

Установка:   pip install -U aiogram pillow
Запуск:      python bot.py
Перед запуском впиши BOT_TOKEN и ADMIN_IDS (ниже) или задай их переменными окружения.
Для пополнения через Crypto Bot: @CryptoBot → Crypto Pay → Create App → скопируй токен в CRYPTO_TOKEN.
"""
import asyncio
import html
import logging
import os
import sqlite3
import tempfile
from datetime import datetime

import aiohttp
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ======================= НАСТРОЙКИ =======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8851216228:AAFyUm-arqv2I7oKaVqBvRd0ZJGnOOTpz8I")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "8759747461").split(",") if x.strip()}
SUPPORT = "@VladkaSmyrfanka"                                   # поддержка
PAY_LINK = os.getenv("PAY_LINK", "http://t.me/send?start=IVXbX0mcEeBt")   # счёт в Crypto Bot (ручное подтверждение)
SHOP_NAME = "Sm Hosting"
CURRENCY = "$"
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "")      # токен Crypto Pay (@CryptoBot)
CRYPTO_TESTNET = os.getenv("CRYPTO_TESTNET", "0") == "1"   # 1 = тестовая сеть (@CryptoTestnetBot)
CRYPTO_API = "https://testnet-pay.crypt.bot/api" if CRYPTO_TESTNET else "https://pay.crypt.bot/api"
MIN_TOPUP = 1.0                                # минимальное пополнение, $
DB_PATH = "shop.db"
BANNER_PATH = "banner.jpg"      # картинка приветствия (если нет файла — создастся автоматически)
AUTO_BACKUP_HOURS = 24          # автобэкап базы админам

esc = html.escape


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def money(x):
    s = f"{float(x):.2f}"
    return CURRENCY + (s[:-3] if s.endswith(".00") else s)


def num(s):
    try:
        return float(s.replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


# ======================= БАЗА ДАННЫХ =======================
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT, name TEXT, lang TEXT DEFAULT 'ru',
    balance REAL DEFAULT 0, banned INTEGER DEFAULT 0, reg_date TEXT);
CREATE TABLE IF NOT EXISTS sections(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, section_id INTEGER, name TEXT,
    descr TEXT, price REAL, stock INTEGER, content TEXT);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER,
    product_name TEXT, price REAL, date TEXT);
CREATE TABLE IF NOT EXISTS topups(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL,
    proof TEXT, status TEXT DEFAULT 'pending', date TEXT, invoice_id INTEGER, pay_url TEXT);
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, author TEXT, text TEXT, date TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS texts(key TEXT PRIMARY KEY, value TEXT);
""")
for _col in ("invoice_id INTEGER", "pay_url TEXT"):
    try:
        db.execute(f"ALTER TABLE topups ADD COLUMN {_col}")
    except sqlite3.OperationalError:
        pass
db.commit()


def one(sql, a=()):
    return db.execute(sql, a).fetchone()


def many(sql, a=()):
    return db.execute(sql, a).fetchall()


def run(sql, a=()):
    cur = db.execute(sql, a)
    db.commit()
    return cur.lastrowid


def get_setting(k, d=""):
    r = one("SELECT value FROM settings WHERE key=?", (k,))
    return r["value"] if r else d


def set_setting(k, v):
    run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))


# ======================= ТЕКСТЫ / ЯЗЫКИ =======================
I18N = {
    "ru": {
        "btn_profile": "👤 Профиль", "btn_products": "🛍 Товары", "btn_reviews": "⭐ Отзывы",
        "btn_rules": "📜 Правила", "btn_faq": "❓ FAQ", "btn_support": "🆘 Поддержка", "btn_lang": "🌐 Язык",
        "back": "⬅️ Назад", "topup_btn": "➕ Пополнить", "orders_btn": "🧾 Покупки", "buy_btn": "🛒 Купить",
        "confirm_btn": "✅ Подтвердить", "cancel_btn": "✖️ Отмена",
        "start": "✨ <b>Добро пожаловать в {shop}, {name}!</b>\n\nМагазин цифровых товаров с моментальной выдачей.\n\n"
                 "⚡ Быстро  •  🔒 Надёжно  •  🕒 24/7\n\nВыберите раздел ниже 👇",
        "profile": "👤 <b>Ваш профиль</b>",
        "products": "🛍 <b>Каталог товаров</b>\nВыберите раздел:",
        "reviews": "⭐ <b>Отзывы наших клиентов</b>",
        "rules": "📜 <b>Правила и соглашение</b>\n\n1. Покупая товар, вы соглашаетесь с правилами магазина.\n"
                 "2. Цифровые товары возврату не подлежат после выдачи.\n3. Администрация вправе отказать в обслуживании.",
        "faq": "❓ <b>Частые вопросы</b>\n\n<b>Как купить?</b>\nПополните баланс и выберите товар в каталоге.\n\n"
               "<b>Как быстро выдаётся товар?</b>\nМоментально после покупки.",
        "support": "🆘 <b>Поддержка</b>\n\nНапишите нам: @Mormonsq",
        "lang": "🌐 <b>Выбор языка</b>\nChoose your language:",
        "topup": "➕ <b>Пополнение баланса</b>\n\nОплата через @CryptoBot: USDT, TON, BTC и другие монеты. Сумма указывается в долларах.",
        "topup_ask": "Введите сумму пополнения в долларах (от 1 $):",
        "topup_min": "Минимальная сумма — {min}",
        "topup_invoice": "💳 <b>Счёт #{id}</b> на {amount}\n\n1. Нажмите «Оплатить в Crypto Bot» и оплатите счёт.\n"
                         "2. Вернитесь сюда и нажмите «✅ Отправил».\n\nБаланс пополнится сразу после подтверждения оплаты. Счёт действует 1 час.",
        "pay_btn": "💸 Оплатить в Crypto Bot", "check_btn": "✅ Отправил",
        "topup_paid": "✅ Оплата получена! Баланс пополнен на {amount}.",
        "topup_wait": "Оплата ещё не поступила. Оплатите счёт в Crypto Bot и нажмите «Отправил» снова.", "topup_exp": "Счёт истёк или закрыт. Создайте новый.",
        "crypto_off": "Оплата временно недоступна. Попробуйте позже.",
        "manual_invoice": "💳 <b>Заявка #{id}</b> на {amount}\n\n1. Нажмите «Оплатить в Crypto Bot» и оплатите {amount}.\n"
                          "2. Вернитесь сюда и нажмите «✅ Отправил».\n\nБаланс пополнится после проверки оплаты администратором.",
        "topup_sent": "✅ Заявка отправлена администратору. Баланс будет пополнен после проверки оплаты.",
        "topup_ok": "✅ Ваш баланс пополнен на {amount}!",
        "topup_no": "❌ Заявка на пополнение {amount} отклонена. Обратитесь в поддержку.",
        "empty": "Пока здесь пусто.", "no_orders": "Покупок пока нет.", "no_reviews": "Отзывов пока нет.",
        "p_bal": "💰 Баланс", "p_orders": "🛒 Покупок", "p_reg": "📅 Регистрация",
        "price": "Цена", "in_stock": "В наличии", "balance": "Ваш баланс",
        "confirm_q": "Подтвердить покупку?", "out_of_stock": "Товар закончился", "no_funds": "Недостаточно средств на балансе",
        "bought": "✅ <b>Покупка успешна!</b>", "your_item": "Ваш товар", "bad_number": "❗ Введите положительное число",
        "lang_set": "Язык изменён",
    },
    "en": {
        "btn_profile": "👤 Profile", "btn_products": "🛍 Products", "btn_reviews": "⭐ Reviews",
        "btn_rules": "📜 Rules", "btn_faq": "❓ FAQ", "btn_support": "🆘 Support", "btn_lang": "🌐 Language",
        "back": "⬅️ Back", "topup_btn": "➕ Top up", "orders_btn": "🧾 Purchases", "buy_btn": "🛒 Buy",
        "confirm_btn": "✅ Confirm", "cancel_btn": "✖️ Cancel",
        "start": "✨ <b>Welcome to {shop}, {name}!</b>\n\nDigital goods store with instant delivery.\n\n"
                 "⚡ Fast  •  🔒 Safe  •  🕒 24/7\n\nChoose a section below 👇",
        "profile": "👤 <b>Your profile</b>",
        "products": "🛍 <b>Product catalog</b>\nChoose a section:",
        "reviews": "⭐ <b>Customer reviews</b>",
        "rules": "📜 <b>Rules & agreement</b>\n\n1. By purchasing you accept the store rules.\n"
                 "2. Digital goods are non-refundable once delivered.\n3. Administration may refuse service.",
        "faq": "❓ <b>FAQ</b>\n\n<b>How to buy?</b>\nTop up your balance and pick a product.\n\n"
               "<b>How fast is delivery?</b>\nInstantly after purchase.",
        "support": "🆘 <b>Support</b>\n\nContact us: @Mormonsq",
        "lang": "🌐 <b>Language</b>\nВыберите язык:",
        "topup": "➕ <b>Balance top-up</b>\n\nPay via @CryptoBot: USDT, TON, BTC and more. The amount is in US dollars.",
        "topup_ask": "Enter the top-up amount in dollars (from $1):",
        "topup_min": "Minimum amount is {min}",
        "topup_invoice": "💳 <b>Invoice #{id}</b> for {amount}\n\n1. Tap “Pay in Crypto Bot” and pay the invoice.\n"
                         "2. Come back and tap “✅ I've paid”.\n\nYour balance is credited right after the payment is confirmed. The invoice is valid for 1 hour.",
        "pay_btn": "💸 Pay in Crypto Bot", "check_btn": "✅ I've paid",
        "topup_paid": "✅ Payment received! Balance topped up by {amount}.",
        "topup_wait": "Payment not received yet. Pay the invoice in Crypto Bot and tap “I've paid” again.", "topup_exp": "Invoice expired or closed. Create a new one.",
        "crypto_off": "Payments are temporarily unavailable. Try again later.",
        "manual_invoice": "💳 <b>Request #{id}</b> for {amount}\n\n1. Tap “Pay in Crypto Bot” and pay {amount}.\n"
                          "2. Come back and tap “✅ I've paid”.\n\nYour balance will be topped up after the admin checks the payment.",
        "topup_sent": "✅ Request sent to the admin. Your balance will be topped up after the payment is verified.",
        "topup_ok": "✅ Your balance has been topped up by {amount}!",
        "topup_no": "❌ Your top-up request for {amount} was declined. Contact support.",
        "empty": "Nothing here yet.", "no_orders": "No purchases yet.", "no_reviews": "No reviews yet.",
        "p_bal": "💰 Balance", "p_orders": "🛒 Purchases", "p_reg": "📅 Registered",
        "price": "Price", "in_stock": "In stock", "balance": "Your balance",
        "confirm_q": "Confirm purchase?", "out_of_stock": "Out of stock", "no_funds": "Insufficient balance",
        "bought": "✅ <b>Purchase successful!</b>", "your_item": "Your item", "bad_number": "❗ Enter a positive number",
        "lang_set": "Language changed",
    },
}

# какие тексты админ может менять через «Описание кнопок»
EDITABLE = {
    "start": "👋 Приветствие (/start)", "profile": "👤 Профиль (заголовок)", "products": "🛍 Товары",
    "reviews": "⭐ Отзывы (заголовок)", "rules": "📜 Правила", "faq": "❓ FAQ",
    "support": "🆘 Поддержка", "lang": "🌐 Язык", "topup": "➕ Пополнение (реквизиты)",
}

STYLES = {"none": "⚪ Без цвета", "primary": "🔵 Синие", "success": "🟢 Зелёные", "danger": "🔴 Красные"}


def t(key, lang):
    r = one("SELECT value FROM texts WHERE key=?", (f"{key}:{lang}",))
    return r["value"] if r else I18N[lang][key]


def lang_of(uid):
    r = one("SELECT lang FROM users WHERE id=?", (uid,))
    return r["lang"] if r else "ru"


def register(u):
    if not one("SELECT 1 FROM users WHERE id=?", (u.id,)):
        lg = "ru" if (u.language_code or "ru").startswith(("ru", "uk", "be", "kk")) else "en"
        run("INSERT INTO users(id,username,name,lang,reg_date) VALUES(?,?,?,?,?)",
            (u.id, u.username, u.full_name, lg, now()))
    else:
        run("UPDATE users SET username=?, name=? WHERE id=?", (u.username, u.full_name, u.id))


# ======================= КНОПКИ / ИНТЕРФЕЙС =======================
def B(text, data, colored=True):
    """Inline-кнопка. Цвет задаётся админом (поле style, нужен свежий aiogram / Bot API 9.4+)."""
    kw = {}
    st = get_setting("btn_style", "primary")
    if colored and st in ("primary", "success", "danger"):
        kw["style"] = st
    return InlineKeyboardButton(text=text, callback_data=data, **kw)


def nav(lang, back="menu"):
    kb = InlineKeyboardBuilder()
    kb.row(B(t("back", lang), back, False))
    return kb.as_markup()


async def show(c: CallbackQuery, text, kb):
    """Редактирует текущее сообщение (и фото-подпись, и обычный текст)."""
    msg = c.message
    try:
        if msg.photo:
            if len(text) <= 1000:
                await msg.edit_caption(caption=text, reply_markup=kb)
            else:
                await msg.delete()
                await msg.answer(text, reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await msg.answer(text, reply_markup=kb)


def make_banner():
    if os.path.exists(BANNER_PATH):
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    w, h = 1280, 720
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        k = y / h
        d.line([(0, y), (w, y)], fill=(int(25 + 70 * k), int(25 + 40 * k), int(95 + 120 * k)))
    for r, a in ((520, 40), (380, 60), (240, 80)):
        d.ellipse([w - r, -r // 2, w + r // 2, r], outline=(255, 255, 255), width=2)
    try:
        big, small = ImageFont.load_default(size=150), ImageFont.load_default(size=44)
    except TypeError:
        big = small = ImageFont.load_default()
    d.text((w // 2, h // 2 - 30), SHOP_NAME, font=big, fill="white", anchor="mm")
    d.text((w // 2, h // 2 + 100), "digital store  •  instant delivery", font=small, fill=(200, 215, 255), anchor="mm")
    img.save(BANNER_PATH, quality=92)


def menu_view(uid):
    u = one("SELECT * FROM users WHERE id=?", (uid,))
    lang = u["lang"] if u else "ru"
    name = u["name"] if u else ""
    cap = t("start", lang).replace("{name}", esc(name)).replace("{shop}", esc(SHOP_NAME))
    kb = InlineKeyboardBuilder()
    kb.row(B(t("btn_profile", lang), "profile"), B(t("btn_products", lang), "products"))
    kb.row(B(t("btn_reviews", lang), "reviews"), B(t("btn_faq", lang), "page:faq"))
    kb.row(B(t("btn_rules", lang), "page:rules"), B(t("btn_support", lang), "page:support"))
    kb.row(B(t("btn_lang", lang), "lang"))
    return cap, kb.as_markup()


async def send_menu(msg: Message, uid: int):
    cap, kb = menu_view(uid)
    fid = get_setting("start_photo")
    src = fid or (FSInputFile(BANNER_PATH) if os.path.exists(BANNER_PATH) else None)
    if src is None:
        return await msg.answer(cap, reply_markup=kb)
    try:
        sent = await msg.answer_photo(src, caption=cap, reply_markup=kb)
    except TelegramBadRequest:
        if fid:
            set_setting("start_photo", "")
            return await send_menu(msg, uid)
        raise
    if not fid and sent.photo:
        set_setting("start_photo", sent.photo[-1].file_id)


# ======================= СОСТОЯНИЯ =======================
class TopUp(StatesGroup):
    amount = State()


class AdminSt(StatesGroup):
    section_name = State()
    p_name = State()
    p_descr = State()
    p_price = State()
    p_stock = State()
    p_content = State()
    new_price = State()
    new_stock = State()
    ann = State()
    rev_author = State()
    rev_text = State()
    user_q = State()
    user_amount = State()
    text_edit = State()
    photo = State()


# ======================= MIDDLEWARE (бан / техработы) =======================
class Guard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and user.id not in ADMIN_IDS:
            row = one("SELECT banned FROM users WHERE id=?", (user.id,))
            if row and row["banned"]:
                return
            if get_setting("maintenance") == "1":
                if isinstance(event, CallbackQuery):
                    await event.answer("🛠 Технические работы / Maintenance", show_alert=True)
                elif isinstance(event, Message):
                    await event.answer("🛠 Технические работы / Maintenance")
                return
        return await handler(event, data)


base = Router()
user = Router()
admin = Router()
admin.message.filter(F.from_user.id.in_(ADMIN_IDS))
admin.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


# ======================= БАЗОВЫЕ КОМАНДЫ =======================
@base.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    register(m.from_user)
    await send_menu(m, m.from_user.id)


def panel_kb():
    pend = one("SELECT COUNT(*) n FROM topups WHERE status='sent' OR (status='pending' AND invoice_id IS NOT NULL)")["n"]
    maint = get_setting("maintenance") == "1"
    items = [
        ("💵 Изменить цену", "ad_price"), ("➕ Добавить товар", "ad_addp"),
        ("📂 Добавить раздел", "ad_adds"), ("📢 Объявления", "ad_ann"),
        ("⭐ Добавить отзыв", "ad_addrev"), ("👤 Пользователь", "ad_user"),
        ("💾 Бэкап базы", "ad_backup"), ("📦 Изменить остаток", "ad_stock"),
        ("🗑 Удалить товар", "ad_delp"), ("🎨 Цвета кнопок", "ad_color"),
        ("📊 Статистика", "ad_stats"), ("🚫 Удалить отзыв", "ad_delrev"),
        (f"💳 Заявки на пополнение ({pend})", "ad_topups"), ("✏️ Описание кнопок", "ad_texts"),
        ("🧾 Последние заказы", "ad_orders"), ("🖼 Фото приветствия", "ad_photo"),
        ("🗂 Удалить раздел", "ad_dels"),
        (f"🛠 Техработы: {'ВКЛ' if maint else 'ВЫКЛ'}", "ad_maint"),
    ]
    kb = InlineKeyboardBuilder()
    for text, data in items:
        kb.add(B(text, data))
    kb.adjust(2)
    return kb.as_markup()


PANEL_TEXT = "🛠 <b>Админ-панель</b>\nВыберите действие:"


@base.message(Command("adm"))
async def cmd_adm(m: Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await m.answer(PANEL_TEXT, reply_markup=panel_kb())


# ======================= ПОЛЬЗОВАТЕЛЬ =======================
@user.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    if c.message.photo:
        cap, kb = menu_view(c.from_user.id)
        await show(c, cap, kb)
    else:
        try:
            await c.message.delete()
        except TelegramBadRequest:
            pass
        await send_menu(c.message, c.from_user.id)
    await c.answer()


@user.callback_query(F.data.in_({"page:rules", "page:faq", "page:support"}))
async def cb_page(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    await show(c, t(c.data.split(":")[1], lang), nav(lang))
    await c.answer()


@user.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    u = one("SELECT * FROM users WHERE id=?", (c.from_user.id,))
    lang = u["lang"]
    n = one("SELECT COUNT(*) n FROM orders WHERE user_id=?", (u["id"],))["n"]
    text = (f"{t('profile', lang)}\n\n🆔 ID: <code>{u['id']}</code>\n👤 {esc(u['name'])}\n"
            f"{I18N[lang]['p_bal']}: <b>{money(u['balance'])}</b>\n"
            f"{I18N[lang]['p_orders']}: <b>{n}</b>\n{I18N[lang]['p_reg']}: {u['reg_date'][:10]}")
    kb = InlineKeyboardBuilder()
    kb.row(B(t("topup_btn", lang), "topup"), B(t("orders_btn", lang), "orders"))
    kb.row(B(t("back", lang), "menu", False))
    await show(c, text, kb.as_markup())
    await c.answer()


@user.callback_query(F.data == "orders")
async def cb_orders(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    rows = many("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (c.from_user.id,))
    text = "🧾\n\n" + ("\n".join(f"#{r['id']} • {esc(r['product_name'])} • {money(r['price'])} • {r['date'][:10]}"
                                for r in rows) or t("no_orders", lang))
    await show(c, text, nav(lang, "profile"))
    await c.answer()


# ---- пополнение ----
@user.callback_query(F.data == "topup")
async def cb_topup(c: CallbackQuery, state: FSMContext):
    lang = lang_of(c.from_user.id)
    if not CRYPTO_TOKEN and not PAY_LINK:
        return await c.answer(I18N[lang]["crypto_off"], show_alert=True)
    await state.set_state(TopUp.amount)
    await show(c, f"{t('topup', lang)}\n\n{t('topup_ask', lang)}", nav(lang, "profile"))
    await c.answer()


async def crypto_call(method, params=None):
    if not CRYPTO_TOKEN:
        raise RuntimeError("CRYPTO_TOKEN is not set")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
        async with http.post(f"{CRYPTO_API}/{method}", json=params or {},
                             headers={"Crypto-Pay-API-Token": CRYPTO_TOKEN}) as r:
            data = await r.json()
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error")))
    return data["result"]


@user.message(TopUp.amount, F.text)
async def topup_amount(m: Message, state: FSMContext):
    lang = lang_of(m.from_user.id)
    v = num(m.text)
    if v is None or v <= 0:
        return await m.answer(t("bad_number", lang))
    if v < MIN_TOPUP:
        return await m.answer(I18N[lang]["topup_min"].format(min=money(MIN_TOPUP)))
    v = round(v, 2)
    if not CRYPTO_TOKEN:
        # ручной режим: оплата по ссылке, админ подтверждает после кнопки «Отправил»
        tid = run("INSERT INTO topups(user_id,amount,date,pay_url) VALUES(?,?,?,?)",
                  (m.from_user.id, v, now(), PAY_LINK))
        await state.clear()
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text=I18N[lang]["pay_btn"], url=PAY_LINK))
        kb.row(B(I18N[lang]["check_btn"], f"tpsent:{tid}"))
        kb.row(B(t("back", lang), "menu", False))
        return await m.answer(I18N[lang]["manual_invoice"].format(id=tid, amount=money(v)), reply_markup=kb.as_markup())
    try:
        inv = await crypto_call("createInvoice", {
            "currency_type": "fiat", "fiat": "USD", "amount": f"{v:.2f}",
            "description": f"{SHOP_NAME} top-up", "payload": str(m.from_user.id),
            "expires_in": 3600, "allow_comments": False})
    except Exception as e:
        logging.error("createInvoice failed: %s", e)
        await state.clear()
        return await m.answer(I18N[lang]["crypto_off"])
    url = inv.get("bot_invoice_url") or inv.get("pay_url")
    tid = run("INSERT INTO topups(user_id,amount,date,invoice_id,pay_url) VALUES(?,?,?,?,?)",
              (m.from_user.id, v, now(), inv["invoice_id"], url))
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=I18N[lang]["pay_btn"], url=url))
    kb.row(B(I18N[lang]["check_btn"], f"tpchk:{tid}"))
    kb.row(B(t("back", lang), "menu", False))
    await m.answer(I18N[lang]["topup_invoice"].format(id=tid, amount=money(v)), reply_markup=kb.as_markup())


async def settle_topup(bot: Bot, tid):
    """Проверяет счёт в Crypto Pay и, если оплачен, зачисляет баланс (один раз)."""
    tp = one("SELECT * FROM topups WHERE id=?", (tid,))
    if not tp:
        return "none"
    if tp["status"] != "pending" or not tp["invoice_id"]:
        return tp["status"]
    res = await crypto_call("getInvoices", {"invoice_ids": str(tp["invoice_id"])})
    items = res.get("items", []) if isinstance(res, dict) else res
    if not items:
        return "pending"
    st = items[0].get("status")
    if st == "paid":
        cur = db.execute("UPDATE topups SET status='approved' WHERE id=? AND status='pending'", (tid,))
        db.commit()
        if cur.rowcount:
            run("UPDATE users SET balance=balance+? WHERE id=?", (tp["amount"], tp["user_id"]))
            lang = lang_of(tp["user_id"])
            try:
                await bot.send_message(tp["user_id"], I18N[lang]["topup_paid"].format(amount=money(tp["amount"])))
            except Exception:
                pass
            u = one("SELECT name FROM users WHERE id=?", (tp["user_id"],))
            for a in ADMIN_IDS:
                try:
                    await bot.send_message(a, f"💰 Пополнение {money(tp['amount'])} от {esc(u['name'])} "
                                              f"(<code>{tp['user_id']}</code>)")
                except Exception:
                    pass
        return "approved"
    if st == "expired":
        run("UPDATE topups SET status='expired' WHERE id=? AND status='pending'", (tid,))
        return "expired"
    return "pending"


@user.callback_query(F.data.startswith("tpchk:"))
async def cb_topup_check(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    tid = int(c.data.split(":")[1])
    tp = one("SELECT * FROM topups WHERE id=?", (tid,))
    if not tp or tp["user_id"] != c.from_user.id:
        return await c.answer()
    try:
        st = await settle_topup(c.bot, tid)
    except Exception as e:
        logging.warning("check invoice failed: %s", e)
        return await c.answer(I18N[lang]["crypto_off"], show_alert=True)
    if st == "approved":
        await show(c, I18N[lang]["topup_paid"].format(amount=money(tp["amount"])), nav(lang, "profile"))
        await c.answer()
    elif st in ("expired", "rejected"):
        await c.answer(I18N[lang]["topup_exp"], show_alert=True)
    else:
        await c.answer(I18N[lang]["topup_wait"], show_alert=True)


@user.callback_query(F.data.startswith("tpsent:"))
async def cb_topup_sent(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    tid = int(c.data.split(":")[1])
    tp = one("SELECT * FROM topups WHERE id=?", (tid,))
    if not tp or tp["user_id"] != c.from_user.id:
        return await c.answer()
    if tp["status"] != "pending":
        return await c.answer(I18N[lang]["topup_sent"], show_alert=True)
    run("UPDATE topups SET status='sent' WHERE id=? AND status='pending'", (tid,))
    for a in ADMIN_IDS:
        try:
            await send_topup_card(c.bot, a, tid)
        except Exception as e:
            logging.warning("notify admin failed: %s", e)
    await show(c, I18N[lang]["topup_sent"], nav(lang, "profile"))
    await c.answer()


async def topup_watcher(bot: Bot):
    while True:
        await asyncio.sleep(20)
        if not CRYPTO_TOKEN:
            continue
        for r in many("SELECT id FROM topups WHERE status='pending' AND invoice_id IS NOT NULL "
                      "ORDER BY id DESC LIMIT 50"):
            try:
                await settle_topup(bot, r["id"])
            except Exception as e:
                logging.warning("watcher: %s", e)


async def send_topup_card(bot: Bot, chat_id, tid):
    tp = one("SELECT * FROM topups WHERE id=?", (tid,))
    u = one("SELECT * FROM users WHERE id=?", (tp["user_id"],))
    status = {"pending": "⏳ ожидает оплаты", "sent": "📨 пользователь нажал «Отправил» — проверьте оплату",
              "approved": "✅ оплачена", "rejected": "❌ отклонена", "expired": "⌛ истёк"}[tp["status"]]
    inv_line = f"🧾 Invoice: <code>{tp['invoice_id']}</code>\n" if tp["invoice_id"] else ""
    text = (f"💳 <b>Заявка #{tid}</b>\n👤 {esc(u['name'])} (<code>{u['id']}</code>)\n"
            f"💰 {money(tp['amount'])}\n{inv_line}🕒 {tp['date']}\n📌 {status}")
    kb = InlineKeyboardBuilder()
    if tp["status"] in ("pending", "sent"):
        kb.row(B("✅ Зачесть вручную", f"tpok:{tid}"), B("❌ Отклонить", f"tprej:{tid}"))
    kb.row(B("⬅️ К заявкам", "ad_topups", False))
    await bot.send_message(chat_id, text, reply_markup=kb.as_markup())


# ---- каталог ----
@user.callback_query(F.data == "products")
async def cb_products(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    secs = many("SELECT s.id, s.name, (SELECT COUNT(*) FROM products p WHERE p.section_id=s.id) n FROM sections s")
    kb = InlineKeyboardBuilder()
    for s in secs:
        kb.row(B(f"📂 {s['name']} ({s['n']})", f"sec:{s['id']}"))
    kb.row(B(t("back", lang), "menu", False))
    text = t("products", lang) + ("" if secs else f"\n\n{t('empty', lang)}")
    await show(c, text, kb.as_markup())
    await c.answer()


@user.callback_query(F.data.startswith("sec:"))
async def cb_section(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    sid = int(c.data.split(":")[1])
    sec = one("SELECT * FROM sections WHERE id=?", (sid,))
    prods = many("SELECT * FROM products WHERE section_id=?", (sid,))
    kb = InlineKeyboardBuilder()
    for p in prods:
        mark = "🔹" if p["stock"] > 0 else "⛔"
        kb.row(B(f"{mark} {p['name']} — {money(p['price'])}", f"prod:{p['id']}"))
    kb.row(B(t("back", lang), "products", False))
    title = f"📂 <b>{esc(sec['name'])}</b>" if sec else ""
    await show(c, title + ("" if prods else f"\n\n{t('empty', lang)}"), kb.as_markup())
    await c.answer()


@user.callback_query(F.data.startswith("prod:"))
async def cb_product(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    p = one("SELECT * FROM products WHERE id=?", (int(c.data.split(":")[1]),))
    if not p:
        return await c.answer(t("empty", lang), show_alert=True)
    text = (f"🛍 <b>{esc(p['name'])}</b>\n\n{esc(p['descr'] or '')}\n\n"
            f"💰 {I18N[lang]['price']}: <b>{money(p['price'])}</b>\n"
            f"📦 {I18N[lang]['in_stock']}: <b>{p['stock']}</b>")
    kb = InlineKeyboardBuilder()
    if p["stock"] > 0:
        kb.row(B(t("buy_btn", lang), f"buy:{p['id']}"))
    kb.row(B(t("back", lang), f"sec:{p['section_id']}", False))
    await show(c, text, kb.as_markup())
    await c.answer()


@user.callback_query(F.data.startswith("buy:"))
async def cb_buy(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    p = one("SELECT * FROM products WHERE id=?", (int(c.data.split(":")[1]),))
    u = one("SELECT * FROM users WHERE id=?", (c.from_user.id,))
    if not p or p["stock"] <= 0:
        return await c.answer(t("out_of_stock", lang), show_alert=True)
    text = (f"🛒 <b>{esc(p['name'])}</b>\n\n💰 {money(p['price'])}\n"
            f"💳 {I18N[lang]['balance']}: {money(u['balance'])}\n\n{I18N[lang]['confirm_q']}")
    kb = InlineKeyboardBuilder()
    kb.row(B(t("confirm_btn", lang), f"buyok:{p['id']}"), B(t("cancel_btn", lang), f"prod:{p['id']}", False))
    await show(c, text, kb.as_markup())
    await c.answer()


@user.callback_query(F.data.startswith("buyok:"))
async def cb_buyok(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    p = one("SELECT * FROM products WHERE id=?", (int(c.data.split(":")[1]),))
    u = one("SELECT * FROM users WHERE id=?", (c.from_user.id,))
    if not p or p["stock"] <= 0:
        return await c.answer(t("out_of_stock", lang), show_alert=True)
    if u["balance"] < p["price"]:
        return await c.answer(I18N[lang]["no_funds"], show_alert=True)
    run("UPDATE users SET balance=balance-? WHERE id=?", (p["price"], u["id"]))
    run("UPDATE products SET stock=stock-1 WHERE id=?", (p["id"],))
    run("INSERT INTO orders(user_id,product_id,product_name,price,date) VALUES(?,?,?,?,?)",
        (u["id"], p["id"], p["name"], p["price"], now()))
    kb = InlineKeyboardBuilder()
    kb.row(B(t("back", lang), "menu", False))
    await show(c, f"{I18N[lang]['bought']}\n\n🛍 {esc(p['name'])} — {money(p['price'])}", kb.as_markup())
    await c.message.answer(f"🎁 <b>{I18N[lang]['your_item']}:</b>\n\n<code>{esc(p['content'] or '')}</code>")
    await c.answer()


# ---- отзывы / язык ----
@user.callback_query(F.data == "reviews")
async def cb_reviews(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    rows = many("SELECT * FROM reviews ORDER BY id DESC LIMIT 8")
    body = "\n\n".join(f"⭐️ <b>{esc(r['author'])}</b> · {r['date'][:10]}\n{esc(r['text'])}" for r in rows)
    await show(c, f"{t('reviews', lang)}\n\n{body or t('no_reviews', lang)}", nav(lang))
    await c.answer()


@user.callback_query(F.data == "lang")
async def cb_lang(c: CallbackQuery):
    lang = lang_of(c.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.row(B("🇷🇺 Русский", "setlang:ru"), B("🇬🇧 English", "setlang:en"))
    kb.row(B(t("back", lang), "menu", False))
    await show(c, t("lang", lang), kb.as_markup())
    await c.answer()


@user.callback_query(F.data.startswith("setlang:"))
async def cb_setlang(c: CallbackQuery):
    lg = c.data.split(":")[1]
    if lg not in I18N:
        return await c.answer()
    run("UPDATE users SET lang=? WHERE id=?", (lg, c.from_user.id))
    cap, kb = menu_view(c.from_user.id)
    await show(c, cap, kb)
    await c.answer(I18N[lg]["lang_set"])


# ======================= АДМИН-ПАНЕЛЬ =======================
def back_panel():
    kb = InlineKeyboardBuilder()
    kb.row(B("🛠 В панель", "adm", False))
    return kb.as_markup()


def cancel_kb():
    kb = InlineKeyboardBuilder()
    kb.row(B("✖️ Отмена", "adm", False))
    return kb.as_markup()


@admin.callback_query(F.data == "adm")
async def cb_adm(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(c, PANEL_TEXT, panel_kb())
    await c.answer()


async def pick_product(c: CallbackQuery, prefix, title):
    rows = many("SELECT p.id, p.name, p.price, p.stock, s.name sn FROM products p "
                "LEFT JOIN sections s ON s.id=p.section_id ORDER BY s.name, p.name")
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.row(B(f"{r['sn']} › {r['name']} • {money(r['price'])} • {r['stock']} шт", f"{prefix}:{r['id']}"))
    kb.row(B("⬅️ Панель", "adm", False))
    await show(c, title if rows else "Товаров пока нет.", kb.as_markup())
    await c.answer()


# 1) изменить цену
@admin.callback_query(F.data == "ad_price")
async def ad_price(c: CallbackQuery):
    await pick_product(c, "pp", "💵 Выберите товар для изменения цены:")


@admin.callback_query(F.data.startswith("pp:"))
async def pp_pick(c: CallbackQuery, state: FSMContext):
    pid = int(c.data.split(":")[1])
    p = one("SELECT * FROM products WHERE id=?", (pid,))
    await state.set_state(AdminSt.new_price)
    await state.update_data(pid=pid)
    await show(c, f"💵 <b>{esc(p['name'])}</b>\nТекущая цена: {money(p['price'])}\n\nВведите новую цену в $:", cancel_kb())
    await c.answer()


@admin.message(AdminSt.new_price, F.text)
async def price_set(m: Message, state: FSMContext):
    v = num(m.text)
    if v is None or v < 0:
        return await m.answer("❗ Введите число")
    d = await state.get_data()
    run("UPDATE products SET price=? WHERE id=?", (v, d["pid"]))
    await state.clear()
    await m.answer(f"✅ Цена обновлена: {money(v)}", reply_markup=back_panel())


# 8) изменить остаток
@admin.callback_query(F.data == "ad_stock")
async def ad_stock(c: CallbackQuery):
    await pick_product(c, "ps", "📦 Выберите товар для изменения остатка:")


@admin.callback_query(F.data.startswith("ps:"))
async def ps_pick(c: CallbackQuery, state: FSMContext):
    pid = int(c.data.split(":")[1])
    p = one("SELECT * FROM products WHERE id=?", (pid,))
    await state.set_state(AdminSt.new_stock)
    await state.update_data(pid=pid)
    await show(c, f"📦 <b>{esc(p['name'])}</b>\nТекущий остаток: {p['stock']}\n\nВведите новый остаток:", cancel_kb())
    await c.answer()


@admin.message(AdminSt.new_stock, F.text)
async def stock_set(m: Message, state: FSMContext):
    v = num(m.text)
    if v is None or v < 0:
        return await m.answer("❗ Введите целое число ≥ 0")
    d = await state.get_data()
    run("UPDATE products SET stock=? WHERE id=?", (int(v), d["pid"]))
    await state.clear()
    await m.answer(f"✅ Остаток обновлён: {int(v)}", reply_markup=back_panel())


# 9) удалить товар
@admin.callback_query(F.data == "ad_delp")
async def ad_delp(c: CallbackQuery):
    await pick_product(c, "pd", "🗑 Выберите товар для удаления:")


@admin.callback_query(F.data.startswith("pd:"))
async def pd_ask(c: CallbackQuery):
    pid = int(c.data.split(":")[1])
    p = one("SELECT * FROM products WHERE id=?", (pid,))
    kb = InlineKeyboardBuilder()
    kb.row(B("🗑 Да, удалить", f"pdy:{pid}"), B("✖️ Нет", "adm", False))
    await show(c, f"Удалить товар <b>{esc(p['name'])}</b>?", kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("pdy:"))
async def pd_do(c: CallbackQuery):
    run("DELETE FROM products WHERE id=?", (int(c.data.split(":")[1]),))
    await show(c, "✅ Товар удалён", back_panel())
    await c.answer()


# удалить раздел (вместе с его товарами)
@admin.callback_query(F.data == "ad_dels")
async def ad_dels(c: CallbackQuery):
    secs = many("SELECT s.id, s.name, (SELECT COUNT(*) FROM products p WHERE p.section_id=s.id) n FROM sections s")
    kb = InlineKeyboardBuilder()
    for s in secs:
        kb.row(B(f"🗂 {s['name']} ({s['n']})", f"sd:{s['id']}"))
    kb.row(B("⬅️ Панель", "adm", False))
    await show(c, "🗂 Выберите раздел для удаления:" if secs else "Разделов пока нет.", kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("sd:"))
async def sd_ask(c: CallbackQuery):
    sid = int(c.data.split(":")[1])
    s = one("SELECT * FROM sections WHERE id=?", (sid,))
    if not s:
        return await c.answer("Раздел не найден", show_alert=True)
    n = one("SELECT COUNT(*) n FROM products WHERE section_id=?", (sid,))["n"]
    kb = InlineKeyboardBuilder()
    kb.row(B("🗑 Да, удалить", f"sdy:{sid}"), B("✖️ Нет", "adm", False))
    await show(c, f"Удалить раздел <b>{esc(s['name'])}</b>?\n\n⚠️ Вместе с ним удалятся все товары в нём: {n} шт.",
               kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("sdy:"))
async def sd_do(c: CallbackQuery):
    sid = int(c.data.split(":")[1])
    run("DELETE FROM products WHERE section_id=?", (sid,))
    run("DELETE FROM sections WHERE id=?", (sid,))
    await show(c, "✅ Раздел удалён", back_panel())
    await c.answer()


# 3) добавить раздел
@admin.callback_query(F.data == "ad_adds")
async def ad_adds(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.section_name)
    await show(c, "📂 Введите название нового раздела:", cancel_kb())
    await c.answer()


@admin.message(AdminSt.section_name, F.text)
async def section_add(m: Message, state: FSMContext):
    run("INSERT INTO sections(name) VALUES(?)", (m.text.strip(),))
    await state.clear()
    await m.answer(f"✅ Раздел «{esc(m.text.strip())}» добавлен", reply_markup=back_panel())


# 2) добавить товар
@admin.callback_query(F.data == "ad_addp")
async def ad_addp(c: CallbackQuery):
    secs = many("SELECT * FROM sections")
    kb = InlineKeyboardBuilder()
    for s in secs:
        kb.row(B(f"📂 {s['name']}", f"apsec:{s['id']}"))
    kb.row(B("⬅️ Панель", "adm", False))
    await show(c, "➕ Выберите раздел для нового товара:" if secs else "Сначала добавьте раздел.", kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("apsec:"))
async def apsec(c: CallbackQuery, state: FSMContext):
    await state.update_data(p_sec=int(c.data.split(":")[1]))
    await state.set_state(AdminSt.p_name)
    await show(c, "Введите <b>название</b> товара:", cancel_kb())
    await c.answer()


@admin.message(AdminSt.p_name, F.text)
async def p_name(m: Message, state: FSMContext):
    await state.update_data(p_name=m.text.strip())
    await state.set_state(AdminSt.p_descr)
    await m.answer("Введите <b>описание</b> товара:", reply_markup=cancel_kb())


@admin.message(AdminSt.p_descr, F.text)
async def p_descr(m: Message, state: FSMContext):
    await state.update_data(p_descr=m.text.strip())
    await state.set_state(AdminSt.p_price)
    await m.answer("Введите <b>цену</b> в $:", reply_markup=cancel_kb())


@admin.message(AdminSt.p_price, F.text)
async def p_price(m: Message, state: FSMContext):
    v = num(m.text)
    if v is None or v < 0:
        return await m.answer("❗ Введите число")
    await state.update_data(p_price=v)
    await state.set_state(AdminSt.p_stock)
    await m.answer("Введите <b>остаток</b> (кол-во штук):", reply_markup=cancel_kb())


@admin.message(AdminSt.p_stock, F.text)
async def p_stock(m: Message, state: FSMContext):
    v = num(m.text)
    if v is None or v < 0:
        return await m.answer("❗ Введите целое число")
    await state.update_data(p_stock=int(v))
    await state.set_state(AdminSt.p_content)
    await m.answer("Что получит покупатель после оплаты? (ключ, ссылка, текст):", reply_markup=cancel_kb())


@admin.message(AdminSt.p_content, F.text)
async def p_content(m: Message, state: FSMContext):
    d = await state.get_data()
    run("INSERT INTO products(section_id,name,descr,price,stock,content) VALUES(?,?,?,?,?,?)",
        (d["p_sec"], d["p_name"], d["p_descr"], d["p_price"], d["p_stock"], m.text))
    await state.clear()
    await m.answer(f"✅ Товар «{esc(d['p_name'])}» добавлен", reply_markup=back_panel())


# 4) объявления (рассылка)
@admin.callback_query(F.data == "ad_ann")
async def ad_ann(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.ann)
    await show(c, "📢 Отправьте сообщение для рассылки (текст, фото, видео — что угодно):", cancel_kb())
    await c.answer()


@admin.message(AdminSt.ann)
async def ann_got(m: Message, state: FSMContext):
    await state.update_data(chat=m.chat.id, mid=m.message_id)
    await state.set_state(None)
    n = one("SELECT COUNT(*) n FROM users WHERE banned=0")["n"]
    kb = InlineKeyboardBuilder()
    kb.row(B("📤 Отправить", "annok"), B("✖️ Отмена", "adm", False))
    await m.reply(f"Разослать это сообщение {n} пользователям?", reply_markup=kb.as_markup())


@admin.callback_query(F.data == "annok")
async def ann_send(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if "mid" not in d:
        return await c.answer("Нет сообщения", show_alert=True)
    await state.clear()
    await show(c, "⏳ Рассылка идёт…", None)
    ok = fail = 0
    for r in many("SELECT id FROM users WHERE banned=0"):
        try:
            await c.bot.copy_message(r["id"], d["chat"], d["mid"])
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await show(c, f"✅ Рассылка завершена\nДоставлено: {ok}\nНе доставлено: {fail}", back_panel())


# 5) добавить отзыв
@admin.callback_query(F.data == "ad_addrev")
async def ad_addrev(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.rev_author)
    await show(c, "⭐ Введите имя автора отзыва:", cancel_kb())
    await c.answer()


@admin.message(AdminSt.rev_author, F.text)
async def rev_author(m: Message, state: FSMContext):
    await state.update_data(author=m.text.strip())
    await state.set_state(AdminSt.rev_text)
    await m.answer("Введите текст отзыва:", reply_markup=cancel_kb())


@admin.message(AdminSt.rev_text, F.text)
async def rev_text(m: Message, state: FSMContext):
    d = await state.get_data()
    run("INSERT INTO reviews(author,text,date) VALUES(?,?,?)", (d["author"], m.text, now()))
    await state.clear()
    await m.answer("✅ Отзыв добавлен", reply_markup=back_panel())


# 12) удалить отзыв
@admin.callback_query(F.data == "ad_delrev")
async def ad_delrev(c: CallbackQuery):
    rows = many("SELECT * FROM reviews ORDER BY id DESC LIMIT 30")
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.row(B(f"🗑 {r['author']}: {r['text'][:25]}", f"rd:{r['id']}"))
    kb.row(B("⬅️ Панель", "adm", False))
    await show(c, "🚫 Нажмите на отзыв, чтобы удалить:" if rows else "Отзывов нет.", kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("rd:"))
async def rd_do(c: CallbackQuery):
    run("DELETE FROM reviews WHERE id=?", (int(c.data.split(":")[1]),))
    await c.answer("Удалено")
    await ad_delrev(c)


# 6) пользователь
def user_card(uid):
    u = one("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        return None, None
    o = one("SELECT COUNT(*) n, COALESCE(SUM(price),0) s FROM orders WHERE user_id=?", (uid,))
    uname = f"@{u['username']}" if u["username"] else "—"
    text = (f"👤 <b>{esc(u['name'])}</b> {uname}\n🆔 <code>{u['id']}</code>\n"
            f"💰 Баланс: <b>{money(u['balance'])}</b>\n🛒 Покупок: {o['n']} на {money(o['s'])}\n"
            f"📅 Регистрация: {u['reg_date']}\n🚦 Статус: {'🚫 забанен' if u['banned'] else '✅ активен'}")
    kb = InlineKeyboardBuilder()
    kb.row(B("➕ Баланс", f"ub:{uid}:add"), B("➖ Баланс", f"ub:{uid}:sub"))
    kb.row(B("✅ Разбанить" if u["banned"] else "🚫 Забанить", f"ub:{uid}:ban"))
    kb.row(B("⬅️ Панель", "adm", False))
    return text, kb.as_markup()


@admin.callback_query(F.data == "ad_user")
async def ad_user(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.user_q)
    await show(c, "👤 Введите ID или @username пользователя:", cancel_kb())
    await c.answer()


@admin.message(AdminSt.user_q, F.text)
async def user_find(m: Message, state: FSMContext):
    q = m.text.strip().lstrip("@")
    u = one("SELECT id FROM users WHERE id=?", (int(q),)) if q.isdigit() else \
        one("SELECT id FROM users WHERE lower(username)=?", (q.lower(),))
    if not u:
        return await m.answer("❗ Не найден. Попробуйте ещё раз:", reply_markup=cancel_kb())
    await state.clear()
    text, kb = user_card(u["id"])
    await m.answer(text, reply_markup=kb)


@admin.callback_query(F.data.startswith("ub:"))
async def user_action(c: CallbackQuery, state: FSMContext):
    _, uid, act = c.data.split(":")
    uid = int(uid)
    if act == "ban":
        run("UPDATE users SET banned=1-banned WHERE id=?", (uid,))
        text, kb = user_card(uid)
        await show(c, text, kb)
    else:
        await state.set_state(AdminSt.user_amount)
        await state.update_data(uid=uid, sign=1 if act == "add" else -1)
        await show(c, "Введите сумму:", cancel_kb())
    await c.answer()


@admin.message(AdminSt.user_amount, F.text)
async def user_amount(m: Message, state: FSMContext):
    v = num(m.text)
    if v is None or v <= 0:
        return await m.answer("❗ Введите положительное число")
    d = await state.get_data()
    run("UPDATE users SET balance=balance+? WHERE id=?", (v * d["sign"], d["uid"]))
    await state.clear()
    text, kb = user_card(d["uid"])
    await m.answer("✅ Баланс изменён\n\n" + text, reply_markup=kb)


# 7) бэкап
def make_backup():
    path = os.path.join(tempfile.gettempdir(), f"shop_backup_{datetime.now():%Y%m%d_%H%M}.db")
    dst = sqlite3.connect(path)
    db.backup(dst)
    dst.close()
    return path


async def send_backup(bot: Bot, chat_id, caption):
    path = make_backup()
    try:
        await bot.send_document(chat_id, FSInputFile(path), caption=caption)
    finally:
        os.remove(path)


@admin.callback_query(F.data == "ad_backup")
async def ad_backup(c: CallbackQuery):
    await send_backup(c.bot, c.message.chat.id, f"💾 Бэкап базы • {now()}")
    await c.answer("Готово")


async def auto_backup(bot: Bot):
    while True:
        await asyncio.sleep(AUTO_BACKUP_HOURS * 3600)
        for a in ADMIN_IDS:
            try:
                await send_backup(bot, a, f"💾 Автобэкап • {now()}")
            except Exception as e:
                logging.warning("auto backup failed: %s", e)


# 10) цвета кнопок
@admin.callback_query(F.data == "ad_color")
async def ad_color(c: CallbackQuery):
    cur = get_setting("btn_style", "primary")
    kb = InlineKeyboardBuilder()
    for k, v in STYLES.items():
        kb.row(B(("✔ " if k == cur else "") + v, f"col:{k}", False))
    kb.row(B("⬅️ Панель", "adm", False))
    await show(c, "🎨 <b>Цвет кнопок</b> для всех пользователей.\nТекущий: " + STYLES.get(cur, cur), kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("col:"))
async def col_set(c: CallbackQuery):
    set_setting("btn_style", c.data.split(":")[1])
    await ad_color(c)


# 11) статистика
@admin.callback_query(F.data == "ad_stats")
async def ad_stats(c: CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d") + "%"
    users = one("SELECT COUNT(*) n FROM users")["n"]
    new_today = one("SELECT COUNT(*) n FROM users WHERE reg_date LIKE ?", (today,))["n"]
    o = one("SELECT COUNT(*) n, COALESCE(SUM(price),0) s FROM orders")
    ot = one("SELECT COUNT(*) n, COALESCE(SUM(price),0) s FROM orders WHERE date LIKE ?", (today,))
    pr = one("SELECT COUNT(*) n, COALESCE(SUM(stock),0) s FROM products")
    bal = one("SELECT COALESCE(SUM(balance),0) s FROM users")["s"]
    pend = one("SELECT COUNT(*) n FROM topups WHERE status='pending'")["n"]
    tops = one("SELECT COALESCE(SUM(amount),0) s FROM topups WHERE status='approved'")["s"]
    text = (f"📊 <b>Статистика</b>\n\n👥 Пользователей: <b>{users}</b> (сегодня +{new_today})\n"
            f"🛒 Заказов: <b>{o['n']}</b> на {money(o['s'])}\n📅 Сегодня: {ot['n']} на {money(ot['s'])}\n"
            f"🛍 Товаров: <b>{pr['n']}</b> (остаток {pr['s']} шт)\n💰 Баланс пользователей: {money(bal)}\n"
            f"💳 Пополнено всего: {money(tops)}\n⏳ Заявок в ожидании: <b>{pend}</b>")
    await show(c, text, back_panel())
    await c.answer()


# 13) заявки на пополнение
@admin.callback_query(F.data == "ad_topups")
async def ad_topups(c: CallbackQuery):
    rows = many("SELECT t.*, u.name FROM topups t JOIN users u ON u.id=t.user_id "
                "WHERE t.status='sent' OR (t.status='pending' AND t.invoice_id IS NOT NULL) "
                "ORDER BY t.id DESC LIMIT 30")
    kb = InlineKeyboardBuilder()
    for r in rows:
        kb.row(B(f"#{r['id']} • {r['name']} • {money(r['amount'])}", f"tpv:{r['id']}"))
    kb.row(B("⬅️ Панель", "adm", False))
    await show(c, "💳 <b>Заявки на пополнение</b> (неоплаченные счета)" + ("" if rows else "\n\nОжидающих заявок нет."), kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("tpv:"))
async def tp_view(c: CallbackQuery):
    try:
        await c.message.delete()
    except TelegramBadRequest:
        pass
    await send_topup_card(c.bot, c.message.chat.id, int(c.data.split(":")[1]))
    await c.answer()


@admin.callback_query(F.data.startswith("tpok:") | F.data.startswith("tprej:"))
async def tp_decide(c: CallbackQuery):
    act, tid = c.data.split(":")
    tid = int(tid)
    tp = one("SELECT * FROM topups WHERE id=?", (tid,))
    if not tp or tp["status"] not in ("pending", "sent"):
        return await c.answer("Уже обработана", show_alert=True)
    lang = lang_of(tp["user_id"])
    if act == "tpok":
        run("UPDATE topups SET status='approved' WHERE id=?", (tid,))
        run("UPDATE users SET balance=balance+? WHERE id=?", (tp["amount"], tp["user_id"]))
        msg, res = I18N[lang]["topup_ok"], f"✅ Заявка #{tid} одобрена"
    else:
        run("UPDATE topups SET status='rejected' WHERE id=?", (tid,))
        msg, res = I18N[lang]["topup_no"], f"❌ Заявка #{tid} отклонена"
    try:
        await c.bot.send_message(tp["user_id"], msg.format(amount=money(tp["amount"])))
    except Exception:
        pass
    kb = InlineKeyboardBuilder()
    kb.row(B("⬅️ К заявкам", "ad_topups", False))
    await show(c, res, kb.as_markup())
    await c.answer()


# 14) описание любой кнопки
@admin.callback_query(F.data == "ad_texts")
async def ad_texts(c: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for k, name in EDITABLE.items():
        kb.row(B(name, f"et:{k}"))
    kb.row(B("⬅️ Панель", "adm", False))
    await show(c, "✏️ Выберите кнопку/раздел, текст которого нужно изменить:", kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("et:"))
async def et_lang(c: CallbackQuery):
    key = c.data.split(":")[1]
    kb = InlineKeyboardBuilder()
    kb.row(B("🇷🇺 Русский", f"etl:{key}:ru"), B("🇬🇧 English", f"etl:{key}:en"))
    kb.row(B("⬅️ Назад", "ad_texts", False))
    await show(c, f"{EDITABLE[key]}\nВыберите язык:", kb.as_markup())
    await c.answer()


@admin.callback_query(F.data.startswith("etl:"))
async def et_edit(c: CallbackQuery, state: FSMContext):
    _, key, lg = c.data.split(":")
    await state.set_state(AdminSt.text_edit)
    await state.update_data(key=key, lg=lg)
    kb = InlineKeyboardBuilder()
    kb.row(B("♻️ Сбросить к стандартному", f"etr:{key}:{lg}", False))
    kb.row(B("✖️ Отмена", "adm", False))
    await show(c, f"{EDITABLE[key]} [{lg}]\n\nТекущий текст:\n<pre>{esc(t(key, lg))}</pre>\n\n"
                  f"Отправьте новый текст (HTML-разметка допустима; в приветствии: {{name}}, {{shop}}):", kb.as_markup())
    await c.answer()


@admin.message(AdminSt.text_edit, F.text)
async def et_save(m: Message, state: FSMContext):
    d = await state.get_data()
    run("INSERT INTO texts(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (f"{d['key']}:{d['lg']}", m.html_text))
    await state.clear()
    await m.answer("✅ Текст обновлён", reply_markup=back_panel())


@admin.callback_query(F.data.startswith("etr:"))
async def et_reset(c: CallbackQuery, state: FSMContext):
    _, key, lg = c.data.split(":")
    run("DELETE FROM texts WHERE key=?", (f"{key}:{lg}",))
    await state.clear()
    await show(c, "♻️ Сброшено к стандартному тексту", back_panel())
    await c.answer()


# --- доп. функции ---
@admin.callback_query(F.data == "ad_orders")
async def ad_orders(c: CallbackQuery):
    rows = many("SELECT o.*, u.name FROM orders o LEFT JOIN users u ON u.id=o.user_id ORDER BY o.id DESC LIMIT 15")
    text = "🧾 <b>Последние заказы</b>\n\n" + ("\n".join(
        f"#{r['id']} • {esc(r['name'] or '?')} • {esc(r['product_name'])} • {money(r['price'])} • {r['date']}"
        for r in rows) or "Заказов пока нет.")
    await show(c, text, back_panel())
    await c.answer()


@admin.callback_query(F.data == "ad_photo")
async def ad_photo(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSt.photo)
    await show(c, "🖼 Отправьте фото для приветственного сообщения:", cancel_kb())
    await c.answer()


@admin.message(AdminSt.photo, F.photo)
async def photo_set(m: Message, state: FSMContext):
    set_setting("start_photo", m.photo[-1].file_id)
    await state.clear()
    await m.answer("✅ Фото приветствия обновлено. Проверьте: /start", reply_markup=back_panel())


@admin.callback_query(F.data == "ad_maint")
async def ad_maint(c: CallbackQuery):
    set_setting("maintenance", "0" if get_setting("maintenance") == "1" else "1")
    await show(c, PANEL_TEXT, panel_kb())
    await c.answer("Режим техработ переключён")


# ======================= ЗАПУСК =======================
async def main():
    logging.basicConfig(level=logging.INFO)
    make_banner()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.outer_middleware(Guard())
    dp.callback_query.outer_middleware(Guard())
    dp.include_routers(base, admin, user)
    backup_task = asyncio.create_task(auto_backup(bot))  # noqa: F841
    watcher_task = asyncio.create_task(topup_watcher(bot))  # noqa: F841
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
