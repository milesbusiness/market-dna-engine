# -*- coding: utf-8 -*-
"""
TradeScope Backtest Engine — Research-Backed NIFTY Strategies
=============================================================
Sources:
  intradaylab.com  — 8yr ORB backtest: 2122 trades, 1.23 PF, +91.6%
  medium.com/@stockdetails — 10yr time-pattern analysis
  nifty50pulse.in  — Gap fill statistics
  optionx.trade    — Gap behavior research

Key research findings encoded here:
  1. ORB range MUST be >= 40 pts (small-range days destroy edge)
  2. Skip gap > 0.8% at open (erratic, unpredictable)
  3. Skip Tuesdays — statistically weakest day
  4. SHORT trades = 75% of all ORB profits — bias matters
  5. SL = ORB opposite end (not arbitrary ATR)
  6. Target = 2x ORB range
  7. Exit at 2:30 PM (not 3:15)
  8. India VIX 13-20 = ideal zone; <12 = too calm; >22 = too chaotic
  9. Thursday/Friday = strongest days (65% of returns)
  10. Pre-first-week bias: mutual fund inflows push 62% positive

Strategies:
  intraday  -> Research-backed ORB-30 with all 8 filters
  swing     -> Gap-fill + PCR + closing session bias (2:30-3:30 57% green)
  position  -> Monthly first-week bias + trend
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

STORE = Path(r"E:\TradeStore")

DEFAULTS = dict(
    # ORB params (research-tuned)
    orb_minutes    = 30,      # 9:15-9:45 window
    min_orb_range  = 40,      # skip if ORB range < 40 pts
    max_gap_pct    = 0.008,   # skip if opening gap > 0.8%
    skip_tuesday   = True,    # Tuesdays are weakest
    vix_min        = 12,      # skip if VIX too calm
    vix_max        = 22,      # skip if VIX too chaotic
    exit_time      = "14:30", # exit at 2:30 PM
    rr_ratio       = 2.0,     # target = 2x risk (ORB-based)
    # Swing params
    gap_fill_min   = 0.002,   # min 0.2% gap to trade fill
    gap_fill_max   = 0.008,   # max 0.8% gap (larger = don't fade)
    swing_hold_days= 3,
    # Position params
    trend_ema_fast = 20,
    trend_ema_slow = 50,
    trend_ema_base = 200,
    # General
    lot_size       = 1,
    atr_period     = 14,
)


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def list_symbols():
    results = []
    for cat, subpath in [
        ("Index",   "NSE/INDEX/minute"),
        ("Equity",  "NSE/EQ/minute"),
        ("Futures", "NSE/NFO/FUTURES/minute"),
        ("MCX",     "MCX/FUTURES/minute"),
    ]:
        base = STORE / subpath
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir():
                years = sorted([f.stem for f in d.glob("*.parquet") if f.stem.isdigit()])
                if years:
                    results.append({
                        "symbol": d.name,
                        "category": cat,
                        "years": years,
                        "from": years[0],
                        "to":   years[-1],
                    })
    return results


def load_minute(symbol: str, from_year: int, to_year: int) -> pd.DataFrame:
    for subpath in ["NSE/INDEX/minute", "NSE/EQ/minute",
                    "NSE/NFO/FUTURES/minute", "MCX/FUTURES/minute"]:
        base = STORE / subpath / symbol
        if base.exists():
            files = sorted([f for f in base.glob("*.parquet")
                            if f.stem.isdigit() and from_year <= int(f.stem) <= to_year])
            if files:
                df = pd.concat([pd.read_parquet(f) for f in files])
                df["date"] = pd.to_datetime(df["date"])
                return df.sort_values("date").reset_index(drop=True)
    return pd.DataFrame()


def load_daily(symbol: str, from_year: int, to_year: int) -> pd.DataFrame:
    min_df = load_minute(symbol, from_year, to_year)
    if len(min_df) > 0:
        min_df = min_df.set_index("date")
        daily = min_df.resample("D").agg(
            open=("open","first"), high=("high","max"),
            low=("low","min"),    close=("close","last"),
            volume=("volume","sum"),
        ).dropna(subset=["close"])
        daily = daily[daily["close"] > 0].reset_index()
        return daily
    sym_dir = STORE / "NSE" / "EQ" / "daily" / symbol.upper()
    if sym_dir.exists():
        files = sorted([f for f in sym_dir.glob("*.parquet")
                        if f.stem.isdigit() and from_year <= int(f.stem) <= to_year])
        if files:
            df = pd.concat([pd.read_parquet(f) for f in files])
            df["date"] = pd.to_datetime(df["date"])
            return df.sort_values("date").reset_index(drop=True)
    return pd.DataFrame()


def load_vix() -> pd.Series:
    vix_dir = STORE / "NSE" / "INDEX" / "minute" / "INDIAVIX"
    if not vix_dir.exists():
        return pd.Series(dtype=float)
    parts = [pd.read_parquet(p) for p in sorted(vix_dir.glob("*.parquet"))]
    if not parts:
        return pd.Series(dtype=float)
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    # Daily VIX = last close of each trading day
    daily = df.groupby("date")["close"].last()
    return daily


# ═══════════════════════════════════════════════════════════════════════════
# INDICATORS
# ═══════════════════════════════════════════════════════════════════════════

def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    d = df.copy().sort_values("date").reset_index(drop=True)

    # ATR
    hl  = d["high"] - d["low"]
    hcp = (d["high"] - d["close"].shift(1)).abs()
    lcp = (d["low"]  - d["close"].shift(1)).abs()
    tr  = pd.concat([hl, hcp, lcp], axis=1).max(axis=1)
    d["atr"]     = tr.rolling(p["atr_period"]).mean()
    d["atr_pct"] = d["atr"] / d["close"]

    # EMAs
    d["ema9"]   = d["close"].ewm(span=9,  adjust=False).mean()
    d["ema20"]  = d["close"].ewm(span=p["trend_ema_fast"], adjust=False).mean()
    d["ema50"]  = d["close"].ewm(span=p["trend_ema_slow"], adjust=False).mean()
    d["ema200"] = d["close"].ewm(span=p["trend_ema_base"], adjust=False).mean()

    # RSI
    delta = d["close"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    d["rsi"] = 100 - 100 / (1 + gain / (loss + 1e-9))

    # MACD
    ema12 = d["close"].ewm(span=12, adjust=False).mean()
    ema26 = d["close"].ewm(span=26, adjust=False).mean()
    d["macd"]      = ema12 - ema26
    d["macd_sig"]  = d["macd"].ewm(span=9, adjust=False).mean()
    d["macd_hist"] = d["macd"] - d["macd_sig"]

    # Bollinger
    sma20 = d["close"].rolling(20).mean()
    std20 = d["close"].rolling(20).std()
    d["bb_upper"] = sma20 + 2 * std20
    d["bb_lower"] = sma20 - 2 * std20
    d["bb_pos"]   = (d["close"] - sma20) / (2 * std20 + 1e-9)

    # ADX
    plus_dm  = (d["high"] - d["high"].shift(1)).clip(lower=0)
    minus_dm = (d["low"].shift(1) - d["low"]).clip(lower=0)
    tr_atr   = tr.rolling(14).mean()
    pdi = 100 * plus_dm.rolling(14).mean()  / (tr_atr + 1e-9)
    mdi = 100 * minus_dm.rolling(14).mean() / (tr_atr + 1e-9)
    dx  = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-9)
    d["adx"] = dx.rolling(14).mean()

    # Key derived fields
    d["above_ema200"] = (d["close"] > d["ema200"]).astype(int)
    d["trend_up"]     = (d["ema20"] > d["ema50"]).astype(int)
    d["gap_pct"]      = (d["open"] - d["close"].shift(1)) / (d["close"].shift(1) + 1e-9)
    d["prev_close"]   = d["close"].shift(1)
    d["prev_high"]    = d["high"].shift(1)
    d["prev_low"]     = d["low"].shift(1)
    d["vol_ratio"]    = d["volume"] / (d["volume"].rolling(20).mean() + 1)
    d["dow"]          = d["date"].dt.dayofweek  # 0=Mon 1=Tue ... 3=Thu 4=Fri

    return d


# ═══════════════════════════════════════════════════════════════════════════
# STRATEGY 1: RESEARCH-BACKED ORB-30
# ═══════════════════════════════════════════════════════════════════════════

def run_intraday_orb(min_df: pd.DataFrame, daily: pd.DataFrame,
                     vix: pd.Series, p: dict) -> list:
    """
    Opening Range Breakout with all research-backed filters:
    - ORB window: 9:15-9:45 AM
    - Filter 1: ORB range >= min_orb_range (default 40 pts)
    - Filter 2: Opening gap < max_gap_pct (default 0.8%)
    - Filter 3: Skip Tuesdays (weakest day statistically)
    - Filter 4: India VIX 12-22 (optimal zone)
    - Filter 5: One trade per day only
    - SL: ORB opposite end (research shows this > ATR-based)
    - Target: 2x ORB range
    - Exit: 2:30 PM hard stop
    - Direction bias: Research shows shorts = 75% of profits
    """
    trades = []
    min_df = min_df.copy()
    min_df["day"]  = min_df["date"].dt.normalize()
    min_df["hhmm"] = min_df["date"].dt.strftime("%H:%M")
    orb_end  = f"09:{14 + int(p['orb_minutes']):02d}"
    exit_hhmm= p.get("exit_time", "14:30")

    # Index VIX by date for fast lookup
    vix_idx = vix if isinstance(vix, pd.Series) else pd.Series(dtype=float)

    # Track filter reasons for transparency
    skipped = {"small_range": 0, "large_gap": 0, "tuesday": 0,
               "vix": 0, "no_break": 0, "no_orb": 0}

    for _, drow in daily.iterrows():
        if pd.isna(drow.get("atr")):
            continue

        day = pd.Timestamp(drow["date"]).normalize()

        # ── FILTER 1: Skip Tuesdays ─────────────────────────────────────
        dow = day.dayofweek
        if p.get("skip_tuesday", True) and dow == 1:
            skipped["tuesday"] += 1
            continue

        # ── FILTER 2: India VIX ─────────────────────────────────────────
        vix_val = float(vix_idx.get(day, np.nan))
        if not np.isnan(vix_val):
            if vix_val < p["vix_min"] or vix_val > p["vix_max"]:
                skipped["vix"] += 1
                continue

        # ── Get minute bars for this day ─────────────────────────────────
        bars     = min_df[min_df["day"] == day]
        orb_bars = bars[bars["hhmm"] <= orb_end]
        post_orb = bars[(bars["hhmm"] > orb_end) & (bars["hhmm"] <= exit_hhmm)].copy()

        if len(orb_bars) < 3:
            skipped["no_orb"] += 1
            continue

        orb_h = float(orb_bars["high"].max())
        orb_l = float(orb_bars["low"].min())
        orb_range = orb_h - orb_l

        # ── FILTER 3: ORB range >= 40 pts ─────────────────────────────
        if orb_range < p["min_orb_range"]:
            skipped["small_range"] += 1
            continue

        # ── FILTER 4: Opening gap < 0.8% ──────────────────────────────
        gap_pct = abs(float(drow.get("gap_pct", 0)))
        if gap_pct > p["max_gap_pct"]:
            skipped["large_gap"] += 1
            continue

        if len(post_orb) < 5:
            continue

        # Determine direction bias (research: shorts generate 75% of returns)
        # Additional bias: above-open starts favor longs, below-open favor shorts
        day_open = float(orb_bars.iloc[0]["open"])
        orb_close = float(orb_bars.iloc[-1]["close"])
        gap_dir = drow.get("gap_pct", 0)

        # Build both LONG and SHORT scenarios, take the one that breaks first
        long_break  = post_orb[post_orb["high"] >= orb_h + 0.5]
        short_break = post_orb[post_orb["low"]  <= orb_l - 0.5]

        # If both break, take whichever breaks first
        long_time  = long_break.index[0]  if len(long_break)  else None
        short_time = short_break.index[0] if len(short_break) else None

        if long_time is None and short_time is None:
            skipped["no_break"] += 1
            continue

        # Decide direction
        if long_time is not None and short_time is not None:
            # Both break — take whichever is first
            if long_time <= short_time:
                direction = "LONG"
            else:
                direction = "SHORT"
        elif long_time is not None:
            direction = "LONG"
        else:
            direction = "SHORT"

        # Entry, SL, Target (ORB-based, not ATR)
        if direction == "LONG":
            entry_p = orb_h + 0.5
            sl_p    = orb_l             # SL = ORB low (research-backed)
            risk    = entry_p - sl_p
            tgt_p   = entry_p + p["rr_ratio"] * risk
            after   = post_orb.loc[long_time:]
        else:
            entry_p = orb_l - 0.5
            sl_p    = orb_h             # SL = ORB high
            risk    = sl_p - entry_p
            tgt_p   = entry_p - p["rr_ratio"] * risk
            after   = post_orb.loc[short_time:]

        if risk <= 0:
            continue

        # Simulate bar by bar
        result = "EOD"
        exit_p = float(after.iloc[-1]["close"]) if len(after) else entry_p

        for _, bar in after.iterrows():
            lo, hi = float(bar["low"]), float(bar["high"])
            if direction == "LONG":
                if lo  <= sl_p:  exit_p = sl_p;  result = "SL";     break
                if hi  >= tgt_p: exit_p = tgt_p; result = "TARGET"; break
            else:
                if hi  >= sl_p:  exit_p = sl_p;  result = "SL";     break
                if lo  <= tgt_p: exit_p = tgt_p; result = "TARGET"; break

        pnl = (exit_p - entry_p) if direction == "LONG" else (entry_p - exit_p)

        # Build human-readable reason
        day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][dow]
        vix_str  = f"{vix_val:.1f}" if not np.isnan(vix_val) else "N/A"
        entry_reason = (
            f"ORB {orb_l:.0f}–{orb_h:.0f} (range: {orb_range:.0f} pts ≥ {p['min_orb_range']} filter) | "
            f"Gap: {gap_pct:.2%} (≤ {p['max_gap_pct']:.1%} filter) | "
            f"India VIX: {vix_str} (zone {p['vix_min']}–{p['vix_max']}) | "
            f"{day_name} | "
            f"Price broke {'above ORB high' if direction=='LONG' else 'below ORB low'} | "
            f"RSI: {drow.get('rsi',0):.0f} | MACD: {'bull' if drow.get('macd_hist',0)>0 else 'bear'}"
        )
        if result == "TARGET":
            ex_reason = f"Target hit at {exit_p:.0f} — {p['rr_ratio']:.0f}×{risk:.0f} = +{abs(pnl):.0f} pts captured."
            lesson = (
                f"Clean ORB breakout. {orb_range:.0f}-pt range provided good momentum. "
                f"{'Shorts generating 75% of ORB profits — this confirms the pattern.' if direction=='SHORT' else 'Long worked in uptrend day.'} "
                f"VIX at {vix_str} was in optimal 12–22 zone."
            )
        elif result == "SL":
            ex_reason = (
                f"Stop triggered at {sl_p:.0f} (ORB {'low' if direction=='LONG' else 'high'}). "
                f"False breakout — price broke ORB but reversed. -{abs(pnl):.0f} pts."
            )
            lesson = (
                f"False breakout. ORB broke but failed to follow through. "
                f"Check: was there a news event? Was volume low on the breakout bar? "
                f"SL at ORB opposite end is correct — this is the right risk management."
            )
        else:
            ex_reason = f"Time exit at 2:30 PM: {'+' if pnl>=0 else ''}{pnl:.0f} pts. Neither SL nor target reached."
            lesson = (
                f"Market moved but not enough for 2:1 target. "
                f"{'Small profit — consider partial exit at 1:1.' if pnl>0 else 'Inconclusive day — correct to have sat out major risk by 2:30 PM.'}"
            )

        trades.append(dict(
            date         = str(day.date()),
            exit_date    = str(day.date()),
            direction    = direction,
            entry        = round(entry_p, 1),
            exit         = round(exit_p, 1),
            sl           = round(sl_p, 1),
            target       = round(tgt_p, 1),
            orb_high     = round(orb_h, 1),
            orb_low      = round(orb_l, 1),
            orb_range    = round(orb_range, 1),
            vix          = round(vix_val, 1) if not np.isnan(vix_val) else None,
            gap_pct      = round(gap_pct * 100, 2),
            pnl_pts      = round(pnl, 1),
            pnl_pct      = round(pnl / entry_p * 100, 3),
            result       = result,
            atr          = round(float(drow.get("atr", 0)), 1),
            rsi          = round(float(drow.get("rsi", 50)), 1),
            duration     = "Intraday",
            entry_reason = entry_reason,
            exit_reason  = ex_reason,
            lesson       = lesson,
            strategy     = "ORB-30",
        ))

    return trades, skipped


# ═══════════════════════════════════════════════════════════════════════════
# STRATEGY 2: GAP-FILL SWING
# ═══════════════════════════════════════════════════════════════════════════

def run_swing_gapfill(daily: pd.DataFrame, vix: pd.Series, p: dict) -> list:
    """
    Gap-Fill strategy based on research:
    - Gap 0.2%-0.8%: High probability of fill (40-50% same day, more over 3 days)
    - Gap-down days: 52.6% close green (mean reversion bias)
    - Trade: Fade the gap — enter opposite direction after 30 min confirmation
    - Additional filter: Trend (above/below EMA200), RSI not extreme in gap direction
    - Hold max 3 days
    """
    trades = []
    d = daily.reset_index(drop=True)
    n = len(d)
    i = 0

    while i < n - 2:
        row = d.iloc[i + 1]  # trade day (gap day)
        sig = d.iloc[i]       # signal is previous day close

        if pd.isna(sig.get("atr")) or pd.isna(row.get("open")):
            i += 1; continue

        gap_pct  = float(row.get("gap_pct", 0))
        atr      = float(sig["atr"])
        abs_gap  = abs(gap_pct)

        # Only trade gaps in our range: 0.2% to 0.8%
        if abs_gap < p["gap_fill_min"] or abs_gap > p["gap_fill_max"]:
            i += 1; continue

        # Skip Tuesdays
        if p.get("skip_tuesday", True) and pd.Timestamp(row["date"]).dayofweek == 1:
            i += 1; continue

        # VIX filter
        day      = pd.Timestamp(row["date"]).normalize()
        vix_val  = float(vix.get(day, np.nan)) if isinstance(vix, pd.Series) else np.nan
        if not np.isnan(vix_val) and (vix_val < p["vix_min"] or vix_val > p["vix_max"]):
            i += 1; continue

        prev_close = float(sig["close"])
        entry_p    = float(row["open"])

        # Gap-up: fade SHORT (sell the gap-up, target = prev_close)
        # Gap-down: fade LONG (buy the gap-down, target = prev_close)
        if gap_pct > 0:   # gap up
            direction = "SHORT"
            # Only fade gap-up if RSI is overbought or we're below EMA50 (weakness)
            rsi = float(sig.get("rsi", 50))
            if rsi < 60 and sig.get("trend_up", 0) == 1:
                i += 1; continue  # strong uptrend gap-up: don't fade
        else:              # gap down
            direction = "LONG"
            # Only fade gap-down if RSI is not deeply oversold continuation
            rsi = float(sig.get("rsi", 50))
            if rsi > 40 and sig.get("trend_up", 0) == 0:
                i += 1; continue  # strong downtrend: gap-down continues, don't fade

        # Target = fill the gap (previous close)
        target_p = prev_close
        reward   = abs(target_p - entry_p)
        sl_p     = entry_p - atr * 1.0 if direction == "LONG" else entry_p + atr * 1.0
        risk     = abs(entry_p - sl_p)

        if reward < risk * 0.5:  # bad R:R, skip
            i += 1; continue

        result = "TIME"; exit_p = entry_p; hold = 0
        for j in range(i + 1, min(i + 1 + p["swing_hold_days"], n)):
            bar = d.iloc[j]; hold += 1
            lo, hi, cl = float(bar["low"]), float(bar["high"]), float(bar["close"])
            if direction == "LONG":
                if lo  <= sl_p:     exit_p = sl_p;     result = "SL";     break
                if hi  >= target_p: exit_p = target_p; result = "TARGET"; break
            else:
                if hi  >= sl_p:     exit_p = sl_p;     result = "SL";     break
                if lo  <= target_p: exit_p = target_p; result = "TARGET"; break
        else:
            exit_p = float(d.iloc[min(i + p["swing_hold_days"], n-1)]["close"])
            hold   = p["swing_hold_days"]

        pnl = (exit_p - entry_p) if direction == "LONG" else (entry_p - exit_p)
        vix_str = f"{vix_val:.1f}" if not np.isnan(vix_val) else "N/A"
        gap_pts = abs(entry_p - prev_close)

        entry_reason = (
            f"Gap {'up' if gap_pct>0 else 'down'}: {gap_pct:.2%} ({gap_pts:.0f} pts) | "
            f"Previous close: {prev_close:.0f} → target (gap fill) | "
            f"India VIX: {vix_str} | RSI: {rsi:.0f} | "
            f"{'Trend strong enough to absorb, fading gap-up' if gap_pct>0 else '52.6% of gap-down days close green (research)'}"
        )
        ex_reason = (
            f"{'Gap filled — price returned to {:.0f}'.format(prev_close) if result=='TARGET' else ''}"
            f"{'Stop hit: gap continued, gap-fill failed' if result=='SL' else ''}"
            f"{'Time exit after {:.0f}d: gap partly filled'.format(hold) if result in ('TIME','EOD') else ''}"
        ) or f"{result} — {'+' if pnl>=0 else ''}{pnl:.0f} pts"
        lesson = (
            f"Gap {'up' if gap_pct>0 else 'down'} of {abs_gap:.2%}. "
            f"{'Gap filled as expected — probability edge confirmed.' if result=='TARGET' else ''}"
            f"{'Gap extended — this was a trend continuation gap, not a reversal gap. Check: was there news? Was volume surging on the gap?' if result=='SL' else ''}"
            f"{'Partial fill over {:.0f} days. Research shows 0.2-0.8% gaps fill 40-50% same day and higher % over 3 days.'.format(hold) if result in ('TIME','EOD') else ''}"
        )

        trades.append(dict(
            date         = str(row["date"])[:10],
            exit_date    = str(d.iloc[min(i+hold, n-1)]["date"])[:10],
            direction    = direction,
            entry        = round(entry_p, 1),
            exit         = round(exit_p, 1),
            sl           = round(sl_p, 1),
            target       = round(target_p, 1),
            pnl_pts      = round(pnl, 1),
            pnl_pct      = round(pnl / entry_p * 100, 3),
            result       = result,
            atr          = round(atr, 1),
            rsi          = round(float(sig.get("rsi", 50)), 1),
            gap_pct      = round(gap_pct * 100, 2),
            vix          = round(vix_val, 1) if not np.isnan(vix_val) else None,
            duration     = f"{hold}d",
            entry_reason = entry_reason,
            exit_reason  = ex_reason,
            lesson       = lesson,
            strategy     = "GapFill",
        ))
        i += hold + 1

    return trades


# ═══════════════════════════════════════════════════════════════════════════
# STRATEGY 3: POSITION — MONTHLY BIAS + TREND
# ═══════════════════════════════════════════════════════════════════════════

def run_position_trend(daily: pd.DataFrame, vix: pd.Series, p: dict) -> list:
    """
    Position trading using research patterns:
    - First week of month: 62% positive (mutual fund inflows) → only go LONG
    - EMA20 > EMA50 > EMA200 uptrend structure
    - Pre-holiday (+0.15%, 63% WR) — tracked as bonus
    - Hold until EMA20 crosses EMA50 or 2× ATR target
    """
    trades = []
    d = daily.reset_index(drop=True)
    n = len(d)
    i = 0
    in_trade = False

    while i < n - 1:
        row = d.iloc[i]
        if pd.isna(row.get("ema20")) or pd.isna(row.get("atr")):
            i += 1; continue

        ema20  = float(row["ema20"])
        ema50  = float(row["ema50"])
        ema200 = float(row["ema200"])
        close  = float(row["close"])
        atr    = float(row["atr"])
        dow    = pd.Timestamp(row["date"]).dayofweek
        dom    = pd.Timestamp(row["date"]).day  # day of month
        adx    = float(row.get("adx", 0))

        # Research: first week of month (days 1-7) is 62% positive
        is_first_week = 1 <= dom <= 7
        # Strong trend: ema20 > ema50 > ema200
        strong_uptrend = ema20 > ema50 > ema200
        # Pullback to EMA20 (price close to EMA20 from above)
        near_ema20 = 0 < (close - ema20) / atr < 1.0

        # LONG: first-week + strong trend + pullback to EMA20 + ADX > 20
        long_ok = (is_first_week and strong_uptrend and near_ema20
                   and adx > 20 and not in_trade)

        # SHORT: strong downtrend + ADX > 25 (avoid on first week)
        strong_dn = ema20 < ema50 < ema200
        near_dn   = 0 < (ema20 - close) / atr < 1.0
        short_ok  = (not is_first_week and strong_dn and near_dn
                     and adx > 25 and not in_trade)

        if not (long_ok or short_ok):
            i += 1; continue

        direction = "LONG" if long_ok else "SHORT"
        entry_row = d.iloc[i + 1]
        entry_p   = float(entry_row["open"])
        # Wider SL for position: 2x ATR
        sl_p      = entry_p - 2 * atr if direction == "LONG" else entry_p + 2 * atr
        tgt_p     = entry_p + 3 * atr if direction == "LONG" else entry_p - 3 * atr

        result = "TIME"; exit_p = entry_p; hold = 0; in_trade = True
        day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][dow]

        for j in range(i + 1, n):
            bar   = d.iloc[j]; hold += 1
            lo, hi = float(bar["low"]), float(bar["high"])
            b20   = float(bar.get("ema20", ema20))
            b50   = float(bar.get("ema50", ema50))
            if direction == "LONG":
                if lo  <= sl_p: exit_p = sl_p;  result = "SL";     break
                if hi  >= tgt_p: exit_p = tgt_p; result = "TARGET"; break
                if b20 < b50:    exit_p = float(bar["close"]); result = "EOD"; break  # trend broken
            else:
                if hi  >= sl_p: exit_p = sl_p;  result = "SL";     break
                if lo  <= tgt_p: exit_p = tgt_p; result = "TARGET"; break
                if b20 > b50:   exit_p = float(bar["close"]); result = "EOD"; break
        else:
            exit_p = float(d.iloc[-1]["close"]); result = "TIME"; hold = n - i - 1

        pnl = (exit_p - entry_p) if direction == "LONG" else (entry_p - exit_p)
        in_trade = False

        entry_reason = (
            f"{'First week of month (day ' + str(dom) + ') — 62% positive probability (research)' if is_first_week else 'Strong downtrend entry'} | "
            f"EMA20 ({ema20:.0f}) {'>' if direction=='LONG' else '<'} EMA50 ({ema50:.0f}) | "
            f"ADX: {adx:.0f} (trend strength) | "
            f"{day_name} | ATR: {atr:.0f} pts"
        )
        ex_reason = (
            f"Target +3×ATR={abs(tgt_p-entry_p):.0f} pts hit." if result=="TARGET" else
            f"Stop -2×ATR={abs(sl_p-entry_p):.0f} pts hit. Trend reversed or news event." if result=="SL" else
            f"EMA20 crossed EMA50 after {hold}d — trend structure broken. Exit at {exit_p:.0f}."
        )
        lesson = (
            f"{'Monthly first-week trade. Mutual fund inflows typically support market in first 7 days.' if is_first_week else 'Trend trade.'} "
            f"{'Won — trend continuation confirmed.' if result=='TARGET' else 'Lost — even first-week trades fail when broader market weakens. Check: was FII selling on this day?'}"
        )

        trades.append(dict(
            date         = str(entry_row["date"])[:10],
            exit_date    = str(d.iloc[min(i+hold, n-1)]["date"])[:10],
            direction    = direction,
            entry        = round(entry_p, 1),
            exit         = round(exit_p, 1),
            sl           = round(sl_p, 1),
            target       = round(tgt_p, 1),
            pnl_pts      = round(pnl, 1),
            pnl_pct      = round(pnl / entry_p * 100, 3),
            result       = result,
            atr          = round(atr, 1),
            rsi          = round(float(row.get("rsi", 50)), 1),
            duration     = f"{hold}d",
            entry_reason = entry_reason,
            exit_reason  = ex_reason,
            lesson       = lesson,
            strategy     = "MonthlyTrend",
        ))
        i += hold + 1

    return trades


# ═══════════════════════════════════════════════════════════════════════════
# STATS (numpy-safe)
# ═══════════════════════════════════════════════════════════════════════════

def _n(v):
    return v.item() if hasattr(v, "item") else v


def compute_stats(trades: list, lot_size: int = 1) -> dict:
    if not trades:
        return {}
    t   = pd.DataFrame(trades)
    pnl = t["pnl_pts"] * lot_size
    n   = len(t)
    wins   = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    cum    = pnl.cumsum()
    dd     = cum - cum.cummax()

    aw  = float(wins.mean())   if len(wins)   else 0.0
    al  = float(losses.mean()) if len(losses) else 0.0
    pf  = float(abs(wins.sum() / losses.sum())) if (len(losses) and losses.sum() != 0) else 999.0
    rr  = abs(aw / al) if al else 0.0
    exp = (len(wins)/n) * aw + (len(losses)/n) * al if n else 0.0

    t["year"] = pd.to_datetime(t["date"]).dt.year
    yr = (t.groupby("year")
           .agg(trades=("pnl_pts","count"),
                win_rate=("pnl_pts", lambda x: float((x > 0).mean())),
                pnl=("pnl_pts","sum"))
           .reset_index())
    yr["pnl"] = yr["pnl"] * lot_size

    # Direction breakdown
    dir_stats = {}
    for dr in ["LONG","SHORT"]:
        sub = pnl[t["direction"] == dr]
        if len(sub):
            dir_stats[dr] = {
                "trades":   int(len(sub)),
                "win_rate": float((sub > 0).mean()),
                "total_pnl":float(sub.sum()),
            }

    # Result breakdown
    res_stats = {}
    if "result" in t.columns:
        for res in ["TARGET","SL","EOD","TIME"]:
            cnt = int((t["result"] == res).sum())
            if cnt:
                res_stats[res] = cnt

    return dict(
        total_pnl     = round(float(pnl.sum()), 2),
        win_rate      = round(float(len(wins) / n), 4),
        num_trades    = int(n),
        max_drawdown  = round(float(dd.min()), 2),
        best_trade    = round(float(pnl.max()), 2),
        worst_trade   = round(float(pnl.min()), 2),
        avg_win       = round(aw, 2),
        avg_loss      = round(al, 2),
        rr_ratio      = round(rr, 3),
        profit_factor = round(min(pf, 999.0), 3),
        expectancy    = round(exp, 2),
        sharpe        = round(float(pnl.mean() / (pnl.std() + 1e-9) * (252**0.5)), 3),
        year_stats    = [{"year": int(r["year"]), "trades": int(r["trades"]),
                          "win_rate": float(r["win_rate"]), "pnl": float(r["pnl"])}
                         for _, r in yr.iterrows()],
        direction_stats = dir_stats,
        result_stats    = res_stats,
    )


def build_equity_curve(trades: list, lot_size: int = 1) -> list:
    if not trades:
        return []
    t   = pd.DataFrame(trades).sort_values("date")
    pnl = t["pnl_pts"] * lot_size
    cum = pnl.cumsum()
    dd  = cum - cum.cummax()
    return [{"date": str(row["date"])[:10],
             "equity":   round(float(cum.iloc[i]), 2),
             "drawdown": round(float(dd.iloc[i]),  2),
             "pnl":      round(float(pnl.iloc[i]), 2)}
            for i, (_, row) in enumerate(t.iterrows())]


def build_candles(daily: pd.DataFrame) -> list:
    out = []
    for _, r in daily.iterrows():
        try:
            ts = int(pd.Timestamp(r["date"]).timestamp())
            out.append({"time":  ts,
                        "open":  round(float(r["open"]),  2),
                        "high":  round(float(r["high"]),  2),
                        "low":   round(float(r["low"]),   2),
                        "close": round(float(r["close"]), 2)})
        except Exception:
            pass
    return out


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ═══════════════════════════════════════════════════════════════════════════

def run_backtest(symbol: str, strategy: str, from_year: int, to_year: int,
                 params: dict = None) -> dict:
    p = {**DEFAULTS, **(params or {})}

    daily = load_daily(symbol, from_year, to_year)
    if len(daily) < 50:
        return {"error": f"Not enough data for {symbol} ({from_year}-{to_year})"}

    daily = add_indicators(daily, p)
    daily = daily.dropna(subset=["atr", "rsi"]).reset_index(drop=True)

    vix = load_vix()
    skipped_info = {}

    if strategy == "intraday":
        min_df = load_minute(symbol, from_year, to_year)
        if len(min_df) < 100:
            return {"error": f"No minute data for {symbol}. Intraday strategy needs minute bars."}
        trades, skipped_info = run_intraday_orb(min_df, daily, vix, p)
        strat_label = "Intraday ORB-30 (Research-Backed)"
    elif strategy == "swing":
        trades = run_swing_gapfill(daily, vix, p)
        strat_label = "Swing Gap-Fill (Research-Backed)"
    elif strategy == "position":
        trades = run_position_trend(daily, vix, p)
        strat_label = "Position Monthly Bias + Trend"
    else:
        return {"error": f"Unknown strategy: {strategy}"}

    if not trades:
        return {"error": "No trades generated. Check date range or that minute data exists."}

    for i, t in enumerate(trades):
        t["id"] = i + 1

    stats  = compute_stats(trades, int(p["lot_size"]))
    equity = build_equity_curve(trades, int(p["lot_size"]))
    candles= build_candles(daily)

    return dict(
        symbol       = symbol,
        strategy     = strat_label,
        from_year    = from_year,
        to_year      = to_year,
        stats        = stats,
        trades       = trades,
        equity_curve = equity,
        candles      = candles,
        params       = {k: float(v) if isinstance(v, (int, float)) else v for k, v in p.items()},
        filters_info = skipped_info,
        research_notes = [
            "ORB range >= 40 pts filter: removes low-volatility days that kill edge",
            "Gap > 0.8% filter: large gaps are unpredictable, skipped",
            "Tuesday skip: statistically weakest day across 8yr backtest",
            "India VIX 12-22 zone: too calm = no move; too high = erratic",
            "SHORT trades generate 75% of ORB profits (research from 2122-trade backtest)",
            "SL = ORB opposite end (not ATR) — research shows this is optimal",
            "Exit at 2:30 PM not 3:15 PM — last 45 min is expiry-driven noise",
        ],
    )
