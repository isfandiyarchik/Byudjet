"""
Ай есабының ортақ логикасы (баслапқы бет, азанғы хабар, есап, диаграмма, Excel, төлеў тексериўи).

Қағыйдалар:
1) Алдынғы айдан қалған «Қолда бар» автоматлық түрде кейинги айға өтеди.
2) «Семьяда айланған бюджет» = ТЕК нағыз төленген кредит/тұрақлы харажатлар + басқа харажатлар.
   Төленбегенлери бюджетке кирмейди, «⏳ Төленбеген» бөлиминде бөлек көринеди.
3) Келеси (план) айларда — барлық ойласылған сумма көрсетиледи.
4) Өткен айда төленбей қалған кредит/тұрақлы харажат ОШИРИЛМЕЙДИ: ол қарыз болып таза айға өтеди,
   суммасы қалдықтан алынып қойылады ҳәм «⚠️ Өткен айлардан төленбеген» бөлиминде көринеди.
   Оны төлеўге ямаса есаптан алып тастаўға болады ("skipped").
   Бул қағыйда ARREARS_FROM айынан (әдеттегиде 2026-10) баслап ислейди,
   сонда ески айлардың мәлиметлери отирик қарыз шығармайды.
"""
import os
import re
from common import uz_now
from database import get_credits_for_month, get_fixed_for_month

MONTHS_KK = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель",
    5: "май", 6: "июнь", 7: "июль", 8: "август",
    9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь",
}

_raw_from = os.getenv("ARREARS_FROM", "2026-10")
ARREARS_FROM = _raw_from if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", _raw_from or "") else "2026-10"

_EMPTY_PAY = {"paid": {}, "skipped": set()}


def _next_month(m):
    y, mo = map(int, m.split("-"))
    mo += 1
    if mo == 13:
        y, mo = y + 1, 1
    return f"{y}-{mo:02d}"


def _current_month(today=None):
    return (today or uz_now()).strftime("%Y-%m")


def _months_between(start, end_exclusive):
    m = start
    while m < end_exclusive:
        yield m
        m = _next_month(m)


def month_label(month):
    """'2026-10' -> 'октябрь'"""
    return MONTHS_KK[int(month.split("-")[1])]


def _load_payments(conn):
    """{ай: {"paid": {(түри, id): сумма}, "skipped": {(түри, id)}}}"""
    c = conn.cursor()
    c.execute("SELECT month, type, ref_id, amount, status FROM payments")
    res = {}
    for m, t, rid, a, st in c.fetchall():
        d = res.setdefault(m, {"paid": {}, "skipped": set()})
        if st == "paid":
            d["paid"][(t, rid)] = d["paid"].get((t, rid), 0.0) + float(a)
        elif st == "skipped":
            d["skipped"].add((t, rid))
    return res


def _unsettled(conn, month, pay):
    """Сол айда төленбеген ҳәм есаптан алынбаған кредит/тұрақлы харажатлар."""
    p = pay.get(month, _EMPTY_PAY)
    done = set(p["paid"]) | p["skipped"]
    credits = [x for x in get_credits_for_month(month, conn=conn) if ("credit", x[0]) not in done]
    fixed = [x for x in get_fixed_for_month(month, conn=conn) if ("fixed", x[0]) not in done]
    return credits, fixed


def get_arrears(conn, today=None, pay=None):
    """
    Өткен айлардан (ARREARS_FROM ден усы айға шекем) төленбей қалғанлар.
    Қайтарады: [(түри 'credit'|'fixed', id, аты, сумма, төлем күни, ай), ...]
    """
    current = _current_month(today)
    if pay is None:
        pay = _load_payments(conn)
    result = []
    for m in _months_between(ARREARS_FROM, current):
        credits, fixed = _unsettled(conn, m, pay)
        for cid, name, amount, day in credits:
            if amount > 0:
                result.append(("credit", cid, name, float(amount), day, m))
        for fid, name, amount, day in fixed:
            if amount > 0:
                result.append(("fixed", fid, name, float(amount), day, m))
    return result


def get_arrears_total(conn, today=None):
    return sum(a[3] for a in get_arrears(conn, today))


def build_carry_map(conn, last_month, today=None):
    """
    {ай: сол айға кириўши қалдық}. Биринши мәлимет бар айдан баслап
    ҳәр айдың қалдығы кейинги айға өтип барады.
    - Өткен айлар: төленгени + (ARREARS_FROM ден баслап) төленбей қалғаны (қарыз ретинде);
    - Усы ай (кейинги айға план ушын): төленбеген төлемлер де алынады;
    - Келеси айлар: план бойынша.
    """
    current = _current_month(today)
    c = conn.cursor()

    c.execute("SELECT SUBSTRING(created_at, 1, 7), COALESCE(SUM(amount),0) "
              "FROM budget GROUP BY SUBSTRING(created_at, 1, 7)")
    income = {m: float(a) for m, a in c.fetchall() if m}

    c.execute("SELECT SUBSTRING(created_at, 1, 7), COALESCE(SUM(amount),0) "
              "FROM other_expenses GROUP BY SUBSTRING(created_at, 1, 7)")
    other = {m: float(a) for m, a in c.fetchall() if m}

    pay = _load_payments(conn)
    paid_total = {m: sum(d["paid"].values()) for m, d in pay.items()}

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
            if m >= ARREARS_FROM:
                cr, fx = _unsettled(conn, m, pay)
                spent += sum(a for _, _, a, _ in cr if a > 0) + sum(a for _, _, a, _ in fx if a > 0)
        elif m == current:
            spent = paid_total.get(m, 0.0)
            cr, fx = _unsettled(conn, m, pay)
            spent += sum(a for _, _, a, _ in cr) + sum(a for _, _, a, _ in fx)
        else:
            spent = sum(a for _, _, a, _ in get_credits_for_month(m, conn=conn))
            spent += sum(a for _, _, a, _ in get_fixed_for_month(m, conn=conn))
        bal += income.get(m, 0.0) - spent - other.get(m, 0.0)
        m = _next_month(m)
    return carry


def get_month_stats(month, conn, today=None, carry_map=None):
    current = _current_month(today)
    is_future = month > current
    is_past = month < current
    c = conn.cursor()

    c.execute("SELECT source, COALESCE(SUM(amount),0) FROM budget WHERE created_at LIKE %s GROUP BY source",
              (f"{month}%",))
    income_by_source = [(s, float(a)) for s, a in c.fetchall()]
    income_total = sum(a for _, a in income_by_source)

    c.execute("SELECT category, COALESCE(SUM(amount),0) FROM other_expenses WHERE created_at LIKE %s GROUP BY category",
              (f"{month}%",))
    other_by_cat = [(cat, float(a)) for cat, a in c.fetchall()]
    other_total = sum(a for _, a in other_by_cat)

    pay = _load_payments(conn)
    p = pay.get(month, _EMPTY_PAY)

    c.execute("SELECT id, name FROM credits")
    credit_names = dict(c.fetchall())
    c.execute("SELECT id, name FROM fixed_expenses")
    fixed_names = dict(c.fetchall())

    credits = get_credits_for_month(month, conn=conn)
    fixed = get_fixed_for_month(month, conn=conn)

    paid_credits = [(credit_names.get(rid, "?"), a) for (t, rid), a in p["paid"].items() if t == "credit"]
    paid_fixed = [(fixed_names.get(rid, "?"), a) for (t, rid), a in p["paid"].items() if t == "fixed"]

    pending_credits, pending_fixed = _unsettled(conn, month, pay)

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

    # Өткен айда төленбей қалғаны кейинги айға қарыз болып өтеди
    reserved = 0.0
    if is_past and month >= ARREARS_FROM:
        reserved = (sum(a for _, _, a, _ in pending_credits if a > 0)
                    + sum(a for _, _, a, _ in pending_fixed if a > 0))

    arrears = get_arrears(conn, today, pay) if month == current else []
    arrears_total = sum(a[3] for a in arrears)

    return {
        "month": month, "is_future": is_future, "is_past": is_past,
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
        "reserved": reserved,
        "arrears": arrears, "arrears_total": arrears_total,
    }


def get_available(month, conn, today=None):
    """Төлеў алдынан тексериў ушын: қолдағы қаржы (өткен қалдық пенен бирге)."""
    return get_month_stats(month, conn, today)["available"]


def _pay_label(pay_day, month, today):
    name = month_label(month)
    if month == _current_month(today) and pay_day < today.day:
        return f"⚠️ {pay_day}-{name}, мерзими өтти"
    return f"{pay_day}-{name}"


def format_month_text(stats, today=None, title=None):
    today = today or uz_now()
    month = stats["month"]
    text = f"{title}\n\n" if title else ""

    carry = stats["carry_in"]

    # ---------------- План айы ----------------
    if stats["is_future"]:
        if carry != 0 or stats["income_by_source"]:
            text += "📥 <b>Кирис:</b>\n"
            if carry != 0:
                text += f"  • ↪️ Өтетуғын қалдық (план): <b>{carry:+,.0f} сум</b>\n"
            for s, a in stats["income_by_source"]:
                text += f"  • {s}: <b>+{a:,.0f} сум</b>\n"
            text += f"  <b>Итого: {carry + stats['income_total']:+,.0f} сум</b>\n\n"
        text += "🔴 <b>Кредитлер:</b>\n"
        for _, name, amount, _ in stats["credits"]:
            text += f"  • {name}: <b>{amount:,.0f} сум</b>\n"
        text += f"  <b>Итого: -{stats['credit_total']:,.0f} сум</b>\n"
        text += "\n🟡 <b>Тұрақлы харажатлар:</b>\n"
        for _, name, amount, _ in stats["fixed"]:
            text += f"  • {name}: <b>{amount:,.0f} сум</b>\n"
        text += f"  <b>Итого: -{stats['fixed_total']:,.0f} сум</b>\n"
        if stats["other_by_cat"]:
            text += "\n🟢 <b>Басқа харажатлар:</b>\n"
            for cat, a in stats["other_by_cat"]:
                text += f"  • {cat}: <b>-{a:,.0f} сум</b>\n"
            text += f"  <b>Итого: -{stats['other_total']:,.0f} сум</b>\n"
        forecast = carry + stats["income_total"] - stats["planned_expense"]
        text += f"\n💼 Ойласылған жәми харажат: <b>{stats['planned_expense']:,.0f} сум</b>\n"
        text += "\n──────────────────\n"
        text += f"💰 <b>План қалдық: {forecast:,.0f} сум</b>"
        return text

    # ---------------- Усы / өткен ай ----------------
    if carry != 0 or stats["income_by_source"]:
        text += "📥 <b>Кирис:</b>\n"
        if carry != 0:
            text += f"  • ↪️ Алдынғы айдан өткен қалдық: <b>{carry:+,.0f} сум</b>\n"
        for s, a in stats["income_by_source"]:
            text += f"  • {s}: <b>+{a:,.0f} сум</b>\n"
        text += f"  <b>Итого: {carry + stats['income_total']:+,.0f} сум</b>\n\n"

    if stats["paid_credits"]:
        text += "🔴 <b>Кредитлер (төленди):</b>\n"
        for name, a in stats["paid_credits"]:
            text += f"  • {name}: <b>{a:,.0f} сум</b> ✅\n"
        text += f"  <b>Итого: -{stats['paid_credit_total']:,.0f} сум</b>\n"

    if stats["paid_fixed"]:
        text += "\n🟡 <b>Тұрақлы харажатлар (төленди):</b>\n"
        for name, a in stats["paid_fixed"]:
            text += f"  • {name}: <b>{a:,.0f} сум</b> ✅\n"
        text += f"  <b>Итого: -{stats['paid_fixed_total']:,.0f} сум</b>\n"

    if stats["other_by_cat"]:
        text += "\n🟢 <b>Басқа харажатлар:</b>\n"
        for cat, a in stats["other_by_cat"]:
            text += f"  • {cat}: <b>{a:,.0f} сум</b>\n"
        text += f"  <b>Итого: -{stats['other_total']:,.0f} сум</b>\n"

    # Өткен айлардан қалған қарыз (тек усы айда)
    if stats["arrears"]:
        text += "\n⚠️ <b>Өткен айлардан төленбеген:</b>\n"
        for kind, _, name, a, day, m in stats["arrears"]:
            icon = "🔴" if kind == "credit" else "🟡"
            text += f"  • {icon} {name}: <b>{a:,.0f} сум</b> ({day}-{month_label(m)})\n"
        text += f"  <b>Итого: {stats['arrears_total']:,.0f} сум</b>\n"
        text += "  <i>(бул сумма қалдықтан алынып қойылған)</i>\n"

    if stats["pending_credits"] or stats["pending_fixed"]:
        text += "\n⏳ <b>Төленбеген (бюджетке киргизилмейди):</b>\n"
        for _, name, a, d in stats["pending_credits"]:
            text += f"  • 🔴 {name}: <b>{a:,.0f} сум</b> ({_pay_label(d, month, today)})\n"
        for _, name, a, d in stats["pending_fixed"]:
            text += f"  • 🟡 {name}: <b>{a:,.0f} сум</b> ({_pay_label(d, month, today)})\n"
        text += f"  <b>Төлениўи керек: {stats['pending_total']:,.0f} сум</b>\n"

    text += "\n──────────────────\n"
    text += f"💰 <b>Қолда бар: {stats['available']:,.0f} сум</b>\n"
    text += f"💼 <b>Айланған бюджет: {stats['circulating']:,.0f} сум</b>\n"
    text += "<i>(тек төленгени + басқа харажатлар)</i>"

    if stats["reserved"] > 0:
        text += (f"\n\n📌 Кейинги айға өткен қалдық: "
                 f"<b>{stats['available'] - stats['reserved']:,.0f} сум</b>\n"
                 f"<i>(төленбеген {stats['reserved']:,.0f} сум қарыз болып алынды)</i>")
    return text
