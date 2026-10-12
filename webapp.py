"""
SHOP WEB APP  •  FastAPI + Telegram Mini App
Запуск:  uvicorn webapp:app --host 0.0.0.0 --port 8080
Перед запуском задай BOT_TOKEN (тот же, что у бота) и WEBAPP_URL.
"""
import hashlib
import hmac
import json
import os
import sqlite3
import time
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ======================= НАСТРОЙКИ =======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8851216228:AAFyUm-arqv2I7oKaVqBvRd0ZJGnOOTpz8I")
SHOP_NAME = os.getenv("SHOP_NAME", "Sm Hosting")
CURRENCY = "$"
DB_PATH = os.getenv("DB_PATH", "shop.db")
SUPPORT = "@VladkaSmyrfanka"
MIN_TOPUP = 1.0

app = FastAPI(title=f"{SHOP_NAME} WebApp")
app.mount("/static", StaticFiles(directory="static"), name="static")

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row


def one(sql, a=()):
    return db.execute(sql, a).fetchone()


def many(sql, a=()):
    return db.execute(sql, a).fetchall()


def run(sql, a=()):
    cur = db.execute(sql, a)
    db.commit()
    return cur.lastrowid


def money(x):
    s = f"{float(x):.2f}"
    return CURRENCY + (s[:-3] if s.endswith(".00") else s)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ======================= TELEGRAM AUTH =======================
def validate_init_data(init_data: str, max_age: int = 86400) -> dict:
    """Проверка подписи Telegram WebApp initData. Возвращает parsed data или raises."""
    if not init_data:
        raise HTTPException(401, "Missing initData")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "No hash")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Invalid signature")

    auth_date = int(parsed.get("auth_date", 0))
    if time.time() - auth_date > max_age:
        raise HTTPException(401, "initData expired")

    user = json.loads(parsed.get("user", "{}"))
    if not user.get("id"):
        raise HTTPException(401, "No user")
    return {"user": user, "raw": parsed}


def get_user_from_header(authorization: Optional[str] = Header(None)) -> dict:
    # Demo mode without Telegram header → user id=1 (local preview)
    if not authorization or not authorization.startswith("tma "):
        row = one("SELECT * FROM users WHERE id=?", (1,))
        if not row:
            run(
                "INSERT INTO users(id,username,name,lang,balance,reg_date) VALUES(?,?,?,?,?,?)",
                (1, "demo", "Demo User", "ru", 25.0, now()),
            )
            row = one("SELECT * FROM users WHERE id=?", (1,))
        return dict(row)
    init_data = authorization[4:]
    data = validate_init_data(init_data)
    uid = data["user"]["id"]
    # ensure registered
    if not one("SELECT 1 FROM users WHERE id=?", (uid,)):
        lg = "ru" if (data["user"].get("language_code") or "ru").startswith(("ru", "uk", "be", "kk")) else "en"
        name = data["user"].get("first_name", "") or ""
        if data["user"].get("last_name"):
            name += " " + data["user"]["last_name"]
        run(
            "INSERT INTO users(id,username,name,lang,reg_date) VALUES(?,?,?,?,?)",
            (uid, data["user"].get("username"), name.strip(), lg, now()),
        )
    else:
        name = data["user"].get("first_name", "") or ""
        if data["user"].get("last_name"):
            name += " " + data["user"]["last_name"]
        run(
            "UPDATE users SET username=?, name=? WHERE id=?",
            (data["user"].get("username"), name.strip(), uid),
        )
    row = one("SELECT * FROM users WHERE id=?", (uid,))
    if row and row["banned"]:
        raise HTTPException(403, "Banned")
    return dict(row)


# ======================= API =======================
@app.get("/", response_class=HTMLResponse)
async def index():
    path = os.path.join("templates", "index.html")
    with open(path, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/me")
async def api_me(authorization: Optional[str] = Header(None)):
    u = get_user_from_header(authorization)
    n = one("SELECT COUNT(*) n FROM orders WHERE user_id=?", (u["id"],))["n"]
    return {
        "id": u["id"],
        "name": u["name"],
        "username": u["username"],
        "balance": float(u["balance"]),
        "balance_fmt": money(u["balance"]),
        "orders_count": n,
        "reg_date": (u["reg_date"] or "")[:10],
        "lang": u["lang"],
        "shop_name": SHOP_NAME,
        "support": SUPPORT,
        "currency": CURRENCY,
    }


@app.get("/api/sections")
async def api_sections(authorization: Optional[str] = Header(None)):
    get_user_from_header(authorization)
    rows = many(
        "SELECT s.id, s.name, "
        "(SELECT COUNT(*) FROM products p WHERE p.section_id=s.id AND p.stock>0) n "
        "FROM sections s ORDER BY s.name"
    )
    return [{"id": r["id"], "name": r["name"], "count": r["n"]} for r in rows]


@app.get("/api/products")
async def api_products(section_id: Optional[int] = None, authorization: Optional[str] = Header(None)):
    get_user_from_header(authorization)
    if section_id:
        rows = many("SELECT * FROM products WHERE section_id=? ORDER BY name", (section_id,))
    else:
        rows = many("SELECT * FROM products ORDER BY name")
    return [
        {
            "id": r["id"],
            "section_id": r["section_id"],
            "name": r["name"],
            "descr": r["descr"] or "",
            "price": float(r["price"]),
            "price_fmt": money(r["price"]),
            "stock": r["stock"],
            "in_stock": r["stock"] > 0,
        }
        for r in rows
    ]


@app.get("/api/product/{pid}")
async def api_product(pid: int, authorization: Optional[str] = Header(None)):
    get_user_from_header(authorization)
    r = one("SELECT * FROM products WHERE id=?", (pid,))
    if not r:
        raise HTTPException(404, "Not found")
    return {
        "id": r["id"],
        "section_id": r["section_id"],
        "name": r["name"],
        "descr": r["descr"] or "",
        "price": float(r["price"]),
        "price_fmt": money(r["price"]),
        "stock": r["stock"],
        "in_stock": r["stock"] > 0,
    }


class BuyBody(BaseModel):
    product_id: int


@app.post("/api/buy")
async def api_buy(body: BuyBody, authorization: Optional[str] = Header(None)):
    u = get_user_from_header(authorization)
    p = one("SELECT * FROM products WHERE id=?", (body.product_id,))
    if not p:
        raise HTTPException(404, "Product not found")
    if p["stock"] <= 0:
        raise HTTPException(400, "Out of stock")
    if u["balance"] < p["price"]:
        raise HTTPException(400, "Insufficient balance")

    run("UPDATE users SET balance=balance-? WHERE id=?", (p["price"], u["id"]))
    run("UPDATE products SET stock=stock-1 WHERE id=?", (p["id"],))
    run(
        "INSERT INTO orders(user_id,product_id,product_name,price,date) VALUES(?,?,?,?,?)",
        (u["id"], p["id"], p["name"], p["price"], now()),
    )
    content = p["content"] or ""
    return {
        "ok": True,
        "product_name": p["name"],
        "price_fmt": money(p["price"]),
        "content": content,
        "new_balance": float(one("SELECT balance FROM users WHERE id=?", (u["id"],))["balance"]),
        "new_balance_fmt": money(one("SELECT balance FROM users WHERE id=?", (u["id"],))["balance"]),
    }


@app.get("/api/orders")
async def api_orders(authorization: Optional[str] = Header(None)):
    u = get_user_from_header(authorization)
    rows = many(
        "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 30", (u["id"],)
    )
    return [
        {
            "id": r["id"],
            "product_name": r["product_name"],
            "price_fmt": money(r["price"]),
            "date": (r["date"] or "")[:16],
        }
        for r in rows
    ]


@app.get("/api/reviews")
async def api_reviews(authorization: Optional[str] = Header(None)):
    get_user_from_header(authorization)
    rows = many("SELECT * FROM reviews ORDER BY id DESC LIMIT 20")
    return [
        {"author": r["author"], "text": r["text"], "date": (r["date"] or "")[:10]}
        for r in rows
    ]


@app.get("/api/info")
async def api_info(authorization: Optional[str] = Header(None)):
    get_user_from_header(authorization)
    return {
        "shop_name": SHOP_NAME,
        "support": SUPPORT,
        "rules": (
            "1. Покупая товар, вы соглашаетесь с правилами магазина.\n"
            "2. Цифровые товары возврату не подлежат после выдачи.\n"
            "3. Администрация вправе отказать в обслуживании."
        ),
        "faq": (
            "Как купить?\nПополните баланс в боте и выберите товар в каталоге.\n\n"
            "Как быстро выдаётся товар?\nМоментально после покупки."
        ),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
