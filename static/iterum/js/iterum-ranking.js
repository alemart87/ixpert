/* Ranking de asesores. */
(async function () {
    await IterumFilters.init(load);
    await load();
})();

async function load() {
    const params = IterumFilters.queryParams();
    params.limit = 100;
    const data = await IterumAPI.get('/iterum/api/kpi/ranking', params);
    const tbody = document.querySelector('#rankingTable tbody');
    if (!data.ranking || !data.ranking.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="iterum-meta" style="text-align:center">Sin datos suficientes</td></tr>';
        return;
    }
    tbody.innerHTML = data.ranking.map((r, i) => `
        <tr>
            <td><strong>${i + 1}</strong></td>
            <td>${IterumUtils.escapeHtml(r.agent_name || '—')}</td>
            <td><code>${IterumUtils.escapeHtml(r.agent_doc)}</code></td>
            <td><strong>${r.nps}</strong></td>
            <td>${r.total}</td>
            <td><span class="iterum-badge iterum-badge-promotor">${r.promotor}</span></td>
            <td><span class="iterum-badge iterum-badge-pasivo">${r.pasivo}</span></td>
            <td><span class="iterum-badge iterum-badge-detractor">${r.detractor}</span></td>
            <td>
                <a href="/iterum/coaching?agent_doc=${encodeURIComponent(r.agent_doc)}" class="iterum-btn iterum-btn-sm iterum-btn-ghost">Coaching</a>
            </td>
        </tr>`).join('');
}
