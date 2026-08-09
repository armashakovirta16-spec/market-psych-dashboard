"""
Builds a lightweight, browser-ready summary of the item-4 backtest for the
dashboard's Backtesting tab — the full daily series (data/backtest_daily_series.csv,
~1.2MB/6931 rows) is a research artifact, not something to ship to every
page load. This resamples to monthly (plenty of resolution for a 27-year
"does the regime call look right historically" chart) and pulls the
decile/regression summaries straight from backtest_results.json.
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import fetch_data as fd  # single source of truth for TILT_RISK_ON/TILT_RISK_OFF — see fetch_data.py for how they're derived

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def regime_for(score):
    if pd.isna(score):
        return None
    if score > fd.TILT_RISK_ON:
        return "Risk-On"
    if score < fd.TILT_RISK_OFF:
        return "Risk-Off"
    return "Neutral"


def main():
    daily = pd.read_csv(os.path.join(DATA_DIR, "backtest_daily_series.csv"), parse_dates=["date"])
    daily = daily.set_index("date")

    with open(os.path.join(DATA_DIR, "backtest_results.json")) as f:
        results = json.load(f)

    monthly = daily.resample("ME").last()
    spy_start = monthly["spy_close"].dropna().iloc[0]
    monthly["spy_growth"] = monthly["spy_close"] / spy_start * 100

    series = []
    for date, row in monthly.iterrows():
        series.append({
            "date": date.strftime("%Y-%m"),
            "adaptive_composite": None if pd.isna(row["adaptive_composite"]) else round(float(row["adaptive_composite"]), 3),
            "fixed_composite": None if pd.isna(row["fixed_composite"]) else round(float(row["fixed_composite"]), 3),
            "gap": None if pd.isna(row["gap"]) else round(float(row["gap"]), 3),
            "spy_growth": None if pd.isna(row["spy_growth"]) else round(float(row["spy_growth"]), 2),
            "regime": regime_for(row["adaptive_composite"]),
        })

    # How often the adaptive and fixed-weight versions would have called a
    # genuinely different regime — a directly PM-relevant "did this
    # methodology choice ever actually matter" stat, not just an abstract
    # coefficient comparison.
    daily_valid = daily.dropna(subset=["adaptive_composite", "fixed_composite"])
    adaptive_regime = daily_valid["adaptive_composite"].apply(regime_for)
    fixed_regime = daily_valid["fixed_composite"].apply(regime_for)
    disagreement_days = int((adaptive_regime != fixed_regime).sum())
    disagreement_pct = round(disagreement_days / len(daily_valid) * 100, 1)

    frontend = {
        "meta": results["meta"],
        "monthly_series": series,
        "regime_disagreement": {
            "days": disagreement_days,
            "total_days": len(daily_valid),
            "pct": disagreement_pct,
        },
        "gap_deciles": results["gap_deciles"],
        "adaptive_composite_deciles": results["adaptive_composite_deciles"],
        "fixed_composite_deciles": results["fixed_composite_deciles"],
        "regressions": results["regressions"],
    }

    out_path = os.path.join(DATA_DIR, "backtest_frontend.json")
    with open(out_path, "w") as f:
        json.dump(frontend, f, indent=2)
    print(f"Wrote {out_path} ({len(series)} monthly points, {disagreement_pct}% regime disagreement)")


if __name__ == "__main__":
    main()
