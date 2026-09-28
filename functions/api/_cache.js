/* Resposta JSON + cache em memória com TTL (portável Node/Workers).
   Substitui o antigo cache de borda (caches.default) por um Map de módulo. */
const _mem = new Map(); // key: origin+pathname -> { body, expires }

export async function withCache(context, maxAgeSeconds, compute) {
  const { request } = context;
  const url = new URL(request.url);
  const bypass = url.searchParams.has("fresh"); // botão "Atualizar" pede dados novos
  const key = url.origin + url.pathname;         // sem query: um "fresh" aquece o cache normal
  const cors = { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*" };

  if (!bypass) {
    const hit = _mem.get(key);
    if (hit && hit.expires > Date.now()) {
      return new Response(hit.body, { headers: { ...cors, "Cache-Control": `public, max-age=${maxAgeSeconds}` } });
    }
  }
  try {
    const data = await compute();
    const body = JSON.stringify(data);
    _mem.set(key, { body, expires: Date.now() + maxAgeSeconds * 1000 });
    return new Response(body, { headers: { ...cors, "Cache-Control": `public, max-age=${maxAgeSeconds}` } });
  } catch (e) {
    const status = e.status === 401 || e.status === 403 ? 502 : 503;
    return new Response(JSON.stringify({ erro: String(e.message || e) }), {
      status, headers: { ...cors, "Cache-Control": "no-store" },
    });
  }
}
