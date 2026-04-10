from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.config import MSTR_SHARES_OUTSTANDING
from app.services.sources import HoldingPoint, PricePoint


@dataclass(frozen=True)
class PremiumPoint:
    d: date
    mstr_close: float
    btc_usd: float
    btc_holdings: float
    nav_per_share: float
    premium_pct: float


def _as_map(points: list[PricePoint]) -> dict[date, float]:
    return {p.d: p.close for p in points}


def _step_holdings(holdings: list[HoldingPoint]) -> dict[date, float]:
    """
    Convert sparse purchase dates into a daily step function keyed by date.
    """
    holdings_sorted = sorted(holdings, key=lambda p: p.d)
    return {p.d: p.btc_total for p in holdings_sorted}


def compute_daily_premium_to_nav(
    *,
    mstr_prices: list[PricePoint],
    btc_prices: list[PricePoint],
    mstr_holdings: list[HoldingPoint],
    shares_outstanding: int = MSTR_SHARES_OUTSTANDING,
) -> list[PremiumPoint]:
    mstr_by_day = _as_map(mstr_prices)
    btc_by_day = _as_map(btc_prices)
    holdings_by_purchase_day = _step_holdings(mstr_holdings)

    if not mstr_by_day or not btc_by_day:
        return []

    start = max(min(mstr_by_day), min(btc_by_day))
    end = min(max(mstr_by_day), max(btc_by_day))
    if start > end:
        return []

    # Holdings are stepwise; carry forward last known value.
    purchase_days = sorted(holdings_by_purchase_day)
    last_holdings = None
    idx = 0

    out: list[PremiumPoint] = []
    d = start
    while d <= end:
        mstr = mstr_by_day.get(d)
        btc = btc_by_day.get(d)
        if mstr is None or btc is None:
            d += timedelta(days=1)
            continue

        while idx < len(purchase_days) and purchase_days[idx] <= d:
            last_holdings = holdings_by_purchase_day[purchase_days[idx]]
            idx += 1

        if last_holdings is None:
            d += timedelta(days=1)
            continue

        nav_per_share = (last_holdings * btc) / float(shares_outstanding)
        if nav_per_share <= 0:
            d += timedelta(days=1)
            continue

        premium_pct = ((mstr / nav_per_share) - 1.0) * 100.0

        out.append(
            PremiumPoint(
                d=d,
                mstr_close=mstr,
                btc_usd=btc,
                btc_holdings=last_holdings,
                nav_per_share=nav_per_share,
                premium_pct=premium_pct,
            )
        )
        d += timedelta(days=1)

    return out


def summarize(points: list[PremiumPoint], *, shares_outstanding: int = MSTR_SHARES_OUTSTANDING) -> dict:
    if not points:
        return {
            "latest": None,
            "delta_30d_pp": None,
            "min": None,
            "max": None,
        }

    latest = points[-1]
    min_p = min(points, key=lambda p: p.premium_pct)
    max_p = max(points, key=lambda p: p.premium_pct)

    delta_30d = None
    if len(points) >= 31:
        delta_30d = latest.premium_pct - points[-31].premium_pct

    return {
        "latest": {
            "date": latest.d.isoformat(),
            "premium_pct": latest.premium_pct,
            "mstr_close": latest.mstr_close,
            "btc_usd": latest.btc_usd,
            "btc_holdings": latest.btc_holdings,
            "nav_per_share": latest.nav_per_share,
        },
        "delta_30d_pp": delta_30d,
        "min": {"date": min_p.d.isoformat(), "premium_pct": min_p.premium_pct},
        "max": {"date": max_p.d.isoformat(), "premium_pct": max_p.premium_pct},
        "assumptions": {
            "shares_outstanding": shares_outstanding,
            "note": (
                "Premium-to-NAV is computed as (MSTR close / NAV per share - 1)*100, "
                "where NAV per share uses BTC holdings (stepwise from purchase history), "
                "BTC/USD daily prices, and a shares-outstanding assumption."
            ),
        },
    }
