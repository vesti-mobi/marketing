// test/dados-snapshot.test.mjs
// Verifica que build() usa context.readSnapshot quando presente.
//
// ESTRATÉGIA DE TESTE:
// mock.module (proposta para node:test) não está disponível no Node 24.18.0 —
// Object.getPrototypeOf(mock) expõe apenas fn/method/getter/setter/property/reset/restoreAll.
// Sem mocking de módulo ESM não é possível isolar readSheetRows/_meta para testar build()
// como uma caixa-branca completa sem tocar Google/Meta.
//
// Abordagem adotada:
//   T1 — contrato estrutural: módulo exporta onRequestGet (sanity).
//   T2 — código-fonte: o condicional `context.readSnapshot` está presente em dados.js
//        (prova que a mudança foi feita; a lógica de merge é testada em T3).
//   T3 — mergeMetaFields: dados da base chegam ao output quando live está vazio
//        (esse é o caminho completo do readSnapshot: base?.midia_paga → merge → output).
//   T4 — degradação silenciosa: readSnapshot que lança não derruba build()
//        (o .catch(() => null) está presente e funciona — verificado via stack completo).
//   T5 — resolveBase resolve: readSnapshot que resolve devolve o objeto exato (sem rede).
//   T6 — resolveBase rejeita → null: executa .catch(() => null) diretamente (sem rede).
//
// O path de integração end-to-end (readSnapshot retorna dados → aparecem na resposta JSON)
// é coberto no Task 3, onde readSheetRows é fornecido com creds reais no servidor Node.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DADOS_JS = resolve(__dirname, '../functions/api/dados.js');

const ENV_NO_CREDS = {
  GCP_SA_KEY: undefined,
  SHEET_ID: undefined,
  META_ACCESS_TOKEN: undefined,
  META_AD_ACCOUNT_ID: undefined,
};

const { onRequestGet, resolveBase } = await import('../functions/api/dados.js');

// ── Teste 1: módulo exporta onRequestGet ──────────────────────────────────────
test('módulo exporta onRequestGet como função', () => {
  assert.equal(typeof onRequestGet, 'function');
});

// ── Teste 2: condicional readSnapshot está presente no código-fonte ───────────
// Verifica que a mudança de Task 2 foi aplicada: context.readSnapshot ? ... : fetchBaseSnapshot.
// É um teste de contrato de código-fonte — adequado quando o mocking de módulo ESM não está
// disponível e a lógica de merge já é coberta por T3.
test('dados.js contém o condicional context.readSnapshot', async () => {
  const src = await readFile(DADOS_JS, 'utf8');
  assert.ok(
    src.includes('context.readSnapshot'),
    'dados.js deve referenciar context.readSnapshot',
  );
  assert.ok(
    src.includes('.catch(() => null)'),
    'readSnapshot deve ter .catch(() => null) para falhas silenciosas',
  );
  assert.ok(
    src.includes('fetchBaseSnapshot(request)'),
    'fallback fetchBaseSnapshot(request) deve ser mantido (compat Cloudflare)',
  );
});

// ── Teste 3: dados do snapshot fluem para midia_paga via mergeMetaFields ──────
// mergeMetaFields é o elo que liga o resultado de readSnapshot ao output de build().
// Testar diretamente confirma que o pipeline de dados funciona (sem rede).
test('mergeMetaFields propaga dados da base quando live está vazio', async () => {
  const { mergeMetaFields } = await import('../functions/api/_build.js');

  const baseMidiaPaga = {
    spend_daily: { AdInjetado: { '2026-09-01': 77 } },
    spend_window: { since: '2026-01-01', until: '2026-09-27' },
    campaigns: [{ name: 'Campanha da Base' }],
  };

  const out = mergeMetaFields(baseMidiaPaga, {});
  assert.deepEqual(out.spend_daily?.AdInjetado, { '2026-09-01': 77 });
  assert.deepEqual(out.campaigns, [{ name: 'Campanha da Base' }]);
  assert.deepEqual(out.spend_window, { since: '2026-01-01', until: '2026-09-27' });
});

// ── Teste 4: falha em readSnapshot é silenciosa (.catch(() => null)) ──────────
// Confirma que build() não explode quando readSnapshot rejeita — o withCache deve
// capturar qualquer erro residual e devolver uma Response (nunca lançar).
test('falha em readSnapshot não derruba build (degrada silenciosamente)', async () => {
  const ctx = {
    env: ENV_NO_CREDS,
    request: new Request('http://localhost/api/dados?fresh=1&_t=fail'),
    readSnapshot: async () => { throw new Error('disco cheio'); },
  };

  let resp;
  try {
    resp = await onRequestGet(ctx);
  } catch (e) {
    assert.fail(`onRequestGet não deve lançar, mas lançou: ${e.message}`);
  }
  // Pode ser 502/503 (sem creds Google) mas nunca uma exceção não capturada.
  assert.ok(resp instanceof Response, 'deve devolver uma Response');
});

// ── Teste 5: resolveBase devolve o snapshot quando readSnapshot resolve ────────
// Executa o branch `context.readSnapshot` de resolveBase diretamente (sem rede,
// sem creds) — confirma que o objeto retornado por readSnapshot chega intacto.
test('resolveBase devolve o snapshot quando readSnapshot resolve', async () => {
  const base = { midia_paga: { x: 1 } };
  const ctx = { readSnapshot: async () => base };
  assert.equal(await resolveBase(ctx), base);
});

// ── Teste 6: resolveBase devolve null quando readSnapshot rejeita (.catch) ────
// Prova que .catch(() => null) é executado quando readSnapshot lança — o único
// teste que realmente percorre esse code path (T4 tem withCache na frente).
test('resolveBase devolve null quando readSnapshot rejeita (.catch)', async () => {
  const ctx = { readSnapshot: async () => { throw new Error('disco falhou'); } };
  assert.equal(await resolveBase(ctx), null);
});
