"""test/test_gerar.py — testes para gerar_marketing.py (P4).

Os testes injetam read_sheet_rows e fetch_meta_window para evitar qualquer
chamada de rede (Google Sheets / Meta). Verificam:
- schema esperado no dict retornado por gerar()
- escrita do arquivo JSON com indent 2
- fallback Meta: quando fetch_meta_window lança, campos Meta vindos do arquivo anterior
- janela completa: desde o lead mais antigo (ou 90d fallback) até hoje
"""
import json
import os
import tempfile

import pytest

# Linhas sintéticas que satisfazem o header padrão
FAKE_HEADER = [
    "DATA", "ORIGEM", "PERFIL", "ETAPA", "ANUNCIO", "NOME CRIATIVO",
    "FORMULARIO", "Datetime Etapa", "X", "Y", "Z",
]
FAKE_ROWS = [
    FAKE_HEADER,
    ["01/06/2026", "Indicação", "Pro", "Etapa 1 - inicial", "", "", "Sim", "01/06/2026", "", "", ""],
    ["15/08/2026", "Orgânico", "Starter", "Etapa 2 - Identificado", "", "", "Não", "", "", "", ""],
    ["10/09/2026", "Mídia paga", "Desqualificado", "Etapa desqualificado", "Ad1", "Criativo1", "", "", "", "", ""],
]

FAKE_META = {
    "spend_daily": {"Ad1": {"2026-09-10": 99.99}},
    "impressions_daily": {"Ad1": {"2026-09-10": 1000}},
    "reach_daily": {"Ad1": {"2026-09-10": 800}},
    "new_msg_contacts_daily": {"Ad1": {"2026-09-10": 5}},
    "spend_window": {"since": "2026-06-01", "until": "2026-09-28"},
    "reach_monthly": {"Ad1": {"2026-09": 800}},
    "thumbnails": {},
    "ad_campaign": {},
    "ad_adset": {},
    "campaigns": [],
}

TOP_LEVEL_KEYS = [
    "generated_at", "sheet_id", "sheet_tab",
    "total_leads", "total_sql", "sql_pct",
    "perfis", "origens", "perfil_counts", "origem_counts",
    "sql_by_origem", "sql_perfis",
    "etapas", "midia_paga", "leads",
]


def _import_gerar():
    import gerar_marketing
    return gerar_marketing


# ---------------------------------------------------------------------------
# P4-1: schema e arquivo
# ---------------------------------------------------------------------------

def test_gerar_returns_expected_schema(tmp_path, monkeypatch):
    """gerar() com dados injetados devolve dict com todas as chaves top-level."""
    gerar = _import_gerar()
    out_file = tmp_path / "data.json"

    monkeypatch.setattr(gerar, "_read_sheet_rows", lambda env, **kw: FAKE_ROWS)
    monkeypatch.setattr(gerar, "_fetch_meta_window", lambda env, window: FAKE_META)

    result = gerar.gerar(
        env={"SHEET_ID": "fake-sheet", "SHEET_TAB": "LeadsV2"},
        out_path=str(out_file),
    )

    for key in TOP_LEVEL_KEYS:
        assert key in result, f"Chave '{key}' ausente no resultado"

    assert result["total_leads"] == 3
    assert result["sheet_id"] == "fake-sheet"
    assert result["sheet_tab"] == "LeadsV2"
    assert isinstance(result["leads"], list)
    assert isinstance(result["midia_paga"], dict)
    assert "chanel" in result["midia_paga"]


def test_gerar_writes_json_with_indent2(tmp_path, monkeypatch):
    """gerar() escreve o arquivo JSON com indent 2."""
    gerar = _import_gerar()
    out_file = tmp_path / "data.json"

    monkeypatch.setattr(gerar, "_read_sheet_rows", lambda env, **kw: FAKE_ROWS)
    monkeypatch.setattr(gerar, "_fetch_meta_window", lambda env, window: FAKE_META)

    gerar.gerar(
        env={"SHEET_ID": "fake-sheet", "SHEET_TAB": "LeadsV2"},
        out_path=str(out_file),
    )

    assert out_file.exists(), "data.json não foi criado"
    raw = out_file.read_text(encoding="utf-8")
    # indent 2: every key at top level is preceded by 2 spaces
    assert '  "generated_at"' in raw
    # valid JSON
    parsed = json.loads(raw)
    assert "total_leads" in parsed


def test_gerar_creates_parent_dirs(tmp_path, monkeypatch):
    """gerar() cria os diretórios pais do arquivo de saída."""
    gerar = _import_gerar()
    out_file = tmp_path / "docs" / "data" / "data.json"

    monkeypatch.setattr(gerar, "_read_sheet_rows", lambda env, **kw: FAKE_ROWS)
    monkeypatch.setattr(gerar, "_fetch_meta_window", lambda env, window: FAKE_META)

    gerar.gerar(
        env={"SHEET_ID": "x", "SHEET_TAB": "LeadsV2"},
        out_path=str(out_file),
    )
    assert out_file.exists()


# ---------------------------------------------------------------------------
# P4-2: meta fields overlay
# ---------------------------------------------------------------------------

def test_gerar_meta_fields_in_midia_paga(tmp_path, monkeypatch):
    """Campos Meta (spend_daily etc.) aparecem em midia_paga depois do merge."""
    gerar = _import_gerar()
    out_file = tmp_path / "data.json"

    monkeypatch.setattr(gerar, "_read_sheet_rows", lambda env, **kw: FAKE_ROWS)
    monkeypatch.setattr(gerar, "_fetch_meta_window", lambda env, window: FAKE_META)

    result = gerar.gerar(env={"SHEET_ID": "x"}, out_path=str(out_file))

    mp = result["midia_paga"]
    assert "spend_daily" in mp
    assert "impressions_daily" in mp
    assert "spend_window" in mp


# ---------------------------------------------------------------------------
# P4-3: fallback Meta — restore from previous data.json on failure
# ---------------------------------------------------------------------------

def test_gerar_meta_failure_restores_from_prev(tmp_path, monkeypatch):
    """Quando fetch_meta_window lança, campos Meta são restaurados do arquivo anterior."""
    gerar = _import_gerar()
    out_file = tmp_path / "data.json"

    # Write a previous data.json with Meta fields
    prev = {
        "generated_at": "2026-09-27T00:00:00.000Z",
        "sheet_id": "x", "sheet_tab": "LeadsV2",
        "total_leads": 0, "total_sql": 0, "sql_pct": 0,
        "perfis": [], "origens": [], "perfil_counts": {}, "origem_counts": {},
        "sql_by_origem": {}, "sql_perfis": [],
        "etapas": {"list": [], "funnel_order": [], "out_of_funnel": [],
                   "counts": {}, "by_origem": {}, "by_perfil": {}, "by_month": {}},
        "midia_paga": {
            "chanel": {"total": 0, "total_sql": 0, "sql_pct": 0,
                       "sem_criativo": 0, "sem_anuncio": 0, "pct_sem_criativo": 0,
                       "criativos": [], "anuncios": [], "leads": []},
            "spend_daily": {"OldAd": {"2026-09-26": 55.0}},
            "thumbnails": {"OldAd": "http://thumb.example.com/old.jpg"},
        },
        "leads": [],
    }
    out_file.write_text(json.dumps(prev, indent=2), encoding="utf-8")

    def bad_meta(env, window):
        raise RuntimeError("Meta API down")

    monkeypatch.setattr(gerar, "_read_sheet_rows", lambda env, **kw: FAKE_ROWS)
    monkeypatch.setattr(gerar, "_fetch_meta_window", bad_meta)

    result = gerar.gerar(env={"SHEET_ID": "x"}, out_path=str(out_file))

    mp = result["midia_paga"]
    # spend_daily should be restored from previous data.json
    assert "spend_daily" in mp, "spend_daily não foi restaurado do data.json anterior"
    assert mp["spend_daily"] == {"OldAd": {"2026-09-26": 55.0}}
    assert "thumbnails" in mp


# ---------------------------------------------------------------------------
# P4-4: window from earliest lead date
# ---------------------------------------------------------------------------

def test_gerar_window_from_earliest_lead(tmp_path, monkeypatch):
    """A janela Meta parte do lead mais antigo (ou 90d fallback, o que for mais cedo)."""
    gerar = _import_gerar()
    out_file = tmp_path / "data.json"

    captured = {}

    def capture_window(env, window):
        captured["window"] = window
        return {}

    monkeypatch.setattr(gerar, "_read_sheet_rows", lambda env, **kw: FAKE_ROWS)
    monkeypatch.setattr(gerar, "_fetch_meta_window", capture_window)

    gerar.gerar(env={"SHEET_ID": "x"}, out_path=str(out_file))

    assert "window" in captured
    w = captured["window"]
    # The earliest lead is 01/06/2026 → 2026-06-01
    # today (mocked or real) > 90d ago, so since must be 2026-06-01
    assert "since" in w and "until" in w
    # since should be at or before 2026-06-01
    assert w["since"] <= "2026-06-01"
