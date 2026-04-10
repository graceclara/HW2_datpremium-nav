from __future__ import annotations

import json

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette import status

from app.config import DEFAULT_DAYS, GEMINI_API_KEY, GEMINI_MODEL, MSTR_SHARES_OUTSTANDING
from app.services.premium_nav import compute_daily_premium_to_nav, summarize
from app.services.http_client import get_client
from app.services.sources import (
    HoldingPoint,
    fetch_btc_usd_daily,
    fetch_mstr_btc_holdings_history,
    fetch_alpha_vantage_daily_close,
)

app = FastAPI(title="DAT.co Indicator Dashboard - Premium to NAV")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


async def _generate_ai_summary(payload: dict) -> str:
    """
    Generate AI summary using Gemini API.
    Falls back to a rule-based summary if API key is missing or request fails.
    """
    summary = payload.get("summary", {}) or {}
    latest = summary.get("latest")
    delta_30d = summary.get("delta_30d_pp")

    # Fallback first (used if Gemini not available)
    if latest:
        base = (
            f"目前 Premium 為 {latest.get('premium_pct', 0):.2f}%，"
            f"近 30 天變化 {delta_30d:.2f}pp。"
            if delta_30d is not None
            else f"目前 Premium 為 {latest.get('premium_pct', 0):.2f}%。"
        )
    else:
        base = "目前資料不足，無法產生完整 Premium 趨勢分析。"

    if not GEMINI_API_KEY:
        return base + "（未設定 GEMINI_API_KEY，使用規則摘要）"

    prompt = (
        "你是金融分析助理。請根據以下 JSON，產生 3-4 句繁體中文摘要，"
        "需包含：目前 Premium 水平、近 30 天變化、可能與 BTC 的關聯。"
        "語氣中性、不要過度預測。\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with get_client() as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
        return text or base
    except Exception:
        return base + "（Gemini 暫時不可用，已使用規則摘要）"


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
            holdings = [HoldingPoint(d=btc[0].d, btc_total=766970.0)] if btc else []
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

    response_payload = {
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
    response_payload["ai_summary"] = await _generate_ai_summary(
        {"meta": response_payload["meta"], "summary": response_payload["summary"]}
    )
    return response_payload
