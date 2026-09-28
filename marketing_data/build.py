"""
marketing_data/build.py — port of functions/api/_build.js (pure transform, no network).

Ported faithfully from the JS source: constants, alias dicts, and all rules are copied
VERBATIM from _build.js to guarantee byte-identical output.
"""
import locale
import re
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Constants — copied verbatim from _build.js
# ---------------------------------------------------------------------------

KNOWN_PERFIS = [
    'Pro',
    'Starter',
    'Multimarca',
    'Qualificado (Sem Faixa)',
    'Desqualificado',
    'Suporte',
    'Em atendimento',
    'Qualificação_incompleta',
]

SQL_PERFIS = {'Pro', 'Starter', 'Qualificado (Sem Faixa)'}
# Ordered list matching JS Array.from(new Set([...])) insertion order
SQL_PERFIS_LIST = ['Pro', 'Starter', 'Qualificado (Sem Faixa)']

# Ordem oficial do funil de vendas (Etapa 1 → Etapa 6) + etapas fora do funil.
FUNNEL_ETAPAS = [
    'Etapa 1 - inicial',
    'Etapa 2 - Identificado',
    'Etapa 3 - concluído',
    'Etapa 4 - reunião agendada',
    'Etapa 5 - em negociação',
    'Etapa 6 - Ganho',
]

OUT_OF_FUNNEL_ETAPAS = ['Etapa cliente', 'Etapa desqualificado', 'Etapa perdido']

# Mapeia tanto os códigos da integração (ETAPA_X_NOME) quanto os labels humanos.
ETAPA_ALIASES = {
    'etapa_1_inicial': 'Etapa 1 - inicial',
    'etapa 1': 'Etapa 1 - inicial',
    'etapa 1 - inicial': 'Etapa 1 - inicial',
    'etapa_2_identificado': 'Etapa 2 - Identificado',
    'etapa 2': 'Etapa 2 - Identificado',
    'etapa 2 - identificado': 'Etapa 2 - Identificado',
    'etapa_3_concluido': 'Etapa 3 - concluído',
    'etapa_3_concluído': 'Etapa 3 - concluído',
    'etapa 3': 'Etapa 3 - concluído',
    'etapa 3 - concluido': 'Etapa 3 - concluído',
    'etapa 3 - concluído': 'Etapa 3 - concluído',
    'etapa_4_reuniao_agendada': 'Etapa 4 - reunião agendada',
    'etapa_4_reunião_agendada': 'Etapa 4 - reunião agendada',
    'etapa 4': 'Etapa 4 - reunião agendada',
    'etapa 4 - reuniao agendada': 'Etapa 4 - reunião agendada',
    'etapa 4 - reunião agendada': 'Etapa 4 - reunião agendada',
    'etapa_5_em_negociacao': 'Etapa 5 - em negociação',
    'etapa_5_em_negociação': 'Etapa 5 - em negociação',
    'etapa 5': 'Etapa 5 - em negociação',
    'etapa 5 - em negociacao': 'Etapa 5 - em negociação',
    'etapa 5 - em negociação': 'Etapa 5 - em negociação',
    'etapa_6_ganho': 'Etapa 6 - Ganho',
    'etapa 6': 'Etapa 6 - Ganho',
    'etapa 6 - ganho': 'Etapa 6 - Ganho',
    # Out-of-funnel
    'etapa_cliente': 'Etapa cliente',
    'etapa_0_cliente': 'Etapa cliente',
    'etapa cliente': 'Etapa cliente',
    'etapa_desqualificado': 'Etapa desqualificado',
    'etapa_0_desqualificado': 'Etapa desqualificado',
    'etapa desqualificado': 'Etapa desqualificado',
    'etapa_perdido': 'Etapa perdido',
    'etapa_0_perdido': 'Etapa perdido',
    'etapa perdido': 'Etapa perdido',
}

PERFIL_ALIASES = {
    'desqualficado': 'Desqualificado',
    'qualificado (sem faixa )': 'Qualificado (Sem Faixa)',
    'qualificado (sem faixa)': 'Qualificado (Sem Faixa)',
}

META_FIELDS = [
    'spend_daily', 'impressions_daily', 'reach_daily', 'new_msg_contacts_daily',
    'spend_window', 'reach_monthly', 'thumbnails', 'ad_campaign', 'ad_adset', 'campaigns',
]


# ---------------------------------------------------------------------------
# Helper functions — ported from _build.js
# ---------------------------------------------------------------------------

def normalize(s) -> str:
    """Trim + collapse internal whitespace. Mirrors JS normalize()."""
    return re.sub(r'\s+', ' ', str(s or '').strip())


def canonical_perfil(raw) -> str:
    """Map raw perfil string to the canonical form. Mirrors JS canonicalPerfil()."""
    v = normalize(raw)
    if not v:
        return ''
    lower = v.lower()
    if lower in PERFIL_ALIASES:
        return PERFIL_ALIASES[lower]
    for known in KNOWN_PERFIS:
        if known.lower() == lower:
            return known
    return v


def canonical_etapa(raw) -> str:
    """Map raw etapa string to the canonical form. Mirrors JS canonicalEtapa()."""
    v = normalize(raw)
    if not v:
        return ''
    lower = v.lower()
    if lower in ETAPA_ALIASES:
        return ETAPA_ALIASES[lower]
    for known in FUNNEL_ETAPAS + OUT_OF_FUNNEL_ETAPAS:
        if known.lower() == lower:
            return known
    return v


def _sort_key_pt_br(s: str):
    """Sort key using pt_BR locale if available, else fallback to strxfrm."""
    try:
        # Try to use locale for proper pt-BR sort
        return locale.strxfrm(s)
    except Exception:
        return s.lower()


def _try_set_locale():
    """Try to set pt_BR locale for sorting."""
    for loc in ('pt_BR.UTF-8', 'pt_BR', 'Portuguese_Brazil.1252', ''):
        try:
            locale.setlocale(locale.LC_COLLATE, loc)
            return True
        except locale.Error:
            continue
    return False


# Set locale once at module load
_try_set_locale()


def _js_pct(n: int, d: int):
    """
    Mirrors JS: +(100 * n / d).toFixed(2)
    Returns int when result is whole (e.g., 100 not 100.0), else float with 2dp.
    This matches JS JSON serialization where 100.00 → 100.
    """
    if d == 0:
        return 0
    v = round(100 * n / d, 2)
    return int(v) if v == int(v) else v


def finalize_list(mapping: dict) -> list:
    """
    Convert {name: {name, total, sql, by_perfil}} dict to sorted list with sql_pct.
    Mirrors JS finalizeList().
    """
    result = []
    for entry in mapping.values():
        e = dict(entry)
        e['sql_pct'] = _js_pct(e['sql'], e['total']) if e['total'] else 0
        result.append(e)
    result.sort(key=lambda x: x['total'], reverse=True)
    return result


def now_iso_date_brt() -> str:
    """Return current date in BRT (UTC-3) as YYYY-MM-DD."""
    brt = timezone(timedelta(hours=-3))
    return datetime.now(tz=brt).date().isoformat()


def recent_window(today_iso: str, months_back: int = 1) -> dict:
    """
    Return {"since": "YYYY-MM-01", "until": today_iso} where since is the
    1st of the month (months_back) months before today_iso.
    Mirrors JS recentWindow().
    """
    parts = today_iso.split('-')
    y = int(parts[0])
    m = int(parts[1])  # 1-12
    # Go back months_back months from m
    total_months = (y * 12 + (m - 1)) - months_back
    since_y = total_months // 12
    since_m = (total_months % 12) + 1
    since = f"{since_y}-{str(since_m).zfill(2)}-01"
    return {'since': since, 'until': today_iso}


def _is_series_map(v) -> bool:
    return v is not None and isinstance(v, dict) and not isinstance(v, list)


def _overlay_series(base: dict, live: dict) -> dict:
    """Merge two series dicts; live wins for overlapping keys. Mirrors JS overlaySeries()."""
    out = {}
    for ad in set(list(base.keys()) + list(live.keys())):
        out[ad] = {**(base.get(ad) or {}), **(live.get(ad) or {})}
    return out


def merge_meta_fields(base_midia, live_meta: dict) -> dict:
    """
    Merge base midia_paga dict with live meta fields.
    Mirrors JS mergeMetaFields().
    """
    base = base_midia or {}
    live = live_meta or {}
    out = {}

    series_keys = ['spend_daily', 'impressions_daily', 'reach_daily', 'new_msg_contacts_daily', 'reach_monthly']
    shallow_keys = ['thumbnails', 'ad_campaign', 'ad_adset']

    for k in series_keys:
        if k not in base and k not in live:
            continue
        out[k] = _overlay_series(
            base[k] if _is_series_map(base.get(k)) else {},
            live[k] if _is_series_map(live.get(k)) else {},
        )

    for k in shallow_keys:
        if k not in base and k not in live:
            continue
        out[k] = {**(base.get(k) or {}), **(live.get(k) or {})}

    # campaigns: uses live if non-empty, else base
    if live.get('campaigns'):
        out['campaigns'] = live['campaigns']
    elif 'campaigns' in base:
        out['campaigns'] = base['campaigns']

    # spend_window: base covers full history; only use live if no base
    if 'spend_window' in base and base['spend_window'] is not None:
        out['spend_window'] = base['spend_window']
    elif 'spend_window' in live:
        out['spend_window'] = live['spend_window']

    return out


# ---------------------------------------------------------------------------
# buildDataFromRows — main transform
# ---------------------------------------------------------------------------

def build_data_from_rows(rows: list, *, sheet_id: str, tab: str, generated_at: str) -> dict:
    """
    Transform sheet rows into the data.json model the frontend consumes.
    Mirrors JS buildDataFromRows().
    """
    if len(rows) < 2:
        raise ValueError('Planilha vazia ou sem header.')

    header = [normalize(h) for h in rows[0]]

    def find_index(name):
        try:
            return header.index(name)
        except ValueError:
            return -1

    def find_index_re(pattern):
        for i, h in enumerate(header):
            if re.search(pattern, str(h), re.IGNORECASE):
                return i
        return -1

    idx_data = find_index('DATA')
    idx_origem = find_index('ORIGEM')
    idx_perfil = find_index('PERFIL')
    idx_etapa = find_index('ETAPA')
    idx_anuncio = find_index('ANUNCIO')
    idx_criativo = find_index('NOME CRIATIVO')
    idx_formulario = find_index_re(r'formul')
    idx_data_etapa = find_index_re(r'datetime.*etapa|data.*etapa')

    # Fallback: column K (index 10) if header is wide enough
    if idx_data_etapa < 0 and len(header) > 10:
        idx_data_etapa = 10

    if idx_origem < 0 or idx_perfil < 0:
        raise ValueError(
            f'Header esperado nao encontrado. Header lido: {header}'
        )

    leads = []
    perfil_counts = {}
    origem_counts = {}
    sql_by_origem = {}
    origem_set = []  # ordered insertion
    origem_seen = set()
    perfil_set = []
    perfil_seen = set()
    etapa_set = []
    etapa_seen = set()
    etapa_counts = {}
    etapa_by_origem = {}
    etapa_by_perfil = {}
    etapa_by_month = {}

    chanel = {
        'total': 0,
        'total_sql': 0,
        'sem_criativo': 0,
        'sem_anuncio': 0,
        'by_criativo': {},  # name -> {name, total, sql, by_perfil}
        'by_anuncio': {},
        'leads': [],
    }

    def bump_agg(mapping, key, perfil):
        if key not in mapping:
            mapping[key] = {'name': key, 'total': 0, 'sql': 0, 'by_perfil': {}}
        e = mapping[key]
        e['total'] += 1
        if perfil in SQL_PERFIS:
            e['sql'] += 1
        if perfil:
            e['by_perfil'][perfil] = e['by_perfil'].get(perfil, 0) + 1

    def get_col(row, idx):
        if idx < 0 or idx >= len(row):
            return ''
        return row[idx]

    for row in rows[1:]:
        raw_origem = normalize(get_col(row, idx_origem))
        perfil = canonical_perfil(get_col(row, idx_perfil))
        if not raw_origem and not perfil:
            continue

        data = normalize(get_col(row, idx_data))
        etapa = canonical_etapa(get_col(row, idx_etapa)) if idx_etapa >= 0 else ''
        anuncio = normalize(get_col(row, idx_anuncio)) if idx_anuncio >= 0 else ''
        criativo = normalize(get_col(row, idx_criativo)) if idx_criativo >= 0 else ''
        data_etapa = normalize(get_col(row, idx_data_etapa)) if idx_data_etapa >= 0 else ''

        # Coluna FORMULÁRIO: "Sim" if matches /sim/i, else "Não" (including empty)
        formulario_raw = normalize(get_col(row, idx_formulario)) if idx_formulario >= 0 else ''
        formulario = 'Sim' if re.search(r'sim', formulario_raw, re.IGNORECASE) else 'Não'

        # Reclassify as "Mídia paga" if ANUNCIO or NOME CRIATIVO is filled
        origem = 'Mídia paga' if (anuncio or criativo) else raw_origem

        leads.append({
            'data': data,
            'origem': origem,
            'perfil': perfil,
            'etapa': etapa,
            'data_etapa': data_etapa,
            'formulario': formulario,
        })

        if origem and origem not in origem_seen:
            origem_set.append(origem)
            origem_seen.add(origem)
        if perfil and perfil not in perfil_seen:
            perfil_set.append(perfil)
            perfil_seen.add(perfil)

        if perfil:
            perfil_counts[perfil] = perfil_counts.get(perfil, 0) + 1
        if origem:
            origem_counts[origem] = origem_counts.get(origem, 0) + 1
        if perfil in SQL_PERFIS:
            key = origem or '(sem origem)'
            sql_by_origem[key] = sql_by_origem.get(key, 0) + 1

        if etapa:
            if etapa not in etapa_seen:
                etapa_set.append(etapa)
                etapa_seen.add(etapa)
            etapa_counts[etapa] = etapa_counts.get(etapa, 0) + 1

            o_key = origem or '(sem origem)'
            if o_key not in etapa_by_origem:
                etapa_by_origem[o_key] = {}
            etapa_by_origem[o_key][etapa] = etapa_by_origem[o_key].get(etapa, 0) + 1

            p_key = perfil or '(sem perfil)'
            if p_key not in etapa_by_perfil:
                etapa_by_perfil[p_key] = {}
            etapa_by_perfil[p_key][etapa] = etapa_by_perfil[p_key].get(etapa, 0) + 1

            m_match = re.match(r'^(\d{2})/(\d{2})/(\d{4})', str(data))
            if m_match:
                m_key = f"{m_match.group(3)}-{m_match.group(2)}"
                if m_key not in etapa_by_month:
                    etapa_by_month[m_key] = {}
                etapa_by_month[m_key][etapa] = etapa_by_month[m_key].get(etapa, 0) + 1

        if anuncio or criativo:
            chanel['total'] += 1
            if perfil in SQL_PERFIS:
                chanel['total_sql'] += 1
            if criativo:
                bump_agg(chanel['by_criativo'], criativo, perfil)
            else:
                chanel['sem_criativo'] += 1
            if anuncio:
                bump_agg(chanel['by_anuncio'], anuncio, perfil)
            else:
                chanel['sem_anuncio'] += 1
            chanel['leads'].append({
                'data': data,
                'perfil': perfil,
                'anuncio': anuncio,
                'criativo': criativo,
                'origem': raw_origem,
                'etapa': etapa,
            })

    # midia_paga.chanel
    midia_paga = {
        'chanel': {
            'total': chanel['total'],
            'total_sql': chanel['total_sql'],
            'sql_pct': _js_pct(chanel['total_sql'], chanel['total']),
            'sem_criativo': chanel['sem_criativo'],
            'sem_anuncio': chanel['sem_anuncio'],
            'pct_sem_criativo': _js_pct(chanel['sem_criativo'], chanel['total']),
            'criativos': finalize_list(chanel['by_criativo']),
            'anuncios': finalize_list(chanel['by_anuncio']),
            'leads': chanel['leads'],
        },
    }

    total_leads = len(leads)
    total_sql = sum(sql_by_origem.values())

    # perfis: KNOWN_PERFIS order for known; extras at end
    perfil_set_s = set(perfil_set)
    perfis = [p for p in KNOWN_PERFIS if p in perfil_set_s or perfil_counts.get(p)]
    perfis += [p for p in perfil_set if p not in KNOWN_PERFIS]

    # origens: sorted pt-BR
    origens = sorted(list(origem_seen), key=_sort_key_pt_br)

    # etapas list: funnel → out-of-funnel → unknown (sorted pt-BR)
    etapa_set_s = set(etapa_set)
    etapas_ordered = (
        [e for e in FUNNEL_ETAPAS if e in etapa_set_s]
        + [e for e in OUT_OF_FUNNEL_ETAPAS if e in etapa_set_s]
        + sorted(
            [e for e in etapa_set if e not in FUNNEL_ETAPAS and e not in OUT_OF_FUNNEL_ETAPAS],
            key=_sort_key_pt_br,
        )
    )

    return {
        'generated_at': generated_at,
        'sheet_id': sheet_id,
        'sheet_tab': tab,
        'total_leads': total_leads,
        'total_sql': total_sql,
        'sql_pct': _js_pct(total_sql, total_leads),
        'perfis': perfis,
        'origens': origens,
        'perfil_counts': perfil_counts,
        'origem_counts': origem_counts,
        'sql_by_origem': sql_by_origem,
        'sql_perfis': SQL_PERFIS_LIST,
        'etapas': {
            'list': etapas_ordered,
            'funnel_order': FUNNEL_ETAPAS,
            'out_of_funnel': OUT_OF_FUNNEL_ETAPAS,
            'counts': etapa_counts,
            'by_origem': etapa_by_origem,
            'by_perfil': etapa_by_perfil,
            'by_month': etapa_by_month,
        },
        'midia_paga': midia_paga,
        'leads': leads,
    }
