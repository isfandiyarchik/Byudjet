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


def _draw_pie(ax, items, cmap_name, title, donut=False):
    labels = [_clean(l) for l, _ in items]
    values = [a for _, a in items]
    colors = plt.get_cmap(cmap_name).colors
    wedgeprops = {"width": 0.45, "edgecolor": "white"} if donut else {"edgecolor": "white"}
    ax.pie(
        values,
        labels=labels,
        autopct=lambda pct: f"{pct:.1f}%" if pct >= 4 else "",
        startangle=90,
        colors=colors,
        pctdistance=0.78 if donut else 0.6,
        wedgeprops=wedgeprops,
        textprops={"fontsize": 9},
    )
    ax.axis("equal")
    ax.set_title(title, fontsize=12)


def generate_expense_pie_chart(date_filter, labeled_amounts, income_amounts=None):
    """
    labeled_amounts: харажатлар — (label, amount) дизими.
    income_amounts:  кирислер — (source, amount) дизими (ихтиярий).
    Шеп тәрепте — харажатлар диаграммасы, оң тәрепте — кирис диаграммасы,
    төменде — Кирис / Харажат / Айырма қысқаша есабы.
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

    if expenses:
        _draw_pie(ax_exp, expenses, "tab20", f"Харажатлар — {date_filter}")
        ax_exp.text(0, -1.32, f"Жәми харажат: {_fmt(total_exp)} сум",
                    ha="center", fontsize=11, fontweight="bold", color="#C0392B")
    else:
        ax_exp.axis("off")
        ax_exp.text(0.5, 0.5, "Харажат жоқ", ha="center", va="center", fontsize=13, color="gray")
        ax_exp.set_title(f"Харажатлар — {date_filter}", fontsize=12)

    if incomes:
        _draw_pie(ax_inc, incomes, "Set2", f"Кирис — {date_filter}", donut=True)
        ax_inc.text(0, -1.32, f"Жәми кирис: {_fmt(total_inc)} сум",
                    ha="center", fontsize=11, fontweight="bold", color="#1E8449")
    else:
        ax_inc.axis("off")
        ax_inc.text(0.5, 0.5, "Бул айда кирис жоқ", ha="center", va="center", fontsize=13, color="gray")
        ax_inc.set_title(f"Кирис — {date_filter}", fontsize=12)

    sign = "+" if diff >= 0 else "-"
    color = "#1E8449" if diff >= 0 else "#C0392B"
    fig.text(0.5, 0.02,
             f"Кирис: {_fmt(total_inc)}   |   Харажат: {_fmt(total_exp)}   |   "
             f"Айырма: {sign}{_fmt(abs(diff))} сум",
             ha="center", fontsize=12, fontweight="bold", color=color)

    fig.subplots_adjust(bottom=0.1, wspace=0.25)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=130)
    plt.close(fig)
    buf.seek(0)
    buf.name = f"chart_{date_filter}.png"
    return buf
