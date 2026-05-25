/* Patrones: keyword detection + structured origen + top alertas. */

(async function () {
    await IterumFilters.init(load);
    await load();
})();

async function load() {
    const [dash, pats] = await Promise.all([
        IterumAPI.get('/iterum/api/analytics/dashboard', IterumFilters.queryParams()),
        IterumAPI.get('/iterum/api/analytics/patterns', IterumFilters.queryParams()),
    ]);

    // Banners
    const noResuelto = dash.resolution.total > 0
        ? Math.round(100 * dash.resolution.sin_resolver / dash.resolution.total) : 0;
    document.getElementById('indexNoResuelto').textContent = noResuelto + '%';
    const total = dash.effort.reduce((s, e) => s + e.count, 0) || 1;
    const altoEsf = (dash.effort.find(e => e.effort === 'Dificil')?.count || 0) +
                    (dash.effort.find(e => e.effort === 'Muy dificil')?.count || 0);
    document.getElementById('indexEsfuerzo').textContent = Math.round(100 * altoEsf / total) + '%';

    renderPatternsList(pats.keywords);
    renderOriginList(pats.origin);
    renderAlerts(pats.top_alerts);
    renderKeywords(pats.keywords);
}

function renderPatternsList(rows) {
    const colors = ['#dc2626', '#f97316', '#fbbf24', '#16a34a', '#6b7280'];
    const labels = {
        'Tiempo de respuesta / demora': 'Demora / Tiempos de Espera',
        'No resolución del problema': 'Falta de Resolución / Bucle',
        'Cierre de chat / desconexión': 'Caídas de Sistema / Error Técnico',
        'Falta de asesor humano': 'Trato / Calidad de Atención',
    };
    const el = document.getElementById('patternsList');
    if (!rows.length) { el.innerHTML = '<div class="iterum-empty">Sin patrones detectados</div>'; return; }
    const totalDetractores = rows[0].total;
    el.innerHTML = rows.map((r, i) => `
        <div class="iterum-pattern-row" style="border-left-color:${colors[i % colors.length]}">
            <div>
                <strong>${IterumUtils.escapeHtml(labels[r.label] || r.label)}</strong>
                <span class="iterum-pattern-count" style="color:${colors[i % colors.length]}">${r.count} casos (${r.pct}%)</span>
            </div>
        </div>`).join('');
}

function renderOriginList(rows) {
    const el = document.getElementById('originList');
    if (!rows.length) { el.innerHTML = '<div class="iterum-empty">Sin datos estructurados</div>'; return; }
    const max = rows[0]?.count || 1;
    el.innerHTML = rows.map(r => `
        <div class="iterum-bar-row" style="grid-template-columns:180px 1fr 50px 40px">
            <div title="${IterumUtils.escapeHtml(r.label)}">${IterumUtils.escapeHtml(r.label)}</div>
            <div class="iterum-bar-track"><div style="width:${100*r.count/max}%;height:100%;background:linear-gradient(90deg,#dc2626,#f97316)"></div></div>
            <div><strong>${r.count}</strong></div>
            <div class="iterum-meta">${r.pct}%</div>
        </div>`).join('');
}

function renderAlerts(rows) {
    const tbody = document.querySelector('#topAlertsTable tbody');
    if (!rows.length) { tbody.innerHTML = '<tr><td colspan="2" class="iterum-empty">Sin alertas</td></tr>'; return; }
    tbody.innerHTML = rows.map(r => `
        <tr><td>👤 ${IterumUtils.escapeHtml(r.agent_name)}</td><td><strong style="color:#dc2626">${r.alerts}</strong></td></tr>
    `).join('');
}

function renderKeywords(rows) {
    const el = document.getElementById('keywordsList');
    if (!rows.length) { el.innerHTML = '<div class="iterum-empty">Sin keywords detectadas</div>'; return; }
    el.innerHTML = rows.map(r => `
        <div class="iterum-keyword-row">
            <div><strong>${IterumUtils.escapeHtml(r.label)}</strong><br>
                <small class="iterum-meta">Detectado en ${r.count} de ${r.total} comentarios de detractores.</small>
            </div>
            <div class="iterum-keyword-pct">${r.pct}%</div>
        </div>`).join('');
}
