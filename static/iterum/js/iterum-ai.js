/* Iterum AI Analyst — cliente SSE con UI compacta y streaming live. */

const State = {
    currentChatId: null,
    chats: [],
    canvasDirty: false,
    canvasVersion: 0,
    streaming: false,
};

// ============================================================================
// Utilities
// ============================================================================
function $(id) { return document.getElementById(id); }
function escapeHtml(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
let _mermaidCounter = 0;
function mdToHtml(md) {
    if (!md) return '';
    // 1. Extraer code blocks ``` ``` para no procesar markdown adentro.
    //    Distingue mermaid (renderizado como diagrama) de codigo normal.
    const codeBlocks = [];
    md = md.replace(/```([a-z]*)\n?([\s\S]*?)```/gm, (m, lang, code) => {
        const i = codeBlocks.length;
        const l = (lang || '').toLowerCase().trim();
        const mermaidLangs = ['mermaid', 'mindmap', 'flowchart', 'gantt', 'sequencediagram', 'graph'];
        if (mermaidLangs.includes(l)) {
            const id = 'mermaid-' + (++_mermaidCounter);
            const def = (l === 'mermaid') ? code : (l + '\n' + code);
            codeBlocks.push(
                '<div class="ai-mermaid-block" data-mermaid-id="' + id + '">' +
                '<div class="ai-mermaid-loading">Renderizando diagrama...</div>' +
                '<div class="ai-mermaid-src" style="display:none">' + escapeHtml(def) + '</div>' +
                '</div>'
            );
        } else {
            codeBlocks.push('<pre><code class="lang-' + escapeHtml(l) + '">' + escapeHtml(code) + '</code></pre>');
        }
        return '__CB' + i + '__';
    });

    let h = escapeHtml(md);

    // 2. Tablas markdown (| col | col |)
    h = h.replace(/((?:^\|.+\|\n?)+)/gm, (block) => {
        const lines = block.trim().split('\n');
        if (lines.length < 2) return block;
        const sep = lines[1];
        const isTable = /^\|[\s\-:|]+\|$/.test(sep);
        const rows = isTable ? [lines[0]].concat(lines.slice(2)) : lines;
        const headRow = isTable ? lines[0] : null;
        const bodyRows = isTable ? lines.slice(2) : lines;
        const cellHtml = (row, tag) => row.slice(1, -1).split('|')
            .map(c => `<${tag}>${c.trim()}</${tag}>`).join('');
        let out = '<table>';
        if (headRow) out += `<thead><tr>${cellHtml(headRow, 'th')}</tr></thead>`;
        out += '<tbody>' + bodyRows.map(r => `<tr>${cellHtml(r, 'td')}</tr>`).join('') + '</tbody>';
        out += '</table>';
        return out;
    });

    // 3. Headers, bold, italic, inline code, blockquote, hr
    h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    h = h.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    h = h.replace(/^---$/gm, '<hr>');
    h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/(?<![\*_])\*([^\*\n]+?)\*(?![\*_])/g, '<em>$1</em>');
    h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // 4. Listas — agrupar bullets consecutivos
    h = h.replace(/^\s*[-*] (.+)$/gm, '<li class="bullet">$1</li>');
    h = h.replace(/^\s*(\d+)\. (.+)$/gm, '<li class="ordered">$2</li>');
    h = h.replace(/((?:<li class="bullet">.*?<\/li>\s*)+)/gs, '<ul>$1</ul>');
    h = h.replace(/((?:<li class="ordered">.*?<\/li>\s*)+)/gs, '<ol>$1</ol>');
    h = h.replace(/ class="bullet"| class="ordered"/g, '');

    // 5. Parrafos por dobles newlines (pero no romper blocks ya formados)
    const lines = h.split('\n');
    const out = [];
    let para = [];
    function flush() {
        if (!para.length) return;
        const txt = para.join(' ').trim();
        if (txt) out.push(`<p>${txt}</p>`);
        para = [];
    }
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) { flush(); continue; }
        if (/^<(h\d|ul|ol|li|table|thead|tbody|tr|td|th|pre|blockquote|hr|div)/i.test(trimmed) || /^__CB\d+__/.test(trimmed)) {
            flush();
            out.push(trimmed);
        } else {
            para.push(trimmed);
        }
    }
    flush();
    h = out.join('\n');

    // 6. Restaurar code blocks
    h = h.replace(/__CB(\d+)__/g, (_, i) => codeBlocks[parseInt(i)] || '');
    return h;
}

// Renderiza diagramas mermaid presentes en el container dado
async function renderMermaid(container) {
    if (!window.IterumMermaid) return;  // todavia no cargo
    const blocks = container.querySelectorAll('.ai-mermaid-block[data-mermaid-id]');
    for (const block of blocks) {
        if (block.dataset.rendered === '1') continue;
        const src = block.querySelector('.ai-mermaid-src');
        if (!src) continue;
        const def = src.textContent.trim();
        const id = block.dataset.mermaidId;
        try {
            const { svg } = await window.IterumMermaid.render(id, def);
            block.innerHTML = svg;
            block.dataset.rendered = '1';
        } catch (e) {
            block.innerHTML = '<div class="ai-error">Error en diagrama: ' + escapeHtml(e.message || String(e)) + '</div>';
        }
    }
}
function shortJson(obj, max=120) {
    try {
        const s = JSON.stringify(obj);
        return s.length > max ? s.slice(0, max) + '…' : s;
    } catch { return ''; }
}
function bytes(obj) {
    try { return JSON.stringify(obj).length; } catch { return 0; }
}

// ============================================================================
// API
// ============================================================================
const API = {
    async listChats() {
        const r = await fetch('/iterum/api/ai/chats', { credentials: 'same-origin' });
        return (await r.json()).chats || [];
    },
    async createChat() {
        const r = await fetch('/iterum/api/ai/chats', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }, body: '{}',
        });
        return await r.json();
    },
    async getChat(id) {
        const r = await fetch(`/iterum/api/ai/chats/${id}`, { credentials: 'same-origin' });
        if (!r.ok) throw new Error('not found');
        return await r.json();
    },
    async renameChat(id, title) {
        await fetch(`/iterum/api/ai/chats/${id}/rename`, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });
    },
    async archiveChat(id) {
        await fetch(`/iterum/api/ai/chats/${id}`, {
            method: 'DELETE', credentials: 'same-origin',
        });
    },
    async saveCanvas(id, content_md, title) {
        await fetch(`/iterum/api/ai/chats/${id}/canvas`, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content_md, title }),
        });
    },
};

// ============================================================================
// Sidebar
// ============================================================================
async function loadChatsList() {
    State.chats = await API.listChats();
    const el = $('aiChatsList');
    if (!State.chats.length) {
        el.innerHTML = '<div class="ai-empty">Sin conversaciones</div>';
        return;
    }
    el.innerHTML = State.chats.map(c => `
        <div class="ai-chat-item ${c.id === State.currentChatId ? 'active' : ''}" data-id="${c.id}">
            <div class="ai-chat-item-title">${escapeHtml(c.title)}</div>
            <div class="ai-chat-item-meta">${formatDate(c.last_message_at)}</div>
        </div>`).join('');
    el.querySelectorAll('.ai-chat-item').forEach(it => {
        it.addEventListener('click', () => loadChat(parseInt(it.dataset.id)));
    });
}

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const diff = (new Date() - d) / 1000;
    if (diff < 60) return 'ahora';
    if (diff < 3600) return Math.floor(diff / 60) + ' min';
    if (diff < 86400) return Math.floor(diff / 3600) + ' h';
    return d.toLocaleDateString('es-PY');
}

// ============================================================================
// Load chat (historial)
// ============================================================================
async function loadChat(id) {
    State.currentChatId = id;
    const chat = await API.getChat(id);
    $('aiChatTitle').textContent = chat.title || 'Conversación';
    $('aiChatTokens').textContent = chat.total_tokens ? `${chat.total_tokens} tokens` : '';
    renderMessagesGrouped(chat.messages);
    renderCanvas(chat.canvas);
    await loadChatsList();
}

const SUGGESTIONS = [
    'Resumime la semana',
    'Asesores que necesitan coaching urgente',
    'Por qué bajó el NPS',
    'Plan de acción para PERSONAL BANK',
    'Mapa mental de causas raíz',
    'Ruta crítica para alcanzar el objetivo 77%',
];

function renderWelcome(intro = 'Tu analista IA está listo para revisar el NPS, detectar causa raíz y armar planes de acción.') {
    return `<div class="ai-welcome">
        <h2>Bienvenido, SuperAdmin</h2>
        <p>${intro}</p>
        <div class="ai-suggestions">
            ${SUGGESTIONS.map(s => `<button class="ai-suggestion">${s}</button>`).join('')}
        </div>
    </div>`;
}

function bindSuggestions(container) {
    container.querySelectorAll('.ai-suggestion').forEach(b => {
        b.addEventListener('click', () => {
            $('aiInput').value = b.textContent.trim();
            $('aiInput').focus();
            $('aiInput').style.height = 'auto';
            $('aiInput').style.height = Math.min(160, $('aiInput').scrollHeight) + 'px';
        });
    });
}

/**
 * Agrupa los items del historial en "turnos": cada turno tiene
 * - 1 user message
 * - 0..1 reasoning
 * - 0..N tool calls + outputs (los agrupamos en una pill compacta)
 * - 1 assistant final
 */
function renderMessagesGrouped(messages) {
    const el = $('aiMessages');
    if (!messages || !messages.length) {
        el.innerHTML = renderWelcome('Escribí tu pregunta para empezar, o usá una de estas sugerencias:');
        bindSuggestions(el);
        return;
    }
    el.innerHTML = '';
    let currentTurn = null;
    function newTurn() {
        currentTurn = { tools: [], reasoning: '', assistant: '', userText: '', dom: null };
    }
    for (const m of messages) {
        if (m.role === 'user') {
            if (currentTurn) flushTurn(currentTurn, el);
            newTurn();
            currentTurn.userText = m.content || '';
        } else if (!currentTurn) {
            newTurn();
        }
        if (m.role === 'reasoning') currentTurn.reasoning = m.content || '';
        else if (m.role === 'tool_call') currentTurn.tools.push({ name: m.tool_name, args: m.tool_args, result: null });
        else if (m.role === 'tool_output') {
            // matchear con el ultimo tool_call del mismo nombre sin result
            for (let i = currentTurn.tools.length - 1; i >= 0; i--) {
                if (currentTurn.tools[i].name === m.tool_name && currentTurn.tools[i].result === null) {
                    currentTurn.tools[i].result = m.tool_result; break;
                }
            }
        } else if (m.role === 'assistant') currentTurn.assistant = m.content || '';
    }
    if (currentTurn) flushTurn(currentTurn, el);
    el.scrollTop = el.scrollHeight;
}

function flushTurn(turn, container) {
    if (turn.userText) {
        const userDiv = document.createElement('div');
        userDiv.className = 'ai-msg ai-msg-user';
        userDiv.innerHTML = `<div class="ai-msg-bubble ai-msg-user-bubble">${escapeHtml(turn.userText)}</div>`;
        container.appendChild(userDiv);
    }
    const assistDom = buildAssistantTurnDom();
    container.appendChild(assistDom.root);
    if (turn.reasoning) {
        assistDom.reasoning.style.display = 'block';
        assistDom.reasoningBody.textContent = turn.reasoning;
    }
    if (turn.tools.length) {
        assistDom.toolsStrip.style.display = 'flex';
        assistDom.toolsCount.textContent = turn.tools.length;
        turn.tools.forEach(t => addToolChip(assistDom.toolsList, t.name, t.args, t.result));
    }
    if (turn.assistant) {
        assistDom.bubble.innerHTML = mdToHtml(turn.assistant);
    } else {
        assistDom.bubble.style.display = 'none';
    }
}

/**
 * Construye el DOM de un turno del asistente con secciones colapsables:
 * [avatar] [
 *    🧠 Razonamiento (panel amarillo, oculto si no hay)
 *    🔧 Tools usadas (3)  [▼]  con chips dentro
 *    📝 Respuesta (burbuja blanca)
 * ]
 */
function buildAssistantTurnDom() {
    const root = document.createElement('div');
    root.className = 'ai-msg ai-msg-assistant';
    root.innerHTML = `
        <div class="ai-msg-avatar">🤖</div>
        <div class="ai-msg-body">
            <details class="ai-reasoning" style="display:none">
                <summary>🧠 <strong>Razonamiento</strong> <span class="ai-pulse"></span></summary>
                <div class="ai-reasoning-body"></div>
            </details>
            <div class="ai-tools-strip" style="display:none">
                <div class="ai-tools-header">
                    <span class="ai-tools-icon">🔧</span>
                    <strong>Herramientas usadas (<span class="ai-tools-count">0</span>)</strong>
                    <button class="ai-tools-toggle" type="button">Ver detalles ▾</button>
                </div>
                <div class="ai-tools-list" style="display:none"></div>
            </div>
            <div class="ai-msg-bubble"></div>
        </div>
    `;
    const reasoning = root.querySelector('.ai-reasoning');
    const reasoningBody = root.querySelector('.ai-reasoning-body');
    const toolsStrip = root.querySelector('.ai-tools-strip');
    const toolsCount = root.querySelector('.ai-tools-count');
    const toolsList = root.querySelector('.ai-tools-list');
    const toolsToggle = root.querySelector('.ai-tools-toggle');
    const bubble = root.querySelector('.ai-msg-bubble');

    toolsToggle.addEventListener('click', () => {
        const isOpen = toolsList.style.display === 'block';
        toolsList.style.display = isOpen ? 'none' : 'block';
        toolsToggle.textContent = isOpen ? 'Ver detalles ▾' : 'Ocultar ▴';
    });

    return { root, reasoning, reasoningBody, toolsStrip, toolsCount, toolsList, bubble };
}

function addToolChip(toolsList, name, args, result) {
    const chip = document.createElement('div');
    chip.className = 'ai-tool-chip';
    chip.dataset.tool = name;
    const isRunning = result === null || result === undefined;
    const argsBrief = args ? shortJson(args, 80) : '';
    chip.innerHTML = `
        <div class="ai-tool-chip-head">
            <span class="ai-tool-chip-dot ${isRunning ? 'running' : 'done'}"></span>
            <code>${escapeHtml(name)}</code>
            ${argsBrief ? `<span class="ai-tool-chip-args">${escapeHtml(argsBrief)}</span>` : ''}
            ${result !== undefined && result !== null ? `<span class="ai-tool-chip-size">${bytes(result)}b</span>` : ''}
        </div>
        ${result !== null && result !== undefined ? `
        <details class="ai-tool-chip-result">
            <summary>Resultado</summary>
            <pre>${escapeHtml(JSON.stringify(result, null, 2).slice(0, 4000))}</pre>
        </details>` : ''}
    `;
    toolsList.appendChild(chip);
    return chip;
}

// ============================================================================
// Canvas
// ============================================================================
function renderCanvas(canvas) {
    if (!canvas) return;
    $('aiCanvas').value = canvas.content_md || '';
    $('aiCanvasTitle').value = canvas.title || 'Workspace';
    $('aiCanvasVersion').textContent = `v${canvas.version || 0}`;
    State.canvasVersion = canvas.version || 0;
    State.canvasDirty = false;
    updateCanvasPreview();
}
function updateCanvasPreview() {
    const el = $('aiCanvasPreview');
    el.innerHTML = mdToHtml($('aiCanvas').value);
    renderMermaid(el);
}
async function saveCanvasManually() {
    if (!State.currentChatId) return;
    await API.saveCanvas(State.currentChatId, $('aiCanvas').value, $('aiCanvasTitle').value);
    State.canvasDirty = false;
    State.canvasVersion++;
    $('aiCanvasVersion').textContent = `v${State.canvasVersion}`;
    flashCanvas();
}
function flashCanvas() {
    const el = $('aiCanvasCol');
    el.classList.add('ai-canvas-flash');
    setTimeout(() => el.classList.remove('ai-canvas-flash'), 700);
}

// ============================================================================
// Streaming SSE con UI live
// ============================================================================
async function sendMessage() {
    if (State.streaming) return;
    if (!State.currentChatId) {
        const c = await API.createChat();
        State.currentChatId = c.id;
        await loadChatsList();
    }
    const text = $('aiInput').value.trim();
    if (!text) return;
    $('aiInput').value = '';
    $('aiInput').style.height = 'auto';
    State.streaming = true;
    $('aiSend').disabled = true;

    const welcome = document.querySelector('.ai-welcome');
    if (welcome) welcome.remove();

    // 1. User bubble
    const userDiv = document.createElement('div');
    userDiv.className = 'ai-msg ai-msg-user';
    userDiv.innerHTML = `<div class="ai-msg-bubble ai-msg-user-bubble">${escapeHtml(text)}</div>`;
    $('aiMessages').appendChild(userDiv);

    // 2. Assistant turn skeleton (todo oculto, se va revelando)
    const turn = buildAssistantTurnDom();
    $('aiMessages').appendChild(turn.root);

    // Status pill abajo del avatar — muestra qué está haciendo
    const status = document.createElement('div');
    status.className = 'ai-thinking-status';
    status.innerHTML = `<span class="ai-thinking-spinner"><span></span><span></span><span></span></span><span class="ai-thinking-label">Pensando…</span>`;
    turn.root.querySelector('.ai-msg-body').prepend(status);
    const statusLabel = status.querySelector('.ai-thinking-label');

    let assistantText = '';
    const toolChipMap = new Map();  // name → chip DOM

    function setStatus(label) { statusLabel.textContent = label; }
    function scrollBottom() { $('aiMessages').scrollTop = $('aiMessages').scrollHeight; }

    const resp = await fetch(`/iterum/api/ai/chats/${State.currentChatId}/message`, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
        body: JSON.stringify({ content: text }),
    });

    if (!resp.ok || !resp.body) {
        turn.bubble.innerHTML = `<div class="ai-error">Error al iniciar el stream (${resp.status})</div>`;
        status.remove();
        State.streaming = false;
        $('aiSend').disabled = false;
        return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() || '';
        for (const block of blocks) {
            if (!block.trim() || block.startsWith(':')) continue;  // keep-alives
            const lines = block.split('\n');
            let event = 'message', data = '';
            for (const line of lines) {
                if (line.startsWith('event: ')) event = line.slice(7).trim();
                else if (line.startsWith('data: ')) data += line.slice(6);
            }
            if (!data) continue;
            let payload; try { payload = JSON.parse(data); } catch { continue; }

            // ===== Handlers =====
            if (event === 'reasoning') {
                if (turn.reasoning.style.display === 'none') {
                    turn.reasoning.style.display = 'block';
                    turn.reasoning.open = true;
                }
                turn.reasoning.classList.add('streaming');
                turn.reasoningBody.textContent += payload.delta;
                turn.reasoningBody.scrollTop = turn.reasoningBody.scrollHeight;
                setStatus('Razonando…');
                scrollBottom();
            }
            else if (event === 'tool_call') {
                if (turn.toolsStrip.style.display === 'none') {
                    turn.toolsStrip.style.display = 'block';
                }
                const count = turn.toolsList.children.length + 1;
                turn.toolsCount.textContent = count;
                const chip = addToolChip(turn.toolsList, payload.name, payload.args, null);
                toolChipMap.set(payload.name + '#' + count, chip);
                // Tambien guardo por nombre para matching simple
                if (!toolChipMap.has(payload.name)) toolChipMap.set(payload.name, []);
                toolChipMap.get(payload.name).push(chip);
                setStatus(`Consultando ${payload.name}…`);
                scrollBottom();
            }
            else if (event === 'tool_output') {
                // matchear con el primer chip de ese name que esté 'running'
                const chips = toolChipMap.get(payload.name) || [];
                for (const chip of chips) {
                    const dot = chip.querySelector('.ai-tool-chip-dot');
                    if (dot && dot.classList.contains('running')) {
                        dot.classList.remove('running');
                        dot.classList.add('done');
                        // Agregar el resultado expandible
                        const out = payload.result;
                        const outStr = typeof out === 'string' ? out : JSON.stringify(out, null, 2);
                        const det = document.createElement('details');
                        det.className = 'ai-tool-chip-result';
                        det.innerHTML = `<summary>Resultado</summary><pre>${escapeHtml(outStr.slice(0, 4000))}</pre>`;
                        chip.appendChild(det);
                        // Tamano
                        const sizeSpan = document.createElement('span');
                        sizeSpan.className = 'ai-tool-chip-size';
                        sizeSpan.textContent = bytes(out) + 'b';
                        chip.querySelector('.ai-tool-chip-head').appendChild(sizeSpan);
                        break;
                    }
                }
            }
            else if (event === 'canvas_update') {
                $('aiCanvas').value = payload.content_md || '';
                $('aiCanvasTitle').value = payload.title || 'Workspace';
                $('aiCanvasVersion').textContent = `v${payload.version}`;
                State.canvasVersion = payload.version;
                updateCanvasPreview();
                flashCanvas();
                setStatus('Canvas actualizado');
            }
            else if (event === 'assistant_delta') {
                status.style.display = 'none';
                // Stop streaming cursor en reasoning + colapsar
                turn.reasoning.classList.remove('streaming');
                if (turn.reasoning.open) turn.reasoning.open = false;
                turn.bubble.classList.add('streaming');
                assistantText += payload.delta;
                turn.bubble.innerHTML = mdToHtml(assistantText);
                // Reaplicar clase porque innerHTML la pisa? No, classList persiste
                turn.bubble.classList.add('streaming');
                scrollBottom();
            }
            else if (event === 'done') {
                status.style.display = 'none';
                turn.reasoning.classList.remove('streaming');
                turn.bubble.classList.remove('streaming');
                turn.root.querySelectorAll('.ai-pulse').forEach(p => p.remove());
                if (payload.title) $('aiChatTitle').textContent = payload.title;
            }
            else if (event === 'error') {
                status.remove();
                turn.bubble.innerHTML = `<div class="ai-error">⚠ ${escapeHtml(payload.error || 'error')}</div>`;
            }
        }
    }

    State.streaming = false;
    $('aiSend').disabled = false;
    loadChatsList();
}

// ============================================================================
// Init
// ============================================================================
async function init() {
    await loadChatsList();
    if (State.chats.length) {
        await loadChat(State.chats[0].id);
    } else {
        // Sin chats: mostrar welcome con sugerencias
        $('aiMessages').innerHTML = renderWelcome();
        bindSuggestions($('aiMessages'));
    }

    $('aiNewChat').addEventListener('click', async () => {
        const c = await API.createChat();
        await loadChatsList();
        await loadChat(c.id);
    });
    $('aiSend').addEventListener('click', sendMessage);
    $('aiInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    $('aiInput').addEventListener('input', (e) => {
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(160, e.target.scrollHeight) + 'px';
    });
    // Sugerencias se bindean dinamicamente en renderWelcome/bindSuggestions
    // porque el welcome se re-renderiza al crear nueva conversacion.
    $('aiCanvas').addEventListener('input', () => {
        State.canvasDirty = true; updateCanvasPreview();
    });
    $('aiCanvasSave').addEventListener('click', saveCanvasManually);
    $('aiRenameChat').addEventListener('click', async () => {
        if (!State.currentChatId) return;
        const t = prompt('Nuevo título:', $('aiChatTitle').textContent);
        if (t && t.trim()) {
            await API.renameChat(State.currentChatId, t.trim());
            $('aiChatTitle').textContent = t.trim();
            await loadChatsList();
        }
    });
    $('aiArchiveChat').addEventListener('click', async () => {
        if (!State.currentChatId) return;
        if (!confirm('¿Archivar esta conversación?')) return;
        await API.archiveChat(State.currentChatId);
        State.currentChatId = null;
        await loadChatsList();
        $('aiChatTitle').textContent = 'Seleccioná o creá una conversación';
        $('aiMessages').innerHTML = '';
        $('aiCanvas').value = '';
    });
    // === Canvas: tabs (vista / editor / dividir) ===
    document.querySelectorAll('.ai-canvas-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.ai-canvas-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const mode = tab.dataset.tab;
            const editor = $('aiCanvas');
            const preview = $('aiCanvasPreview');
            const body = document.querySelector('.ai-canvas-body');
            body.style.flexDirection = 'column';
            if (mode === 'editor') {
                editor.classList.remove('ai-canvas-hidden-pane');
                preview.classList.add('ai-canvas-hidden-pane');
            } else if (mode === 'preview') {
                editor.classList.add('ai-canvas-hidden-pane');
                preview.classList.remove('ai-canvas-hidden-pane');
            } else {
                // dividir
                editor.classList.remove('ai-canvas-hidden-pane');
                preview.classList.remove('ai-canvas-hidden-pane');
                editor.style.flex = '0 0 40%';
                preview.style.flex = '1 1 auto';
                preview.style.borderTop = '1px solid var(--ai-slate-200)';
            }
            if (mode !== 'split') {
                editor.style.flex = ''; preview.style.flex = '';
                preview.style.borderTop = '';
            }
            renderMermaid(preview);
        });
    });

    // === Canvas: redimensionable (drag handle) + persistencia ===
    const savedWidth = localStorage.getItem('iterum_ai_canvas_width');
    if (savedWidth) {
        document.documentElement.style.setProperty('--ai-canvas-width', savedWidth + 'px');
    }
    const resizer = $('aiCanvasResizer');
    if (resizer) {
        let dragging = false;
        const onMove = (e) => {
            if (!dragging) return;
            // Si esta en fullscreen, ignorar
            if ($('aiCanvasCol').classList.contains('fullscreen')) return;
            const x = e.touches ? e.touches[0].clientX : e.clientX;
            const w = Math.max(340, Math.min(window.innerWidth - 520, window.innerWidth - x));
            document.documentElement.style.setProperty('--ai-canvas-width', w + 'px');
            e.preventDefault();
        };
        const stop = () => {
            if (!dragging) return;
            dragging = false;
            resizer.classList.remove('dragging');
            document.body.classList.remove('ai-resizing');  // libera cursor global
            const w = getComputedStyle(document.documentElement).getPropertyValue('--ai-canvas-width').trim();
            if (w) localStorage.setItem('iterum_ai_canvas_width', parseInt(w));
        };
        resizer.addEventListener('mousedown', e => {
            dragging = true;
            resizer.classList.add('dragging');
            document.body.classList.add('ai-resizing');  // fuerza col-resize en TODOS los elementos
            e.preventDefault();
        });
        resizer.addEventListener('touchstart', e => {
            dragging = true;
            resizer.classList.add('dragging');
            document.body.classList.add('ai-resizing');
        });
        document.addEventListener('mousemove', onMove);
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('mouseup', stop);
        document.addEventListener('touchend', stop);
        document.addEventListener('mouseleave', stop);
    }

    // === Canvas: fullscreen ===
    const fsBtn = $('aiCanvasFullscreen');
    if (fsBtn) {
        fsBtn.addEventListener('click', () => {
            $('aiCanvasCol').classList.toggle('fullscreen');
            fsBtn.textContent = $('aiCanvasCol').classList.contains('fullscreen') ? '⛶' : '⛶';
        });
    }

    // === Re-renderizar mermaid cuando carga la libreria si el preview ya tiene contenido ===
    window.addEventListener('mermaid-ready', () => renderMermaid($('aiCanvasPreview')));

    $('aiToggleCanvas').addEventListener('click', () => {
        $('aiCanvasCol').classList.toggle('ai-canvas-hidden');
    });
    window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault(); saveCanvasManually();
        }
    });
}

init();
