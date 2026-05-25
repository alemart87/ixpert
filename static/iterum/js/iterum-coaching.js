/* Coaching: lista + alta + cambio de estado. */

let coachingId = null;

(function () {
    const newBtn = document.getElementById('newCoaching');
    if (newBtn) newBtn.addEventListener('click', () => openModal());

    document.getElementById('coachCancel').addEventListener('click', closeModal);
    document.getElementById('coachSave').addEventListener('click', save);
    document.getElementById('coachingModal').addEventListener('click', e => {
        if (e.target.id === 'coachingModal') closeModal();
    });

    const statusSel = document.getElementById('filterStatus');
    const agentInp = document.getElementById('filterAgent');
    const apply = document.getElementById('filterApply');
    const clear = document.getElementById('filterClear');
    if (apply) apply.addEventListener('click', load);
    if (clear) clear.addEventListener('click', () => {
        if (statusSel) statusSel.value = '';
        if (agentInp) agentInp.value = '';
        load();
    });

    // Pre-llenar agent_doc de la URL si viene de ranking
    const params = new URLSearchParams(window.location.search);
    if (params.get('agent_doc')) {
        if (agentInp) agentInp.value = params.get('agent_doc');
    }

    load();
})();

async function load() {
    const params = {};
    const s = document.getElementById('filterStatus');
    const a = document.getElementById('filterAgent');
    if (s && s.value) params.status = s.value;
    if (a && a.value) params.agent_doc = a.value.trim();

    const data = await IterumAPI.get('/iterum/api/coaching', params);
    const tbody = document.querySelector('#coachingTable tbody');
    if (!data.coaching.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="iterum-meta" style="text-align:center">Sin sesiones</td></tr>';
        return;
    }
    tbody.innerHTML = data.coaching.map(c => `
        <tr data-id="${c.id}">
            <td>${IterumUtils.escapeHtml(c.agent_name || c.agent_doc)}</td>
            <td>${IterumUtils.escapeHtml(c.coach_name || '')}</td>
            <td>${IterumUtils.escapeHtml(c.topic || '—')}</td>
            <td>${IterumUtils.urgencyBadge(c.urgency)}</td>
            <td>${IterumUtils.statusBadge(c.status)}</td>
            <td class="iterum-meta">${IterumUtils.fmtDate(c.scheduled_at)}</td>
            <td>
                ${c.status === 'pending'
                    ? `<button class="iterum-btn iterum-btn-sm iterum-btn-primary" data-action="done">Completar</button>
                       <button class="iterum-btn iterum-btn-sm iterum-btn-ghost" data-action="skip">Omitir</button>`
                    : '—'}
            </td>
        </tr>`).join('');
    tbody.querySelectorAll('[data-action]').forEach(b => {
        b.addEventListener('click', () => {
            const id = parseInt(b.closest('tr').dataset.id);
            const status = b.dataset.action === 'done' ? 'done' : 'skipped';
            updateStatus(id, status);
        });
    });
}

function openModal() {
    coachingId = null;
    document.getElementById('coachingModalTitle').textContent = 'Nueva sesión de coaching';
    document.getElementById('coachAgentDoc').value = '';
    document.getElementById('coachAgentName').value = '';
    document.getElementById('coachTopic').value = '';
    document.getElementById('coachUrgency').value = 'med';
    document.getElementById('coachScheduledAt').value = '';
    document.getElementById('coachNotes').value = '';
    document.getElementById('coachingModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('coachingModal').style.display = 'none';
}

async function save() {
    const payload = {
        agent_doc: document.getElementById('coachAgentDoc').value.trim(),
        agent_name: document.getElementById('coachAgentName').value.trim(),
        topic: document.getElementById('coachTopic').value.trim(),
        urgency: document.getElementById('coachUrgency').value,
        scheduled_at: document.getElementById('coachScheduledAt').value || null,
        notes: document.getElementById('coachNotes').value.trim(),
    };
    if (!payload.agent_doc) { alert('Documento del asesor requerido'); return; }
    try {
        await IterumAPI.post('/iterum/api/coaching', payload);
        closeModal();
        load();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function updateStatus(id, status) {
    try {
        await IterumAPI.patch(`/iterum/api/coaching/${id}`, { status });
        load();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}
