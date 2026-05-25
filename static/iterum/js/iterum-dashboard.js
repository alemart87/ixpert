/* Dashboard de Iterum: KPIs + breakdown por canal/celula + timeseries + uploads. */

(async function () {
    await IterumFilters.init(load);
    await load();
    await loadUploads();
})();

async function load() {
    const params = IterumFilters.queryParams();
    params.granularity = 'week';
    let data;
    try {
        data = await IterumAPI.get('/iterum/api/kpi/dashboard', params);
    } catch (e) {
        console.error(e);
        return;
    }
    renderKpis(data.kpis);
    renderBars('byChannel', data.channels, 'channel');
    renderBars('byCell', data.cells, 'cell');
    renderTimeseries(data.timeseries);
}

function renderKpis(k) {
    document.getElementById('kpiNps').textContent = (k.nps !== null && k.nps !== undefined) ? k.nps : '—';
    document.getElementById('kpiTotal').textContent = `${k.total} respuestas`;
    document.getElementById('kpiPromotor').textContent = k.counts.promotor;
    document.getElementById('kpiPromotorPct').textContent = `${k.promotor_pct}%`;
    document.getElementById('kpiPasivo').textContent = k.counts.pasivo;
    document.getElementById('kpiPasivoPct').textContent = `${k.pasivo_pct}%`;
    document.getElementById('kpiDetractor').textContent = k.counts.detractor;
    document.getElementById('kpiDetractorPct').textContent = `${k.detractor_pct}%`;
    document.getElementById('kpiAvg').textContent = (k.avg_score !== null && k.avg_score !== undefined) ? k.avg_score : '—';
}

function renderBars(containerId, rows, keyName) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!rows || rows.length === 0) {
        el.innerHTML = '<p class="iterum-meta">Sin datos</p>';
        return;
    }
    el.innerHTML = rows.slice(0, 10).map(r => {
        const total = r.total || 1;
        const pP = (100 * r.promotor / total).toFixed(1);
        const pPa = (100 * r.pasivo / total).toFixed(1);
        const pD = (100 * r.detractor / total).toFixed(1);
        return `<div class="iterum-bar-row">
            <div title="${IterumUtils.escapeHtml(r[keyName] || '—')}">${IterumUtils.escapeHtml(r[keyName] || '—')}</div>
            <div class="iterum-bar-track">
                <div class="iterum-bar-promotor" style="width:${pP}%" title="Promotores ${pP}%"></div>
                <div class="iterum-bar-pasivo" style="width:${pPa}%" title="Pasivos ${pPa}%"></div>
                <div class="iterum-bar-detractor" style="width:${pD}%" title="Detractores ${pD}%"></div>
            </div>
            <div><strong>${r.nps}</strong></div>
            <div class="iterum-meta">${r.total}</div>
        </div>`;
    }).join('');
}

function renderTimeseries(rows) {
    const el = document.getElementById('timeseries');
    if (!el) return;
    if (!rows || rows.length === 0) {
        el.innerHTML = '<p class="iterum-meta" style="text-align:center;padding:20px">Sin datos suficientes</p>';
        return;
    }
    const maxTotal = Math.max(...rows.map(r => r.total || 0), 1);
    el.innerHTML = rows.map(r => {
        const h = Math.max(4, Math.round(180 * (r.total || 0) / maxTotal));
        const label = (r.period || '').slice(0, 10);
        const color = r.nps === null ? '#999' :
                      r.nps >= 30 ? '#2c7c2c' :
                      r.nps >= 0 ? '#c98b00' : '#b71c1c';
        return `<div class="iterum-ts-col" title="${label} · NPS ${r.nps} · ${r.total} resp">
            <div class="iterum-ts-bar" style="height:${h}px;background:${color}"></div>
            <div class="iterum-ts-label">${label}</div>
        </div>`;
    }).join('');
}

async function loadUploads() {
    const tbody = document.querySelector('#uploadsTable tbody');
    if (!tbody) return;
    try {
        const data = await IterumAPI.get('/iterum/api/uploads');
        if (!data.uploads.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="iterum-meta" style="text-align:center">Sin cargas</td></tr>';
            return;
        }
        tbody.innerHTML = data.uploads.slice(0, 10).map(u => `
            <tr>
                <td>${IterumUtils.escapeHtml(u.filename || '')}</td>
                <td>${IterumUtils.statusBadge(u.status)}</td>
                <td>${u.rows_new}</td>
                <td>${u.rows_duplicate}</td>
                <td>${u.rows_invalid}</td>
                <td>${IterumUtils.escapeHtml(u.uploaded_by || '')}</td>
                <td class="iterum-meta">${IterumUtils.fmtDate(u.created_at)}</td>
            </tr>`).join('');
    } catch (e) { console.error(e); }
}
