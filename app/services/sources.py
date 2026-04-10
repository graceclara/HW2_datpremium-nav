from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from app.config import (
    ALPHAVANTAGE_API_KEY,
    ALPHAVANTAGE_DAILY_URL,
    COINGECKO_BTC_DAILY_URL,
    MSTR_PURCHASE_HISTORY_URL,
)
from app.services.http_client import get_client


@dataclass(frozen=True)
class PricePoint:
    d: date
    close: float


@dataclass(frozen=True)
class HoldingPoint:
    d: date
    btc_total: float


async def fetch_btc_usd_daily(days: int) -> list[PricePoint]:
    """
    Primary: CoinGecko daily BTC/USD
    Fallback: Yahoo Finance BTC-USD daily
    """
    url = COINGECKO_BTC_DAILY_URL.format(days=days)
    try:
        async with get_client() as client:
            r = await client.get(url)
            r.raise_for_status()
            payload = r.json()

        out: dict[date, float] = {}
        for ms, price in payload.get("prices", []):
            dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date()
            out[dt] = float(price)

        return [PricePoint(d=k, close=v) for k, v in sorted(out.items(), key=lambda kv: kv[0])]
    except Exception:
        yurl = "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?range=2y&interval=1d"
        async with get_client() as client:
            r = await client.get(yurl)
            r.raise_for_status()
            payload = r.json()

        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not result:
            return []

        timestamps = result.get("timestamp") or []
        closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])

        out: list[PricePoint] = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            out.append(PricePoint(d=d, close=float(close)))

        out.sort(key=lambda p: p.d)
        return out


def _normalize_equity_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith(".US"):
        s = s[:-3]
    return s


async def fetch_alpha_vantage_daily_close(symbol: str) -> list[PricePoint]:
    """
    Fetch daily close prices via Yahoo Finance chart API (free, no API key).
    Kept function name unchanged so callers do not need updates.
    """
    sym = _normalize_equity_symbol(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"

    async with get_client() as client:
        r = await client.get(url)
        r.raise_for_status()
        payload = r.json()

    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        return []

    timestamps = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])

    out: list[PricePoint] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        out.append(PricePoint(d=d, close=float(close)))

    out.sort(key=lambda p: p.d)
    return out


def _parse_purchase_history_table_rows(tds: Iterable[str]) -> HoldingPoint | None:
    # Expected cells: Date | BTC Purchased | Amount | Total Bitcoin | Total Dollars
    cells = [c.strip() for c in tds]
    if len(cells) < 5:
        return None
    raw_date, _, _, raw_total_btc, _ = cells[:5]
    if raw_date.lower() in ("date", ""):
        return None
    try:
        d = date_parser.parse(raw_date, dayfirst=False, yearfirst=False).date()
    except Exception:
        return None
    raw_total_btc = raw_total_btc.replace(",", "")
    try:
        total_btc = float(raw_total_btc)
    except ValueError:
        return None
    return HoldingPoint(d=d, btc_total=total_btc)


async def fetch_mstr_btc_holdings_history() -> list[HoldingPoint]:
    """
    Returns a step-series anchor points of MSTR total BTC holdings.

    Source: BuyBitcoinWorldwide (MicroStrategy/Strategy statistics page), using their
    "MicroStrategy Bitcoin Purchase History" table which includes Total Bitcoin.
    """
    async with get_client() as client:
        r = await client.get(MSTR_PURCHASE_HISTORY_URL)
        r.raise_for_status()
        html = r.text

    soup = BeautifulSoup(html, "html.parser")

    # Pick the first table whose first row includes "Total Bitcoin".
    target_table = None
    for tbl in soup.find_all("table"):
        first = tbl.find("tr")
        if first is None:
            continue
        cells = [c.get_text(" ", strip=True).lower() for c in first.find_all(["td", "th"])]
        if any("total bitcoin" in c for c in cells):
            target_table = tbl
            break

    if target_table is None:
        return []

    points: dict[date, HoldingPoint] = {}
    for tr in target_table.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        hp = _parse_purchase_history_table_rows(tds)
        if hp is None:
            continue
        points[hp.d] = hp

    out = sorted(points.values(), key=lambda p: p.d)
    return out
