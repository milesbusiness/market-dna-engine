# Market DNA Engine

**Statistical research platform for Indian equity markets — NIFTY 50 and Bank Nifty**

> *"Build a Market Statistics Engine first. This alone may already be tradable. No ML required."*

---

## What This Is

Most trading research starts with indicators (RSI, MACD, Supertrend) and ends with curve-fitting.

This project starts one level deeper: **What actually happens in Indian markets, across 8 years of data, under specific conditions?**

The engine tags every trading day with:
- Gap type and size (0.5%, 1%, 2%+)
- Whether the gap filled or continued
- Previous Day High / Low sweep detection (5-stage institutional logic)
- Opening Range (9:15–9:45) direction and outcome
- India VIX zone (calm / normal / volatile)
- ADX-based market regime (choppy / ranging / trending)
- Days to NSE expiry (DTE 0–5+)
- Session green/red rates (9:15–9:30 through 14:30–15:30)

Results stored in DuckDB. Query any combination in seconds.

---

## Key Findings (NIFTY 50 · 2015–2022 · 1,965 days)

| Finding | Edge |
|---------|------|
| Gap Up + PDH not swept → gap fills | **71.7%** (n=53) |
| ORB Shorts generate 88% of total profits | SHORT bias confirmed |
| 9:15–9:30 opening session is bearish-biased | 55.4% of opens close red |
| BankNifty DTE 1 gap-up fill rate | **57.9%** (n=57) |
| Gap fills need VIX > 13 to have any edge | Below 13: no mean reversion |

See [RESEARCH_FINDINGS.md](./RESEARCH_FINDINGS.md) for the full statistical breakdown.

---

## Components

### 1. Market DNA Engine (`market_dna.py`)
Statistical analysis across any symbol in the data store.

```bash
# Analyse NIFTY 50 (2015–2022)
python market_dna.py --symbol "NIFTY 50_MINUTE" --from 2015 --to 2022

# Analyse Bank Nifty
python market_dna.py --symbol "NIFTY BANK_MINUTE" --from 2015 --to 2022

# Run all pure indices
python market_dna.py --all-indices --no-edge-scan

# Query the DuckDB database directly
python market_dna.py --query "SELECT gap_type, COUNT(*) n, AVG(gap_filled::int) fill_rate FROM market_dna WHERE symbol='NIFTY 50_MINUTE' GROUP BY gap_type"
```

Output: gap statistics · PDH/PDL sweeps · ORB stats · session analysis · expiry patterns · edge scanner

### 2. Backtest App (`backtest_app/`)
Web-based backtester with TradingView charts, entry/exit markers, and per-trade reasoning.

```bash
python backtest_app/server.py
# Open http://localhost:5050
```

Strategies:
- **Intraday ORB-30** — research-backed Opening Range Breakout with 8 filters (VIX, gap, Tuesday skip, ORB range, DTE)
- **Swing Gap-Fill** — fade 0.2–0.8% gaps with regime and RSI confirmation
- **Position Monthly Bias** — first-week-of-month long bias (62% win rate from mutual fund inflows)

### 3. Data Fetch (`fetch_nifty_yfinance.py`)
Extends NIFTY index data from yfinance when local broker data has gaps.

```bash
python fetch_nifty_yfinance.py
```

---

## Data Source

All analysis reads from a local TradeStore directory:

```
E:\TradeStore\
├── indices\minute\NIFTY 50_MINUTE\     ← 2015–2022 real minute bars (737K rows)
├── indices\minute\NIFTY BANK_MINUTE\   ← 2015–2022 real minute bars (737K rows)
├── equities\minute\                    ← 4,298 NSE equity symbols
├── futures\nfo\minute\                 ← 656 NFO futures symbols
└── indices\daily\INDIAVIX.parquet      ← India VIX 2015–2026
```

The data is **not included in this repository** — it is sourced from local broker data exports (Fyers, Shoonya, AngelOne, ICICI Breeze). Point `STORE` in `market_dna.py` to your own data directory.

```python
# market_dna.py — line 50
STORE = Path(r"E:\TradeStore")   # change to your local path
```

---

## Installation

```bash
pip install -r requirements.txt
```

Requirements: `pandas`, `numpy`, `pyarrow`, `duckdb`, `flask`, `yfinance`

---

## Architecture

```
Local minute-bar data (E:\TradeStore)
        │
        ▼
market_dna.py
  ├── build_daily_dna()      — one row per trading day with 35 tagged fields
  ├── add_adx_regime()       — rolling ADX + regime classification
  ├── gap_statistics()       — fill/continuation rates across all dimensions
  ├── pdh_pdl_statistics()   — 5-stage institutional sweep detection
  ├── orb_statistics()       — ORB direction, success, range bucket analysis
  ├── session_statistics()   — time-of-day green rate analysis
  ├── expiry_statistics()    — DTE-tagged patterns
  └── edge_scanner()         — exhaustive 2-condition combo search
        │
        ▼
market_dna.duckdb            — queryable DNA database
        │
        ▼
backtest_app/
  ├── engine.py              — strategy execution (ORB, gap-fill, trend)
  ├── server.py              — Flask API
  └── static/index.html      — dark-theme SPA (TradingView + Chart.js)
```

---

## Research Methodology

No look-ahead bias. No indicator optimisation.

1. Tag every historical day with objective conditions (gap size, VIX level, regime, DTE)
2. Measure what happened next across thousands of occurrences
3. Build strategies only on conditions with ≥ 25 observations and ≥ 60% edge
4. Backtest with realistic filters (ORB range ≥ 40 pts, gap < 0.8%, skip Tuesdays)

The ORB backtest (2015–2022, 609 filtered trades):
- Win rate: 51.6%
- Total: +2,687 pts
- Profit factor: 1.20
- Sharpe: 1.13
- SHORT trades: 88% of total profit

---

## License

MIT
