/**
 * Voice Chat Resume Builder - ADHD Optimized
 * Conversational interface with Back/Add buttons, micro-questions
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
    const contextLabel = document.getElementById('context-label');
    const navButtons = document.getElementById('nav-buttons');
    const backBtn = document.getElementById('back-btn');
    const addBtn = document.getElementById('add-btn');

    // State
    let sessionId = null;
    let isRecording = false;
    let recognition = null;
    let accumulatedFinal = '';
    let currentStepIndex = 0;
    let totalSteps = 9; // Approximate for progress bar
    let canGoBack = false;
    let isDecisionPoint = false;

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
        
        // Clear button
        const clearBtn = document.getElementById('clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                textInput.value = '';
                accumulatedFinal = '';
                textInput.focus();
            });
        }

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

        // Navigation buttons
        if (backBtn) {
            backBtn.addEventListener('click', goBack);
        }
        if (addBtn) {
            addBtn.addEventListener('click', addAnother);
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
            
            if (newFinal) {
                accumulatedFinal += newFinal;
            }
            
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
            if (textInput.value.trim()) {
                sendMessage();
            }
        } else {
            startRecording();
        }
    }

    function startRecording() {
        if (!recognition) return;
        // Clear previous transcript so each question starts fresh
        accumulatedFinal = '';
        textInput.value = '';
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

    // Navigation Actions
    async function goBack() {
        if (!sessionId || !canGoBack) return;
        
        textInput.disabled = true;
        sendBtn.disabled = true;
        showTyping();

        try {
            const response = await fetch('/api/voice/turn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, transcript: '', action: 'back' })
            });
            const data = await response.json();
            hideTyping();

            if (data.error) {
                addMessage('ai', 'Sorry: ' + data.error, false);
            } else {
                // Remove the last user message from chat
                removeLastUserMessage();
                
                // Show re-ask
                addMessage('ai', data.question, false);
                clearInput(data.field === '_bullet');
                updateProgress(data.step_index);
                updateContextLabel(data.context_label);
                updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                updateBulletUI(data);
            }
        } catch (e) {
            hideTyping();
            console.error('Back error:', e);
        } finally {
            textInput.disabled = false;
            sendBtn.disabled = false;
            textInput.focus();
        }
    }

    async function addAnother() {
        if (!sessionId) return;
        
        textInput.disabled = true;
        sendBtn.disabled = true;
        showTyping();

        try {
            const response = await fetch('/api/voice/turn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, transcript: '', action: 'add' })
            });
            const data = await response.json();
            hideTyping();

            if (data.error) {
                addMessage('ai', 'Sorry: ' + data.error, false);
            } else {
                addMessage('ai', data.question, false);
                clearInput(data.field === '_bullet');
                updateProgress(data.step_index);
                updateContextLabel(data.context_label);
                updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                updateBulletUI(data);
            }
        } catch (e) {
            hideTyping();
            console.error('Add error:', e);
        } finally {
            textInput.disabled = false;
            sendBtn.disabled = false;
            textInput.focus();
        }
    }

    function removeLastUserMessage() {
        const messages = chatMessages.querySelectorAll('.user-message');
        if (messages.length > 0) {
            messages[messages.length - 1].remove();
        }
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
            currentStepIndex = data.step_index || 0;
            
            // Clear welcome and show first question
            const welcome = document.getElementById('welcome-message');
            if (welcome) welcome.remove();
            
            addMessage('ai', data.question, false);
            clearInput(data.field === '_bullet');
            updateProgress(currentStepIndex);
            updateContextLabel(data.context_label);
            updateNavButtons(data.can_go_back, data.field, data.show_add_job);
            updateBulletUI(data);
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
        accumulatedFinal = '';
        textInput.disabled = true;
        sendBtn.disabled = true;

        showTyping();

        try {
            const response = await fetch('/api/voice/turn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, transcript: text, action: 'answer' })
            });
            const data = await response.json();
            hideTyping();

            if (data.error) {
                addMessage('ai', 'Sorry: ' + data.error + '. Please try again.', false);
            } else {
                addMessage('ai', data.question, false);
                clearInput(data.field === '_bullet');
                updateProgress(data.step_index);
                updateContextLabel(data.context_label);
                updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                updateBulletUI(data);

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
    function clearInput(addBulletPrefix) {
        textInput.value = addBulletPrefix ? '• ' : '';
        accumulatedFinal = '';
    }

    function updateBulletUI(data) {
        const helperText = document.getElementById('helper-text');
        const isFirstBullet = data.is_first_bullet;
        const isBulletField = data.field === '_bullet';
        const bulletCount = data.bullet_count || 0;
        const jobCount = data.job_count || 0;
        
        // Show helper text only on first bullet of each job
        if (helperText) {
            if (isFirstBullet && isBulletField) {
                helperText.textContent = `Say one descriptive sentence explaining one task you did at Job ${jobCount}, then press send.`;
                helperText.classList.remove('hidden');
            } else {
                helperText.classList.add('hidden');
            }
        }
        
        // Pre-fill bullet prefix for all bullet fields
        if (isBulletField) {
            clearInput(true);
        }
        
        // Update add button label for bullets
        if (isBulletField && addBtn) {
            addBtn.textContent = bulletCount > 1 ? `+ Add bullet ${bulletCount + 1}` : '+ Add bullet 2';
        } else if (data.field === '_decision') {
            addBtn.textContent = '+ Add Another';
        }
    }

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

    function updateProgress(stepIndex) {
        currentStepIndex = stepIndex;
        const pct = Math.min(Math.round((stepIndex / totalSteps) * 100), 100);
        progressFill.style.width = pct + '%';
        progressText.textContent = pct + '%';
    }

    function updateContextLabel(label) {
        if (!label) {
            contextLabel.classList.add('hidden');
            return;
        }
        contextLabel.textContent = label;
        contextLabel.classList.remove('hidden');
    }

    function updateNavButtons(canBack, field, showAddJob) {
        canGoBack = canBack;
        
        // Show nav buttons if we can go back or if this is a loop field
        const isLoopField = field && !field.startsWith('_') && 
            (field === 'company' || field === 'title' || field === 'school' || 
             field === 'degree' || field === 'project_name' || field === 'competency' ||
             field === 'community_org' || field === 'cert_name');
        
        const isDecisionPoint = field === '_decision';
        const isBulletField = field === '_bullet';
        const inExperience = isLoopField || isBulletField || showAddJob;
        
        if (canBack || isLoopField || isDecisionPoint || isBulletField || showAddJob) {
            navButtons.classList.remove('hidden');
        } else {
            navButtons.classList.add('hidden');
        }
        
        // Show/hide individual buttons
        backBtn.style.display = canBack ? 'inline-block' : 'none';
        
        // Show add button at decision points, loop fields, or when show_add_job is true
        if (isDecisionPoint || isLoopField || isBulletField || showAddJob) {
            addBtn.style.display = 'inline-block';
            if (isDecisionPoint) {
                addBtn.textContent = '+ Add Another';
            } else if (inExperience) {
                addBtn.textContent = '+ Add Job';
            }
        } else {
            addBtn.style.display = 'none';
        }
    }

    function showViewResumeButton() {
        micBtn.style.display = 'none';
        textInput.style.display = 'none';
        sendBtn.style.display = 'none';
        navButtons.style.display = 'none';

        const btn = document.createElement('a');
        btn.href = `/build?mode=form&voice_session=${sessionId}`;
        btn.className = 'view-resume-btn';
        btn.textContent = '👁️ View Your Resume';
        document.querySelector('.voice-chat-container').appendChild(btn);

        addMessage('ai', 'Great! Your resume is ready. Click below to preview and purchase.', false);
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
