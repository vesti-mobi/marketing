# Deploy — Marketing Dashboard (bi.vesti.com.br/marketing)

Servidor `allan@216.238.108.108`. Espelha o padrão do painel KPIs (**Python/Flask/gunicorn/venv**).

| Onde | Caminho |
|---|---|
| Código (servidor) | `~/marketing` (clone do `vesti-mobi/marketing`) |
| Web root publicado | `/var/www/marketing/` (conteúdo de `docs/`) |
| venv | `~/marketing/.venv` |
| Serviço API ao vivo | systemd `marketing-backend` (gunicorn `backend.app:app`, 127.0.0.1:5002) |
| Secrets | `~/marketing/secrets/marketing.env` + `~/marketing/secrets/sa.json` (fora do git) |
| Snippet nginx | `/etc/nginx/snippets/marketing.conf` |

Fluxo: **push no GitHub → `git pull` no servidor → regenera → publica** (via `atualizar.sh`).

**Credenciais Google:** o JSON cru da service account fica em `secrets/sa.json`; o `marketing.env`
aponta `GOOGLE_APPLICATION_CREDENTIALS` para ele. O `gerar_marketing.py` (cron) e o backend Flask
leem esse arquivo direto (não precisa de ponte).

## Instalação (1ª vez)
```bash
cd ~ && git clone https://github.com/vesti-mobi/marketing.git && cd marketing
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r backend/requirements.txt
# secrets:
mkdir -p secrets && nano secrets/sa.json           # JSON cru da service account
cp deploy/marketing.env.example secrets/marketing.env && nano secrets/marketing.env  # META_ACCESS_TOKEN
chmod 600 secrets/sa.json secrets/marketing.env
# 1º snapshot + publicar:
sudo mkdir -p /var/www/marketing && sudo chown allan:allan /var/www/marketing
chmod +x atualizar.sh && ./atualizar.sh
# serviço + nginx + cron:
sudo cp deploy/marketing-backend.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now marketing-backend
curl -s http://127.0.0.1:5002/api/health          # -> {"status":"ok"}
sudo cp deploy/nginx/marketing.conf /etc/nginx/snippets/marketing.conf
# incluir 1 linha "include /etc/nginx/snippets/marketing.conf;" no server{} de bi.vesti.com.br
sudo nginx -t && sudo systemctl reload nginx
# cron 6h: 0 6 * * * /home/allan/marketing/atualizar.sh >> ~/marketing/cron.log 2>&1
```

Ver `ATUALIZAR.md` para o dia a dia.
