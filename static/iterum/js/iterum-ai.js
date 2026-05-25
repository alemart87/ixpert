/* Iterum AI Analyst — cliente SSE + render del chat + canvas en vivo. */

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
function mdToHtml(md) {
    if (!md) return '';
    let h = escapeHtml(md);
    // Headers
    h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    // Bold
    h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    h = h.replace(/(?<!\*)\*([^\*]+?)\*(?!\*)/g, '<em>$1</em>');
    // Code inline
    h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Lists
    h = h.replace(/^- (.+)$/gm, '<li>$1</li>');
    h = h.replace(/(<li>.*<\/li>\n?)+/g, m => '<ul>' + m + '</ul>');
    h = h.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');
    // Paragraphs (saltos de linea dobles)
    h = h.replace(/\n\n/g, '</p><p>');
    h = '<p>' + h + '</p>';
    h = h.replace(/<p>\s*<\/p>/g, '');
    // Tablas markdown simples
    h = h.replace(/\|(.+)\|/g, (m) => {
        const cells = m.slice(1, -1).split('|').map(c => `<td>${c.trim()}</td>`).join('');
        return `<tr>${cells}</tr>`;
    });
    h = h.replace(/(<tr>.*<\/tr>\n?)+/g, m => `<table class="ai-md-table">${m}</table>`);
    return h;
}

// ============================================================================
// API client
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
        if (!r.ok) throw new Error('chat no encontrado');
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
// Render chats sidebar
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
        </div>
    `).join('');
    el.querySelectorAll('.ai-chat-item').forEach(it => {
        it.addEventListener('click', () => loadChat(parseInt(it.dataset.id)));
    });
}

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return 'ahora';
    if (diff < 3600) return Math.floor(diff / 60) + ' min';
    if (diff < 86400) return Math.floor(diff / 3600) + ' h';
    return d.toLocaleDateString('es-PY');
}

// ============================================================================
// Load chat (mensajes + canvas)
// ============================================================================
async function loadChat(id) {
    State.currentChatId = id;
    const chat = await API.getChat(id);
    $('aiChatTitle').textContent = chat.title || 'Conversación';
    $('aiChatTokens').textContent = chat.total_tokens ? `${chat.total_tokens} tokens` : '';
    renderMessages(chat.messages);
    renderCanvas(chat.canvas);
    await loadChatsList();
}

function renderMessages(messages) {
    const el = $('aiMessages');
    if (!messages.length) {
        el.innerHTML = '<div class="ai-welcome"><h2>Conversación nueva</h2><p>Escribí algo para empezar.</p></div>';
        return;
    }
    el.innerHTML = '';
    messages.forEach(m => el.appendChild(renderMessage(m)));
    el.scrollTop = el.scrollHeight;
}

function renderMessage(m) {
    const div = document.createElement('div');
    div.className = `ai-msg ai-msg-${m.role}`;
    if (m.role === 'user') {
        div.innerHTML = `<div class="ai-msg-bubble ai-msg-user-bubble">${escapeHtml(m.content || '')}</div>`;
    } else if (m.role === 'assistant') {
        div.innerHTML = `<div class="ai-msg-avatar">🤖</div>
            <div class="ai-msg-bubble">${mdToHtml(m.content || '')}</div>`;
    } else if (m.role === 'reasoning') {
        div.innerHTML = `<details class="ai-reasoning">
            <summary>🧠 Razonamiento</summary>
            <div class="ai-reasoning-body">${escapeHtml(m.content || '')}</div>
        </details>`;
    } else if (m.role === 'tool_call') {
        const argsStr = m.tool_args ? JSON.stringify(m.tool_args, null, 2) : '';
        div.innerHTML = `<details class="ai-tool">
            <summary><span class="ai-tool-icon">🔧</span> ${escapeHtml(m.tool_name)}</summary>
            <pre class="ai-tool-body">${escapeHtml(argsStr)}</pre>
        </details>`;
    } else if (m.role === 'tool_output') {
        const resStr = m.tool_result ? JSON.stringify(m.tool_result, null, 2) : '';
        div.innerHTML = `<details class="ai-tool ai-tool-output">
            <summary><span class="ai-tool-icon">📥</span> Resultado de ${escapeHtml(m.tool_name || '')}</summary>
            <pre class="ai-tool-body">${escapeHtml(resStr.length > 4000 ? resStr.slice(0, 4000) + '...' : resStr)}</pre>
        </details>`;
    }
    return div;
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
    $('aiCanvasPreview').innerHTML = mdToHtml($('aiCanvas').value);
}

async function saveCanvasManually() {
    if (!State.currentChatId) return;
    await API.saveCanvas(State.currentChatId,
        $('aiCanvas').value, $('aiCanvasTitle').value);
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
// Streaming SSE de un mensaje nuevo
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

    // Hide welcome
    const welcome = document.querySelector('.ai-welcome');
    if (welcome) welcome.remove();

    // Append user message
    const userMsg = renderMessage({ role: 'user', content: text });
    $('aiMessages').appendChild(userMsg);

    // Placeholder assistant bubble where we stream into
    const assistDiv = document.createElement('div');
    assistDiv.className = 'ai-msg ai-msg-assistant';
    assistDiv.innerHTML = `<div class="ai-msg-avatar">🤖</div>
        <div class="ai-msg-bubble" id="aiStreamingBubble">
            <div class="ai-thinking-spinner"><span></span><span></span><span></span></div>
        </div>`;
    $('aiMessages').appendChild(assistDiv);

    let reasoningEl = null;
    let assistantText = '';
    let bubble = $('aiStreamingBubble');
    let spinnerVisible = true;

    function removeSpinner() {
        if (spinnerVisible) {
            const sp = bubble.querySelector('.ai-thinking-spinner');
            if (sp) sp.remove();
            spinnerVisible = false;
        }
    }

    // SSE via fetch streaming
    const resp = await fetch(`/iterum/api/ai/chats/${State.currentChatId}/message`, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
        body: JSON.stringify({ content: text }),
    });

    if (!resp.ok || !resp.body) {
        bubble.innerHTML = `<div class="ai-error">Error al iniciar el stream (${resp.status})</div>`;
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

        // SSE format: blocks separated by \n\n, each block has lines "event: X\ndata: Y"
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() || '';
        for (const block of blocks) {
            const lines = block.split('\n');
            let event = 'message';
            let data = '';
            for (const line of lines) {
                if (line.startsWith('event: ')) event = line.slice(7).trim();
                else if (line.startsWith('data: ')) data += line.slice(6);
            }
            if (!data) continue;
            let payload;
            try { payload = JSON.parse(data); } catch { continue; }
            handleSSE(event, payload, { bubble, getReasoningEl: () => reasoningEl,
                setReasoningEl: (e) => reasoningEl = e,
                appendAssistant: (delta) => { assistantText += delta; bubble.innerHTML = mdToHtml(assistantText); $('aiMessages').scrollTop = $('aiMessages').scrollHeight; },
                removeSpinner,
            });
        }
    }

    State.streaming = false;
    $('aiSend').disabled = false;
    loadChatsList();  // refresh title si fue auto-generado
}

function handleSSE(event, data, ctx) {
    if (event === 'user_msg') {
        // ya lo renderizamos optimista, ignoramos
    } else if (event === 'reasoning') {
        // Crear el details una sola vez, append delta al body
        let re = ctx.getReasoningEl();
        if (!re) {
            re = document.createElement('details');
            re.className = 'ai-reasoning ai-reasoning-streaming';
            re.open = true;
            re.innerHTML = '<summary>🧠 Razonamiento <span class="ai-pulse">●</span></summary><div class="ai-reasoning-body"></div>';
            ctx.bubble.parentElement.insertBefore(re, ctx.bubble);
            ctx.setReasoningEl(re);
            ctx.removeSpinner();
        }
        re.querySelector('.ai-reasoning-body').textContent += data.delta;
    } else if (event === 'tool_call') {
        ctx.removeSpinner();
        const el = document.createElement('details');
        el.className = 'ai-tool';
        el.innerHTML = `<summary><span class="ai-tool-icon">🔧</span> ${escapeHtml(data.name)} <span class="ai-pulse">●</span></summary>
            <pre class="ai-tool-body">${escapeHtml(JSON.stringify(data.args, null, 2))}</pre>`;
        ctx.bubble.parentElement.insertBefore(el, ctx.bubble);
    } else if (event === 'tool_output') {
        const el = document.createElement('details');
        el.className = 'ai-tool ai-tool-output';
        const out = data.result;
        const outStr = typeof out === 'string' ? out : JSON.stringify(out, null, 2);
        el.innerHTML = `<summary><span class="ai-tool-icon">📥</span> Resultado de ${escapeHtml(data.name || '')}</summary>
            <pre class="ai-tool-body">${escapeHtml(outStr.length > 4000 ? outStr.slice(0, 4000) + '...' : outStr)}</pre>`;
        ctx.bubble.parentElement.insertBefore(el, ctx.bubble);
    } else if (event === 'canvas_update') {
        $('aiCanvas').value = data.content_md || '';
        $('aiCanvasTitle').value = data.title || 'Workspace';
        $('aiCanvasVersion').textContent = `v${data.version}`;
        State.canvasVersion = data.version;
        updateCanvasPreview();
        flashCanvas();
    } else if (event === 'assistant_delta') {
        ctx.removeSpinner();
        // Close streaming reasoning indicator
        const re = ctx.getReasoningEl();
        if (re) {
            re.classList.remove('ai-reasoning-streaming');
            re.open = false;  // Auto-collapse when answer starts
            const pulse = re.querySelector('.ai-pulse');
            if (pulse) pulse.remove();
        }
        ctx.appendAssistant(data.delta);
    } else if (event === 'done') {
        // Limpiar pulses residuales
        document.querySelectorAll('.ai-pulse').forEach(p => p.remove());
        if (data.title) {
            $('aiChatTitle').textContent = data.title;
        }
    } else if (event === 'error') {
        ctx.bubble.innerHTML = `<div class="ai-error">⚠ Error: ${escapeHtml(data.error || 'desconocido')}</div>`;
    }
}

// ============================================================================
// Event handlers
// ============================================================================
async function init() {
    await loadChatsList();
    // Cargar la mas reciente si hay
    if (State.chats.length) {
        await loadChat(State.chats[0].id);
    }

    $('aiNewChat').addEventListener('click', async () => {
        const c = await API.createChat();
        await loadChatsList();
        await loadChat(c.id);
    });

    $('aiSend').addEventListener('click', sendMessage);
    $('aiInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    $('aiInput').addEventListener('input', (e) => {
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(160, e.target.scrollHeight) + 'px';
    });

    document.querySelectorAll('.ai-suggestion').forEach(b => {
        b.addEventListener('click', () => {
            $('aiInput').value = b.textContent.replace(/^[^\s]+\s/, '');
            $('aiInput').focus();
        });
    });

    $('aiCanvas').addEventListener('input', () => {
        State.canvasDirty = true;
        updateCanvasPreview();
    });
    $('aiCanvasSave').addEventListener('click', saveCanvasManually);
    $('aiRenameChat').addEventListener('click', async () => {
        if (!State.currentChatId) return;
        const newTitle = prompt('Nuevo título:', $('aiChatTitle').textContent);
        if (newTitle && newTitle.trim()) {
            await API.renameChat(State.currentChatId, newTitle.trim());
            $('aiChatTitle').textContent = newTitle.trim();
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
    $('aiToggleCanvas').addEventListener('click', () => {
        $('aiCanvasCol').classList.toggle('ai-canvas-hidden');
    });

    // Ctrl+S guarda canvas
    window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            saveCanvasManually();
        }
    });
}

init();
