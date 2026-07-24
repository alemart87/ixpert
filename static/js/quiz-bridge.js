/* iXpert Quiz Bridge
 * ------------------
 * Se inyecta DENTRO del iframe de cada contenido tipo quiz (raw_html / trivia).
 * Como el iframe usa srcdoc + sandbox con allow-same-origin, este script corre
 * en el mismo origen que la app y puede guardar el resultado con la cookie de
 * sesion del usuario logueado.
 *
 * Tres formas de registrar un resultado, de mas a menos exacta:
 *
 *   1) El quiz llama explicitamente (recomendado, exacto):
 *        window.iXpertQuiz.save({ correct_answers: 8, total_questions: 10 });
 *      o con puntos:
 *        window.iXpertQuiz.save({ score: 85, max_score: 100 });
 *
 *   2) El quiz manda un postMessage:
 *        window.postMessage({ type: 'quiz_result', correct_answers: 8, total_questions: 10 }, '*');
 *
 *   3) Deteccion automatica: si el quiz no fue instrumentado, el bridge observa
 *      la pantalla de resultados y parsea el puntaje del texto visible. Requiere
 *      que el texto tenga (a) una senal de finalizacion y (b) un puntaje
 *      interpretable (X/Y, X de Y, o N%).
 *
 * Nunca debe romper el quiz: todo va dentro de try/catch.
 */
(function () {
    'use strict';

    var cfg = {};
    try {
        var tag = document.currentScript || document.querySelector('script[data-ixpert-quiz]');
        if (tag) {
            cfg = {
                contentId: tag.getAttribute('data-content-id') || null,
                slug: tag.getAttribute('data-quiz-slug') || '',
                title: tag.getAttribute('data-quiz-title') || 'Quiz',
                userName: tag.getAttribute('data-user-name') || '',
                autoDetect: tag.getAttribute('data-auto-detect') !== 'false'
            };
        }
    } catch (e) { /* noop */ }

    var startedAt = Date.now();
    var lastSentKey = null;
    var sending = false;
    // Si el quiz reporto su resultado de forma exacta, apagamos la deteccion
    // automatica: ya tenemos el dato bueno y no hace falta adivinarlo del texto.
    var exactSaveDone = false;

    // --- Patrones de deteccion ---------------------------------------------

    // Senal de que el quiz TERMINO. Sin esto no se auto-guarda nada: evita
    // capturar el marcador parcial o una barra de progreso a mitad del quiz.
    var FINALIZED = /(resultado\s*final|puntuaci[oó]n\s*final|puntaje\s*final|nota\s*final|calificaci[oó]n\s*final|finaliz|termin(aste|ado|ó|o\s+el\s+quiz)|felicitac|complet(aste|ado)|tu\s+(puntaje|puntuaci[oó]n|nota|calificaci[oó]n|resultado)|obtuviste|acertaste|respondiste\s+correctamente|(des)?aprobad|volver\s+a\s+intentar|reintentar|intentar\s+de\s+nuevo)/i;

    // "Pregunta 3 de 10" NO es un puntaje.
    var COUNTER_CONTEXT = /(pregunta|question|item|paso|slide|n[°º]|nro\.?)\s*$/i;

    function toNum(s) {
        return parseFloat(String(s).replace(',', '.'));
    }

    /* Extrae un resultado del texto visible. Devuelve null si no hay nada
     * confiable. El orden importa: los patrones explicitos ganan sobre los
     * genericos, porque son los que no se confunden con contadores. */
    function extract(text) {
        var m;

        // "8 de 10 correctas" / "8/10 respuestas correctas"
        m = text.match(/(\d+)\s*(?:de|\/)\s*(\d+)\s*(?:respuestas?\s*)?(?:correctas?|aciertos?|buenas?)/i);
        if (m) return { correct_answers: +m[1], total_questions: +m[2] };

        // "correctas: 8 de 10" / "aciertos 8/10"
        m = text.match(/(?:correctas?|aciertos?|acertaste)\s*[:=]?\s*(\d+)\s*(?:de|\/)\s*(\d+)/i);
        if (m) return { correct_answers: +m[1], total_questions: +m[2] };

        // "85 puntos de 100" / "85 pts / 100"
        m = text.match(/(\d+(?:[.,]\d+)?)\s*(?:puntos?|pts?\.?)\s*(?:de|\/)\s*(\d+(?:[.,]\d+)?)/i);
        if (m) return { score: toNum(m[1]), max_score: toNum(m[2]) };

        // "puntuación final es: 85 de 100"
        m = text.match(/(?:puntaje|puntuaci[oó]n|nota|calificaci[oó]n|score)[^\d%]{0,30}?(\d+(?:[.,]\d+)?)\s*(?:de|\/)\s*(\d+(?:[.,]\d+)?)/i);
        if (m) return { score: toNum(m[1]), max_score: toNum(m[2]) };

        // Porcentaje explicito: "obtuviste 80%" / "Resultado: 80 %"
        m = text.match(/(\d+(?:[.,]\d+)?)\s*%/);
        if (m) {
            var pct = toNum(m[1]);
            if (pct >= 0 && pct <= 100) return { percentage: pct };
        }

        // Generico "8 de 10" / "8/10", descartando contadores de pregunta.
        var generic = /(\d+)\s*(?:\s+de\s+|\/)\s*(\d+)/g;
        while ((m = generic.exec(text)) !== null) {
            var before = text.slice(Math.max(0, m.index - 25), m.index);
            if (COUNTER_CONTEXT.test(before.trim() + ' ')) continue;
            var a = +m[1], b = +m[2];
            if (b > 0 && a <= b) return { correct_answers: a, total_questions: b };
        }

        return null;
    }

    function resultKey(payload) {
        return [payload.score, payload.max_score, payload.correct_answers,
                payload.total_questions, payload.percentage].join('|');
    }

    // --- Envio --------------------------------------------------------------

    function save(payload, opts) {
        opts = opts || {};
        try {
            if (!payload || typeof payload !== 'object') return;
            var key = resultKey(payload);
            if (key === lastSentKey || sending) return;
            if (exactSaveDone && opts.source === 'auto') return;

            var body = {
                content_id: cfg.contentId,
                quiz_slug: cfg.slug,
                quiz_title: cfg.title,
                duration_seconds: Math.round((Date.now() - startedAt) / 1000),
                source: opts.source || 'api'
            };
            for (var k in payload) {
                if (Object.prototype.hasOwnProperty.call(payload, k)) body[k] = payload[k];
            }

            sending = true;
            fetch('/api/quiz/result', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(body)
            }).then(function (r) {
                return r.ok ? r.json() : null;
            }).then(function (data) {
                sending = false;
                if (!data || !data.ok) return;
                lastSentKey = key;
                if (body.source !== 'auto') exactSaveDone = true;
                showBadge(data, body);
            }).catch(function () { sending = false; });
        } catch (e) { sending = false; }
    }

    // --- Confirmacion visible dentro del quiz -------------------------------
    // El capacitador necesita ver que el resultado quedo registrado, y la
    // persona necesita poder descargar su comprobante.

    function showBadge(data, body) {
        try {
            var existing = document.getElementById('ixpert-quiz-badge');
            if (existing) existing.parentNode.removeChild(existing);

            var box = document.createElement('div');
            box.id = 'ixpert-quiz-badge';
            // Arriba a la derecha: el iframe ocupa casi toda la pantalla, asi que
            // un badge anclado abajo queda fuera de la vista sin hacer scroll.
            box.setAttribute('style', [
                'position:fixed', 'top:12px', 'right:12px', 'z-index:2147483000',
                'background:#ffffff', 'border-left:4px solid #2e7d32',
                'border-radius:10px', 'padding:12px 16px',
                'box-shadow:0 4px 16px rgba(0,0,0,0.25)',
                'font-family:Segoe UI,Tahoma,Geneva,Verdana,sans-serif',
                'font-size:13px', 'color:#333', 'max-width:320px'
            ].join(';'));

            var pct = (data.percentage !== undefined && data.percentage !== null)
                ? data.percentage + '%' : '';
            var who = data.user || cfg.userName || '';

            var title = document.createElement('div');
            title.setAttribute('style', 'font-weight:700;color:#2e7d32;margin-bottom:4px');
            title.textContent = data.duplicate
                ? '✔ Resultado ya registrado'
                : '✔ Resultado registrado';
            box.appendChild(title);

            var info = document.createElement('div');
            info.setAttribute('style', 'color:#555;line-height:1.5');
            info.textContent = who + (pct ? ' — ' + pct : '') +
                ' · Intento ' + (data.attempt_number || 1);
            box.appendChild(info);

            var actions = document.createElement('div');
            actions.setAttribute('style', 'margin-top:8px;display:flex;gap:8px');

            var dl = document.createElement('button');
            dl.type = 'button';
            dl.textContent = '⬇ Descargar';
            dl.setAttribute('style', 'background:#004080;color:#fff;border:none;border-radius:20px;padding:6px 14px;cursor:pointer;font-size:12px');
            dl.onclick = function () { downloadResult(data, body, who); };
            actions.appendChild(dl);

            var close = document.createElement('button');
            close.type = 'button';
            close.textContent = 'Cerrar';
            close.setAttribute('style', 'background:#eee;color:#555;border:none;border-radius:20px;padding:6px 14px;cursor:pointer;font-size:12px');
            close.onclick = function () { box.parentNode && box.parentNode.removeChild(box); };
            actions.appendChild(close);

            box.appendChild(actions);
            document.body.appendChild(box);
        } catch (e) { /* noop */ }
    }

    function downloadResult(data, body, who) {
        try {
            var rows = [
                ['Usuario', who],
                ['Quiz', cfg.title],
                ['Porcentaje', (data.percentage !== undefined ? data.percentage : '') + '%'],
                ['Resultado', data.passed ? 'Aprobado' : 'No aprobado'],
                ['Intento', data.attempt_number || 1],
                ['Correctas', body.correct_answers !== undefined ? body.correct_answers : ''],
                ['Preguntas', body.total_questions !== undefined ? body.total_questions : ''],
                ['Puntaje', body.score !== undefined ? body.score : ''],
                ['Puntaje maximo', body.max_score !== undefined ? body.max_score : ''],
                ['Duracion (seg)', body.duration_seconds],
                ['Fecha', new Date().toLocaleString('es-PY')]
            ];
            var csv = '﻿' + rows.map(function (r) { return r.join(';'); }).join('\n');
            var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            var a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'resultado_' + (cfg.slug || 'quiz') + '.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        } catch (e) { /* noop */ }
    }

    // --- API publica para quizzes instrumentados ----------------------------

    window.iXpertQuiz = {
        save: function (payload) { save(payload, { source: 'api' }); },
        config: cfg
    };

    // Compatibilidad: quizzes que mandan postMessage en vez de llamar la API.
    window.addEventListener('message', function (ev) {
        try {
            var d = ev.data;
            if (d && typeof d === 'object' && d.type === 'quiz_result') {
                save(d, { source: 'api' });
            }
        } catch (e) { /* noop */ }
    });

    // --- Deteccion automatica ----------------------------------------------

    function scanAndSave() {
        try {
            if (!cfg.autoDetect) return;
            // innerText solo incluye texto VISIBLE: si el quiz oculto la pantalla
            // de preguntas y mostro la de resultados, aca queda solo el resultado.
            var text = (document.body.innerText || '').replace(/\s+/g, ' ').trim();
            if (!text || text.length > 6000) return;
            if (!FINALIZED.test(text)) return;

            var found = extract(text);
            if (!found) return;
            save(found, { source: 'auto' });
        } catch (e) { /* noop */ }
    }

    function start() {
        try {
            var timer = null;
            var debounced = function () {
                clearTimeout(timer);
                timer = setTimeout(scanAndSave, 600);
            };
            var obs = new MutationObserver(debounced);
            obs.observe(document.body, {
                childList: true, subtree: true, characterData: true,
                attributes: true, attributeFilter: ['style', 'class', 'hidden']
            });
            // Click en "Finalizar/Ver resultado" tambien dispara el scan.
            document.addEventListener('click', debounced, true);
            scanAndSave();
        } catch (e) { /* noop */ }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
