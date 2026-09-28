// Servidor HTTP Node que expõe a Pages Function /api/dados fora da Cloudflare.
// Traduz req/res do node:http para Request/Response Web-standard e injeta o context.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
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
// pathToFileURL normaliza o caminho (Windows/Unix) — comparar strings cruas quebra no Windows.
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  createServer().listen(PORT, HOST, () => {
    console.log(`marketing-backend ouvindo em http://${HOST}:${PORT}`);
  });
}
