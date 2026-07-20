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
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "history.json")
MANUAL_OVERRIDES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "manual_overrides.json")
HISTORY_MAX_ENTRIES = 90  # keep ~3 months; a daily-cadence dashboard doesn't need more

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


HISTORICAL_AVG_PE = 16.5  # multpl.com's own long-run displayed mean for the S&P 500
NATURAL_UNEMPLOYMENT_ANCHOR = 4.2  # rough full-employment reference point

PILLAR_WEIGHTS = {"finance": 0.4, "economics": 0.3, "psychology": 0.3}

# Thresholds for the behavioral-bias callouts in the narrative — each is a
# compound or extreme condition, not just "any signal in one direction", so
# a callout only fires when positioning genuinely looks like that bias.
HERDING_AAII_SPREAD = 25          # |bullish - bearish| points
LOSS_AVERSION_PUT_CALL = 1.10     # put/call ratio
OVERCONFIDENCE_VIX_MAX = 15       # "complacent" volatility
OVERCONFIDENCE_PE_OVER_AVG = 5    # points above HISTORICAL_AVG_PE


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def _finance_pillar(finance):
    """
    Three equally-weighted, explainable signals:
      - Yield curve (10y-2y): steep/positive reads as healthy growth
        expectations; inverted is the textbook recession warning.
      - Valuation: S&P 500 P/E vs. its long-run historical mean — expensive
        relative to history nudges cautious (less margin of safety), cheap
        relative to history nudges supportive.
      - Breadth: share of the 5 tracked sector ETFs with positive 1-month
        returns — broad-based moves are a simple momentum confirmation.
    """
    parts = {}

    yc = finance.get("yield_curve_10y_2y")
    if yc is not None:
        parts["yield_curve"] = round(_clamp(yc / 1.5), 3)

    pe = finance.get("sp500_pe")
    if pe is not None:
        parts["valuation"] = round(_clamp((HISTORICAL_AVG_PE - pe) / 10), 3)

    sector_returns = [v for v in finance.get("sector_returns_1m", {}).values() if v is not None]
    if sector_returns:
        positive_share = sum(1 for r in sector_returns if r > 0) / len(sector_returns)
        parts["breadth"] = round(_clamp(positive_share * 2 - 1), 3)

    score = round(sum(parts.values()) / len(parts), 3) if parts else 0.0
    return score, parts


def _economics_pillar(economics):
    """
      - ISM PMI vs. the 50 expansion/contraction line.
      - Real policy rate (Fed funds - CPI YoY): restrictive (positive) is a
        headwind, accommodative (negative) is a tailwind.
      - Unemployment vs. a rough full-employment anchor — half-weighted,
        since the "right" direction here is genuinely ambiguous (very low
        unemployment can mean late-cycle overheating as easily as healthy
        growth); included for completeness, not leaned on hard.
    """
    parts = {}

    pmi = economics.get("ism_pmi")
    if pmi is not None:
        parts["pmi"] = round(_clamp((pmi - 50) / 10), 3)

    cpi, fed_funds = economics.get("cpi_yoy"), economics.get("fed_funds_rate")
    if cpi is not None and fed_funds is not None:
        parts["real_rate"] = round(_clamp((cpi - fed_funds) / 3), 3)

    unemployment = economics.get("unemployment_rate")
    if unemployment is not None:
        parts["unemployment"] = round(_clamp((NATURAL_UNEMPLOYMENT_ANCHOR - unemployment) / 2) * 0.5, 3)

    score = round(sum(parts.values()) / len(parts), 3) if parts else 0.0
    return score, parts


def _psychology_pillar(psychology):
    """
    Doubles as the dashboard's fear/greed-style index for the Psychology
    pillar: low VIX, call-heavy put/call, and net-bullish AAII all read as
    "greed"; the inverse of each reads as "fear".
    """
    parts = {}

    vix = psychology.get("vix")
    if vix is not None:
        parts["vix"] = round(_clamp((22 - vix) / 12), 3)

    pc = psychology.get("put_call_ratio")
    if pc is not None:
        parts["put_call"] = round(_clamp((1.0 - pc) / 0.35), 3)

    aaii = psychology.get("aaii_sentiment") or {}
    bullish, bearish = aaii.get("bullish"), aaii.get("bearish")
    if bullish is not None and bearish is not None:
        parts["aaii_spread"] = round(_clamp((bullish - bearish) / 40), 3)

    score = round(sum(parts.values()) / len(parts), 3) if parts else 0.0
    return score, parts


def _describe(score, positive_word, negative_word):
    if score > 0.15:
        return positive_word
    if score < -0.15:
        return negative_word
    return "roughly balanced"


def _bias_callouts(finance, psychology):
    """
    Only ever asserts a bias if the data actually clears that bias's
    threshold — a quiet market doesn't get a herding/overconfidence label
    just because the code has one available.
    """
    callouts = []

    aaii = psychology.get("aaii_sentiment") or {}
    bullish, bearish = aaii.get("bullish"), aaii.get("bearish")
    if bullish is not None and bearish is not None and abs(bullish - bearish) >= HERDING_AAII_SPREAD:
        lean = "bullish" if bullish > bearish else "bearish"
        callouts.append(
            f"AAII sentiment is heavily {lean} ({bullish:.1f}% bullish vs. {bearish:.1f}% bearish, a "
            f"{abs(bullish - bearish):.1f}-point spread) — a one-sided read that looks more like herding "
            "into a single narrative than a balanced market."
        )

    put_call = psychology.get("put_call_ratio")
    if put_call is not None and put_call >= LOSS_AVERSION_PUT_CALL:
        callouts.append(
            f"The put/call ratio at {put_call:.2f} shows investors paying up for downside protection — "
            "a classic loss-aversion signature, where avoiding a loss is being weighted more heavily than "
            "capturing further gains."
        )

    vix, pe = psychology.get("vix"), finance.get("sp500_pe")
    if vix is not None and pe is not None and vix <= OVERCONFIDENCE_VIX_MAX and pe >= HISTORICAL_AVG_PE + OVERCONFIDENCE_PE_OVER_AVG:
        callouts.append(
            f"Volatility this low (VIX {vix:.1f}) alongside valuations well above their historical average "
            f"(P/E {pe:.1f} vs. a ~{HISTORICAL_AVG_PE} long-run mean) suggests overconfidence — positioning "
            "priced for calm markets to keep going, with little cushion if that assumption breaks."
        )

    if not callouts:
        callouts.append(
            "No single extreme-positioning signal (herding, loss-aversion-driven hedging, or overconfidence) "
            "is flashing right now — sentiment, hedging demand, and volatility all look within a normal range."
        )

    return callouts


def compute_composite(finance, economics, psychology) -> dict:
    """
    Transparent, additive scoring: each pillar averages a handful of
    explainable -1..+1 signals (documented above each helper), then the
    three pillar scores are combined with fixed, documented weights
    (PILLAR_WEIGHTS). Not predictive or rigorous by design — the goal is a
    genuinely useful, inspectable first pass, not a black-box model.
    """
    finance_score, finance_parts = _finance_pillar(finance)
    economics_score, economics_parts = _economics_pillar(economics)
    psychology_score, psychology_parts = _psychology_pillar(psychology)

    score = round(
        finance_score * PILLAR_WEIGHTS["finance"]
        + economics_score * PILLAR_WEIGHTS["economics"]
        + psychology_score * PILLAR_WEIGHTS["psychology"],
        3,
    )
    score = _clamp(score)

    if score > 0.3:
        regime = "Risk-On"
    elif score < -0.3:
        regime = "Risk-Off"
    else:
        regime = "Cautiously Neutral"

    overview = (
        f"Regime read: {regime} (composite score {score:+.2f} on a -1 to +1 scale). Finance conditions are "
        f"{_describe(finance_score, 'supportive', 'cautious')} ({finance_score:+.2f}), economic data is "
        f"{_describe(economics_score, 'supportive', 'cautious')} ({economics_score:+.2f}), and market "
        f"psychology leans {_describe(psychology_score, 'greedy', 'fearful')} ({psychology_score:+.2f})."
    )

    detail = (
        f"Finance: the yield curve is {'inverted' if finance.get('yield_curve_10y_2y', 0) < 0 else 'positively sloped'} "
        f"({finance.get('yield_curve_10y_2y', 0):+.2f}pp), the S&P 500 trades at {finance.get('sp500_pe', 0):.1f}x "
        f"earnings against a ~{HISTORICAL_AVG_PE}x historical average, and "
        f"{sum(1 for r in finance.get('sector_returns_1m', {}).values() if (r or 0) > 0)} of "
        f"{len(finance.get('sector_returns_1m', {}))} tracked sectors are positive over the past month. "
        f"Economics: ISM PMI is at {economics.get('ism_pmi', 0):.1f} "
        f"({'expansion' if (economics.get('ism_pmi') or 0) >= 50 else 'contraction'}), CPI is running "
        f"{economics.get('cpi_yoy', 0):.1f}% YoY against a {economics.get('fed_funds_rate', 0):.2f}% Fed funds rate, "
        f"and unemployment sits at {economics.get('unemployment_rate', 0):.1f}%."
    )

    bias_paragraph = " ".join(_bias_callouts(finance, psychology))

    return {
        "regime": regime,
        "score": score,
        "score_range": [-1, 1],
        "pillar_scores": {
            "finance": finance_score,
            "economics": economics_score,
            "psychology": psychology_score,
        },
        "pillar_components": {
            "finance": finance_parts,
            "economics": economics_parts,
            "psychology": psychology_parts,
        },
        "narrative": [overview, detail, bias_paragraph],
    }


def load_history() -> dict:
    try:
        with open(HISTORY_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"entries": []}


def append_history_entry(history: dict, snapshot: dict) -> dict:
    """
    Records one point per calendar day (UTC) so the frontend can show a
    trend, not just a snapshot. Re-running on the same day updates that
    day's entry in place rather than adding a duplicate — a manual re-run
    or a retried Action shouldn't inflate the trend with same-day noise.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    entry = {
        "date": today,
        "composite_score": snapshot["composite"]["score"],
        "pillar_scores": snapshot["composite"]["pillar_scores"],
        "vix": snapshot["psychology"].get("vix"),
        "sp500_pe": snapshot["finance"].get("sp500_pe"),
        "ism_pmi": snapshot["economics"].get("ism_pmi"),
        "put_call_ratio": snapshot["psychology"].get("put_call_ratio"),
    }

    entries = [e for e in history.get("entries", []) if e.get("date") != today]
    entries.append(entry)
    entries.sort(key=lambda e: e["date"])
    entries = entries[-HISTORY_MAX_ENTRIES:]

    return {"entries": entries}


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

    history = append_history_entry(load_history(), snapshot)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)
    print(f"Wrote {len(history['entries'])}-entry history to {HISTORY_PATH}")


if __name__ == "__main__":
    main()
