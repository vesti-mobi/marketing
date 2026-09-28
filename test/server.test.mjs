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
