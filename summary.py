"""
Ай есабының ортақ логикасы (баслапқы бет, азанғы хабар, есап, диаграмма, Excel, төлеў тексериўи).

Қағыйдалар:
1) Алдынғы айдан қалған «Қолда бар» автоматлық түрде кейинги айға өтеди.
2) «Семьяда айланған бюджет» = ТЕК нағыз төленген кредит/тұрақлы харажатлар + басқа харажатлар.
   Төленбегенлери бюджетке кирмейди, «⏳ Төленбеген» бөлиминде бөлек көринеди.
3) Келеси (план) айларда — барлық планласған сумма көрсетиледи.
"""
from datetime import datetime
from database import get_credits_for_month, get_fixed_for_month

MONTHS_KK = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель",
    5: "май", 6: "июнь", 7: "июль", 8: "август",
    9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь",
}


def _next_month(m):
    y, mo = map(int, m.split("-"))
    mo += 1
    if mo == 13:
        y, mo = y + 1, 1
    return f"{y}-{mo:02d}"


def _current_month(today=None):
    return (today or datetime.now()).strftime("%Y-%m")


def build_carry_map(conn, last_month, today=None):
    """
    {ай: сол айға кириўши қалдық}. Биринши мәлимет бар айдан баслап
    ҳәр айдың қалдығы кейинги айға өтип барады.
    Өткен айлар — нағыз төленгени бойынша; усы ай (план ушын) —
    төленбеген төлемлер де алынады; келеси айлар — план бойынша.
    """
    current = _current_month(today)
    c = conn.cursor()

    c.execute("SELECT SUBSTRING(created_at, 1, 7), COALESCE(SUM(amount),0) "
              "FROM budget GROUP BY SUBSTRING(created_at, 1, 7)")
    income = {m: float(a) for m, a in c.fetchall() if m}

    c.execute("SELECT SUBSTRING(created_at, 1, 7), COALESCE(SUM(amount),0) "
              "FROM other_expenses GROUP BY SUBSTRING(created_at, 1, 7)")
    other = {m: float(a) for m, a in c.fetchall() if m}

    c.execute("SELECT month, type, ref_id, amount FROM payments WHERE status='paid'")
    paid_total, paid_ids = {}, {}
    for m, ptype, rid, a in c.fetchall():
        paid_total[m] = paid_total.get(m, 0.0) + float(a)
        paid_ids.setdefault(m, set()).add((ptype, rid))

    months = set(income) | set(other) | set(paid_total)
    carry = {}
    if not months:
        return carry

    m = min(months)
    bal = 0.0
    while m <= last_month:
        carry[m] = bal
        if m == last_month:
            break
        if m < current:
            spent = paid_total.get(m, 0.0)
        elif m == current:
            ids = paid_ids.get(m, set())
            spent = paid_total.get(m, 0.0)
            spent += sum(a for cid, _, a, _ in get_credits_for_month(m, conn=conn) if ("credit", cid) not in ids)
            spent += sum(a for fid, _, a, _ in get_fixed_for_month(m, conn=conn) if ("fixed", fid) not in ids)
        else:
            spent = sum(a for _, _, a, _ in get_credits_for_month(m, conn=conn))
            spent += sum(a for _, _, a, _ in get_fixed_for_month(m, conn=conn))
        bal += income.get(m, 0.0) - spent - other.get(m, 0.0)
        m = _next_month(m)
    return carry


def get_month_stats(month, conn, today=None, carry_map=None):
    current = _current_month(today)
    is_future = month > current
    c = conn.cursor()

    c.execute("SELECT source, COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s GROUP BY source",
              (f"{month}%",))
    income_by_source = [(s, float(a)) for s, a in c.fetchall()]
    income_total = sum(a for _, a in income_by_source)

    c.execute("SELECT category, COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s GROUP BY category",
              (f"{month}%",))
    other_by_cat = [(cat, float(a)) for cat, a in c.fetchall()]
    other_total = sum(a for _, a in other_by_cat)

    c.execute("SELECT type, ref_id, amount FROM payments WHERE month=%s AND status='paid'", (month,))
    pay_rows = c.fetchall()

    c.execute("SELECT id, name FROM credits")
    credit_names = dict(c.fetchall())
    c.execute("SELECT id, name FROM fixed_expenses")
    fixed_names = dict(c.fetchall())

    credits = get_credits_for_month(month, conn=conn)
    fixed = get_fixed_for_month(month, conn=conn)

    paid_credits = [(credit_names.get(rid, "?"), float(a)) for t, rid, a in pay_rows if t == "credit"]
    paid_fixed = [(fixed_names.get(rid, "?"), float(a)) for t, rid, a in pay_rows if t == "fixed"]
    paid_credit_ids = {rid for t, rid, _ in pay_rows if t == "credit"}
    paid_fixed_ids = {rid for t, rid, _ in pay_rows if t == "fixed"}

    pending_credits = [x for x in credits if x[0] not in paid_credit_ids]
    pending_fixed = [x for x in fixed if x[0] not in paid_fixed_ids]

    paid_credit_total = sum(a for _, a in paid_credits)
    paid_fixed_total = sum(a for _, a in paid_fixed)
    paid_total = paid_credit_total + paid_fixed_total

    credit_total = sum(a for _, _, a, _ in credits)      # план
    fixed_total = sum(a for _, _, a, _ in fixed)         # план
    pending_total = sum(a for _, _, a, _ in pending_credits) + sum(a for _, _, a, _ in pending_fixed)

    if carry_map is None:
        carry_map = build_carry_map(conn, month, today)
    carry_in = carry_map.get(month, 0.0)

    available = carry_in + income_total - paid_total - other_total

    return {
        "month": month, "is_future": is_future,
        "income_by_source": income_by_source, "income_total": income_total,
        "other_by_cat": other_by_cat, "other_total": other_total,
        "credits": credits, "fixed": fixed,
        "credit_total": credit_total, "fixed_total": fixed_total,
        "paid_credits": paid_credits, "paid_fixed": paid_fixed,
        "paid_credit_total": paid_credit_total, "paid_fixed_total": paid_fixed_total,
        "paid_total": paid_total,
        "pending_credits": pending_credits, "pending_fixed": pending_fixed,
        "pending_total": pending_total,
        "carry_in": carry_in,
        "circulating": paid_total + other_total,          # нағыз айланған бюджет
        "planned_expense": credit_total + fixed_total + other_total,
        "available": available,
    }


def get_available(month, conn, today=None):
    """Төлеў алдынан тексериў ушын: қолдағы қаржы (өткен қалдық пенен бирге)."""
    return get_month_stats(month, conn, today)["available"]


def _pay_label(pay_day, month, today):
    y, mo = map(int, month.split("-"))
    name = MONTHS_KK[mo]
    if month == _current_month(today) and pay_day < today.day:
        return f"⚠️ {pay_day}-{name}, мерзими өтти"
    return f"{pay_day}-{name}"


def format_month_text(stats, today=None, title=None):
    today = today or datetime.now()
    month = stats["month"]
    text = f"{title}\n\n" if title else ""

    carry = stats["carry_in"]

    # ---------------- План айы ----------------
    if stats["is_future"]:
        if carry != 0:
            text += f"↪️ Алдынғы айдан өтетуғын қалдық (план): <b>{carry:+,.0f} сум</b>\n\n"
        if stats["income_by_source"]:
            text += "📥 <b>Кирис:</b>\n"
            for s, a in stats["income_by_source"]:
                text += f"  • {s}: <b>+{a:,.0f} сум</b>\n"
            text += f"  Итого: <b>+{stats['income_total']:,.0f} сум</b>\n\n"
        text += "🔴 <b>Кредитлер:</b>\n"
        for _, name, amount, _ in stats["credits"]:
            text += f"  • {name}: <b>{amount:,.0f} сум</b>\n"
        text += f"  Итого: <b>-{stats['credit_total']:,.0f} сум</b>\n"
        text += "\n🟡 <b>Тұрақлы харажатлар:</b>\n"
        for _, name, amount, _ in stats["fixed"]:
            text += f"  • {name}: <b>{amount:,.0f} сум</b>\n"
        text += f"  Итого: <b>-{stats['fixed_total']:,.0f} сум</b>\n"
        if stats["other_by_cat"]:
            text += "\n🟢 <b>Басқа харажатлар:</b>\n"
            for cat, a in stats["other_by_cat"]:
                text += f"  • {cat}: <b>-{a:,.0f} сум</b>\n"
            text += f"  Итого: <b>-{stats['other_total']:,.0f} сум</b>\n"
        forecast = carry + stats["income_total"] - stats["planned_expense"]
        text += f"\n💼 Планласған жәми харажат: <b>{stats['planned_expense']:,.0f} сум</b>\n"
        text += "\n──────────────────\n"
        text += f"💰 Болжам қалдық: <b>{forecast:,.0f} сум</b>"
        return text

    # ---------------- Усы ай / өткен ай ----------------
    text += f"💼 Семьяда айланған бюджет: <b>{stats['circulating']:,.0f} сум</b>\n"
    text += "<i>(тек төленгени + басқа харажатлар)</i>\n\n"

    if carry != 0:
        text += f"↪️ Алдынғы айдан өткен қалдық: <b>{carry:+,.0f} сум</b>\n"
    if stats["income_by_source"]:
        text += "📥 <b>Кирис:</b>\n"
        for s, a in stats["income_by_source"]:
            text += f"  • {s}: <b>+{a:,.0f} сум</b>\n"
        text += f"  Итого: <b>+{stats['income_total']:,.0f} сум</b>\n"
    if carry != 0 or stats["income_by_source"]:
        text += "\n"

    if stats["paid_credits"]:
        text += "🔴 <b>Кредитлер (төленди):</b>\n"
        for name, a in stats["paid_credits"]:
            text += f"  • {name}: <b>{a:,.0f} сум</b> ✅\n"
        text += f"  Итого: <b>-{stats['paid_credit_total']:,.0f} сум</b>\n"

    if stats["paid_fixed"]:
        text += "\n🟡 <b>Тұрақлы харажатлар (төленди):</b>\n"
        for name, a in stats["paid_fixed"]:
            text += f"  • {name}: <b>{a:,.0f} сум</b> ✅\n"
        text += f"  Итого: <b>-{stats['paid_fixed_total']:,.0f} сум</b>\n"

    if stats["other_by_cat"]:
        text += "\n🟢 <b>Басқа харажатлар:</b>\n"
        for cat, a in stats["other_by_cat"]:
            text += f"  • {cat}: <b>{a:,.0f} сум</b>\n"
        text += f"  Итого: <b>-{stats['other_total']:,.0f} сум</b>\n"

    if stats["pending_credits"] or stats["pending_fixed"]:
        text += "\n⏳ <b>Төленбеген (бюджетке киргизилмейди):</b>\n"
        for _, name, a, d in stats["pending_credits"]:
            text += f"  • 🔴 {name}: {a:,.0f} сум ({_pay_label(d, month, today)})\n"
        for _, name, a, d in stats["pending_fixed"]:
            text += f"  • 🟡 {name}: {a:,.0f} сум ({_pay_label(d, month, today)})\n"
        text += f"  Төлеўге керек: <b>{stats['pending_total']:,.0f} сум</b>\n"

    text += "\n──────────────────\n"
    text += f"💰 Қолда бар: <b>{stats['available']:,.0f} сум</b>"
    if stats["pending_total"] > 0:
        after = stats["available"] - stats["pending_total"]
        warn = " ⚠️" if after < 0 else ""
        text += f"\n📌 Барлық төлемлерден кейин: <b>{after:,.0f} сум</b>{warn}"
    return text
