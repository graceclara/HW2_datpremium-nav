import os


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


MSTR_SHARES_OUTSTANDING = _int_env("MSTR_SHARES_OUTSTANDING", 17_500_000)
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()

# Data sources
COINGECKO_BTC_DAILY_URL = (
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    "?vs_currency=usd&days={days}&interval=daily"
)
ALPHAVANTAGE_DAILY_URL = (
    "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED"
    "&symbol={symbol}&outputsize=full&apikey={apikey}"
)
MSTR_PURCHASE_HISTORY_URL = "https://buybitcoinworldwide.com/microstrategy-statistics/"

# Default range
DEFAULT_DAYS = _int_env("DEFAULT_DAYS", 365)
