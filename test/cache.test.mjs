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
