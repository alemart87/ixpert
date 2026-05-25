/* Upload XLSX server-side con polling. */

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
        statusTitle.textContent = '⏳ Subiendo archivo...';
        statusMsg.textContent = file.name + ' (' + Math.round(file.size / 1024) + ' KB)';
        statusDetails.innerHTML = '';
        progressBar.style.width = '10%';

        const fd = new FormData();
        fd.append('file', file);

        let resp;
        try {
            resp = await IterumAPI.postForm('/iterum/api/upload', fd);
        } catch (e) {
            statusTitle.textContent = '❌ Error al subir';
            statusMsg.textContent = e.message;
            progressBar.style.width = '0';
            return;
        }

        if (resp.duplicate_file) {
            // El upload previo terminó OK (done) o está en curso.
            // Si fallaba, el backend ahora lo borra y procesa de nuevo.
            statusTitle.textContent = 'ℹ Archivo ya procesado anteriormente';
            statusMsg.textContent = resp.message + ' Si necesitás reprocesar, modificá el archivo o renombralo.';
            progressBar.style.width = '100%';
            await loadHistory();
            return;
        }

        statusTitle.textContent = '⏳ En cola...';
        progressBar.style.width = '30%';
        poll(resp.upload_id);
    }

    async function poll(uploadId) {
        let tries = 0;
        const maxTries = 120;
        const interval = setInterval(async () => {
            tries++;
            try {
                const s = await IterumAPI.get(`/iterum/api/upload/${uploadId}/status`);
                if (s.status === 'pending') {
                    statusTitle.textContent = '⏳ En cola...';
                    progressBar.style.width = '40%';
                } else if (s.status === 'processing') {
                    statusTitle.textContent = '⚙ Procesando filas...';
                    progressBar.style.width = '70%';
                } else if (s.status === 'done') {
                    clearInterval(interval);
                    statusTitle.textContent = '✅ Procesamiento completado';
                    statusMsg.textContent = '';
                    progressBar.style.width = '100%';
                    statusDetails.innerHTML = `
                        <table class="iterum-table iterum-table-sm" style="margin-top:8px;max-width:400px">
                            <tr><th style="width:160px">Total filas</th><td><strong>${s.rows_total}</strong></td></tr>
                            <tr><th>Nuevas insertadas</th><td><strong style="color:#16a34a">${s.rows_new}</strong></td></tr>
                            <tr><th>Duplicadas (skip)</th><td>${s.rows_duplicate}</td></tr>
                            <tr><th>Inválidas (skip)</th><td>${s.rows_invalid}</td></tr>
                            <tr><th>Período detectado</th><td>${s.period_start || '—'} → ${s.period_end || '—'}</td></tr>
                        </table>
                    `;
                    await loadHistory();
                } else if (s.status === 'failed') {
                    clearInterval(interval);
                    statusTitle.textContent = '❌ Error al procesar';
                    statusMsg.textContent = '';
                    progressBar.style.width = '0';
                    statusDetails.innerHTML = `
                        <div class="iterum-error-detail">${IterumUtils.escapeHtml(s.error || 'Error desconocido')}</div>
                        <p class="iterum-meta" style="margin-top:8px">
                            Verificá el formato del archivo. Subí el archivo otra vez después de corregirlo.
                        </p>
                    `;
                    await loadHistory();
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
            tbody.innerHTML = '<tr><td colspan="8" class="iterum-empty">Sin cargas previas</td></tr>';
            return;
        }
        tbody.innerHTML = data.uploads.map(u => {
            const totalRows = (u.rows_total || 0) || (u.rows_new + u.rows_duplicate + u.rows_invalid);
            const errBlock = u.status === 'failed' && u.error_message
                ? `<button class="iterum-error-toggle" data-id="err${u.id}">Ver error</button>
                   <div class="iterum-error-detail" id="err${u.id}" style="display:none">${IterumUtils.escapeHtml(u.error_message)}</div>`
                : '';
            return `
                <tr>
                    <td>${IterumUtils.escapeHtml(u.filename || '')}</td>
                    <td>${IterumUtils.statusBadge(u.status)}${errBlock}</td>
                    <td>${totalRows}</td>
                    <td><strong style="color:#16a34a">${u.rows_new}</strong></td>
                    <td>${u.rows_duplicate}</td>
                    <td>${u.rows_invalid}</td>
                    <td>${IterumUtils.escapeHtml(u.uploaded_by || '')}</td>
                    <td class="iterum-meta">${IterumUtils.fmtDate(u.created_at)}</td>
                </tr>`;
        }).join('');
        tbody.querySelectorAll('.iterum-error-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const el = document.getElementById(btn.dataset.id);
                if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
            });
        });
    }

    loadHistory();
})();
