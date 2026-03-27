// iXpert AI Chat Widget
(function() {
    let currentConvId = null;
    let isOpen = false;
    let convsVisible = false;

    const panel = document.getElementById('chatPanel');
    const mascot = document.getElementById('chatMascot');
    const messagesEl = document.getElementById('chatMessages');
    const inputEl = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSend');
    const typingEl = document.getElementById('chatTyping');
    const convsEl = document.getElementById('chatConvs');
    const newChatBtn = document.getElementById('chatNew');
    const historyBtn = document.getElementById('chatHistory');
    const closeBtn = document.getElementById('chatClose');

    if (!mascot) return;

    // Toggle chat panel
    mascot.addEventListener('click', function() {
        isOpen = !isOpen;
        panel.classList.toggle('open', isOpen);
        mascot.classList.toggle('chat-open', isOpen);
        if (isOpen && !currentConvId) showWelcome();
    });

    closeBtn.addEventListener('click', function() {
        isOpen = false;
        panel.classList.remove('open');
        mascot.classList.remove('chat-open');
    });

    // New conversation
    newChatBtn.addEventListener('click', function() {
        currentConvId = null;
        convsEl.classList.remove('open');
        convsVisible = false;
        showWelcome();
    });

    // Toggle history
    historyBtn.addEventListener('click', function() {
        convsVisible = !convsVisible;
        if (convsVisible) {
            loadConversations();
            convsEl.classList.add('open');
        } else {
            convsEl.classList.remove('open');
        }
    });

    // Send message
    sendBtn.addEventListener('click', sendMessage);
    inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    function showWelcome() {
        messagesEl.innerHTML = '<div class="chat-welcome">' +
            '<h4>Hola! Soy iXpert AI</h4>' +
            '<p>Tu asistente virtual. Preguntame sobre cualquier tema de la plataforma y te ayudo con información y links directos.</p>' +
            '</div>';
    }

    function addMessage(role, content) {
        // Remove welcome if present
        var welcome = messagesEl.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        var div = document.createElement('div');
        div.className = 'chat-msg ' + role;

        // Parse markdown links [text](url) to HTML
        var html = content
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
        div.innerHTML = html;

        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    async function sendMessage() {
        var text = inputEl.value.trim();
        if (!text) return;

        inputEl.value = '';
        sendBtn.disabled = true;
        addMessage('user', text);

        // Show typing
        typingEl.classList.add('active');
        messagesEl.scrollTop = messagesEl.scrollHeight;

        try {
            var res = await fetch('/api/chat/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    conversation_id: currentConvId
                })
            });
            var data = await res.json();

            typingEl.classList.remove('active');

            if (data.error) {
                addMessage('assistant', 'Error: ' + data.error);
            } else {
                currentConvId = data.conversation_id;
                addMessage('assistant', data.message);
            }
        } catch (err) {
            typingEl.classList.remove('active');
            addMessage('assistant', 'Error de conexión. Intenta de nuevo.');
        }

        sendBtn.disabled = false;
        inputEl.focus();
    }

    async function loadConversations() {
        try {
            var res = await fetch('/api/chat/conversations');
            var convs = await res.json();

            if (convs.length === 0) {
                convsEl.innerHTML = '<div style="padding:16px;text-align:center;color:#888;font-size:13px">Sin conversaciones previas</div>';
                return;
            }

            convsEl.innerHTML = convs.map(function(c) {
                return '<div class="chat-conv-item" data-id="' + c.id + '">' +
                    '<span class="conv-title">' + escapeHtml(c.title) + '</span>' +
                    '<button class="conv-delete" data-id="' + c.id + '" title="Eliminar">&times;</button>' +
                    '</div>';
            }).join('');

            // Click to load conversation
            convsEl.querySelectorAll('.chat-conv-item').forEach(function(el) {
                el.addEventListener('click', function(e) {
                    if (e.target.classList.contains('conv-delete')) return;
                    loadConversation(parseInt(el.dataset.id));
                });
            });

            // Delete buttons
            convsEl.querySelectorAll('.conv-delete').forEach(function(btn) {
                btn.addEventListener('click', async function(e) {
                    e.stopPropagation();
                    if (!confirm('¿Eliminar esta conversación?')) return;
                    await fetch('/api/chat/conversations/' + btn.dataset.id, { method: 'DELETE' });
                    if (currentConvId == btn.dataset.id) {
                        currentConvId = null;
                        showWelcome();
                    }
                    loadConversations();
                });
            });
        } catch (err) {
            convsEl.innerHTML = '<div style="padding:16px;color:#888">Error al cargar</div>';
        }
    }

    async function loadConversation(convId) {
        try {
            var res = await fetch('/api/chat/conversations/' + convId);
            var data = await res.json();

            currentConvId = convId;
            messagesEl.innerHTML = '';
            convsEl.classList.remove('open');
            convsVisible = false;

            data.messages.forEach(function(m) {
                addMessage(m.role, m.content);
            });
        } catch (err) {
            addMessage('assistant', 'Error al cargar la conversación.');
        }
    }

    function escapeHtml(text) {
        var d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }
})();
