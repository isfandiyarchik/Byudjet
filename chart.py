import matplotlib
matplotlib.use('Agg')  # headless server - no display needed
import matplotlib.pyplot as plt
from io import BytesIO


def generate_expense_pie_chart(date_filter, labeled_amounts):
    """
    labeled_amounts: list of (label, amount) tuples.
    Returns a BytesIO PNG image (with .name set), or None if there's nothing to plot.
    """
    labeled_amounts = [(label, amount) for label, amount in labeled_amounts if amount > 0]
    if not labeled_amounts:
        return None

    labels = [label for label, _ in labeled_amounts]
    values = [amount for _, amount in labeled_amounts]

    fig, ax = plt.subplots(figsize=(7, 7))
    colors = plt.get_cmap("tab20").colors
    ax.pie(
        values,
        labels=labels,
        autopct=lambda pct: f"{pct:.1f}%" if pct >= 3 else "",
        startangle=90,
        colors=colors,
        textprops={"fontsize": 9},
    )
    ax.axis("equal")
    ax.set_title(f"Харажатлар бөлистириўи — {date_filter}", fontsize=13)

    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    buf.name = f"chart_{date_filter}.png"
    return buf

