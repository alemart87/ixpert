/* Reporte ejecutivo: preview + snapshot + PDF nativo. */

(function () {
    const preview = document.getElementById('reportPreview');
    const generate = document.getElementById('reportGenerate');
    if (preview) preview.addEventListener('click', doPreview);
    if (generate) generate.addEventListener('click', doGenerate);
    loadReports();
})();

function getFilters() {
    const f = {};
    const from = document.getElementById('reportFrom').value;
    const to = document.getElementById('reportTo').value;
    if (from) f.from_date = from;
    if (to) f.to_date = to;
    return f;
}

async function doPreview() {
    const params = getFilters();
    const data = await IterumAPI.get('/iterum/api/report/preview', params);
    document.getElementById('reportPreviewArea').style.display = 'block';
    const html = renderPreviewHtml(data);
    const frame = document.getElementById('reportPreviewFrame');
    frame.srcdoc = html;
}

function renderPreviewHtml(payload) {
    const k = payload.kpis;
    return `<!DOCTYPE html><html><head><meta charset="utf-8">
        <style>
            body { font-family: sans-serif; padding: 20px; }
            .kpis { display: flex; gap: 12px; margin-bottom: 20px; }
            .kpi { flex:1; border: 1px solid #ddd; padding: 12px; border-radius: 6px; text-align: center; }
            .kpi-value { font-size: 28px; font-weight: bold; color: #ff6600; display: block; }
            table { width:100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }
            th,td { padding: 6px; border-bottom: 1px solid #eee; text-align: left; }
            th { background: #f4f4f4; color: #002776; }
            h2 { color: #002776; border-bottom: 2px solid #ff6600; padding-bottom: 4px; }
        </style></head><body>
        <h1>Vista previa del reporte</h1>
        <div class="kpis">
            <div class="kpi"><span>NPS</span><span class="kpi-value">${k.nps ?? '—'}</span></div>
            <div class="kpi"><span>Total</span><span class="kpi-value">${k.total}</span></div>
            <div class="kpi"><span>Promotores</span><span class="kpi-value">${k.promotor_pct}%</span></div>
            <div class="kpi"><span>Detractores</span><span class="kpi-value">${k.detractor_pct}%</span></div>
        </div>
        <h2>Por canal</h2>
        <table><tr><th>Canal</th><th>Total</th><th>NPS</th></tr>
            ${payload.channels.map(c => `<tr><td>${c.channel}</td><td>${c.total}</td><td>${c.nps}</td></tr>`).join('')}
        </table>
        <h2>Por célula</h2>
        <table><tr><th>Célula</th><th>Total</th><th>NPS</th></tr>
            ${payload.cells.slice(0, 10).map(c => `<tr><td>${c.cell}</td><td>${c.total}</td><td>${c.nps}</td></tr>`).join('')}
        </table>
        <h2>Top asesores</h2>
        <table><tr><th>Asesor</th><th>NPS</th><th>Total</th></tr>
            ${payload.ranking_top.map(r => `<tr><td>${r.agent_name || r.agent_doc}</td><td>${r.nps}</td><td>${r.total}</td></tr>`).join('')}
        </table>
    </body></html>`;
}

async function doGenerate() {
    const label = document.getElementById('reportPeriodLabel').value.trim();
    if (!label) { alert('Ingresá una etiqueta de período'); return; }
    const payload = { period_label: label, ...getFilters() };
    try {
        await IterumAPI.post('/iterum/api/report/snapshot', payload);
        loadReports();
        alert('Snapshot generado correctamente.');
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function loadReports() {
    const data = await IterumAPI.get('/iterum/api/reports');
    const tbody = document.querySelector('#reportsTable tbody');
    if (!data.reports.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="iterum-meta" style="text-align:center">Sin snapshots</td></tr>';
        return;
    }
    tbody.innerHTML = data.reports.map(r => `
        <tr>
            <td>${IterumUtils.escapeHtml(r.period_label)}</td>
            <td>${IterumUtils.escapeHtml(r.generated_by)}</td>
            <td class="iterum-meta">${IterumUtils.fmtDate(r.created_at)}</td>
            <td>
                <a href="/iterum/api/report/${r.id}.html" target="_blank" class="iterum-btn iterum-btn-sm iterum-btn-ghost">Ver HTML</a>
                <a href="/iterum/api/report/${r.id}.pdf" class="iterum-btn iterum-btn-sm iterum-btn-primary">Descargar PDF</a>
            </td>
        </tr>`).join('');
}
