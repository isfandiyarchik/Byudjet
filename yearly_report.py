import openpyxl
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment
from io import BytesIO
from datetime import datetime
from database import get_conn
from summary import get_month_stats, build_carry_map

MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="4472C4")


def _style_header_row(ws, row_idx=1):
    for cell in ws[row_idx]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")


def _autosize_columns(ws):
    for col_cells in ws.columns:
        length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=8)
        ws.column_dimensions[col_cells[0].column_letter].width = length + 3


def generate_yearly_report(year):
    """
    Builds an in-memory .xlsx workbook:
      - 12 monthly detail sheets (income/credits/fixed/other + totals)
      - 1 summary sheet with a bar chart comparing months
    Returns a BytesIO (with .name set) ready for bot.send_document().
    """
    wb = openpyxl.Workbook()
    summary_ws = wb.active
    summary_ws.title = "Жыллық есабы"

    summary_ws.append(["Ай", "Кирис", "Кредитлер", "Тұрақлы харажатлар",
                        "Басқа харажатлар", "Улыма харажат", "Қалды", "Алдынғы айдан қалдық"])
    _style_header_row(summary_ws)

    # ТҮЗЕТИЛДИ (тезлик): бурын ҳәр ай ушын 3 бөлек байланыс ашылатын еди (12 айға — 36 байланыс).
    # Енди бир ғана байланыс барлық 12 айға бирдей қолланылады.
    conn = get_conn()
    today = datetime.now()
    carry_map = build_carry_map(conn, f"{year}-12", today)

    for month_num in range(1, 13):
        date_filter = f"{year}-{month_num:02d}"
        st = get_month_stats(date_filter, conn, today, carry_map=carry_map)

        income = st["income_total"]
        other_total = st["other_total"]
        if st["is_future"]:
            # жоспар айы: жоспарланған сумма
            credit_total, fixed_total = st["credit_total"], st["fixed_total"]
        else:
            # өткен/ағымдағы ай: тек нағыз төленгени
            credit_total, fixed_total = st["paid_credit_total"], st["paid_fixed_total"]
        total_expense = credit_total + fixed_total + other_total
        remaining = st["carry_in"] + income - total_expense

        month_name = MONTHS_RU[month_num]
        summary_ws.append([month_name, income, credit_total, fixed_total,
                           other_total, total_expense, remaining, st["carry_in"]])

        # ---- Per-month detail sheet ----
        ws = wb.create_sheet(title=month_name)
        ws.append(["Түри", "Аты/Категория", "Сумма"])
        _style_header_row(ws)

        if st["is_future"]:
            for _, name, amount, _ in st["credits"]:
                ws.append(["Кредит (план)", name, float(amount)])
            for _, name, amount, _ in st["fixed"]:
                ws.append(["Тұрақлы харажат (план)", name, float(amount)])
        else:
            for name, amount in st["paid_credits"]:
                ws.append(["Кредит (төленди)", name, float(amount)])
            for name, amount in st["paid_fixed"]:
                ws.append(["Тұрақлы харажат (төленди)", name, float(amount)])
            for _, name, amount, _ in st["pending_credits"]:
                ws.append(["Кредит (төленбеген)", name, float(amount)])
            for _, name, amount, _ in st["pending_fixed"]:
                ws.append(["Тұрақлы харажат (төленбеген)", name, float(amount)])
        for cat, amount in st["other_by_cat"]:
            ws.append(["Басқа харажат", cat, float(amount)])

        ws.append([])
        ws.append(["Алдынғы айдан қалдық", "", st["carry_in"]])
        ws.append(["Кирис", "", income])
        ws.append(["Улыума харажат", "", total_expense])
        ws.append(["Қалды", "", remaining])
        _autosize_columns(ws)

    conn.close()

    # ---- Bar chart on the summary sheet ----
    chart = BarChart()
    chart.type = "col"
    chart.title = f"{year} — Айлар бойынша кирис ҳәм харажат"
    chart.y_axis.title = "Сум"
    chart.x_axis.title = "Ай"
    chart.width = 26
    chart.height = 13

    data = Reference(summary_ws, min_col=2, max_col=6, min_row=1, max_row=13)
    cats = Reference(summary_ws, min_col=1, min_row=2, max_row=13)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    summary_ws.add_chart(chart, "I2")

    _autosize_columns(summary_ws)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = f"jyldyq_esap_{year}.xlsx"
    return buf
