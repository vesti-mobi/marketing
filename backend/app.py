"""
backend/app.py — Flask backend para o dashboard de marketing.

Espelha o padrão do KPIs (backend/app.py do vesti-pago-kpis), mas com
GET /api/dados ao vivo (planilha + Meta em tempo real) no lugar do POST.

Endpoints:
  GET /api/dados   → computa ao vivo, retorna JSON; TTL cache 10 min;
                     ?fresh=1 força recompute
  GET /api/health  → {"status": "ok"}

Arquitetura:
  - Um worker gunicorn (--workers 1 --threads 4)
  - threading.Lock para proteger o cache
  - Cache in-memory: dict {path: (timestamp, data_dict)}
  - SNAPSHOT_PATH env: caminho para o data.json estático (base do merge Meta)
  - _build_live(env) é um atributo do módulo para ser monkeypatchável em testes
"""

import json
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CACHE_TTL = int(os.environ.get("CACHE_TTL", "600"))  # 10 minutes default
SNAPSHOT_PATH = os.environ.get("SNAPSHOT_PATH", "/var/www/marketing/data/data.json")

# ---------------------------------------------------------------------------
# App + state
# ---------------------------------------------------------------------------

app = Flask(__name__)
_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}  # {path: (ts, data)}


# ---------------------------------------------------------------------------
# Injectable build function (monkeypatchable for tests)
# ---------------------------------------------------------------------------

def _build_live(env: dict) -> dict:
    """
    Compute live data: read sheet → build → fetch Meta (recent window) → merge.
    Mirrors the logic in functions/api/dados.js#build().

    This function is a module-level attribute so tests can monkeypatch it
    without needing mock.patch.
    """
    import datetime as _dt

    from marketing_data.build import (
        build_data_from_rows,
        merge_meta_fields,
        recent_window,
        now_iso_date_brt,
    )
    from marketing_data.sheets import read_sheet_rows
    from marketing_data.meta import fetch_meta_window

    tab = env.get("SHEET_TAB", "LeadsV2")
    sheet_id = env.get("SHEET_ID", "1zNRw8zfoASVlO2EhR56sldTCy4IXRCLKfauU1ROChCE")

    # 1. Reads sheet rows
    rows = read_sheet_rows(env, tab=tab, rng="A:K")

    # 2. Build base data from rows
    data = build_data_from_rows(
        rows,
        sheet_id=sheet_id,
        tab=tab,
        generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
    )

    # 3. Load base snapshot from disk for Meta merge
    base_midia = _load_snapshot_midia_paga()

    # 4. Fetch live Meta (recent window: current month + previous)
    today = now_iso_date_brt()
    win = recent_window(today, 1)
    live_meta: dict = {}
    try:
        live_meta = fetch_meta_window(env, win)
    except Exception:
        # Meta failed → use only base snapshot (same philosophy as dados.js)
        live_meta = {}

    # 5. Merge: chanel always fresh from sheet; Meta financial fields merged
    chanel_fresh = data["midia_paga"]["chanel"]
    merged_meta = merge_meta_fields(base_midia, live_meta)
    data["midia_paga"] = {"chanel": chanel_fresh, **merged_meta}

    return data


def _load_snapshot_midia_paga():
    """Load midia_paga from the on-disk snapshot. Returns None on any failure."""
    try:
        p = Path(SNAPSHOT_PATH)
        if p.exists():
            snap = json.loads(p.read_text(encoding="utf-8"))
            return (snap or {}).get("midia_paga") or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/dados")
def dados():
    """Return live marketing data JSON, with TTL cache."""
    env = dict(os.environ)
    cache_key = "/api/dados"
    fresh = request.args.get("fresh") == "1"

    with _lock:
        now = time.time()
        if not fresh and cache_key in _cache:
            ts, cached_data = _cache[cache_key]
            if now - ts < CACHE_TTL:
                return jsonify(cached_data)

        # Compute live
        try:
            data = _build_live(env)
        except Exception as e:
            return jsonify({"erro": str(e)}), 503

        _cache[cache_key] = (time.time(), data)
        return jsonify(data)


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})
