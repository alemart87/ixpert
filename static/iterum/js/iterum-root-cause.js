/* Causa Raiz: lista acciones abiertas + detractores sin analizar + modal 5 whys. */

let rcSurveyId = null;

(async function () {
    document.getElementById('rcCancel').addEventListener('click', closeModal);
    document.getElementById('rcSave').addEventListener('click', save);
    document.getElementById('rcModal').addEventListener('click', e => {
        if (e.target.id === 'rcModal') closeModal();
    });
    await loadOpen();
    await loadPending();
})();

async function loadOpen() {
    const data = await IterumAPI.get('/iterum/api/root-causes');
    const tbody = document.querySelector('#rcTable tbody');
    if (!data.root_causes.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="iterum-meta" style="text-align:center">Sin acciones abiertas</td></tr>';
        return;
    }
    tbody.innerHTML = data.root_causes.map(rc => `
        <tr data-survey="${rc.survey_id}">
            <td><a href="#" data-action="edit">#${rc.survey_id}</a></td>
            <td>${IterumUtils.escapeHtml(rc.root_cause || '—')}</td>
            <td>${IterumUtils.escapeHtml(rc.action_owner_name || '—')}</td>
            <td>${IterumUtils.fmtDateShort(rc.due_date)}</td>
            <td>${IterumUtils.statusBadge(rc.status)}</td>
            <td><button class="iterum-btn iterum-btn-sm iterum-btn-ghost" data-action="edit">Editar</button></td>
        </tr>`).join('');
    tbody.querySelectorAll('[data-action="edit"]').forEach(b => {
        b.addEventListener('click', e => {
            e.preventDefault();
            openModal(parseInt(b.closest('tr').dataset.survey));
        });
    });
}

async function loadPending() {
    const data = await IterumAPI.get('/iterum/api/surveys', { category: 'detractor', per_page: 20 });
    const tbody = document.querySelector('#rcPending tbody');
    if (!data.surveys.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="iterum-meta" style="text-align:center">Sin detractores recientes</td></tr>';
        return;
    }
    tbody.innerHTML = data.surveys.map(s => `
        <tr data-id="${s.id}">
            <td class="iterum-meta">${IterumUtils.fmtDateShort(s.response_date)}</td>
            <td>${IterumUtils.escapeHtml(s.agent_name || s.agent_doc || '—')}</td>
            <td><strong>${s.nps_score}</strong></td>
            <td>${IterumUtils.escapeHtml(IterumUtils.truncate(s.comment || '', 150))}</td>
            <td><button class="iterum-btn iterum-btn-sm iterum-btn-primary" data-action="analyze">Analizar</button></td>
        </tr>`).join('');
    tbody.querySelectorAll('[data-action="analyze"]').forEach(b => {
        b.addEventListener('click', () => openModal(parseInt(b.closest('tr').dataset.id)));
    });
}

async function openModal(surveyId) {
    rcSurveyId = surveyId;
    const s = await IterumAPI.get(`/iterum/api/surveys/${surveyId}`);
    document.getElementById('rcSurveyId').textContent = s.id;
    document.getElementById('rcSurveyInfo').innerHTML = `
        <strong>${IterumUtils.fmtDate(s.response_date)}</strong> · ${IterumUtils.escapeHtml(s.agent_name || s.agent_doc || '')}<br>
        NPS <strong>${s.nps_score}</strong> ${IterumUtils.categoryBadge(s.category)}<br>
        <em>${IterumUtils.escapeHtml(s.comment || 'Sin comentario')}</em>
    `;
    const rc = s.root_cause || {};
    ['why_1', 'why_2', 'why_3', 'why_4', 'why_5'].forEach((k, i) => {
        document.getElementById(`why${i + 1}`).value = rc[k] || '';
    });
    document.getElementById('rcRootCause').value = rc.root_cause || '';
    document.getElementById('rcDueDate').value = rc.due_date || '';
    document.getElementById('rcStatus').value = rc.status || 'open';

    document.getElementById('rcModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('rcModal').style.display = 'none';
    rcSurveyId = null;
}

async function save() {
    if (!rcSurveyId) return;
    const whys = [1, 2, 3, 4, 5].map(i => document.getElementById(`why${i}`).value);
    const payload = {
        whys,
        root_cause: document.getElementById('rcRootCause').value,
        due_date: document.getElementById('rcDueDate').value || null,
        status: document.getElementById('rcStatus').value,
    };
    try {
        await IterumAPI.post(`/iterum/api/root-cause/${rcSurveyId}`, payload);
        closeModal();
        loadOpen();
        loadPending();
    } catch (e) {
        alert('Error al guardar: ' + e.message);
    }
}
