"""
test/test_build.py — TDD Step 1 (RED): tests for marketing_data/build.py
Covers: header discovery, perfil/etapa canonicalization, mídia paga reclassification,
all aggregations, midia_paga.chanel, finalize_list precision/sort, recent_window,
merge_meta_fields.
"""
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_header():
    return ['DATA', 'ORIGEM', 'PERFIL', 'ETAPA', 'ANUNCIO', 'NOME CRIATIVO', 'FORMULÁRIO', 'Datetime Etapa']


def make_row(data='01/09/2026', origem='Orgânico', perfil='Pro', etapa='Etapa 1 - inicial',
             anuncio='', criativo='', formulario='', data_etapa=''):
    return [data, origem, perfil, etapa, anuncio, criativo, formulario, data_etapa]


# ---------------------------------------------------------------------------
# Tests for normalize
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_strips_whitespace(self):
        from marketing_data.build import normalize
        assert normalize('  hello  ') == 'hello'

    def test_collapses_inner_spaces(self):
        from marketing_data.build import normalize
        assert normalize('hello   world') == 'hello world'

    def test_empty_string(self):
        from marketing_data.build import normalize
        assert normalize('') == ''

    def test_none(self):
        from marketing_data.build import normalize
        assert normalize(None) == ''

    def test_converts_to_string(self):
        from marketing_data.build import normalize
        assert normalize(42) == '42'


# ---------------------------------------------------------------------------
# Tests for canonical_perfil
# ---------------------------------------------------------------------------

class TestCanonicalPerfil:
    def test_empty(self):
        from marketing_data.build import canonical_perfil
        assert canonical_perfil('') == ''

    def test_none(self):
        from marketing_data.build import canonical_perfil
        assert canonical_perfil(None) == ''

    def test_typo_desqualficado(self):
        from marketing_data.build import canonical_perfil
        # typo alias: 'desqualficado' → 'Desqualificado'
        assert canonical_perfil('desqualficado') == 'Desqualificado'

    def test_typo_qualificado_sem_faixa_space(self):
        from marketing_data.build import canonical_perfil
        # trailing space alias
        assert canonical_perfil('qualificado (sem faixa )') == 'Qualificado (Sem Faixa)'

    def test_typo_qualificado_sem_faixa_no_space(self):
        from marketing_data.build import canonical_perfil
        assert canonical_perfil('qualificado (sem faixa)') == 'Qualificado (Sem Faixa)'

    def test_known_perfil_case_insensitive(self):
        from marketing_data.build import canonical_perfil
        assert canonical_perfil('pro') == 'Pro'
        assert canonical_perfil('STARTER') == 'Starter'
        assert canonical_perfil('multimarca') == 'Multimarca'

    def test_known_perfil_exact(self):
        from marketing_data.build import canonical_perfil
        assert canonical_perfil('Pro') == 'Pro'
        assert canonical_perfil('Starter') == 'Starter'

    def test_unknown_passthrough(self):
        from marketing_data.build import canonical_perfil
        assert canonical_perfil('Algum Perfil Novo') == 'Algum Perfil Novo'


# ---------------------------------------------------------------------------
# Tests for canonical_etapa
# ---------------------------------------------------------------------------

class TestCanonicalEtapa:
    def test_empty(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('') == ''

    def test_alias_etapa_1_underscore(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa_1_inicial') == 'Etapa 1 - inicial'

    def test_alias_etapa_2_space(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa 2') == 'Etapa 2 - Identificado'

    def test_alias_etapa_3_concluido_no_accent(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa 3 - concluido') == 'Etapa 3 - concluído'

    def test_alias_etapa_3_concluido_underscore(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa_3_concluido') == 'Etapa 3 - concluído'

    def test_alias_etapa_4_reuniao_underscore(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa_4_reuniao_agendada') == 'Etapa 4 - reunião agendada'

    def test_alias_etapa_5_negociacao_underscore(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa_5_em_negociacao') == 'Etapa 5 - em negociação'

    def test_alias_etapa_6_ganho(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa 6 - ganho') == 'Etapa 6 - Ganho'

    def test_alias_etapa_cliente_underscore(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa_cliente') == 'Etapa cliente'

    def test_alias_etapa_0_cliente(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa_0_cliente') == 'Etapa cliente'

    def test_alias_etapa_desqualificado(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa_desqualificado') == 'Etapa desqualificado'

    def test_alias_etapa_perdido(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('etapa_0_perdido') == 'Etapa perdido'

    def test_exact_funnel_label_passthrough(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('Etapa 1 - inicial') == 'Etapa 1 - inicial'

    def test_unknown_passthrough(self):
        from marketing_data.build import canonical_etapa
        assert canonical_etapa('Etapa X - custom') == 'Etapa X - custom'


# ---------------------------------------------------------------------------
# Tests for header discovery
# ---------------------------------------------------------------------------

class TestHeaderDiscovery:
    def test_header_discovery_standard(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row()]
        result = build_data_from_rows(rows, sheet_id='sid', tab='LeadsV2', generated_at='2026-09-28T00:00:00Z')
        assert result['total_leads'] == 1

    def test_formulario_detected_by_pattern(self):
        """Column 'formulário' is found by /formul/i regex."""
        from marketing_data.build import build_data_from_rows
        header = ['DATA', 'ORIGEM', 'PERFIL', 'ETAPA', 'ANUNCIO', 'NOME CRIATIVO', 'formulário', 'Datetime Etapa']
        rows = [header, make_row(formulario='Sim')]
        result = build_data_from_rows(rows, sheet_id='sid', tab='LeadsV2', generated_at='2026-09-28')
        lead = result['leads'][0]
        assert lead['formulario'] == 'Sim'

    def test_data_etapa_fallback_to_col_10(self):
        """dataEtapa falls back to index 10 when header length > 10 and no match."""
        from marketing_data.build import build_data_from_rows
        # Build 11-column header without datetime etapa keyword
        header = ['DATA', 'ORIGEM', 'PERFIL', 'ETAPA', 'ANUNCIO', 'NOME CRIATIVO', 'FORMULÁRIO', 'COL8', 'COL9', 'COL10', 'DATA_ETAPA_VAL']
        row = ['01/09/2026', 'Orgânico', 'Pro', 'Etapa 1 - inicial', '', '', '', '', '', '', '2026-09-01']
        rows = [header, row]
        result = build_data_from_rows(rows, sheet_id='sid', tab='LeadsV2', generated_at='2026-09-28')
        assert result['leads'][0]['data_etapa'] == '2026-09-01'

    def test_missing_origem_raises(self):
        from marketing_data.build import build_data_from_rows
        header = ['DATA', 'PERFIL', 'ETAPA']  # no ORIGEM
        rows = [header, ['01/09/2026', 'Pro', 'Etapa 1 - inicial']]
        with pytest.raises(Exception, match='[Hh]eader|ORIGEM|esperado'):
            build_data_from_rows(rows, sheet_id='sid', tab='LeadsV2', generated_at='2026-09-28')

    def test_missing_perfil_raises(self):
        from marketing_data.build import build_data_from_rows
        header = ['DATA', 'ORIGEM', 'ETAPA']  # no PERFIL
        rows = [header, ['01/09/2026', 'Orgânico', 'Etapa 1 - inicial']]
        with pytest.raises(Exception, match='[Hh]eader|PERFIL|esperado'):
            build_data_from_rows(rows, sheet_id='sid', tab='LeadsV2', generated_at='2026-09-28')

    def test_empty_rows_raises(self):
        from marketing_data.build import build_data_from_rows
        with pytest.raises(Exception):
            build_data_from_rows([], sheet_id='sid', tab='LeadsV2', generated_at='2026-09-28')

    def test_only_header_no_data_rows(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header()]
        with pytest.raises(Exception):
            build_data_from_rows(rows, sheet_id='sid', tab='LeadsV2', generated_at='2026-09-28')


# ---------------------------------------------------------------------------
# Tests for reclassification: mídia paga
# ---------------------------------------------------------------------------

class TestMidiaPagaReclassification:
    def test_with_anuncio_reclassified(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row(origem='Indicação', anuncio='Ad XYZ')]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['leads'][0]['origem'] == 'Mídia paga'

    def test_with_criativo_reclassified(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row(origem='Orgânico', criativo='Creative A')]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['leads'][0]['origem'] == 'Mídia paga'

    def test_without_anuncio_and_criativo_keeps_origem(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row(origem='Orgânico', anuncio='', criativo='')]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['leads'][0]['origem'] == 'Orgânico'

    def test_rawOrigem_preserved_in_chanel_leads(self):
        """chanel.leads preserves rawOrigem (before reclassification)."""
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row(origem='Indicação', anuncio='Ad XYZ')]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        chanel_leads = result['midia_paga']['chanel']['leads']
        assert len(chanel_leads) == 1
        assert chanel_leads[0]['origem'] == 'Indicação'  # rawOrigem


# ---------------------------------------------------------------------------
# Tests for aggregations
# ---------------------------------------------------------------------------

class TestAggregations:
    def _rows_two_leads(self):
        header = make_header()
        rows = [
            header,
            make_row(origem='Orgânico', perfil='Pro', etapa='Etapa 1 - inicial', data='01/09/2026'),
            make_row(origem='Indicação', perfil='Desqualificado', etapa='Etapa 2 - Identificado', data='15/09/2026'),
        ]
        return rows

    def test_total_leads(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['total_leads'] == 2

    def test_perfil_counts(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['perfil_counts']['Pro'] == 1
        assert result['perfil_counts']['Desqualificado'] == 1

    def test_origem_counts(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['origem_counts']['Orgânico'] == 1
        assert result['origem_counts']['Indicação'] == 1

    def test_total_sql_only_sql_perfis(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # Only Pro is SQL; Desqualificado is not
        assert result['total_sql'] == 1

    def test_sql_by_origem(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['sql_by_origem']['Orgânico'] == 1
        assert 'Indicação' not in result['sql_by_origem']

    def test_sql_pct_calculation(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # 1/2 * 100 = 50.0
        assert result['sql_pct'] == 50.0

    def test_etapas_counts(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['etapas']['counts']['Etapa 1 - inicial'] == 1
        assert result['etapas']['counts']['Etapa 2 - Identificado'] == 1

    def test_etapas_by_origem(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        by_origem = result['etapas']['by_origem']
        assert by_origem['Orgânico']['Etapa 1 - inicial'] == 1
        assert by_origem['Indicação']['Etapa 2 - Identificado'] == 1

    def test_etapas_by_perfil(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        by_perfil = result['etapas']['by_perfil']
        assert by_perfil['Pro']['Etapa 1 - inicial'] == 1
        assert by_perfil['Desqualificado']['Etapa 2 - Identificado'] == 1

    def test_etapas_by_month_dd_mm_yyyy(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        by_month = result['etapas']['by_month']
        # Both rows in September 2026
        assert '2026-09' in by_month
        assert by_month['2026-09']['Etapa 1 - inicial'] == 1
        assert by_month['2026-09']['Etapa 2 - Identificado'] == 1

    def test_etapas_funnel_order_in_output(self):
        from marketing_data.build import build_data_from_rows
        rows = self._rows_two_leads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # funnel_order should be complete list from JS
        fo = result['etapas']['funnel_order']
        assert fo[0] == 'Etapa 1 - inicial'
        assert fo[5] == 'Etapa 6 - Ganho'

    def test_etapas_list_ordering(self):
        """Funnel etapas come before out-of-funnel."""
        from marketing_data.build import build_data_from_rows
        header = make_header()
        rows = [
            header,
            make_row(etapa='Etapa cliente', perfil='Pro'),
            make_row(etapa='Etapa 3 - concluído', perfil='Starter'),
        ]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        lst = result['etapas']['list']
        # Etapa 3 (funnel) should come before Etapa cliente (out-of-funnel)
        assert lst.index('Etapa 3 - concluído') < lst.index('Etapa cliente')

    def test_perfis_order_matches_known_perfis(self):
        """perfis list follows KNOWN_PERFIS order for known perfis."""
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row(perfil='Starter'), make_row(perfil='Pro')]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # Pro is index 0 in KNOWN_PERFIS, Starter is index 1
        assert result['perfis'].index('Pro') < result['perfis'].index('Starter')

    def test_origens_sorted_pt_br(self):
        from marketing_data.build import build_data_from_rows
        rows = [
            make_header(),
            make_row(origem='Orgânico'),
            make_row(origem='Indicação'),
            make_row(origem='Anuncio'),
        ]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        origens = result['origens']
        # Should be sorted pt-BR locale (Anuncio < Indicação < Orgânico alphabetically)
        assert len(origens) == 3
        # At minimum the list should be consistent/sorted
        assert origens == sorted(origens, key=lambda x: x)

    def test_skip_empty_rows(self):
        """Rows with no rawOrigem and no perfil are skipped."""
        from marketing_data.build import build_data_from_rows
        header = make_header()
        rows = [
            header,
            make_row(origem='Orgânico', perfil='Pro'),
            ['', '', '', '', '', '', '', ''],  # empty row
        ]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['total_leads'] == 1

    def test_formulario_sim(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row(formulario='SIM')]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['leads'][0]['formulario'] == 'Sim'

    def test_formulario_not_sim(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row(formulario='')]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['leads'][0]['formulario'] == 'Não'

    def test_meta_fields_in_output(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row()]
        result = build_data_from_rows(rows, sheet_id='my_id', tab='LeadsV2', generated_at='2026-09-28T12:00:00Z')
        assert result['generated_at'] == '2026-09-28T12:00:00Z'
        assert result['sheet_id'] == 'my_id'
        assert result['sheet_tab'] == 'LeadsV2'

    def test_sql_perfis_exported(self):
        from marketing_data.build import build_data_from_rows
        rows = [make_header(), make_row()]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # sql_perfis is a list
        assert isinstance(result['sql_perfis'], list)
        assert set(result['sql_perfis']) == {'Pro', 'Starter', 'Qualificado (Sem Faixa)'}


# ---------------------------------------------------------------------------
# Tests for midia_paga.chanel
# ---------------------------------------------------------------------------

class TestMidiaPagaChanel:
    def _make_rows_with_ads(self):
        header = make_header()
        return [
            header,
            make_row(origem='Facebook', perfil='Pro', anuncio='Ad A', criativo='Creative X'),
            make_row(origem='Facebook', perfil='Starter', anuncio='Ad A', criativo='Creative X'),
            make_row(origem='Facebook', perfil='Desqualificado', anuncio='Ad B', criativo=''),
            make_row(origem='Google', perfil='Pro', anuncio='', criativo='Creative Y'),
            make_row(origem='Orgânico', perfil='Pro'),  # non-ad
        ]

    def test_chanel_total(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # 4 rows have anuncio or criativo
        assert result['midia_paga']['chanel']['total'] == 4

    def test_chanel_total_sql(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # Pro (row1) + Starter (row2) + Pro (row4) = 3 SQL
        assert result['midia_paga']['chanel']['total_sql'] == 3

    def test_chanel_sql_pct(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # 3/4 = 75.0
        assert result['midia_paga']['chanel']['sql_pct'] == 75.0

    def test_chanel_sem_criativo(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # row3 has anuncio but no criativo
        assert result['midia_paga']['chanel']['sem_criativo'] == 1

    def test_chanel_sem_anuncio(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        # row4 has criativo but no anuncio
        assert result['midia_paga']['chanel']['sem_anuncio'] == 1

    def test_criativos_list_structure(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        criativos = result['midia_paga']['chanel']['criativos']
        assert isinstance(criativos, list)
        # Should have Creative X and Creative Y
        names = [c['name'] for c in criativos]
        assert 'Creative X' in names
        assert 'Creative Y' in names

    def test_criativos_sql_pct(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        criativos = result['midia_paga']['chanel']['criativos']
        cx = next(c for c in criativos if c['name'] == 'Creative X')
        # 2 total (Pro + Starter), 2 SQL → 100.0
        assert cx['total'] == 2
        assert cx['sql'] == 2
        assert cx['sql_pct'] == 100.0

    def test_criativos_by_perfil(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        criativos = result['midia_paga']['chanel']['criativos']
        cx = next(c for c in criativos if c['name'] == 'Creative X')
        assert cx['by_perfil']['Pro'] == 1
        assert cx['by_perfil']['Starter'] == 1

    def test_chanel_leads_rawOrigem(self):
        from marketing_data.build import build_data_from_rows
        rows = self._make_rows_with_ads()
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        leads = result['midia_paga']['chanel']['leads']
        # All leads should have their raw origem (Facebook/Google, not 'Mídia paga')
        origens = {l['origem'] for l in leads}
        assert 'Facebook' in origens or 'Google' in origens
        assert 'Mídia paga' not in origens

    def test_anuncios_list_sorted_by_total_desc(self):
        from marketing_data.build import build_data_from_rows
        header = make_header()
        rows = [
            header,
            make_row(anuncio='Ad B', criativo='C1'),
            make_row(anuncio='Ad A', criativo='C2'),
            make_row(anuncio='Ad A', criativo='C3'),
        ]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        anuncios = result['midia_paga']['chanel']['anuncios']
        # Ad A should come first (2 total > Ad B's 1)
        assert anuncios[0]['name'] == 'Ad A'
        assert anuncios[1]['name'] == 'Ad B'


# ---------------------------------------------------------------------------
# Tests for finalize_list precision and sort
# ---------------------------------------------------------------------------

class TestFinalizeList:
    def test_sql_pct_rounded_to_2_decimals(self):
        from marketing_data.build import build_data_from_rows
        # 1 SQL out of 3 = 33.333...% → rounds to 33.33
        header = make_header()
        rows = [
            header,
            make_row(anuncio='Ad A', perfil='Pro'),
            make_row(anuncio='Ad A', perfil='Desqualificado'),
            make_row(anuncio='Ad A', perfil='Desqualificado'),
        ]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        anuncios = result['midia_paga']['chanel']['anuncios']
        a = anuncios[0]
        assert a['sql_pct'] == round(100 * 1 / 3, 2)

    def test_sql_pct_zero_when_no_total(self):
        """Empty map → empty list (no division by zero)."""
        from marketing_data.build import build_data_from_rows
        # If only non-ad leads, chanel lists should be empty
        rows = [make_header(), make_row(origem='Orgânico')]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        assert result['midia_paga']['chanel']['criativos'] == []
        assert result['midia_paga']['chanel']['anuncios'] == []

    def test_sorted_desc_by_total(self):
        from marketing_data.build import build_data_from_rows
        header = make_header()
        rows = [
            header,
            make_row(criativo='Low', perfil='Pro'),
            make_row(criativo='High', perfil='Pro'),
            make_row(criativo='High', perfil='Starter'),
        ]
        result = build_data_from_rows(rows, sheet_id='s', tab='t', generated_at='x')
        criativos = result['midia_paga']['chanel']['criativos']
        assert criativos[0]['name'] == 'High'
        assert criativos[1]['name'] == 'Low'


# ---------------------------------------------------------------------------
# Tests for recent_window
# ---------------------------------------------------------------------------

class TestRecentWindow:
    def test_one_month_back(self):
        from marketing_data.build import recent_window
        result = recent_window('2026-09-28', 1)
        assert result == {'since': '2026-08-01', 'until': '2026-09-28'}

    def test_two_months_back(self):
        from marketing_data.build import recent_window
        result = recent_window('2026-09-28', 2)
        assert result == {'since': '2026-07-01', 'until': '2026-09-28'}

    def test_default_is_one_month(self):
        from marketing_data.build import recent_window
        result = recent_window('2026-09-28')
        assert result == {'since': '2026-08-01', 'until': '2026-09-28'}

    def test_crosses_year_boundary(self):
        from marketing_data.build import recent_window
        result = recent_window('2026-01-15', 1)
        assert result == {'since': '2025-12-01', 'until': '2026-01-15'}

    def test_crosses_year_boundary_two_months(self):
        from marketing_data.build import recent_window
        result = recent_window('2026-02-28', 2)
        assert result == {'since': '2025-12-01', 'until': '2026-02-28'}


# ---------------------------------------------------------------------------
# Tests for merge_meta_fields
# ---------------------------------------------------------------------------

class TestMergeMetaFields:
    def test_series_union_live_wins_overlapping_keys(self):
        from marketing_data.build import merge_meta_fields
        base = {'spend_daily': {'ad1': {'2026-09-01': 10.0}, 'ad2': {'2026-09-01': 5.0}}}
        live = {'spend_daily': {'ad1': {'2026-09-01': 12.0, '2026-09-02': 8.0}}}
        result = merge_meta_fields(base, live)
        # ad1: live wins for 2026-09-01, adds 2026-09-02; ad2 preserved from base
        assert result['spend_daily']['ad1']['2026-09-01'] == 12.0
        assert result['spend_daily']['ad1']['2026-09-02'] == 8.0
        assert result['spend_daily']['ad2']['2026-09-01'] == 5.0

    def test_shallow_keys_live_wins(self):
        from marketing_data.build import merge_meta_fields
        base = {'thumbnails': {'ad1': 'base_url'}}
        live = {'thumbnails': {'ad1': 'live_url', 'ad2': 'new_url'}}
        result = merge_meta_fields(base, live)
        assert result['thumbnails']['ad1'] == 'live_url'
        assert result['thumbnails']['ad2'] == 'new_url'

    def test_campaigns_live_wins_if_nonempty(self):
        from marketing_data.build import merge_meta_fields
        base = {'campaigns': [{'id': 'old'}]}
        live = {'campaigns': [{'id': 'new1'}, {'id': 'new2'}]}
        result = merge_meta_fields(base, live)
        assert result['campaigns'] == [{'id': 'new1'}, {'id': 'new2'}]

    def test_campaigns_base_used_if_live_empty(self):
        from marketing_data.build import merge_meta_fields
        base = {'campaigns': [{'id': 'old'}]}
        live = {'campaigns': []}
        result = merge_meta_fields(base, live)
        assert result['campaigns'] == [{'id': 'old'}]

    def test_campaigns_base_used_if_live_absent(self):
        from marketing_data.build import merge_meta_fields
        base = {'campaigns': [{'id': 'old'}]}
        live = {}
        result = merge_meta_fields(base, live)
        assert result['campaigns'] == [{'id': 'old'}]

    def test_spend_window_prefers_base(self):
        from marketing_data.build import merge_meta_fields
        base = {'spend_window': 100.0}
        live = {'spend_window': 50.0}
        result = merge_meta_fields(base, live)
        assert result['spend_window'] == 100.0

    def test_spend_window_uses_live_if_no_base(self):
        from marketing_data.build import merge_meta_fields
        base = {}
        live = {'spend_window': 50.0}
        result = merge_meta_fields(base, live)
        assert result['spend_window'] == 50.0

    def test_none_base_treated_as_empty(self):
        from marketing_data.build import merge_meta_fields
        live = {'campaigns': [{'id': 'x'}], 'spend_window': 10.0}
        result = merge_meta_fields(None, live)
        assert result['campaigns'] == [{'id': 'x'}]
        assert result['spend_window'] == 10.0

    def test_keys_absent_in_both_omitted(self):
        """Series keys absent in both base and live are not added to output."""
        from marketing_data.build import merge_meta_fields
        result = merge_meta_fields({}, {})
        assert 'spend_daily' not in result
        assert 'thumbnails' not in result
        assert 'campaigns' not in result

    def test_ad_campaign_shallow_merge(self):
        from marketing_data.build import merge_meta_fields
        base = {'ad_campaign': {'ad1': 'Campaign Old'}}
        live = {'ad_campaign': {'ad1': 'Campaign New', 'ad2': 'Campaign 2'}}
        result = merge_meta_fields(base, live)
        assert result['ad_campaign']['ad1'] == 'Campaign New'
        assert result['ad_campaign']['ad2'] == 'Campaign 2'
