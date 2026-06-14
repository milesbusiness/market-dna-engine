# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from engine import run_backtest, list_symbols, DEFAULTS, STORE

# ── Numpy-safe JSON encoder ────────────────────────────────────────────────
class NumpyProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray):  return obj.tolist()
        if isinstance(obj, np.bool_):    return bool(obj)
        return super().default(obj)

app = Flask(__name__, static_folder="static")
app.json_provider_class = NumpyProvider
app.json = NumpyProvider(app)

# ── Symbol cache ───────────────────────────────────────────────────────────
_symbols = None

def get_symbols():
    global _symbols
    if _symbols is None:
        print("Building symbol list...")
        _symbols = list_symbols()
        print(f"  {len(_symbols)} symbols")
    return _symbols

# ── Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/symbols")
def api_symbols():
    syms = get_symbols()
    q = request.args.get("q", "").upper().strip()
    if q:
        syms = [s for s in syms if q in s["symbol"].upper()]
    # Always put NIFTY 50_MINUTE first
    nifty = [s for s in syms if "NIFTY 50" in s["symbol"]]
    rest  = [s for s in syms if "NIFTY 50" not in s["symbol"]]
    return jsonify(nifty + rest)          # no limit — send all


@app.route("/api/symbol_years")
def api_symbol_years():
    """Return available years for a given symbol."""
    symbol = request.args.get("symbol", "")
    if not symbol:
        return jsonify([])
    syms = get_symbols()
    match = next((s for s in syms if s["symbol"] == symbol), None)
    if not match:
        return jsonify([])
    return jsonify(match["years"])


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    body = request.json or {}
    symbol   = body.get("symbol",   "NIFTY 50_MINUTE")
    strategy = body.get("strategy", "swing")
    from_yr  = int(body.get("from_year", 2018))
    to_yr    = int(body.get("to_year",   2025))

    params = {**DEFAULTS}
    for k in ["orb_minutes","min_orb_range","max_gap_pct","vix_min","vix_max",
              "exit_time","rr_ratio","skip_tuesday","gap_fill_min","gap_fill_max",
              "swing_hold_days","trend_ema_fast","trend_ema_slow","trend_ema_base",
              "lot_size","atr_period"]:
        if k in body:
            try:
                if k in ("skip_tuesday",):
                    params[k] = bool(body[k])
                elif k == "exit_time":
                    params[k] = str(body[k])
                else:
                    params[k] = float(body[k])
            except Exception: pass

    try:
        result = run_backtest(symbol, strategy, from_yr, to_yr, params)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

    return jsonify(result)


@app.route("/api/defaults")
def api_defaults():
    return jsonify(DEFAULTS)


if __name__ == "__main__":
    print("\n" + "="*55)
    print("  TradeScope Backtest Server")
    print("  Open: http://localhost:5050")
    print("="*55 + "\n")
    get_symbols()
    app.run(host="0.0.0.0", port=5050, debug=False)
