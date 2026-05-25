/* Ranking estilo cards (replica del Iterum original) — sin minimo, sin paginar.
   Si hay > 100 agentes, paginación client-side de 100 por vista. */

const AVATAR_COLORS = ['#2563eb', '#02ac66', '#ec7000', '#7c3aed', '#db2777',
                       '#0891b2', '#65a30d', '#dc2626', '#9d174d', '#1e40af'];

let currentPage = 1;
const PER_PAGE = 100;

(async function () {
    await IterumFilters.init(() => { currentPage = 1; load(); });
    const sortSel = document.getElementById('filterSort');
    if (sortSel) sortSel.addEventListener('change', () => { currentPage = 1; load(); });
    await load();
})();

async function load() {
    const params = IterumFilters.queryParams();
    const sortSel = document.getElementById('filterSort');
    params.sort = sortSel ? sortSel.value : 'nps';
    const data = await IterumAPI.get('/iterum/api/kpi/ranking', params);
    render(data.ranking);
}

function render(ranking) {
    const meta = document.getElementById('rankingMeta');
    const list = document.getElementById('rankingList');
    if (!ranking.length) {
        meta.textContent = 'Sin asesores en el período';
        list.innerHTML = '<div class="iterum-empty">Sin datos</div>';
        return;
    }

    const totalPages = Math.ceil(ranking.length / PER_PAGE);
    const start = (currentPage - 1) * PER_PAGE;
    const end = Math.min(start + PER_PAGE, ranking.length);
    const visible = ranking.slice(start, end);

    meta.textContent = `${ranking.length} asesores · mostrando ${start + 1}–${end}`;

    const maxAbsNps = Math.max(...ranking.map(a => Math.abs(a.nps)), 1);

    list.innerHTML = visible.map((a, i) => {
        const globalPos = start + i + 1;
        const initials = (a.agent_name || a.agent_doc || '?').slice(0, 2).toUpperCase();
        const color = AVATAR_COLORS[(start + i) % AVATAR_COLORS.length];
        // Bar y texto usan colores distintos (mismo estado, props distintas)
        const stateKey = a.nps >= 50 ? 'ok' : a.nps >= 0 ? 'warn' : 'err';
        const barCls = 'rank-bar-' + stateKey;
        const textCls = 'rank-text-' + stateKey;
        const barPct = Math.max(3, (Math.abs(a.nps) / maxAbsNps) * 100);
        const medal = globalPos === 1 ? '🥇' : globalPos === 2 ? '🥈' : globalPos === 3 ? '🥉' : globalPos;
        const channelIcon = a.channel === 'whatsapp' ? '💬 WA' : a.channel === 'call' ? '📞 Llamadas' : (a.channel || '—');
        const resPart = a.resolution_pct > 0 ? ` · Res: ${a.resolution_pct}%` : '';

        return `
        <div class="iterum-rank-item">
            <div class="iterum-rank-pos ${globalPos <= 3 ? 'gold' : ''}">${medal}</div>
            <div class="iterum-rank-avatar" style="background:${color}">${initials}</div>
            <div class="iterum-rank-info">
                <div class="iterum-rank-name">${IterumUtils.escapeHtml(a.agent_name || a.agent_doc)}</div>
                <div class="iterum-rank-sub">
                    ${IterumUtils.escapeHtml(a.cell || '—')} · ${channelIcon}
                    · ${a.total} enc. · ${a.promotor}P ${a.detractor}D${resPart}
                </div>
            </div>
            <div class="iterum-rank-bar-bg">
                <div class="iterum-rank-bar-fill ${barCls}" style="width:${barPct.toFixed(0)}%"></div>
            </div>
            <div class="iterum-rank-nps ${textCls}">${a.nps.toFixed(1)}%</div>
        </div>`;
    }).join('');

    // Paginacion si hay > 100 agentes
    if (totalPages > 1) {
        let pag = '<div class="iterum-pagination" style="margin-top:16px">';
        for (let p = 1; p <= totalPages; p++) {
            pag += `<button data-p="${p}" class="${p === currentPage ? 'active' : ''}">${p}</button>`;
        }
        pag += '</div>';
        list.insertAdjacentHTML('beforeend', pag);
        list.querySelectorAll('[data-p]').forEach(b => b.addEventListener('click', () => {
            currentPage = parseInt(b.dataset.p);
            load();
        }));
    }
}
