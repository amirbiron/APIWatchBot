"""כלי עזר לאנונימיזציה של מזהי משתמשים ללוגים.

הרעיון: לא לרשום telegram_id גולמי ב-INFO logs (סיכון פרטיות אם logs נשמרים
ב-aggregator חיצוני). במקום זאת — hash קצר וקבוע פר משתמש, שמאפשר לעקוב
אחרי פעולות של אותו משתמש בלי לדעת מי הוא.

אין צורך ב-key סודי — זו אנונימיזציה, לא הצפנה. ה-hash הוא דטרמיניסטי
כדי שייצור אותו "user_hash" יישאר עקבי לאורך הזמן.
"""

from __future__ import annotations

import hashlib


def anon_user_id(telegram_id: int) -> str:
    """SHA-256 של telegram_id, מקוצר ל-12 תווים — מספיק לזיהוי ייחודי בlogs."""
    return hashlib.sha256(str(telegram_id).encode("utf-8")).hexdigest()[:12]
