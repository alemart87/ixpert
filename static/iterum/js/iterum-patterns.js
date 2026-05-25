/* Patrones: nube de palabras y clasificaciones frecuentes. */

const STOPWORDS = new Set([
    'el','la','de','que','y','a','en','un','ser','se','no','haber','por','con','su','para','como','estar',
    'tener','le','lo','mi','me','si','sin','sobre','este','ya','entre','cuando','todo','esta','muy','sus',
    'ese','era','los','las','del','una','unos','unas','pero','sino','o','u','al','es','son','fue','fui','ha',
    'porque','pero','sí','también','así','más','mas','muy','tan','solo','sólo','aun','aún','hay','han','hace',
]);

(async function () {
    await loadWordcloud();
    await loadClassifications();
})();

async function loadWordcloud() {
    try {
        const data = await IterumAPI.get('/iterum/api/surveys', { category: 'detractor', per_page: 100 });
        const freq = {};
        data.surveys.forEach(s => {
            if (!s.comment) return;
            s.comment.toLowerCase().split(/[\s.,;:!?¿¡()\[\]"'-]+/).forEach(w => {
                if (w.length < 4 || STOPWORDS.has(w)) return;
                freq[w] = (freq[w] || 0) + 1;
            });
        });
        const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 30);
        const el = document.getElementById('wordCloud');
        if (!sorted.length) {
            el.innerHTML = '<p class="iterum-meta">Sin comentarios suficientes</p>';
            return;
        }
        const max = sorted[0][1];
        el.innerHTML = sorted.map(([w, c]) => {
            const size = 12 + Math.round(24 * c / max);
            return `<span class="iterum-wordcloud-word" style="font-size:${size}px" title="${c} apariciones">${w}</span>`;
        }).join('');
    } catch (e) { console.error(e); }
}

async function loadClassifications() {
    try {
        const data = await IterumAPI.get('/iterum/api/audit');
        const freq = {};
        data.audits.forEach(a => {
            if (!a.classification) return;
            freq[a.classification] = (freq[a.classification] || 0) + 1;
        });
        const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 15);
        const el = document.getElementById('classificationStats');
        if (!sorted.length) {
            el.innerHTML = '<p class="iterum-meta">Sin clasificaciones registradas</p>';
            return;
        }
        const max = sorted[0][1];
        el.innerHTML = sorted.map(([k, c]) => {
            const pct = (100 * c / max).toFixed(1);
            return `<div class="iterum-bar-row" style="grid-template-columns:200px 1fr 60px">
                <div>${IterumUtils.escapeHtml(k)}</div>
                <div class="iterum-bar-track"><div style="background:#004080;width:${pct}%;height:100%"></div></div>
                <div><strong>${c}</strong></div>
            </div>`;
        }).join('');
    } catch (e) { console.error(e); }
}
