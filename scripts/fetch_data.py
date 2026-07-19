"""
Pulls live data for all three pillars (Finance, Economics, Psychology)
and writes it to data/snapshot.json for the frontend to consume.

Data sources:
  - Finance / Psychology (VIX, sector & asset ETFs): yfinance (no API key needed)
  - Economics (CPI, unemployment, rates): FRED API (needs a free API key)
  - S&P 500 P/E, ISM PMI, Cboe put/call ratio: scraped (no free API exists for
    any of these); each falls back to data/manual_overrides.json if the scrape
    fails, so a broken page never leaves the field silently null.
  - AAII sentiment: aaii.com blocks scrapers outright, so this one is manual
    only — update data/manual_overrides.json weekly from
    https://www.aaii.com/sentimentsurvey (released Thursdays).

Setup:
  pip install -r requirements.txt --break-system-packages
  Get a free FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
  Set it as an environment variable: export FRED_API_KEY=your_key_here
"""

import json
import os
import re
from datetime import datetime, timezone

import requests
import yfinance as yf
from fredapi import Fred

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "snapshot.json")
MANUAL_OVERRIDES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "manual_overrides.json")

# A browser UA avoids the bot-blocking a bare "python-requests" UA hits on some sites.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

SECTOR_ETFS = {
    "Tech (XLK)": "XLK",
    "Financials (XLF)": "XLF",
    "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV",
    "Utilities (XLU)": "XLU",
}

ASSET_CLASS_ETFS = {
    "Equities (SPY)": "SPY",
    "Bonds (AGG)": "AGG",
    "Gold (GLD)": "GLD",
}

FRED_SERIES = {
    "cpi_yoy": "CPIAUCSL",          # you'll want to transform this to YoY % change
    "unemployment_rate": "UNRATE",
    "fed_funds_rate": "FEDFUNDS",
    "yield_10y": "DGS10",
    "yield_2y": "DGS2",
}


def pct_change_1m(ticker: str) -> float:
    """Approximate 1-month percent return for a ticker via yfinance."""
    hist = yf.Ticker(ticker).history(period="1mo")
    if hist.empty or len(hist) < 2:
        return None
    start, end = hist["Close"].iloc[0], hist["Close"].iloc[-1]
    return round((end - start) / start * 100, 2)


def fetch_finance_and_psychology():
    sector_returns = {name: pct_change_1m(t) for name, t in SECTOR_ETFS.items()}
    asset_returns = {name: pct_change_1m(t) for name, t in ASSET_CLASS_ETFS.items()}

    vix_hist = yf.Ticker("^VIX").history(period="5d")
    vix = round(vix_hist["Close"].iloc[-1], 2) if not vix_hist.empty else None

    return {
        "sector_returns_1m": sector_returns,
        "asset_class_returns_1m": asset_returns,
    }, {
        "vix": vix,
    }


def load_manual_overrides() -> dict:
    with open(MANUAL_OVERRIDES_PATH) as f:
        return json.load(f)


def fetch_with_fallback(fetch_fn, fallback_value, label: str):
    """Try a live scrape; fall back to the manual_overrides.json value on any failure.

    Returns (value, source) where source is "scraped" or "manual_fallback" so the
    snapshot can be transparent about which numbers are live vs. stale-by-design.
    """
    try:
        value = fetch_fn()
        print(f"[{label}] scraped live value: {value}")
        return value, "scraped"
    except Exception as exc:
        print(f"[{label}] scrape failed ({exc}); using manual_overrides.json fallback: {fallback_value}")
        return fallback_value, "manual_fallback"


def fetch_sp500_pe() -> float:
    """Scrape multpl.com's meta description for the current trailing S&P 500 P/E.

    No free API exposes this for the index (Yahoo Finance only has it for
    individual tickers). multpl.com renders the current value directly into a
    static <meta name="description"> tag, so no JS execution is needed.
    """
    resp = requests.get("https://www.multpl.com/s-p-500-pe-ratio", headers=REQUEST_HEADERS, timeout=10)
    resp.raise_for_status()
    match = re.search(r"Current S&P 500 PE Ratio is ([\d.]+)", resp.text)
    if not match:
        raise ValueError("P/E value not found in multpl.com page — page structure may have changed")
    return float(match.group(1))


def fetch_put_call_ratio() -> float:
    """Scrape Cboe's daily market statistics page for the total put/call ratio.

    Cboe publishes this daily but not as a downloadable file; the current page
    (market-statistics/daily, not the old market_statistics/daily/ path, which
    redirects) renders the ratio into a plain HTML table.
    """
    resp = requests.get(
        "https://www.cboe.com/markets/us/options/market-statistics/daily",
        headers=REQUEST_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    match = re.search(r"TOTAL PUT/CALL RATIO</td><td[^>]*>([\d.]+)", resp.text)
    if not match:
        raise ValueError("Put/call ratio not found on Cboe page — page structure may have changed")
    return float(match.group(1))


def fetch_ism_pmi() -> float:
    """Scrape Trading Economics' business confidence page for the latest ISM Manufacturing PMI.

    ISM doesn't offer a free API and FRED doesn't carry ISM's series (licensing).
    Trading Economics renders the latest headline value into a static meta
    description, updated once a month when ISM releases.
    """
    resp = requests.get(
        "https://tradingeconomics.com/united-states/business-confidence",
        headers=REQUEST_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    match = re.search(r"to ([\d.]+) points in (\w+)", resp.text)
    if not match:
        raise ValueError("ISM PMI value not found on Trading Economics page — page structure may have changed")
    return float(match.group(1))


def fetch_economics(fred: Fred):
    unemployment = fred.get_series(FRED_SERIES["unemployment_rate"]).iloc[-1]
    fed_funds = fred.get_series(FRED_SERIES["fed_funds_rate"]).iloc[-1]
    y10 = fred.get_series(FRED_SERIES["yield_10y"]).dropna().iloc[-1]
    y2 = fred.get_series(FRED_SERIES["yield_2y"]).dropna().iloc[-1]

    cpi = fred.get_series(FRED_SERIES["cpi_yoy"])
    cpi_yoy = round((cpi.iloc[-1] / cpi.iloc[-13] - 1) * 100, 2) if len(cpi) > 13 else None

    return {
        "cpi_yoy": cpi_yoy,
        "unemployment_rate": round(float(unemployment), 2),
        "fed_funds_rate": round(float(fed_funds), 2),
        "yield_curve_10y_2y": round(float(y10 - y2), 2),
    }


def compute_composite(finance, economics, psychology) -> dict:
    """
    Placeholder scoring logic — replace with your own weighting once you've
    sanity-checked it with your professor. Keep it simple and explainable:
    a transparent rule beats a black-box model for a v1.
    """
    score = 0.0
    # Example rule: high VIX or wide bear/bull sentiment spread -> more cautious
    if psychology.get("vix"):
        score -= (psychology["vix"] - 18) * 0.01  # above 18 nudges cautious

    if economics.get("ism_pmi"):
        score += (economics["ism_pmi"] - 50) * 0.02  # below 50 = contraction, nudges cautious

    score = max(-1.0, min(1.0, round(score, 2)))

    if score > 0.3:
        regime = "Risk-On"
    elif score < -0.3:
        regime = "Risk-Off"
    else:
        regime = "Cautiously Neutral"

    return {
        "regime": regime,
        "score": score,
        "score_range": [-1, 1],
        "narrative": "Auto-generated placeholder narrative — refine this once your composite logic is finalized.",
    }


def main():
    fred_key = os.environ.get("FRED_API_KEY")
    if not fred_key:
        raise SystemExit(
            "Set FRED_API_KEY as an environment variable first. "
            "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
        )
    fred = Fred(api_key=fred_key)
    overrides = load_manual_overrides()

    finance, psychology = fetch_finance_and_psychology()
    economics = fetch_economics(fred)

    spx_pe, pe_source = fetch_with_fallback(fetch_sp500_pe, overrides.get("sp500_pe"), "sp500_pe")
    put_call, pc_source = fetch_with_fallback(fetch_put_call_ratio, overrides.get("put_call_ratio"), "put_call_ratio")
    ism_pmi, pmi_source = fetch_with_fallback(fetch_ism_pmi, overrides.get("ism_pmi"), "ism_pmi")

    economics["ism_pmi"] = ism_pmi
    finance["sp500_pe"] = spx_pe
    finance["yield_curve_10y_2y"] = economics.pop("yield_curve_10y_2y")

    psychology["put_call_ratio"] = put_call
    # AAII blocks scrapers outright, so this is manual-only — see data/manual_overrides.json.
    psychology["aaii_sentiment"] = overrides.get(
        "aaii_sentiment", {"bullish": None, "neutral": None, "bearish": None}
    )

    composite = compute_composite(finance, economics, psychology)

    snapshot = {
        "meta": {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "data_sources": {
                "sp500_pe": pe_source,
                "put_call_ratio": pc_source,
                "ism_pmi": pmi_source,
                "aaii_sentiment": "manual (data/manual_overrides.json)",
            },
        },
        "finance": finance,
        "economics": economics,
        "psychology": psychology,
        "composite": composite,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Wrote snapshot to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
