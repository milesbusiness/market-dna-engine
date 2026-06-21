# Market DNA Engine

> **Statistical research platform that transforms 8 years of Indian market data into actionable trading edges — replacing guesswork with conditional probability.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![DuckDB](https://img.shields.io/badge/DuckDB-0.10-FFCA28)](https://duckdb.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## The Problem

Every trading desk faces the same challenge: traders rely on intuition, anecdote, and poorly-remembered patterns to make decisions. When someone says "gap-ups usually fill" or "expiry days are choppy," there is no rigorous foundation behind that claim — no sample size, no conditions, no statistical confidence.

This leads to capital deployed into strategies that have never been validated, drawdowns that were avoidable, and genuine edges that are never discovered because no one looked systematically.

## The Solution

The Market DNA Engine tags every trading day since 2015 with 35+ objective, measurable conditions — then stores them in a queryable database so you can find genuine statistical edges.

Instead of opinion, you get answers like:

> *"When NIFTY gaps up 0.3–0.8% on a Monday, with VIX between 14–18, and ADX below 20 (choppy regime), the gap fills by 11:00 AM in **74% of cases** across 312 observations."*

That is not intuition. That is evidence.

---

## Key Capabilities

### Gap Analysis
Classifies every day as gap-up, gap-down, or flat. Tracks fill rate, continuation rate, and reversal. Segments by gap size, VIX zone, ADX regime, and day of week.

### PDH/PDL Sweep Detection (5-Stage Model)
Identifies institutional sweep patterns — the 5 stages from initial probe to confirmed breakout or fake-out — across Previous Day High and Previous Day Low levels.

### ORB-30 Strategy Engine
Opening Range Breakout analysis for the 9:15–9:45 window. Tracks direction, range size, and success rate segmented by VIX, gap type, and DTE.

### VIX Zone Classification
Classifies each day as Low (<13), Mid (13–20), or High (>20) volatility. All patterns are cross-referenced against regime.

### ADX Regime Tagging
Classifies each day as Choppy / Ranging / Mild Trend / Trending using 14-period ADX. Every edge is segmented by regime — strategies that work in trending markets often fail in choppy ones.

### DTE (Days to Expiry) Analysis
Tags every day with days remaining to NSE weekly expiry. Reveals expiry-specific price behaviours including pinning, gamma effects, and pre-expiry directional bias.

### Edge Scanner
Exhaustively tests all two-condition combinations across the 35 daily fields to surface statistically significant edges with minimum sample size enforcement.

### Web Backtest Application
Full research-grade backtest tool with 8-filter ORB-30 strategy, equity curve visualisation, trade-by-trade analysis, and adjustable parameters.

---

## Research Findings (NIFTY 50, 2015–2022)

| Pattern | Conditions | Rate | Sample Size |
|---------|-----------|------|-------------|
| Gap fill | Gap up 0.3–0.8%, VIX 14–18 | 71% | 284 days |
| Gap continuation | Gap up > 0.8% | 63% | 156 days |
| PDH sweep success | Stage 3+ confirmation | 68% | 412 days |
| ORB short success | VIX 14–20, ADX < 25 | 54% | 609 trades |
| Monday gap fill | Any gap, ADX < 20 | 69% | 198 days |

### ORB-30 Backtest Results (2015–2022)

| Metric | Value |
|--------|-------|
| Win Rate | 51.6% |
| Profit Factor | 1.20 |
| Sharpe Ratio | 1.13 |
| Total Trades | 609 |
| SHORT Bias | 88% of total profit |

The **88% SHORT bias** is a non-obvious finding that would never have been discovered without systematic analysis. It has direct implications for position sizing and strategy design.

---

## How It Works

```
Raw Data (E:\TradeStore)
  └── 737,000 minute bars per symbol (NIFTY 50, Bank NIFTY, 2015–2022)
         │
         ▼
market_dna.py — DNA Engine
  ├── Loads minute OHLCV data from Parquet files
  ├── Computes daily DNA tags (35+ fields per day × 1,965 days)
  ├── Gap analysis: size, direction, fill, continuation
  ├── PDH/PDL: 5-stage sweep detection
  ├── ORB: range, direction, success
  ├── VIX: zone classification
  ├── ADX: regime classification
  ├── DTE: NSE weekly expiry calendar
  └── Saves to market_dna.duckdb
         │
         ▼
market_dna.duckdb — Queryable Analytical Database
  └── 1,965 rows × 35 fields per symbol
         │
         ▼
Backtest Application (Flask, port 5050)
  ├── engine.py — 8-filter ORB-30 strategy
  ├── server.py — REST API
  └── static/index.html — Dark-theme SPA (Chart.js)
```

---

## Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Analytical database | DuckDB | Embedded, columnar, 10× faster than SQLite for aggregations |
| Data format | Apache Parquet | Columnar storage, 5× compression, pandas-native |
| Data processing | pandas + NumPy | Industry standard for financial time-series |
| Web API | Flask | Lightweight, sufficient for single-user research tool |
| Visualisation | Chart.js | Professional charting with candlestick and equity curve |

---

## Getting Started

### Prerequisites
- Python 3.10+
- Local TradeStore at `E:\TradeStore\` (update `STORE` path in `market_dna.py` if different)

### Installation
```bash
git clone https://github.com/milesbusiness/market-dna-engine
cd market-dna-engine
pip install -r requirements.txt
```

### Build the DNA Database
```bash
python market_dna.py --symbol "NIFTY 50_MINUTE" --from 2015 --to 2022
# Takes ~13 seconds. Creates market_dna.duckdb
```

### Run the Backtest Application
```bash
python backtest_app/server.py
# Open http://localhost:5050
```

### Query the Database Directly
```bash
python market_dna.py --query "SELECT gap_type, COUNT(*) n, ROUND(AVG(gap_filled::int)*100,1) fill_pct FROM market_dna GROUP BY gap_type ORDER BY n DESC"
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Executive Summary](docs/EXECUTIVE_SUMMARY.md) | Business case, findings, and value proposition |
| [Architecture Guide](docs/ARCHITECTURE.md) | System design, data model, design decisions |
| [Development Guide](docs/DEVELOPMENT.md) | Setup, configuration, extending the engine |

---

## Who This Is For

| Role | Use Case |
|------|----------|
| Quantitative Analyst | SQL queries against the DNA database to discover and validate edges |
| Proprietary Trader | Backtest app to test strategy ideas with 8 years of evidence |
| Risk Manager | Regime identification to adjust position sizing by VIX zone |
| Researcher | Edge scanner to surface non-obvious statistical patterns |

---

## About

Built as part of a quantitative research portfolio demonstrating statistical analysis, financial data engineering, and evidence-based strategy development for Indian equity markets.

**Author:** Dilip Kumar Jena
**Market:** Indian Equity (NSE) — NIFTY 50, Bank NIFTY
**Data:** 8 years minute bars (2015–2022), 1,965 trading days per symbol
