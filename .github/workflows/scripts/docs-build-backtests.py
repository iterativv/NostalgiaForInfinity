import os
import re
from datetime import datetime
from collections import defaultdict

INPUT_DIR = "docs/backtest-results"
OUTPUT_DIR = "docs/backtest-results"
WALLET_CAPITAL = 10000
WALLET_TYPE = "Dry Backtest Wallet"

# ----------------------------
# DATE HELPERS
# ----------------------------
def to_month_name(date_int):
    return datetime.strptime(str(date_int), "%Y%m%d").strftime("%B")


def get_start_date(filename):
    return int(filename.replace(".txt", "").split("-")[-2])


def detect_exchange(filename):
    f = filename.lower()
    if "binance-futures" in f:
        return "binance-futures"
    if "binance-spot" in f:
        return "binance-spot"
    if "kucoin" in f:
        return "kucoin-spot"
    return "unknown"

def wallet_banner():
    return f"""
<div style="padding:12px;border:1px solid #444;border-radius:8px;background:#111;color:#eee">

<b>⚠️ SIMULATION ENVIRONMENT</b><br><br>

💰 Wallet Type: <b>{WALLET_TYPE}</b><br>
💵 Starting Capital: <b>{WALLET_CAPITAL:,} USDT</b><br>
📊 Mode: Backtest / No real capital risk<br>

</div>

---
"""

# ----------------------------
# PARSER
# ----------------------------
def parse_txt(text):
    for line in text.splitlines():
        if "NostalgiaForInfinityX7" in line:
            parts = [p.strip() for p in line.split("│")]

            if len(parts) > 8:
                trades = int(parts[2])
                avg_profit = float(parts[3])
                total_profit_usdt = float(parts[4])
                total_profit_pct = float(parts[5])

                win_block = parts[7].split()
                winrate = float(win_block[3]) if len(win_block) >= 4 else 0

                dd = re.search(r"([\d\.]+)%", parts[8])
                drawdown = float(dd.group(1)) if dd else 0

                return {
                    "trades": trades,
                    "avg_profit": avg_profit,
                    "total_profit_usdt": total_profit_usdt,
                    "total_profit_pct": total_profit_pct,
                    "winrate": winrate,
                    "drawdown": drawdown
                }

    return {
        "trades": 0,
        "avg_profit": 0,
        "total_profit_usdt": 0,
        "total_profit_pct": 0,
        "winrate": 0,
        "drawdown": 0
    }


# ----------------------------
# STORAGE
# ----------------------------
data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
exchange_summary = defaultdict(list)


# ----------------------------
# SCAN FILES
# ----------------------------
for f in os.listdir(INPUT_DIR):
    if not f.endswith(".txt"):
        continue

    start_date = get_start_date(f)

    if start_date > 20251231:
        continue

    exchange = detect_exchange(f)
    year = str(start_date)[:4]
    month = to_month_name(start_date)

    with open(os.path.join(INPUT_DIR, f), "r", encoding="utf-8") as file:
        parsed = parse_txt(file.read())

    parsed["file"] = f

    data[exchange][year][month].append(parsed)
    exchange_summary[exchange].append(parsed)


# ----------------------------
# MONTHLY PAGES
# ----------------------------
for ex, years in data.items():
    for year, months in years.items():
        for month, rows in months.items():

            path = os.path.join(OUTPUT_DIR, ex, year)
            os.makedirs(path, exist_ok=True)

            file_path = os.path.join(path, f"{month.lower()}.md")

            def avg(k):
                return sum(r[k] for r in rows) / len(rows)

            md = f"# 📊 {ex.upper()} - {month} {year}\n\n"
            md += wallet_banner() + "\n"

            md += "## KPIs\n\n"
            md += f"- Avg Profit: **{avg('avg_profit'):.2f}%**\n"
            md += f"- Avg Winrate: **{avg('winrate'):.2f}%**\n"
            md += f"- Avg Drawdown: **{avg('drawdown'):.2f}%**\n"
            md += f"- Total Trades: **{sum(r['trades'] for r in rows)}**\n\n"

            md += "## Runs\n\n"
            md += "| File | Trades | Profit % | Winrate | Drawdown |\n"
            md += "|------|--------|----------|----------|----------|\n"

            for r in rows:
                md += f"| {r['file']} | {r['trades']} | {r['total_profit_pct']} | {r['winrate']} | {r['drawdown']} |\n"

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(md)


# ----------------------------
# EXCHANGE SUMMARY
# ----------------------------
for ex, rows in exchange_summary.items():

    path = os.path.join(OUTPUT_DIR, ex)
    os.makedirs(path, exist_ok=True)

    total_trades = sum(r["trades"] for r in rows)
    total_profit = sum(r["total_profit_usdt"] for r in rows)
    avg_winrate = sum(r["winrate"] for r in rows) / len(rows)
    avg_drawdown = sum(r["drawdown"] for r in rows) / len(rows)

    md = f"# 🌍 {ex.upper()} Summary\n\n"
    md += wallet_banner() + "\n"

    md += "## 📊 Exchange Overview\n\n"
    md += f"- Total Trades: **{total_trades}**\n"
    md += f"- Total Profit (USDT): **{total_profit:.2f}**\n"
    md += f"- Avg Winrate: **{avg_winrate:.2f}%**\n"
    md += f"- Avg Drawdown: **{avg_drawdown:.2f}%**\n\n"

    md += "## 🧠 Insight\n"
    md += "- Aggregated across all years & months\n"
    md += "- Represents full strategy performance on this exchange\n"

    with open(os.path.join(path, "summary.md"), "w", encoding="utf-8") as f:
        f.write(md)


print("✅ Done: full MkDocs structure generated")