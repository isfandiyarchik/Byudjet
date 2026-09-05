import json
from io import BytesIO
from datetime import datetime
from database import get_conn

TABLES = [
    "users", "budget", "credits", "fixed_expenses", "other_expenses",
    "payments", "credit_overrides", "fixed_overrides", "category_limits",
]

def generate_backup():
    """
    Reads every table and returns an in-memory .json file (BytesIO with .name set)
    ready to be sent via bot.send_document(). Table names are hardcoded above
    (not user input), so this is safe from SQL injection.
    """
    conn = get_conn()
    c = conn.cursor()
    data = {}
    for table in TABLES:
        c.execute(f"SELECT * FROM {table}")
        cols = [desc[0] for desc in c.description]
        rows = c.fetchall()
        data[table] = [dict(zip(cols, row)) for row in rows]
    conn.close()

    payload = json.dumps(data, default=str, ensure_ascii=False, indent=2)
    buf = BytesIO(payload.encode("utf-8"))
    buf.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return buf

