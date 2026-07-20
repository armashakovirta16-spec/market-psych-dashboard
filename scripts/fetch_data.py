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


CYCLICAL_SECTORS = {"Tech (XLK)", "Financials (XLF)", "Energy (XLE)"}
DEFENSIVE_SECTORS = {"Healthcare (XLV)", "Utilities (XLU)"}

TILT_RISK_ON = 0.3
TILT_RISK_OFF = -0.3
VALUATION_CAVEAT = -0.5      # finance "valuation" component this negative = stretched vs. history
REAL_YIELD_ATTRACTIVE = -0.5  # economics "real_rate" component this negative = real yields historically high
GOLD_FEAR = -0.2             # psychology score this negative = fear-driven hedge demand
GOLD_INFLATION_CPI = 3.5     # CPI YoY % at/above this = inflation-hedge case for gold
SECTOR_MOMENTUM_NOTE = 3.0   # 1-month sector return %, for a descriptive note in a neutral regime


def compute_allocation_tilts(finance, economics, psychology, composite) -> dict:
    """
    Translates the composite/pillar scores into concrete overweight /
    neutral / underweight tilts per asset class and sector — illustrative
    starting points generated by a simple, named-threshold rule (same
    transparent-over-black-box approach as compute_composite()), not
    personalized investment advice for any individual's actual portfolio,
    mandate, or risk tolerance.
    """
    score = composite["score"]
    psychology_score = composite["pillar_scores"]["psychology"]
    components = composite.get("pillar_components", {})
    valuation = (components.get("finance") or {}).get("valuation")
    real_rate = (components.get("economics") or {}).get("real_rate")
    cpi = economics.get("cpi_yoy")

    asset_classes = {}

    # Equities: follows the composite regime directly, tempered by valuation.
    if score > TILT_RISK_ON:
        eq_tilt, eq_reason = "Overweight", f"Composite regime is Risk-On ({score:+.2f})."
    elif score < TILT_RISK_OFF:
        eq_tilt, eq_reason = "Underweight", f"Composite regime is Risk-Off ({score:+.2f})."
    else:
        eq_tilt, eq_reason = "Neutral", f"Composite regime is balanced ({score:+.2f})."
    if valuation is not None and valuation <= VALUATION_CAVEAT:
        if eq_tilt == "Overweight":
            eq_tilt = "Neutral"
            eq_reason += f" Downgraded from Overweight — valuations are stretched (valuation component {valuation:+.2f})."
        else:
            eq_reason += f" Valuations are also stretched (valuation component {valuation:+.2f}), a headwind if the regime turns."
    asset_classes["Equities"] = {"tilt": eq_tilt, "rationale": eq_reason}

    # Bonds: inverse of the equity call, upgraded if real yields look historically attractive.
    if score > TILT_RISK_ON:
        bd_tilt, bd_reason = "Underweight", f"Regime is Risk-On ({score:+.2f}); equities are favored over duration."
    elif score < TILT_RISK_OFF:
        bd_tilt, bd_reason = "Overweight", f"Regime is Risk-Off ({score:+.2f}); flight-to-quality demand typically firms up."
    else:
        bd_tilt, bd_reason = "Neutral", f"Composite regime is balanced ({score:+.2f})."
    if real_rate is not None and real_rate <= REAL_YIELD_ATTRACTIVE and bd_tilt != "Overweight":
        bd_tilt = "Overweight" if bd_tilt == "Neutral" else bd_tilt
        bd_reason += f" Real policy rates look historically high (real-rate component {real_rate:+.2f}), a supportive entry point for duration."
    asset_classes["Bonds"] = {"tilt": bd_tilt, "rationale": bd_reason}

    # Gold: a hedge call, driven by fear-leaning psychology or hot inflation — not the composite score.
    gold_reasons = []
    gold_tilt = "Neutral"
    if psychology_score <= GOLD_FEAR:
        gold_tilt = "Overweight"
        gold_reasons.append(f"psychology is fear-leaning ({psychology_score:+.2f}), typical of hedge demand for gold")
    if cpi is not None and cpi >= GOLD_INFLATION_CPI:
        gold_tilt = "Overweight"
        gold_reasons.append(f"CPI is running hot ({cpi:.1f}% YoY), an inflation-hedge case for gold")
    if gold_reasons:
        gold_reason = "; ".join(gold_reasons).capitalize() + "."
    else:
        gold_reason = f"No strong fear or inflation signal right now (psychology {psychology_score:+.2f}, CPI {cpi:.1f}% YoY)."
    asset_classes["Gold"] = {"tilt": gold_tilt, "rationale": gold_reason}

    # Sectors: cyclical vs. defensive tilt from the composite regime; in a
    # balanced regime, fall back to a descriptive (not predictive) momentum note.
    sector_tilts = {}
    for name, ret in finance.get("sector_returns_1m", {}).items():
        is_cyclical = name in CYCLICAL_SECTORS
        is_defensive = name in DEFENSIVE_SECTORS
        if score > TILT_RISK_ON and is_cyclical:
            tilt, reason = "Overweight", f"Cyclical sector, and the regime is Risk-On ({score:+.2f})."
        elif score < TILT_RISK_OFF and is_defensive:
            tilt, reason = "Overweight", f"Defensive sector, and the regime is Risk-Off ({score:+.2f})."
        elif score > TILT_RISK_ON and is_defensive:
            tilt, reason = "Underweight", f"Defensive sector in a Risk-On regime ({score:+.2f})."
        elif score < TILT_RISK_OFF and is_cyclical:
            tilt, reason = "Underweight", f"Cyclical sector in a Risk-Off regime ({score:+.2f})."
        else:
            tilt = "Neutral"
            if ret is not None and abs(ret) >= SECTOR_MOMENTUM_NOTE:
                direction = "positive" if ret > 0 else "negative"
                reason = f"Regime is balanced, but this sector has notable {direction} 1-month momentum ({ret:+.1f}%)."
            elif ret is not None:
                reason = f"Regime is balanced ({score:+.2f}) and this sector has no standout momentum ({ret:+.1f}%)."
            else:
                reason = f"Regime is balanced ({score:+.2f})."
        sector_tilts[name] = {"tilt": tilt, "rationale": reason}

    return {
        "disclaimer": (
            "Illustrative starting points generated from the scores above via simple, "
            "documented rules — not personalized investment advice. Apply your own "
            "judgment, mandate constraints, and risk tolerance."
        ),
        "asset_classes": asset_classes,
        "sectors": sector_tilts,
    }


NEUTRAL_BAND = 0.2  # |composite score| at or below this counts as "genuinely balanced"


def compute_strategies(composite, economics, allocation_tilts) -> list:
    """
    A small fixed menu of named, well-known strategy postures, each
    evaluated against the current composite/pillar scores with a simple
    documented rule. Deliberately not mutually exclusive — a PM can hold
    more than one tactical view at once (e.g. "stay neutral on net
    exposure, but trim winners because valuations are stretched"). Reuses
    the composite/pillar/tilt outputs already computed above rather than
    introducing parallel logic — this is a synthesis layer, not a new
    scoring model.
    """
    score = composite["score"]
    psychology_score = composite["pillar_scores"]["psychology"]
    components = composite.get("pillar_components", {})
    valuation = (components.get("finance") or {}).get("valuation")
    breadth = (components.get("finance") or {}).get("breadth")
    real_rate = (components.get("economics") or {}).get("real_rate")
    gold_tilt = (allocation_tilts.get("asset_classes", {}).get("Gold") or {}).get("tilt")

    strategies = []

    momentum_ok = score > 0.3 and (breadth or 0) > 0 and psychology_score < 0.5
    strategies.append({
        "name": "Broad equity risk-on / momentum continuation",
        "indicated": bool(momentum_ok),
        "rationale": (
            f"Composite is Risk-On ({score:+.2f}) with positive sector breadth and psychology not "
            f"already overheated ({psychology_score:+.2f}) — conditions support leaning into the trend."
            if momentum_ok else
            f"Composite ({score:+.2f}), breadth, or psychology ({psychology_score:+.2f}) isn't clearly "
            "confirming a Risk-On trend worth chasing right now."
        ),
    })

    defensive_ok = score < -0.2 or (valuation is not None and valuation <= -0.5 and psychology_score < 0)
    strategies.append({
        "name": "Quality / defensive rotation",
        "indicated": bool(defensive_ok),
        "rationale": (
            f"Composite is cautious ({score:+.2f}) and/or valuations are stretched with fear-leaning "
            f"psychology ({psychology_score:+.2f}) — a case for rotating toward quality and defensives."
            if defensive_ok else
            f"Composite ({score:+.2f}) and psychology ({psychology_score:+.2f}) aren't both flashing "
            "caution at once — no strong case for a defensive rotation yet."
        ),
    })

    barbell_ok = abs(score) <= NEUTRAL_BAND and real_rate is not None and real_rate <= -0.5
    strategies.append({
        "name": "Barbell: quality equities + duration",
        "indicated": bool(barbell_ok),
        "rationale": (
            f"Regime is genuinely balanced ({score:+.2f}) and real policy rates look historically "
            f"attractive (real-rate component {real_rate:+.2f}) — a case for pairing quality equity "
            "exposure with a duration add rather than picking a hard direction."
            if barbell_ok else
            "Either the regime isn't balanced enough or real yields aren't attractive enough to "
            "justify a barbell right now."
        ),
    })

    inflation_hedge_ok = gold_tilt == "Overweight"
    strategies.append({
        "name": "Inflation hedge / real-assets tilt",
        "indicated": bool(inflation_hedge_ok),
        "rationale": (
            "Gold is already flagged Overweight above (fear-leaning psychology and/or hot CPI) — "
            "the same signal supports a broader real-assets hedge."
            if inflation_hedge_ok else
            "Neither fear-leaning psychology nor hot CPI is showing up right now, so a real-assets "
            "hedge isn't specifically indicated."
        ),
    })

    trim_ok = valuation is not None and valuation <= -0.7 and score > -NEUTRAL_BAND
    strategies.append({
        "name": "Valuation-aware trim / raise cash on strength",
        "indicated": bool(trim_ok),
        "rationale": (
            f"Valuations are significantly stretched (valuation component {valuation:+.2f}) even "
            f"though the broader regime isn't bearish ({score:+.2f}) — a case for trimming winners "
            "into strength rather than adding new risk at these prices."
            if trim_ok else
            "Valuations aren't stretched enough, or the regime is already bearish, for this specific "
            "trim-on-strength case to apply."
        ),
    })

    neutral_ok = abs(score) <= NEUTRAL_BAND
    strategies.append({
        "name": "Stay neutral on net exposure",
        "indicated": bool(neutral_ok),
        "rationale": (
            f"The composite regime is genuinely balanced ({score:+.2f}) — no pillar is dominant enough "
            "to justify a strong directional tilt on overall market exposure."
            if neutral_ok else
            f"The composite regime ({score:+.2f}) is directional enough that staying purely neutral "
            "isn't the best fit right now."
        ),
    })

    return strategies


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
    allocation_tilts = compute_allocation_tilts(finance, economics, psychology, composite)
    strategies = compute_strategies(composite, economics, allocation_tilts)

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
        "allocation_tilts": allocation_tilts,
        "strategies": strategies,
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
