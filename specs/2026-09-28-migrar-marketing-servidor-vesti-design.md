# Migração do Marketing Dashboard para o servidor Vesti

**Data:** 2026-09-28
**Status:** Aprovado (brainstorming) — pronto para plano de implementação

## Contexto

O Marketing Dashboard (leads + Meta Ads) hoje roda na **Cloudflare Pages**, com uma
Pages Function serverless (`/api/dados`) que lê Google Sheets + Meta Ads ao vivo, e um
snapshot diário (`docs/data/data.json`) gerado por uma GitHub Action.

O objetivo é **auto-hospedar tudo no servidor da Vesti** (`bi.vesti.com.br/marketing/`),
consolidando a infra junto dos outros painéis (KPIs em `/kpis/`, Sintonia em `/sintonia/`)
e **removendo a dependência externa** (Cloudflare + GitHub Actions). O deploy espelha o
padrão já usado no KPIs (nginx snippet por subpath + serviço systemd + cron + `atualizar.sh`).

## Decisões (do brainstorming)

| Tema | Decisão |
|---|---|
| Escopo | Migrar **tudo**, inclusive a API ao vivo (botão "Atualizar") |
| Endereço | `bi.vesti.com.br/marketing/` (subpath, snippet nginx próprio) |
| Login (PIN) | Client-side (`login.js`/`auth-guard.js`) — **migra como está**, sem backend de auth |
| Snapshot diário | **Cron no servidor** (roda `extract.js` no server), sem GitHub Actions |
| Cloudflare | **Desligar** após validar o servidor |
| API ao vivo | **Serviço Node** portando a Function existente (não reescrever em Python) |

## Arquitetura

Servidor `allan@216.238.108.108`, clone em `~/marketing` (git pull para atualizar):

```
Browser ──▶ nginx (bi.vesti.com.br)
              ├─ /marketing/            → estático  /var/www/marketing/   (conteúdo de docs/)
              └─ /marketing/api/dados   → proxy → 127.0.0.1:5002 (marketing-backend, Node)
                                                     │ lê Sheets (JWT) + Meta ao vivo
                                                     │ + merge sobre o snapshot (lido do disco)
Cron 06:00 ─▶ ~/marketing/atualizar.sh:  git pull + node scripts/extract.js
                                          → publica docs/ em /var/www/marketing/
```

Portas em uso no servidor: Sintonia `5000`, KPIs `5001` → **marketing usa `5002`**.

## Componentes

1. **Frontend estático** (`docs/`) — servido pelo nginx em `/marketing/`. Login client-side
   migra sem alteração (senha fixa no `login.js`, flag em sessionStorage 8h).
2. **Serviço Node `marketing-backend`** — um `server.js` envolve a Function existente
   (`functions/api/dados.js` + `_sheets.js` + `_meta.js` + `_build.js` + `_cache.js`) num
   servidor HTTP fino, escutando `127.0.0.1:5002`. systemd com `Restart=always`, lê secrets
   de um `EnvironmentFile`.
3. **Snippet nginx `deploy/nginx/marketing.conf`** — `location /marketing/` (estático) +
   `location /marketing/api/` (proxy pro Node, faixa `/marketing/api/` → `/api/`). Incluído
   no `bi.vesti.com.br` por **uma linha** `include`, como o KPIs (não editar o arquivo do hub).
4. **Cron + `atualizar.sh`** — `git pull` + `node scripts/extract.js` (regenera `data.json`)
   + publica `docs/` em `/var/www/marketing/`. Uma linha no crontab, diário 06:00 BRT.
5. **Secrets no servidor** (fora do git, em `~/marketing/secrets/` como EnvironmentFile):
   `GCP_SA_KEY`, `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `SHEET_ID`, `SHEET_TAB`.

## Mudanças no código (mínimas e isoladas)

Pré-requisito: **Node 18+ no servidor** (a Function e o `extract.js` são Node; APIs
Web-standard — `fetch`, `WebCrypto`, `btoa/atob` — já são nativas no Node 18+).

- **Novo `server.js`** — servidor HTTP Node que injeta `process.env` como `env`, roteia
  `GET /api/dados`, e chama a lógica existente. Nada da lógica de negócio muda.
- **`functions/api/_cache.js`** — substituir o cache de borda da Cloudflare (`caches.default`
  + `context.waitUntil`, inexistentes no Node) por um **cache em memória com TTL**,
  preservando: bypass `?fresh=1`, headers CORS, e o mapeamento de erro (401/403 → 502, senão 503).
- **`functions/api/dados.js`** — `fetchBaseSnapshot` passa a **ler o `data.json` do disco**
  (o caminho publicado), em vez do self-fetch de `/data/data.json` (que não existe no runtime Node).
- **Frontend (4 arquivos):** trocar a chamada **absoluta** `/api/dados` por **relativa**
  `api/dados` em `docs/js/app.jsx`, `docs/etapas.html`, `docs/meta.html`, `docs/midia-paga.html`.
  A forma relativa funciona **tanto** na Cloudflare (raiz) **quanto** no subpath `/marketing/`.
  As leituras de snapshot já são relativas (`data/data.json`) e não mudam.
- **Novos arquivos de deploy:** `deploy/nginx/marketing.conf`, `deploy/marketing-backend.service`,
  `atualizar.sh`, e docs `DEPLOY.md`/`ATUALIZAR.md` (molde do KPIs).

## Fluxo de dados

- **Carga inicial:** nginx serve `index.html`/js/css + `data/data.json` (snapshot) → primeiro
  paint rápido.
- **Botão "Atualizar":** front chama `api/dados?fresh=1` → nginx → Node lê Sheets + Meta ao
  vivo + faz merge sobre o snapshot (do disco) → devolve JSON (bypassa o cache).
- **Acesso normal (background):** `api/dados` (sem `fresh`) → serve do cache em memória (TTL 10 min).
- **Cron diário 06:00:** `extract.js` regenera `data.json` → publicado em `/var/www/marketing/data/`.

## Tratamento de erros / fallback

Mantém a filosofia atual: se a Meta falhar, usa a base do snapshot; se o Sheets falhar, o
front mantém os dados já exibidos. O serviço systemd usa `Restart=always`; se o backend cair,
`/marketing/api/dados` responde 502 e o front continua no snapshot estático (comportamento atual).

## Segurança

Login segue **client-side** (segurança básica, senha visível no fonte) — inalterado nesta
migração. Os secrets do Google/Meta ficam **fora do git**, num EnvironmentFile lido pelo
systemd, servido só ao processo do backend (nunca exposto ao browser).

## Testes / validação / rollout

1. **Local:** rodar `server.js`, `curl localhost:5002/api/dados` e comparar o JSON com o da
   Cloudflare (paridade de números); rodar `extract.js` e conferir o `data.json`.
2. **Servidor:** subir serviço + nginx snippet + cron; validar `bi.vesti.com.br/marketing/`
   no ar (login, páginas, botão Atualizar ao vivo, cron gerando o snapshot).
3. **Só depois de validado:** **desligar a Cloudflare Pages** e a GitHub Action de deploy.

## Fora de escopo (YAGNI)

- Reescrever a lógica em Python.
- Trocar o login client-side por auth server-side.
- Redirect da URL antiga da Cloudflare (decisão foi desligar de vez).
- Mudanças de visual/métricas do dashboard (é migração de infra, não de produto).

## Arquivos afetados (resumo)

| Arquivo | Ação |
|---|---|
| `server.js` | **novo** — wrapper HTTP Node |
| `functions/api/_cache.js` | editar — cache em memória (sem Cloudflare) |
| `functions/api/dados.js` | editar — `fetchBaseSnapshot` lê do disco |
| `docs/js/app.jsx`, `docs/etapas.html`, `docs/meta.html`, `docs/midia-paga.html` | editar — `/api/dados` → `api/dados` |
| `deploy/nginx/marketing.conf` | **novo** |
| `deploy/marketing-backend.service` | **novo** |
| `atualizar.sh` | **novo** |
| `DEPLOY.md`, `ATUALIZAR.md` | **novos** (molde do KPIs) |
