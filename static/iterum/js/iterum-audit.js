/* Auditoría: lista detractores + revisión con estado correcto/dudoso/incorrecto. */

(async function () {
    await IterumFilters.init(load);
    const sel = document.getElementById('filterReviewStatus');
    if (sel) sel.addEventListener('change', load);
    await load();
})();

async function load() {
    const params = IterumFilters.queryParams();
    const sel = document.getElementById('filterReviewStatus');
    if (sel && sel.value) params.review_status = sel.value;
    const data = await IterumAPI.get('/iterum/api/analytics/audit-review', params);
    renderStats(data.stats);
    renderCases(data.cases);
}

function renderStats(s) {
    document.getElementById('auditStats').innerHTML = `
        <div class="iterum-stat-pill"><strong>${s.total}</strong><small>CASOS</small></div>
        <div class="iterum-stat-pill" style="color:#16a34a"><strong>${s.correctos}</strong><small>CORRECTOS</small></div>
        <div class="iterum-stat-pill" style="color:#d97706"><strong>${s.dudosos}</strong><small>DUDOSOS</small></div>
        <div class="iterum-stat-pill" style="color:#dc2626"><strong>${s.incorrectos}</strong><small>INCORRECTOS</small></div>
        <div class="iterum-stat-pill"><strong>${s.sin_revisar}</strong><small>SIN REVISAR</small></div>
        <div class="iterum-stat-progress">
            Progreso de revisión<br>
            <div class="iterum-progress"><div class="iterum-progress-bar" style="width:${s.progreso_pct}%;background:#16a34a"></div></div>
            <small>${s.progreso_pct}% revisado</small>
        </div>
    `;
}

function renderCases(cases) {
    const el = document.getElementById('auditCases');
    if (!cases.length) { el.innerHTML = '<div class="iterum-card iterum-empty">Sin casos para revisar</div>'; return; }
    el.innerHTML = cases.map(c => {
        const statusClass = 'iterum-audit-' + (c.review_status || 'sin_revisar');
        return `
        <div class="iterum-card iterum-audit-case ${statusClass}" data-id="${c.id}">
            <div class="iterum-audit-head">
                <span class="iterum-audit-score">${c.nps_score ?? '—'}</span>
                <div>
                    <strong>${IterumUtils.escapeHtml(c.agent_name || '—')}</strong>
                    · Cliente: ${IterumUtils.escapeHtml(c.client_name || '—')}
                    · ${IterumUtils.escapeHtml(c.cell || '')}
                    · ${IterumUtils.fmtDateShort(c.response_date)}
                </div>
                <div style="margin-left:auto">
                    ${c.review_status === 'sin_revisar' ? '<span class="iterum-chip">Sin revisar</span>' :
                      c.review_status === 'correcto' ? '<span class="iterum-chip chip-ok">✓ Correcto</span>' :
                      c.review_status === 'dudoso' ? '<span class="iterum-chip chip-warn">⚠ Dudoso</span>' :
                      '<span class="iterum-chip chip-err">✗ Incorrecto</span>'}
                </div>
            </div>
            ${c.motive || c.root_cause_type || c.responsibility ? `
            <div class="iterum-audit-tags">
                ${c.motive ? `<span class="iterum-chip">${IterumUtils.escapeHtml(c.motive)}</span>` : ''}
                ${c.root_cause_type ? `<span class="iterum-chip chip-warn">${IterumUtils.escapeHtml(c.root_cause_type)}</span>` : ''}
                ${c.responsibility ? `<span class="iterum-chip">${IterumUtils.escapeHtml(c.responsibility)}</span>` : ''}
                ${c.origin ? `<span class="iterum-chip">${IterumUtils.escapeHtml(c.origin)}</span>` : ''}
            </div>` : '<div class="iterum-meta">Sin causa raíz</div>'}
            <div class="iterum-audit-actions">
                <button class="iterum-btn iterum-btn-sm" data-status="correcto" style="background:#16a34a;color:#fff">✓ Correcto</button>
                <button class="iterum-btn iterum-btn-sm" data-status="dudoso" style="background:#d97706;color:#fff">⚠ Dudoso</button>
                <button class="iterum-btn iterum-btn-sm" data-status="incorrecto" style="background:#dc2626;color:#fff">✗ Incorrecto</button>
            </div>
        </div>`;
    }).join('');

    el.querySelectorAll('[data-status]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.closest('.iterum-audit-case').dataset.id;
            const status = btn.dataset.status;
            try {
                await IterumAPI.post(`/iterum/api/analytics/audit-review/${id}`, { status });
                load();
            } catch (e) { alert('Error: ' + e.message); }
        });
    });
}
