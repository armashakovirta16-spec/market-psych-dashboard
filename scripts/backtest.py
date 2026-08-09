"""
Item 4 from Will's memo: does an extreme fundamentals-vs-psychology gap
predict abnormal forward S&P 500 returns, and does the adaptive 15-55%
psychology weight actually add value over a static 35%?

Reconstructs the composite score daily back to 1999-01-04 (bounded by the
sector ETFs' 1998-12-22 inception — see backtest_fetch.py / memory/
backtest_data_availability.md for why not further back) using EXPANDING-
WINDOW z-score references (no look-ahead) instead of fetch_data.py's fixed
approximations, per Will's explicit ask. Two real data gaps mean some
proxies are simply unavailable for parts of the window — handled the same
way the live pillars already handle a missing proxy (excluded from that
day's average, not treated as zero) rather than faked:
  - ISM PMI: no free historical source exists at all (see memory) — the
    Economics pillar here runs on real_rate + unemployment only, for the
    ENTIRE backtest, and cycle_stage is always "Unknown" as a result (PMI
    is required to classify it), so the VIX cycle-stage adjustment never
    activates historically either.
  - HY OAS: FRED's free history only starts 2023-07-28.
  - Put/call ratio: free bulk downloads only cover 2003-10-17 to 2019-10-04
    (a real gap discovered while fetching, not anticipated going in) —
    excluded 2019-2026 despite the live daily scraper working fine today.

Caveats documented in the final report, not silently smoothed over:
  - Monthly/weekly series (CPI, unemployment, fed funds, consumer
    sentiment, AAII, NAAIM, P/E) are forward-filled from their own release
    date with a simple assumed publication lag, not exact historical
    release-calendar dates.
  - Uses CURRENT-vintage FRED data (today's revised CPI/unemployment
    figures), not real-time-as-then vintages — a known, unresolved
    look-ahead source for those two series specifically (ALFRED vintage
    data would fix this; out of scope here).
  - Expanding-window stats use each date's own value inclusively; a
    stricter no-look-ahead convention would exclude same-day and is a
    one-line change (`.shift(1)` before `.shift(0)`) if wanted later.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, os.path.dirname(__file__))
import fetch_data as fd  # reuse _clamp/_zscore_to_unit and the fixed-anchor constants that are staying fixed

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "backtest_raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
START_DATE = "1999-01-04"  # first trading day after all 5 sector ETFs have inception data


def _load(name, value_col, date_col="date"):
    df = pd.read_csv(os.path.join(RAW_DIR, f"{name}.csv"), parse_dates=[date_col])
    return df.set_index(date_col)[value_col].sort_index()


def _asof_align(series, grid_index, max_staleness_days=None):
    """Forward-fill `series` onto `grid_index` using only same-or-earlier
    values (merge_asof backward) — the standard no-look-ahead alignment for
    mixing daily/weekly/monthly series onto one daily grid."""
    s = series.sort_index()
    left = pd.DataFrame({"date": grid_index})
    right = pd.DataFrame({"date": s.index, "value": s.values})
    merged = pd.merge_asof(left, right, on="date", direction="backward")
    if max_staleness_days is not None:
        # Guard against forward-filling a since-discontinued series forever
        # (e.g. put/call's 2019-2026 gap) rather than silently pretending
        # a 7-year-old reading is still "current."
        idx = np.searchsorted(s.index.values, grid_index.values, side="right") - 1
        staleness = np.full(len(grid_index), np.nan)
        valid = idx >= 0
        staleness[valid] = (grid_index.values[valid] - s.index.values[idx[valid]]) / np.timedelta64(1, "D")
        merged.loc[staleness > max_staleness_days, "value"] = np.nan
    return pd.Series(merged["value"].values, index=grid_index)


def expanding_zscore(series, min_periods=52):
    """Expanding-window z-score: at each date, standardize against the
    mean/std of all *prior* values only (shift(1) before computing today's
    z so today's own reading can't bleed into its own reference) — this is
    the concrete fix for Will's "no look-ahead... replaces the current
    approximation-based reference values" ask, replacing fetch_data.py's
    fixed VIX_LONG_RUN_MEAN-style constants for the historical
    reconstruction specifically (the live daily pipeline keeps the fixed
    constants; recomputing them fresh on every Actions run would make the
    live regime read wobble as the expanding window grows, which isn't
    what a stable daily signal should do)."""
    prior_mean = series.shift(1).expanding(min_periods=min_periods).mean()
    prior_std = series.shift(1).expanding(min_periods=min_periods).std()
    z = (series - prior_mean) / prior_std
    return z


def build_grid():
    spy = _load("etf_SPY", "close")
    grid = spy.index[(spy.index >= START_DATE)]
    return grid, spy.reindex(grid)


def build_finance(grid):
    etfs = {name: _load(f"etf_{t}", "close") for name, t in
            [("Tech (XLK)", "XLK"), ("Financials (XLF)", "XLF"), ("Energy (XLE)", "XLE"),
             ("Healthcare (XLV)", "XLV"), ("Utilities (XLU)", "XLU")]}
    sector_returns_1m = {}
    for name, series in etfs.items():
        aligned = series.reindex(series.index.union(grid)).sort_index().ffill().reindex(grid)
        ret_21d = aligned.pct_change(21) * 100
        sector_returns_1m[name] = ret_21d

    dgs10 = _asof_align(_load("fred_dgs10", "value"), grid)
    dgs2 = _asof_align(_load("fred_dgs2", "value"), grid)
    yield_curve = dgs10 - dgs2

    pe_monthly = _load("sp500_pe_monthly", "pe")
    pe = _asof_align(pe_monthly, grid, max_staleness_days=45)
    earnings_yield = 100 / pe

    # Both z-scored against their own expanding (no-look-ahead) history,
    # same method as every Psychology proxy below — replaces a fixed
    # +/-1.5pp yield-curve clamp and a fixed-vs-1871-average P/E clamp,
    # both of which pinned their component at an extreme on ~1/3 of all
    # days regardless of actual conditions (see fetch_data.py's
    # EARNINGS_YIELD_LONG_RUN_MEAN / YIELD_CURVE_LONG_RUN_MEAN comments for
    # the full writeup — this was a real, verified bug, not a style choice).
    # Earnings yield (not raw P/E) avoids the triple-digit P/E distortion
    # when earnings collapse near zero (e.g. 2008-09).
    parts = pd.DataFrame(index=grid)
    parts["yield_curve"] = expanding_zscore(yield_curve).clip(-2.5, 2.5) / 2.5
    parts["valuation"] = expanding_zscore(earnings_yield).clip(-2.5, 2.5) / 2.5

    sector_df = pd.DataFrame(sector_returns_1m)
    positive_share = (sector_df > 0).sum(axis=1) / sector_df.notna().sum(axis=1).replace(0, np.nan)
    parts["breadth"] = (positive_share * 2 - 1).clip(-1, 1)

    score = parts.mean(axis=1, skipna=True)
    return score, parts, pe


def build_economics(grid):
    """PMI is never available historically (see module docstring) — this
    pillar runs on real_rate + unemployment only for the entire backtest,
    a real reduction from the live pillar's 3 components to 2."""
    cpi = _asof_align(_load("fred_cpi", "value"), grid, max_staleness_days=60)
    cpi_yoy = (cpi / cpi.shift(365) - 1) * 100  # ~365 calendar days on a daily-reindexed series
    fed_funds = _asof_align(_load("fred_fedfunds", "value"), grid, max_staleness_days=60)
    unemployment = _asof_align(_load("fred_unemployment", "value"), grid, max_staleness_days=60)

    parts = pd.DataFrame(index=grid)
    parts["real_rate"] = ((cpi_yoy - fed_funds) / 3).clip(-1, 1)
    parts["unemployment"] = (((fd.NATURAL_UNEMPLOYMENT_ANCHOR - unemployment) / 2) * 0.5).clip(-1, 1)

    score = parts.mean(axis=1, skipna=True)
    return score, parts, cpi_yoy


def build_psychology(grid):
    vix = _asof_align(_load("vix_historical", "close"), grid, max_staleness_days=10)
    put_call = _asof_align(_load("put_call_historical", "total_pc"), grid, max_staleness_days=10)
    consumer_sentiment = _asof_align(_load("fred_consumer_sentiment", "value"), grid, max_staleness_days=45)
    hy_oas = _asof_align(_load("fred_hy_oas", "value"), grid, max_staleness_days=10)
    news_sentiment = _asof_align(_load("news_sentiment_historical", "value"), grid, max_staleness_days=10)
    naaim = _asof_align(_load("naaim_historical", "naaim_number"), grid, max_staleness_days=14)

    aaii = pd.read_csv(os.path.join(RAW_DIR, "aaii_historical.csv"), parse_dates=["date"]).set_index("date")
    aaii_spread_raw = (aaii["bullish"] - aaii["bearish"]) * (100 if aaii["bullish"].max() <= 1.5 else 1)
    aaii_spread = _asof_align(aaii_spread_raw.sort_index(), grid, max_staleness_days=14)

    parts = pd.DataFrame(index=grid)
    parts["vix"] = (-expanding_zscore(vix)).clip(-2.5, 2.5) / 2.5
    parts["put_call"] = (-expanding_zscore(put_call)).clip(-2.5, 2.5) / 2.5
    parts["aaii_spread"] = expanding_zscore(aaii_spread).clip(-2.5, 2.5) / 2.5
    parts["consumer_sentiment"] = expanding_zscore(consumer_sentiment).clip(-2.5, 2.5) / 2.5
    parts["hy_oas"] = (-expanding_zscore(hy_oas)).clip(-2.5, 2.5) / 2.5
    parts["news_sentiment"] = expanding_zscore(news_sentiment).clip(-2.5, 2.5) / 2.5
    parts["naaim_exposure"] = expanding_zscore(naaim).clip(-2.5, 2.5) / 2.5

    score = parts.mean(axis=1, skipna=True)
    return score, parts


def build_composite(finance_score, economics_score, psychology_score):
    fw, ew = fd.PILLAR_WEIGHTS["finance"], fd.PILLAR_WEIGHTS["economics"]
    baseline = (finance_score * fw + economics_score * ew) / (fw + ew)

    psychology_extremity = psychology_score.abs().clip(upper=1.0)
    adaptive_weight = fd.MIN_PSYCHOLOGY_WEIGHT + (fd.MAX_PSYCHOLOGY_WEIGHT - fd.MIN_PSYCHOLOGY_WEIGHT) * psychology_extremity
    adaptive_composite = (baseline * (1 - adaptive_weight) + psychology_score * adaptive_weight).clip(-1, 1)

    fixed_weight = 0.35
    fixed_composite = (baseline * (1 - fixed_weight) + psychology_score * fixed_weight).clip(-1, 1)

    gap = adaptive_composite - baseline
    return baseline, adaptive_weight, adaptive_composite, fixed_composite, gap


def forward_returns(spy, horizons_trading_days):
    out = {}
    for label, n in horizons_trading_days.items():
        out[label] = spy.shift(-n) / spy - 1
    return pd.DataFrame(out)


def decile_table(signal, fwd_returns, label):
    df = pd.DataFrame({"signal": signal}).join(fwd_returns).dropna(subset=["signal"])
    df["decile"] = pd.qcut(df["signal"], 10, labels=False, duplicates="drop")
    table = df.groupby("decile")[fwd_returns.columns].mean().mul(100).round(3)
    table["n"] = df.groupby("decile").size()
    return table


def newey_west_regression(signal, fwd_return, lag):
    df = pd.DataFrame({"x": signal, "y": fwd_return}).dropna()
    X = sm.add_constant(df["x"])
    model = sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": lag})
    return {
        "n": int(model.nobs),
        "beta": round(float(model.params["x"]), 5),
        "beta_tstat": round(float(model.tvalues["x"]), 3),
        "beta_pvalue": round(float(model.pvalues["x"]), 4),
        "r_squared": round(float(model.rsquared), 4),
        "newey_west_lag": lag,
    }


def main():
    print("Building master daily grid from SPY...")
    grid, spy = build_grid()
    print(f"Grid: {grid[0].date()} to {grid[-1].date()}, {len(grid)} trading days")

    print("Building Finance pillar...")
    finance_score, finance_parts, pe = build_finance(grid)
    print("Building Economics pillar (PMI unavailable historically — see module docstring)...")
    economics_score, economics_parts, cpi_yoy = build_economics(grid)
    print("Building Psychology pillar (expanding-window z-scores)...")
    psychology_score, psychology_parts = build_psychology(grid)

    print("Building composite (adaptive vs. fixed-35% weight)...")
    baseline, adaptive_weight, adaptive_composite, fixed_composite, gap = build_composite(
        finance_score, economics_score, psychology_score
    )

    print("Computing forward returns...")
    horizons = {"fwd_1m": 21, "fwd_3m": 63, "fwd_6m": 126}
    fwd = forward_returns(spy, horizons)

    results = {"meta": {
        "start_date": str(grid[0].date()),
        "end_date": str(grid[-1].date()),
        "n_trading_days": len(grid),
        "note": "Reconstructed historical series — see script docstring and the final report for data-availability caveats.",
    }}

    print("Event study: gap (adaptive composite - baseline) deciles...")
    results["gap_deciles"] = decile_table(gap, fwd, "gap").reset_index().to_dict(orient="records")
    print("Event study: adaptive composite score deciles...")
    results["adaptive_composite_deciles"] = decile_table(adaptive_composite, fwd, "adaptive").reset_index().to_dict(orient="records")
    print("Event study: fixed-35%-weight composite deciles...")
    results["fixed_composite_deciles"] = decile_table(fixed_composite, fwd, "fixed").reset_index().to_dict(orient="records")

    print("Newey-West regressions...")
    results["regressions"] = {}
    for horizon, lag in [("fwd_1m", 21), ("fwd_3m", 63), ("fwd_6m", 126)]:
        results["regressions"][horizon] = {
            "gap_vs_forward_return": newey_west_regression(gap, fwd[horizon], lag),
            "adaptive_composite_vs_forward_return": newey_west_regression(adaptive_composite, fwd[horizon], lag),
            "fixed_composite_vs_forward_return": newey_west_regression(fixed_composite, fwd[horizon], lag),
        }

    # Full daily series, for anyone who wants to plot/re-analyze rather than
    # trust only the summary tables above.
    daily = pd.DataFrame({
        "finance_score": finance_score,
        "economics_score": economics_score,
        "psychology_score": psychology_score,
        "baseline_score": baseline,
        "adaptive_weight": adaptive_weight,
        "adaptive_composite": adaptive_composite,
        "fixed_composite": fixed_composite,
        "gap": gap,
        "spy_close": spy,
    })
    daily.index.name = "date"
    daily.to_csv(os.path.join(OUT_DIR, "backtest_daily_series.csv"))
    print(f"Wrote daily series -> {os.path.join(OUT_DIR, 'backtest_daily_series.csv')}")

    with open(os.path.join(OUT_DIR, "backtest_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote results -> {os.path.join(OUT_DIR, 'backtest_results.json')}")


if __name__ == "__main__":
    main()
