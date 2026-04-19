from __future__ import annotations

from backend.scanner import scan_breakout_stocks, scan_strong_fundamentals
from utils.telegram_alerts import send_telegram_alert


def build_daily_scanner_report() -> str:
    breakout = scan_breakout_stocks()[:5]
    fundamentals = scan_strong_fundamentals()[:5]
    lines = ["Daily Indian Stock Scanner Report", "", "Breakout candidates:"]
    lines.extend([f"- {row['Symbol']}: score {row['Score']}" for row in breakout] or ["- No matches"])
    lines.append("")
    lines.append("Strong fundamental candidates:")
    lines.extend([f"- {row['Symbol']}: score {row['Score']}" for row in fundamentals] or ["- No matches"])
    return "\n".join(lines)


def send_daily_scanner_report() -> bool:
    return send_telegram_alert(build_daily_scanner_report())
