/* Dashboard NPS enriquecido. */

(async function () {
    await IterumFilters.init(load);
    await load();
    await loadUploads();
})();

async function load() {
    const data = await IterumAPI.get('/iterum/api/analytics/dashboard', IterumFilters.queryParams());
    window.IterumNpsTarget = data.nps_target || 77;
    renderKpis(data.kpis);
    renderAction(data.kpis);
    renderComposition(data.kpis);
    renderGender(data.gender, data.unknown_names);
    renderEffort(data.effort);
    renderResolution(data.resolution);
}

function renderKpis(k) {
    document.getElementById('kpiTotal').textContent = k.total;
    document.getElementById('kpiPromotores').textContent = k.promotores;
    document.getElementById('kpiPromotoresPct').textContent = k.promotor_pct + '%';
    document.getElementById('kpiDetractores').textContent = k.detractores;
    document.getElementById('kpiDetractoresPct').textContent = k.detractor_pct + '%';
    document.getElementById('kpiAvg').textContent = k.avg_score ?? '—';
    document.getElementById('kpiResolucion').textContent = k.resolucion_pct !== null ? k.resolucion_pct + '%' : '—';
    document.getElementById('kpiResolucionSub').textContent = `${k.resolucion_count}/${k.resolucion_total} resueltos`;
    document.getElementById('kpiMuyDificil').textContent = k.muy_dificil;
    document.getElementById('kpiConComentario').textContent = k.con_comentario;
    document.getElementById('kpiConComentarioPct').textContent = k.con_comentario_pct + '% de encuestas';
    document.getElementById('kpiTopMotivo').textContent = k.top_motivo || '—';
    document.getElementById('kpiTopMotivoSub').textContent = k.top_motivo_count ? `${k.top_motivo_count} casos · Ver análisis →` : '';
    document.getElementById('kpiTopResp').textContent = k.top_responsable || '—';
    document.getElementById('kpiTopRespSub').textContent = k.top_responsable_count ? `${k.top_responsable_count} detracciones` : '';
    document.getElementById('kpiConCausa').textContent = k.con_causa_raiz;
}

/* Logica textualmente replicada del Iterum original (function estadoInfo).
   Objetivo del canal viene del backend (window.IterumNpsTarget). */
function estadoInfo(nps) {
    const target = window.IterumNpsTarget || 77;
    const dif = Math.max(0, target - nps);
    if (nps >= target) {
        return {
            label: 'META ALCANZADA', color: 'ok',
            title: `NPS alineado al objetivo del canal (${target}%)`,
            desc: 'Resultado igual o superior a la meta. Mantener buenas prácticas, proteger promotores y sostener la consistencia del servicio.',
        };
    }
    if (nps >= 70) {
        return {
            label: 'CERCA DE LA META', color: 'warn',
            title: `NPS cercano al objetivo del canal (${target}%)`,
            desc: `Faltan ${dif.toFixed(1)} puntos para llegar a la meta. Enfocar el seguimiento en detractores recuperables, resolución y motivos recurrentes.`,
        };
    }
    if (nps >= 60) {
        return {
            label: 'EN SEGUIMIENTO', color: 'warn',
            title: `NPS por debajo del objetivo del canal (${target}%)`,
            desc: `La diferencia es de ${dif.toFixed(1)} puntos. Se requiere revisar causa raíz, experiencia de atención, resolución y repetición del problema por asesor/proceso.`,
        };
    }
    return {
        label: 'ACCIÓN PRIORITARIA', color: 'err',
        title: `NPS lejos del objetivo del canal (${target}%)`,
        desc: `La diferencia es de ${dif.toFixed(1)} puntos. Priorizar detractores, casos sin causa raíz y problemas de servicio que generan insatisfacción.`,
    };
}

function renderAction(k) {
    const el = document.getElementById('dashAction');
    if (k.total === 0 || k.nps === null) { el.style.display = 'none'; return; }
    el.style.display = 'flex';

    // Color theme segun estado
    el.classList.remove('iterum-action-ok', 'iterum-action-warn', 'iterum-action-err');
    const s = estadoInfo(k.nps);
    el.classList.add('iterum-action-' + s.color);

    document.getElementById('dashActionNps').textContent = k.nps;
    document.getElementById('dashActionLabel').textContent = s.label;
    document.getElementById('dashActionTitle').textContent = s.title;

    let text = s.desc + ` · ${k.total} encuestas · ${k.promotores} promotores · ${k.detractores} detractores`;
    if (k.resolucion_pct !== null) text += ` · Resolución: ${k.resolucion_pct}%`;
    if (k.avg_score !== null) text += ` · Nota promedio: ${k.avg_score}`;
    document.getElementById('dashActionText').textContent = text;
}

function renderComposition(k) {
    const total = k.total || 1;
    const pD = (100 * k.detractores / total);
    const pP = (100 * k.pasivos / total);
    const pPr = (100 * k.promotores / total);
    document.getElementById('stackD').style.width = pD + '%';
    document.getElementById('stackP').style.width = pP + '%';
    document.getElementById('stackPr').style.width = pPr + '%';
    document.getElementById('stackDLabel').textContent = pD.toFixed(0) + '%';
    document.getElementById('stackPLabel').textContent = pP.toFixed(0) + '%';
    document.getElementById('stackPrLabel').textContent = pPr.toFixed(0) + '%';
    document.getElementById('stackDCount').textContent = k.detractores;
    document.getElementById('stackPCount').textContent = k.pasivos;
    document.getElementById('stackPrCount').textContent = k.promotores;
}

function renderGender(rows, unknown) {
    const tbody = document.querySelector('#genderTable tbody');
    if (!rows.length) { tbody.innerHTML = '<tr><td colspan="6" class="iterum-empty">Sin datos</td></tr>'; return; }
    const icons = { 'Femenino': '👩', 'Masculino': '👨', 'No Detectado': '❓' };
    tbody.innerHTML = rows.map(r => `
        <tr>
            <td>${icons[r.gender] || '·'} ${IterumUtils.escapeHtml(r.gender)}</td>
            <td>${r.total} encuestas (${r.participation_pct}%)</td>
            <td style="color:#16a34a">${r.promotor} (${r.promotor_pct}%)</td>
            <td style="color:#d97706">${r.pasivo} (${r.pasivo_pct}%)</td>
            <td style="color:#dc2626">${r.detractor} (${r.detractor_pct}%)</td>
            <td><strong>${r.nps}%</strong></td>
        </tr>`).join('');
    const ubox = document.getElementById('unknownBox');
    if (unknown && unknown.length) {
        ubox.style.display = 'block';
        document.getElementById('unknownPills').innerHTML =
            unknown.map(n => `<span class="iterum-pill">${IterumUtils.escapeHtml(n)}</span>`).join('');
    } else {
        ubox.style.display = 'none';
    }
}

function renderEffort(effort) {
    const total = effort.reduce((s, e) => s + e.count, 0) || 1;
    const colors = ['#16a34a', '#86efac', '#fbbf24', '#fb923c', '#dc2626'];
    document.getElementById('effortBar').innerHTML = effort.map((e, i) => {
        const pct = (100 * e.count / total);
        return `<div class="iterum-effort-seg" style="flex:${pct};background:${colors[i]}" title="${e.effort}: ${e.count}">
                    <strong>${e.count}</strong>
                    <small>${e.effort}</small>
                </div>`;
    }).join('');
}

function renderResolution(r) {
    document.getElementById('resolBar').style.width = r.resueltos_pct + '%';
    document.getElementById('resolOk').textContent = r.resueltos;
    document.getElementById('resolOkPct').textContent = r.resueltos_pct + '%';
    document.getElementById('resolNo').textContent = r.sin_resolver;
}

async function loadUploads() {
    const tbody = document.querySelector('#uploadsTable tbody');
    if (!tbody) return;
    const data = await IterumAPI.get('/iterum/api/uploads');
    if (!data.uploads.length) { tbody.innerHTML = '<tr><td colspan="6" class="iterum-empty">Sin cargas</td></tr>'; return; }
    tbody.innerHTML = data.uploads.slice(0, 5).map(u => `
        <tr>
            <td>${IterumUtils.escapeHtml(u.filename || '')}</td>
            <td>${IterumUtils.statusBadge(u.status)}</td>
            <td><strong style="color:#16a34a">${u.rows_new}</strong></td>
            <td>${u.rows_duplicate}</td>
            <td>${IterumUtils.escapeHtml(u.uploaded_by || '')}</td>
            <td class="iterum-meta">${IterumUtils.fmtDate(u.created_at)}</td>
        </tr>`).join('');
}
