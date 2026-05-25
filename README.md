# APIWatchBot

> בוט טלגרם המנטר 10 ספקי API נפוצים ושולח עדכונים מותאמים אישית בעברית.

## מפרט מלא

המפרט הטכני המלא נמצא ב-[`docs/Spec.md`](docs/Spec.md).

## סטטוס

🚧 **בפיתוח — שלב 1 (תשתית בסיס)**

- [x] שלב 1 — תשתית: FastAPI + MongoDB + שלד בוט + webhook
- [ ] שלב 2 — Collectors (10 ספקי API)
  - [x] שלב 2a — `BaseSource` + Wave 1 (Render, OpenAI, Twilio) + APScheduler
  - [ ] שלב 2b — Wave 2 (HTML scraping) + Wave 3 (יציבות + retries)
- [ ] שלב 3 — AI Layer (Gemini)
- [ ] שלב 4 — פלואו רישום מלא
- [ ] שלב 5 — Dispatcher (התראות + סיכום שבועי)

## מבנה הפרויקט

```text
APIWatchBot/
├── app/                    # FastAPI app + Telegram webhook
│   ├── bot/                # handlers של הבוט
│   ├── collectors/         # מקורות איסוף + runner + storage
│   │   ├── base.py         # BaseSource + RawItem
│   │   ├── runner.py       # מריץ את כל המקורות במקביל
│   │   ├── storage.py      # שמירה ל-DB עם dedup אטומי
│   │   ├── registry.py     # רישום כל המקורות הפעילים
│   │   └── sources/        # מימוש פר-ספק (render, openai, twilio, ...)
│   ├── db/                 # חיבור MongoDB ואינדקסים
│   ├── models/             # סכמות Pydantic
│   ├── config.py           # טעינת ENV
│   ├── logging_config.py   # structlog
│   └── main.py             # entrypoint
├── worker/                 # background worker (APScheduler)
│   ├── __main__.py
│   └── scheduler.py
├── tests/
│   └── fixtures/           # XML feeds לבדיקות מקורות
├── docs/Spec.md
├── render.yaml             # blueprint לדיפלוי
├── pyproject.toml
└── requirements.txt
```

## הרצה מקומית

```bash
# 1. יצירת virtual env
python -m venv .venv
source .venv/bin/activate

# 2. התקנת תלויות
pip install -r requirements.txt
pip install -e ".[dev]"

# 3. הגדרת משתני סביבה
cp .env.example .env
# ערוך את .env עם הערכים שלך

# 4. הרצת השרת
uvicorn app.main:app --reload

# 5. הרצת הבדיקות
pytest
```

## דיפלוי ל-Render

הקובץ [`render.yaml`](render.yaml) מגדיר שני שירותים:

- **`api-watch-web`** — FastAPI עם ה-webhook של הבוט (Starter plan).
- **`api-watch-worker`** — Collector + Dispatcher (Standard plan).

בעת חיבור הריפו ל-Render, הוא יזהה את ה-blueprint אוטומטית. יש להזין ידנית את כל ה-secrets המסומנים `sync: false` (Bot Token, Mongo URI, Gemini key וכו').

## משתני סביבה

ראה [`.env.example`](.env.example) לרשימה מלאה.

חיוניים לשלב 1:

- `TELEGRAM_BOT_TOKEN` — מה-BotFather
- `TELEGRAM_WEBHOOK_SECRET` — מחרוזת אקראית ארוכה (לאימות webhook)
- `TELEGRAM_WEBHOOK_BASE_URL` — ה-URL הציבורי של ה-Web Service
- `MONGODB_URI` — URI של MongoDB Atlas
- `MONGODB_DB_NAME` — שם המסד (ברירת מחדל: `apiwatch`)

## רישיון

MIT.
