# Market Psychology & Asset Allocation Dashboard

A dashboard that layers behavioral/psychological signals on top of standard
finance and macro data, synthesizing all three into a single allocation-relevant
"regime" read.

## Structure

```
├── index.html              # Static frontend — the page itself
├── style.css                # All visual styling (CSS variables at top for easy theming)
├── dashboard.js              # Fetches data/snapshot.json and renders charts/metrics
├── data/
│   └── snapshot.json         # Generated data file the frontend reads (sample data included)
├── scripts/
│   ├── fetch_data.py         # Pulls live data from FRED + yfinance, writes snapshot.json
│   └── requirements.txt
└── .github/workflows/
    └── refresh_data.yml      # Daily GitHub Actions job to auto-refresh snapshot.json
```

## Running locally

1. View the dashboard right now with sample data:
   ```bash
   python -m http.server 8000
   # open http://localhost:8000
   ```

2. To pull real data:
   ```bash
   cd scripts
   pip install -r requirements.txt --break-system-packages
   export FRED_API_KEY=your_key_here   # free at https://fred.stlouisfed.org/docs/api/api_key.html
   python fetch_data.py
   ```
   This overwrites `data/snapshot.json` with live numbers.

## Deploying

1. Push this repo to GitHub.
2. In repo Settings → Pages, set source to the `main` branch, root folder.
3. In repo Settings → Secrets → Actions, add `FRED_API_KEY` so the scheduled
   workflow can fetch data automatically.
4. Your site will be live at `https://<username>.github.io/<repo-name>/`.

## What's stubbed vs. real

None of these four have a free API, so `fetch_data.py` scrapes three of them
(with a manual fallback) and leaves the fourth fully manual:

- **S&P 500 P/E** — scraped from multpl.com's static meta description
  (`fetch_sp500_pe()`). Yahoo Finance doesn't expose trailing P/E for the index.
- **ISM PMI** — scraped from Trading Economics' business confidence page
  (`fetch_ism_pmi()`). ISM has no free API and FRED doesn't carry the series
  (licensing), so this is the best free source; it only updates monthly anyway.
- **CBOE put/call ratio** — scraped from Cboe's own daily market statistics
  page (`fetch_put_call_ratio()`) — it's a plain HTML table, not a downloadable
  file, but no JS execution or auth is needed.
- **AAII sentiment** — **manual only**. aaii.com returns HTTP 403 to
  scrapers (Cloudflare bot protection) regardless of user-agent, so there's no
  scraping path here. Update `data/manual_overrides.json`'s `aaii_sentiment`
  field weekly from https://www.aaii.com/sentimentsurvey (released Thursdays)
  — this is a ~10-second manual task, not a real burden.

If a scrape fails (a page's HTML structure changes, a site blocks the request
that day, etc.), that field silently falls back to the corresponding value in
`data/manual_overrides.json` instead of writing `null` — check
`snapshot.json`'s `meta.data_sources` block to see which fields were actually
scraped vs. fell back to manual for a given run. Keep the fallback values in
`manual_overrides.json` reasonably fresh (they don't need daily updates —
these indicators move slowly) so a fallback day isn't wildly stale.

Scraping note: these are read-only, low-frequency (daily/monthly) requests
against public pages for a non-commercial academic project — reasonable in
practice, but each site's ToS technically restricts automated access, and page
structures can change without notice and silently break the regexes in
`fetch_data.py`. If a GitHub Actions run logs a "scrape failed" warning for one
of these three, that's expected occasionally — just check the fallback value
is still reasonably current.

## Customizing

- **Colors, fonts, spacing**: edit the `:root` variables at the top of `style.css`.
- **Composite scoring logic**: see `compute_composite()` in `scripts/fetch_data.py` —
  this is intentionally a simple, transparent starting rule. Replace it with
  whatever weighting you and your professor land on.
- **Adding/removing indicators**: add fields to `snapshot.json`, update the
  corresponding fetch logic in `fetch_data.py`, and add a matching render
  function/element in `dashboard.js` + `index.html`.
