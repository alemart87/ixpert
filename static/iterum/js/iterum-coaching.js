/* Coaching: cards por asesor con detalle de detractores + promotores. */

let urgencyFilter = '';

(async function () {
    await IterumFilters.init(load);
    const sel = document.getElementById('filterUrgency');
    if (sel) sel.addEventListener('change', () => { urgencyFilter = sel.value; load(); });
    await load();
})();

async function load() {
    const data = await IterumAPI.get('/iterum/api/analytics/coaching', IterumFilters.queryParams());
    renderStats(data.stats);
    renderAgents(data.agents);
}

function renderStats(s) {
    document.getElementById('coachStats').innerHTML = `
        <div class="iterum-kpi-card"><span class="iterum-kpi-label">Asesores con detractores</span><span class="iterum-kpi-value">${s.asesores_con_detractores}</span></div>
        <div class="iterum-kpi-card iterum-kpi-detractor"><span class="iterum-kpi-label">⚡ Urgentes</span><span class="iterum-kpi-value">${s.urgentes}</span></div>
        <div class="iterum-kpi-card iterum-kpi-pasivo"><span class="iterum-kpi-label">⚠ En riesgo</span><span class="iterum-kpi-value">${s.en_riesgo}</span></div>
        <div class="iterum-kpi-card"><span class="iterum-kpi-label">Sin causa raíz asignada</span><span class="iterum-kpi-value">${s.sin_causa_raiz}</span></div>
        <div class="iterum-kpi-card iterum-kpi-promotor"><span class="iterum-kpi-label">⭐ Solo promotores</span><span class="iterum-kpi-value">${s.solo_promotores}</span></div>
    `;
}

function renderAgents(agents) {
    let filtered = agents;
    if (urgencyFilter) filtered = agents.filter(a => a.urgency === urgencyFilter);
    const el = document.getElementById('coachAgentsList');
    if (!filtered.length) { el.innerHTML = '<div class="iterum-card iterum-empty">Sin asesores</div>'; return; }
    el.innerHTML = filtered.map(agentCard).join('');
}

function agentCard(a) {
    const urgencyBadge = a.urgency === 'urgente' ? '<span class="iterum-chip chip-err">🔴 URGENTE</span>'
        : a.urgency === 'riesgo' ? '<span class="iterum-chip chip-warn">⚠ EN RIESGO</span>'
        : '<span class="iterum-chip chip-ok">NORMAL</span>';

    const detractorCases = a.detractor_cases.map(c => `
        <div class="iterum-coach-case">
            <div class="iterum-coach-case-head">
                <strong>${c.nps_score ?? '—'}</strong>
                <span>${IterumUtils.escapeHtml(c.motive || '—')}</span>
                <span class="iterum-meta">· ${IterumUtils.fmtDateShort(c.response_date)}</span>
                ${c.responsibility ? `<span class="iterum-chip">${IterumUtils.escapeHtml(c.responsibility)}</span>` : ''}
                ${c.resolution ? `<span class="iterum-chip ${c.resolution === 'Si' ? 'chip-ok' : 'chip-err'}">Resolvió: ${c.resolution}</span>` : ''}
            </div>
            ${c.problem_description ? `<p>${IterumUtils.escapeHtml(c.problem_description)}</p>` : ''}
            ${c.comment ? `<p class="iterum-coach-comment">"${IterumUtils.escapeHtml(c.comment)}"</p>` : ''}
        </div>`).join('');

    const promoterBlock = a.promotores_count > 0 ? `
        <div class="iterum-coach-fortalezas">
            <h4>⭐ Fortalezas detectadas — ${a.promotores_count} promotores</h4>
            <div class="iterum-coach-stats-mini">
                <div><strong>${a.promotores_count}</strong><small>Promotores</small></div>
                <div><strong>${a.avg_promoter_score ?? '—'}</strong><small>Nota media</small></div>
            </div>
            <div class="iterum-coach-voices">
                <h5>Voz del cliente</h5>
                ${a.promoter_voices.map(v => `<div class="iterum-coach-voice">⭐ "${IterumUtils.escapeHtml(v)}"</div>`).join('')}
            </div>
        </div>` : '';

    return `
    <div class="iterum-card iterum-coach-card iterum-coach-${a.urgency}">
        <div class="iterum-coach-head">
            <strong class="iterum-coach-name">${IterumUtils.escapeHtml(a.agent_name)}</strong>
            ${urgencyBadge}
            <span class="iterum-chip">${a.detractores_count} detractores</span>
            ${a.promotores_count > 0 ? `<span class="iterum-chip chip-ok">⭐ ${a.promotores_count} promotores</span>` : ''}
        </div>
        <div class="iterum-coach-summary">
            🔴 <strong>${a.detractores_count}</strong> detractores ·
            ❌ <strong>${a.sin_resolver}</strong> sin resolver ·
            ⚠ <strong>${a.sin_causa_raiz}</strong> sin causa raíz ·
            ${a.top_motive ? `<strong>${IterumUtils.escapeHtml(a.top_motive)}</strong> (${a.top_motive_count})` : ''}
        </div>
        <h4>Casos detractores</h4>
        ${detractorCases || '<div class="iterum-meta">Sin casos</div>'}
        ${promoterBlock}
    </div>`;
}
