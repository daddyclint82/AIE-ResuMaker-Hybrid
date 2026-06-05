/**
 * Voice Chat Resume Builder
 * Conversational interface with SpeechRecognition + text fallback
 */

(function() {
    // DOM Elements
    const chatMessages = document.getElementById('chat-messages');
    const textInput = document.getElementById('text-input');
    const sendBtn = document.getElementById('send-btn');
    const micBtn = document.getElementById('mic-btn');
    const recordingStatus = document.getElementById('recording-status');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');

    // State
    let sessionId = null;
    let isRecording = false;
    let recognition = null;
    const totalQuestions = 12;

    // Initialize
    init();

    function init() {
        // Check speech support
        if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
            setupSpeechRecognition();
        } else {
            micBtn.style.display = 'none';
        }

        // Bind events
        sendBtn.addEventListener('click', sendMessage);
        textInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
        micBtn.addEventListener('click', toggleRecording);
        
        // Mode toggle
        const modeToggle = document.getElementById('mode-toggle');
        if (modeToggle) {
            modeToggle.addEventListener('click', () => {
                const url = sessionId 
                    ? `/build?mode=form&voice_session=${sessionId}`
                    : '/build?mode=form';
                localStorage.setItem('aie_mode', 'form');
                window.location.href = url;
            });
        }

        // Start session
        startSession();
    }

    // Speech Recognition
    function setupSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        // Accumulated transcript storage
        let accumulatedFinal = '';
        
        recognition.onresult = (event) => {
            let newFinal = '';
            let interimTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    newFinal += transcript + ' ';
                } else {
                    interimTranscript = transcript;
                }
            }
            
            // Append new finalized text to accumulated buffer
            if (newFinal) {
                accumulatedFinal += newFinal;
            }
            
            // Show accumulated + current interim
            textInput.value = (accumulatedFinal + interimTranscript).trim();
        };

        recognition.onerror = (event) => {
            console.error('Speech error:', event.error);
            stopRecording();
            if (event.error === 'not-allowed') {
                addMessage('ai', 'Microphone access denied. Please allow mic permission or type your answer.', false);
            }
        };

        recognition.onend = () => {
            if (isRecording) {
                try { recognition.start(); } catch(e) {}
            }
        };
    }

    function toggleRecording() {
        if (isRecording) {
            stopRecording();
            // Auto-send if we got text
            if (textInput.value.trim()) {
                sendMessage();
            }
        } else {
            startRecording();
        }
    }

    function startRecording() {
        if (!recognition) return;
        try {
            recognition.start();
            isRecording = true;
            micBtn.classList.add('recording');
            recordingStatus.classList.remove('hidden');
            textInput.placeholder = 'Listening... speak now';
        } catch (e) {
            console.error('Start recording failed:', e);
        }
    }

    function stopRecording() {
        if (!recognition) return;
        try { recognition.stop(); } catch (e) {}
        isRecording = false;
        micBtn.classList.remove('recording');
        recordingStatus.classList.add('hidden');
        textInput.placeholder = 'Type your answer...';
    }

    // API Calls
    async function startSession() {
        try {
            showTyping();
            const response = await fetch('/api/voice/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            hideTyping();

            sessionId = data.session_id;
            addMessage('ai', data.question, false);
            updateProgress(data.turn);
        } catch (e) {
            hideTyping();
            addMessage('ai', 'Sorry, something went wrong. Please refresh and try again.', false);
            console.error('Start session error:', e);
        }
    }

    async function sendMessage() {
        const text = textInput.value.trim();
        if (!text || !sessionId) return;

        // Stop recording if active
        if (isRecording) stopRecording();

        // Add user message
        addMessage('user', text, true);
        textInput.value = '';
        textInput.disabled = true;
        sendBtn.disabled = true;

        showTyping();

        try {
            const response = await fetch('/api/voice/turn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, transcript: text })
            });
            const data = await response.json();
            hideTyping();

            if (data.error) {
                addMessage('ai', 'Sorry: ' + data.error + '. Please try again.', false);
            } else {
                addMessage('ai', data.question, false);
                updateProgress(data.turn);
                
                // Clear input and accumulated text for next question
                textInput.value = '';
                accumulatedFinal = '';

                // Show done state
                if (data.done) {
                    showViewResumeButton();
                }
            }
        } catch (e) {
            hideTyping();
            addMessage('ai', 'Sorry, I had trouble with that. Please try again.', false);
            console.error('Turn error:', e);
        } finally {
            textInput.disabled = false;
            sendBtn.disabled = false;
            textInput.focus();
        }
    }

    // UI Helpers
    function addMessage(type, text, isUser) {
        const div = document.createElement('div');
        div.className = `message ${type}-message`;
        div.innerHTML = `
            <div class="message-bubble">${escapeHtml(text)}</div>
            <div class="message-time">${formatTime()}</div>
        `;
        chatMessages.appendChild(div);
        scrollToBottom();
    }

    function showTyping() {
        const div = document.createElement('div');
        div.id = 'typing-indicator';
        div.className = 'message ai-message';
        div.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
        chatMessages.appendChild(div);
        scrollToBottom();
    }

    function hideTyping() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    }

    function updateProgress(turn) {
        const pct = Math.min(Math.round((turn / totalQuestions) * 100), 100);
        progressFill.style.width = pct + '%';
        progressText.textContent = pct + '%';
    }

    function showViewResumeButton() {
        micBtn.style.display = 'none';
        textInput.style.display = 'none';
        sendBtn.style.display = 'none';

        const btn = document.createElement('a');
        btn.href = `/build?mode=form&voice_session=${sessionId}`;
        btn.className = 'view-resume-btn';
        btn.textContent = '👁️ View Your Resume';
        document.querySelector('.voice-chat-container').appendChild(btn);

        addMessage('ai', 'Great! Your resume is ready. Click the button below to preview and purchase.', false);
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatTime() {
        const now = new Date();
        return now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }
})();
