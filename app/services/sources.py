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
    url = COINGECKO_BTC_DAILY_URL.format(days=days)
    async with get_client() as client:
        r = await client.get(url)
        r.raise_for_status()
        payload = r.json()

    # CoinGecko: prices = [[ms_since_epoch, price], ...]
    out: dict[date, float] = {}
    for ms, price in payload.get("prices", []):
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date()
        out[dt] = float(price)

    return [PricePoint(d=k, close=v) for k, v in sorted(out.items(), key=lambda kv: kv[0])]


def _normalize_equity_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    # accept common variants from UI like "mstr.us"
    if s.endswith(".US"):
        s = s[:-3]
    return s


async def fetch_alpha_vantage_daily_close(symbol: str) -> list[PricePoint]:
    """
    Fetch daily close prices via AlphaVantage.
    Requires env `ALPHAVANTAGE_API_KEY`.
    """
    if not ALPHAVANTAGE_API_KEY:
        raise RuntimeError("Missing ALPHAVANTAGE_API_KEY. Set it in your environment for equity price data.")

    sym = _normalize_equity_symbol(symbol)
    url = ALPHAVANTAGE_DAILY_URL.format(symbol=sym, apikey=ALPHAVANTAGE_API_KEY)
    async with get_client() as client:
        r = await client.get(url)
        r.raise_for_status()
        payload = r.json()

    # AlphaVantage error/limit messages
    if "Error Message" in payload:
        raise RuntimeError(payload["Error Message"])
    if "Note" in payload:
        raise RuntimeError(payload["Note"])
    if "Information" in payload:
        raise RuntimeError(payload["Information"])

    ts = payload.get("Time Series (Daily)", {})
    out: list[PricePoint] = []
    for k, v in ts.items():
        try:
            d = date_parser.parse(k).date()
            close = float(v.get("4. close"))
        except Exception:
            continue
        out.append(PricePoint(d=d, close=close))

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

    # Normalize: keep one point per date (last one wins), sort ascending
    out = sorted(points.values(), key=lambda p: p.d)
    return out
