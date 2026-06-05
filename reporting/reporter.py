"""
Enhanced Reporter — full analytics dashboard with regime overlays.
Equity curve, underwater DD, rolling Sharpe, exposure, regime breakdown.
"""
import sys, os, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from analytics.metrics import compute_all_metrics, rolling_window
from analytics.regime import build_regime_labels, segment_by_regime

DARK = {
    "bg": "#0d1117",
    "fg": "#c9d1d9",
    "green": "#3fb950",
    "red": "#f85149",
    "blue": "#58a6ff",
    "yellow": "#d2991d",
    "grid": "#21262d",
    "purple": "#bc8cff",
}


def _setup_style():
    plt.rcParams.update({
        "figure.facecolor": DARK["bg"],
        "axes.facecolor": DARK["bg"],
        "axes.edgecolor": DARK["grid"],
        "axes.labelcolor": DARK["fg"],
        "text.color": DARK["fg"],
        "xtick.color": DARK["fg"],
        "ytick.color": DARK["fg"],
        "grid.color": DARK["grid"],
        "grid.alpha": 0.3,
    })


def generate_report(engine, months: list, weeks: list, output_dir: str = "reports"):
    """Generate comprehensive analytics dashboard."""
    os.makedirs(output_dir, exist_ok=True)
    _setup_style()

    sells = [t for t in engine.trades if t["action"] == "SELL"]
    if not sells:
        print("No trades to report.")
        return

    # Extract data
    eq_dates = [e[0] for e in engine.equity_curve if e[0] is not None]
    eq_values = [e[1] for e in engine.equity_curve]
    trade_pnls = [t.get("net_pnl_pct", t.get("pnl_pct", 0)) for t in sells]
    years = (len(weeks) / 52) if weeks else 1.0

    # Compute metrics
    metrics = compute_all_metrics(sells, eq_values, years)

    # Regime analysis
    monthly_closes = [m["close"] for m in months]
    regime_labels = build_regime_labels(monthly_closes)
    trade_wins = [1 if p > 0 else 0 for p in trade_pnls]

    # ---- Chart 1: Equity Curve with Drawdown Underwater ----
    fig = plt.figure(figsize=(18, 10))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.05)

    ax1 = fig.add_subplot(gs[0])
    ax1.plot(eq_dates, eq_values[1:], color=DARK["green"], linewidth=1.2, label="Strategy Equity")
    ax1.axhline(y=engine.initial, color=DARK["fg"], linewidth=0.5, alpha=0.3, linestyle="--")
    ax1.set_title(f"Equity Curve | Return: {metrics['total_return_pct']}% | Sharpe: {metrics['sharpe_ratio']} | MaxDD: {metrics['max_drawdown_pct']}%",
                  fontsize=11, fontweight="bold", pad=10)
    ax1.set_ylabel("Equity (HKD)", fontsize=9)
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.15)

    # Underwater
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    peak = engine.initial
    dds = []
    for v in eq_values[1:]:
        if v > peak:
            peak = v
        dds.append((v - peak) / peak * 100 if peak > 0 else 0)
    ax2.fill_between(eq_dates, dds, 0, color=DARK["red"], alpha=0.4)
    ax2.plot(eq_dates, dds, color=DARK["red"], linewidth=0.8)
    ax2.set_ylabel("DD %", fontsize=9)
    ax2.set_xlabel("Date", fontsize=9)
    ax2.grid(True, alpha=0.15)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.tight_layout()
    fig.savefig(f"{output_dir}/equity_drawdown.png", dpi=150, facecolor=DARK["bg"])
    plt.close()
    print(f"✅ equity_drawdown.png")

    # ---- Chart 2: Rolling Sharpe ----
    weekly_returns = []
    for i in range(1, len(eq_values)):
        r = (eq_values[i] - eq_values[i - 1]) / eq_values[i - 1] * 100 if eq_values[i - 1] > 0 else 0
        weekly_returns.append(r)

    roll_sharpe = []
    window = 26  # ~6 months
    for i in range(len(weekly_returns)):
        start = max(0, i - window)
        wr = weekly_returns[start:i + 1]
        if len(wr) >= 2:
            mu = sum(wr) / len(wr)
            sd = (sum((r - mu) ** 2 for r in wr) / (len(wr) - 1)) ** 0.5
            sr = (mu / sd) * (52 ** 0.5) if sd > 0 else 0
        else:
            sr = 0
        roll_sharpe.append(sr)

    fig, ax = plt.subplots(figsize=(18, 5))
    ax.plot(eq_dates, roll_sharpe, color=DARK["blue"], linewidth=1.2)
    ax.axhline(y=0, color=DARK["fg"], linewidth=0.5, alpha=0.3)
    ax.axhline(y=1, color=DARK["green"], linewidth=0.5, alpha=0.3, linestyle="--", label="Sharpe=1")
    ax.fill_between(eq_dates, roll_sharpe, 0, where=[s > 0 for s in roll_sharpe],
                     color=DARK["green"], alpha=0.1)
    ax.fill_between(eq_dates, roll_sharpe, 0, where=[s <= 0 for s in roll_sharpe],
                     color=DARK["red"], alpha=0.1)
    ax.set_title("Rolling Sharpe Ratio (6-month window)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Sharpe", fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.15)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.tight_layout()
    fig.savefig(f"{output_dir}/rolling_sharpe.png", dpi=150, facecolor=DARK["bg"])
    plt.close()
    print(f"✅ rolling_sharpe.png")

    # ---- Chart 3: Trade P&L Distribution + Win/Loss ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5))
    colors = [DARK["green"] if p > 0 else DARK["red"] for p in trade_pnls]
    ax1.bar(range(len(trade_pnls)), trade_pnls, color=colors, edgecolor=DARK["fg"], linewidth=0.3)
    ax1.axhline(y=0, color=DARK["fg"], linewidth=0.5)
    ax1.set_title(f"Trade-by-Trade | WR: {metrics['win_rate_pct']}% | PF: {metrics['profit_factor']}",
                  fontsize=10, fontweight="bold")
    ax1.set_ylabel("Return %", fontsize=9)
    ax1.grid(True, alpha=0.15)

    wins = sum(1 for p in trade_pnls if p > 0)
    losses = len(trade_pnls) - wins
    ax2.pie([wins, losses], labels=[f"Win ({wins})", f"Loss ({losses})"],
            colors=[DARK["green"], DARK["red"]], autopct="%1.0f%%",
            explode=(0.05, 0), startangle=90,
            textprops={"color": DARK["fg"], "fontsize": 10})
    ax2.set_title("Win Rate", fontsize=10, fontweight="bold")
    plt.tight_layout()
    fig.savefig(f"{output_dir}/pnl_analysis.png", dpi=150, facecolor=DARK["bg"])
    plt.close()
    print(f"✅ pnl_analysis.png")

    # ---- Chart 4: Exposure Chart ----
    in_position = []
    for t in engine.trades:
        if t["action"] == "BUY":
            in_position.append({"date": t["date"], "exposed": True})
        elif t["action"] == "SELL" and in_position:
            in_position[-1]["exit_date"] = t["date"]

    fig, ax = plt.subplots(figsize=(18, 4))
    for entry in in_position:
        if "exit_date" not in entry:
            continue
        ax.axvspan(entry["date"], entry["exit_date"], alpha=0.3, color=DARK["green"])
    ax.set_title(f"Exposure Timeline | {len(in_position)} positions | Exposure: {metrics['trades']} trades",
                 fontsize=10, fontweight="bold")
    ax.set_xlabel("Date", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.tight_layout()
    fig.savefig(f"{output_dir}/exposure.png", dpi=150, facecolor=DARK["bg"])
    plt.close()
    print(f"✅ exposure.png")

    # ---- Save JSON Report ----
    report = {
        "metrics": metrics,
        "config": {
            "trailing_activation_pct": getattr(engine.strategy, 'trailing_activation', 'N/A'),
            "trailing_distance_pct": getattr(engine.strategy, 'trailing_distance', 'N/A'),
            "confirmation_weeks": getattr(engine.strategy, 'confirmation_weeks', 'N/A'),
            "kelly_fraction": getattr(engine.strategy, 'kelly', 'N/A'),
        },
        "trades": engine.trades,
    }
    json_path = f"{output_dir}/report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"✅ report.json")
    
    return report
