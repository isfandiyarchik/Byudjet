import re
import matplotlib
matplotlib.use('Agg')  # headless server - no display needed
import matplotlib.pyplot as plt
from io import BytesIO

# DejaVu Sans эмодзини көрсете алмайды (квадрат болып шығады), сонлықтан
# диаграмма жазыўларынан эмодзилер алып тасланады.
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # эмодзи блоклары
    "\U00002600-\U000027BF"   # символлар / dingbats
    "\U00002B00-\U00002BFF"
    "\uFE0F\u200d"
    "]+",
    flags=re.UNICODE,
)


def _clean(label):
    return _EMOJI_RE.sub("", str(label)).strip()


def _fmt(v):
    return f"{v:,.0f}".replace(",", " ")


EXPENSE_COLORS = ["#C0392B", "#E67E22", "#F1C40F", "#D35400", "#E74C3C",
                  "#F39C12", "#A93226", "#F5B041", "#CD6155", "#DC7633"]
INCOME_COLORS = ["#1E8449", "#27AE60", "#58D68D", "#145A32", "#52BE80",
                 "#82E0AA", "#239B56", "#28B463"]
MIN_SHARE = 0.03   # 3% тен киши бөлимлер «Басқалар» ға қосылады


def _merge_small(items):
    """Киши үлесли бөлимлерди бир «Басқалар» ға бириктиреди (диаграмма тазалығы ушын)."""
    total = sum(a for _, a in items)
    if total <= 0 or len(items) <= 4:
        return items
    big, small = [], []
    for label, a in sorted(items, key=lambda x: -x[1]):
        (small if a / total < MIN_SHARE else big).append((label, a))
    if len(small) >= 2:
        big.append(("Басқалар", sum(a for _, a in small)))
    else:
        big.extend(small)
    return big


def _draw_donut(ax, items, palette, title, total_text, total_color):
    labels = [_clean(l) for l, _ in items]
    values = [a for _, a in items]
    colors = [palette[i % len(palette)] for i in range(len(items))]
    _, _, autotexts = ax.pie(
        values,
        labels=labels,
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 5 else "",
        startangle=90,
        counterclock=False,
        colors=colors,
        pctdistance=0.78,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 10},
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontweight("bold")
    ax.axis("equal")
    ax.set_title(title, fontsize=13, fontweight="bold")
    # Ортасына жәми сумма
    ax.text(0, 0.08, "Жәми", ha="center", va="center", fontsize=10, color="gray")
    ax.text(0, -0.1, total_text, ha="center", va="center", fontsize=14,
            fontweight="bold", color=total_color)


def generate_expense_pie_chart(date_filter, labeled_amounts, income_amounts=None):
    """
    labeled_amounts: харажатлар — (label, amount) дизими.
    income_amounts:  кирислер — (source, amount) дизими (ихтиярий).
    Шеп тәрепте — харажатлар (ыссы түслер), оң тәрепте — кирис (жасыл),
    ортасында жәми сумма, төменде — Кирис / Харажат / Айырма.
    Қайтарады: .name қойылған BytesIO PNG, ямаса кирис те харажат та жоқ болса None.
    """
    expenses = [(l, a) for l, a in (labeled_amounts or []) if a > 0]
    incomes = [(l, a) for l, a in (income_amounts or []) if a > 0]
    if not expenses and not incomes:
        return None

    total_exp = sum(a for _, a in expenses)
    total_inc = sum(a for _, a in incomes)
    diff = total_inc - total_exp

    fig, (ax_exp, ax_inc) = plt.subplots(1, 2, figsize=(14, 7.5))
    fig.patch.set_facecolor("white")

    if expenses:
        _draw_donut(ax_exp, _merge_small(expenses), EXPENSE_COLORS,
                    f"Харажатлар — {date_filter}", _fmt(total_exp), "#C0392B")
    else:
        ax_exp.axis("off")
        ax_exp.text(0.5, 0.5, "Харажат жоқ", ha="center", va="center", fontsize=13, color="gray")
        ax_exp.set_title(f"Харажатлар — {date_filter}", fontsize=13, fontweight="bold")

    if incomes:
        _draw_donut(ax_inc, _merge_small(incomes), INCOME_COLORS,
                    f"Кирис — {date_filter}", _fmt(total_inc), "#1E8449")
    else:
        ax_inc.axis("off")
        ax_inc.text(0.5, 0.5, "Бул айда кирис жоқ", ha="center", va="center", fontsize=13, color="gray")
        ax_inc.set_title(f"Кирис — {date_filter}", fontsize=13, fontweight="bold")

    sign = "+" if diff >= 0 else "-"
    color = "#1E8449" if diff >= 0 else "#C0392B"
    fig.text(0.5, 0.02,
             f"Кирис: {_fmt(total_inc)}   |   Харажат: {_fmt(total_exp)}   |   "
             f"Айырма: {sign}{_fmt(abs(diff))} сум",
             ha="center", fontsize=12, fontweight="bold", color=color)

    fig.subplots_adjust(bottom=0.1, wspace=0.25)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=130, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    buf.name = f"chart_{date_filter}.png"
    return buf
