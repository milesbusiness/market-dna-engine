# -*- coding: utf-8 -*-
"""
Download NIFTY 50 daily data from Yahoo Finance (^NSEI)
and save as year-parquets into the indices/minute store.

One bar per day at 09:15 — resample_to_daily passes it through as-is.
Covers the gap: Jan 2023 -> present (extends what FromURL-Minute-Indices has).
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd
import yfinance as yf
from pathlib import Path

NIFTY_DIR = Path(r"E:\TradeStore\indices\minute\NIFTY 50_MINUTE")
SYMBOL    = "NIFTY 50_MINUTE"

# Find what's already in store
existing = sorted(NIFTY_DIR.glob("*.parquet"))
last_date = None
if existing:
    last_df = pd.read_parquet(existing[-1])
    last_date = pd.to_datetime(last_df["date"]).max()
    print(f"Store last date : {last_date.date()}")

start = "2015-01-01"  # full download to ensure no gaps
end   = "2026-06-07"

print(f"Downloading ^NSEI daily {start} -> {end} ...")
raw = yf.download("^NSEI", start=start, end=end, interval="1d",
                  progress=False, auto_adjust=True)
raw = raw.droplevel(1, axis=1)   # drop Ticker level
raw.index = pd.to_datetime(raw.index)
raw = raw.reset_index().rename(columns={
    "Date":   "date",
    "Open":   "open",
    "High":   "high",
    "Low":    "low",
    "Close":  "close",
    "Volume": "volume",
})
raw["date"] = pd.to_datetime(raw["date"]) + pd.Timedelta(hours=9, minutes=15)
raw = raw[["date","open","high","low","close","volume"]].dropna()
raw["symbol"]   = SYMBOL
raw["exchange"] = "NSE"
raw["source"]   = "Yahoo-yfinance"
raw["open"]     = raw["open"].astype("float32")
raw["high"]     = raw["high"].astype("float32")
raw["low"]      = raw["low"].astype("float32")
raw["close"]    = raw["close"].astype("float32")
raw["volume"]   = raw["volume"].astype("int64")

print(f"Downloaded {len(raw)} daily bars: {raw['date'].min().date()} to {raw['date'].max().date()}")

# Split by year and save — only save years not already in store (or append new rows)
raw["_year"] = raw["date"].dt.year
STORE_COLS = ["date","symbol","exchange","open","high","low","close","volume","source"]

added = 0
for year, yr_df in raw.groupby("_year"):
    yr_df = yr_df.drop(columns="_year")[STORE_COLS].reset_index(drop=True)
    out = NIFTY_DIR / f"{year}.parquet"

    if out.exists():
        existing_df = pd.read_parquet(out)
        existing_df["date"] = pd.to_datetime(existing_df["date"])
        # Only append Yahoo rows for dates NOT already covered by minute data
        existing_dates = set(existing_df["date"].dt.date.astype(str))
        new_only = yr_df[~yr_df["date"].dt.date.astype(str).isin(existing_dates)]
        if len(new_only) == 0:
            print(f"  {year}: already complete ({len(existing_df)} rows), skipping")
            continue
        merged = pd.concat([existing_df, new_only]).sort_values("date").reset_index(drop=True)
        merged.to_parquet(out, index=False)
        print(f"  {year}: appended {len(new_only)} Yahoo bars to {len(existing_df)} existing -> {len(merged)} total")
        added += len(new_only)
    else:
        yr_df.to_parquet(out, index=False)
        print(f"  {year}: created new file with {len(yr_df)} bars")
        added += len(yr_df)

print(f"\nDone. {added} new bars added to store.")

# Final range check
all_files = sorted(NIFTY_DIR.glob("*.parquet"))
print(f"NIFTY store now has {len(all_files)} year files: {[f.stem for f in all_files]}")
last = pd.read_parquet(all_files[-1])
print(f"Latest bar: {pd.to_datetime(last['date']).max().date()}")
