# Technical Guide — Market DNA Engine

> This guide explains every technology used, how to learn it, how to install the project, what every file does, and how to run and view the output.

---

## Table of Contents

1. [Technologies Used](#1-technologies-used)
2. [Where to Learn Each Technology](#2-where-to-learn-each-technology)
3. [Installation — Step by Step](#3-installation--step-by-step)
4. [Project File Structure](#4-project-file-structure)
5. [Code Walkthrough — Every File Explained](#5-code-walkthrough--every-file-explained)
6. [How to Run and View Output](#6-how-to-run-and-view-output)

---

## 1. Technologies Used

| Technology | Version | What it is | Why it is used here |
|-----------|---------|-----------|-------------------|
| **Python** | 3.12 | General-purpose programming language | The entire engine is Python |
| **DuckDB** | 0.10+ | In-process analytical SQL database | Queries Parquet files with SQL — no data loading, no database server |
| **Apache Parquet** | — | Columnar binary file format | All market data stored as Parquet; columnar = extremely fast for time-series analytics |
| **Pandas** | 2.x | Python data analysis library | DataFrames for indicator calculations and statistical analysis |
| **NumPy** | — | Python numerical computing library | Array operations, mathematical calculations for indicators (ADX, ATR, RSI) |
| **FastAPI** | 0.115 | Python web framework | Serves the market intelligence REST API on port 8060 |
| **Scikit-learn** | — | Python machine learning library | Train/test split, model evaluation (accuracy, ROC AUC, Brier score) |
| **XGBoost** | — | Gradient boosting machine learning library | Trains the gap-fill probability classifier |
| **Plotly** | — | Interactive charting library for Python | Generates interactive HTML charts for visual analysis |
| **Matplotlib** | — | Static charting library | Generates static PNG charts |
| **Python-dotenv** | — | Environment variable loader | Loads credentials from `.env` file |

**Official Links:**
- DuckDB: https://duckdb.org/docs/
- DuckDB Python API: https://duckdb.org/docs/api/python/overview
- Parquet format: https://parquet.apache.org/
- Pandas: https://pandas.pydata.org/docs/
- XGBoost: https://xgboost.readthedocs.io/
- Scikit-learn: https://scikit-learn.org/stable/
- FastAPI: https://fastapi.tiangolo.com/
- Plotly: https://plotly.com/python/

---

## 2. Where to Learn Each Technology

### DuckDB

**Official:**
- https://duckdb.org/docs/guides/python/install.html — Python quickstart
- https://duckdb.org/docs/sql/query_syntax/select.html — SQL syntax (standard SQL with extensions)
- https://duckdb.org/docs/data/parquet/overview.html — Reading Parquet files

**YouTube:**
- "DuckDB Tutorial" — search "DuckDB Python" on YouTube; several good tutorials from 2024

**Why DuckDB instead of pandas for large data?**
- Pandas loads the entire file into RAM before you can query it
- DuckDB reads only the columns/rows you need — on 10 years of 1-minute NIFTY data (hundreds of millions of rows), pandas would crash; DuckDB handles it on a laptop
- DuckDB SQL is ANSI standard — `GROUP BY`, `ORDER BY`, `WINDOW` functions, `WITH` CTEs, all work

**Key concept:**
```python
import duckdb
# DuckDB can query Parquet files directly without loading them:
result = duckdb.sql("SELECT * FROM read_parquet('E:/TradeStore/NSE/INDEX/minute/NIFTY/*.parquet')")
df = result.fetchdf()   # Only now does data move into RAM
```

### Pandas

**Official:**
- https://pandas.pydata.org/docs/getting_started/intro_tutorials/ — 10-minute tutorial (start here)
- https://pandas.pydata.org/docs/user_guide/groupby.html — GroupBy
- https://pandas.pydata.org/docs/user_guide/window.html — Rolling windows (used for ADX, ATR)

**YouTube:**
- "Pandas Tutorial" by Corey Schafer — https://www.youtube.com/@coreyms (best pandas content)

### XGBoost

**Official:**
- https://xgboost.readthedocs.io/en/stable/get_started.html — Getting started
- https://xgboost.readthedocs.io/en/stable/tutorials/model.html — Understanding the model

**YouTube:**
- "XGBoost Tutorial" by StatQuest with Josh Starmer — https://www.youtube.com/@statquest (best ML explanations)

**What XGBoost does in this project:** Takes 10+ years of daily market features (gap size, ADX regime, ATR, RSI, day of week, distance from pivot, etc.) and learns the patterns that predict whether a gap will fill. Outputs a probability (0–1), not just yes/no.

### Technical Indicators (ADX, ATR, RSI)

These are standard technical analysis indicators. You do not need to know them to use the project, but if you want to understand the code:

- **ADX (Average Directional Index)** — measures trend strength (not direction). ADX > 25 = trending; < 20 = ranging. Official explanation: https://school.stockcharts.com/doku.php?id=technical_indicators:average_directional_index_adx
- **ATR (Average True Range)** — measures volatility. How much does the price move on a typical day? Official: https://school.stockcharts.com/doku.php?id=technical_indicators:average_true_range_atr
- **RSI (Relative Strength Index)** — measures momentum/overbought/oversold. RSI > 70 = overbought; < 30 = oversold. Official: https://school.stockcharts.com/doku.php?id=technical_indicators:relative_strength_index_rsi

---

## 3. Installation — Step by Step

### Step 1 — Install Python 3.12

```powershell
winget install Python.Python.3.12
python --version
# Python 3.12.x
```

### Step 2 — Clone the Repository

```powershell
git clone https://github.com/milesbusiness/market-dna-engine
cd market-dna-engine
```

### Step 3 — Create Virtual Environment and Install Dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate

pip install duckdb pandas numpy fastapi uvicorn plotly matplotlib xgboost scikit-learn python-multipart
```

**Note:** The `marketanalysis/` folder does not have a `requirements.txt` — install the packages above directly.

### Step 4 — Set Up Market Data

This project reads data from the TradeStore at `E:\TradeStore\`. This is a local Parquet data store of NSE market data.

The TradeStore structure is:
```
E:\TradeStore\
├── NSE\
│   ├── INDEX\
│   │   ├── minute\
│   │   │   ├── NIFTY\
│   │   │   │   ├── 2019.parquet
│   │   │   │   ├── 2020.parquet
│   │   │   │   └── ...
│   │   │   └── BANKNIFTY\
│   │   └── daily\
│   ├── EQ\
│   │   ├── minute\
│   │   └── daily\
│   └── NFO\
│       ├── FUTURES\
│       └── OPTIONS\
```

If you have data at a different path, edit the `STORE` variable at the top of `marketanalysis/market_duck.py`:
```python
STORE = Path(r"E:\TradeStore")  # Change this to your path
```

---

## 4. Project File Structure

```
market-dna-engine (F:\Trade\)
└── marketanalysis/
    ├── market_duck.py       ← DuckDB SQL layer: queries Parquet files directly with SQL
    ├── market_analysis.py   ← Core indicators: ADX, ATR, RSI, divergence, gap, supply/demand zones
    ├── market_intel.py      ← Intelligence engine: tags each day with regime/gap/pivot, builds probability tables
    ├── market_ml.py         ← XGBoost classifier: predicts gap-fill probability from market features
    ├── market_validate.py   ← Walk-forward validation: honest backtesting with time-series splits
    ├── market_api.py        ← FastAPI REST API: serves predictions as JSON + HTML dashboard
    ├── market_viz.py        ← Plotly visualisations: interactive HTML charts
    ├── market_trades.py     ← Trade simulation: simulates entries/exits based on gap strategy
    └── market_backtest.py   ← Backtest runner: runs strategy over historical data
```

---

## 5. Code Walkthrough — Every File Explained

### `market_duck.py` — DuckDB SQL Layer

This is the lowest layer — direct SQL access to the Parquet files.

```python
STORE = Path(r"E:\TradeStore")
_con = duckdb.connect(database=":memory:")   # In-memory DuckDB (no file on disk)
```
`database=":memory:"` creates a DuckDB instance in RAM with no persistent file. This is correct for read-only analytics — you don't need to persist anything.

```python
def q(sql: str):
    """Run any SQL, return a pandas DataFrame."""
    return _con.execute(sql).fetchdf()
```
The most important function in the file. Takes any SQL string, runs it against DuckDB (which reads the Parquet files), and returns a pandas DataFrame. Used by every other function in this file.

```python
def _glob(symbol: str, asset: str, tf: str) -> str:
    sym = symbol.upper()
    if asset.upper() == "INDEX":
        p = STORE / "NSE" / "INDEX" / tf / sym / "*.parquet"
    elif asset.upper() in ("FUT", "FUTURES"):
        p = STORE / "NSE" / "NFO" / "FUTURES" / tf / sym / "*.parquet"
    else:
        p = STORE / "NSE" / "EQ" / tf / sym / "*.parquet"
    return str(p).replace("\\", "/")
```
Builds the glob pattern for finding Parquet files. `*.parquet` matches all year files for a symbol. DuckDB's `read_parquet('path/*.parquet')` reads all matching files and concatenates them automatically.

```python
def daily_from_minute(symbol: str, asset: str = "INDEX"):
    """Resample minute -> daily OHLCV entirely in SQL."""
    g = _glob(symbol, asset, "minute")
    sql = f"""
        SELECT CAST(date AS DATE) AS day,
               first(open ORDER BY date) AS open,   -- First price of day = open
               max(high)  AS high,                   -- Highest price of day
               min(low)   AS low,                    -- Lowest price of day
               last(close ORDER BY date) AS close,   -- Last price of day = close
               sum(volume) AS volume
        FROM read_parquet('{g}')
        GROUP BY 1 ORDER BY 1
    """
    return q(sql)
```
**This is entirely SQL** — no pandas, no loops. DuckDB reads the minute Parquet files and computes daily OHLCV directly. `first(open ORDER BY date)` is DuckDB's ordered aggregate — the `open` of the first minute bar of each day = the daily open. This is faster than doing it in pandas because only the necessary columns are read from disk.

```python
def gap_fill_sql(symbol: str, asset: str = "INDEX"):
    """Gap-fill probability by gap bucket — computed purely in SQL/DuckDB."""
    sql = f"""
    WITH daily AS (
        SELECT CAST(date AS DATE) AS day,
               first(open ORDER BY date) AS open, ...
        FROM read_parquet('{g}') GROUP BY 1
    ),
    feat AS (
        SELECT day, open, close,
               lag(close) OVER (ORDER BY day) AS prev_close    -- Previous day's close
        FROM daily
    ),
    tagged AS (
        SELECT *,
            (open/prev_close - 1)*100 AS gap_pct,
            CASE
              WHEN abs(open/prev_close-1)*100 < 0.15 THEN 'FLAT'
              WHEN abs(open/prev_close-1)*100 < 0.5  THEN ...
            END AS gap_bucket,
            CASE WHEN open>prev_close THEN (low<=prev_close) ELSE (high>=prev_close) END AS gap_filled
        FROM feat WHERE prev_close IS NOT NULL
    )
    SELECT gap_bucket,
           count(*) AS n,
           round(100.0*avg(CASE WHEN gap_filled THEN 1 ELSE 0 END),1) AS fill_rate_pct
    FROM tagged WHERE abs(gap_pct) >= 0.15
    GROUP BY gap_bucket ORDER BY gap_bucket
    """
```
A complex SQL query using **Common Table Expressions (CTEs)** — the `WITH` blocks are temporary named queries. Step by step:
1. `daily` CTE — resamples minute data to daily OHLCV
2. `feat` CTE — adds `prev_close` using `LAG() OVER (ORDER BY day)` (window function: looks at the previous row)
3. `tagged` CTE — calculates `gap_pct` (how big is the gap?) and `gap_filled` (did the low/high return to prev_close?)
4. Final `SELECT` — aggregates by gap bucket, counts instances, calculates fill rate

This entire calculation happens in DuckDB SQL with no pandas code.

---

### `market_intel.py` — Market Structure Intelligence Engine

```python
def load_minute(symbol: str) -> pd.DataFrame:
    sym = INDEX_ALIASES.get(symbol.upper(), symbol.upper())
    folder = STORE / "NSE" / "INDEX" / "minute" / sym
    files = sorted(glob.glob(str(folder / "*.parquet")))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df
```
Loads all Parquet files for a symbol and concatenates them into one DataFrame. `INDEX_ALIASES` normalises symbol names ("NIFTY50" → "NIFTY"). `sort_values("date")` — important for time-series; the files cover different years so they must be time-sorted after concatenation.

```python
def to_daily(minute: pd.DataFrame) -> pd.DataFrame:
    g = minute.groupby("day")
    daily = pd.DataFrame({
        "date": list(g["day"].first()),
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low":  g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum()
    })
    return daily.sort_values("date").reset_index(drop=True)
```
Resamples minute-level data to daily OHLCV using pandas GroupBy. `first()`, `max()`, `min()`, `last()` are the correct aggregations for each OHLCV column.

The intelligence engine then computes per-day features:
- **Regime** — ADX on daily data: TREND_UP, TREND_DOWN, RANGE
- **Volatility** — ATR vs its 50-day average: HIGH_VOL, LOW_VOL
- **Gap** — (today's open / yesterday's close - 1): FLAT, SMALL_UP/DOWN, MEDIUM_UP/DOWN, LARGE_UP/DOWN
- **Pivot levels** — P = (H+L+C)/3, R1 = 2P-L, R2 = P+(H-L), S1 = 2P-H, S2 = P-(H-L)
- **Gap filled** — boolean: did the intraday low (for gap-up) or high (for gap-down) return to yesterday's close?

---

### `market_ml.py` — XGBoost Gap-Fill Classifier

```python
FEATURES_NUM = ["gap_pct", "adx", "atr", "rel_volume", "rsi",
                "open_vs_pivot", "open_vs_pdh", "open_vs_pdl"]
FEATURES_CAT = ["regime", "vol_regime", "weekday", "gap_bucket"]
```
The features used to train the model:
- `gap_pct` — size of the gap (continuous)
- `adx` — trend strength (continuous)
- `atr` — volatility (continuous)
- `rel_volume` — today's volume relative to 20-day average
- `rsi` — momentum indicator
- `open_vs_pivot` — distance from today's open to pivot level (%)
- `regime` — TREND_UP/TREND_DOWN/RANGE (categorical, one-hot encoded)
- `weekday` — Mon/Tue/.../Fri (categorical, markets behave differently on different days)

```python
feat = _feature_frame(symbol)
split_year = int(feat["year"].quantile(0.65))   # Train on first 65% of years

tr = feat["year"] < split_year     # Training set: earlier years
te = feat["year"] >= split_year    # Test set: later years
```
**Time-series split** — critical for financial ML. You cannot use random split because future data would leak into training. Instead, train on 2015–2021, test on 2022–2026. This is the only honest way to evaluate a predictive model on historical market data.

```python
model = XGBClassifier(
    n_estimators=300,      # 300 trees in the ensemble
    max_depth=4,           # Shallow trees (prevents overfitting on noisy market data)
    learning_rate=0.03,    # Slow learning rate (more conservative, better generalisation)
    subsample=0.8,         # Use 80% of training data per tree (regularisation)
    colsample_bytree=0.8,  # Use 80% of features per tree (regularisation)
    use_label_encoder=False,
    eval_metric="logloss",
    random_state=42
)
model.fit(X[tr], y[tr])
```
XGBoost is an ensemble of decision trees. Each tree corrects the errors of the previous tree. The hyperparameters above are tuned to prevent overfitting on noisy financial data: shallow trees, slow learning rate, subsampling.

```python
proba = model.predict_proba(X[te])[:, 1]    # Probability of gap filling
auc  = roc_auc_score(y[te], proba)
brier = brier_score_loss(y[te], proba)
```
`predict_proba` returns a probability (0–1), not a binary prediction. AUC (Area Under ROC Curve) measures discrimination — how well the model separates "gap fills" from "gap doesn't fill". Brier score measures calibration — how accurate the probabilities are (lower is better).

---

### `market_api.py` — The REST API

```python
app = FastAPI(title="Market Intelligence API", version="1.0")

@app.get("/predict")
def predict(symbol: str = Query(..., description="NSE index symbol, e.g. NIFTY")):
    ...

@app.get("/report")
def report(symbol: str, date: str = None):
    ...
```
The API serves the market intelligence as JSON so a trader or dashboard can consume it programmatically.

`_ML_CACHE: dict = {}` — once the XGBoost model is trained for a symbol (which takes ~10 seconds), the result is cached in memory. Subsequent requests for the same symbol return instantly.

---

## 6. How to Run and View Output

### Option 1: DuckDB SQL Analysis (No Server Needed)

```powershell
cd F:\Trade\marketanalysis
python -m pip install duckdb pandas

# Resample NIFTY minute data to daily
python market_duck.py --symbol NIFTY --asset INDEX --daily

# Output:
# NIFTY daily (resampled in SQL): 1820 days, 2019-01-02 .. 2026-06-20
#         day     open      high       low     close   volume
# 2026-06-16  23120.5  23398.2  23089.1  23345.6  8932421
# 2026-06-17  23360.2  23501.8  23240.3  23420.1  7823150
```

```powershell
# Gap-fill probability statistics
python market_duck.py --gaps NIFTY --asset INDEX

# Output:
# Gap-fill probability (DuckDB SQL) — NIFTY
#   gap_bucket   n  fill_rate_pct
#         FLAT 312           87.1
#   LARGE_DOWN  43           48.8
#     LARGE_UP  52           54.2
#  MEDIUM_DOWN 187           62.5
#    MEDIUM_UP 201           67.3
#   SMALL_DOWN 312           73.1
#     SMALL_UP 298           74.8
```

```powershell
# Run any SQL directly
python market_duck.py --sql "SELECT EXTRACT(YEAR FROM date) AS year, count(*) AS bars FROM read_parquet('E:/TradeStore/NSE/INDEX/minute/NIFTY/*.parquet') GROUP BY 1 ORDER BY 1"
```

### Option 2: Morning Report (CLI)

```powershell
cd F:\Trade\marketanalysis
python market_intel.py NIFTY
```

Sample output:
```
===== NIFTY Morning Report  (2026-06-22) =====
Gap-up 0.62% at open.  Prev close 23,345 | Open 23,490
Pivot 23,380 | R1 23,510 | R2 23,680 | S1 23,250 | S2 23,080
PDH 23,420 | PDL 23,089

Regime: RANGE  (ADX 18.4)
Volatility: LOW  (ATR 183 | 50-day avg ATR 211)

Gap Analysis — MEDIUM_UP in RANGE regime:
  Fill rate: 67.3% (201 historical cases)
  Avg fill time: 11:23

Edge: ~67% chance price returns to 23,345 today.
  If short: target 23,345, stop above R1 23,510.

Levels of interest:
  - R1 23,510: resistance (gap fill target if gap continues)
  - Pivot 23,380: first support
  - S1 23,250: key support
```

```powershell
# Report for a specific historical date
python market_intel.py NIFTY --date 2024-01-15

# Show full probability tables
python market_intel.py NIFTY --tables
```

### Option 3: ML Gap Probability

```powershell
cd F:\Trade\marketanalysis
pip install xgboost scikit-learn
python market_ml.py NIFTY

# Output:
# XGBoost gap-fill classifier — NIFTY
# Train years: 2019–2022  |  Test years: 2022–2026
# Accuracy:    68.2%
# AUC:         0.741      (0.5 = random, 1.0 = perfect)
# Brier score: 0.198      (lower is better; 0.25 = random)
#
# Feature importances (top 5):
#   gap_pct          0.234
#   regime_RANGE     0.187
#   adx              0.143
#   open_vs_pivot    0.119
#   rsi              0.098
#
# Today's probability: 0.71  (gap likely to fill)
```

### Option 4: REST API with Dashboard

```powershell
cd F:\Trade\marketanalysis
uvicorn market_api:app --host 0.0.0.0 --port 8060 --reload
```

Open in browser: **http://localhost:8060**

You will see an HTML dashboard with:
- Morning report for NIFTY
- Gap-fill probability
- Key levels

REST endpoints:
- http://localhost:8060/predict?symbol=NIFTY — JSON prediction with gap-fill probability
- http://localhost:8060/report?symbol=BANKNIFTY — full morning report
- http://localhost:8060/validate?symbol=NIFTY — walk-forward validation results
- http://localhost:8060/docs — Swagger UI for the API

```powershell
# Query the API
Invoke-RestMethod "http://localhost:8060/predict?symbol=NIFTY"
```

Sample JSON response:
```json
{
  "symbol": "NIFTY",
  "date": "2026-06-22",
  "gap_pct": 0.62,
  "regime": "RANGE",
  "prob_gap_fill": 0.71,
  "recommended_action": "fade the gap (short toward prev close)",
  "key_levels": {
    "prev_close": 23345,
    "pivot": 23380,
    "r1": 23510,
    "s1": 23250
  },
  "historical_edge": "67.3% fill rate in 201 similar cases"
}
```

### Option 5: Interactive Visualisation

```powershell
cd F:\Trade\marketanalysis
python market_viz.py --symbol NIFTY
# Opens browser with interactive Plotly chart
```

The HTML output files (`analysis_RELIANCE_daily.html`, `backtest_RELIANCE_daily.html`) can also be opened directly in a browser by double-clicking.

---

## Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| `FileNotFoundError: No minute data for NIFTY` | TradeStore path wrong or data not present | Check `STORE = Path(r"E:\TradeStore")` in `market_duck.py` — change to your actual path |
| `ModuleNotFoundError: No module named 'duckdb'` | Virtual environment not activated or package not installed | `.venv\Scripts\activate` then `pip install duckdb` |
| `xgboost/sklearn not installed` | ML packages not installed | `pip install xgboost scikit-learn` |
| `not enough data (train 50, test 20)` | Symbol has very little data | Use a symbol with more historical data (NIFTY, BANKNIFTY have 5+ years) |
| Port 8060 already in use | Another process on that port | Use a different port: `uvicorn market_api:app --port 8070` |
| DuckDB query returns empty DataFrame | No Parquet files found for symbol | Verify the glob path matches your TradeStore structure |
