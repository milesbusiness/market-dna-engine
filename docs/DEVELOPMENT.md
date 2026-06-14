# Development Guide

## Prerequisites

- Python 3.10+
- Local TradeStore at `E:\TradeStore\` (or update `STORE` path in `market_dna.py`)
- ~4 GB free disk space for DuckDB output

## Setup

```bash
# Clone
git clone https://github.com/milesbusiness/market-dna-engine
cd market-dna-engine

# Install dependencies
pip install -r requirements.txt
```

## Running the Market DNA Engine

```bash
# Analyse NIFTY 50 (2015–2022) — takes ~13 seconds
python market_dna.py --symbol "NIFTY 50_MINUTE" --from 2015 --to 2022

# Analyse Bank Nifty
python market_dna.py --symbol "NIFTY BANK_MINUTE" --from 2015 --to 2022

# Run all pure indices (no edge scan for speed)
python market_dna.py --all-indices --no-edge-scan

# Query the DuckDB database directly
python market_dna.py --query "SELECT gap_type, COUNT(*) n, ROUND(AVG(gap_filled::int)*100,1) fill_pct FROM market_dna WHERE symbol='NIFTY 50_MINUTE' GROUP BY gap_type ORDER BY n DESC"
```

## Running the Backtest App

```bash
python backtest_app/server.py
# Open http://localhost:5050
```

The server auto-detects all symbols available in your TradeStore.

## Configuring Your Data Path

```python
# market_dna.py — line ~50
STORE = Path(r"E:\TradeStore")   # change to your local path
```

Expected TradeStore layout:
```
E:\TradeStore\
├── indices\minute\
│   ├── NIFTY 50_MINUTE\      ← parquet files by year
│   └── NIFTY BANK_MINUTE\
├── equities\minute\          ← 4,298 equity symbols
└── indices\daily\
    └── INDIAVIX.parquet
```

## Project Structure

```
market-dna-engine/
├── market_dna.py          ← main engine
├── backtest_app/
│   ├── engine.py          ← strategy execution
│   ├── server.py          ← Flask API
│   └── static/
│       └── index.html     ← dark-theme SPA
├── fetch_nifty_yfinance.py ← extend data from yfinance
├── docs/
│   ├── ARCHITECTURE.md
│   └── DEVELOPMENT.md
└── requirements.txt
```

## Adding a New Strategy

1. Add a function `run_my_strategy(min_df, params)` in `backtest_app/engine.py`
2. Add it to the `if strategy == 'my_strategy'` block in `run_backtest()`
3. Add params to `DEFAULTS` dict in `server.py`
4. Add UI controls in `backtest_app/static/index.html`

## Common Issues

**`FileNotFoundError: E:\TradeStore\...`**
Update `STORE` path in `market_dna.py` to point to your data directory.

**`duckdb.CatalogException: Table 'market_dna' does not exist`**
Run `market_dna.py` first to build the database before querying.

**Flask port 5050 already in use**
```powershell
netstat -ano | findstr :5050
taskkill /PID <pid> /F
```
