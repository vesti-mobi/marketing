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

echo "[marketing] gerando snapshot (extract.cjs)…"
# Carrega os mesmos secrets do serviço.
set -a; source ~/marketing/secrets/marketing.env; set +a
node scripts/extract.cjs

echo "[marketing] publicando docs/ em /var/www/marketing/…"
sudo rsync -a --delete docs/ /var/www/marketing/

echo "[marketing] OK ($(date '+%Y-%m-%d %H:%M:%S'))"
