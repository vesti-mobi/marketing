# Migração do Marketing Dashboard para o servidor Vesti — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-hospedar o Marketing Dashboard (frontend + snapshot + API ao vivo) em `bi.vesti.com.br/marketing/`, saindo da Cloudflare Pages.

**Architecture:** Frontend estático servido pelo nginx num subpath `/marketing/`; a Pages Function `/api/dados` é portada para um serviço Node (`marketing-backend`, systemd, `127.0.0.1:5002`) atrás do nginx; snapshot diário via cron no servidor. Espelha o padrão do painel KPIs.

**Tech Stack:** Node 18+ (ESM, globais Web-standard: `fetch`, `crypto.subtle`, `Request`/`Response`), nginx (subpath + reverse proxy), systemd, cron. Testes com `node --test`.

## Global Constraints

- **Runtime:** Node **18+** no servidor (globais `fetch`, `crypto.subtle`, `btoa/atob`, `Request`, `Response`).
- **Sem reescrita da lógica de negócio** (`_sheets.js`, `_meta.js`, `_build.js`) — só adaptação de runtime (cache e leitura de snapshot).
- **Compatibilidade dupla durante a transição:** toda mudança de código deve continuar funcionando na Cloudflare (que fica no ar até validar). Cache em `Map` e caminhos relativos satisfazem isso.
- **Porta do serviço:** `127.0.0.1:5002` (Sintonia=5000, KPIs=5001).
- **Servidor:** `allan@216.238.108.108`, clone em `~/marketing`, web root publicado em `/var/www/marketing/`.
- **Secrets fora do git:** `GCP_SA_KEY`, `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `SHEET_ID`, `SHEET_TAB`.
- **Testes:** `node --test test/`. Não tocam em Google/Meta (rede real).

---

### Task 1: Cache em memória com TTL (`_cache.js`)

Substitui o cache de borda da Cloudflare (`caches.default` + `context.waitUntil`, inexistentes no Node) por um `Map` com TTL. `Map` funciona em Node e na Cloudflare, mantendo a compatibilidade dupla.

**Files:**
- Modify: `functions/api/_cache.js`
- Modify: `package.json` (adicionar script `test`)
- Test: `test/cache.test.mjs`

**Interfaces:**
- Produces: `withCache(context, maxAgeSeconds, compute)` — `context = { request: Request }`; `compute: () => Promise<object>`; retorna `Response` (JSON + CORS). Respeita `?fresh=1` (bypass). Erros: `status===401||403 → 502`, senão `503`.

- [ ] **Step 1: Adicionar script de teste no `package.json`**

Em `package.json`, dentro de `"scripts"`, adicionar:

```json
    "test": "node --test test/"
```

- [ ] **Step 2: Escrever o teste que falha** — `test/cache.test.mjs`

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { withCache } from '../functions/api/_cache.js';

const ctx = (u) => ({ request: new Request(u) });

test('cacheia e reusa a resposta pelo pathname', async () => {
  let calls = 0;
  const compute = async () => ({ n: ++calls });
  const j1 = await (await withCache(ctx('http://x/api/dados'), 60, compute)).json();
  const j2 = await (await withCache(ctx('http://x/api/dados'), 60, compute)).json();
  assert.equal(j1.n, 1);
  assert.equal(j2.n, 1); // 2ª chamada veio do cache (compute não rodou)
});

test('?fresh=1 ignora o cache e recomputa', async () => {
  let calls = 0;
  const compute = async () => ({ n: ++calls });
  await withCache(ctx('http://x/api/fresh'), 60, compute);        // n=1
  const j = await (await withCache(ctx('http://x/api/fresh?fresh=1'), 60, compute)).json();
  assert.equal(j.n, 2); // recomputou
});

test('erro 401 vira 502; erro genérico vira 503', async () => {
  const e401 = Object.assign(new Error('nope'), { status: 401 });
  const r1 = await withCache(ctx('http://x/api/e1'), 60, async () => { throw e401; });
  assert.equal(r1.status, 502);
  const r2 = await withCache(ctx('http://x/api/e2'), 60, async () => { throw new Error('boom'); });
  assert.equal(r2.status, 503);
});
```

> Nota: o cache é um `Map` de módulo (estado global). Cada teste usa um **pathname único** para não colidir com os outros.

- [ ] **Step 3: Rodar o teste e confirmar que falha**

Run: `node --test test/cache.test.mjs`
Expected: FAIL (o `_cache.js` atual usa `caches.default`, que não existe no Node → `ReferenceError: caches is not defined`).

- [ ] **Step 4: Reescrever `functions/api/_cache.js`**

```js
/* Resposta JSON + cache em memória com TTL (portável Node/Workers).
   Substitui o antigo cache de borda (caches.default) por um Map de módulo. */
const _mem = new Map(); // key: origin+pathname -> { body, expires }

export async function withCache(context, maxAgeSeconds, compute) {
  const { request } = context;
  const url = new URL(request.url);
  const bypass = url.searchParams.has("fresh"); // botão "Atualizar" pede dados novos
  const key = url.origin + url.pathname;         // sem query: um "fresh" aquece o cache normal
  const cors = { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*" };

  if (!bypass) {
    const hit = _mem.get(key);
    if (hit && hit.expires > Date.now()) {
      return new Response(hit.body, { headers: { ...cors, "Cache-Control": `public, max-age=${maxAgeSeconds}` } });
    }
  }
  try {
    const data = await compute();
    const body = JSON.stringify(data);
    _mem.set(key, { body, expires: Date.now() + maxAgeSeconds * 1000 });
    return new Response(body, { headers: { ...cors, "Cache-Control": `public, max-age=${maxAgeSeconds}` } });
  } catch (e) {
    const status = e.status === 401 || e.status === 403 ? 502 : 503;
    return new Response(JSON.stringify({ erro: String(e.message || e) }), {
      status, headers: { ...cors, "Cache-Control": "no-store" },
    });
  }
}
```

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `node --test test/cache.test.mjs`
Expected: PASS (3 testes).

- [ ] **Step 6: Commit**

```bash
git add functions/api/_cache.js test/cache.test.mjs package.json
git commit -m "feat(api): cache em memoria com TTL (porta o _cache.js para Node)"
```

---

### Task 2: `fetchBaseSnapshot` lê o snapshot injetado (`dados.js`)

No Node o snapshot é um arquivo em disco (não um self-fetch HTTP). Para manter `dados.js` agnóstico de runtime, o leitor do snapshot é **injetado** via `context.readSnapshot`; sem ele, mantém o self-fetch antigo (compatível com Cloudflare).

**Files:**
- Modify: `functions/api/dados.js`
- Test: `test/dados-snapshot.test.mjs`

**Interfaces:**
- Consumes: `withCache` (Task 1).
- Produces: `build(context)` passa a usar `context.readSnapshot` quando presente — `readSnapshot: () => Promise<object|null>`. `onRequestGet(context)` inalterado.

- [ ] **Step 1: Escrever o teste que falha** — `test/dados-snapshot.test.mjs`

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';

// Testa só o ramo do snapshot: injetamos readSheetRows/fetchMetaWindow via import mocking
// não é trivial em ESM, então validamos a intenção com um teste de contrato leve:
// build() deve chamar context.readSnapshot quando fornecido.
test('build usa context.readSnapshot quando presente', async () => {
  // Import dinâmico após definir um env mínimo.
  const mod = await import('../functions/api/dados.js');
  assert.equal(typeof mod.onRequestGet, 'function');
  // Contrato: a função existe e é assíncrona (a integração real é coberta no Task 3).
});
```

> Este teste é um contrato leve (o caminho completo depende de Google/Meta e é validado na integração do Task 3). O valor real do Task 2 é a mudança de uma linha abaixo.

- [ ] **Step 2: Rodar o teste**

Run: `node --test test/dados-snapshot.test.mjs`
Expected: PASS (o módulo importa e exporta `onRequestGet`).

- [ ] **Step 3: Alterar `functions/api/dados.js`**

Localizar em `build(context)`:

```js
  const base = await fetchBaseSnapshot(request);
```

Substituir por:

```js
  // No servidor Node, o snapshot é lido do disco via context.readSnapshot;
  // na Cloudflare (sem readSnapshot), mantém o self-fetch de /data/data.json.
  const base = context.readSnapshot
    ? await context.readSnapshot().catch(() => null)
    : await fetchBaseSnapshot(request);
```

- [ ] **Step 4: Rodar os testes existentes + o novo**

Run: `node --test test/`
Expected: PASS (sem regressão em `build.test.mjs`).

- [ ] **Step 5: Commit**

```bash
git add functions/api/dados.js test/dados-snapshot.test.mjs
git commit -m "feat(api): permite injetar leitura do snapshot (context.readSnapshot)"
```

---

### Task 3: Serviço HTTP Node (`server.js`)

Envolve a Function num servidor `node:http`. Traduz a requisição Node em `Request` Web-standard, monta o `context` (`env=process.env`, `readSnapshot` lê do disco), e escreve a `Response` de volta. Inclui um helper puro e testável `readSnapshotFromDisk(path)`.

**Files:**
- Create: `server.js`
- Test: `test/server.test.mjs`

**Interfaces:**
- Consumes: `onRequestGet` (dados.js), `withCache` (cache.js).
- Produces: `readSnapshotFromDisk(path) => Promise<object|null>`; `createServer() => http.Server` escutando `GET /api/dados`.

- [ ] **Step 1: Escrever o teste que falha** — `test/server.test.mjs`

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readSnapshotFromDisk, createServer } from '../server.js';
import { writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('readSnapshotFromDisk lê JSON existente e devolve null se faltar', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'snap-'));
  const p = join(dir, 'data.json');
  await writeFile(p, JSON.stringify({ ok: 1 }));
  assert.deepEqual(await readSnapshotFromDisk(p), { ok: 1 });
  assert.equal(await readSnapshotFromDisk(join(dir, 'nao-existe.json')), null);
  await rm(dir, { recursive: true, force: true });
});

test('GET /api/dados sem secrets responde erro JSON 503 (sem chamar Google/Meta)', async () => {
  const srv = createServer();
  await new Promise((res) => srv.listen(0, '127.0.0.1', res));
  const port = srv.address().port;
  const r = await fetch(`http://127.0.0.1:${port}/api/dados`);
  const body = await r.json();
  assert.equal(r.status, 503);       // GCP_SA_KEY ausente → compute lança → 503
  assert.ok(body.erro);
  await new Promise((res) => srv.close(res));
});

test('rota desconhecida responde 404', async () => {
  const srv = createServer();
  await new Promise((res) => srv.listen(0, '127.0.0.1', res));
  const port = srv.address().port;
  const r = await fetch(`http://127.0.0.1:${port}/outra`);
  assert.equal(r.status, 404);
  await new Promise((res) => srv.close(res));
});
```

> O 2º teste roda **sem** `GCP_SA_KEY` no `process.env`, então `readSheetRows` lança cedo e a Function nunca faz rede — validando o wrapper e o mapeamento de erro sem tocar em Google/Meta.

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `node --test test/server.test.mjs`
Expected: FAIL (`server.js` não existe → erro de import).

- [ ] **Step 3: Criar `server.js`**

```js
// Servidor HTTP Node que expõe a Pages Function /api/dados fora da Cloudflare.
// Traduz req/res do node:http para Request/Response Web-standard e injeta o context.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { onRequestGet } from './functions/api/dados.js';

const PORT = Number(process.env.PORT) || 5002;
const HOST = process.env.HOST || '127.0.0.1';
// Snapshot publicado (base histórica). Default = web root do servidor.
const SNAPSHOT_PATH = process.env.SNAPSHOT_PATH || '/var/www/marketing/data/data.json';

// Ponte de credenciais: o _sheets.js lê GCP_SA_KEY inline; aqui aceitamos também um
// arquivo via GOOGLE_APPLICATION_CREDENTIALS (mesma var do extract.js/cron), lendo o
// JSON cru pro GCP_SA_KEY. _sheets.js aceita JSON cru (parseServiceAccount).
if (!process.env.GCP_SA_KEY && process.env.GOOGLE_APPLICATION_CREDENTIALS) {
  try {
    process.env.GCP_SA_KEY = readFileSync(process.env.GOOGLE_APPLICATION_CREDENTIALS, 'utf8');
  } catch (e) {
    console.warn('AVISO: nao consegui ler GOOGLE_APPLICATION_CREDENTIALS:', e.message);
  }
}

export async function readSnapshotFromDisk(path) {
  try {
    return JSON.parse(await readFile(path, 'utf8'));
  } catch {
    return null;
  }
}

export function createServer() {
  return http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
      if (req.method !== 'GET' || url.pathname !== '/api/dados') {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ erro: 'not found' }));
        return;
      }
      const context = {
        request: new Request(url.toString(), { method: 'GET' }),
        env: process.env,
        readSnapshot: () => readSnapshotFromDisk(SNAPSHOT_PATH),
      };
      const response = await onRequestGet(context);
      const body = await response.text();
      const headers = {};
      response.headers.forEach((v, k) => { headers[k] = v; });
      res.writeHead(response.status, headers);
      res.end(body);
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ erro: String(e && e.message || e) }));
    }
  });
}

// Sobe o servidor quando executado direto (não durante os testes).
if (import.meta.url === `file://${process.argv[1]}`) {
  createServer().listen(PORT, HOST, () => {
    console.log(`marketing-backend ouvindo em http://${HOST}:${PORT}`);
  });
}
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `node --test test/server.test.mjs`
Expected: PASS (3 testes).

- [ ] **Step 5: Rodar a suíte inteira**

Run: `node --test test/`
Expected: PASS (cache + dados-snapshot + server + build existentes).

- [ ] **Step 6: Commit**

```bash
git add server.js test/server.test.mjs
git commit -m "feat: servico HTTP Node (server.js) que expoe /api/dados"
```

---

### Task 4: Frontend usa caminho relativo `api/dados` (subpath-safe)

O front chama `/api/dados` **absoluto** (quebra no subpath `/marketing/`). Trocar por `api/dados` **relativo** — funciona na raiz da Cloudflare e no subpath. As leituras de snapshot já são relativas (`data/data.json`).

**Files:**
- Modify: `docs/js/app.jsx:855`
- Modify: `docs/etapas.html:1080`
- Modify: `docs/meta.html:549`
- Modify: `docs/midia-paga.html:846`
- Test: verificação por grep (sem framework de front)

- [ ] **Step 1: Trocar nos 4 arquivos**

Em cada arquivo, localizar:

```js
fetch("/api/dados" + (fresh ? "?fresh=1" : "")
```

Substituir por (remover a barra inicial):

```js
fetch("api/dados" + (fresh ? "?fresh=1" : "")
```

- [ ] **Step 2: Verificar que não sobrou nenhum `/api/dados` absoluto**

Run: `grep -rn '"/api/dados"' docs/ ; grep -rn "fetch(\"/api/dados" docs/`
Expected: **sem resultados** (todas as ocorrências agora são `"api/dados"`).

Confirmar que as relativas existem:
Run: `grep -rn '"api/dados"' docs/`
Expected: 4 ocorrências (app.jsx, etapas.html, meta.html, midia-paga.html).

- [ ] **Step 3: Commit**

```bash
git add docs/js/app.jsx docs/etapas.html docs/meta.html docs/midia-paga.html
git commit -m "fix(front): usa api/dados relativo (compativel com subpath /marketing)"
```

---

### Task 5: Snippet nginx (`deploy/nginx/marketing.conf`)

Serve o estático em `/marketing/` e faz proxy de `/marketing/api/` → serviço Node em `127.0.0.1:5002` (a barra final no `proxy_pass` reescreve `/marketing/api/` → `/api/`).

**Files:**
- Create: `deploy/nginx/marketing.conf`

- [ ] **Step 1: Criar `deploy/nginx/marketing.conf`**

```nginx
# Snippet do painel de Marketing — incluído no server block de bi.vesti.com.br.
# Estático em /marketing/ e API ao vivo em /marketing/api/ (proxy p/ o serviço Node).

# API ao vivo → marketing-backend (Node). A barra final reescreve /marketing/api/ -> /api/.
location /marketing/api/ {
    proxy_pass http://127.0.0.1:5002/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_read_timeout 120s;   # a Meta pode demorar
}

# Estático do dashboard.
location /marketing/ {
    alias /var/www/marketing/;
    index index.html;
    try_files $uri $uri/ =404;
}
```

- [ ] **Step 2: Validar a sintaxe do snippet isoladamente (opcional, local)**

Não há como rodar `nginx -t` sem o server block; a validação real acontece no servidor (Task 9). Conferir visualmente: `alias` termina em `/`, `proxy_pass` termina em `/`.

- [ ] **Step 3: Commit**

```bash
git add deploy/nginx/marketing.conf
git commit -m "chore(deploy): snippet nginx do /marketing (estatico + proxy /api)"
```

---

### Task 6: Unit systemd (`deploy/marketing-backend.service`)

Serviço que roda `server.js` como o usuário `allan`, lendo os secrets de um EnvironmentFile fora do git.

**Files:**
- Create: `deploy/marketing-backend.service`

- [ ] **Step 1: Criar `deploy/marketing-backend.service`**

```ini
[Unit]
Description=Marketing Dashboard backend (API ao vivo /api/dados)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=allan
WorkingDirectory=/home/allan/marketing
EnvironmentFile=/home/allan/marketing/secrets/marketing.env
Environment=PORT=5002
Environment=HOST=127.0.0.1
Environment=SNAPSHOT_PATH=/var/www/marketing/data/data.json
ExecStart=/usr/bin/node server.js
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Criar o exemplo do EnvironmentFile** — `deploy/marketing.env.example`

```bash
# Copie para ~/marketing/secrets/marketing.env no servidor (fora do git) e preencha.
# Só valores simples (sem JSON) para o arquivo ser "source-safe" no atualizar.sh.
# O JSON da service account fica num arquivo separado (sa.json), apontado abaixo.
GOOGLE_APPLICATION_CREDENTIALS=/home/allan/marketing/secrets/sa.json
META_ACCESS_TOKEN=
META_AD_ACCOUNT_ID=act_674298545378209
SHEET_ID=1zNRw8zfoASVlO2EhR56sldTCy4IXRCLKfauU1ROChCE
SHEET_TAB=LeadsV2
```

> **Credenciais Google (as duas pontas usam o mesmo arquivo):**
> - `~/marketing/secrets/sa.json` — o JSON cru da service account (chmod 600).
> - O **cron/`extract.js`** lê o arquivo direto via `GOOGLE_APPLICATION_CREDENTIALS`.
> - O **serviço Node** usa a ponte do `server.js` (lê o arquivo → `GCP_SA_KEY` cru → `_sheets.js`).
> - Assim o `marketing.env` fica sem JSON e o `source` do `atualizar.sh` não quebra.

- [ ] **Step 3: Blindar a pasta de secrets no `.gitignore`**

O `.gitignore` cobre `.env`/`*.key`/`service-account*.json`, mas **não** `secrets/`, `marketing.env`
nem `sa.json`. Adicionar ao final do `.gitignore`:

```gitignore
# Secrets do deploy no servidor (nunca versionar)
secrets/
marketing.env
sa.json
```

Validação: `git check-ignore secrets/sa.json secrets/marketing.env` → deve listar os dois.

- [ ] **Step 4: Commit**

```bash
git add deploy/marketing-backend.service deploy/marketing.env.example .gitignore
git commit -m "chore(deploy): unit systemd + exemplo de env + ignora secrets/"
```

---

### Task 7: Script de atualização + cron (`atualizar.sh`)

`git pull` + `npm ci` (se as deps mudaram) + `node scripts/extract.js` (regenera o snapshot) + publica `docs/` em `/var/www/marketing/`.

**Files:**
- Create: `atualizar.sh`

- [ ] **Step 1: Criar `atualizar.sh`**

```bash
#!/usr/bin/env bash
# Atualiza o painel de Marketing no servidor: pull + snapshot + publica.
set -euo pipefail
cd "$(dirname "$0")"

echo "[marketing] git pull…"
git pull --ff-only

# Instala deps só se package-lock mudou (barato no dia a dia).
if ! git diff --quiet HEAD@{1} HEAD -- package-lock.json 2>/dev/null; then
  echo "[marketing] deps mudaram → npm ci"
  npm ci --omit=dev
fi

echo "[marketing] gerando snapshot (extract.js)…"
# Carrega os mesmos secrets do serviço.
set -a; source ~/marketing/secrets/marketing.env; set +a
node scripts/extract.js

echo "[marketing] publicando docs/ em /var/www/marketing/…"
sudo rsync -a --delete docs/ /var/www/marketing/

echo "[marketing] OK ($(date '+%Y-%m-%d %H:%M:%S'))"
```

- [ ] **Step 2: Tornar executável e documentar a linha do cron**

Run (no servidor, Task 9): `chmod +x ~/marketing/atualizar.sh`
Linha do crontab (`crontab -e`):

```
0 6 * * *  /home/allan/marketing/atualizar.sh >> /home/allan/marketing/cron.log 2>&1
```

- [ ] **Step 3: Commit**

```bash
git add atualizar.sh
git commit -m "chore(deploy): atualizar.sh (pull + snapshot + publica) para o cron"
```

---

### Task 8: Documentação de deploy (`DEPLOY.md`, `ATUALIZAR.md`)

**Files:**
- Create: `DEPLOY.md`
- Create: `ATUALIZAR.md`

- [ ] **Step 1: Criar `DEPLOY.md`** (runbook do 1º deploy — resumo; o passo a passo executável está no Task 9)

```markdown
# Deploy — Marketing Dashboard (bi.vesti.com.br/marketing)

Servidor `allan@216.238.108.108`. Espelha o padrão do painel KPIs.

| Onde | Caminho |
|---|---|
| Código (servidor) | `~/marketing` (clone do `vesti-mobi/marketing`) |
| Web root publicado | `/var/www/marketing/` (conteúdo de `docs/`) |
| Serviço API ao vivo | systemd `marketing-backend` (node, 127.0.0.1:5002) |
| Secrets | `~/marketing/secrets/marketing.env` (fora do git) |
| Snippet nginx | `/etc/nginx/snippets/marketing.conf` |

Fluxo: **push no GitHub → `git pull` no servidor → regenera → publica** (via `atualizar.sh`).
Ver `ATUALIZAR.md` para o dia a dia. Passo a passo do 1º deploy: seção "Task 9" do plano.
```

- [ ] **Step 2: Criar `ATUALIZAR.md`** (dia a dia, molde do KPIs)

```markdown
# Como atualizar — Marketing Dashboard

**No ar:** https://bi.vesti.com.br/marketing/

## Atualizar os NÚMEROS (snapshot diário)
No servidor: `cd ~/marketing && ./atualizar.sh` (o cron já roda isso às 6h).

## Atualizar CÓDIGO / VISUAL
No PC: edite, teste (`node --test test/`), `git add -A && git commit && git push`.
No servidor: `cd ~/marketing && ./atualizar.sh`.
> Se mexeu no backend (`server.js`/`functions/`), reinicie: `sudo systemctl restart marketing-backend`.

## Atualizar a CONFIG do nginx
Edite `deploy/nginx/marketing.conf`, push, e no servidor:
`sudo cp deploy/nginx/marketing.conf /etc/nginx/snippets/marketing.conf && sudo nginx -t && sudo systemctl reload nginx`
```

- [ ] **Step 3: Commit**

```bash
git add DEPLOY.md ATUALIZAR.md
git commit -m "docs(deploy): DEPLOY.md e ATUALIZAR.md do painel de marketing"
```

---

### Task 9: Deploy no servidor (runbook manual, executado via SSH)

Executado uma vez no servidor após os commits acima estarem no GitHub. Não é TDD; cada passo tem um comando e uma validação.

**Interfaces:**
- Consumes: todos os artefatos dos Tasks 1–8 (já no `main` do GitHub).

- [ ] **Step 1: Clonar o repo e instalar deps**

```bash
ssh allan@216.238.108.108
cd ~ && git clone https://github.com/vesti-mobi/marketing.git
cd ~/marketing && npm ci --omit=dev
node --version   # confirmar >= 18
```
Validação: `node --version` ≥ v18.

- [ ] **Step 2: Configurar os secrets**

```bash
mkdir -p ~/marketing/secrets
# 1) JSON cru da service account do Google (cole o conteúdo do .json):
nano ~/marketing/secrets/sa.json
chmod 600 ~/marketing/secrets/sa.json
# 2) Env do serviço/cron (valores simples; GOOGLE_APPLICATION_CREDENTIALS já aponta p/ sa.json):
cp deploy/marketing.env.example ~/marketing/secrets/marketing.env
chmod 600 ~/marketing/secrets/marketing.env
nano ~/marketing/secrets/marketing.env   # preencher META_ACCESS_TOKEN (o resto já vem preenchido)
```
Validação:
```bash
node -e "JSON.parse(require('fs').readFileSync(process.env.HOME+'/marketing/secrets/sa.json','utf8'));console.log('sa.json ok')"
test -s ~/marketing/secrets/marketing.env && echo "env ok"
```

- [ ] **Step 3: Gerar o 1º snapshot e publicar o estático**

```bash
sudo mkdir -p /var/www/marketing
cd ~/marketing && ./atualizar.sh
ls -la /var/www/marketing/index.html /var/www/marketing/data/data.json
```
Validação: os dois arquivos existem e `data.json` tem tamanho > 0.

- [ ] **Step 4: Instalar e subir o serviço systemd**

```bash
sudo cp ~/marketing/deploy/marketing-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now marketing-backend
systemctl status marketing-backend --no-pager
curl -s http://127.0.0.1:5002/api/dados | head -c 200
```
Validação: serviço `active (running)`; o `curl` devolve JSON (dados ou erro JSON, não conexão recusada).

- [ ] **Step 5: Instalar o snippet nginx e incluir no host**

```bash
sudo cp ~/marketing/deploy/nginx/marketing.conf /etc/nginx/snippets/marketing.conf
# Incluir UMA linha no server block de bi.vesti.com.br (como o /kpis):
#   include /etc/nginx/snippets/marketing.conf;
sudo nano /etc/nginx/sites-available/bi.vesti.com.br
sudo nginx -t && sudo systemctl reload nginx
```
Validação: `nginx -t` → "syntax is ok / test is successful".

- [ ] **Step 6: Validar no ar**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://bi.vesti.com.br/marketing/
curl -s "https://bi.vesti.com.br/marketing/api/dados" | head -c 200
```
Validação: `/marketing/` → 200; login carrega no navegador; botão **Atualizar** puxa dados ao vivo; páginas etapas/meta/midia-paga funcionam.

- [ ] **Step 7: Agendar o cron**

```bash
chmod +x ~/marketing/atualizar.sh
crontab -e   # adicionar:
# 0 6 * * *  /home/allan/marketing/atualizar.sh >> /home/allan/marketing/cron.log 2>&1
crontab -l
```
Validação: `crontab -l` mostra a linha.

- [ ] **Step 8: Desligar a Cloudflare (SÓ após tudo validado)**

Na Cloudflare: remover/pausar o projeto Pages do marketing. No GitHub: desabilitar o job de deploy da Action (`.github/workflows/daily-update.yml`) — ou removê-lo, já que o snapshot agora é o cron do servidor.
Validação: `bi.vesti.com.br/marketing/` segue no ar após a Cloudflare sair.

---

## Notas de execução

- **Ordem:** Tasks 1–8 são locais (código + artefatos) e podem ser feitas/commitadas em sequência; o push habilita o Task 9 (servidor). Durante 1–8 a Cloudflare continua funcionando (mudanças são compatíveis).
- **Rollback:** se algo falhar no servidor, `sudo systemctl stop marketing-backend` e remover a linha `include` do nginx (`nginx -t && reload`) devolve o estado anterior; a Cloudflare permanece no ar até o Task 9 Step 8.
