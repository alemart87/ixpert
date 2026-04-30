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

    // DOM — use train* IDs to avoid conflict with chat widget
    var chatList = document.getElementById('trainList');
    var chatMessages = document.getElementById('trainChatMessages');
    var chatHeader = document.getElementById('trainHeader');
    var chatInput = document.getElementById('trainInput');
    var chatSend = document.getElementById('trainSend');
    var chatEnd = document.getElementById('trainEnd');
    var chatTyping = document.getElementById('trainTyping');
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
            document.getElementById('trainInputArea').style.display = 'none';
            setTimeout(function() {
                window.location.href = '/training/batch/' + batchId + '/result';
            }, 2000);
        }
    }

    function selectChat(sid) {
        // Limpiar indicador de "cliente leyendo" del chat que estamos dejando
        var prev = document.getElementById('clientWaiting');
        if (prev) prev.remove();

        activeSessionId = sid;
        var i = interactions[sid];
        chatHeader.textContent = 'Chat ' + i.number + (i.status === 'completed' ? ' ✅ Completado' : '');
        renderChat(sid);

        if (i.status === 'completed') {
            document.getElementById('trainInputArea').style.display = 'none';
        } else {
            document.getElementById('trainInputArea').style.display = 'flex';
            chatInput.focus();
        }

        // Si el chat al que entramos tiene countdown activo, mostrar el indicador
        var t = flushTimers && flushTimers[sid];
        if (t && t.deadline) {
            var remaining = Math.max(0, Math.ceil((t.deadline - Date.now()) / 1000));
            updateClientWaitingUI(sid, remaining);
        }

        renderSidebar();
    }

    function addMsgToDOM(role, content) {
        var typing = document.getElementById('trainTyping');
        var div = document.createElement('div');
        div.className = 'training-msg ' + role;
        div.textContent = content;
        // Insert before typing indicator
        if (typing) chatMessages.insertBefore(div, typing);
        else chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function renderChat(sid) {
        /**Re-render the chat area from the interaction state (source of truth).**/
        var i = interactions[sid];
        if (!i) return;
        // Remove all messages but keep typing indicator
        var typing = document.getElementById('trainTyping');
        chatMessages.innerHTML = '';
        if (typing) chatMessages.appendChild(typing);
        // Re-add all messages from state
        i.messages.forEach(function(m) {
            var div = document.createElement('div');
            div.className = 'training-msg ' + m.role;
            div.textContent = m.content;
            if (typing) chatMessages.insertBefore(div, typing);
            else chatMessages.appendChild(div);
        });
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Auto-resize del textarea: crece con el contenido hasta el max-height del CSS.
    function autoResize() {
        if (!chatInput) return;
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + 'px';
    }
    chatInput.addEventListener('input', autoResize);

    // Send message — Enter envia; Shift+Enter inserta salto de linea.
    chatSend.addEventListener('click', sendMsg);
    chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMsg();
        }
    });

    // ===== Debounce flow: encolar -> esperar N segundos -> flush =====
    var DEFAULT_DELAY = (window.CLIENT_DELAY_SECONDS && window.CLIENT_DELAY_SECONDS > 0)
        ? window.CLIENT_DELAY_SECONDS : 30;
    var flushTimers = {};      // sid -> { intervalId, deadline, remaining }
    var flushInFlight = {};    // sid -> bool

    async function sendMsg() {
        if (!activeSessionId) return;
        var sendingSid = activeSessionId;
        var i = interactions[sendingSid];
        if (i.status !== 'active') return;
        var text = chatInput.value.trim();
        if (!text) return;

        chatInput.value = '';
        autoResize();
        chatSend.disabled = true;
        i.messages.push({role: 'user', content: text});
        addMsgToDOM('user', text);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // 1) Persistir en backend (sin disparar IA)
        var delayUsed = DEFAULT_DELAY;
        try {
            var res = await fetch('/api/training/queue', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({session_id: parseInt(sendingSid), message: text})
            });
            var data = await res.json();
            if (data && data.client_response_delay_seconds) {
                delayUsed = parseInt(data.client_response_delay_seconds, 10) || DEFAULT_DELAY;
            }
        } catch(e) { /* el mensaje ya esta en UI; el flush volvera a intentar */ }

        chatSend.disabled = false;
        if (activeSessionId == sendingSid) chatInput.focus();

        // 2) (Re)iniciar countdown para esta sesion
        startFlushCountdown(sendingSid, delayUsed);
        renderSidebar();
        return;
    }

    // Inicia o reinicia el countdown de "cliente leyendo" para una sesion.
    // Cada nuevo mensaje del asesor lo reinicia (debounce).
    function startFlushCountdown(sid, delaySeconds) {
        cancelFlushCountdown(sid);
        var deadline = Date.now() + delaySeconds * 1000;
        var entry = { deadline: deadline, intervalId: null };
        flushTimers[sid] = entry;

        function tick() {
            var remaining = Math.max(0, Math.ceil((entry.deadline - Date.now()) / 1000));
            updateClientWaitingUI(sid, remaining);
            if (remaining <= 0) {
                clearInterval(entry.intervalId);
                delete flushTimers[sid];
                triggerFlush(sid);
            }
        }
        tick(); // pinta inmediato
        entry.intervalId = setInterval(tick, 1000);
    }

    function cancelFlushCountdown(sid) {
        var t = flushTimers[sid];
        if (t && t.intervalId) clearInterval(t.intervalId);
        delete flushTimers[sid];
        hideClientWaitingUI(sid);
    }

    async function triggerFlush(sid) {
        if (flushInFlight[sid]) {
            // Si ya hay un flush en vuelo, reprogramar para despues.
            // Cuando termine el flush en curso, el JS volvera a evaluar pendientes.
            startFlushCountdown(sid, 2);
            return;
        }
        flushInFlight[sid] = true;
        hideClientWaitingUI(sid);
        // Mostrar typing solo si el chat activo es este
        if (activeSessionId == sid) chatTyping.classList.add('active');

        try {
            var res = await fetch('/api/training/flush', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({session_id: parseInt(sid)})
            });
            var data = await res.json();
            if (activeSessionId == sid) chatTyping.classList.remove('active');

            if (data && data.response) {
                var i = interactions[sid];
                if (i) {
                    i.messages.push({role: 'client', content: data.response});
                    if (activeSessionId == sid) {
                        addMsgToDOM('client', data.response);
                        chatMessages.scrollTop = chatMessages.scrollHeight;
                    }
                }
            }
        } catch(e) {
            if (activeSessionId == sid) {
                chatTyping.classList.remove('active');
                addMsgToDOM('client', 'Error de conexión. Probá enviar otro mensaje.');
            }
        } finally {
            flushInFlight[sid] = false;
            renderSidebar();
        }
    }

    // UI auxiliar: indicador "💭 Cliente leyendo... 28s"
    function getOrCreateWaitingEl(sid) {
        if (activeSessionId != sid) return null;
        var el = document.getElementById('clientWaiting');
        if (!el) {
            el = document.createElement('div');
            el.id = 'clientWaiting';
            el.className = 'client-waiting';
            el.innerHTML = '<span class="cw-dot"></span><span class="cw-text"></span>';
            chatMessages.appendChild(el);
        }
        return el;
    }
    function updateClientWaitingUI(sid, remaining) {
        var el = getOrCreateWaitingEl(sid);
        if (!el) return;
        var txt = el.querySelector('.cw-text');
        txt.textContent = 'Cliente está leyendo y respondiendo… ' + remaining + 's';
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    function hideClientWaitingUI(sid) {
        if (activeSessionId != sid) return;
        var el = document.getElementById('clientWaiting');
        if (el) el.remove();
    }

    // End individual interaction
    chatEnd.addEventListener('click', async function() {
        if (!activeSessionId || interactions[activeSessionId].status !== 'active') return;
        var closingSid = activeSessionId;  // Capture BEFORE confirm/async
        var closingNum = interactions[closingSid].number;
        if (!confirm('¿Cerrar Chat ' + closingNum + '? Se evaluará individualmente.')) return;

        // Si habia un countdown corriendo, cancelarlo: la sesion se va a evaluar.
        cancelFlushCountdown(closingSid);

        chatEnd.disabled = true;
        chatEnd.textContent = 'Evaluando Chat ' + closingNum + '...';
        chatSend.disabled = true;

        try {
            var res = await fetch('/api/training/end/' + closingSid, {method: 'POST'});
            var data = await res.json();
            if (data.ok) {
                interactions[closingSid].status = 'completed';
                // Only update UI if user is still viewing the closed chat
                if (activeSessionId == closingSid) {
                    document.getElementById('trainInputArea').style.display = 'none';
                    chatHeader.textContent = 'Chat ' + closingNum + ' ✅ Completado';
                }
                renderSidebar();
                // If batch is fully complete, redirect to results
                if (data.batch_complete) {
                    setTimeout(function() {
                        window.location.href = '/training/batch/' + batchId + '/result';
                    }, 1500);
                }
            }
        } catch(e) { alert('Error al cerrar Chat ' + closingNum); }
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
