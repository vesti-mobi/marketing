# Deploy — Marketing Dashboard (bi.vesti.com.br/marketing)

Servidor `allan@216.238.108.108` (`vesti-site`). Backend **Python/Flask/gunicorn/venv**,
espelhando o padrão do painel KPIs. Roda **ao lado** de `/kpis`, `/sintonia`, `/vesti-pago`
no mesmo hub nginx `bi.vesti.com.br` — o único toque no hub é **uma linha de `include`**.

> **Por que Python e não Node?** O servidor só tem Node 12 (velho demais p/ a Function
> original). O backend foi reescrito em Python, que já está no servidor (3.10) — sem instalar
> nada no sistema, só um `venv` isolado. O backend Node (`server.js`, `functions/`) continua no
> repo servindo a Cloudflare de fallback até validar o servidor.

| Onde | Caminho |
|---|---|
| Código (servidor) | `~/marketing` (clone do `vesti-mobi/marketing`) |
| venv | `~/marketing/.venv` |
| Web root publicado | `/var/www/marketing/` (dono `allan:allan`, conteúdo de `docs/`) |
| Serviço API ao vivo | systemd `marketing-backend` (gunicorn `backend.app:app`, `127.0.0.1:5002`) |
| Secrets (fora do git) | `~/marketing/secrets/{sa.json, meta.json, marketing.env}` |
| Snippet nginx | `/etc/nginx/snippets/marketing.conf` (incluído no host `bi.vesti.com.br`) |
| Cron | diário, `atualizar.sh` (git pull + gera snapshot + publica) |

Portas no servidor: Sintonia `5000`, KPIs `5001`, **Marketing `5002`**.

---

## Pré-requisitos (checar antes — read-only)

```bash
python3 --version                 # 3.10+ (Ubuntu 22.04 tem)
python3 -m venv /tmp/_v && echo "venv OK" && rm -rf /tmp/_v
sudo ss -ltnp | grep ':5002' || echo "5002 LIVRE"          # deve estar livre
grep -n 'snippets' /etc/nginx/sites-available/bi.vesti.com.br   # includes atuais (sintonia, kpis...)
```

## 1. Clonar + venv + deps (isolado, nada global)

```bash
cd ~ && git clone https://github.com/vesti-mobi/marketing.git && cd marketing
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r backend/requirements.txt
python -c "import flask, gunicorn, googleapiclient, google.auth, requests; print('deps ok')"
```
> A cada novo login SSH, reative o venv: `cd ~/marketing && . .venv/bin/activate`.

## 2. Secrets (colar no `nano`, **não** scp)

As credenciais ficam no PC em `C:\Users\gusth\.secrets\` (`sheets-sa.json`, `meta.json`).
No servidor, cole o conteúdo com `nano` (igual ao KPIs):

```bash
mkdir -p secrets
nano secrets/sa.json      # cole o conteudo de sheets-sa.json (o GRANDE, ~2.4KB, tem private_key/client_email)
nano secrets/meta.json    # cole o conteudo de meta.json (~267B, {access_token, ad_account_id})
```
Salvar no nano: **Ctrl+O → Enter → Ctrl+X**. Validar:
```bash
python3 -c "import json; d=json.load(open('secrets/sa.json')); print('sa.json OK', d['client_email'])"
python3 -c "import json; m=json.load(open('secrets/meta.json')); print('meta OK', m['ad_account_id'])"
```
> A service account precisa ter acesso de leitura à planilha `LeadsV2`. Se der 403, compartilhe
> a planilha com o `client_email` da SA (ex.: `sheets-bot@automacao-sheets-493517.iam.gserviceaccount.com`).

Montar o `marketing.env` a partir do `meta.json` (sem digitar o token):
```bash
cp deploy/marketing.env.example secrets/marketing.env
python3 - <<'PY'
import json, re
m = json.load(open('secrets/meta.json'))
acct = m['ad_account_id']; acct = acct if acct.startswith('act_') else 'act_'+acct
p='secrets/marketing.env'; s=open(p).read()
s=re.sub(r'^META_ACCESS_TOKEN=.*$','META_ACCESS_TOKEN='+m['access_token'],s,flags=re.M)
s=re.sub(r'^META_AD_ACCOUNT_ID=.*$','META_AD_ACCOUNT_ID='+acct,s,flags=re.M)
open(p,'w').write(s); print('marketing.env montado')
PY
chmod 600 secrets/sa.json secrets/meta.json secrets/marketing.env
```

## 3. 1º snapshot + publicar o estático

```bash
# gera o data.json (le Sheets + Meta ao vivo):
set -a; source secrets/marketing.env; set +a
python gerar_marketing.py --out docs/data/data.json
# publica o site:
sudo mkdir -p /var/www/marketing && sudo chown allan:allan /var/www/marketing
rsync -a --delete docs/ /var/www/marketing/
ls -l /var/www/marketing/index.html /var/www/marketing/data/data.json
```

## 4. Serviço da API ao vivo (systemd/gunicorn)

```bash
sudo cp deploy/marketing-backend.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now marketing-backend
systemctl status marketing-backend --no-pager | head -5     # active (running)
curl -s http://127.0.0.1:5002/api/health; echo               # {"status":"ok"}
```
> Mexeu no backend (`backend/`, `marketing_data/`, `gerar_marketing.py`)?
> `sudo systemctl restart marketing-backend`.

## 5. nginx — colocar `/marketing` no ar (com backup + teste)

```bash
sudo cp deploy/nginx/marketing.conf /etc/nginx/snippets/marketing.conf
# BACKUP do host antes de editar:
sudo cp /etc/nginx/sites-available/bi.vesti.com.br /etc/nginx/sites-available/bi.vesti.com.br.bak-marketing-$(date +%F)
# adiciona o include logo apos o do kpis (sem editar a mao):
sudo sed -i '/include \/etc\/nginx\/snippets\/kpis.conf;/a include /etc/nginx/snippets/marketing.conf;' /etc/nginx/sites-available/bi.vesti.com.br
sudo nginx -t          # DEVE dizer "syntax is ok / test is successful"
```
- **Se `nginx -t` passou** → `sudo systemctl reload nginx`
- **Se falhou** → restaura e NÃO recarrega:
  `sudo cp /etc/nginx/sites-available/bi.vesti.com.br.bak-marketing-$(date +%F) /etc/nginx/sites-available/bi.vesti.com.br`

Validar:
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://bi.vesti.com.br/marketing/   # 200
curl -s https://bi.vesti.com.br/marketing/api/health; echo                    # {"status":"ok"}
```
Abrir no navegador **https://bi.vesti.com.br/marketing/** (login `Marketing1961`, testar o botão **Atualizar**).

## 6. Cron diário (atualiza o snapshot sozinho)

```bash
chmod +x ~/marketing/atualizar.sh
# adiciona a linha sem abrir editor (preserva o cron do KPIs):
( crontab -l 2>/dev/null; echo '10 6 * * *  /home/allan/marketing/atualizar.sh >> /home/allan/marketing/cron.log 2>&1' ) | crontab -
crontab -l | grep marketing
```
> `atualizar.sh` = `git pull` (restaura o `data.json` antes p/ não conflitar) + gera o snapshot +
> publica em `/var/www/marketing/` (rsync **sem** sudo, pois a pasta é do `allan`).

## 7. Desligar a Cloudflare (SÓ após validar tudo acima)

Na Cloudflare: remover/pausar o projeto Pages do marketing. Depois disso, o `/marketing` no ar
passa a ser **só** o servidor Vesti.

---

## Notas / troubleshooting
- **Serviço `failed`:** `journalctl -u marketing-backend -n 30 --no-pager` (geralmente caminho do venv/módulo).
- **`git pull` reclama do `data.json`:** o `atualizar.sh` já restaura antes; manualmente é `git checkout -- docs/data/data.json`.
- **Backup do nginx:** `bi.vesti.com.br.bak-marketing-<data>` em `/etc/nginx/sites-available/`.
- **Warnings `conflicting server name "vestipago.com.br"` no `nginx -t`:** pré-existentes, não são do marketing.
- Dia a dia (atualizar dados/código): ver `ATUALIZAR.md`.
