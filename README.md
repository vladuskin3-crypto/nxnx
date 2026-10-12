# Shop Bot + Telegram Mini App

Цифровой магазин на **aiogram 3** + **SQLite** с веб-приложением (Telegram Mini App) на **FastAPI**.

## Что внутри

| Компонент | Файл | Описание |
|-----------|------|----------|
| Бот | `bot.py` | Каталог, баланс, CryptoBot / ручное пополнение, админка, отзывы |
| Web App API | `webapp.py` | REST API + отдача Mini App |
| Frontend | `templates/index.html`, `static/` | UI магазина внутри Telegram |

### Возможности Mini App
- Каталог по разделам
- Карточка товара и покупка с баланса
- Профиль, история покупок
- Отзывы, правила, поддержка
- Тема Telegram (светлая/тёмная)
- Авторизация через `initData` (HMAC)

---

## Быстрый старт

### 1. Зависимости

```bash
pip install -r requirements.txt
```

### 2. Настройки

Одинаковый `BOT_TOKEN` для бота и веб-приложения.

```bash
export BOT_TOKEN="123456:ABC..."
export ADMIN_IDS="8759747461"
export CRYPTO_TOKEN=""          # опционально, Crypto Pay
export WEBAPP_URL="https://your-domain.com"   # HTTPS URL Mini App
export DB_PATH="shop.db"
```

Или правь значения прямо в `bot.py` / `webapp.py`.

### 3. Запуск бота

```bash
python bot.py
```

### 4. Запуск Web App

В **той же папке** (общая `shop.db`):

```bash
uvicorn webapp:app --host 0.0.0.0 --port 8080
```

Для локальной разработки с HTTPS используй [ngrok](https://ngrok.com):

```bash
ngrok http 8080
# Скопируй https://xxxx.ngrok-free.app → WEBAPP_URL
```

### 5. Подключение Mini App в Telegram

1. Открой [@BotFather](https://t.me/BotFather)
2. `/mybots` → выбери бота → **Bot Settings** → **Menu Button**  
   или **Configure Mini App** / **Edit Web App URL**
3. Укажи `WEBAPP_URL` (должен быть HTTPS)
4. В меню бота появится кнопка «🌐 Открыть магазин» (если `WEBAPP_URL` задан)

---

## Структура

```
shop_webapp/
├── bot.py              # Telegram-бот
├── webapp.py           # FastAPI + Mini App backend
├── requirements.txt
├── shop.db             # создаётся автоматически
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── app.js
```

---

## API (для разработки)

Все запросы (кроме `/`) требуют заголовок:

```
Authorization: tma <Telegram.WebApp.initData>
```

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/me` | Профиль + баланс |
| GET | `/api/sections` | Разделы |
| GET | `/api/products?section_id=` | Товары |
| GET | `/api/product/{id}` | Один товар |
| POST | `/api/buy` | `{ "product_id": 1 }` — покупка |
| GET | `/api/orders` | История |
| GET | `/api/reviews` | Отзывы |
| GET | `/api/info` | Правила / FAQ |

---

## Важно

- **Бот и webapp должны видеть одну и ту же `shop.db`.**
- Mini App **обязан** работать по HTTPS (Telegram не откроет http).
- Пополнение баланса — через бота (CryptoBot / ручная заявка). В веб-приложении только трата баланса.
- Токен бота в коде — только для теста. В проде используй переменные окружения.

---

## Деплой (кратко)

1. VPS / Railway / Render / Fly.io
2. Запусти `bot.py` (polling) и `uvicorn webapp:app`
3. Проксируй HTTPS на порт webapp (Caddy / nginx / Cloudflare Tunnel)
4. Пропиши URL в BotFather и в `WEBAPP_URL`
