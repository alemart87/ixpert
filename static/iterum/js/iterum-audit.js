/* Auditoria: lista detractores/pasivos sin auditar + modal de veredicto. */

let currentPage = 1;
let modalSurveyId = null;

(async function () {
    await IterumFilters.init(() => { currentPage = 1; load(); });
    const verdictSel = document.getElementById('filterVerdict');
    if (verdictSel) verdictSel.addEventListener('change', () => { currentPage = 1; load(); });

    document.getElementById('auditCancel').addEventListener('click', closeModal);
    document.getElementById('auditSave').addEventListener('click', save);
    document.getElementById('auditModal').addEventListener('click', e => {
        if (e.target.id === 'auditModal') closeModal();
    });

    await load();
})();

async function load() {
    const params = IterumFilters.queryParams();
    params.page = currentPage;
    params.per_page = 50;
    const data = await IterumAPI.get('/iterum/api/surveys', params);
    const tbody = document.querySelector('#auditTable tbody');
    if (!data.surveys.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="iterum-meta" style="text-align:center">Sin resultados</td></tr>';
        return;
    }
    tbody.innerHTML = data.surveys.map(s => `
        <tr data-id="${s.id}">
            <td class="iterum-meta">${IterumUtils.fmtDateShort(s.response_date)}</td>
            <td>${IterumUtils.escapeHtml(s.channel || '—')}</td>
            <td>${IterumUtils.escapeHtml(s.agent_name || s.agent_doc || '—')}</td>
            <td><strong>${s.nps_score}</strong> ${IterumUtils.categoryBadge(s.category)}</td>
            <td>${IterumUtils.escapeHtml(IterumUtils.truncate(s.comment || '', 150))}</td>
            <td>${s.audit ? IterumUtils.verdictBadge(s.audit.verdict) : '<span class="iterum-meta">sin auditar</span>'}</td>
            <td><button class="iterum-btn iterum-btn-sm iterum-btn-primary" data-action="audit">Auditar</button></td>
        </tr>`).join('');
    tbody.querySelectorAll('button[data-action="audit"]').forEach(b => {
        b.addEventListener('click', () => openModal(parseInt(b.closest('tr').dataset.id)));
    });
}

async function openModal(surveyId) {
    modalSurveyId = surveyId;
    const s = await IterumAPI.get(`/iterum/api/surveys/${surveyId}`);
    document.getElementById('modalSurveyId').textContent = s.id;
    document.getElementById('modalSurveyInfo').innerHTML = `
        <strong>${IterumUtils.fmtDate(s.response_date)}</strong> · ${IterumUtils.escapeHtml(s.channel || '')} · ${IterumUtils.escapeHtml(s.agent_name || s.agent_doc || '')}<br>
        NPS <strong>${s.nps_score}</strong> ${IterumUtils.categoryBadge(s.category)}<br>
        <em>${IterumUtils.escapeHtml(s.comment || 'Sin comentario')}</em>
    `;
    document.getElementById('auditClassification').value = s.audit?.classification || '';
    document.getElementById('auditNotes').value = s.audit?.notes || '';
    document.querySelectorAll('input[name="verdict"]').forEach(r => {
        r.checked = (s.audit?.verdict === r.value);
    });
    document.getElementById('auditModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('auditModal').style.display = 'none';
    modalSurveyId = null;
}

async function save() {
    if (!modalSurveyId) return;
    const verdict = document.querySelector('input[name="verdict"]:checked')?.value;
    if (!verdict) { alert('Seleccioná un veredicto'); return; }

    try {
        await IterumAPI.post(`/iterum/api/audit/${modalSurveyId}`, {
            verdict,
            classification: document.getElementById('auditClassification').value,
            notes: document.getElementById('auditNotes').value,
        });
        closeModal();
        load();
    } catch (e) {
        alert('Error al guardar: ' + e.message);
    }
}
