// Multi-Chat Training Session Manager
(function() {
    var batchId = window.BATCH_ID;
    var maxConcurrent = window.MAX_CONCURRENT || 1;
    if (!batchId) return;

    // State
    var interactions = {};  // session_id → {number, status, messages[], words, msgs}
    var activeSessionId = null;
    var startTime = Date.now();
    var addInterval = null;
    var spawnedCount = 0;

    // DOM
    var chatList = document.getElementById('chatList');
    var chatMessages = document.getElementById('chatMessages');
    var chatHeader = document.getElementById('chatHeader');
    var chatInput = document.getElementById('chatInput');
    var chatSend = document.getElementById('chatSend');
    var chatEnd = document.getElementById('chatEnd');
    var chatTyping = document.getElementById('chatTyping');
    var emojiBtn = document.getElementById('emojiBtn');
    var emojiPicker = document.getElementById('emojiPicker');

    // Emoji picker
    var emojis = ['😊','😃','😅','😂','🤔','👍','👋','🙏','💪','⭐','✅','❌','📋','🔍','💳','🏦','📞','📧','🔐','💰','⏳','🎯','❤️','🙂','😢','😡','🤝','👏','🔔','📌'];
    if (emojiPicker) {
        emojiPicker.innerHTML = emojis.map(function(e) { return '<span data-emoji="' + e + '">' + e + '</span>'; }).join('');
        emojiPicker.addEventListener('click', function(ev) {
            if (ev.target.dataset.emoji) {
                chatInput.value += ev.target.dataset.emoji;
                chatInput.focus();
            }
        });
    }
    if (emojiBtn) {
        emojiBtn.addEventListener('click', function() {
            emojiPicker.style.display = emojiPicker.style.display === 'none' ? 'flex' : 'none';
        });
        // Close picker when clicking outside
        document.addEventListener('click', function(e) {
            if (!emojiBtn.contains(e.target) && !emojiPicker.contains(e.target)) {
                emojiPicker.style.display = 'none';
            }
        });
    }

    // Initialize from server data
    (window.BATCH_INTERACTIONS || []).forEach(function(i) {
        interactions[i.session_id] = {
            number: i.interaction_number,
            status: i.status,
            messages: i.messages || [],
            words: 0, msgs: 0
        };
        spawnedCount++;
    });

    // Render sidebar
    function renderSidebar() {
        var ids = Object.keys(interactions).sort(function(a,b) {
            return interactions[a].number - interactions[b].number;
        });
        var completed = 0, active = 0;
        chatList.innerHTML = ids.map(function(sid) {
            var i = interactions[sid];
            var isActive = sid == activeSessionId;
            var statusIcon = i.status === 'completed' ? '✅' : '🟠';
            var lastMsg = i.messages.length ? i.messages[i.messages.length-1].content.substring(0, 40) + '...' : '';
            if (i.status === 'completed') completed++;
            else active++;
            return '<div class="chat-list-item ' + (isActive ? 'active' : '') + ' ' + i.status + '" data-sid="' + sid + '">' +
                '<div class="cli-header"><span class="cli-num">' + statusIcon + ' Chat ' + i.number + '</span></div>' +
                '<div class="cli-preview">' + lastMsg + '</div></div>';
        }).join('');

        // Add pending slots
        for (var p = spawnedCount + 1; p <= maxConcurrent; p++) {
            chatList.innerHTML += '<div class="chat-list-item pending"><div class="cli-header"><span class="cli-num">⏳ Chat ' + p + '</span></div><div class="cli-preview">Esperando ingreso...</div></div>';
        }

        // Click handlers
        chatList.querySelectorAll('.chat-list-item[data-sid]').forEach(function(el) {
            el.addEventListener('click', function() { selectChat(el.dataset.sid); });
        });

        // Stats
        document.getElementById('gResolved').textContent = completed + '/' + maxConcurrent;
        document.getElementById('gActive').textContent = active;
        document.getElementById('sidebarStats').innerHTML =
            '<div>✅ ' + completed + ' resueltas</div>' +
            '<div>🟢 ' + active + ' activas</div>' +
            '<div>⏳ ' + (maxConcurrent - spawnedCount) + ' pendientes</div>';

        // Check if all done
        if (completed === maxConcurrent && spawnedCount === maxConcurrent) {
            clearInterval(addInterval);
            chatHeader.textContent = '¡Todas las interacciones completadas!';
            chatMessages.innerHTML = '<div style="text-align:center;padding:40px;color:#888"><h3>Sesión finalizada</h3><p>Redirigiendo a resultados...</p></div>';
            document.getElementById('chatInputArea').style.display = 'none';
            setTimeout(function() {
                window.location.href = '/training/batch/' + batchId + '/result';
            }, 2000);
        }
    }

    function selectChat(sid) {
        activeSessionId = sid;
        var i = interactions[sid];
        chatHeader.textContent = 'Chat ' + i.number + (i.status === 'completed' ? ' (completado)' : '');
        chatMessages.innerHTML = '';
        i.messages.forEach(function(m) { addMsgToDOM(m.role, m.content); });
        chatMessages.scrollTop = chatMessages.scrollHeight;

        if (i.status === 'completed') {
            document.getElementById('chatInputArea').style.display = 'none';
        } else {
            document.getElementById('chatInputArea').style.display = 'flex';
            chatInput.focus();
        }
        renderSidebar();
    }

    function addMsgToDOM(role, content) {
        var div = document.createElement('div');
        div.className = 'training-msg ' + role;
        div.textContent = content;
        chatMessages.appendChild(div);
    }

    // Send message
    chatSend.addEventListener('click', sendMsg);
    chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); sendMsg(); }
    });

    async function sendMsg() {
        if (!activeSessionId) return;
        var i = interactions[activeSessionId];
        if (i.status !== 'active') return;
        var text = chatInput.value.trim();
        if (!text) return;

        chatInput.value = '';
        chatSend.disabled = true;
        i.messages.push({role: 'user', content: text});
        addMsgToDOM('user', text);
        chatTyping.classList.add('active');
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            var res = await fetch('/api/training/message', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({session_id: parseInt(activeSessionId), message: text})
            });
            var data = await res.json();
            chatTyping.classList.remove('active');
            if (data.response) {
                i.messages.push({role: 'client', content: data.response});
                addMsgToDOM('client', data.response);
            }
        } catch(e) {
            chatTyping.classList.remove('active');
            addMsgToDOM('client', 'Error de conexión.');
        }
        chatSend.disabled = false;
        chatInput.focus();
        renderSidebar();
    }

    // End individual interaction
    chatEnd.addEventListener('click', async function() {
        if (!activeSessionId || interactions[activeSessionId].status !== 'active') return;
        if (!confirm('¿Cerrar esta interacción? Se evaluará individualmente.')) return;

        chatEnd.disabled = true;
        chatEnd.textContent = 'Evaluando...';
        chatSend.disabled = true;

        try {
            var res = await fetch('/api/training/end/' + activeSessionId, {method: 'POST'});
            var data = await res.json();
            if (data.ok) {
                interactions[activeSessionId].status = 'completed';
                document.getElementById('chatInputArea').style.display = 'none';
                chatHeader.textContent = 'Chat ' + interactions[activeSessionId].number + ' ✅ Completado';
                renderSidebar();
                // If batch is fully complete, redirect to results
                if (data.batch_complete) {
                    setTimeout(function() {
                        window.location.href = '/training/batch/' + batchId + '/result';
                    }, 1500);
                }
            }
        } catch(e) { alert('Error al cerrar'); }
        chatEnd.disabled = false;
        chatEnd.textContent = 'Cerrar Interacción';
        chatSend.disabled = false;
    });

    // Timer
    setInterval(function() {
        var s = Math.floor((Date.now() - startTime) / 1000);
        document.getElementById('gTimer').textContent = Math.floor(s/60) + ':' + ('0' + s%60).slice(-2);
    }, 1000);

    // Progressive client spawn
    if (maxConcurrent > 1 && spawnedCount < maxConcurrent) {
        addInterval = setInterval(async function() {
            if (spawnedCount >= maxConcurrent) { clearInterval(addInterval); return; }
            try {
                var res = await fetch('/api/training/batch/' + batchId + '/add', {method: 'POST'});
                var data = await res.json();
                if (data.session_id) {
                    spawnedCount++;
                    interactions[data.session_id] = {
                        number: data.interaction_number,
                        status: 'active',
                        messages: [{role: 'client', content: data.first_message}],
                        words: 0, msgs: 0
                    };
                    renderSidebar();
                    // Notify user
                    var notif = document.createElement('div');
                    notif.style.cssText = 'position:fixed;top:20px;right:20px;background:#ff6600;color:#fff;padding:12px 20px;border-radius:12px;z-index:9999;animation:msgFadeIn 0.3s';
                    notif.textContent = '🔔 Nuevo cliente #' + data.interaction_number + ' ingresó';
                    document.body.appendChild(notif);
                    setTimeout(function() { notif.remove(); }, 3000);
                }
            } catch(e) {}
        }, 20000); // New client every 20 seconds
    }

    // Init: select first active chat
    var firstActive = Object.keys(interactions).find(function(sid) { return interactions[sid].status === 'active'; });
    if (firstActive) selectChat(firstActive);
    renderSidebar();
})();
