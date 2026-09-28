# Backend Python do Marketing (igual ao KPIs) — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Reescrever o backend do dashboard de marketing em **Python** (Flask/gunicorn/venv), espelhando o padrão do KPIs, para rodar no servidor Vesti **sem instalar nada no sistema** (o servidor só tem Node 12; Python 3 já está lá) e mantendo o botão "Atualizar ao vivo".

**Architecture:** Módulos Python portados do JS (`sheets`, `meta`, `build`) + gerador diário (`gerar_marketing.py`, cron) + backend Flask (`backend/app.py`, `GET /api/dados` ao vivo, porta 5002) atrás do nginx. Mesma estrutura do KPIs (`~/vesti-pago-kpis`).

**Tech Stack:** Python 3.10 (já no servidor), `google-auth`, `requests`, `flask`, `gunicorn` — tudo em `venv` isolado. Testes com `pytest`.

## Global Constraints
- **Paridade de números:** a saída (`data.json`) e as respostas do `/api/dados` devem ser **idênticas** ao backend JS atual. Cada módulo é portado LENDO o JS-fonte correspondente e replicando constantes e regras exatamente.
- **Fonte da verdade:** `functions/api/_build.js`, `functions/api/_sheets.js`, `functions/api/_meta.js`, `functions/api/dados.js`, `scripts/extract.cjs`. Portar deles, não de memória.
- **Schema do `data.json`** (contrato do front) — top-level: `generated_at, sheet_id, sheet_tab, total_leads, total_sql, sql_pct, perfis, origens, perfil_counts, origem_counts, sql_by_origem, sql_perfis, etapas{list,funnel_order,out_of_funnel,counts,by_origem,by_perfil,by_month}, midia_paga{chanel{...},spend_daily,impressions_daily,reach_daily,new_msg_contacts_daily,spend_window,reach_monthly,thumbnails,ad_campaign,ad_adset,campaigns}, leads[]`.
- **Precisão:** `sql_pct` e afins = `round(100*n/d, 2)` float; `spend` = `round(float,2)`; `impressions/reach/new_msg_contacts` = int.
- **Sheets:** aba `LeadsV2`, range `A:K`, Sheet ID `1zNRw8zfoASVlO2EhR56sldTCy4IXRCLKfauU1ROChCE` (overridáveis por `SHEET_TAB`/`SHEET_ID`). Auth: `GCP_SA_KEY` (JSON inline) OU `GOOGLE_APPLICATION_CREDENTIALS` (arquivo), scope `spreadsheets.readonly`.
- **Meta:** Graph API `v21.0`, conta via `META_AD_ACCOUNT_ID` (prefixa `act_` se faltar), token `META_ACCESS_TOKEN`.
- **Porta do serviço:** gunicorn em `127.0.0.1:5002`, módulo `backend.app:app`, `--workers 1 --threads 4`.
- **Servidor:** `allan@216.238.108.108`, `~/marketing`, web root `/var/www/marketing/`, venv em `~/marketing/.venv`.
- **Testes** com `pytest`; não tocam em Google/Meta (rede real).

---

### Task P1: `marketing_data/build.py` (o coração — porta de `_build.js`)

Porta pura (sem rede), a parte crítica pra paridade. LEIA `functions/api/_build.js` e replique EXATAMENTE: `normalize`, `PERFIL_ALIASES`, `KNOWN_PERFIS`, `canonicalPerfil`, `ETAPA_ALIASES`, `FUNNEL_ETAPAS`, `OUT_OF_FUNNEL_ETAPAS`, `canonicalEtapa`, `SQL_PERFIS`, `buildDataFromRows`, `finalizeList`, `recentWindow`, `mergeMetaFields`, `nowIsoDateBRT`. Ordenação `pt-BR` de `origens`/etapas desconhecidas via `locale.strxfrm` (pt_BR) ou fallback estável.

**Files:**
- Create: `marketing_data/__init__.py` (vazio), `marketing_data/build.py`
- Test: `test/test_build.py`

**Interfaces (produz):**
- `build_data_from_rows(rows: list[list[str]], *, sheet_id, tab, generated_at) -> dict`
- `recent_window(today_iso: str, months_back: int = 1) -> dict`  → `{"since","until"}`
- `merge_meta_fields(base_midia: dict|None, live: dict) -> dict`
- `now_iso_date_brt() -> str`
- `canonical_perfil(raw)`, `canonical_etapa(raw)`, `normalize(s)` (auxiliares)

- [ ] **Step 1: Escrever testes que falham** — `test/test_build.py`. Cubra, com linhas sintéticas representativas:
  - header discovery (colunas DATA/ORIGEM/PERFIL/ETAPA/ANUNCIO/NOME CRIATIVO/formul/data etapa); erro se faltar ORIGEM/PERFIL.
  - `canonical_perfil` (aliases de typo: `desqualficado`→`Desqualificado`, `qualificado (sem faixa )`→`Qualificado (Sem Faixa)`) e `canonical_etapa` (todos os `ETAPA_ALIASES`).
  - reclassificação: linha com `anuncio` ou `criativo` vira `origem='Mídia paga'`; linha sem os dois mantém origem.
  - agregações: `perfil_counts`, `origem_counts`, `sql_by_origem` (só perfis em `SQL_PERFIS`), `etapas.counts/by_origem/by_perfil/by_month` (mês de `DD/MM/YYYY`→`YYYY-MM`).
  - `midia_paga.chanel`: total, total_sql, sql_pct, sem_criativo/sem_anuncio, listas `criativos`/`anuncios` (com `sql_pct` e `by_perfil`), `leads` (usa `rawOrigem`).
  - `finalize_list`: `sql_pct=round(100*sql/total,2)` (0 se total=0), ordenado desc por total.
  - `recent_window('2026-09-28',1) == {"since":"2026-08-01","until":"2026-09-28"}`.
  - `merge_meta_fields`: séries → union por ad, live vence chaves iguais; shallow (`thumbnails`/`ad_campaign`/`ad_adset`) live vence; `campaigns` live se não-vazio senão base; `spend_window` prefere base.
  Rode `pytest test/test_build.py` → FAIL (módulo não existe).
- [ ] **Step 2: Implementar `marketing_data/build.py`** portando `_build.js` linha a linha (mesmas constantes e regras). Rode `pytest test/test_build.py` → PASS.
- [ ] **Step 3: Teste de PARIDADE JS×Python** — `test/test_build_parity.py`: um conjunto fixo de linhas sintéticas (diversas: mídia paga, orgânico, cada etapa, perfis SQL/não-SQL, campos vazios) é passado por AMBOS: roda `node -e` sobre `functions/api/_build.js#buildDataFromRows` dumpando JSON, e `build_data_from_rows` em Python; compara os dois JSON (iguais). Rode e confirme match.
- [ ] **Step 4: Commit** `git add marketing_data/ test/test_build*.py && git commit -m "feat(py): porta _build.js -> marketing_data/build.py (com teste de paridade JS×Py)"`

---

### Task P2: `marketing_data/sheets.py` (porta de `_sheets.js`)

**Files:** Create `marketing_data/sheets.py`; Test `test/test_sheets.py`

**Interfaces:** `read_sheet_rows(env: dict|Mapping, *, tab, rng='A:K') -> list[list[str]]`; `get_google_credentials(env)` (seleção GCP_SA_KEY inline vs GOOGLE_APPLICATION_CREDENTIALS arquivo).

- [ ] **Step 1: Teste que falha** — `test/test_sheets.py`: `get_google_credentials` escolhe JSON inline quando `GCP_SA_KEY` presente e arquivo quando só `GOOGLE_APPLICATION_CREDENTIALS`; erro claro se nenhum. Coerção de célula p/ string (None→''). NÃO chama a rede (mocka `google.oauth2.service_account.Credentials`/o client, OU testa só os helpers puros). Rode → FAIL.
- [ ] **Step 2: Implementar** com `google.oauth2.service_account` + `googleapiclient.discovery.build('sheets','v4')` (scope `spreadsheets.readonly`), lendo `{tab}!{rng}`, devolvendo matriz de strings (`str(c or '')`). Rode → PASS.
- [ ] **Step 3: Commit** `git commit -m "feat(py): porta _sheets.js -> marketing_data/sheets.py"`

---

### Task P3: `marketing_data/meta.py` (porta de `_meta.js`)

**Files:** Create `marketing_data/meta.py`; Test `test/test_meta.py`

**Interfaces:** `month_windows(since, until) -> list[dict]`; `fetch_meta_insights_daily(creds, since, until)`; `fetch_meta_reach_monthly(creds, since, until)`; `fetch_meta_ads_metadata(creds)`; `fetch_meta_window(env, window) -> dict`; `load_meta_creds(env)`.

- [ ] **Step 1: Teste que falha** — `test/test_meta.py`: `month_windows` fatia por mês calendário (bordas recortadas), ex.: `('2026-08-15','2026-09-10')` → 2 janelas. `load_meta_creds` prefixa `act_`. Parsing de uma linha de insight sintética (action `onsite_conversion.messaging_first_reply` → int). NÃO chama a Graph API (usa `requests` mockado OU testa só os helpers puros). Rode → FAIL.
- [ ] **Step 2: Implementar** com `requests`, endpoints/fields/params idênticos ao `_meta.js` (v21.0, `/insights` level=ad time_increment=1, `/insights` reach mensal, `/ads` metadata com o mesmo `filtering`), paginação por `paging.next` com os mesmos limites de página. `fetch_meta_window` engole falhas parciais (reach/metadata), propaga só falha do insights diário. Rode → PASS.
- [ ] **Step 3: Commit** `git commit -m "feat(py): porta _meta.js -> marketing_data/meta.py"`

---

### Task P4: `gerar_marketing.py` (gerador diário — porta de `extract.cjs`)

Orquestra: lê a planilha (janela Meta = do 1º lead, ou 90d fallback, até hoje) → `build_data_from_rows` → `fetch_meta_window` (janela completa) → merge → escreve `docs/data/data.json` (indent 2). Fallback: em falha da Meta, restaura campos do `data.json` anterior no disco (como o `extract.cjs`).

**Files:** Create `gerar_marketing.py`; Test `test/test_gerar.py`

- [ ] **Step 1: Teste que falha** — `test/test_gerar.py`: com `read_sheet_rows`/`fetch_meta_window` **injetados/mockados** (sem rede), `gerar()` produz um dict com o schema esperado e escreve o arquivo destino. Rode → FAIL.
- [ ] **Step 2: Implementar** com CLI mínima (`--out docs/data/data.json`, lê env p/ creds) e as funções injetáveis (p/ testar). Rode → PASS.
- [ ] **Step 3: Commit** `git commit -m "feat(py): gerar_marketing.py (porta de extract.cjs) escreve data.json"`

---

### Task P5: Backend Flask (`backend/app.py`) — espelha o KPIs

`GET /api/dados`: lê a planilha ao vivo → `build_data_from_rows` → `fetch_meta_window(recent_window(now_brt,1))` → sobrepõe `midia_paga` com `merge_meta_fields(base_do_disco, live)` (chanel sempre fresco) → JSON. Cache TTL em memória (10 min) com bypass `?fresh=1`; `GET /api/health` → `{"status":"ok"}`. Um worker, `threading.Lock`, igual ao KPIs.

**Files:** Create `backend/__init__.py`, `backend/app.py`, `backend/requirements.txt`; Test `test/test_app.py`

- [ ] **Step 1: Teste que falha** — `test/test_app.py` (Flask test client): com o build **injetado/mockado** (sem rede), `GET /api/dados` devolve 200 + JSON; 2ª chamada vem do cache; `?fresh=1` recomputa; `GET /api/health` → `{"status":"ok"}`; erro no build → 503 JSON. Rode → FAIL.
- [ ] **Step 2: Implementar** (`SNAPSHOT_PATH` default `/var/www/marketing/data/data.json`; lê o snapshot base do disco p/ o merge). `backend/requirements.txt` = `flask>=2.3` + `gunicorn>=21`. Rode → PASS.
- [ ] **Step 3: Commit** `git commit -m "feat(py): backend Flask /api/dados (ao vivo, cache TTL) espelhando o KPIs"`

---

### Task P6: Artefatos de deploy (Python) — reescreve os de Node

Substitui os artefatos Node pelos Python (padrão KPIs).

**Files:**
- Overwrite: `deploy/marketing-backend.service`, `atualizar.sh`, `deploy/nginx/marketing.conf`, `deploy/marketing.env.example`, `DEPLOY.md`, `ATUALIZAR.md`
- Create: `requirements.txt` (raiz)

- [ ] **Step 1:** `requirements.txt` (raiz) = `google-auth`, `google-api-python-client`, `requests`.
- [ ] **Step 2:** `deploy/marketing-backend.service` → gunicorn:
  ```ini
  ExecStart=/home/allan/marketing/.venv/bin/gunicorn --chdir /home/allan/marketing \
    --workers 1 --threads 4 --timeout 200 --bind 127.0.0.1:5002 backend.app:app
  ```
  com `User=allan`, `WorkingDirectory=/home/allan/marketing`, `EnvironmentFile=/home/allan/marketing/secrets/marketing.env`, `Environment=SNAPSHOT_PATH=/var/www/marketing/data/data.json`, `Restart=on-failure`.
- [ ] **Step 3:** `atualizar.sh` → `git pull --ff-only` + `. .venv/bin/activate` + `pip install -q -r requirements.txt` + `python gerar_marketing.py --out docs/data/data.json` + `sudo rsync -a --delete docs/ /var/www/marketing/`.
- [ ] **Step 4:** `deploy/nginx/marketing.conf` → padrão KPIs (redirect bare `/marketing`, `location /marketing/api/` → `127.0.0.1:5002/api/` com `X-Real-IP`/`X-Forwarded-*`, blocos estáticos `location = /marketing/` e `location /marketing/`).
- [ ] **Step 5:** `marketing.env.example` (só `META_*`, `SHEET_*`, `GOOGLE_APPLICATION_CREDENTIALS=…/sa.json`), `DEPLOY.md`/`ATUALIZAR.md` atualizados (venv, gunicorn, `python gerar_marketing.py`).
- [ ] **Step 6: Commit** `git commit -m "chore(deploy): artefatos Python (gunicorn/venv/cron) no lugar dos de Node"`

---

## Notas
- **Node fica no repo** (`server.js`, `functions/`, `_cache.js`) — segue servindo a Cloudflare até validarmos o servidor; o **servidor usa só o Python**.
- **Frontend não muda:** já chama `api/dados` relativo; o nginx aponta pro gunicorn 5002.
- **Deploy no servidor (Task 9 antiga, agora Python):** `python3 -m venv .venv && pip install -r requirements.txt -r backend/requirements.txt`; resto igual ao runbook do KPIs (secrets, systemd, nginx, cron). Sem instalar nada no sistema.
- **Validação de paridade end-to-end:** no servidor (onde há creds), comparar o `data.json` gerado pelo Python com o gerado pela Action/JS.
