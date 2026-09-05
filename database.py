import psycopg2
import os

def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def get_credits_for_month(month):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, amount, pay_day FROM credits WHERE is_active=1")
    credits = c.fetchall()
    result = []
    for cid, name, amount, pay_day in credits:
        c.execute("SELECT amount, pay_day, is_active FROM credit_overrides WHERE credit_id=%s AND month=%s",
                  (cid, month))
        override = c.fetchone()
        if override:
            if override[2] == 0:
                continue
            result.append((cid, name, float(override[0]), override[1]))
        else:
            result.append((cid, name, float(amount), pay_day))
    conn.close()
    return result

def get_fixed_for_month(month):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, amount, pay_day FROM fixed_expenses WHERE is_active=1")
    fixed = c.fetchall()
    result = []
    for fid, name, amount, pay_day in fixed:
        c.execute("SELECT amount, pay_day, is_active FROM fixed_overrides WHERE fixed_id=%s AND month=%s",
                  (fid, month))
        override = c.fetchone()
        if override:
            if override[2] == 0:
                continue
            result.append((fid, name, float(override[0]), override[1]))
        else:
            result.append((fid, name, float(amount), pay_day))
    conn.close()
    return result

def get_category_limit(category):
    """Returns the monthly limit (float) for a category, or None if not set."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT limit_amount FROM category_limits WHERE category=%s", (category,))
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row else None

def set_category_limit(category, limit_amount):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT category FROM category_limits WHERE category=%s", (category,))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE category_limits SET limit_amount=%s WHERE category=%s",
                  (limit_amount, category))
    else:
        c.execute("INSERT INTO category_limits (category, limit_amount) VALUES (%s,%s)",
                  (category, limit_amount))
    conn.commit()
    conn.close()

def get_all_category_limits():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT category, limit_amount FROM category_limits ORDER BY category")
    rows = c.fetchall()
    conn.close()
    return rows

def delete_category_limit(category):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM category_limits WHERE category=%s", (category,))
    conn.commit()
    conn.close()

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE,
        name TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS budget (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT,
        source TEXT,
        amount REAL,
        created_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS credits (
        id SERIAL PRIMARY KEY,
        name TEXT,
        amount REAL,
        pay_day INTEGER DEFAULT 1,
        is_active INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS fixed_expenses (
        id SERIAL PRIMARY KEY,
        name TEXT,
        amount REAL,
        pay_day INTEGER DEFAULT 1,
        is_active INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS other_expenses (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT,
        category TEXT,
        amount REAL,
        comment TEXT,
        created_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        type TEXT,
        ref_id INTEGER,
        amount REAL,
        status TEXT,
        month TEXT,
        created_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS credit_overrides (
        id SERIAL PRIMARY KEY,
        credit_id INTEGER,
        month TEXT,
        amount REAL,
        pay_day INTEGER,
        is_active INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS fixed_overrides (
        id SERIAL PRIMARY KEY,
        fixed_id INTEGER,
        month TEXT,
        amount REAL,
        pay_day INTEGER,
        is_active INTEGER DEFAULT 1
    )''')

    # ЖАҢА: категория бойынша ай сайынғы лимит
    c.execute('''CREATE TABLE IF NOT EXISTS category_limits (
        category TEXT PRIMARY KEY,
        limit_amount REAL
    )''')

    c.execute("SELECT COUNT(*) FROM credits")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO credits (name, amount, pay_day) VALUES (%s,%s,%s)", [
            ("Солнечный панель", 0, 1),
            ("Талим кредит", 0, 1),
            ("Миллий кредит", 0, 1),
        ])

    c.execute("SELECT COUNT(*) FROM fixed_expenses")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO fixed_expenses (name, amount, pay_day) VALUES (%s,%s,%s)", [
            ("Квартира", 0, 1),
            ("Бала таярлығы", 0, 1),
        ])

    conn.commit()
    conn.close()

def reset_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS credit_overrides")
    c.execute("DROP TABLE IF EXISTS fixed_overrides")
    c.execute("DROP TABLE IF EXISTS payments")
    c.execute("DROP TABLE IF EXISTS other_expenses")
    c.execute("DROP TABLE IF EXISTS fixed_expenses")
    c.execute("DROP TABLE IF EXISTS credits")
    c.execute("DROP TABLE IF EXISTS budget")
    c.execute("DROP TABLE IF EXISTS users")
    c.execute("DROP TABLE IF EXISTS category_limits")
    conn.commit()
    conn.close()
