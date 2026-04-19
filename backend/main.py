from fastapi import FastAPI, HTTPException

from backend.ai_analysis import generate_ai_analysis
from backend.fundamentals import get_fundamentals
from backend.nse_universe import segment_options, universe_for_segment
from backend.patterns import detect_chart_patterns
from backend.scanner import SCAN_FUNCTIONS
from backend.stock_data import collect_price_histories, get_price_history, get_quote
from backend.technical_analysis import technical_summary
from backend.tradingview_analysis import get_tradingview_summary
from backend.watchlist import add_to_watchlist, list_watchlist, remove_from_watchlist, seed_default_watchlist


app = FastAPI(title="Indian Stock AI Agent API", version="1.0.0")


@app.on_event("startup")
def startup() -> None:
    seed_default_watchlist()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/stock/{symbol}")
def stock_analysis(symbol: str) -> dict:
    try:
        quote = get_quote(symbol)
        _, history = get_price_history(symbol, period="1y")
        tech_df, technicals = technical_summary(history)
        patterns = detect_chart_patterns(tech_df)
        sources = collect_price_histories(symbol, period="1y")
        fundamentals = get_fundamentals(symbol)
        tradingview = get_tradingview_summary(quote.symbol)
        ai = generate_ai_analysis(quote.__dict__, technicals, fundamentals, tradingview)
        return {
            "quote": quote.__dict__,
            "technicals": technicals,
            "patterns": patterns,
            "fundamentals": fundamentals,
            "tradingview": tradingview,
            "sources": {
                "status": sources["status"],
                "histories": [
                    {key: value for key, value in item.items() if key != "data"}
                    for item in sources["histories"]
                ],
            },
            "ai_analysis": ai,
        }
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/scanner/{scan_name}")
def scanner(scan_name: str) -> dict:
    normalized = scan_name.replace("-", " ").replace("_", " ").lower()
    key = next((name for name in SCAN_FUNCTIONS if name.replace("-", " ").lower() == normalized), scan_name)
    scan_fn = SCAN_FUNCTIONS.get(key)
    if not scan_fn:
        raise HTTPException(status_code=404, detail=f"Unknown scanner: {scan_name}")
    return {"scan": key, "results": scan_fn()}


@app.get("/universe/options")
def universe_options() -> list[str]:
    return segment_options()


@app.get("/universe/{segment}")
def universe(segment: str, limit: int = 100) -> dict:
    clean_segment = segment.replace("-", " ")
    return {"segment": clean_segment, "symbols": universe_for_segment(clean_segment, limit=limit)}


@app.get("/watchlist")
def get_watchlist() -> list[dict]:
    return list_watchlist()


@app.post("/watchlist/{symbol}")
def add_watchlist(symbol: str) -> dict:
    add_to_watchlist(symbol)
    return {"status": "added", "symbol": symbol.upper()}


@app.delete("/watchlist/{symbol}")
def delete_watchlist(symbol: str) -> dict:
    remove_from_watchlist(symbol)
    return {"status": "removed", "symbol": symbol.upper()}
