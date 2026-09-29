import psycopg2
import os

def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def _items_for_month(base_table, ov_table, fk, month, conn=None):
    """
    Кредит ҳәм тұрақлы харажат ушын ортақ логика.
    - Сол айға жазылған override бар болса — сол қолланылады.
    - Override жоқ болса — тек is_active=1 болған тийкарғы жазба алынады.
    - Тек бир айға қосылған жазба (base is_active=0 + сол айда active override)
      сол айда көринеди, басқа айларда көринбейди.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    c = conn.cursor()
    c.execute(f"SELECT id, name, amount, pay_day, is_active FROM {base_table} ORDER BY id")
    base = c.fetchall()

    c.execute(f"SELECT {fk}, amount, pay_day, is_active FROM {ov_table} WHERE month=%s", (month,))
    overrides = {row[0]: (row[1], row[2], row[3]) for row in c.fetchall()}

    result = []
    for iid, name, amount, pay_day, is_active in base:
        if iid in overrides:
            o_amount, o_pay_day, o_active = overrides[iid]
            if o_active == 0:
                continue
            result.append((iid, name, float(o_amount), o_pay_day))
        elif is_active == 1:
            result.append((iid, name, float(amount), pay_day))

    if own_conn:
        conn.close()
    return result


def get_credits_for_month(month, conn=None):
    return _items_for_month("credits", "credit_overrides", "credit_id", month, conn)


def get_fixed_for_month(month, conn=None):
    return _items_for_month("fixed_expenses", "fixed_overrides", "fixed_id", month, conn)


def freeze_past_months(kind, item_id, conn):
    """
    Тийкарғы (глобал) жазба өзгертилгенде/өширилгенде өткен айлардың есабы
    өзгерип кетпеўи ушын, ески мәнислер сол айларға override сыпатында сақланады.
    kind: 'credit' | 'fixed'. conn: ашық байланыс (commit-ти шақырыўшы өзи етеди).
    Бул функция өзгертиўден АЛДЫН шақырылыўы керек.
    """
    from datetime import datetime
    current = datetime.now().strftime("%Y-%m")
    if kind == "credit":
        base_table, ov_table, fk = "credits", "credit_overrides", "credit_id"
    else:
        base_table, ov_table, fk = "fixed_expenses", "fixed_overrides", "fixed_id"
    c = conn.cursor()
    c.execute(f"SELECT amount, pay_day, is_active FROM {base_table} WHERE id=%s", (item_id,))
    row = c.fetchone()
    if not row or row[2] != 1:
        return
    amount, pay_day, _ = row

    # Өткен айлар: төлем, кирис ямаса харажат жазбасы бар айлар
    c.execute("SELECT DISTINCT month FROM payments WHERE month < %s", (current,))
    months = {r[0] for r in c.fetchall() if r[0]}
    c.execute("SELECT DISTINCT SUBSTRING(created_at, 1, 7) FROM budget")
    months |= {r[0] for r in c.fetchall() if r[0] and r[0] < current}
    c.execute("SELECT DISTINCT SUBSTRING(created_at, 1, 7) FROM other_expenses")
    months |= {r[0] for r in c.fetchall() if r[0] and r[0] < current}

    for m in sorted(months):
        c.execute(f"SELECT id FROM {ov_table} WHERE {fk}=%s AND month=%s", (item_id, m))
        if c.fetchone():
            continue
        c.execute(
            f"INSERT INTO {ov_table} ({fk}, month, amount, pay_day, is_active) VALUES (%s,%s,%s,%s,1)",
            (item_id, m, amount, pay_day))


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
