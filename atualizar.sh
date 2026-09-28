#!/usr/bin/env bash
# Atualiza o painel de Marketing no servidor: pull + snapshot (Python) + publica.
set -euo pipefail
# Vai pra pasta do script (robusto a symlink e a chamada de qualquer diretório).
cd "$(dirname "$(readlink -f "$0")")"

echo "[marketing] git pull…"
git pull --ff-only

echo "[marketing] venv + deps…"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt -r backend/requirements.txt

echo "[marketing] gerando snapshot (gerar_marketing.py)…"
# Carrega os secrets (valores simples; source-safe).
set -a; source secrets/marketing.env; set +a
python gerar_marketing.py --out docs/data/data.json

echo "[marketing] publicando docs/ em /var/www/marketing/…"
sudo rsync -a --delete docs/ /var/www/marketing/

echo "[marketing] OK ($(date '+%Y-%m-%d %H:%M:%S'))"
