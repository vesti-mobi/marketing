# Deploy — Marketing Dashboard (bi.vesti.com.br/marketing)

Servidor `allan@216.238.108.108`. Espelha o padrão do painel KPIs.

| Onde | Caminho |
|---|---|
| Código (servidor) | `~/marketing` (clone do `vesti-mobi/marketing`) |
| Web root publicado | `/var/www/marketing/` (conteúdo de `docs/`) |
| Serviço API ao vivo | systemd `marketing-backend` (node, 127.0.0.1:5002) |
| Secrets | `~/marketing/secrets/marketing.env` + `~/marketing/secrets/sa.json` (fora do git) |
| Snippet nginx | `/etc/nginx/snippets/marketing.conf` |

Fluxo: **push no GitHub → `git pull` no servidor → regenera → publica** (via `atualizar.sh`).

Credenciais Google: o JSON cru da service account fica em `secrets/sa.json`; o `marketing.env`
aponta `GOOGLE_APPLICATION_CREDENTIALS` para ele. O `extract.cjs` (cron) lê o arquivo direto;
o serviço Node usa a ponte do `server.js` (arquivo → `GCP_SA_KEY`).

Ver `ATUALIZAR.md` para o dia a dia. Passo a passo do 1º deploy: seção "Task 9" do plano
(`plans/2026-09-28-migrar-marketing-servidor-vesti.md`).
