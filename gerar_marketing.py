#!/usr/bin/env python3
"""
gerar_marketing.py — gerador diário do data.json de marketing.

Porta fiel de scripts/extract.cjs.

Orquestra:
  1. Lê a planilha (read_sheet_rows) → build_data_from_rows
  2. Determina a janela Meta: lead mais antigo → hoje (fallback 90d se não houver data)
  3. Busca Meta Ads (fetch_meta_window) com retry
  4. Faz merge do chanel (sempre fresco) + campos Meta sobre o snapshot anterior
  5. Escreve docs/data/data.json (indent 2)
  6. Em falha da Meta: restaura campos do data.json anterior (igual ao extract.cjs)

Uso:
  python gerar_marketing.py [--out PATH]

As funções _read_sheet_rows e _fetch_meta_window são atributos do módulo
(não imports fixos) para que os testes possam monkeypatch-á-las sem mock.patch.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from marketing_data.build import (
    build_data_from_rows,
    merge_meta_fields,
    now_iso_date_brt,
    META_FIELDS,
)
from marketing_data.sheets import read_sheet_rows as _real_read_sheet_rows
from marketing_data.meta import fetch_meta_window as _real_fetch_meta_window

# ---------------------------------------------------------------------------
# Injectable data functions (monkeypatchable in tests)
# ---------------------------------------------------------------------------

def _read_sheet_rows(env, **kw):
    return _real_read_sheet_rows(env, **kw)


def _fetch_meta_window(env, window):
    return _real_fetch_meta_window(env, window)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FALLBACK_DAYS = 90
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 3.0  # seconds


def _today_brt() -> str:
    """Current date in BRT (UTC-3) as YYYY-MM-DD."""
    return now_iso_date_brt()


def _with_retry(label: str, fn, attempts: int = _RETRY_ATTEMPTS,
                base_delay: float = _RETRY_BASE_DELAY):
    """Retry fn up to `attempts` times with exponential back-off. Mirrors extract.cjs withRetry."""
    last_err = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if i < attempts:
                delay = base_delay * i
                print(
                    f"AVISO: {label} falhou (tentativa {i}/{attempts}): {e} "
                    f"— repetindo em {delay:.0f}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
    raise last_err


def _load_prev_midia_paga(out_path: str):
    """Load midia_paga from the previous data.json. Returns None if unavailable."""
    try:
        p = Path(out_path)
        if p.exists():
            prev = json.loads(p.read_text(encoding="utf-8"))
            return (prev or {}).get("midia_paga") or None
    except Exception:
        pass
    return None


def _earliest_lead_iso(leads: list) -> str | None:
    """Return the ISO date of the earliest lead (DD/MM/YYYY → YYYY-MM-DD), or None."""
    import re
    earliest = None
    for lead in leads:
        m = re.match(r'^(\d{2})/(\d{2})/(\d{4})', str(lead.get("data", "")))
        if not m:
            continue
        iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        if earliest is None or iso < earliest:
            earliest = iso
    return earliest


def _compute_meta_window(leads: list, today: str) -> dict:
    """
    Determine the Meta fetch window: from the earliest lead date (or 90-day
    fallback if no leads / no parseable date) to today. Mirrors extract.cjs logic.
    """
    from datetime import date, timedelta
    today_dt = date.fromisoformat(today)
    fallback_dt = today_dt - timedelta(days=_FALLBACK_DAYS)
    fallback = fallback_dt.isoformat()

    earliest = _earliest_lead_iso(leads)
    since = earliest if (earliest and earliest < fallback) else fallback
    return {"since": since, "until": today}


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def gerar(
    *,
    env: dict | None = None,
    out_path: str = "docs/data/data.json",
) -> dict:
    """
    Orchestrate the full data generation pipeline and write the result to out_path.

    Parameters
    ----------
    env : dict, optional
        Credentials/config dict (defaults to os.environ).
    out_path : str
        Destination path for the output data.json.

    Returns
    -------
    dict
        The generated data object (same as what is written to disk).
    """
    if env is None:
        env = dict(os.environ)

    sheet_id = env.get("SHEET_ID", "1zNRw8zfoASVlO2EhR56sldTCy4IXRCLKfauU1ROChCE")
    tab = env.get("SHEET_TAB", "LeadsV2")

    # -----------------------------------------------------------------------
    # 1. Load previous midia_paga for fallback
    # -----------------------------------------------------------------------
    prev_midia_paga = _load_prev_midia_paga(out_path)

    # -----------------------------------------------------------------------
    # 2. Read sheet → build base data
    # -----------------------------------------------------------------------
    print(f"Lendo {sheet_id} :: {tab}!A:K ...", file=sys.stderr)
    rows = _read_sheet_rows(env, tab=tab, rng="A:K")

    data = build_data_from_rows(
        rows,
        sheet_id=sheet_id,
        tab=tab,
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    # -----------------------------------------------------------------------
    # 3. Determine Meta window and fetch
    # -----------------------------------------------------------------------
    today = _today_brt()
    window = _compute_meta_window(data["leads"], today)

    print(
        f"Buscando insights diários no Meta Ads ({window['since']} → {window['until']})...",
        file=sys.stderr,
    )

    meta_ok = False
    live_meta: dict = {}
    try:
        live_meta = _with_retry(
            "insights diários da Meta",
            lambda: _fetch_meta_window(env, window),
        )
        meta_ok = True
    except Exception as e:
        print(
            f"AVISO: falha ao buscar Meta Ads ({e}) — seguindo sem gasto.",
            file=sys.stderr,
        )

    # -----------------------------------------------------------------------
    # 4. Merge Meta fields into midia_paga
    #    chanel always comes from the freshly built data (planilha), Meta
    #    financial fields are merged from prev (base) + live on top.
    # -----------------------------------------------------------------------
    chanel_fresh = data["midia_paga"]["chanel"]  # always the live sheet-based chanel

    # merge_meta_fields returns only the Meta financial fields (no chanel)
    merged_meta = merge_meta_fields(prev_midia_paga, live_meta)

    data["midia_paga"] = {"chanel": chanel_fresh, **merged_meta}

    # -----------------------------------------------------------------------
    # 5. Fallback: restore any missing Meta field from previous data.json
    # -----------------------------------------------------------------------
    if prev_midia_paga:
        restored = []
        for field in META_FIELDS:
            if data["midia_paga"].get(field) is None and prev_midia_paga.get(field) is not None:
                data["midia_paga"][field] = prev_midia_paga[field]
                restored.append(field)
        if restored:
            print(
                f"AVISO: reaproveitando dados anteriores da Meta (atualização falhou para): "
                f"{', '.join(restored)}",
                file=sys.stderr,
            )

    # -----------------------------------------------------------------------
    # 6. Write output
    # -----------------------------------------------------------------------
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    n_leads = data["total_leads"]
    n_sql = data["total_sql"]
    sql_pct = data["sql_pct"]
    print(
        f"OK. {n_leads} leads, {n_sql} SQL ({sql_pct}%). Escrito em {out_path}",
        file=sys.stderr,
    )

    return data


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="Gerador diário do data.json de marketing.")
    parser.add_argument(
        "--out",
        default="docs/data/data.json",
        help="Caminho de saída (default: docs/data/data.json)",
    )
    args = parser.parse_args()

    try:
        gerar(out_path=args.out)
    except Exception as e:
        print(f"Falha na extração: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _cli()
