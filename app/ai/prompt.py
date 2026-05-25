"""פרומפט הסיכום ו-JSON schema ל-Gemini.

ה-prompt העתקה כמעט מילולית של Spec §6.2 (התאמות מינוריות לפורמט).
ה-schema מתורגם ל-`response_schema` של ה-SDK — מבטיח שה-output תמיד
תקין מבחינת מבנה, ולא צריך לטפל ב-malformed JSON.
"""

from __future__ import annotations

# ה-schema מועבר ל-Gemini כ-response_schema. הוא גם משמש לתיעוד
# למה ה-processor מצפה מה-AI להחזיר.
RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "is_noise": {
            "type": "boolean",
            "description": "true אם זה לא משמעותי (תיקון UI/typo קוסמטי)",
        },
        "summary_he": {
            "type": "string",
            "description": "סיכום 1-3 משפטים בעברית. ריק אם is_noise=true.",
        },
        "severity": {
            "type": "string",
            "enum": ["critical", "important", "info"],
        },
        "is_urgent": {
            "type": "boolean",
            "description": "true רק אם נדרשת פעולה תוך 7 ימים",
        },
        "categories": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "deprecation",
                    "breaking",
                    "new_feature",
                    "pricing",
                    "security",
                    "bugfix",
                    "performance",
                ],
            },
            "description": "1-3 תגיות",
        },
    },
    "required": ["is_noise", "summary_he", "severity", "is_urgent", "categories"],
}


def build_prompt(
    *,
    api_name: str,
    raw_title: str,
    raw_content: str,
    source_url: str,
) -> str:
    """בונה את הפרומפט לפי Spec §6.2.

    ה-values מוטמעים as-is — Gemini לא רגיש ל-injection דרך תוכן
    changelog (אנחנו לא מבצעים פעולות על בסיס הפלט מעבר להצגה
    למשתמש שעובר escape בנפרד בכלל 6 ב-CLAUDE.md).
    """
    return f"""אתה עורך תוכן טכני בעברית. אני אתן לך פריט מתוך changelog של ספק API.
המשימה שלך: לסכם בעברית קצרה ובהירה, ולסווג.

הפריט:
API: {api_name}
כותרת: {raw_title}
תוכן: {raw_content}
URL: {source_url}

החזר JSON בלבד בפורמט הבא:
{{
  "is_noise": boolean,        // true אם זה לא משמעותי (תיקון טעות כתיב, עדכון UI קוסמטי)
  "summary_he": string,       // סיכום של 1-3 משפטים בעברית. אם is_noise=true, החזר ""
  "severity": "critical" | "important" | "info",
  "is_urgent": boolean,       // true רק אם נדרשת פעולה תוך 7 ימים (deprecation effective soon, breaking change live, security advisory)
  "categories": [string]      // 1-3 תגיות מתוך: deprecation, breaking, new_feature, pricing, security, bugfix, performance
}}

הנחיות לסיווג חומרה:
- critical: deprecation עם תאריך תוקף, breaking change, security issue
- important: תכונה משמעותית חדשה, שינוי תמחור, שינוי authentication
- info: שיפורים, תכונות קטנות, תיקוני באגים

הנחיות לעברית:
- שפה מקצועית אבל לא מסורבלת
- מונחים טכניים באנגלית כשמתאים (endpoint, deprecation, rate limit)
- בלי קלישאות שיווקיות
"""
