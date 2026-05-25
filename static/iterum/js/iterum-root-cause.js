/* Causa Raíz: 4 charts + cadena de porqués. */

(async function () {
    await IterumFilters.init(load);
    await load();
})();

async function load() {
    const data = await IterumAPI.get('/iterum/api/analytics/root-cause', IterumFilters.queryParams());
    bar('chartTipo', data.charts.tipo_causa, ['#dc2626', '#f97316']);
    respGrid('chartResp', data.charts.responsabilidad);
    bar('chartMotivo', data.charts.motivo, ['#dc2626', '#fbbf24']);
    bar('chartOrigen', data.charts.origen, ['#dc2626', '#3b82f6']);
    chain('chainList', data.chain);
}

function bar(id, rows, colors) {
    const el = document.getElementById(id);
    if (!rows.length) { el.innerHTML = '<div class="iterum-empty">Sin datos</div>'; return; }
    const max = rows[0]?.count || 1;
    el.innerHTML = rows.map(r => `
        <div class="iterum-bar-row" style="grid-template-columns:160px 1fr 40px 40px">
            <div title="${IterumUtils.escapeHtml(r.label)}">${IterumUtils.escapeHtml(r.label)}</div>
            <div class="iterum-bar-track"><div style="width:${100*r.count/max}%;height:100%;background:linear-gradient(90deg,${colors[0]},${colors[1]})"></div></div>
            <div><strong>${r.count}</strong></div>
            <div class="iterum-meta">${r.pct}%</div>
        </div>`).join('');
}

function respGrid(id, rows) {
    const icons = { 'Asesor': '🎧', 'Externo': '🌐', 'Proceso': '⚙', 'Servicio': '🔧' };
    const el = document.getElementById(id);
    if (!rows.length) { el.innerHTML = '<div class="iterum-empty">Sin datos</div>'; return; }
    const total = rows.reduce((s, r) => s + r.count, 0);
    const colors = { 'Asesor': '#dc2626', 'Externo': '#3b82f6', 'Proceso': '#6b7280', 'Servicio': '#94a3b8' };
    const cells = ['Asesor', 'Externo', 'Proceso', 'Servicio'].map(label => {
        const r = rows.find(x => x.label === label) || { count: 0 };
        const pct = total ? Math.round(100 * r.count / total) : 0;
        return `<div class="iterum-resp-cell">
            <div class="iterum-resp-icon">${icons[label]}</div>
            <div class="iterum-resp-pct" style="color:${colors[label]}">${pct}%</div>
            <div class="iterum-resp-label">${label}</div>
            <div class="iterum-meta">${r.count} casos</div>
        </div>`;
    }).join('');
    el.innerHTML = cells;
}

function chain(id, rows) {
    const el = document.getElementById(id);
    if (!rows.length) { el.innerHTML = '<div class="iterum-empty">Sin análisis de causa raíz cargados</div>'; return; }
    el.innerHTML = rows.map(r => `
        <div class="iterum-chain-card iterum-chain-${(r.root_cause_type || '').toLowerCase().includes('empatia') ? 'empatia' : 'other'}">
            <div class="iterum-chain-head">
                <span class="iterum-chip ${r.root_cause_type ? 'chip-warn' : ''}">${IterumUtils.escapeHtml(r.root_cause_type || '—')}</span>
                <span class="iterum-chip">${IterumUtils.escapeHtml(r.responsibility || '—')}</span>
                <span class="iterum-meta" style="margin-left:auto">${IterumUtils.escapeHtml(r.agent_name || '')} · ${IterumUtils.escapeHtml(r.cell || '')}</span>
            </div>
            ${r.problem_description ? `<div><strong>Problema:</strong> ${IterumUtils.escapeHtml(r.problem_description)}</div>` : ''}
            <div class="iterum-porques">
                ${r.why_1 ? `<span class="iterum-porque-pill">1. ${IterumUtils.escapeHtml(r.why_1)}</span>` : ''}
                ${r.why_2 ? `<span class="iterum-porque-pill">2. ${IterumUtils.escapeHtml(r.why_2)}</span>` : ''}
                ${r.why_3 ? `<span class="iterum-porque-pill">3. ${IterumUtils.escapeHtml(r.why_3)}</span>` : ''}
            </div>
        </div>`).join('');
}
