/* Listado paginado de comentarios con filtros y busqueda textual. */

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
    params.per_page = 50;
    const s = document.getElementById('filterSearch');
    if (s && s.value) params.q = s.value;
    const c = document.getElementById('filterCategory');
    if (c && c.value) params.category = c.value;

    const data = await IterumAPI.get('/iterum/api/surveys', params);
    renderTable(data.surveys);
    renderPagination(data.total, data.page, data.per_page);
}

function renderTable(surveys) {
    const tbody = document.querySelector('#commentsTable tbody');
    if (!surveys.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="iterum-meta" style="text-align:center">Sin resultados</td></tr>';
        return;
    }
    tbody.innerHTML = surveys.map(s => `
        <tr>
            <td class="iterum-meta">${IterumUtils.fmtDateShort(s.response_date)}</td>
            <td>${IterumUtils.escapeHtml(s.channel || '—')}</td>
            <td>${IterumUtils.escapeHtml(s.cell || '—')}</td>
            <td>${IterumUtils.escapeHtml(s.agent_name || s.agent_doc || '—')}</td>
            <td><strong>${s.nps_score}</strong> ${IterumUtils.categoryBadge(s.category)}</td>
            <td>${IterumUtils.escapeHtml(IterumUtils.truncate(s.comment || '', 200))}</td>
            <td>${s.audit ? IterumUtils.verdictBadge(s.audit.verdict) : '—'}</td>
        </tr>`).join('');
}

function renderPagination(total, page, perPage) {
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
