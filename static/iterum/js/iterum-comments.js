/* Comentarios enriquecidos como cards. */

let currentPage = 1;

(async function () {
    await IterumFilters.init(() => { currentPage = 1; load(); });
    const searchInp = document.getElementById('filterSearch');
    const categorySel = document.getElementById('filterCategory');
    if (searchInp) searchInp.addEventListener('keypress', e => {
        if (e.key === 'Enter') { currentPage = 1; load(); }
    });
    if (categorySel) categorySel.addEventListener('change', () => { currentPage = 1; load(); });
    await load();
})();

async function load() {
    const params = IterumFilters.queryParams();
    params.page = currentPage;
    params.per_page = 20;
    const s = document.getElementById('filterSearch');
    if (s && s.value) params.q = s.value;
    const c = document.getElementById('filterCategory');
    if (c && c.value) params.category = c.value;
    const data = await IterumAPI.get('/iterum/api/surveys', params);
    render(data.surveys);
    pagination(data.total, data.page, data.per_page);
}

function render(surveys) {
    const el = document.getElementById('commentsList');
    if (!surveys.length) { el.innerHTML = '<div class="iterum-empty">Sin resultados</div>'; return; }
    el.innerHTML = surveys.filter(s => s.comment).map(s => renderCard(s)).join('');
}

function renderCard(s) {
    const catBadge = `<span class="iterum-badge iterum-badge-${s.category}">${(s.category || '').toUpperCase()}</span>`;
    const channelIcon = s.channel === 'whatsapp' ? '💬 WHATSAPP' : (s.channel === 'call' ? '📞 LLAMADAS' : s.channel || '');
    const date = IterumUtils.fmtDateShort(s.response_date);
    const structured = s.motive || s.origin || s.problem_description || s.why_1;
    const effortBadge = s.effort ? `<span class="iterum-chip">⚡ ${IterumUtils.escapeHtml(s.effort)}</span>` : '';
    const resolBadge = s.resolution ? `<span class="iterum-chip ${s.resolution === 'Si' ? 'chip-ok' : 'chip-warn'}">${s.resolution === 'Si' ? '✓ Resuelto' : '✗ Sin resolver'}</span>` : '';
    const scoreBadge = `<span class="iterum-chip">⭐ Nota: ${s.nps_score}</span>`;
    const genderBadge = s.gender ? `<span class="iterum-chip">👤 Género Cliente: ${IterumUtils.escapeHtml(s.gender)}</span>` : '';

    return `
    <div class="iterum-card iterum-comment-card iterum-comment-${s.category}">
        <div class="iterum-comment-header">
            ${catBadge}
            <strong>${IterumUtils.escapeHtml(s.agent_name || '—')}</strong>
            <span class="iterum-meta">${IterumUtils.escapeHtml(s.cell || '')}</span>
            <span class="iterum-meta">${channelIcon}</span>
            <span class="iterum-meta iterum-comment-date">${date}</span>
        </div>
        <p class="iterum-comment-text">"${IterumUtils.escapeHtml(s.comment)}"</p>
        ${structured && s.category === 'detractor' ? `
        <div class="iterum-comment-structured">
            ${s.motive ? `<div><strong>Motivo:</strong> ${IterumUtils.escapeHtml(s.motive)} ${s.gestion_type ? `· <strong>Gestión:</strong> ${IterumUtils.escapeHtml(s.gestion_type)}` : ''}</div>` : ''}
            ${s.origin ? `<div><strong>Origen:</strong> ${IterumUtils.escapeHtml(s.origin)}</div>` : ''}
            ${s.problem_description ? `<div><strong>Diagnóstico:</strong> ${IterumUtils.escapeHtml(s.problem_description)}</div>` : ''}
            ${s.why_1 ? `<div class="iterum-porques">
                <span class="iterum-porque-pill">1. ${IterumUtils.escapeHtml(s.why_1)}</span>
                ${s.why_2 ? `<span class="iterum-porque-pill">2. ${IterumUtils.escapeHtml(s.why_2)}</span>` : ''}
                ${s.why_3 ? `<span class="iterum-porque-pill">3. ${IterumUtils.escapeHtml(s.why_3)}</span>` : ''}
                ${s.root_cause_type ? `<span class="iterum-porque-pill chip-ok"> ${IterumUtils.escapeHtml(s.root_cause_type)}</span>` : ''}
                ${s.responsibility ? `<span class="iterum-porque-pill"> ${IterumUtils.escapeHtml(s.responsibility)}</span>` : ''}
            </div>` : ''}
        </div>` : ''}
        <div class="iterum-comment-chips">
            ${effortBadge}${resolBadge}${scoreBadge}${genderBadge}
        </div>
    </div>`;
}

function pagination(total, page, perPage) {
    const totalPages = Math.ceil(total / perPage);
    const el = document.getElementById('commentsPagination');
    if (totalPages <= 1) { el.innerHTML = ''; return; }
    let html = '';
    const start = Math.max(1, page - 3);
    const end = Math.min(totalPages, page + 3);
    if (start > 1) html += `<button data-page="1">1</button><span>…</span>`;
    for (let i = start; i <= end; i++) {
        html += `<button data-page="${i}" class="${i === page ? 'active' : ''}">${i}</button>`;
    }
    if (end < totalPages) html += `<span>…</span><button data-page="${totalPages}">${totalPages}</button>`;
    el.innerHTML = html;
    el.querySelectorAll('button').forEach(b => {
        b.addEventListener('click', () => { currentPage = parseInt(b.dataset.page); load(); });
    });
}
