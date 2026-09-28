"""
test/test_build_parity.py — JS×Python parity test for build_data_from_rows.

Runs a fixed set of diverse synthetic rows through BOTH:
  - JS: node --input-type=module requiring functions/api/_build.js (buildDataFromRows)
  - Python: marketing_data.build.build_data_from_rows

Then asserts the JSON outputs are EQUAL (after normalization to canonical JSON).

The same generated_at/sheet_id/tab are passed to both sides so only the transform
is compared.

Row coverage:
  - mídia paga with criativo+anuncio
  - mídia paga with only anuncio (sem_criativo)
  - mídia paga with only criativo (sem_anuncio)
  - orgânico (non-ad)
  - each etapa (all 6 funnel + all 3 out-of-funnel)
  - SQL perfis (Pro, Starter, Qualificado (Sem Faixa))
  - non-SQL perfis (Desqualificado, Multimarca, Suporte, Em atendimento)
  - typo aliases (desqualficado, qualificado (sem faixa ))
  - etapa aliases (underscore codes)
  - empty fields (empty etapa, empty data)
  - DD/MM/YYYY date for by_month
  - multiple months
  - formulario Sim/Não
"""
import json
import subprocess
import sys
import os
import pytest

# ---------------------------------------------------------------------------
# Synthetic test data
# ---------------------------------------------------------------------------

HEADER = ['DATA', 'ORIGEM', 'PERFIL', 'ETAPA', 'ANUNCIO', 'NOME CRIATIVO', 'FORMULÁRIO', 'Datetime Etapa']

ROWS = [
    HEADER,
    # Mídia paga with criativo+anuncio, SQL perfil Pro, Etapa 1 canonical
    ['01/09/2026', 'Facebook', 'Pro', 'Etapa 1 - inicial', 'Ad Alpha', 'Creative Alpha', 'Sim', '2026-09-01'],
    # Mídia paga with only anuncio (sem_criativo), Starter
    ['02/09/2026', 'Facebook', 'Starter', 'Etapa 2 - Identificado', 'Ad Beta', '', 'Não', ''],
    # Mídia paga with only criativo (sem_anuncio), Qualificado (Sem Faixa)
    ['03/09/2026', 'Google', 'Qualificado (Sem Faixa)', 'etapa_3_concluido', '', 'Creative Beta', 'Sim', '2026-09-03'],
    # Orgânico, non-SQL perfil Desqualificado, Etapa 4
    ['04/09/2026', 'Orgânico', 'Desqualificado', 'Etapa 4 - reunião agendada', '', '', '', ''],
    # Typo alias: desqualficado → Desqualificado, Etapa 5 alias
    ['05/09/2026', 'Indicação', 'desqualficado', 'etapa_5_em_negociacao', '', '', 'Não', ''],
    # Typo alias: qualificado (sem faixa ) → Qualificado (Sem Faixa), Etapa 6
    ['06/09/2026', 'Orgânico', 'qualificado (sem faixa )', 'etapa 6 - ganho', '', '', 'Sim', ''],
    # Out-of-funnel: Etapa cliente alias
    ['07/09/2026', 'Orgânico', 'Multimarca', 'etapa_cliente', '', '', '', ''],
    # Out-of-funnel: Etapa desqualificado alias
    ['08/09/2026', 'Indicação', 'Suporte', 'etapa_0_desqualificado', '', '', '', ''],
    # Out-of-funnel: Etapa perdido alias
    ['09/09/2026', 'Indicação', 'Em atendimento', 'etapa_perdido', '', '', '', ''],
    # Empty etapa and data fields
    ['', 'Orgânico', 'Pro', '', '', '', '', ''],
    # Different month (August)
    ['15/08/2026', 'Orgânico', 'Starter', 'Etapa 1 - inicial', '', '', 'Sim', '2026-08-15'],
    # Mídia paga both criativo and anuncio, non-SQL
    ['20/08/2026', 'Facebook', 'Qualificação_incompleta', 'etapa_2_identificado', 'Ad Gamma', 'Creative Gamma', '', ''],
    # etapa_4 underscore alias
    ['21/08/2026', 'Google', 'Pro', 'etapa_4_reunião_agendada', 'Ad Delta', 'Creative Delta', '', ''],
]

META = {
    'generatedAt': '2026-09-28T00:00:00.000Z',
    'sheetId': 'test_sheet_id',
    'tab': 'LeadsV2',
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_js_build(rows, meta) -> dict:
    """Run buildDataFromRows via node ESM import, return parsed dict."""
    js_rows = json.dumps(rows)
    js_meta = json.dumps(meta)
    script = f"""
import {{ buildDataFromRows }} from './functions/api/_build.js';
const rows = {js_rows};
const meta = {js_meta};
const result = buildDataFromRows(rows, meta);
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        ['node', '--input-type=module'],
        input=script,
        capture_output=True,
        text=True,
        encoding='utf-8',
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    if result.returncode != 0:
        raise RuntimeError(f"node failed: {result.stderr}")
    return json.loads(result.stdout)


def run_py_build(rows, meta) -> dict:
    from marketing_data.build import build_data_from_rows
    return build_data_from_rows(
        rows,
        sheet_id=meta['sheetId'],
        tab=meta['tab'],
        generated_at=meta['generatedAt'],
    )


def normalize_for_compare(d: dict) -> str:
    """Serialize to canonical JSON (sorted keys) for comparison."""
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Parity tests
# ---------------------------------------------------------------------------

class TestParityJsPython:
    def setup_method(self):
        self.js_out = run_js_build(ROWS, META)
        self.py_out = run_py_build(ROWS, META)

    def test_full_output_equal(self):
        """The complete JSON output of JS and Python must be identical."""
        js_str = normalize_for_compare(self.js_out)
        py_str = normalize_for_compare(self.py_out)
        if js_str != py_str:
            # Provide useful diff info
            import json
            js_d = self.js_out
            py_d = self.py_out
            diffs = []
            for k in set(list(js_d.keys()) + list(py_d.keys())):
                if js_d.get(k) != py_d.get(k):
                    diffs.append(f"KEY '{k}':\n  JS: {json.dumps(js_d.get(k))[:300]}\n  PY: {json.dumps(py_d.get(k))[:300]}")
            assert js_str == py_str, "JS/Python mismatch:\n" + "\n".join(diffs)

    def test_total_leads(self):
        # 14 data rows; no empty-rowset skips (all have origem or perfil)
        assert self.js_out['total_leads'] == self.py_out['total_leads']

    def test_total_sql(self):
        assert self.js_out['total_sql'] == self.py_out['total_sql']

    def test_sql_pct(self):
        assert self.js_out['sql_pct'] == self.py_out['sql_pct']

    def test_perfis(self):
        assert self.js_out['perfis'] == self.py_out['perfis']

    def test_origens(self):
        assert self.js_out['origens'] == self.py_out['origens']

    def test_perfil_counts(self):
        assert self.js_out['perfil_counts'] == self.py_out['perfil_counts']

    def test_origem_counts(self):
        assert self.js_out['origem_counts'] == self.py_out['origem_counts']

    def test_sql_by_origem(self):
        assert self.js_out['sql_by_origem'] == self.py_out['sql_by_origem']

    def test_sql_perfis_set_equal(self):
        assert set(self.js_out['sql_perfis']) == set(self.py_out['sql_perfis'])

    def test_etapas_list(self):
        assert self.js_out['etapas']['list'] == self.py_out['etapas']['list']

    def test_etapas_funnel_order(self):
        assert self.js_out['etapas']['funnel_order'] == self.py_out['etapas']['funnel_order']

    def test_etapas_out_of_funnel(self):
        assert self.js_out['etapas']['out_of_funnel'] == self.py_out['etapas']['out_of_funnel']

    def test_etapas_counts(self):
        assert self.js_out['etapas']['counts'] == self.py_out['etapas']['counts']

    def test_etapas_by_origem(self):
        assert self.js_out['etapas']['by_origem'] == self.py_out['etapas']['by_origem']

    def test_etapas_by_perfil(self):
        assert self.js_out['etapas']['by_perfil'] == self.py_out['etapas']['by_perfil']

    def test_etapas_by_month(self):
        assert self.js_out['etapas']['by_month'] == self.py_out['etapas']['by_month']

    def test_midia_paga_chanel_total(self):
        assert self.js_out['midia_paga']['chanel']['total'] == self.py_out['midia_paga']['chanel']['total']

    def test_midia_paga_chanel_total_sql(self):
        assert self.js_out['midia_paga']['chanel']['total_sql'] == self.py_out['midia_paga']['chanel']['total_sql']

    def test_midia_paga_chanel_sql_pct(self):
        assert self.js_out['midia_paga']['chanel']['sql_pct'] == self.py_out['midia_paga']['chanel']['sql_pct']

    def test_midia_paga_chanel_sem_criativo(self):
        assert self.js_out['midia_paga']['chanel']['sem_criativo'] == self.py_out['midia_paga']['chanel']['sem_criativo']

    def test_midia_paga_chanel_sem_anuncio(self):
        assert self.js_out['midia_paga']['chanel']['sem_anuncio'] == self.py_out['midia_paga']['chanel']['sem_anuncio']

    def test_midia_paga_chanel_criativos(self):
        assert self.js_out['midia_paga']['chanel']['criativos'] == self.py_out['midia_paga']['chanel']['criativos']

    def test_midia_paga_chanel_anuncios(self):
        assert self.js_out['midia_paga']['chanel']['anuncios'] == self.py_out['midia_paga']['chanel']['anuncios']

    def test_midia_paga_chanel_leads(self):
        assert self.js_out['midia_paga']['chanel']['leads'] == self.py_out['midia_paga']['chanel']['leads']

    def test_leads(self):
        assert self.js_out['leads'] == self.py_out['leads']
