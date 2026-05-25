/* Upload de XLSX server-side con polling de estado del job. */

(function () {
    const dropZone = document.getElementById('dropZone');
    const pickBtn = document.getElementById('pickFile');
    const fileInput = document.getElementById('fileInput');
    const statusBox = document.getElementById('uploadStatus');
    const statusTitle = document.getElementById('uploadStatusTitle');
    const statusMsg = document.getElementById('uploadStatusMessage');
    const statusDetails = document.getElementById('uploadStatusDetails');
    const progressBar = document.getElementById('uploadProgress');

    pickBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) upload(fileInput.files[0]);
    });
    ['dragenter', 'dragover'].forEach(ev => {
        dropZone.addEventListener(ev, e => {
            e.preventDefault(); e.stopPropagation();
            dropZone.classList.add('iterum-dropzone-active');
        });
    });
    ['dragleave', 'drop'].forEach(ev => {
        dropZone.addEventListener(ev, e => {
            e.preventDefault(); e.stopPropagation();
            dropZone.classList.remove('iterum-dropzone-active');
        });
    });
    dropZone.addEventListener('drop', e => {
        const f = e.dataTransfer.files[0];
        if (f) upload(f);
    });

    async function upload(file) {
        statusBox.style.display = 'block';
        statusTitle.textContent = 'Subiendo archivo…';
        statusMsg.textContent = file.name + ' (' + Math.round(file.size / 1024) + ' KB)';
        statusDetails.innerHTML = '';
        progressBar.style.width = '10%';

        const fd = new FormData();
        fd.append('file', file);

        let resp;
        try {
            resp = await IterumAPI.postForm('/iterum/api/upload', fd);
        } catch (e) {
            statusTitle.textContent = '❌ Error';
            statusMsg.textContent = e.message;
            progressBar.style.width = '0';
            return;
        }

        if (resp.duplicate_file) {
            statusTitle.textContent = 'ℹ Archivo ya procesado';
            statusMsg.textContent = resp.message;
            progressBar.style.width = '100%';
            await loadHistory();
            return;
        }

        statusTitle.textContent = 'En cola…';
        progressBar.style.width = '30%';
        poll(resp.upload_id);
    }

    async function poll(uploadId) {
        let tries = 0;
        const maxTries = 120;  // 4 minutos a 2s
        const interval = setInterval(async () => {
            tries++;
            try {
                const s = await IterumAPI.get(`/iterum/api/upload/${uploadId}/status`);
                if (s.status === 'pending') {
                    statusTitle.textContent = 'En cola…';
                    progressBar.style.width = '40%';
                } else if (s.status === 'processing') {
                    statusTitle.textContent = 'Procesando filas…';
                    progressBar.style.width = '70%';
                } else if (s.status === 'done') {
                    clearInterval(interval);
                    statusTitle.textContent = '✅ Procesamiento completado';
                    statusMsg.textContent = '';
                    progressBar.style.width = '100%';
                    statusDetails.innerHTML = `
                        <table class="iterum-table iterum-table-sm" style="margin-top:8px">
                            <tr><th>Total filas</th><td>${s.rows_total}</td></tr>
                            <tr><th>Nuevas</th><td>${s.rows_new}</td></tr>
                            <tr><th>Duplicadas</th><td>${s.rows_duplicate}</td></tr>
                            <tr><th>Inválidas</th><td>${s.rows_invalid}</td></tr>
                            <tr><th>Período</th><td>${s.period_start || '—'} a ${s.period_end || '—'}</td></tr>
                        </table>
                    `;
                    await loadHistory();
                } else if (s.status === 'failed') {
                    clearInterval(interval);
                    statusTitle.textContent = '❌ Error al procesar';
                    statusMsg.textContent = s.error || 'Error desconocido';
                    progressBar.style.width = '0';
                }
            } catch (e) { console.error(e); }
            if (tries >= maxTries) {
                clearInterval(interval);
                statusTitle.textContent = '⏱ Timeout';
                statusMsg.textContent = 'El procesamiento está demorando más de lo esperado. Refrescá la página en unos minutos.';
            }
        }, 2000);
    }

    async function loadHistory() {
        const tbody = document.querySelector('#uploadsHistory tbody');
        if (!tbody) return;
        const data = await IterumAPI.get('/iterum/api/uploads');
        if (!data.uploads.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="iterum-meta" style="text-align:center">Sin cargas</td></tr>';
            return;
        }
        tbody.innerHTML = data.uploads.map(u => `
            <tr>
                <td>${IterumUtils.escapeHtml(u.filename || '')}</td>
                <td>${IterumUtils.statusBadge(u.status)}</td>
                <td>${u.rows_new + u.rows_duplicate + u.rows_invalid}</td>
                <td>${u.rows_new}</td>
                <td>${u.rows_duplicate}</td>
                <td>${u.rows_invalid}</td>
                <td>${IterumUtils.escapeHtml(u.uploaded_by || '')}</td>
                <td class="iterum-meta">${IterumUtils.fmtDate(u.created_at)}</td>
            </tr>`).join('');
    }

    loadHistory();
})();
