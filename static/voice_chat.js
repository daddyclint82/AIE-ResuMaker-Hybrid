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
    const doneJobsBtn = document.getElementById('done-jobs-btn');
    const saveBtn = document.getElementById('save-btn');

    // 42 Skill Categories (all tiers)
    const ALL_SKILL_CATEGORIES = [
        "Programming & Development",
        "Frameworks & Libraries", 
        "Databases & Data Storage",
        "Cloud & Infrastructure",
        "DevOps & Automation",
        "AI/ML & Data Science",
        "Cybersecurity",
        "Testing & Quality Assurance",
        "Mobile Development",
        "Embedded Systems",
        "Welding & Metalwork",
        "Electrical Systems",
        "Plumbing & Pipefitting",
        "HVAC & Refrigeration",
        "Carpentry & Woodworking",
        "Masonry & Concrete",
        "Heavy Equipment Operation",
        "Machining & Manufacturing",
        "Automotive & Mechanical",
        "Agriculture & Landscaping",
        "Project & Program Management",
        "Financial & Accounting",
        "Sales & Business Development",
        "Marketing & Communications",
        "HR & Talent Management",
        "Legal & Compliance",
        "Research & Analysis",
        "Administrative & Operations",
        "Healthcare & Medical",
        "Education & Training",
        "Customer Service & Hospitality",
        "Counseling & Social Work",
        "Food Service & Culinary",
        "Design & Visual Arts",
        "Writing & Content",
        "Media & Broadcasting",
        "Music & Performing Arts",
        "Sports & Fitness",
        "Safety & Risk Management",
        "Environmental & Sustainability",
        "Quality Control & Inspection",
        "Security & Surveillance",
        "Other Skills"
    ];
    let sessionId = null;
    let isRecording = false;
    let recognition = null;
    let accumulatedFinal = '';
    let currentStepIndex = 0;
    let totalSteps = 12;
    let canGoBack = false;
    let currentField = '';
    let currentSkillsCategorized = {};
    let skillsPanelExpanded = false;
    let lastQuestion = '';
    let lastUserMessage = '';

    // Initialize
    init();

    function init() {
        // Check for saved session
        checkForSavedSession();

        // Check speech support
        if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
            setupSpeechRecognition();
        } else {
            if (micBtn) micBtn.style.display = 'none';
        }

        // Bind events
        if (sendBtn) {
            sendBtn.addEventListener('click', sendMessage);
        }
        if (textInput) {
            textInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') sendMessage();
            });
        }
        if (micBtn) {
            micBtn.addEventListener('click', toggleRecording);
        }
        
        // Clear button
        const clearBtn = document.getElementById('clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                if (textInput) textInput.value = '';
                accumulatedFinal = '';
                if (textInput) textInput.focus();
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
        if (doneJobsBtn) {
            doneJobsBtn.addEventListener('click', finishJobs);
        }
        if (saveBtn) {
            saveBtn.addEventListener('click', saveProgress);
        }

        // UNIVERSAL OVERRIDE: Container-anchored "COMPILE RESUME NOW" button in header
        const compileBtn = document.createElement('button');
        compileBtn.id = 'universal-compile-btn';
        compileBtn.textContent = '⚙️ COMPILE RESUME NOW';
        compileBtn.style.cssText = 'position:absolute!important;top:12px!important;right:16px!important;padding:6px 14px!important;background:#FF4D4D!important;color:#FFFFFF!important;border:none!important;border-radius:20px!important;font-size:13px!important;font-weight:700!important;cursor:pointer!important;z-index:999!important;box-shadow:0 2px 4px rgba(0,0,0,0.1)!important;';

        compileBtn.addEventListener('click', async () => {
            if (!sessionId) {
                alert('Please wait for the session to start.');
                return;
            }
            // GUARD: confirm before finalizing — prevents stray taps from ending the session early
            if (!confirm('Compile your resume now? This finalizes your answers and ends the questionnaire. You can keep editing in the form afterward.')) {
                return;
            }
            compileBtn.textContent = '⏳ Compiling...';
            compileBtn.disabled = true;

            try {
                const response = await fetch('/api/voice/turn', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId, transcript: '', action: 'universal_force_compile' })
                });
                const data = await response.json();
                if (data.error) {
                    alert('Error: ' + data.error);
                    compileBtn.textContent = '⚙️ COMPILE RESUME NOW';
                    compileBtn.disabled = false;
                } else {
                    window.location.href = `/build?mode=form&voice_session=${window.sessionId || ''}`;
                }
            } catch (e) {
                console.error('Compile error:', e);
                compileBtn.textContent = '⚙️ COMPILE RESUME NOW';
                compileBtn.disabled = false;
            }
        });

        // Mount into .chat-header with relative positioning context
        const chatHeader = document.querySelector('.chat-header');
        if (chatHeader) {
            chatHeader.style.position = 'relative';
            chatHeader.appendChild(compileBtn);
        } else {
            // Fallback: mount into .voice-chat-container with relative positioning
            const chatContainer = document.querySelector('.voice-chat-container');
            if (chatContainer) {
                chatContainer.style.position = 'relative';
                chatContainer.appendChild(compileBtn);
            } else {
                // Emergency fallback to body with fixed positioning
                compileBtn.style.cssText = 'position:fixed!important;top:20px!important;right:20px!important;padding:6px 14px!important;background:#FF4D4D!important;color:#FFFFFF!important;border:none!important;border-radius:20px!important;font-size:13px!important;font-weight:700!important;cursor:pointer!important;z-index:999!important;box-shadow:0 2px 4px rgba(0,0,0,0.1)!important;';
                document.body.appendChild(compileBtn);
            }
        }
    }

    // ===== SAVE / LOAD =====

    async function checkForSavedSession() {
        // Attempt transcript rehydration from server before starting fresh
        const priorSid = localStorage.getItem('aie_voice_sid');
        if (priorSid) {
            try {
                const r = await fetch(`/api/voice/session-history?sessionId=${encodeURIComponent(priorSid)}`);
                if (r.ok) {
                    const payload = await r.json();
                    const hist = Array.isArray(payload.history) ? payload.history : [];
                    if (hist.length > 0) {
                        sessionId = priorSid;
                        window.sessionId = priorSid;
                        hist.forEach(m => addMessage(m.role === 'user' ? 'user' : 'ai', m.text, m.role === 'user'));
                        scrollToBottom();
                        return; // rehydrated — do not start a new session
                    }
                }
            } catch (e) {
                console.warn('[Rehydrate] failed, starting fresh:', e);
            }
        }
        const saved = localStorage.getItem('aie_voice_session');
        if (saved) {
            try {
                const state = JSON.parse(saved);
                if (confirm('Resume your previous session?')) {
                    await loadSession(state);
                    return;
                } else {
                    localStorage.removeItem('aie_voice_session');
                }
            } catch (e) {
                console.error('Failed to load saved session:', e);
                localStorage.removeItem('aie_voice_session');
            }
        }
        // Start fresh
        try {
            startSession();
        } catch (e) {
            console.error('Start session failed:', e);
        }
    }

    async function saveProgress() {
        if (!sessionId) return;
        
        // Show saving feedback immediately
        showSaveFeedback('Saving...');
        
        try {
            const response = await fetch('/api/voice/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });
            const data = await response.json();
            
            if (data.success && data.state) {
                // Save to localStorage for persistence
                localStorage.setItem('aie_voice_session', JSON.stringify(data.state));
                showSaveFeedback('✅ Progress saved!');
                console.log('[Save] Session saved:', sessionId);
            } else {
                showSaveFeedback('❌ Save failed', true);
            }
        } catch (e) {
            console.error('Save error:', e);
            showSaveFeedback('❌ Save failed', true);
        }
    }

    function showSaveFeedback(text, isError) {
        // Remove existing feedback
        const existing = document.querySelector('.save-feedback');
        if (existing) existing.remove();
        
        const feedback = document.createElement('div');
        feedback.className = 'save-feedback' + (isError ? ' error' : '');
        feedback.textContent = text;
        document.body.appendChild(feedback);
        
        // Auto-remove after 2 seconds
        setTimeout(() => {
            if (feedback.parentNode) feedback.remove();
        }, 2000);
    }

    async function loadSession(state) {
        try {
            showTyping();
            const response = await fetch('/api/voice/load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: state })
            });
            const data = await response.json();
            hideTyping();

            if (data.error) {
                // Fall back to new session
                try { startSession(); } catch (e) { console.error(e); }
                return;
            }

            sessionId = data.session_id;
            window.sessionId = sessionId;  // Expose for tests/automation
            try { localStorage.setItem('aie_voice_sid', sessionId); } catch (e) {}
            currentStepIndex = data.step_index || 0;
            
            // Prefix question with context label for clarity
            const displayQuestion = data.context_label 
                ? `[${data.context_label}] ${data.question}` 
                : data.question;
            
            addMessage('ai', displayQuestion, false);
            clearInput(data.field === '_bullet');
            currentField = data.field;
            updateProgress(data.progress_pct || 0);
            updateContextLabel(data.context_label);
            updateNavButtons(data.can_go_back, data.field, data.show_add_job);
            updateBulletUI(data);

            // Restore skills if in review phase
            if (data.field === 'skills_review' && data.skills_categorized) {
                currentSkillsCategorized = data.skills_categorized;
                renderSkillsPanel(data.skills_categorized);
            }
        } catch (e) {
            hideTyping();
            console.error('Load session error:', e);
            try { startSession(); } catch (e2) { console.error(e2); }
        }
    }

    // ===== SPEECH RECOGNITION =====

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

    // ===== NAVIGATION ACTIONS =====

    async function goBack() {
        if (!sessionId || !canGoBack) return;
        
        if (textInput) textInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
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
                removeLastUserMessage();
                const displayQuestion = data.context_label 
                    ? `[${data.context_label}] ${data.question}` 
                    : data.question;
                addMessage('ai', displayQuestion, false);
                clearInput(data.field === '_bullet');
                currentField = data.field;
                updateProgress(data.progress_pct);
                updateContextLabel(data.context_label);
                updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                updateBulletUI(data);
            }
        } catch (e) {
            hideTyping();
            console.error('Back error:', e);
        } finally {
            if (textInput) {
                textInput.disabled = false;
                textInput.focus();
            }
            if (sendBtn) sendBtn.disabled = false;
        }
    }

    async function finishJobs() {
        if (!sessionId) return;
        
        if (textInput) textInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
        showTyping();

        try {
            // ESCAPE HATCH: Use force_done_jobs action to bypass state machine loops
            const response = await fetch('/api/voice/turn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    session_id: sessionId, 
                    transcript: '', 
                    action: 'force_done_jobs' 
                })
            });
            const data = await response.json();
            hideTyping();

            if (data.error) {
                addMessage('ai', 'Sorry: ' + data.error, false);
            } else {
                // Hide experience-phase UI elements
                if (navButtons) navButtons.style.display = 'none';
                if (doneJobsBtn) doneJobsBtn.style.display = 'none';
                if (addBtn) addBtn.style.display = 'none';
                
                const displayQuestion = data.context_label 
                    ? `[${data.context_label}] ${data.question}` 
                    : data.question;
                addMessage('ai', displayQuestion, false);
                clearInput(false);
                currentField = data.field;
                updateProgress(data.progress_pct);
                updateContextLabel(data.context_label);
                updateNavButtons(data.can_go_back, data.field, data.show_add_job);
            }
        } catch (e) {
            hideTyping();
            console.error('Finish jobs error:', e);
        } finally {
            if (textInput) {
                textInput.disabled = false;
                textInput.style.display = 'block';
                textInput.focus();
            }
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.style.display = 'block';
            }
        }
    }

    async function addAnother() {
        if (!sessionId) return;
        
        if (textInput) textInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
        showTyping();

        try {
            const action = currentField === '_bullet' || currentField === 'company' || 
                          currentField === 'title' || currentField === 'dates' ? 'add_job' : 'add';
            
            const response = await fetch('/api/voice/turn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, transcript: '__ADD_JOB__', action: action })
            });
            const data = await response.json();
            hideTyping();

            if (data.error) {
                addMessage('ai', 'Sorry: ' + data.error, false);
            } else {
                const displayQuestion = data.context_label 
                    ? `[${data.context_label}] ${data.question}` 
                    : data.question;
                addMessage('ai', displayQuestion, false);
                clearInput(data.field === '_bullet');
                currentField = data.field;
                updateProgress(data.progress_pct);
                updateContextLabel(data.context_label);
                updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                updateBulletUI(data);
            }
        } catch (e) {
            hideTyping();
            console.error('Add error:', e);
        } finally {
            if (textInput) {
                textInput.disabled = false;
                textInput.focus();
            }
            if (sendBtn) sendBtn.disabled = false;
        }
    }

    function removeLastUserMessage() {
        const messages = chatMessages.querySelectorAll('.user-message');
        if (messages.length > 0) {
            messages[messages.length - 1].remove();
        }
    }

    // ===== API CALLS =====

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
            window.sessionId = sessionId;  // Expose for tests/automation
            try { localStorage.setItem('aie_voice_sid', sessionId); } catch (e) {}
            currentStepIndex = data.step_index || 0;
            
            // GLOBAL CIRCUIT BREAKER: Wrap ALL UI rendering to prevent crash loops
            try {
                const displayQuestion = data.context_label 
                    ? `[${data.context_label}] ${data.question}` 
                    : data.question;
                
                addMessage('ai', displayQuestion, false);
                clearInput(data.field === '_bullet');
                currentField = data.field;
                updateProgress(data.progress_pct || 0);
                updateContextLabel(data.context_label);
                updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                updateBulletUI(data);
            } catch (renderError) {
                console.warn("Caught a layout rendering exception in startSession, bypassing:", renderError);
                // DO NOT re-add message here — it causes duplicates if the message already rendered above
            }
        } catch (e) {
            hideTyping();
            addMessage('ai', 'Sorry, something went wrong. Please refresh and try again.', false);
            console.error('Start session error:', e);
        }
    }

    async function sendMessage() {
        const text = textInput ? textInput.value.trim() : '';
        if (!text || !sessionId) return;

        if (isRecording) stopRecording();

        lastUserMessage = text;
        addMessage('user', text, true);
        if (textInput) textInput.value = '';
        accumulatedFinal = '';
        if (textInput) textInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;

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
                lastQuestion = data.question;
                // GLOBAL CIRCUIT BREAKER: Wrap ALL UI rendering to prevent crash loops
                try {
                    // Don't show skills review message in chat — panel shows it visually
                    if (data.field !== 'skills_review') {
                        const displayQuestion = data.context_label 
                            ? `[${data.context_label}] ${data.question}` 
                            : data.question;
                        addMessage('ai', displayQuestion, false);
                    }
                    clearInput(data.field === '_bullet');
                    currentField = data.field;
                    updateProgress(data.progress_pct);
                    updateContextLabel(data.context_label);
                    updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                    updateBulletUI(data);

                    // Handle skills review phase
                    if (data.field === 'skills_review' && data.skills_categorized) {
                        currentSkillsCategorized = data.skills_categorized;
                        renderSkillsPanel(data.skills_categorized);
                    } else {
                        // Hide skills panel if not in skills review
                        hideSkillsPanel();
                    }

                    if (data.done) {
                        showViewResumeButton();
                        
                        // HARDCODED PREVIEW BUTTON: Guarantee visible CTA regardless of sub-function state
                        const forcePreviewBtn = document.createElement('button');
                        forcePreviewBtn.textContent = 'PREVIEW MY RESUME';
                        forcePreviewBtn.className = 'primary-cta-btn';
                        forcePreviewBtn.style.cssText = 'display:block!important;visibility:visible!important;width:100%;padding:16px;margin:20px 0;background:#0066FF;color:#FFFFFF;border:none;border-radius:12px;font-size:18px;font-weight:700;cursor:pointer;z-index:9999;';

                        forcePreviewBtn.addEventListener('click', () => {
                            window.location.href = `/build?mode=form&voice_session=${window.sessionId || ''}`;
                        });

                        // Inject into chat container — guaranteed visible
                        const mainChatContainer = document.getElementById('chat-messages') || document.querySelector('.voice-preview-container');
                        if (mainChatContainer) {
                            mainChatContainer.appendChild(forcePreviewBtn);
                        } else {
                            document.body.appendChild(forcePreviewBtn); // Absolute emergency fallback
                        }
                    }
                } catch (renderError) {
                    console.warn("Caught a layout rendering exception, bypassing to prevent conversation crash:", renderError);
                    // DO NOT re-add message here — it causes duplicates if the message already rendered above
                }
            }
        } catch (e) {
            hideTyping();
            addMessage('ai', 'Sorry, I had trouble with that. Please try again.', false);
            console.error('Turn error:', e);
        } finally {
            if (textInput) {
                textInput.disabled = false;
                textInput.style.display = 'block';
                textInput.focus();
            }
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.style.display = 'block';
            }
        }
    }

    // ===== SKILLS PANEL (Collapsible) =====

    function renderSkillsPanel(categorized) {
        // Remove existing panel
        hideSkillsPanel();

        const panel = document.createElement('div');
        panel.id = 'skills-panel';
        panel.className = 'skills-panel';
        
        const totalSkills = Object.values(categorized).reduce((sum, arr) => sum + arr.length, 0);
        const totalCategories = Object.keys(categorized).length;

        let html = `
            <div class="skills-panel-header" id="skills-panel-header">
                <span class="skills-panel-title">▼ Your Skills</span>
                <span class="skills-panel-count">${totalCategories} categories, ${totalSkills} skills</span>
                <button class="skills-panel-close" id="skills-panel-close" title="Close panel">✕</button>
            </div>
            <div class="skills-panel-body" id="skills-panel-body">
                <div class="skills-panel-content">
        `;

        for (const [category, skills] of Object.entries(categorized)) {
            if (!skills || skills.length === 0) continue;
            html += `<div class="skill-category">
                <div class="skill-category-name">${escapeHtml(category)}</div>
                <div class="skill-list">`;
            for (const skill of skills) {
                const skillName = typeof skill === 'object' ? (skill.name || JSON.stringify(skill)) : skill;
                const skillWeight = typeof skill === 'object' ? (skill.weight || 50) : 50;
                html += `<div class="skill-tag" title="Relevance: ${skillWeight}/100">
                    <span>${escapeHtml(skillName)}</span>
                    <button class="skill-remove" data-skill="${escapeHtml(skillName)}" data-category="${escapeHtml(category)}">−</button>
                </div>`;
            }
            html += `</div></div>`;
        }

        html += `
                <div class="skill-add-section">
                    <input type="text" id="new-skill-input" placeholder="Add a skill..." />
                    <select id="new-skill-category">
                        <option value="">Category...</option>`;
        // Add all 42 categories so user can add to any category
        const usedCats = new Set(Object.keys(categorized));
        for (const cat of ALL_SKILL_CATEGORIES) {
            const hasSkills = usedCats.has(cat);
            html += `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}${hasSkills ? ' (has skills)' : ''}</option>`;
        }
        html += `</select>
                    <button id="add-skill-btn">+</button>
                </div>
                <button class="skills-done-btn" id="skills-done-btn">✅ Done with Skills</button>
            </div>
        </div>`;

        panel.innerHTML = html;
        const container = document.querySelector('.voice-chat-container');
        if (container) container.appendChild(panel);

        // Bind toggle
        const header = document.getElementById('skills-panel-header');
        if (header) {
            header.addEventListener('click', (e) => {
                // Don't toggle if clicking close button
                if (e.target.id === 'skills-panel-close' || e.target.closest('#skills-panel-close')) {
                    return;
                }
                toggleSkillsPanel();
            });
        }

        // Bind close button
        const closeBtn = document.getElementById('skills-panel-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                hideSkillsPanel();
            });
        }

        // Bind remove buttons
        panel.querySelectorAll('.skill-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const skill = e.target.dataset.skill;
                const category = e.target.dataset.category;
                removeSkill(category, skill);
            });
        });

        // Bind add button
        const addBtn = document.getElementById('add-skill-btn');
        if (addBtn) {
            addBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const input = document.getElementById('new-skill-input');
                const select = document.getElementById('new-skill-category');
                const skill = input.value.trim();
                const category = select.value;
                if (skill) {
                    addSkill(category || 'Other Skills', skill);
                    input.value = '';
                }
            });
        }

        // Bind done button
        const doneBtn = document.getElementById('skills-done-btn');
        if (doneBtn) {
            doneBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                textInput.value = 'done';
                sendMessage();
                hideSkillsPanel();
            });
        }

        // Auto-expand on first render
        if (!skillsPanelExpanded) {
            skillsPanelExpanded = true;
            panel.classList.add('expanded');
        }
    }

    function toggleSkillsPanel() {
        const panel = document.getElementById('skills-panel');
        if (!panel) return;
        
        skillsPanelExpanded = !skillsPanelExpanded;
        if (skillsPanelExpanded) {
            panel.classList.add('expanded');
        } else {
            panel.classList.remove('expanded');
        }
    }

    function hideSkillsPanel() {
        const panel = document.getElementById('skills-panel');
        if (panel) panel.remove();
        skillsPanelExpanded = false;
    }

    function removeSkill(category, skill) {
        if (currentSkillsCategorized[category]) {
            currentSkillsCategorized[category] = currentSkillsCategorized[category].filter(s => s !== skill);
            if (currentSkillsCategorized[category].length === 0) {
                delete currentSkillsCategorized[category];
            }
        }
        renderSkillsPanel(currentSkillsCategorized);
        updateSkillsOnServer();
    }

    function addSkill(category, skill) {
        if (!currentSkillsCategorized[category]) {
            currentSkillsCategorized[category] = [];
        }
        currentSkillsCategorized[category].push(skill);
        renderSkillsPanel(currentSkillsCategorized);
        updateSkillsOnServer();
    }

    async function updateSkillsOnServer() {
        if (!sessionId) return;
        try {
            await fetch('/api/voice/turn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    session_id: sessionId, 
                    transcript: '', 
                    action: 'update_skills',
                    skills_categorized: currentSkillsCategorized
                })
            });
        } catch (e) {
            console.error('Update skills error:', e);
        }
    }

    // ===== UI HELPERS =====

    function clearInput(addBulletPrefix) {
        if (textInput) textInput.value = addBulletPrefix ? '• ' : '';
        accumulatedFinal = '';
    }

    function updateBulletUI(data) {
        const helperText = document.getElementById('helper-text');
        const isFirstBullet = data.is_first_bullet;
        const isBulletField = data.field === '_bullet';
        const bulletCount = data.bullet_count || 0;
        const jobCount = data.job_count || 0;
        
        if (helperText) {
            if (isFirstBullet && isBulletField) {
                helperText.textContent = `Say one descriptive sentence explaining one task you did at Job ${jobCount}, then press send.`;
                helperText.classList.remove('hidden');
            } else {
                helperText.classList.add('hidden');
            }
        }
        
        if (isBulletField) {
            clearInput(true);
        }
        
        const isExperiencePhase = isBulletField || data.field === '_decision' || data.show_add_job;
        if (isExperiencePhase && addBtn) {
            addBtn.textContent = '+ Add New Job';
        }
    }

    function addMessage(type, text, isUser) {
        // Dedup guard: skip if the last AI message is identical (prevents double greeting)
        if (!isUser) {
            const messages = chatMessages ? chatMessages.querySelectorAll('.ai-message .message-bubble') : [];
            const lastAi = messages.length > 0 ? messages[messages.length - 1].textContent.trim() : '';
            if (lastAi === text.trim()) {
                console.log('[addMessage] Skipping duplicate AI message:', text.substring(0, 60));
                return;
            }
        }

        const div = document.createElement('div');
        div.className = `message ${type}-message`;

        if (!isUser) {
            // Parse Markdown action links: [Label](action://action_name)
            const actionRegex = /\[([^\]]+)\]\(action:\/\/([^)]+)\)/g;
            let renderedText = escapeHtml(text);
            let hasActions = actionRegex.test(text);
            actionRegex.lastIndex = 0; // reset after test

            if (hasActions) {
                // Replace action links with styled buttons
                renderedText = escapeHtml(text).replace(
                    /\[([^\]]+)\]\(action:\/\/([^)]+)\)/g,
                    (match, label, action) => {
                        return `<button class="action-btn" data-action="${action}" style="display:inline-block;padding:6px 16px;margin:2px 4px;background:#0066FF;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;transition:background 0.2s;" onmouseover="this.style.background='#0052CC'" onmouseout="this.style.background='#0066FF'">${label}</button>`;
                    }
                );
            }

            div.innerHTML = `
                <div class="message-bubble">${renderedText}</div>
                <div class="message-time">${formatTime()}</div>
            `;

            // Attach click handlers for action buttons
            if (hasActions) {
                setTimeout(() => {
                    div.querySelectorAll('.action-btn').forEach(btn => {
                        btn.addEventListener('click', () => {
                            const action = btn.getAttribute('data-action');
                            handleAction(action, text);
                        });
                    });
                }, 0);
            }
        } else {
            div.innerHTML = `
                <div class="message-bubble">${escapeHtml(text)}</div>
                <div class="message-time">${formatTime()}</div>
            `;
        }

        if (chatMessages) chatMessages.appendChild(div);
        scrollToBottom();
    }

    function handleAction(action, originalQuestion) {
        // Map action:// URLs to transcript text the state machine already understands
        const actionMap = {
            'add_bullet': 'yes',
            'finish_bullets': 'done',
            'add_job': 'yes',
            'finish_jobs': 'done',
            'add_item': 'yes',
            'skip_item': 'skip'
        };
        const text = actionMap[action] || action;
        if (!text) return;

        // Show the user's choice as a message
        addMessage('user', actionMap[action], true);

        // Send to the voice API just like a typed answer
        sendActionText(text);
    }

    async function sendActionText(text) {
        if (!sessionId) return;
        if (textInput) textInput.disabled = true;
        if (sendBtn) sendBtn.disabled = true;
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
                lastQuestion = data.question;
                try {
                    if (data.field !== 'skills_review') {
                        const displayQuestion = data.context_label 
                            ? `[${data.context_label}] ${data.question}` 
                            : data.question;
                        addMessage('ai', displayQuestion, false);
                    }
                    clearInput(data.field === '_bullet');
                    currentField = data.field;
                    updateProgress(data.progress_pct);
                    updateContextLabel(data.context_label);
                    updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                    updateBulletUI(data);

                    if (data.field === 'skills_review' && data.skills_categorized) {
                        currentSkillsCategorized = data.skills_categorized;
                        renderSkillsPanel(data.skills_categorized);
                    } else {
                        hideSkillsPanel();
                    }

                    if (data.done) {
                        showViewResumeButton();
                    }
                } catch (renderError) {
                    console.warn('Render error after action:', renderError);
                }
            }
        } catch (e) {
            hideTyping();
            addMessage('ai', 'Sorry, something went wrong. Please try again.', false);
        } finally {
            if (textInput) { textInput.disabled = false; textInput.focus(); }
            if (sendBtn) sendBtn.disabled = false;
        }
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
        if (chatMessages) chatMessages.appendChild(div);
        scrollToBottom();
    }

    function hideTyping() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    }

    function updateProgress(pctOrStepIndex) {
        // If server sends progress_pct, use it directly; otherwise fall back to step-based calc
        let pct;
        if (typeof pctOrStepIndex === 'number' && pctOrStepIndex > 0 && pctOrStepIndex <= 100) {
            // Could be either a step index or a percentage — check if it looks like a percentage
            // Server sends progress_pct (0-100), old path sends step_index (0-9)
            pct = pctOrStepIndex;
        } else {
            pct = 0;
        }
        if (progressFill) progressFill.style.width = pct + '%';
        if (progressText) progressText.textContent = pct + '%';
    }

    function updateContextLabel(label) {
        if (!contextLabel) return;
        if (!label) {
            contextLabel.classList.add('hidden');
            return;
        }
        contextLabel.textContent = label;
        contextLabel.classList.remove('hidden');
    }

    function updateNavButtons(canBack, field, showAddJob) {
        canGoBack = canBack;
        
        const isLoopField = field && !field.startsWith('_') && (
            field === 'company' || field === 'title' ||
            field === 'school' || field === 'degree' ||
            field === 'project_name' || field === 'competency' ||
            field === 'community_org' || field === 'community_role' ||
            field === 'cert_name' || field === 'cert_issuer' ||
            field === 'reference_name' || field === 'reference_phone' ||
            field === 'website' || field === 'linkedin'
        );
        
        const isBulletField = field === '_bullet';
        const isMoreBullets = field === '_more_bullets';
        const isAddJob = field === '_add_job';
        const isDecisionPoint = field === '_decision' || field === '_add_references';
        
        // Show Done with Jobs button during entire experience phase
        const inExperiencePhase = isBulletField || isMoreBullets || isAddJob || 
                                   field === 'company' || field === 'title' || 
                                   field === 'dates' || field === 'location';
        
        if (navButtons) {
            if (canBack || isLoopField || isDecisionPoint || isBulletField || isMoreBullets || isAddJob || showAddJob) {
                navButtons.classList.remove('hidden');
            } else {
                navButtons.classList.add('hidden');
            }
        }
        
        if (backBtn) backBtn.style.display = canBack ? 'inline-block' : 'none';
        
        // Show save button always when we have a session
        if (saveBtn) {
            saveBtn.style.display = sessionId ? 'inline-block' : 'none';
        }
        
        // ESCAPE HATCH: Show Done with Jobs button during entire experience phase
        if (doneJobsBtn) {
            doneJobsBtn.style.display = inExperiencePhase ? 'inline-block' : 'none';
        }
        
        if (addBtn) {
            if (isDecisionPoint || isLoopField || isBulletField || isMoreBullets || isAddJob || showAddJob) {
                addBtn.style.display = 'inline-block';
                if (isDecisionPoint) {
                    addBtn.textContent = '+ Add Another';
                } else if (inExperiencePhase) {
                    addBtn.textContent = '+ Add Job';
                }
            } else {
                addBtn.style.display = 'none';
            }
        }
    }

    function showViewResumeButton() {
        console.log('[DEBUG] showViewResumeButton called');
        if (micBtn) micBtn.style.display = 'none';
        if (textInput) textInput.style.display = 'none';
        if (sendBtn) sendBtn.style.display = 'none';
        if (navButtons) navButtons.style.display = 'none';
        hideSkillsPanel();

        // ABANDONED: Broken inline preview — replaced with direct redirect button
        // fetchPreviewAndDisplay();

        // Create visible "Preview Resume" CTA button
        const previewBtn = document.createElement('button');
        previewBtn.textContent = 'Preview Resume';
        previewBtn.className = 'preview-resume-btn';
        previewBtn.style.cssText = 'display:block;width:100%;padding:14px 24px;margin-top:16px;background:#0066FF;color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:600;cursor:pointer;';
        
        // Bind redirect to working form builder
        previewBtn.addEventListener('click', () => {
            window.location.href = `/build?mode=form&voice_session=${window.sessionId || ''}`;
        });
        
        // Mount into chat area where user can see it
        if (chatMessages) {
            chatMessages.appendChild(previewBtn);
            scrollToBottom();
        }
    }

    async function fetchPreviewAndDisplay() {
        console.log('[DEBUG] fetchPreviewAndDisplay started');
        showTyping();
        try {
            console.log('[DEBUG] Making fetch to /api/voice/preview with sessionId:', sessionId);
            const response = await fetch('/api/voice/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, template_style: 'professional' })
            });
            console.log('[DEBUG] Fetch response status:', response.status);
            const data = await response.json();
            console.log('[DEBUG] Fetch response data:', { success: data.success, has_preview: !!data.preview_html });
            hideTyping();

            if (data.success && data.preview_html) {
                console.log('[DEBUG] Preview HTML received, creating container');
                // Add preview message
                addMessage('ai', '📄 Here is your resume preview:', false);
                
                // Create preview container
                const previewDiv = document.createElement('div');
                previewDiv.className = 'voice-preview-container';
                previewDiv.innerHTML = data.preview_html;
                if (chatMessages) chatMessages.appendChild(previewDiv);
                console.log('[DEBUG] Preview container appended to chat');
                
                // Add purchase button
                const buyBtn = document.createElement('a');
                buyBtn.href = `/build?mode=form&voice_session=${sessionId}`;
                buyBtn.className = 'view-resume-btn';
                buyBtn.textContent = '💳 Purchase Resume ($9.99)';
                if (chatMessages) chatMessages.appendChild(buyBtn);
                
                scrollToBottom();
            } else {
                console.log('[DEBUG] No preview HTML, using fallback');
                // Fallback to old link
                const btn = document.createElement('a');
                btn.href = `/build?mode=form&voice_session=${sessionId}`;
                btn.className = 'view-resume-btn';
                btn.textContent = '👁️ View Your Resume';
                if (chatMessages) chatMessages.appendChild(btn);
                addMessage('ai', 'Great! Your resume is ready. Click below to preview and purchase.', false);
            }
        } catch (e) {
            hideTyping();
            console.error('[DEBUG] Preview fetch error:', e);
            // Fallback
            const btn = document.createElement('a');
            btn.href = `/build?mode=form&voice_session=${sessionId}`;
            btn.className = 'view-resume-btn';
            btn.textContent = '👁️ View Your Resume';
            if (chatMessages) chatMessages.appendChild(btn);
            addMessage('ai', 'Great! Your resume is ready. Click below to preview and purchase.', false);
        }
        console.log('[DEBUG] fetchPreviewAndDisplay completed');
    }

    function scrollToBottom() {
        if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
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

    // Initialize safely
    try {
        init();
    } catch (e) {
        console.error('Init failed:', e);
    }
})();
