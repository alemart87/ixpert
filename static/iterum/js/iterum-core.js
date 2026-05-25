/* Iterum core - estado compartido, fetch wrapper, helpers de filtros.
   Cada pagina-JS depende SOLO de este modulo. */

window.IterumState = {
    filters: {
        channel: '',
        cell: '',
        from_date: '',
        to_date: '',
    },
};

window.IterumAPI = {
    async get(path, params) {
        const url = new URL(path, window.location.origin);
        if (params) {
            Object.entries(params).forEach(([k, v]) => {
                if (v !== '' && v !== null && v !== undefined) url.searchParams.set(k, v);
            });
        }
        const res = await fetch(url, { credentials: 'same-origin' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ error: res.statusText }));
            throw new Error(err.error || 'Error');
        }
        return res.json();
    },
    async post(path, body) {
        const res = await fetch(path, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ error: res.statusText }));
            throw new Error(err.error || 'Error');
        }
        return res.json();
    },
    async patch(path, body) {
        const res = await fetch(path, {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        if (!res.ok) throw new Error('Error');
        return res.json();
    },
    async postForm(path, formData) {
        const res = await fetch(path, {
            method: 'POST',
            credentials: 'same-origin',
            body: formData,
        });
        const out = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(out.error || 'Error');
        return out;
    },
};

window.IterumUtils = {
    fmtDate(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        if (isNaN(d)) return iso;
        return d.toLocaleDateString('es-PY') + ' ' + d.toLocaleTimeString('es-PY', { hour: '2-digit', minute: '2-digit' });
    },
    fmtDateShort(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        return isNaN(d) ? iso : d.toLocaleDateString('es-PY');
    },
    npsClass(n) {
        if (n === null || n === undefined) return '';
        if (n >= 30) return 'nps-pos';
        if (n >= 0) return 'nps-neu';
        return 'nps-neg';
    },
    categoryBadge(cat) {
        if (!cat) return '—';
        return `<span class="iterum-badge iterum-badge-${cat}">${cat}</span>`;
    },
    verdictBadge(v) {
        if (!v) return '<span class="iterum-meta">sin auditar</span>';
        const labels = { ok: '✅ OK', warn: '⚠ Atención', err: '❌ Error' };
        return `<span class="iterum-badge iterum-badge-${v}">${labels[v] || v}</span>`;
    },
    statusBadge(s) {
        if (!s) return '';
        return `<span class="iterum-badge iterum-badge-status-${s}">${s}</span>`;
    },
    urgencyBadge(u) {
        return `<span class="iterum-badge iterum-badge-${u || 'low'}">${u || 'low'}</span>`;
    },
    truncate(str, n) {
        if (!str) return '';
        return str.length > n ? str.slice(0, n) + '…' : str;
    },
    escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    },
};

/* Filtros globales: lee URL params + popula los selects + maneja Aplicar/Limpiar */
window.IterumFilters = {
    async init(onApply) {
        const params = new URLSearchParams(window.location.search);
        IterumState.filters.channel = params.get('channel') || '';
        IterumState.filters.cell = params.get('cell') || '';
        IterumState.filters.from_date = params.get('from_date') || '';
        IterumState.filters.to_date = params.get('to_date') || '';

        const channelSel = document.getElementById('filterChannel');
        const cellSel = document.getElementById('filterCell');
        const fromInp = document.getElementById('filterFrom');
        const toInp = document.getElementById('filterTo');

        try {
            const meta = await IterumAPI.get('/iterum/api/meta/filters');
            if (channelSel) {
                meta.channels.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c; opt.textContent = c;
                    if (IterumState.filters.channel === c) opt.selected = true;
                    channelSel.appendChild(opt);
                });
            }
            if (cellSel) {
                meta.cells.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c; opt.textContent = c;
                    if (IterumState.filters.cell === c) opt.selected = true;
                    cellSel.appendChild(opt);
                });
            }
        } catch (e) { console.warn('iterum: no se pudieron cargar metadatos de filtros', e); }

        if (fromInp) fromInp.value = IterumState.filters.from_date;
        if (toInp) toInp.value = IterumState.filters.to_date;

        const apply = document.getElementById('filterApply');
        const clear = document.getElementById('filterClear');
        if (apply) apply.addEventListener('click', () => {
            IterumState.filters.channel = channelSel ? channelSel.value : '';
            IterumState.filters.cell = cellSel ? cellSel.value : '';
            IterumState.filters.from_date = fromInp ? fromInp.value : '';
            IterumState.filters.to_date = toInp ? toInp.value : '';
            if (onApply) onApply(IterumState.filters);
        });
        if (clear) clear.addEventListener('click', () => {
            if (channelSel) channelSel.value = '';
            if (cellSel) cellSel.value = '';
            if (fromInp) fromInp.value = '';
            if (toInp) toInp.value = '';
            IterumState.filters = { channel: '', cell: '', from_date: '', to_date: '' };
            if (onApply) onApply(IterumState.filters);
        });
    },
    queryParams() {
        const f = IterumState.filters;
        const p = {};
        if (f.channel) p.channel = f.channel;
        if (f.cell) p.cell = f.cell;
        if (f.from_date) p.from_date = f.from_date;
        if (f.to_date) p.to_date = f.to_date;
        return p;
    },
};
