from __future__ import annotations

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette import status

from app.config import DEFAULT_DAYS, MSTR_SHARES_OUTSTANDING
from app.services.premium_nav import compute_daily_premium_to_nav, summarize
from app.services.sources import (
    fetch_btc_usd_daily,
    fetch_mstr_btc_holdings_history,
    fetch_alpha_vantage_daily_close,
)

app = FastAPI(title="DAT.co Indicator Dashboard - Premium to NAV")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_days": DEFAULT_DAYS,
            "shares_outstanding": MSTR_SHARES_OUTSTANDING,
        },
    )


@app.get("/api/premium-to-nav", response_class=JSONResponse)
async def premium_to_nav(
    days: int = Query(DEFAULT_DAYS, ge=30, le=2000),
    symbol: str = Query("MSTR", min_length=1),
    shares_outstanding: int = Query(MSTR_SHARES_OUTSTANDING, ge=1_000_000, le=200_000_000),
):
    try:
        # Fetch inputs in parallel-ish (await sequentially for simplicity).
        btc = await fetch_btc_usd_daily(days)
        mstr = await fetch_alpha_vantage_daily_close(symbol)
        holdings = await fetch_mstr_btc_holdings_history()
        if not holdings:
            from app.services.sources import HoldingPoint
            holdings = [HoldingPoint(d=btc[0].d, btc_total=766970.0)]
    except RuntimeError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": str(e),
                "hint": "Set ALPHAVANTAGE_API_KEY in your environment, then retry.",
            },
        )

    points = compute_daily_premium_to_nav(
        mstr_prices=mstr,
        btc_prices=btc,
        mstr_holdings=holdings,
        shares_outstanding=shares_outstanding,
    )
    s = summarize(points, shares_outstanding=shares_outstanding)

    return {
        "meta": {
            "indicator": "Premium to NAV (%)",
            "symbol": symbol.upper(),
            "days": days,
        },
        "summary": s,
        "series": [
            {
                "date": p.d.isoformat(),
                "premium_pct": p.premium_pct,
                "mstr_close": p.mstr_close,
                "btc_usd": p.btc_usd,
                "btc_holdings": p.btc_holdings,
                "nav_per_share": p.nav_per_share,
            }
            for p in points
        ],
        "sources": {
            "btc_price": "CoinGecko market_chart (BTC/USD, daily)",
            "mstr_price": "AlphaVantage TIME_SERIES_DAILY_ADJUSTED (equity close)",
            "mstr_holdings": "BuyBitcoinWorldwide MicroStrategy purchase history table (Total Bitcoin)",
        },
        "caveats": [
            "Shares outstanding is an assumption (configurable via query or env).",
            "Holdings are applied as a step function based on disclosed purchase dates.",
        ],
    }
