(function setupLogout() {
  const btn = document.getElementById('btn-logout');
  if (!btn) return;
  btn.addEventListener('click', () => {
    try { sessionStorage.removeItem('vesti.auth.ok'); } catch (_) {}
    window.location.replace('login.html');
  });
})();

(async function () {
  try {
    const data = await DataLoader.load();
    document.getElementById('meta-info').textContent =
      `Atualizado em ${new Date(data.generated_at).toLocaleString('pt-BR')} · ${data.total_leads.toLocaleString('pt-BR')} leads na base`;

    Filters.init(data);
    KPIs.init(data);
    Charts.init(data);

    function rerender() {
      const filtered = Filters.apply(data.leads);
      KPIs.render(filtered);
      Charts.render(filtered);
    }
    Filters.onChange(rerender);
    rerender();
  } catch (err) {
    document.querySelector('main').innerHTML =
      `<div class="empty">Falha ao carregar os dados: ${err.message}</div>`;
    console.error(err);
  }
})();
