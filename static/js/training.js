// Training Session Chat Logic
(function() {
    var sessionId = window.TRAINING_SESSION_ID;
    if (!sessionId) return;

    var messagesEl = document.getElementById('trainingMessages');
    var inputEl = document.getElementById('trainingInput');
    var sendBtn = document.getElementById('trainingSend');
    var endBtn = document.getElementById('trainingEnd');
    var typingEl = document.getElementById('trainingTyping');

    // Metrics elements
    var timerEl = document.getElementById('metricTimer');
    var wpmEl = document.getElementById('metricWpm');
    var msgsEl = document.getElementById('metricMsgs');

    var startTime = Date.now();
    var totalWords = 0;
    var totalMsgs = 0;
    var sending = false;

    // Timer update
    setInterval(function() {
        var elapsed = Math.floor((Date.now() - startTime) / 1000);
        var min = Math.floor(elapsed / 60);
        var sec = elapsed % 60;
        if (timerEl) timerEl.textContent = min + ':' + (sec < 10 ? '0' : '') + sec;
    }, 1000);

    // Send message
    sendBtn.addEventListener('click', sendMessage);
    inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // End session
    endBtn.addEventListener('click', async function() {
        if (!confirm('¿Terminar esta sesión de entrenamiento? Se generará la evaluación.')) return;
        endBtn.disabled = true;
        endBtn.textContent = 'Evaluando...';
        sendBtn.disabled = true;
        inputEl.disabled = true;

        try {
            var res = await fetch('/api/training/end/' + sessionId, { method: 'POST' });
            var data = await res.json();
            if (data.ok) {
                window.location.href = '/training/result/' + sessionId;
            } else {
                alert('Error: ' + (data.error || 'Error al finalizar'));
                endBtn.disabled = false;
                endBtn.textContent = 'Terminar Sesión';
                sendBtn.disabled = false;
                inputEl.disabled = false;
            }
        } catch (err) {
            alert('Error de conexión');
            endBtn.disabled = false;
            endBtn.textContent = 'Terminar Sesión';
            sendBtn.disabled = false;
            inputEl.disabled = false;
        }
    });

    function addMessage(role, content) {
        var div = document.createElement('div');
        div.className = 'training-msg ' + role;
        div.textContent = content;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    async function sendMessage() {
        var text = inputEl.value.trim();
        if (!text || sending) return;

        sending = true;
        inputEl.value = '';
        sendBtn.disabled = true;
        addMessage('user', text);

        totalWords += text.split(/\s+/).length;
        totalMsgs++;
        if (msgsEl) msgsEl.textContent = totalMsgs;

        // Update WPM
        var elapsed = (Date.now() - startTime) / 60000;
        if (elapsed > 0 && wpmEl) wpmEl.textContent = Math.round(totalWords / elapsed);

        // Show typing
        typingEl.classList.add('active');
        messagesEl.scrollTop = messagesEl.scrollHeight;

        try {
            var res = await fetch('/api/training/message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, message: text })
            });
            var data = await res.json();
            typingEl.classList.remove('active');

            if (data.error) {
                addMessage('client', 'Error: ' + data.error);
            } else {
                addMessage('client', data.response);
                // Update metrics from server
                if (data.metrics) {
                    if (wpmEl) wpmEl.textContent = Math.round(data.metrics.wpm || 0);
                }
            }
        } catch (err) {
            typingEl.classList.remove('active');
            addMessage('client', 'Error de conexión.');
        }

        sending = false;
        sendBtn.disabled = false;
        inputEl.focus();
    }
})();
