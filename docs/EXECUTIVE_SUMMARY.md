# Executive Summary — Market DNA Engine

## One Line
A statistical research platform that transforms 8 years of raw market data into a queryable database of trading edges — replacing trader intuition with conditional probability.

---

## The Business Problem

Trading desks at hedge funds, proprietary trading firms, and asset managers make daily decisions worth millions of dollars based on pattern recognition that has never been statistically validated. Traders believe certain market behaviours exist — gap fills, expiry pinning, momentum continuation — but they cannot quantify:

- How often does the pattern actually occur?
- Under exactly what conditions does it work?
- What is the sample size? Is it statistically meaningful?
- Does it work in all market regimes or only in specific conditions?

This lack of rigorous analysis leads to overconfidence in strategies that do not have genuine statistical edge, and underutilisation of strategies that do.

**The cost:** Capital allocated to unvalidated strategies, drawdowns that could have been avoided, and missed opportunities in genuine edges that were never discovered.

---

## The Solution

The Market DNA Engine ingests 8 years of minute-by-minute price data for Indian equity indices (NIFTY 50 and Bank NIFTY) and processes it into a structured analytical database.

Every trading day from 2015 to 2022 — **1,965 days per symbol** — is tagged with 35+ measurable conditions:

- Gap characteristics (size, direction, fill/continuation)
- Previous Day High/Low sweep patterns (5-stage detection)
- Opening Range Breakout metrics
- Volatility regime (India VIX zone)
- Trend strength (ADX regime classification)
- Time-to-expiry tagging (weekly NSE options)

The result is a queryable database where analysts can ask precise statistical questions and receive evidence-based answers with sample sizes, rates, and confidence.

---

## Business Value Delivered

### Risk Reduction
Strategies are validated against 8 years of data before capital is deployed. A strategy showing 51% win rate across 600+ trades is far more reliable than a trader's recollection of recent patterns.

### Research Acceleration
A research question that previously took a quantitative analyst days to code and test can be answered in seconds with a SQL query against the DNA database.

### Regime Awareness
The engine automatically identifies whether the market is in a choppy, ranging, or trending regime each day. Strategy performance is segmented by regime — traders know when to increase or reduce position size.

### Expiry Edge Discovery
NSE weekly options expiry creates predictable price behaviours. DTE tagging allows precise analysis of pre-expiry, expiry-day, and post-expiry patterns.

---

## Proven Results

The ORB-30 backtest strategy, developed entirely from the statistical findings in this engine, produced:

| Metric | Value |
|--------|-------|
| Sharpe Ratio | 1.13 |
| Profit Factor | 1.20 |
| Win Rate | 51.6% |
| Total Trades (8 years) | 609 |
| SHORT bias | 88% of total profit |

The SHORT bias finding — that 88% of profitable ORB trades are on the short side — is a non-obvious result that would never have been discovered without systematic statistical analysis.

---

## Target Users

- **Proprietary Trading Desks** — strategy validation and edge discovery
- **Hedge Funds** — quantitative research on Indian equity markets
- **Asset Managers** — regime-aware strategy allocation
- **Independent Quantitative Analysts** — research tool for systematic trading

---

## Technology Summary

Built in Python using DuckDB (embedded analytical database), Apache Parquet (columnar data storage), pandas/NumPy (data processing), and Flask (web backtest interface). Entirely local — no cloud costs, no external dependencies.

---

## Investment Summary

| Item | Detail |
|------|--------|
| Infrastructure cost | Zero (fully local) |
| Data coverage | 8 years, 2 symbols, 737K bars each |
| Analysis dimensions | 35+ daily conditions |
| Backtest trades analysed | 609 |
| Time to first result | ~13 seconds |
