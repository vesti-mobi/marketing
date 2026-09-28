# Como atualizar — Marketing Dashboard

**No ar:** https://bi.vesti.com.br/marketing/

## Atualizar os NÚMEROS (snapshot diário)
No servidor: `cd ~/marketing && ./atualizar.sh` (o cron já roda isso às 6h).

## Atualizar CÓDIGO / VISUAL
No PC: edite, teste (`python -m pytest test/`), `git add -A && git commit && git push`.
No servidor: `cd ~/marketing && ./atualizar.sh`.
> Se mexeu no backend (`backend/`, `marketing_data/`, `gerar_marketing.py`), reinicie o serviço:
> `sudo systemctl restart marketing-backend`.

## Atualizar a CONFIG do nginx
Edite `deploy/nginx/marketing.conf`, push, e no servidor:
`sudo cp deploy/nginx/marketing.conf /etc/nginx/snippets/marketing.conf && sudo nginx -t && sudo systemctl reload nginx`
