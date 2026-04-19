from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def export_stock_pdf(symbol: str, quote: dict[str, Any], technicals: dict[str, Any], ai_analysis: dict[str, Any]) -> Path:
    output_dir = Path("data/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{symbol.upper()}_report.pdf"
    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, f"{symbol.upper()} AI Stock Report")
    y -= 34
    pdf.setFont("Helvetica", 10)
    lines = [
        f"Company: {quote.get('company_name', symbol)}",
        f"Current Price: {quote.get('current_price')}",
        f"Trend: {technicals.get('Trend')}",
        f"RSI: {technicals.get('RSI (14)')}",
        f"AI Stance: {ai_analysis.get('stance')}",
        f"Final Score: {ai_analysis.get('final_score')}/100",
        "",
        "Short-term Outlook:",
        str(ai_analysis.get("short_term_outlook", "")),
        "",
        "Long-term Outlook:",
        str(ai_analysis.get("long_term_outlook", "")),
    ]
    for line in lines:
        if y < 50:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y, line[:105])
        y -= 18
    pdf.save()
    return path
