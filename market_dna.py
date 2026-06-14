# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║            MARKET DNA ENGINE  —  Indian Quant Research Platform            ║
║                                                                              ║
║  What this builds:                                                           ║
║    • Gap Statistics     — fill rate, continuation by size/DOW/DTE/regime    ║
║    • PDH/PDL Sweeps     — 5-stage institutional sweep detection              ║
║    • ORB Statistics     — breakout direction, time-of-day, regime           ║
║    • Session Analysis   — 9:15-9:30 / 9:30-10 / 10-11 / 11-13 / 13-14:30  ║
║    • Expiry Context     — DTE tagging for NSE weekly/monthly expiry          ║
║    • Regime Detection   — ADX + VIX based trending/ranging classification   ║
║    • Edge Scanner       — finds highest-expectancy multi-condition combos    ║
║                                                                              ║
║  Symbols: NIFTY 50_MINUTE, NIFTY BANK_MINUTE, BANKNIFTY, and all equities  ║
║  Storage: DuckDB at F:/Trade/market_dna.duckdb                              ║
║                                                                              ║
║  Usage:                                                                      ║
║    python market_dna.py --symbol "NIFTY 50_MINUTE" --from 2015 --to 2022   ║
║    python market_dna.py --symbol "NIFTY BANK_MINUTE" --from 2015 --to 2022 ║
║    python market_dna.py --all-indices                                        ║
║    python market_dna.py --edge-scan "NIFTY 50_MINUTE"                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys, io, warnings, argparse, re
from pathlib import Path
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import duckdb

# ── Paths ──────────────────────────────────────────────────────────────────
STORE    = Path(r"E:\TradeStore")
DNA_DB   = Path(r"F:\Trade\market_dna.duckdb")
VIX_PATH = STORE / "indices" / "daily" / "INDIAVIX.parquet"

# ── Terminal colors ────────────────────────────────────────────────────────
GRN  = "\033[92m"
RED  = "\033[91m"
YEL  = "\033[93m"
BLU  = "\033[94m"
CYN  = "\033[96m"
DIM  = "\033[2m"
BOLD = "\033[1m"
RST  = "\033[0m"

def c(text, col): return f"{col}{text}{RST}"
def pct(v):       return f"{v*100:.1f}%"
def pts(v):       return f"{v:+.1f}"


# ══════════════════════════════════════════════════════════════════════════
# NSE EXPIRY CALENDAR
# ══════════════════════════════════════════════════════════════════════════

def nse_weekly_expiry_dates(symbol: str, start: str, end: str) -> set:
    """
    Generate NSE weekly expiry dates.
    NIFTY   → Thursday (3) from June 2019; Monthly = last Thursday before June 2019
    BANKNIFTY → Wednesday (2) from 2016
    Others  → Thursday monthly (last Thursday of month)
    """
    start_d = pd.Timestamp(start)
    end_d   = pd.Timestamp(end)
    dates   = set()

    sym_up = symbol.upper()
    if "BANK" in sym_up:
        weekly_dow   = 2  # Wednesday
        weekly_start = pd.Timestamp("2016-01-01")
    else:
        weekly_dow   = 3  # Thursday
        weekly_start = pd.Timestamp("2019-06-01")

    cur = start_d
    while cur <= end_d:
        if cur >= weekly_start:
            # Weekly: every Wednesday/Thursday
            if cur.dayofweek == weekly_dow:
                dates.add(cur.normalize())
        else:
            # Monthly: last Thursday of month
            if cur.dayofweek == 3:
                # Check if it's the last Thursday
                nxt = cur + pd.Timedelta(days=7)
                if nxt.month != cur.month:
                    dates.add(cur.normalize())
        cur += pd.Timedelta(days=1)
    return dates


def tag_dte(day: pd.Timestamp, expiry_dates: set) -> int:
    """Days to next expiry (0 = expiry day, 1 = day before, etc.)"""
    future = sorted([e for e in expiry_dates if e >= day.normalize()])
    if not future:
        return -1
    return int((future[0] - day.normalize()).days)


# ══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════

def load_minute_data(symbol: str, from_year: int, to_year: int) -> pd.DataFrame:
    for subpath in ["indices/minute", "equities/minute",
                    "futures/nfo/minute", "futures/mcx/minute"]:
        base = STORE / subpath / symbol
        if base.exists():
            files = sorted([f for f in base.glob("*.parquet")
                            if f.stem.isdigit() and from_year <= int(f.stem) <= to_year])
            if files:
                df = pd.concat([pd.read_parquet(f) for f in files])
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").reset_index(drop=True)
                # filter to market hours only (9:00-15:30)
                hhmm = df["date"].dt.hour * 60 + df["date"].dt.minute
                df = df[(hhmm >= 555) & (hhmm <= 930)].reset_index(drop=True)
                return df
    return pd.DataFrame()


def load_vix_series() -> pd.Series:
    if VIX_PATH.exists():
        df = pd.read_parquet(VIX_PATH)
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        return df.set_index("date")["vix"]
    return pd.Series(dtype=float)


def build_daily_dna(min_df: pd.DataFrame, symbol: str,
                    vix_series: pd.Series, expiry_dates: set) -> pd.DataFrame:
    """
    Build one row per trading day with ALL context fields needed for DNA analysis.
    """
    min_df = min_df.copy()
    min_df["day"]  = min_df["date"].dt.normalize()
    min_df["hhmm"] = min_df["date"].dt.hour * 60 + min_df["date"].dt.minute

    records = []
    days = sorted(min_df["day"].unique())

    for i, day in enumerate(days):
        bars = min_df[min_df["day"] == day].sort_values("date")
        if len(bars) < 10:
            continue

        day_open  = float(bars.iloc[0]["open"])
        day_high  = float(bars["high"].max())
        day_low   = float(bars["low"].min())
        day_close = float(bars.iloc[-1]["close"])
        day_vol   = float(bars["volume"].sum()) if "volume" in bars.columns else 0

        # ── Previous day ────────────────────────────────────────────────
        if i == 0:
            continue
        prev_bars = min_df[min_df["day"] == days[i-1]].sort_values("date")
        if len(prev_bars) < 5:
            continue
        prev_close = float(prev_bars.iloc[-1]["close"])
        prev_high  = float(prev_bars["high"].max())
        prev_low   = float(prev_bars["low"].min())
        prev_open  = float(prev_bars.iloc[0]["open"])
        prev_vol   = float(prev_bars["volume"].sum()) if "volume" in prev_bars.columns else 1

        # ── Gap ─────────────────────────────────────────────────────────
        gap_pct   = (day_open - prev_close) / prev_close
        gap_pts   = day_open - prev_close
        gap_up    = gap_pct > 0
        gap_type  = ("up" if gap_pct > 0.005 else
                     "down" if gap_pct < -0.005 else "flat")
        gap_size  = ("large" if abs(gap_pct) > 0.01 else
                     "medium" if abs(gap_pct) > 0.005 else "small")

        # ── Gap fill logic ──────────────────────────────────────────────
        # Gap up filled = price traded at or below prev_close during the day
        # Gap down filled = price traded at or above prev_close during the day
        if gap_up:
            gap_filled     = day_low  <= prev_close
            gap_continued  = day_close > day_open * 1.002  # closed above open
        elif not gap_up and abs(gap_pct) > 0.002:
            gap_filled     = day_high >= prev_close
            gap_continued  = day_close < day_open * 0.998
        else:
            gap_filled    = False
            gap_continued = False

        # ── ORB (9:15-9:45 = first 30 min) ─────────────────────────────
        orb_bars = bars[bars["hhmm"] <= 570]   # up to 9:30 AM (hhmm = 9*60+30=570)
        orb30_bars = bars[bars["hhmm"] <= 585] # up to 9:45 AM
        if len(orb_bars) >= 2:
            orb15_h = float(orb_bars["high"].max())
            orb15_l = float(orb_bars["low"].min())
        else:
            orb15_h = orb15_l = day_open

        if len(orb30_bars) >= 3:
            orb30_h = float(orb30_bars["high"].max())
            orb30_l = float(orb30_bars["low"].min())
            orb30_range = orb30_h - orb30_l
        else:
            orb30_h = orb30_l = day_open
            orb30_range = 0

        # Post-ORB action
        post_orb = bars[bars["hhmm"] > 585]
        if len(post_orb) > 5 and orb30_range > 0:
            orb_broke_up   = float(post_orb["high"].max()) > orb30_h
            orb_broke_down = float(post_orb["low"].min())  < orb30_l
            if orb_broke_up and not orb_broke_down:
                orb_direction = "LONG"
            elif orb_broke_down and not orb_broke_up:
                orb_direction = "SHORT"
            elif orb_broke_up and orb_broke_down:
                # Which broke first?
                first_up   = post_orb[post_orb["high"] >= orb30_h]
                first_dn   = post_orb[post_orb["low"]  <= orb30_l]
                orb_direction = ("LONG" if first_up.index[0] <= first_dn.index[0]
                                 else "SHORT")
            else:
                orb_direction = "NONE"

            # Did the ORB breakout follow through?
            if orb_direction == "LONG":
                target = orb30_h + orb30_range  # 1:1 target
                orb_success = day_high >= target
                orb_fail    = day_low  <= orb30_l  # SL hit
            elif orb_direction == "SHORT":
                target = orb30_l - orb30_range
                orb_success = day_low  <= target
                orb_fail    = day_high >= orb30_h
            else:
                orb_success = orb_fail = False
        else:
            orb_direction = "NONE"
            orb_success   = orb_fail = False

        # ── PDH / PDL Sweeps (5-stage institutional detection) ───────────
        post_open_bars = bars[bars["hhmm"] > 558]  # after 9:18 (let first candle form)

        def detect_sweep(level, direction, bars_after, vol_rolling):
            """
            5-stage sweep detection:
            1. Price crosses level (sweep)
            2. Closes back below (rejection) within 5 candles
            3. ATR displacement
            4. Volume spike
            5. Follow-through (next candle in reversal direction)
            """
            if direction == "PDH":
                cross_bars = bars_after[bars_after["high"] > level]
            else:
                cross_bars = bars_after[bars_after["low"] < level]
            if len(cross_bars) == 0:
                return False, False

            # Stage 1: Sweep exists
            first_sweep_idx = cross_bars.index[0]
            sweep_row = bars_after.loc[first_sweep_idx]

            # Stage 2: Close back below/above within 5 candles
            window = bars_after.loc[first_sweep_idx:].head(6)
            if direction == "PDH":
                rejection = (window["close"] < level).any()
            else:
                rejection = (window["close"] > level).any()

            if not rejection:
                return True, False  # sweep only, no valid reversal

            # Stage 3+4: ATR + Volume (simplified: check if vol was elevated)
            avg_vol = vol_rolling
            high_vol = float(sweep_row.get("volume", 0)) > avg_vol * 1.3

            # Stage 5: follow-through — next bar after rejection continues reversal
            rej_idx = window[window["close"] < level if direction == "PDH"
                             else window["close"] > level].index[0]
            after_rej = bars_after.loc[rej_idx:].head(3)
            if len(after_rej) >= 2:
                if direction == "PDH":
                    follow = float(after_rej.iloc[1]["low"]) < float(after_rej.iloc[0]["low"])
                else:
                    follow = float(after_rej.iloc[1]["high"]) > float(after_rej.iloc[0]["high"])
            else:
                follow = False

            valid = rejection and (high_vol or follow)
            return True, valid

        avg_vol_today = float(bars["volume"].mean()) if "volume" in bars.columns else 1
        pdh_swept, pdh_valid = detect_sweep(prev_high, "PDH", post_open_bars, avg_vol_today)
        pdl_swept, pdl_valid = detect_sweep(prev_low,  "PDL", post_open_bars, avg_vol_today)

        # ── Session OHLC ─────────────────────────────────────────────────
        def session_stats(start_hhmm, end_hhmm):
            s = bars[(bars["hhmm"] >= start_hhmm) & (bars["hhmm"] < end_hhmm)]
            if len(s) == 0:
                return None, None, None, None
            return (float(s.iloc[0]["open"]), float(s["high"].max()),
                    float(s["low"].min()),    float(s.iloc[-1]["close"]))

        s1o, s1h, s1l, s1c = session_stats(555, 570)   # 9:15-9:30
        s2o, s2h, s2l, s2c = session_stats(570, 600)   # 9:30-10:00
        s3o, s3h, s3l, s3c = session_stats(600, 660)   # 10:00-11:00
        s4o, s4h, s4l, s4c = session_stats(660, 810)   # 11:00-13:30
        s5o, s5h, s5l, s5c = session_stats(810, 870)   # 13:30-14:30
        s6o, s6h, s6l, s6c = session_stats(870, 930)   # 14:30-15:30

        # ── ADX (regime) ─────────────────────────────────────────────────
        # Approximate using recent daily range expansion
        # (we'll compute proper ADX over rolling daily bars later)
        day_range    = day_high - day_low
        prev_range   = prev_high - prev_low
        range_expansion = day_range / (prev_range + 0.001)

        # ── VIX ─────────────────────────────────────────────────────────
        vix_val = float(vix_series.get(pd.Timestamp(day), np.nan))

        # ── Expiry ───────────────────────────────────────────────────────
        dte = tag_dte(pd.Timestamp(day), expiry_dates)

        # ── Day context ──────────────────────────────────────────────────
        dow = pd.Timestamp(day).dayofweek   # 0=Mon
        dom = pd.Timestamp(day).day         # day of month
        month_week = (dom - 1) // 7 + 1    # 1-5 (week of month)

        records.append({
            "symbol":       symbol,
            "date":         str(day.date()),
            "dow":          int(dow),
            "dom":          int(dom),
            "month_week":   int(month_week),
            "dte":          int(dte),
            # Price
            "prev_close":   round(prev_close, 2),
            "prev_high":    round(prev_high, 2),
            "prev_low":     round(prev_low, 2),
            "day_open":     round(day_open, 2),
            "day_high":     round(day_high, 2),
            "day_low":      round(day_low, 2),
            "day_close":    round(day_close, 2),
            # Gap
            "gap_pct":      round(gap_pct * 100, 3),
            "gap_pts":      round(gap_pts, 2),
            "gap_type":     gap_type,
            "gap_size":     gap_size,
            "gap_filled":   bool(gap_filled),
            "gap_continued":bool(gap_continued),
            # ORB
            "orb30_high":   round(orb30_h, 2),
            "orb30_low":    round(orb30_l, 2),
            "orb30_range":  round(orb30_range, 2),
            "orb_direction":orb_direction,
            "orb_success":  bool(orb_success),
            "orb_fail":     bool(orb_fail),
            # PDH/PDL
            "pdh_swept":    bool(pdh_swept),
            "pdh_valid":    bool(pdh_valid),
            "pdl_swept":    bool(pdl_swept),
            "pdl_valid":    bool(pdl_valid),
            # Sessions (green = close > open)
            "s1_green":     bool(s1c and s1o and s1c > s1o),
            "s2_green":     bool(s2c and s2o and s2c > s2o),
            "s3_green":     bool(s3c and s3o and s3c > s3o),
            "s4_green":     bool(s4c and s4o and s4c > s4o),
            "s5_green":     bool(s5c and s5o and s5c > s5o),
            "s6_green":     bool(s6c and s6o and s6c > s6o),
            "s1_range":     round(abs((s1h or 0) - (s1l or 0)), 2),
            "s2_range":     round(abs((s2h or 0) - (s2l or 0)), 2),
            # Day result
            "day_green":    bool(day_close > day_open),
            "day_range":    round(day_range, 2),
            "range_exp":    round(range_expansion, 3),
            # Regime
            "vix":          round(vix_val, 2) if not np.isnan(vix_val) else None,
            "vix_zone":     ("low" if vix_val < 13 else
                             "mid" if vix_val <= 20 else
                             "high" if not np.isnan(vix_val) else None),
        })

    df = pd.DataFrame(records)
    return df


# ══════════════════════════════════════════════════════════════════════════
# ADD DAILY ADX (proper rolling computation on daily bars)
# ══════════════════════════════════════════════════════════════════════════

def add_adx_regime(df: pd.DataFrame, period=14) -> pd.DataFrame:
    d = df.sort_values("date").reset_index(drop=True)
    h, l, c = d["day_high"], d["day_low"], d["day_close"]

    hl  = h - l
    hcp = (h - c.shift(1)).abs()
    lcp = (l - c.shift(1)).abs()
    tr  = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)

    plus_dm  = (h - h.shift(1)).clip(lower=0)
    minus_dm = (l.shift(1) - l).clip(lower=0)
    tr_s   = tr.rolling(period).mean()
    pdi = 100 * plus_dm.rolling(period).mean() / (tr_s + 1e-9)
    mdi = 100 * minus_dm.rolling(period).mean() / (tr_s + 1e-9)
    dx  = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-9)
    adx = dx.rolling(period).mean()

    d["atr"]    = tr.rolling(period).mean()
    d["adx"]    = adx
    d["regime"] = pd.cut(adx,
                         bins  =[-np.inf, 15, 20, 25, np.inf],
                         labels=["choppy", "ranging", "mild_trend", "trending"])
    return d


# ══════════════════════════════════════════════════════════════════════════
# DUCKDB STORAGE
# ══════════════════════════════════════════════════════════════════════════

def save_to_duckdb(df: pd.DataFrame, symbol: str):
    con = duckdb.connect(str(DNA_DB))
    con.execute("""
        CREATE TABLE IF NOT EXISTS market_dna (
            symbol TEXT, date TEXT, dow INT, dom INT, month_week INT, dte INT,
            prev_close DOUBLE, prev_high DOUBLE, prev_low DOUBLE,
            day_open DOUBLE, day_high DOUBLE, day_low DOUBLE, day_close DOUBLE,
            gap_pct DOUBLE, gap_pts DOUBLE, gap_type TEXT, gap_size TEXT,
            gap_filled BOOLEAN, gap_continued BOOLEAN,
            orb30_high DOUBLE, orb30_low DOUBLE, orb30_range DOUBLE,
            orb_direction TEXT, orb_success BOOLEAN, orb_fail BOOLEAN,
            pdh_swept BOOLEAN, pdh_valid BOOLEAN, pdl_swept BOOLEAN, pdl_valid BOOLEAN,
            s1_green BOOLEAN, s2_green BOOLEAN, s3_green BOOLEAN,
            s4_green BOOLEAN, s5_green BOOLEAN, s6_green BOOLEAN,
            s1_range DOUBLE, s2_range DOUBLE,
            day_green BOOLEAN, day_range DOUBLE, range_exp DOUBLE,
            vix DOUBLE, vix_zone TEXT, atr DOUBLE, adx DOUBLE, regime TEXT,
            PRIMARY KEY (symbol, date)
        )
    """)
    # Delete existing rows for this symbol then reinsert
    con.execute("DELETE FROM market_dna WHERE symbol = ?", [symbol])
    con.execute("INSERT OR REPLACE INTO market_dna SELECT * FROM df")
    n = con.execute("SELECT COUNT(*) FROM market_dna WHERE symbol=?", [symbol]).fetchone()[0]
    con.close()
    return n


def query_dna(sql: str, params=None):
    con = duckdb.connect(str(DNA_DB), read_only=True)
    result = con.execute(sql, params or []).df()
    con.close()
    return result


# ══════════════════════════════════════════════════════════════════════════
# STATISTICS ENGINE
# ══════════════════════════════════════════════════════════════════════════

def stat_block(df: pd.DataFrame, condition_mask, outcome_col: str,
               label: str, min_n: int = 20) -> dict:
    """Compute stats for a condition → outcome pair."""
    sub = df[condition_mask]
    n   = len(sub)
    if n < min_n:
        return None
    rate = float(sub[outcome_col].mean())
    return {"label": label, "n": n, "rate": rate}


def gap_statistics(df: pd.DataFrame) -> dict:
    """Full gap analysis: fill rate, continuation by size/DOW/DTE/regime."""
    results = {}

    # ── Overall ─────────────────────────────────────────────────────────
    for gt in ["up", "down"]:
        mask = df["gap_type"] == gt
        sub  = df[mask]
        if len(sub) < 10: continue
        results[f"gap_{gt}_overall"] = {
            "n":           len(sub),
            "fill_rate":   float(sub["gap_filled"].mean()),
            "cont_rate":   float(sub["gap_continued"].mean()),
            "day_green":   float(sub["day_green"].mean()),
        }

    # ── By size ──────────────────────────────────────────────────────────
    for gt in ["up", "down"]:
        for gs in ["small", "medium", "large"]:
            mask = (df["gap_type"] == gt) & (df["gap_size"] == gs)
            sub  = df[mask]
            if len(sub) < 5: continue
            results[f"gap_{gt}_{gs}"] = {
                "n":         len(sub),
                "fill_rate": float(sub["gap_filled"].mean()),
                "cont_rate": float(sub["gap_continued"].mean()),
                "day_green": float(sub["day_green"].mean()),
            }

    # ── By DOW ───────────────────────────────────────────────────────────
    dow_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri"}
    for gt in ["up", "down"]:
        for dow, name in dow_names.items():
            mask = (df["gap_type"] == gt) & (df["dow"] == dow)
            sub  = df[mask]
            if len(sub) < 5: continue
            results[f"gap_{gt}_dow_{name}"] = {
                "n":         len(sub),
                "fill_rate": float(sub["gap_filled"].mean()),
                "cont_rate": float(sub["gap_continued"].mean()),
            }

    # ── By DTE ───────────────────────────────────────────────────────────
    for gt in ["up", "down"]:
        for dte in [0, 1, 2, 3]:
            mask = (df["gap_type"] == gt) & (df["dte"] == dte)
            sub  = df[mask]
            if len(sub) < 5: continue
            results[f"gap_{gt}_dte{dte}"] = {
                "n":         len(sub),
                "fill_rate": float(sub["gap_filled"].mean()),
                "cont_rate": float(sub["gap_continued"].mean()),
            }

    # ── By Regime ────────────────────────────────────────────────────────
    for gt in ["up", "down"]:
        for reg in ["choppy", "ranging", "mild_trend", "trending"]:
            mask = (df["gap_type"] == gt) & (df["regime"] == reg)
            sub  = df[mask]
            if len(sub) < 5: continue
            results[f"gap_{gt}_regime_{reg}"] = {
                "n":         len(sub),
                "fill_rate": float(sub["gap_filled"].mean()),
                "cont_rate": float(sub["gap_continued"].mean()),
            }

    # ── By VIX zone ──────────────────────────────────────────────────────
    for gt in ["up", "down"]:
        for vzone in ["low", "mid", "high"]:
            mask = (df["gap_type"] == gt) & (df["vix_zone"] == vzone)
            sub  = df[mask]
            if len(sub) < 5: continue
            results[f"gap_{gt}_vix_{vzone}"] = {
                "n":         len(sub),
                "fill_rate": float(sub["gap_filled"].mean()),
                "cont_rate": float(sub["gap_continued"].mean()),
            }

    return results


def pdh_pdl_statistics(df: pd.DataFrame) -> dict:
    results = {}

    for level, swept_col, valid_col in [
        ("PDH", "pdh_swept", "pdh_valid"),
        ("PDL", "pdl_swept", "pdl_valid"),
    ]:
        swept = df[df[swept_col] == True]
        if len(swept) == 0: continue

        results[f"{level}_overall"] = {
            "n_days":       len(df),
            "n_swept":      int(df[swept_col].sum()),
            "sweep_rate":   float(df[swept_col].mean()),
            "n_valid":      int(df[valid_col].sum()),
            "valid_of_swept": float(df[valid_col].sum() / max(df[swept_col].sum(), 1)),
        }

        # By DOW
        dow_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri"}
        for dow, name in dow_names.items():
            sub = df[df["dow"] == dow]
            if len(sub) < 5: continue
            results[f"{level}_dow_{name}"] = {
                "n":          len(sub),
                "sweep_rate": float(sub[swept_col].mean()),
                "valid_rate": float(sub[valid_col].mean()),
            }

        # By regime
        for reg in ["choppy", "ranging", "mild_trend", "trending"]:
            sub = df[df["regime"] == reg]
            if len(sub) < 5: continue
            results[f"{level}_regime_{reg}"] = {
                "n":          len(sub),
                "sweep_rate": float(sub[swept_col].mean()),
                "valid_rate": float(sub[valid_col].mean()),
            }

        # By gap type (crucial combination)
        for gt in ["up", "down", "flat"]:
            sub = df[df["gap_type"] == gt]
            if len(sub) < 5: continue
            results[f"{level}_after_gap_{gt}"] = {
                "n":          len(sub),
                "sweep_rate": float(sub[swept_col].mean()),
                "valid_rate": float(sub[valid_col].mean()),
            }

    return results


def orb_statistics(df: pd.DataFrame) -> dict:
    results = {}

    for direction in ["LONG", "SHORT", "NONE"]:
        sub = df[df["orb_direction"] == direction]
        if len(sub) < 5: continue
        results[f"orb_{direction.lower()}"] = {
            "n":            len(sub),
            "success_rate": float(sub["orb_success"].mean()) if direction != "NONE" else None,
            "fail_rate":    float(sub["orb_fail"].mean()) if direction != "NONE" else None,
            "day_green":    float(sub["day_green"].mean()),
        }

    # ORB by DOW
    dow_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri"}
    for direction in ["LONG", "SHORT"]:
        for dow, name in dow_names.items():
            mask = (df["orb_direction"] == direction) & (df["dow"] == dow)
            sub  = df[mask]
            if len(sub) < 5: continue
            results[f"orb_{direction.lower()}_dow_{name}"] = {
                "n":            len(sub),
                "success_rate": float(sub["orb_success"].mean()),
            }

    # ORB by regime
    for direction in ["LONG", "SHORT"]:
        for reg in ["choppy", "ranging", "mild_trend", "trending"]:
            mask = (df["orb_direction"] == direction) & (df["regime"] == reg)
            sub  = df[mask]
            if len(sub) < 5: continue
            results[f"orb_{direction.lower()}_regime_{reg}"] = {
                "n":            len(sub),
                "success_rate": float(sub["orb_success"].mean()),
            }

    # ORB range bucket analysis
    orb_active = df[df["orb_direction"] != "NONE"].copy()
    orb_active["range_bucket"] = pd.cut(orb_active["orb30_range"],
        bins=[0, 30, 50, 75, 100, 150, 9999],
        labels=["<30", "30-50", "50-75", "75-100", "100-150", ">150"])
    for rb in orb_active["range_bucket"].dropna().unique():
        sub = orb_active[orb_active["range_bucket"] == rb]
        if len(sub) < 5: continue
        results[f"orb_range_{rb}"] = {
            "n":            len(sub),
            "success_rate": float(sub["orb_success"].mean()),
            "long_pct":     float((sub["orb_direction"] == "LONG").mean()),
        }

    return results


def session_statistics(df: pd.DataFrame) -> dict:
    results = {}
    sessions = {
        "9:15-9:30":  "s1_green",
        "9:30-10:00": "s2_green",
        "10:00-11:00":"s3_green",
        "11:00-13:30":"s4_green",
        "13:30-14:30":"s5_green",
        "14:30-15:30":"s6_green",
    }
    for name, col in sessions.items():
        sub = df[df[col].notna()]
        if len(sub) < 5: continue
        # Overall green rate
        results[f"session_{name}"] = {
            "n":          len(sub),
            "green_rate": float(sub[col].mean()),
        }
        # After gap up
        for gt in ["up", "down"]:
            mask = sub["gap_type"] == gt
            s2   = sub[mask]
            if len(s2) < 5: continue
            results[f"session_{name}_after_gap_{gt}"] = {
                "n":          len(s2),
                "green_rate": float(s2[col].mean()),
            }

    # S1 (9:15-9:30) direction predicting rest of day
    for s1g in [True, False]:
        mask = df["s1_green"] == s1g
        sub  = df[mask]
        if len(sub) < 5: continue
        results[f"day_after_s1_{'green' if s1g else 'red'}"] = {
            "n":           len(sub),
            "day_green_rate": float(sub["day_green"].mean()),
            "orb_long_pct":   float((sub["orb_direction"] == "LONG").mean()),
        }

    return results


def expiry_statistics(df: pd.DataFrame) -> dict:
    results = {}
    for dte in range(-1, 6):
        if dte == -1:
            sub = df[df["dte"] > 4]
            label = "DTE 5+"
        else:
            sub   = df[df["dte"] == dte]
            label = f"DTE {dte}{'(Expiry)' if dte==0 else ''}"
        if len(sub) < 5: continue
        results[f"dte_{dte}"] = {
            "label":      label,
            "n":          len(sub),
            "day_green":  float(sub["day_green"].mean()),
            "gap_fill_if_up":   float(sub.loc[sub["gap_type"]=="up","gap_filled"].mean()) if len(sub[sub["gap_type"]=="up"]) > 2 else None,
            "gap_fill_if_down": float(sub.loc[sub["gap_type"]=="down","gap_filled"].mean()) if len(sub[sub["gap_type"]=="down"]) > 2 else None,
            "avg_range":  float(sub["day_range"].mean()),
            "pdh_sweep":  float(sub["pdh_swept"].mean()),
            "pdl_sweep":  float(sub["pdl_swept"].mean()),
        }
    return results


# ══════════════════════════════════════════════════════════════════════════
# EDGE SCANNER — finds highest-expectancy multi-condition combos
# ══════════════════════════════════════════════════════════════════════════

def edge_scanner(df: pd.DataFrame, min_n: int = 25) -> list:
    """
    Exhaustively test 2- and 3-condition combinations.
    Returns sorted list by expectancy proxy (fill_rate × n) where fill > 65%.
    """
    edges = []
    df = df.copy()

    # Build condition columns
    conditions = {
        "gap_up":          df["gap_type"] == "up",
        "gap_down":        df["gap_type"] == "down",
        "gap_large":       df["gap_size"] == "large",
        "gap_small":       df["gap_size"] == "small",
        "regime_ranging":  df["regime"].isin(["choppy","ranging"]),
        "regime_trending": df["regime"].isin(["mild_trend","trending"]),
        "vix_low":         df["vix_zone"] == "low",
        "vix_mid":         df["vix_zone"] == "mid",
        "vix_high":        df["vix_zone"] == "high",
        "mon":             df["dow"] == 0,
        "tue":             df["dow"] == 1,
        "wed":             df["dow"] == 2,
        "thu":             df["dow"] == 3,
        "fri":             df["dow"] == 4,
        "dte_0":           df["dte"] == 0,
        "dte_1":           df["dte"] == 1,
        "dte_2":           df["dte"] == 2,
        "dte_3p":          df["dte"] >= 3,
        "s1_green":        df["s1_green"] == True,
        "s1_red":          df["s1_green"] == False,
        "pdh_swept":       df["pdh_swept"] == True,
        "pdl_swept":       df["pdl_swept"] == True,
        "orb_long":        df["orb_direction"] == "LONG",
        "orb_short":       df["orb_direction"] == "SHORT",
        "first_week":      df["month_week"] == 1,
        "last_week":       df["month_week"] >= 4,
    }

    cond_keys = list(conditions.keys())

    outcomes = {
        "gap_fill":  "gap_filled",
        "day_green": "day_green",
        "pdh_valid": "pdh_valid",
        "pdl_valid": "pdl_valid",
        "orb_win":   "orb_success",
    }

    # 2-condition combos
    for i in range(len(cond_keys)):
        for j in range(i+1, len(cond_keys)):
            k1, k2 = cond_keys[i], cond_keys[j]
            mask = conditions[k1] & conditions[k2]
            sub  = df[mask]
            if len(sub) < min_n:
                continue
            for out_name, out_col in outcomes.items():
                rate = float(sub[out_col].mean()) if sub[out_col].notna().sum() > 0 else 0
                if rate >= 0.60 or rate <= 0.35:  # strong edge either direction
                    edges.append({
                        "conditions": f"{k1} + {k2}",
                        "outcome":    out_name,
                        "n":          int(len(sub)),
                        "rate":       round(rate, 4),
                        "edge":       round(abs(rate - 0.5), 4),
                        "direction":  "YES" if rate >= 0.5 else "NO",
                    })

    # Sort by edge strength * sample size (confidence-weighted)
    edges.sort(key=lambda x: x["edge"] * (x["n"] ** 0.5), reverse=True)
    return edges[:60]  # top 60 edges


# ══════════════════════════════════════════════════════════════════════════
# REPORT PRINTER
# ══════════════════════════════════════════════════════════════════════════

def bar(rate, width=20):
    filled = int(rate * width)
    col    = GRN if rate >= 0.55 else RED if rate <= 0.45 else YEL
    return col + "█" * filled + DIM + "░" * (width - filled) + RST

def print_section(title):
    print(f"\n{BOLD}{BLU}{'═'*70}{RST}")
    print(f"{BOLD}{BLU}  {title}{RST}")
    print(f"{BOLD}{BLU}{'═'*70}{RST}")

def print_gap_report(stats: dict, symbol: str):
    print_section(f"GAP STATISTICS — {symbol}")
    print(f"\n{'Condition':<40} {'N':>6} {'Fill%':>8} {'Cont%':>8} {'Bar'}")
    print(f"{'─'*40} {'─'*6} {'─'*8} {'─'*8} {'─'*22}")

    # Overall
    for gt in ["up", "down"]:
        key = f"gap_{gt}_overall"
        if key not in stats: continue
        s = stats[key]
        fr, cr = s["fill_rate"], s["cont_rate"]
        label = f"Gap {gt.upper()} — ALL ({abs(s['n'])} days)"
        print(f"{c(label,BOLD):<50} {s['n']:>6} {pct(fr):>8} {pct(cr):>8} {bar(fr)}")

    # By size
    print(f"\n  By Gap Size:")
    for gt in ["up","down"]:
        for gs in ["small(0.5-1%)","medium(1-2%)","large(>2%)"]:
            gkey = gs.split("(")[0]
            key  = f"gap_{gt}_{gkey}"
            if key not in stats: continue
            s    = stats[key]
            print(f"  {'Gap '+gt.upper()+' '+gs:<38} {s['n']:>6} {pct(s['fill_rate']):>8} {pct(s['cont_rate']):>8} {bar(s['fill_rate'])}")

    # By DOW
    print(f"\n  By Day of Week (gap fill rate):")
    days = ["Mon","Tue","Wed","Thu","Fri"]
    for gt in ["up","down"]:
        row = f"  Gap {gt.upper()} fill by DOW: "
        for d in days:
            key = f"gap_{gt}_dow_{d}"
            if key in stats:
                s = stats[key]
                col = GRN if s["fill_rate"] >= 0.60 else RED if s["fill_rate"] <= 0.45 else YEL
                row += f"  {d}:{c(pct(s['fill_rate']),col)}(n={s['n']})"
        print(row)

    # By DTE
    print(f"\n  By Days To Expiry:")
    for gt in ["up","down"]:
        row = f"  Gap {gt.upper()} fill by DTE: "
        for dte in [0,1,2,3]:
            key = f"gap_{gt}_dte{dte}"
            if key in stats:
                s = stats[key]
                col = GRN if s["fill_rate"] >= 0.60 else RED if s["fill_rate"] <= 0.45 else YEL
                row += f"  DTE{dte}:{c(pct(s['fill_rate']),col)}(n={s['n']})"
        print(row)

    # By Regime
    print(f"\n  By Market Regime (ADX-based):")
    for gt in ["up","down"]:
        row = f"  Gap {gt.upper()} fill by Regime: "
        for reg in ["choppy","ranging","mild_trend","trending"]:
            key = f"gap_{gt}_regime_{reg}"
            if key in stats:
                s = stats[key]
                col = GRN if s["fill_rate"] >= 0.60 else RED if s["fill_rate"] <= 0.45 else YEL
                row += f"  {reg}:{c(pct(s['fill_rate']),col)}(n={s['n']})"
        print(row)

    # By VIX
    print(f"\n  By India VIX Zone (low<13, mid 13-20, high>20):")
    for gt in ["up","down"]:
        row = f"  Gap {gt.upper()} fill by VIX: "
        for vz in ["low","mid","high"]:
            key = f"gap_{gt}_vix_{vz}"
            if key in stats:
                s = stats[key]
                col = GRN if s["fill_rate"] >= 0.60 else RED if s["fill_rate"] <= 0.45 else YEL
                row += f"  {vz}:{c(pct(s['fill_rate']),col)}(n={s['n']})"
        print(row)


def print_pdh_report(stats: dict, symbol: str):
    print_section(f"PDH/PDL SWEEP STATISTICS — {symbol}")
    print(f"(5-stage institutional detection: Sweep→Rejection→Displacement→Volume→Follow-through)\n")

    for level in ["PDH","PDL"]:
        key = f"{level}_overall"
        if key not in stats: continue
        s = stats[key]
        print(f"  {c(level, BOLD)} on {s['n_days']} days:")
        print(f"    Days swept:      {s['n_swept']} ({pct(s['sweep_rate'])} of all days)")
        print(f"    Valid reversals: {s['n_valid']} ({pct(s['valid_of_swept'])} of sweeps)")

    # By DOW
    print(f"\n  {c('Sweep rate by DOW',BOLD)}")
    for level in ["PDH","PDL"]:
        row = f"  {level}: "
        for d in ["Mon","Tue","Wed","Thu","Fri"]:
            key = f"{level}_dow_{d}"
            if key in stats:
                s = stats[key]
                col = GRN if s["sweep_rate"] >= 0.35 else DIM
                row += f"  {d}:{c(pct(s['sweep_rate']),col)}→valid:{pct(s['valid_rate'])}"
        print(row)

    # By regime
    print(f"\n  {c('Sweep rate by Regime',BOLD)}")
    for level in ["PDH","PDL"]:
        row = f"  {level}: "
        for reg in ["choppy","ranging","mild_trend","trending"]:
            key = f"{level}_regime_{reg}"
            if key in stats:
                s = stats[key]
                col = GRN if s["valid_rate"] >= 0.30 else DIM
                row += f"  {reg}:{c(pct(s['valid_rate']),col)}(n={s['n']})"
        print(row)

    # Gap + sweep combo
    print(f"\n  {c('Sweep after Gap type (this is the key combo)',BOLD)}")
    for level in ["PDH","PDL"]:
        for gt in ["up","down","flat"]:
            key = f"{level}_after_gap_{gt}"
            if key in stats:
                s = stats[key]
                col = GRN if s["valid_rate"] >= 0.30 else YEL if s["valid_rate"] >= 0.20 else DIM
                print(f"  Gap {gt:4} → {level} sweep: {pct(s['sweep_rate'])} of days | "
                      f"valid reversal: {c(pct(s['valid_rate']),col)} (n={s['n']})")


def print_orb_report(stats: dict, symbol: str):
    print_section(f"ORB STATISTICS — {symbol}")

    for direction in ["long","short"]:
        key = f"orb_{direction}"
        if key not in stats: continue
        s = stats[key]
        print(f"  ORB {direction.upper()}: {s['n']} breakouts | "
              f"Success: {c(pct(s['success_rate']),GRN if s['success_rate']>0.5 else RED)} | "
              f"Fail (SL): {pct(s['fail_rate'])} | Day green: {pct(s['day_green'])}")

    # By range bucket
    print(f"\n  {c('Success rate by ORB Range Size',BOLD)}")
    for rb in ["<30","30-50","50-75","75-100","100-150",">150"]:
        key = f"orb_range_{rb}"
        if key not in stats: continue
        s = stats[key]
        col = GRN if s["success_rate"] >= 0.55 else RED if s["success_rate"] <= 0.40 else YEL
        print(f"  Range {rb:8} pts: {s['n']:4} breakouts  Success: {c(pct(s['success_rate']),col)}  Long%: {pct(s['long_pct'])}")

    # By DOW
    print(f"\n  {c('ORB success by Day of Week',BOLD)}")
    for direction in ["long","short"]:
        row = f"  ORB {direction.upper()}: "
        for d in ["Mon","Tue","Wed","Thu","Fri"]:
            key = f"orb_{direction}_dow_{d}"
            if key in stats:
                s = stats[key]
                col = GRN if s["success_rate"] >= 0.55 else RED if s["success_rate"] <= 0.40 else YEL
                row += f"  {d}:{c(pct(s['success_rate']),col)}(n={s['n']})"
        print(row)

    # By regime
    print(f"\n  {c('ORB success by Regime',BOLD)}")
    for direction in ["long","short"]:
        row = f"  ORB {direction.upper()}: "
        for reg in ["choppy","ranging","mild_trend","trending"]:
            key = f"orb_{direction}_regime_{reg}"
            if key in stats:
                s = stats[key]
                col = GRN if s["success_rate"] >= 0.55 else RED if s["success_rate"] <= 0.40 else YEL
                row += f"  {reg}:{c(pct(s['success_rate']),col)}(n={s['n']})"
        print(row)


def print_expiry_report(stats: dict, symbol: str):
    print_section(f"EXPIRY CONTEXT (DTE) — {symbol}")
    print(f"\n{'DTE':<12} {'N':>5} {'Day Green':>10} {'Gap↑Fill':>10} {'Gap↓Fill':>10} {'Avg Range':>10} {'PDH Sw%':>8}")
    print("─" * 70)
    for dte in sorted(stats.keys(), key=lambda k: int(k.split("_")[1])):
        s = stats[dte]
        gf_up  = pct(s["gap_fill_if_up"])   if s["gap_fill_if_up"]   else "  N/A"
        gf_dn  = pct(s["gap_fill_if_down"]) if s["gap_fill_if_down"] else "  N/A"
        col    = GRN if s["day_green"] >= 0.55 else RED if s["day_green"] <= 0.45 else YEL
        print(f"  {s['label']:<12} {s['n']:>5} {c(pct(s['day_green']),col):>20} "
              f"{gf_up:>10} {gf_dn:>10} "
              f"{s['avg_range']:>10.1f} {pct(s['pdh_sweep']):>8}")


def print_edge_report(edges: list, symbol: str):
    print_section(f"EDGE SCANNER — Top Multi-Condition Combinations — {symbol}")
    print(f"  Showing conditions where outcome rate ≥ 60% or ≤ 35% (n ≥ 25)\n")
    print(f"  {'Conditions':<45} {'Outcome':<12} {'N':>5} {'Rate':>7} {'Edge':>7} {'Dir'}")
    print(f"  {'─'*45} {'─'*12} {'─'*5} {'─'*7} {'─'*7} {'─'*5}")
    for e in edges[:30]:
        col = GRN if e["rate"] >= 0.55 else RED
        print(f"  {e['conditions']:<45} {e['outcome']:<12} {e['n']:>5} "
              f"{c(pct(e['rate']),col):>17} {pct(e['edge']):>7} {e['direction']}")


def print_summary_table(all_results: list):
    """Cross-symbol summary of key metrics."""
    print_section("CROSS-SYMBOL SUMMARY")
    print(f"\n  {'Symbol':<30} {'Days':>5} {'GapUp Fill':>11} {'GapDn Fill':>11} {'ORB Long':>9} {'ORB Short':>10} {'PDH Valid':>10}")
    print(f"  {'─'*30} {'─'*5} {'─'*11} {'─'*11} {'─'*9} {'─'*10} {'─'*10}")
    for r in all_results:
        gu = pct(r["gap_up_fill"])   if r.get("gap_up_fill")   else "  N/A"
        gd = pct(r["gap_dn_fill"])   if r.get("gap_dn_fill")   else "  N/A"
        ol = pct(r["orb_long_succ"]) if r.get("orb_long_succ") else "  N/A"
        os = pct(r["orb_short_succ"])if r.get("orb_short_succ")else "  N/A"
        pv = pct(r["pdh_valid"])     if r.get("pdh_valid")      else "  N/A"
        print(f"  {r['symbol']:<30} {r['days']:>5} "
              f"{c(gu,GRN if r.get('gap_up_fill',0)>=0.55 else YEL):>21} "
              f"{c(gd,GRN if r.get('gap_dn_fill',0)>=0.55 else YEL):>21} "
              f"{ol:>9} {os:>10} {pv:>10}")


# ══════════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS PIPELINE
# ══════════════════════════════════════════════════════════════════════════

PURE_INDEX_SYMBOLS = [
    ("NIFTY 50_MINUTE",   "nifty"),
    ("NIFTY BANK_MINUTE", "banknifty"),
    ("BANKNIFTY",         "banknifty"),
    ("NIFTY",             "nifty"),
    ("NIFTYIT",           "nifty"),
    ("NIFTYMETAL",        "nifty"),
    ("NIFTYPHARMA",       "nifty"),
    ("NIFTYFMCG",         "nifty"),
    ("NIFTYAUTO",         "nifty"),
    ("NIFTYMIDCAP50",     "nifty"),
    ("NIFTYPSUBANK",      "banknifty"),
    ("NIFTYREALTY",       "nifty"),
    ("NIFTYINFRA",        "nifty"),
    ("NIFTYMEDIA",        "nifty"),
    ("NIFTYENERGY",       "nifty"),
]


def analyse_symbol(symbol: str, from_year: int, to_year: int,
                   expiry_class: str = "nifty", run_edge_scan: bool = True,
                   save_db: bool = True) -> dict:

    print(f"\n{BOLD}{CYN}{'▶'*3} Analyzing: {symbol}  [{from_year}–{to_year}]{RST}")

    # 1. Load
    print(f"  Loading minute data...", end=" ")
    min_df = load_minute_data(symbol, from_year, to_year)
    if len(min_df) < 100:
        print(f"{RED}ERROR: insufficient data{RST}")
        return {}
    print(f"{GRN}{len(min_df):,} rows | {min_df['date'].dt.normalize().nunique()} days{RST}")

    # 2. VIX
    vix = load_vix_series()

    # 3. Expiry calendar
    expiry_dates = nse_weekly_expiry_dates(
        expiry_class,
        str(from_year) + "-01-01",
        str(to_year) + "-12-31"
    )

    # 4. Build DNA rows
    print(f"  Building DNA rows...", end=" ", flush=True)
    dna = build_daily_dna(min_df, symbol, vix, expiry_dates)
    if len(dna) < 50:
        print(f"{RED}only {len(dna)} days — skipping{RST}")
        return {}

    # 5. ADX + regime
    dna = add_adx_regime(dna)
    print(f"{GRN}{len(dna)} trading days built{RST}")

    # 6. Save to DuckDB
    if save_db:
        n = save_to_duckdb(dna, symbol)
        print(f"  Saved {n} rows to DuckDB: {DNA_DB}")

    # 7. Statistics
    print(f"  Computing statistics...", flush=True)
    gap_stats    = gap_statistics(dna)
    pdh_stats    = pdh_pdl_statistics(dna)
    orb_stats    = orb_statistics(dna)
    sess_stats   = session_statistics(dna)
    exp_stats    = expiry_statistics(dna)

    # 8. Print reports
    print_gap_report(gap_stats, symbol)
    print_pdh_report(pdh_stats, symbol)
    print_orb_report(orb_stats, symbol)
    print_expiry_report(exp_stats, symbol)

    # Session summary
    print_section(f"SESSION GREEN RATE — {symbol}")
    print(f"  {'Session':<16} {'N':>5} {'Green%':>8} {'Bar'}")
    for name in ["9:15-9:30","9:30-10:00","10:00-11:00","11:00-13:30","13:30-14:30","14:30-15:30"]:
        key = f"session_{name}"
        if key in sess_stats:
            s   = sess_stats[key]
            col = GRN if s["green_rate"] >= 0.55 else RED if s["green_rate"] <= 0.45 else YEL
            print(f"  {name:<16} {s['n']:>5} {c(pct(s['green_rate']),col):>18} {bar(s['green_rate'])}")

    # 9. Edge scan
    edges = []
    if run_edge_scan:
        print(f"  Running edge scanner...", end=" ", flush=True)
        edges = edge_scanner(dna)
        print(f"{GRN}{len(edges)} edges found{RST}")
        print_edge_report(edges, symbol)

    # 10. Summary metrics for cross-symbol table
    summary = {
        "symbol":       symbol,
        "days":         len(dna),
        "gap_up_fill":  gap_stats.get("gap_up_overall",{}).get("fill_rate"),
        "gap_dn_fill":  gap_stats.get("gap_down_overall",{}).get("fill_rate"),
        "orb_long_succ":orb_stats.get("orb_long",{}).get("success_rate"),
        "orb_short_succ":orb_stats.get("orb_short",{}).get("success_rate"),
        "pdh_valid":    pdh_stats.get("PDH_overall",{}).get("valid_of_swept"),
    }

    return summary


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market DNA Engine")
    parser.add_argument("--symbol",       default="NIFTY 50_MINUTE", help="Symbol name")
    parser.add_argument("--from",         dest="from_year", type=int, default=2015)
    parser.add_argument("--to",           dest="to_year",   type=int, default=2022)
    parser.add_argument("--all-indices",  action="store_true", help="Run all pure indices")
    parser.add_argument("--all-equities", action="store_true", help="Run all equities with 5+ years")
    parser.add_argument("--no-edge-scan", action="store_true", help="Skip edge scanner (faster)")
    parser.add_argument("--query",        type=str, help="Run a DuckDB SQL query and print result")
    args = parser.parse_args()

    # Quick SQL query mode
    if args.query:
        result = query_dna(args.query)
        print(result.to_string())
        sys.exit(0)

    summaries = []

    if args.all_indices:
        for sym, exp_class in PURE_INDEX_SYMBOLS:
            # Detect available years
            for subpath in ["indices/minute", "equities/minute"]:
                base = STORE / subpath / sym
                if base.exists():
                    files = sorted([f for f in base.glob("*.parquet") if f.stem.isdigit()])
                    if files:
                        fy = int(files[0].stem)
                        ty = min(int(files[-1].stem), 2022)  # cap at 2022 (real minute data)
                        if ty > fy:
                            s = analyse_symbol(sym, fy, ty, exp_class, not args.no_edge_scan)
                            if s: summaries.append(s)
                        break

    elif args.all_equities:
        eq_min = STORE / "equities" / "minute"
        count  = 0
        for d in sorted(eq_min.iterdir()):
            if d.is_dir():
                files = sorted([f for f in d.glob("*.parquet") if f.stem.isdigit()])
                if len(files) >= 3:
                    fy, ty = int(files[0].stem), int(files[-1].stem)
                    s = analyse_symbol(d.name, fy, ty, "nifty",
                                       run_edge_scan=False)  # skip edge scan for speed
                    if s: summaries.append(s); count += 1
                    if count >= 50: break  # cap at 50 for now

    else:
        s = analyse_symbol(args.symbol, args.from_year, args.to_year,
                           run_edge_scan=not args.no_edge_scan)
        if s: summaries.append(s)

    if len(summaries) > 1:
        print_summary_table(summaries)

    print(f"\n{GRN}{BOLD}Done. DNA database: {DNA_DB}{RST}")
    print(f"Query example: python market_dna.py --query \"SELECT gap_type, COUNT(*) n, AVG(gap_filled::int) fill_rate FROM market_dna WHERE symbol='NIFTY 50_MINUTE' GROUP BY gap_type\"")
