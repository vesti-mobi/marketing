"""test/test_app.py — testes para backend/app.py (P5).

Usa Flask test client; todas as chamadas de rede são injetadas/mockadas.
Verifica:
- GET /api/dados → 200 + JSON com schema esperado
- 2ª chamada → vem do cache (a função de build NÃO é chamada novamente)
- ?fresh=1 → recomputa mesmo dentro do TTL
- GET /api/health → {"status": "ok"}
- erro no build → 503 com JSON {"erro": "..."}
"""
import json
import time

import pytest

pytest.importorskip("flask")

import backend.app as app_module  # noqa: E402

# Dados retornados pelo build simulado
FAKE_DATA = {
    "generated_at": "2026-09-28T12:00:00.000Z",
    "sheet_id": "fake-sheet",
    "sheet_tab": "LeadsV2",
    "total_leads": 2,
    "total_sql": 1,
    "sql_pct": 50.0,
    "perfis": ["Pro", "Starter"],
    "origens": ["Indicação"],
    "perfil_counts": {"Pro": 1, "Starter": 1},
    "origem_counts": {"Indicação": 2},
    "sql_by_origem": {"Indicação": 1},
    "sql_perfis": ["Pro", "Starter", "Qualificado (Sem Faixa)"],
    "etapas": {
        "list": [], "funnel_order": [], "out_of_funnel": [],
        "counts": {}, "by_origem": {}, "by_perfil": {}, "by_month": {},
    },
    "midia_paga": {
        "chanel": {
            "total": 0, "total_sql": 0, "sql_pct": 0,
            "sem_criativo": 0, "sem_anuncio": 0, "pct_sem_criativo": 0,
            "criativos": [], "anuncios": [], "leads": [],
        },
    },
    "leads": [
        {"data": "28/09/2026", "origem": "Indicação", "perfil": "Pro",
         "etapa": "", "data_etapa": "", "formulario": "Não"},
    ],
}


@pytest.fixture(autouse=True)
def reset_cache():
    """Limpa o cache entre testes para isolamento."""
    app_module._cache.clear()
    yield
    app_module._cache.clear()


# ---------------------------------------------------------------------------
# P5-1: GET /api/dados retorna 200 + JSON válido
# ---------------------------------------------------------------------------

def test_dados_returns_200_with_json(monkeypatch):
    """GET /api/dados devolve 200 e JSON com as chaves esperadas."""
    calls = {"n": 0}

    def fake_build(env):
        calls["n"] += 1
        return FAKE_DATA.copy()

    monkeypatch.setattr(app_module, "_build_live", fake_build)

    client = app_module.app.test_client()
    r = client.get("/api/dados")
    assert r.status_code == 200
    body = r.get_json()
    assert body is not None
    assert body["total_leads"] == 2
    assert "midia_paga" in body
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# P5-2: 2ª chamada vem do cache
# ---------------------------------------------------------------------------

def test_dados_second_call_cached(monkeypatch):
    """Segunda chamada dentro do TTL não chama o build novamente."""
    calls = {"n": 0}

    def fake_build(env):
        calls["n"] += 1
        return FAKE_DATA.copy()

    monkeypatch.setattr(app_module, "_build_live", fake_build)

    client = app_module.app.test_client()
    client.get("/api/dados")
    client.get("/api/dados")

    assert calls["n"] == 1, f"Build chamado {calls['n']} vezes; esperava 1 (cache)"


# ---------------------------------------------------------------------------
# P5-3: ?fresh=1 recomputa mesmo dentro do TTL
# ---------------------------------------------------------------------------

def test_dados_fresh_bypasses_cache(monkeypatch):
    """?fresh=1 recomputa mesmo quando há cache fresco."""
    calls = {"n": 0}

    def fake_build(env):
        calls["n"] += 1
        return FAKE_DATA.copy()

    monkeypatch.setattr(app_module, "_build_live", fake_build)

    client = app_module.app.test_client()
    client.get("/api/dados")            # populates cache
    r2 = client.get("/api/dados?fresh=1")  # must recompute

    assert r2.status_code == 200
    assert calls["n"] == 2, f"Build chamado {calls['n']} vezes com ?fresh=1; esperava 2"


# ---------------------------------------------------------------------------
# P5-4: GET /api/health → {"status": "ok"}
# ---------------------------------------------------------------------------

def test_health_endpoint():
    """GET /api/health devolve {"status": "ok"}."""
    client = app_module.app.test_client()
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# P5-5: erro no build → 503 com JSON {"erro": "..."}
# ---------------------------------------------------------------------------

def test_dados_build_error_returns_503(monkeypatch):
    """Quando _build_live lança, GET /api/dados devolve 503 com JSON {"erro": ...}."""
    def bad_build(env):
        raise RuntimeError("conexão recusada")

    monkeypatch.setattr(app_module, "_build_live", bad_build)

    client = app_module.app.test_client()
    r = client.get("/api/dados")
    assert r.status_code == 503
    body = r.get_json()
    assert body is not None
    assert "erro" in body
    assert "conexão recusada" in body["erro"]


# ---------------------------------------------------------------------------
# P5-6: cache expira após TTL (time-travel)
# ---------------------------------------------------------------------------

def test_dados_cache_expires_after_ttl(monkeypatch):
    """Cache expirado (simulado por time-travel) força recompute."""
    calls = {"n": 0}

    def fake_build(env):
        calls["n"] += 1
        return FAKE_DATA.copy()

    monkeypatch.setattr(app_module, "_build_live", fake_build)

    client = app_module.app.test_client()
    client.get("/api/dados")   # first call, populates cache
    assert calls["n"] == 1

    # Force TTL expiry by backdating the cache timestamp
    key = "/api/dados"
    if key in app_module._cache:
        ts, data = app_module._cache[key]
        app_module._cache[key] = (ts - app_module.CACHE_TTL - 1, data)

    client.get("/api/dados")   # cache expired → must recompute
    assert calls["n"] == 2, f"Build chamado {calls['n']} vezes após TTL; esperava 2"
