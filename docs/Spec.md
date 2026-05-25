# מפרט טכני — @APIWatchBot

> בוט טלגרם המנטר 10 ספקי API ושולח עדכונים מותאמים אישית למפתחים ובעלי עסקים בישראל.

---

## 1. סקירה כללית

### 1.1 מטרה
מערכת שמנטרת באופן אוטומטי את ה-changelogs של 10 ספקי API נפוצים, מסכמת כל שינוי בעברית באמצעות AI, ושולחת לכל משתמש בטלגרם רק את העדכונים שמעניינים אותו — בתדירות שהוא בחר.

### 1.2 קהל יעד
מפתחים, בעלי עסקים וסוכנויות בישראל שמשתמשים ב-APIs האלה ומפסידים שעות בקריאת changelogs באנגלית.

### 1.3 הצעת ערך
- **סינון** — רק העדכונים הרלוונטיים לך.
- **עברית** — סיכום קצר וברור בעברית.
- **התראות חכמות** — סיכום שבועי קבוע + התראה מיידית רק כשבאמת דחוף.

### 1.4 הגדרות מערכת
| פרמטר | ערך |
|---|---|
| שם הבוט | `@APIWatchBot` |
| שפה | עברית בלבד |
| מודל AI לסיכומים | `gemini-2.5-flash` |
| תדירות ברירת מחדל | סיכום שבועי (ראשון בבוקר) |
| התראות מיידיות | רק לפריטים שמסווגים כדחופים (`critical` + תאריך תוקף קרוב) |
| כיסוי APIs | 10 ספקים מהיום הראשון |

---

## 2. ה-APIs המנוטרים

הסדר הוא מהקל לקשה ליישום:

| # | API | שיטת איסוף | URL מקור |
|---|---|---|---|
| 1 | Render | RSS/Atom | `https://render.com/changelog/feed.xml` |
| 2 | OpenAI | RSS | `https://developers.openai.com/rss.xml` |
| 3 | Twilio | RSS | `https://www.twilio.com/en-us/changelog.feed.xml` |
| 4 | Telegram Bot API | HTML scraping | `https://core.telegram.org/bots/api-changelog` |
| 5 | Stripe | HTML scraping | `https://docs.stripe.com/changelog` |
| 6 | Google Business Profile | HTML scraping | `https://developers.google.com/my-business/content/change-log` |
| 7 | Google Gemini | HTML scraping | `https://ai.google.dev/gemini-api/docs/changelog` |
| 8 | Anthropic Claude | HTML scraping (SPA) | `https://platform.claude.com/docs/en/release-notes/overview` |
| 9 | WhatsApp Business + Green API | HTML scraping (כפול) | `https://developers.facebook.com/documentation/business-messaging/whatsapp/changelog` + `https://green-api.com/en/docs/release/` |
| 10 | Meta Graph API | HTML scraping (שביר) | `https://developers.facebook.com/docs/graph-api/changelog/` |

---

## 3. ארכיטקטורה

### 3.1 רכיבים עיקריים

```
┌─────────────────────────────────────────────────────────┐
│                    APIWatchBot                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐    ┌──────────────┐   ┌────────────┐  │
│  │  Collector   │───▶│   AI Layer   │──▶│  MongoDB   │  │
│  │  (Cron Jobs) │    │ (Gemini Flash)│   │            │  │
│  └──────────────┘    └──────────────┘   └─────┬──────┘  │
│                                                │          │
│  ┌──────────────┐                              │          │
│  │  Telegram    │◀─────────────────────────────┤          │
│  │  Bot         │                              │          │
│  │              │    ┌──────────────┐          │          │
│  │              │◀───│  Dispatcher  │◀─────────┘          │
│  └──────────────┘    │  (Scheduler) │                     │
│                      └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

### 3.2 תרשים זרימה

1. **Collector** רץ כל 6 שעות, אוסף שינויים מ-10 המקורות, שומר Raw ב-DB.
2. **AI Layer** מעבד פריטים חדשים — מסכם בעברית, מסווג חומרה, מסמן אם דחוף.
3. **Dispatcher** רץ פעם בשעה לבדיקת פריטים דחופים, ופעם בשבוע לסיכום שבועי.
4. **Telegram Bot** מקבל פקודות, מנהל הגדרות משתמש, שולח הודעות.

### 3.3 סטאק טכנולוגי

| רכיב | טכנולוגיה | סיבה |
|---|---|---|
| שפה | Python 3.11+ | מוכר, יש הרבה ספריות רלוונטיות |
| Framework | FastAPI | למסוף ניהול עתידי, מוכר לך |
| בוט טלגרם | `python-telegram-bot` 21+ | סטנדרט תעשייה |
| DB | MongoDB Atlas | מוכר, יש לך כבר |
| RSS Parser | `feedparser` | בדוק וסטנדרט |
| HTML scraping | `httpx` + `selectolax` | מהיר, lightweight |
| SPA scraping | `playwright` | נחוץ רק ל-Anthropic |
| Scheduler | `APScheduler` | משולב טוב עם FastAPI |
| AI | `google-generativeai` SDK | למודל gemini-2.5-flash |
| Hosting | Render Web Service + Worker | מוכר, יציב |

---

## 4. סכמת MongoDB

### 4.1 קולקציה: `users`

```javascript
{
  _id: ObjectId,
  telegram_id: Number,        // ייחודי
  username: String,
  first_name: String,
  language_code: String,
  
  // העדפות
  subscribed_apis: [String],  // ["openai", "stripe", "render", ...]
  min_severity: String,       // "critical" | "important" | "all"
  frequency: String,          // "weekly" (ברירת מחדל)
  receive_urgent_alerts: Boolean,  // ברירת מחדל: true
  
  // מטא
  registered_at: Date,
  last_active_at: Date,
  paused: Boolean,            // ברירת מחדל: false
  
  // מצב שיחה (למצב הרשמה אינטראקטיבי)
  conversation_state: String  // "idle" | "selecting_apis" | "selecting_severity" | ...
}
```

**אינדקסים:**
- `telegram_id` (unique)
- `subscribed_apis` (multikey)
- `paused`

---

### 4.2 קולקציה: `updates`

```javascript
{
  _id: ObjectId,
  api_id: String,             // "openai", "stripe", "render", ...
  
  // תוכן גולמי
  raw_title: String,
  raw_content: String,
  source_url: String,
  source_published_at: Date,  // אם זמין מהמקור
  
  // hash לזיהוי כפילויות
  content_hash: String,       // sha256 של raw_content
  
  // עיבוד AI
  summary_he: String,         // הסיכום בעברית
  severity: String,           // "critical" | "important" | "info"
  is_urgent: Boolean,         // נדרשת פעולה תוך 7 ימים
  categories: [String],       // ["deprecation", "breaking", "new_feature", "pricing", "security"]
  
  // מטא
  collected_at: Date,
  processed_at: Date,
  
  // סטטוס
  status: String              // "raw" | "processed" | "failed" | "skipped_noise"
}
```

**אינדקסים:**
- `content_hash` (unique)
- `api_id + collected_at`
- `is_urgent + processed_at`
- `status`

---

### 4.3 קולקציה: `deliveries`

מעקב אחרי מה נשלח למי — כדי לא לשלוח פעמיים.

```javascript
{
  _id: ObjectId,
  user_id: ObjectId,          // ref to users
  update_id: ObjectId,        // ref to updates
  delivery_type: String,      // "urgent" | "weekly_digest"
  sent_at: Date
}
```

**אינדקסים:**
- `user_id + update_id` (unique compound)
- `sent_at`

---

### 4.4 קולקציה: `system_state`

מצב פנימי של המערכת — אחרון snapshot per source וכו'.

```javascript
{
  _id: ObjectId,
  key: String,                // "last_collect:openai", "last_html:stripe"
  value: Mixed,
  updated_at: Date
}
```

---

## 5. רכיב האיסוף (Collector)

### 5.1 מבנה כללי

כל מקור הוא מחלקה שיורשת מבסיס `BaseSource`:

```python
class BaseSource:
    api_id: str
    name_he: str
    source_url: str
    
    async def fetch(self) -> List[RawItem]: ...
    def deduplicate(self, items: List[RawItem]) -> List[RawItem]: ...
```

הקולקטור מריץ את כל המקורות במקביל ושומר תוצאות ב-`updates` עם `status: "raw"`.

### 5.2 מיפוי שיטות איסוף

#### Wave 1 — Feeds (קל)

**Render** — `feedparser.parse('https://render.com/changelog/feed.xml')`
- שדות: title, summary, link, published

**OpenAI** — `feedparser.parse('https://developers.openai.com/rss.xml')`
- חשוב: סינון לפי URL — רק פריטים שמכילים `/api/docs/changelog`

**Twilio** — `feedparser.parse('https://www.twilio.com/en-us/changelog.feed.xml')`
- שדות סטנדרטיים, ישר לעניין.

#### Wave 2 — HTML סטטי

**Telegram** — `httpx.get` + `selectolax` parser
- כל פריט מתחיל ב-`<h4>` עם תאריך, ואחריו תוכן עד ה-`<h4>` הבא.
- שמירת hash על כל בלוק.

**Stripe** — `httpx.get` + selectolax
- מבנה הטבלה: עמודה עם תאריך, עמודה עם תיאור. parse לפי `<tr>`.

**Google Business Profile** — `httpx.get` + selectolax
- דף קצר יחסית, כל פריט הוא header + פסקה.

**Google Gemini** — `httpx.get` + selectolax
- חשוב: hash על רמת פריט בודד (לפי תאריך) ולא על הדף כולו, כי יש עדכונים תוך-יומיים.

#### Wave 3 — מאתגרים

**Anthropic** — `playwright` (SPA)
- מחכה ל-`networkidle`, מוציא את כל ה-DOM אחרי רינדור.
- חלופה: לעקוב גם אחרי endpoint רשמי `/api/models/list` כסיגנל משלים.

**WhatsApp + Green API** — שני מקורות, אותו `api_id: "whatsapp"`
- WhatsApp: `httpx.get` + retries (Meta לפעמים חוסם).
- Green API: `httpx.get` + selectolax (MkDocs).

**Meta Graph** — `httpx.get` + retries + User-Agent מסווה
- חוסר יציבות גבוה — להוסיף fallback: אם נכשל 3 פעמים ברצף, לשלוח התראה לאדמין.

### 5.3 לוגיקת deduplication

לכל פריט גולמי:
1. חישוב `content_hash = sha256(api_id + raw_title + raw_content)`
2. בדיקה ב-DB: אם קיים — מדלג.
3. אם לא — שמירה עם `status: "raw"`.

### 5.4 תזמון

`APScheduler` עם cron triggers:
- כל המקורות: כל 6 שעות (00:00, 06:00, 12:00, 18:00 שעון ישראל).
- Meta + Anthropic: גם ב-09:00 ו-15:00 (סיכוי טוב יותר שלא חסום).

---

## 6. רכיב ה-AI (AI Layer)

### 6.1 תהליך עיבוד

עבור כל פריט עם `status: "raw"`:

1. שליחת תוכן ל-`gemini-2.5-flash`.
2. קבלת JSON מובנה עם סיכום + סיווג.
3. עדכון רשומה ב-DB עם `status: "processed"` או `"skipped_noise"`.

### 6.2 פרומפט הסיכום

```
אתה עורך תוכן טכני בעברית. אני אתן לך פריט מתוך changelog של ספק API. 
המשימה שלך: לסכם בעברית קצרה ובהירה, ולסווג.

הפריט:
API: {api_name}
כותרת: {raw_title}
תוכן: {raw_content}
URL: {source_url}

החזר JSON בלבד בפורמט הבא:
{
  "is_noise": boolean,        // true אם זה לא משמעותי (תיקון טעות כתיב, עדכון UI קוסמטי)
  "summary_he": string,       // סיכום של 1-3 משפטים בעברית. אם is_noise=true, החזר ""
  "severity": "critical" | "important" | "info",
  "is_urgent": boolean,       // true רק אם נדרשת פעולה תוך 7 ימים (deprecation effective soon, breaking change live, security advisory)
  "categories": [string]      // 1-3 תגיות מתוך: deprecation, breaking, new_feature, pricing, security, bugfix, performance
}

הנחיות לסיווג חומרה:
- critical: deprecation עם תאריך תוקף, breaking change, security issue
- important: תכונה משמעותית חדשה, שינוי תמחור, שינוי authentication
- info: שיפורים, תכונות קטנות, תיקוני באגים

הנחיות לעברית:
- שפה מקצועית אבל לא מסורבלת
- מונחים טכניים באנגלית כשמתאים (endpoint, deprecation, rate limit)
- בלי קלישאות שיווקיות
```

### 6.3 טיפול בכשלים

- אם ה-AI מחזיר JSON לא תקין: ניסיון חוזר אחד, ואז `status: "failed"` עם הודעה לאדמין.
- אם הפריט מסומן `is_noise: true`: סטטוס `"skipped_noise"`, לא נשלח לאף משתמש.

---

## 7. רכיב הבוט (Telegram Bot)

### 7.1 פקודות

| פקודה | פעולה |
|---|---|
| `/start` | רישום ראשוני + תפריט בחירת APIs |
| `/settings` | תפריט הגדרות |
| `/apis` | שינוי רשימת APIs מנויים |
| `/severity` | שינוי רמת חומרה מינימלית |
| `/pause` | השהיית התראות |
| `/resume` | חידוש התראות |
| `/stop` | מחיקת המשתמש מהמערכת |
| `/help` | עזרה |
| `/about` | על הבוט |

### 7.2 פלואו רישום (`/start`)

1. **בדיקה אם המשתמש קיים** — אם כן, ברוך הבא חזרה + תפריט הגדרות.
2. **הודעת פתיחה**: "ברוך הבא ל-APIWatchBot. אעקוב בשבילך אחרי שינויים ב-APIs שמעניינים אותך. בוא נגדיר מה לשלוח לך."
3. **בחירת APIs** — `InlineKeyboardMarkup` עם 10 כפתורים, כל אחד עם ✅ או ⬜. לחיצה מחליפה מצב. כפתור "סיום" בסוף.
4. **בחירת רמת חומרה** — 3 כפתורים: "רק קריטי 🔴" / "חשוב ומעלה 🟡" / "הכל 🟢".
5. **בחירת תדירות** — לעכשיו רק "שבועי" כפעיל. ניתן להוסיף יומי בעתיד.
6. **אישור התראות דחופות** — "מסכים לקבל התראה מיידית כשמשהו דורש פעולה דחופה?" כן/לא.
7. **סיכום ואישור**: "הכל מוכן. נשלח לך את הסיכום הראשון ביום ראשון בבוקר. אם משהו דחוף יקרה לפני זה — נדע."

### 7.3 פורמט הודעת סיכום שבועי

```
📡 סיכום שבועי — APIWatchBot
24-30 במאי 2026

🔴 קריטי
━━━━━━━━━━━━━━━

▪️ OpenAI: דחיית GPT-4-0613
GPT-4-0613 מוסר ב-13 ביוני. אם אתה משתמש בו ישירות, צריך לעבור ל-gpt-4-turbo.
🔗 פרטים: [link]

▪️ Google Gemini: סוף תמיכה ב-Preview
מודלים בגרסת Preview יוצאים מהשירות ב-1 ביולי 2026.
🔗 פרטים: [link]

🟡 חשוב
━━━━━━━━━━━━━━━

▪️ Stripe: webhook חדש לאירועי Subscription
ניתן עכשיו להאזין ל-customer.subscription.trial_will_end 7 ימים מראש.
🔗 פרטים: [link]

🟢 מידע
━━━━━━━━━━━━━━━

▪️ Render: שיפור ביצועי deploy
זמן deploy של Web Services קוצר ב-30% בממוצע.
🔗 פרטים: [link]

━━━━━━━━━━━━━━━
💡 שינוי הגדרות: /settings
```

### 7.4 פורמט הודעת התראה דחופה

```
⚠️ התראה דחופה — Meta Graph API

Facebook Graph API v18.0 יוצא מהשירות ב-1 ביוני 2026 (בעוד 7 ימים).
כל קריאה לגרסה הזו תיכשל מהתאריך הזה.

עליך לעדכן את הקוד שלך לגרסה v19.0 או v20.0.

🔗 מדריך מעבר: [link]
🔗 הכרזה רשמית: [link]
```

---

## 8. רכיב ההפצה (Dispatcher)

### 8.1 התראות מיידיות

**תזמון:** כל שעה.

**לוגיקה:**
1. שליפת כל ה-updates עם `is_urgent: true`, `processed_at` ב-24 שעות אחרונות.
2. עבור כל update — מציאת כל המשתמשים שמנויים ל-`api_id` הזה, עם `receive_urgent_alerts: true`, ולא `paused`.
3. עבור כל user-update pair — בדיקה ב-`deliveries`. אם לא נשלח, שליחה.
4. רישום ב-`deliveries`.

### 8.2 סיכום שבועי

**תזמון:** ראשון 08:00 שעון ישראל.

**לוגיקה:**
1. שליפת כל ה-updates עם `status: "processed"`, `processed_at` ב-7 ימים אחרונים.
2. עבור כל משתמש פעיל (לא paused, `frequency: "weekly"`):
   - סינון לפי `subscribed_apis` + `min_severity`.
   - אם אין כלום — דילוג (לא לשלוח הודעה ריקה).
   - אם יש — בניית הודעה לפי הפורמט בסעיף 7.3.
   - שליחה + רישום ב-`deliveries` (סוג `weekly_digest`).

### 8.3 הגבלות Telegram

- מקסימום 30 הודעות לשנייה — נשמור על קצב של 25 כדי להיות בטוחים.
- אורך מקסימלי של הודעה: 4096 תווים. אם הסיכום ארוך מדי, מפצלים ל-2 הודעות.

---

## 9. פריסה ב-Render

### 9.1 שירותים נדרשים

| שירות | סוג | תכלית |
|---|---|---|
| `api-watch-web` | Web Service | FastAPI — webhook של הבוט + אדמין פאנל עתידי |
| `api-watch-worker` | Background Worker | הקולקטור + ה-Dispatcher (APScheduler) |

### 9.2 משתני סביבה

```
# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...
ADMIN_TELEGRAM_ID=...           # שלך, לקבלת התראות מערכת

# MongoDB
MONGODB_URI=mongodb+srv://...
MONGODB_DB_NAME=apiwatch

# Google AI
GEMINI_API_KEY=...

# General
ENVIRONMENT=production
LOG_LEVEL=INFO
TIMEZONE=Asia/Jerusalem
```

### 9.3 הערות פריסה

- **Web Service:** הכי זול שאפשר (Starter $7/חודש) — לא צריך הרבה משאבים.
- **Worker:** Standard ($25/חודש) — כי playwright דורש זיכרון.
- **חלופה:** לשלב את הכל ב-Web Service אחד אם רוצים לחסוך, אבל פחות נקי.

---

## 10. סדר עבודה מומלץ

### שלב 1 — תשתית בסיס (2-3 ימים)
1. הקמת פרויקט Python, FastAPI skeleton.
2. חיבור MongoDB, יצירת קולקציות ואינדקסים.
3. רישום הבוט בטלגרם, קבלת token, חיבור בסיסי עם `python-telegram-bot`.
4. פקודות `/start` ו-`/help` בלי לוגיקה מלאה — רק הוכחת חיים.
5. דיפלוי ראשוני ל-Render.

### שלב 2 — Collectors (3-4 ימים)
1. `BaseSource` + מימוש Wave 1 (Render, OpenAI, Twilio) — feeds.
2. בדיקה שהפריטים נכנסים ל-DB עם `status: "raw"`.
3. מימוש Wave 2 (Telegram, Stripe, GBP, Gemini) — HTML scraping.
4. מימוש Wave 3 (Anthropic, WhatsApp+Green, Meta) — כולל retries.
5. תזמון עם APScheduler.

### שלב 3 — AI Layer (1-2 ימים)
1. אינטגרציה עם Gemini SDK.
2. מימוש הפרומפט, וידוא JSON תקין חוזר.
3. עיבוד כל הפריטים שב-`status: "raw"`.
4. בדיקה ידנית של 20-30 סיכומים — האם איכותם מספקת?

### שלב 4 — Bot Flow מלא (3-4 ימים)
1. מימוש פלואו הרישום המלא עם InlineKeyboard.
2. שמירת `conversation_state` וניהול מצבים.
3. פקודות הניהול: `/settings`, `/apis`, `/severity`, `/pause`, `/resume`, `/stop`.

### שלב 5 — Dispatcher (2 ימים)
1. לוגיקת התראות מיידיות.
2. לוגיקת סיכום שבועי.
3. בדיקה end-to-end עם משתמש בודק (אתה).

### שלב 6 — Beta + שיווק (שבוע)
1. הזמנת 5-10 חברים מהקהילה לבטא.
2. איסוף משוב, תיקונים.
3. הכרזה בערוץ `@AndroidAndAI`.

### זמן כולל מוערך
**3-4 שבועות עבודה במקביל לעיסוקים אחרים.**

---

## 11. אופציות עתידיות (לא ל-MVP)

- **תדירות יומית** למשתמשים שרוצים יותר.
- **הוספת APIs** לפי בקשות מהקהילה (Vercel, GitHub, AWS, Cloudflare).
- **אדמין פאנל מלא** ב-FastAPI לראות סטטיסטיקות, פריטים שנכשלו, וכו'.
- **גרסה בתשלום (Pro)** — התראות בזמן אמת לוואטסאפ, התאמה אישית של פורמט, וובהוקים ל-Slack.
- **MCP Server** שמאפשר ל-Claude לקרוא את הנתונים האלה ישירות.
- **הוספת בעלי עסקים** שלא רק מפתחים — סיכומי "מה זה אומר עליי" בעברית פשוטה.

---

## 12. סיכונים וטיפול

| סיכון | סבירות | השפעה | טיפול |
|---|---|---|---|
| Meta חוסם scraping | בינונית | בינונית | retries + User-Agent + fallback |
| Gemini משנה תמחור/תנאים | נמוכה | בינונית | abstraction layer — קל להחליף ל-Claude Haiku |
| Telegram מגביל הבוט | נמוכה | גבוהה | להקפיד על rate limit |
| המודל מסכם לא טוב בעברית | בינונית | גבוהה | בדיקה ידנית של 30 פריטים בתחילה, פרומפט iterations |
| איכות הפריטים מהמקור גרועה | בינונית | בינונית | שכבת `is_noise` שמסננת רעש |

---

## 13. תזכורות אישיות

- **שמירה על focus** — מטרת ה-MVP היא לעבוד עבורך אישית קודם כל. אל תוסיף features שאתה לא משתמש בהם.
- **תזמון** — נסה לסיים את ה-MVP לפני 13 ביוני (GPT-4-0613 retirement) — זה יהיה פוסט שיווקי מצוין.
- **מינוף** — אחרי שיש MVP, פוסט ארוך ב-`@AndroidAndAI` על המסע + הזמנה לבטא.
