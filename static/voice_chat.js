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
        if (doneJobsBtn) {
            doneJobsBtn.addEventListener('click', finishJobs);
        }
        if (saveBtn) {
            saveBtn.addEventListener('click', saveProgress);
        }
    }

    // ===== SAVE / LOAD =====

    async function checkForSavedSession() {
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
        startSession();
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
                startSession();
                return;
            }

            sessionId = data.session_id;
            currentStepIndex = data.step_index || 0;
            
            const welcome = document.getElementById('welcome-message');
            if (welcome) welcome.remove();
            
            // Prefix question with context label for clarity
            const displayQuestion = data.context_label 
                ? `[${data.context_label}] ${data.question}` 
                : data.question;
            
            addMessage('ai', displayQuestion, false);
            clearInput(data.field === '_bullet');
            currentField = data.field;
            updateProgress(currentStepIndex);
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
            startSession();
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
                removeLastUserMessage();
                const displayQuestion = data.context_label 
                    ? `[${data.context_label}] ${data.question}` 
                    : data.question;
                addMessage('ai', displayQuestion, false);
                clearInput(data.field === '_bullet');
                currentField = data.field;
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

    async function finishJobs() {
        if (!sessionId) return;
        
        textInput.disabled = true;
        sendBtn.disabled = true;
        showTyping();

        try {
            const response = await fetch('/api/voice/turn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, transcript: '__DONE_WITH_JOBS__', action: 'finish_jobs' })
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
                clearInput(false);
                currentField = data.field;
                updateProgress(data.step_index);
                updateContextLabel(data.context_label);
                updateNavButtons(data.can_go_back, data.field, data.show_add_job);
                if (doneJobsBtn) doneJobsBtn.style.display = 'none';
            }
        } catch (e) {
            hideTyping();
            console.error('Finish jobs error:', e);
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
            currentStepIndex = data.step_index || 0;
            
            const welcome = document.getElementById('welcome-message');
            if (welcome) welcome.remove();
            
            const displayQuestion = data.context_label 
                ? `[${data.context_label}] ${data.question}` 
                : data.question;
            
            addMessage('ai', displayQuestion, false);
            clearInput(data.field === '_bullet');
            currentField = data.field;
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

        if (isRecording) stopRecording();

        lastUserMessage = text;
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
                lastQuestion = data.question;
                // Don't show skills review message in chat — panel shows it visually
                if (data.field !== 'skills_review') {
                    const displayQuestion = data.context_label 
                        ? `[${data.context_label}] ${data.question}` 
                        : data.question;
                    addMessage('ai', displayQuestion, false);
                }
                clearInput(data.field === '_bullet');
                currentField = data.field;
                updateProgress(data.step_index);
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
        document.querySelector('.voice-chat-container').appendChild(panel);

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
        textInput.value = addBulletPrefix ? '• ' : '';
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
        
        const isLoopField = field && !field.startsWith('_') && 
            (field === 'company' || field === 'title' || field === 'school' || 
             field === 'degree' || field === 'project_name' || field === 'competency' ||
             field === 'community_org' || field === 'cert_name');
        
        const isDecisionPoint = field === '_decision';
        const isBulletField = field === '_bullet';
        const inExperience = isDecisionPoint; // Only show Done with Jobs at decision points
        
        if (canBack || isLoopField || isDecisionPoint || isBulletField || showAddJob) {
            navButtons.classList.remove('hidden');
        } else {
            navButtons.classList.add('hidden');
        }
        
        backBtn.style.display = canBack ? 'inline-block' : 'none';
        
        // Show save button always when we have a session
        if (saveBtn) {
            saveBtn.style.display = sessionId ? 'inline-block' : 'none';
        }
        
        if (doneJobsBtn) {
            // ALWAYS show Done with Jobs button during experience (bullets + decision)
        const inJobEntry = isBulletField || isDecisionPoint || field === 'company' || 
                          field === 'title' || field === 'dates';
        if (doneJobsBtn) {
            doneJobsBtn.style.display = inJobEntry ? 'inline-block' : 'none';
        }
        }
        
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
        hideSkillsPanel();

        // Fetch and display inline preview
        fetchPreviewAndDisplay();
    }

    async function fetchPreviewAndDisplay() {
        showTyping();
        try {
            const response = await fetch('/api/voice/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, template_style: 'professional' })
            });
            const data = await response.json();
            hideTyping();

            if (data.success && data.preview_html) {
                // Add preview message
                addMessage('ai', '📄 Here is your resume preview:', false);
                
                // Create preview container
                const previewDiv = document.createElement('div');
                previewDiv.className = 'voice-preview-container';
                previewDiv.innerHTML = data.preview_html;
                chatMessages.appendChild(previewDiv);
                
                // Add purchase button
                const buyBtn = document.createElement('a');
                buyBtn.href = `/build?mode=form&voice_session=${sessionId}`;
                buyBtn.className = 'view-resume-btn';
                buyBtn.textContent = '💳 Purchase Resume ($9.99)';
                chatMessages.appendChild(buyBtn);
                
                scrollToBottom();
            } else {
                // Fallback to old link
                const btn = document.createElement('a');
                btn.href = `/build?mode=form&voice_session=${sessionId}`;
                btn.className = 'view-resume-btn';
                btn.textContent = '👁️ View Your Resume';
                chatMessages.appendChild(btn);
                addMessage('ai', 'Great! Your resume is ready. Click below to preview and purchase.', false);
            }
        } catch (e) {
            hideTyping();
            console.error('Preview fetch error:', e);
            // Fallback
            const btn = document.createElement('a');
            btn.href = `/build?mode=form&voice_session=${sessionId}`;
            btn.className = 'view-resume-btn';
            btn.textContent = '👁️ View Your Resume';
            chatMessages.appendChild(btn);
            addMessage('ai', 'Great! Your resume is ready. Click below to preview and purchase.', false);
        }
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
