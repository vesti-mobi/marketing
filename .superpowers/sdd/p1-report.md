# Task P1 Report — `marketing_data/build.py` (port of `_build.js`)

**Date:** 2026-09-28  
**Branch:** `backend-python-marketing`

---

## What Was Ported

`functions/api/_build.js` → `marketing_data/build.py` (pure transform, no network).

### Functions and constants ported (verbatim constants):

| JS | Python |
|----|--------|
| `normalize(s)` | `normalize(s)` |
| `PERFIL_ALIASES` | `PERFIL_ALIASES` (dict literal copied verbatim) |
| `KNOWN_PERFIS` | `KNOWN_PERFIS` (list copied verbatim) |
| `canonicalPerfil(raw)` | `canonical_perfil(raw)` |
| `ETAPA_ALIASES` | `ETAPA_ALIASES` (dict literal copied verbatim, all 30 entries) |
| `FUNNEL_ETAPAS` | `FUNNEL_ETAPAS` |
| `OUT_OF_FUNNEL_ETAPAS` | `OUT_OF_FUNNEL_ETAPAS` |
| `canonicalEtapa(raw)` | `canonical_etapa(raw)` |
| `SQL_PERFIS` (Set) | `SQL_PERFIS` (set) + `SQL_PERFIS_LIST` (ordered) |
| `buildDataFromRows(rows, meta)` | `build_data_from_rows(rows, *, sheet_id, tab, generated_at)` |
| `finalizeList(map)` | `finalize_list(mapping)` |
| `recentWindow(todayIso, monthsBack)` | `recent_window(today_iso, months_back)` |
| `mergeMetaFields(baseMidia, liveMeta)` | `merge_meta_fields(base_midia, live_meta)` |
| `nowIsoDateBRT()` | `now_iso_date_brt()` |
| `META_FIELDS` | `META_FIELDS` |

---

## Files Changed

- **Created:** `marketing_data/__init__.py` (empty)
- **Created:** `marketing_data/build.py` (port of `_build.js`)
- **Created:** `test/test_build.py` (85 unit tests, RED→GREEN)
- **Created:** `test/test_build_parity.py` (26 JS×Python parity tests)
- **Created:** `.superpowers/sdd/p1-report.md` (this file)

---

## Parity Approach

`test/test_build_parity.py` runs the same 14 synthetic rows (diverse coverage: all etapas, all SQL/non-SQL perfis, mídia paga with/without criativo/anuncio, typo aliases, underscore aliases, empty fields, multi-month dates) through BOTH:

1. **JS side:** `node --input-type=module` piped with an ESM script that imports `buildDataFromRows` from `./functions/api/_build.js` and dumps JSON to stdout.
2. **Python side:** `build_data_from_rows` from `marketing_data.build`.

The full JSON output (serialized with sorted keys) is asserted equal.

**Parity result: PASS.** All 26 parity tests green on first run after one fix.

---

## Tricky JS Behaviors

1. **`+(x).toFixed(2)` number coercion:** JS's `+` unary after `.toFixed(2)` returns `100` (integer) when the value is whole, not `100.0`. Python's `round(100.0, 2)` serializes as `100.0` in JSON. Fixed with `_js_pct(n, d)` helper that returns `int` when the float is whole.

2. **`sql_perfis` order:** JS `Array.from(new Set(['Pro', 'Starter', ...]))` preserves insertion order from the Set literal. Python `set` has no guaranteed order. Fixed by adding `SQL_PERFIS_LIST = ['Pro', 'Starter', 'Qualificado (Sem Faixa)']` and using it for `sql_perfis` in output.

3. **`origens` sort:** JS uses `localeCompare(b, 'pt-BR')`. Python uses `locale.strxfrm` after attempting to set `pt_BR` locale. On Windows, the locale name is `Portuguese_Brazil.1252`; fallback is always available. The parity test confirms sort matches.

4. **Header regex detection:** JS `header.findIndex(h => /formul/i.test(String(h)))` and `/datetime.*etapa|data.*etapa/i` — ported to Python with `re.search`.

5. **`idx.dataEtapa` fallback:** JS `if (idx.dataEtapa < 0 && header.length > 10) idx.dataEtapa = 10` — ported exactly.

---

## TDD Evidence

- **Step 1 (RED):** `pytest test/test_build.py` → `1 failed` (ModuleNotFoundError — module did not exist).
- **Step 2 (GREEN):** After implementing `marketing_data/build.py` → 85 passed.
- **Step 3 (PARITY):** Initial parity run → 25/26 passed; 1 failure revealed `sql_perfis` order issue. Fixed → 26/26 passed.
- **Full suite:** `pytest test/` → **111 passed** (85 unit + 26 parity).

---

## Concerns

None blocking. The `locale.strxfrm` pt-BR sort may differ from JS `localeCompare` for edge cases with accented characters in `origens`; the parity test confirms match for the tested data. A broader edge-case test could be added when real sheet data is available.
