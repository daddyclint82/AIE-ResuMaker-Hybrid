/**
 * ResumeForge Frontend Logic
 */

// State
let skills = [];
let experienceCount = 0;
let educationCount = 0;
let certificationCount = 0;
let projectCount = 0;
let competencyCount = 0;
let communityCount = 0;
let currentResumeId = null;

// DOM Elements
const form = document.getElementById('resume-form');
const previewContainer = document.getElementById('preview-container');
const summaryTextarea = document.getElementById('summary');
const summaryCount = document.getElementById('summary-count');
const skillsInput = document.getElementById('skill-input');
const skillsTags = document.getElementById('skills-tags');
const skillsHidden = document.getElementById('skills');

// Edit tracking (5 edits per purchase)
const MAX_EDITS = 5;
let currentResumePaid = false;

function getEditCount() {
    return parseInt(localStorage.getItem('aie_edit_count') || '0');
}

function setEditCount(count) {
    localStorage.setItem('aie_edit_count', String(count));
    updateEditCounterUI();
}

function getPurchaseDate() {
    return localStorage.getItem('aie_purchase_date');
}

function recordPurchase() {
    localStorage.setItem('aie_purchase_date', new Date().toISOString());
    setEditCount(0);
    updateEditCounterUI();
}

function updateEditCounterUI() {
    const counter = document.getElementById('edit-counter');
    if (!counter) return;
    
    const count = getEditCount();
    const remaining = Math.max(0, MAX_EDITS - count);
    
    if (remaining > 0) {
        counter.innerHTML = `✏️ AFTER PURCHASE ${remaining} EDIT${remaining !== 1 ? 'S' : ''} REMAINING`;
        counter.className = 'edit-counter';
    } else {
        counter.innerHTML = `✏️ AFTER PURCHASE 0 EDITS REMAINING — <a href="#" id="repurchase-link">REPURCHASE</a>`;
        counter.className = 'edit-counter exhausted';
        
        // Re-attach click handler
        setTimeout(() => {
            document.getElementById('repurchase-link')?.addEventListener('click', (e) => {
                e.preventDefault();
                initiatePayment();
            });
        }, 0);
    }
}

function canEdit() {
    const count = getEditCount();
    return count < MAX_EDITS;
}

function useEdit() {
    const count = getEditCount();
    if (count < MAX_EDITS) {
        setEditCount(count + 1);
        return true;
    }
    return false;
}

function showEditDialog() {
    const count = getEditCount();
    const remaining = Math.max(0, MAX_EDITS - count);
    
    if (remaining <= 0) {
        return confirm('You have used all 5 edits. Repurchase for 5 more?');
    }
    
    return confirm(`You have ${remaining} edit${remaining !== 1 ? 's' : ''} remaining. Use 1 edit to save changes?`);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Check for voice session data first
    loadVoiceData();
    
    // Load saved progress FIRST (before adding empty defaults)
    const hasSavedData = loadSavedProgress();
    
    if (!hasSavedData) {
        // Only add empty fields if NO saved data exists
        setupDynamicFields();
    }
    
    setupEventListeners();
    checkTermsAcceptance();
    checkReferral(); // async but doesn't block
    setupAutoSave();
    updateEditCounterUI();
    setupModeSwitch(); // Add voice mode toggle
    
    // Save on page unload/refresh
    window.addEventListener('beforeunload', () => {
        saveProgress(false);
    });
    
    // Also save when user switches tabs or minimizes
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            saveProgress(false);
        }
    });
    
    // Periodic auto-save every 10 seconds as backup
    setInterval(() => {
        saveProgress(false);
    }, 10000);
    
    // Restore saved theme preference
    const savedTheme = localStorage.getItem('aie_theme');
    if (savedTheme) {
        const themeSelect = document.getElementById('theme-select');
        if (themeSelect) themeSelect.value = savedTheme;
    }
    
    // Check if we should show edit popup (after purchase return)
    checkEditPopup();
});

// Edit Popup Functions
function checkEditPopup() {
    const showPopup = localStorage.getItem('aie_show_edit_popup');
    if (showPopup === 'true') {
        showEditPopup();
        // Don't clear yet - let user close it
    }
}

function showEditPopup() {
    const popup = document.getElementById('edit-popup');
    const countSpan = document.getElementById('edit-popup-count');
    
    if (popup && countSpan) {
        const count = getEditCount();
        const remaining = Math.max(0, MAX_EDITS - count);
        countSpan.textContent = remaining;
        popup.style.display = 'block';
    }
}

function closeEditPopup() {
    const popup = document.getElementById('edit-popup');
    if (popup) {
        popup.style.display = 'none';
        localStorage.removeItem('aie_show_edit_popup');
    }
}

// Make closeEditPopup globally accessible
window.closeEditPopup = closeEditPopup;

// Terms of Service check — now handled on /terms page, just verify localStorage exists
function checkTermsAcceptance() {
    const accepted = localStorage.getItem('aie_terms_accepted');
    
    if (!accepted) {
        // Preserve voice_session/mode so we return to the right build after accepting
        const params = window.location.search; // e.g. ?mode=form&voice_session=abc
        window.location.href = '/terms' + (params ? '?return=' + encodeURIComponent('/build' + params) : '');
    }
}

// Auto-Save Functionality
function setupAutoSave() {
    // Auto-save on any form input change (debounced)
    let debounceTimer;
    form.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            saveProgress(false); // silent save
        }, 300); // Save 300ms after user stops typing (faster)
    });
    
    // Save immediately when user leaves a field
    form.addEventListener('blur', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
            saveProgress(false);
        }
    }, true); // Use capture phase to catch all blur events
    
    // Also save on select changes
    form.addEventListener('change', () => {
        saveProgress(false);
    });
    
    // Save when user clicks outside the form
    document.addEventListener('click', (e) => {
        if (!form.contains(e.target)) {
            saveProgress(false);
        }
    });
    
    // Manual save button
    const saveBtn = document.getElementById('save-progress-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', () => {
            saveProgress(true); // show success message
        });
    }
    
    // Show hint when industry field changes
    const industrySelect = document.getElementById('industry');
    const hintShown = localStorage.getItem('aie_hint_shown');
    
    if (industrySelect && !hintShown) {
        industrySelect.addEventListener('change', () => {
            if (industrySelect.value && !localStorage.getItem('aie_hint_shown')) {
                showIndustryHint();
                localStorage.setItem('aie_hint_shown', 'true');
            }
        });
    }
}

function showIndustryHint() {
    const hint = document.getElementById('industry-hint');
    if (hint) {
        hint.style.display = 'block';
        // Auto-hide after 8 seconds
        setTimeout(() => {
            hint.style.display = 'none';
        }, 8000);
    }
}

function saveProgress(showFeedback = false) {
    const saveStatus = document.getElementById('save-status');
    
    if (showFeedback && saveStatus) {
        saveStatus.textContent = 'Saving...';
        saveStatus.className = 'save-status visible saving';
    }
    
    try {
        // Collect all form data
        const formData = collectFormDataForSave();
        
        console.log('[AIE ResuMaker] Saving data:', JSON.stringify(formData, null, 2));
        
        // Save to localStorage
        localStorage.setItem('aie_resume_progress', JSON.stringify(formData));
        localStorage.setItem('aie_resume_saved_at', new Date().toISOString());
        localStorage.setItem('aie_theme', formData.template_style);
        
        if (showFeedback && saveStatus) {
            saveStatus.textContent = '✓ Saved!';
            saveStatus.className = 'save-status visible';
            
            // Clear after 2 seconds
            setTimeout(() => {
                saveStatus.className = 'save-status';
            }, 2000);
        }
        
        console.log('[AIE ResuMaker] Progress saved successfully');
    } catch (error) {
        console.error('[AIE ResuMaker] Save error:', error);
        if (showFeedback && saveStatus) {
            saveStatus.textContent = 'Save failed';
            saveStatus.style.color = 'var(--error-color)';
            saveStatus.className = 'save-status visible';
        }
    }
}

function collectFormDataForSave() {
    const data = {
        full_name: form.querySelector('input[name="full_name"]')?.value || '',
        email: form.querySelector('input[name="email"]')?.value || '',
        phone: form.querySelector('input[name="phone"]')?.value || '',
        state: form.querySelector('select[name="state"]')?.value || '',
        city: form.querySelector('input[name="city"]')?.value || '',
        linkedin: form.querySelector('input[name="linkedin"]')?.value || '',
        website: form.querySelector('input[name="website"]')?.value || '',
        summary: form.querySelector('textarea[name="summary"]')?.value || '',
        skills: skills.join('|'),
        industry: form.querySelector('select[name="industry"]')?.value || '',
        education_level: form.querySelector('select[name="education_level"]')?.value || '',
        job_title: form.querySelector('input[name="job_title"]')?.value || '',
        experience_level: form.querySelector('select[name="experience_level"]')?.value || '',
        template_style: document.getElementById('theme-select')?.value || form.querySelector('select[name="template_style"]')?.value || 'professional',
    };
    
    // Collect experience
    const experience = [];
    const expTitles = form.querySelectorAll('input[name="exp_title[]"]');
    expTitles.forEach((_, index) => {
        const title = expTitles[index]?.value;
        if (title) {
            experience.push({
                title: title,
                company: form.querySelectorAll('input[name="exp_company[]"]')[index]?.value || '',
                state: form.querySelectorAll('select[name="exp_state[]"]')[index]?.value || '',
                city: form.querySelectorAll('input[name="exp_city[]"]')[index]?.value || '',
                dates: form.querySelectorAll('input[name="exp_dates[]"]')[index]?.value || '',
                phone: form.querySelectorAll('input[name="exp_phone[]"]')[index]?.value || '',
                address: form.querySelectorAll('input[name="exp_address[]"]')[index]?.value || '',
                description: form.querySelectorAll('textarea[name="exp_description[]"]')[index]?.value || ''
            });
        }
    });
    data.experience = experience;
    
    // Collect education
    const education = [];
    const eduSchools = form.querySelectorAll('input[name="edu_school[]"]');
    eduSchools.forEach((_, index) => {
        const school = eduSchools[index]?.value;
        if (school) {
            education.push({
                school: school,
                degree: form.querySelectorAll('select[name="edu_degree[]"]')[index]?.value || '',
                field: form.querySelectorAll('input[name="edu_field[]"]')[index]?.value || '',
                dates: form.querySelectorAll('input[name="edu_dates[]"]')[index]?.value || ''
            });
        }
    });
    data.education = education;
    
    // Collect projects
    const projects = [];
    const projNames = form.querySelectorAll('input[name="proj_name[]"]');
    projNames.forEach((_, index) => {
        const name = projNames[index]?.value;
        if (name) {
            projects.push({
                name: name,
                tech: form.querySelectorAll('input[name="proj_tech[]"]')[index]?.value || '',
                description: form.querySelectorAll('textarea[name="proj_description[]"]')[index]?.value || '',
                result: form.querySelectorAll('input[name="proj_result[]"]')[index]?.value || ''
            });
        }
    });
    data.projects = projects;
    
    // Collect competencies (Notable Competencies)
    const competencies = [];
    const compLabels = form.querySelectorAll('input[name="comp_label[]"]');
    compLabels.forEach((_, index) => {
        const label = compLabels[index]?.value;
        if (label) {
            competencies.push({
                label: label,
                description: form.querySelectorAll('input[name="comp_desc[]"]')[index]?.value || ''
            });
        }
    });
    data.competencies = competencies;
    
    // Collect community involvement
    const community = [];
    const commEvents = form.querySelectorAll('input[name="comm_event[]"]');
    commEvents.forEach((_, index) => {
        const event = commEvents[index]?.value;
        if (event) {
            community.push({
                event: event,
                organization: form.querySelectorAll('input[name="comm_org[]"]')[index]?.value || ''
            });
        }
    });
    data.community = community;
    
    // Collect certifications
    const certifications = [];
    const certNames = form.querySelectorAll('input[name="cert_name[]"]');
    certNames.forEach((_, index) => {
        const name = certNames[index]?.value;
        if (name) {
            certifications.push({
                name: name,
                organization: form.querySelectorAll('input[name="cert_org[]"]')[index]?.value || '',
                date: form.querySelectorAll('input[name="cert_date[]"]')[index]?.value || ''
            });
        }
    });
    data.certifications = certifications;
    
    return data;
}

function loadVoiceData() {
    try {
        const script = document.getElementById('voice-data');
        if (!script) return;
        
        const voiceData = JSON.parse(script.textContent);
        if (!voiceData || Object.keys(voiceData).length === 0) return;
        
        // Detect whether THIS load came from a fresh voice session (URL param).
        // If so, the server session is authoritative — do NOT let stale
        // localStorage shadow it (that caused prompt-text/partial-resume bugs).
        const hasVoiceSession = new URLSearchParams(window.location.search).has('voice_session');
        
        // Check if user has already saved progress in localStorage
        const savedProgress = localStorage.getItem('aie_resume_progress');
        if (savedProgress && !hasVoiceSession) {
            const savedData = JSON.parse(savedProgress);
            const savedAt = localStorage.getItem('aie_resume_saved_at');
            
            // If saved data has voice session fields populated, user has already edited
            // Prefer localStorage data over voice session data to prevent overwriting edits
            if (savedData.full_name && savedData.full_name.trim() !== '') {
                console.log('[AIE ResuMaker] localStorage has saved data, skipping voice data load to preserve edits');
                return;
            }
        }
        if (hasVoiceSession) {
            // Fresh voice session is authoritative — drop stale saved progress
            // so a later reload without the param can't resurrect old data.
            localStorage.removeItem('aie_resume_progress');
            localStorage.removeItem('aie_resume_saved_at');
            console.log('[AIE ResuMaker] Fresh voice session present — using server data, cleared stale localStorage');
        }
        
        console.log('[AIE ResuMaker] Loading voice session data:', voiceData);
        
        // Map voice fields to form fields
        const fieldMap = {
            'full_name': 'full_name',
            'email': 'email',
            'phone': 'phone',
            'city': 'city',
            'industry': 'industry',
            'job_title': 'job_title',
            'experience_level': 'experience_level',
            'summary': 'summary',
            'linkedin': 'linkedin',
            'website': 'website'
        };
        
        // Set simple fields
        Object.entries(fieldMap).forEach(([voiceKey, formKey]) => {
            const el = form.querySelector(`[name="${formKey}"]`);
            if (el && voiceData[voiceKey]) {
                el.value = voiceData[voiceKey];
                console.log(`[Voice→Form] Set ${formKey} = ${voiceData[voiceKey]}`);
            }
        });
        
        // Set skills
        if (voiceData.skills && Array.isArray(voiceData.skills)) {
            skills = [...voiceData.skills];
            renderSkills();
            console.log('[Voice→Form] Set skills:', skills);
        }
        
        // Set experience entries
        if (voiceData.experience && Array.isArray(voiceData.experience)) {
            const expList = document.getElementById('experience-list');
            if (expList) {
                // Clear any existing entries first
                expList.innerHTML = '';
                experienceCount = 0;
                
                voiceData.experience.forEach((exp, i) => {
                    // Prepare data object matching addExperienceField expectations
                    const expData = {
                        title: exp.title || '',
                        company: exp.company || '',
                        city: exp.city || '',
                        state: exp.state || '',
                        dates: exp.dates || '',
                        phone: exp.phone || '',
                        address: exp.address || '',
                        description: exp.description || ''
                    };
                    
                    // Handle bullets array -> description string conversion
                    if (exp.bullets && Array.isArray(exp.bullets)) {
                        expData.description = exp.bullets.join('\n');
                    }
                    
                    addExperienceField(expData);
                    console.log(`[Voice→Form] Added experience entry #${i + 1}:`, expData.title || '(no title)');
                });
            }
            console.log('[Voice→Form] Set experience entries:', voiceData.experience.length);
        }
        
        // Set education entries
        if (voiceData.education && Array.isArray(voiceData.education)) {
            const eduList = document.getElementById('education-list');
            if (eduList) {
                // Clear any existing entries first
                eduList.innerHTML = '';
                educationCount = 0;
                
                voiceData.education.forEach((edu, i) => {
                    // Prepare data object matching addEducationField expectations
                    const eduData = {
                        school: edu.school || '',
                        degree: edu.degree || '',
                        field: edu.field || '',
                        dates: edu.dates || ''
                    };
                    
                    addEducationField(eduData);
                    console.log(`[Voice→Form] Added education entry #${i + 1}:`, eduData.school || '(no school)');
                });
            }
            console.log('[Voice→Form] Set education entries:', voiceData.education.length);
        }
        
        // Set optional sections
        // Projects
        if (voiceData.projects && Array.isArray(voiceData.projects)) {
            const projList = document.getElementById('projects-list');
            if (projList) {
                projList.innerHTML = '';
                projectCount = 0;
                voiceData.projects.forEach((proj, i) => {
                    addProjectField({
                        name: proj.name || '',
                        tech: proj.tech || '',
                        description: proj.description || '',
                        result: proj.result || ''
                    });
                });
                console.log('[Voice→Form] Set project entries:', voiceData.projects.length);
            }
        }
        
        // Competencies
        if (voiceData.competencies && Array.isArray(voiceData.competencies)) {
            const compList = document.getElementById('competencies-list');
            if (compList) {
                compList.innerHTML = '';
                competencyCount = 0;
                voiceData.competencies.forEach((comp, i) => {
                    addCompetencyField({
                        label: comp.label || '',
                        description: comp.description || ''
                    });
                });
                console.log('[Voice→Form] Set competency entries:', voiceData.competencies.length);
            }
        }
        
        // Community Involvement
        if (voiceData.community && Array.isArray(voiceData.community)) {
            const commList = document.getElementById('community-list');
            if (commList) {
                commList.innerHTML = '';
                communityCount = 0;
                voiceData.community.forEach((comm, i) => {
                    addCommunityField({
                        event: comm.event || comm.org || '',
                        organization: comm.organization || comm.description || ''
                    });
                });
                console.log('[Voice→Form] Set community entries:', voiceData.community.length);
            }
        }
        
        // Certifications
        if (voiceData.certifications && Array.isArray(voiceData.certifications)) {
            const certList = document.getElementById('certifications-list');
            if (certList) {
                certList.innerHTML = '';
                certificationCount = 0;
                voiceData.certifications.forEach((cert, i) => {
                    addCertificationField({
                        name: cert.name || '',
                        org: cert.issuer || cert.org || '',
                        date: cert.date || ''
                    });
                });
                console.log('[Voice→Form] Set certification entries:', voiceData.certifications.length);
            }
        }
        
        // Handle address parsing if present (voice asks for "street, city, state zip")
        if (voiceData.address && typeof voiceData.address === 'string') {
            const addressStr = voiceData.address;
            // Try to parse "street, city, state zip" format
            const parts = addressStr.split(',').map(p => p.trim());
            if (parts.length >= 3) {
                // Last part should be "state zip"
                const stateZip = parts[parts.length - 1].trim();
                const stateZipMatch = stateZip.match(/^([A-Za-z\s]+)\s*(\d{5}(-\d{4})?)?$/);
                if (stateZipMatch) {
                    const stateName = stateZipMatch[1].trim();
                    // Find matching state option
                    const stateSelect = form.querySelector('select[name="state"]');
                    if (stateSelect) {
                        // Try to find by text content or value
                        const stateOption = Array.from(stateSelect.options).find(opt => 
                            opt.text.toLowerCase().includes(stateName.toLowerCase()) || 
                            opt.value.toLowerCase() === stateName.toLowerCase()
                        );
                        if (stateOption) {
                            stateSelect.value = stateOption.value;
                            // Trigger city input enable
                            const cityInput = document.getElementById('city');
                            if (cityInput) {
                                cityInput.disabled = false;
                                cityInput.placeholder = 'Type to search cities...';
                            }
                        }
                    }
                    // City is second-to-last part
                    const cityInput = form.querySelector('input[name="city"]');
                    if (cityInput) {
                        cityInput.value = parts[parts.length - 2];
                    }
                }
            }
            // If we couldn't parse properly, just put the whole thing in city as fallback
            if (!form.querySelector('input[name="city"]').value) {
                form.querySelector('input[name="city"]').value = addressStr;
            }
        }
        
        // Save to localStorage so user doesn't lose it
        saveProgress(false);
        
        console.log('[AIE ResuMaker] Voice data loaded successfully');
        
    } catch (e) {
        console.error('[AIE ResuMaker] Failed to load voice data:', e);
    }
}

function loadSavedProgress() {
    try {
        const saved = localStorage.getItem('aie_resume_progress');
        if (!saved) {
            console.log('[AIE ResuMaker] No saved progress found');
            return false;
        }
        
        const data = JSON.parse(saved);
        const savedAt = localStorage.getItem('aie_resume_saved_at');
        
        console.log('[AIE ResuMaker] Loading saved progress from:', savedAt);
        console.log('[AIE ResuMaker] Raw data:', JSON.stringify(data, null, 2));
        
        // Fill basic fields
        const setValue = (name, value) => {
            const el = form.querySelector(`[name="${name}"]`);
            if (el && value) {
                el.value = value;
                console.log(`[AIE ResuMaker] Set ${name} = ${value}`);
            }
        };
        
        setValue('full_name', data.full_name);
        setValue('email', data.email);
        setValue('phone', data.phone);
        setValue('state', data.state);
        setValue('city', data.city);
        setValue('linkedin', data.linkedin);
        setValue('website', data.website);
        setValue('summary', data.summary);
        setValue('industry', data.industry);
        setValue('education_level', data.education_level);
        setValue('job_title', data.job_title);
        setValue('experience_level', data.experience_level);
        
        // Set template style
        const templateSelect = document.getElementById('theme-select');
        if (templateSelect && data.template_style) {
            templateSelect.value = data.template_style;
            localStorage.setItem('aie_theme', data.template_style);
        }
        
        // Load skills
        if (data.skills) {
            skills = data.skills.split('|').filter(s => s.trim());
            renderSkills();
        }
        
        // Load experience (clear defaults first)
        if (data.experience && data.experience.length > 0) {
            console.log('[AIE ResuMaker] Loading', data.experience.length, 'experience entries');
            const expList = document.getElementById('experience-list');
            if (expList) {
                expList.innerHTML = '';
                experienceCount = 0;
                data.experience.forEach((exp, i) => {
                    console.log('[AIE ResuMaker] Adding experience #' + i + ':', exp.title);
                    addExperienceField(exp);
                });
            } else {
                console.error('[AIE ResuMaker] experience-list element NOT FOUND');
            }
        }
        
        // Load education (clear defaults first)
        if (data.education && data.education.length > 0) {
            console.log('[AIE ResuMaker] Loading', data.education.length, 'education entries');
            const eduList = document.getElementById('education-list');
            if (eduList) {
                eduList.innerHTML = '';
                educationCount = 0;
                data.education.forEach((edu, i) => {
                    console.log('[AIE ResuMaker] Adding education #' + i + ':', edu.school);
                    addEducationField(edu);
                });
            } else {
                console.error('[AIE ResuMaker] education-list element NOT FOUND');
            }
        }
        
        // Load projects
        if (data.projects && data.projects.length > 0) {
            console.log('[AIE ResuMaker] Loading', data.projects.length, 'project entries');
            const projList = document.getElementById('projects-list');
            if (projList) {
                projList.innerHTML = '';
                projectCount = 0;
                data.projects.forEach((proj, i) => {
                    console.log('[AIE ResuMaker] Adding project #' + i + ':', proj.name);
                    addProjectField(proj);
                });
            } else {
                console.error('[AIE ResuMaker] projects-list element NOT FOUND');
            }
        }
        
        // Load competencies (Notable Competencies)
        if (data.competencies && data.competencies.length > 0) {
            console.log('[AIE ResuMaker] Loading', data.competencies.length, 'competency entries');
            const compList = document.getElementById('competencies-list');
            if (compList) {
                compList.innerHTML = '';
                competencyCount = 0;
                data.competencies.forEach((comp, i) => {
                    console.log('[AIE ResuMaker] Adding competency #' + i + ':', comp.label);
                    addCompetencyField(comp);
                });
            } else {
                console.error('[AIE ResuMaker] competencies-list element NOT FOUND');
            }
        }
        
        // Load community involvement
        if (data.community && data.community.length > 0) {
            console.log('[AIE ResuMaker] Loading', data.community.length, 'community entries');
            const commList = document.getElementById('community-list');
            if (commList) {
                commList.innerHTML = '';
                communityCount = 0;
                data.community.forEach((comm, i) => {
                    console.log('[AIE ResuMaker] Adding community #' + i + ':', comm.event);
                    addCommunityField(comm);
                });
            } else {
                console.error('[AIE ResuMaker] community-list element NOT FOUND');
            }
        }
        
        // Load certifications
        if (data.certifications && data.certifications.length > 0) {
            console.log('[AIE ResuMaker] Loading', data.certifications.length, 'certification entries');
            const certList = document.getElementById('certifications-list');
            if (certList) {
                certList.innerHTML = '';
                certificationCount = 0;
                data.certifications.forEach((cert, i) => {
                    console.log('[AIE ResuMaker] Adding certification #' + i + ':', cert.name);
                    addCertificationField(cert);
                });
            } else {
                console.error('[AIE ResuMaker] certifications-list element NOT FOUND');
            }
        }
        
        // Update character counter
        updateCharCounter();
        
        // Show feedback
        const saveStatus = document.getElementById('save-status');
        if (saveStatus) {
            const date = savedAt ? new Date(savedAt).toLocaleDateString() : 'previously';
            saveStatus.textContent = `✓ Loaded saved progress (${date})`;
            saveStatus.className = 'save-status visible';
            setTimeout(() => {
                saveStatus.className = 'save-status';
            }, 3000);
        }
        
        console.log('[AIE ResuMaker] Progress loaded successfully');
        return true;
    } catch (error) {
        console.error('[AIE ResuMaker] Load error:', error);
        return false;
    }
}

function setupModeSwitch() {
    const modeBtn = document.getElementById('mode-switch-btn');
    if (!modeBtn) return;
    
    modeBtn.addEventListener('click', () => {
        // Save current progress before switching
        saveProgress(false);
        localStorage.setItem('aie_mode', 'voice');
        
        // Redirect to voice mode
        window.location.href = '/build?mode=voice';
    });
}

function setupEventListeners() {
    // Form submit
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        generatePreview(); // Use generatePreview which has the timer
    });
    
    // Preview button
    document.getElementById('preview-btn').addEventListener('click', generatePreview);
    
    // Character counter
    summaryTextarea.addEventListener('input', updateCharCounter);
    
    // Skills input
    skillsInput.addEventListener('keydown', handleSkillInput);
    skillsInput.addEventListener('paste', handleSkillPaste);
    
    // Add dynamic fields
    document.getElementById('add-experience').addEventListener('click', () => addExperienceField());
    document.getElementById('add-education').addEventListener('click', () => addEducationField());
    document.getElementById('add-certification').addEventListener('click', () => addCertificationField());
    document.getElementById('add-project').addEventListener('click', () => addProjectField());
    document.getElementById('add-competency').addEventListener('click', () => addCompetencyField());
    document.getElementById('add-community').addEventListener('click', () => addCommunityField());
    
    // Mobile preview toggle
    document.getElementById('toggle-preview')?.addEventListener('click', toggleMobilePreview);
    
    // Theme change - auto rebuild if resume exists
    document.getElementById('theme-select')?.addEventListener('change', async () => {
        if (currentResumeId) {
            // Save current theme to localStorage
            const theme = document.getElementById('theme-select')?.value || 'professional';
            localStorage.setItem('aie_theme', theme);
            
            // Rebuild preview with new theme
            showLoading('Updating theme...');
            await generatePreview();
            showSuccess(`Theme updated to ${theme}!`);
        }
    });
    
    // Purchase buttons - require resume to be built first
    document.getElementById('buy-premium').addEventListener('click', () => {
        if (!currentResumeId) {
            showError('Please build your resume first by clicking "Generate Preview"');
            return;
        }
        initiatePayment('regular');
    });
    document.getElementById('buy-referral').addEventListener('click', async () => {
        if (!currentResumeId) {
            showError('Please build your resume first by clicking "Generate Preview"');
            return;
        }
        
        // Check if user already has a verified referral
        const referralCode = localStorage.getItem('aie_referral_code');
        const hasValidReferral = await validateReferralCode(referralCode);
        
        if (hasValidReferral) {
            // User has valid referral with visits, go straight to checkout
            createCheckoutSession('discount', referralCode);
        } else {
            // Show referral modal
            showReferralModal();
        }
    });
    
    // State/City autocomplete
    setupStateCityAutocomplete();
}

function setupDynamicFields() {
    // Add one empty experience and education by default
    addExperienceField();
    addEducationField();
}

// Character Counter
function updateCharCounter() {
    const count = summaryTextarea.value.length;
    summaryCount.textContent = count;
}

// Skills Management
function parseSkillsInput(raw) {
    // Split by comma or newline. No parenthetical extraction — skills are full phrases.
    if (!raw) return [];
    return [...new Set(
        raw.split(/,\s*|\n/)
           .map(s => s.trim())
           .filter(s => s.length > 0)
    )];
}

function handleSkillInput(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        const raw = e.target.value.trim();
        if (!raw) return;
        
        const newSkills = parseSkillsInput(raw);
        
        let added = false;
        for (const skill of newSkills) {
            if (!skills.includes(skill)) {
                skills.push(skill);
                added = true;
            }
        }
        
        if (added) {
            renderSkills();
        }
        e.target.value = '';
    }
}

function handleSkillPaste(e) {
    // Intercept paste to auto-split comma-separated skills
    e.preventDefault();
    const pasted = (e.clipboardData || window.clipboardData).getData('text');
    if (!pasted) return;
    
    const newSkills = parseSkillsInput(pasted);
    
    let added = false;
    for (const skill of newSkills) {
        if (!skills.includes(skill)) {
            skills.push(skill);
            added = true;
        }
    }
    
    if (added) {
        renderSkills();
    }
}

function renderSkills() {
    skillsTags.innerHTML = skills.map(skill => `
        <span class="tag">
            ${skill}
            <span class="remove-tag" onclick="removeSkill('${skill}')">×</span>
        </span>
    `).join('');
    skillsHidden.value = skills.join('|');
}

function removeSkill(skill) {
    skills = skills.filter(s => s !== skill);
    renderSkills();
}

// Experience Fields
function addExperienceField(data = {}) {
    experienceCount++;
    const container = document.getElementById('experience-list');
    const entry = document.createElement('div');
    entry.className = 'entry-item';
    entry.dataset.id = experienceCount;
    entry.innerHTML = `
        <button type="button" class="remove-entry" onclick="removeEntry(this)" title="Remove">×</button>
        <div class="field-row">
            <label>Job Title</label>
            <input type="text" name="exp_title[]" placeholder="Software Engineer" value="${data.title || ''}" autocapitalize="words" class="capitalize-first">
        </div>
        <div class="field-row">
            <label>Company</label>
            <input type="text" name="exp_company[]" class="company-input" placeholder="Type to search companies..." autocomplete="off" value="${data.company || ''}">
            <div class="company-suggestions suggestions"></div>
        </div>
        <div class="field-row">
            <label>State</label>
            <select name="exp_state[]" class="state-select">
                <option value="">Select State</option>
            </select>
        </div>
        <div class="field-row">
            <label>City</label>
            <input type="text" name="exp_city[]" class="city-input" placeholder="Select a state first" autocomplete="off" disabled value="${data.city || ''}">
            <div class="city-suggestions suggestions"></div>
        </div>
        <div class="field-row">
            <label>Dates</label>
            <input type="text" name="exp_dates[]" placeholder="Jan 2020 - Present" value="${data.dates || ''}">
        </div>
        <div class="field-row optional-field">
            <label>Job Phone <span class="optional-tag">(optional)</span></label>
            <input type="tel" name="exp_phone[]" placeholder="(555) 123-4567" value="${data.phone || ''}">
        </div>
        <div class="field-row optional-field">
            <label>Job Address <span class="optional-tag">(optional)</span></label>
            <input type="text" name="exp_address[]" placeholder="123 Main St, City, ST 12345" value="${data.address || ''}">
        </div>
        <div class="field-row">
            <label>Description</label>
            <textarea name="exp_description[]" rows="4" placeholder="Describe your responsibilities and achievements...">${data.description || ''}</textarea>
        </div>
    `;
    container.appendChild(entry);
    
    // Auto-capitalize first letter of Job Title
    const titleInput = entry.querySelector('input[name="exp_title[]"]');
    if (titleInput) {
        titleInput.addEventListener('input', function(e) {
            const val = e.target.value;
            if (val.length > 0) {
                e.target.value = val.charAt(0).toUpperCase() + val.slice(1);
            }
        });
    }
    
    // Setup company autocomplete for this new entry
    const companyInput = entry.querySelector('.company-input');
    const companySuggestions = entry.querySelector('.company-suggestions');
    setupCompanyAutocomplete(companyInput, companySuggestions);
    
    // Setup state/city autocomplete for this new entry
    const stateSelect = entry.querySelector('.state-select');
    const cityInput = entry.querySelector('.city-input');
    const citySuggestions = entry.querySelector('.city-suggestions');
    setupExperienceStateCity(stateSelect, cityInput, citySuggestions);
}

// Education Fields
function addEducationField(data = {}) {
    educationCount++;
    const container = document.getElementById('education-list');
    const entry = document.createElement('div');
    entry.className = 'entry-item';
    entry.dataset.id = educationCount;
    entry.innerHTML = `
        <button type="button" class="remove-entry" onclick="removeEntry(this)" title="Remove">×</button>
        <div class="field-row">
            <label>School / University</label>
            <input type="text" name="edu_school[]" class="uni-input" placeholder="Type to search universities..." autocomplete="off" value="${data.school || ''}">
            <div class="uni-suggestions suggestions"></div>
        </div>
        <div class="field-row">
            <label>Degree / Certificate</label>
            <select name="edu_degree[]" class="degree-select">
                <option value="">Select Degree</option>
            </select>
        </div>
        <div class="field-row">
            <label>Field of Study</label>
            <input type="text" name="edu_field[]" class="field-input" placeholder="Type to search fields..." autocomplete="off" value="${data.field || ''}">
            <div class="field-suggestions suggestions"></div>
        </div>
        <div class="field-row">
            <label>Graduation Date</label>
            <input type="text" name="edu_dates[]" placeholder="May 2020" value="${data.dates || ''}">
        </div>
    `;
    container.appendChild(entry);
    
    // Setup autocomplete for this entry
    const uniInput = entry.querySelector('.uni-input');
    const uniSuggestions = entry.querySelector('.uni-suggestions');
    setupUniversityAutocomplete(uniInput, uniSuggestions);
    
    const degreeSelect = entry.querySelector('.degree-select');
    populateDegreeDropdown(degreeSelect, data.degree || '');
    
    const fieldInput = entry.querySelector('.field-input');
    const fieldSuggestions = entry.querySelector('.field-suggestions');
    setupFieldAutocomplete(fieldInput, fieldSuggestions);
}

// Certification Fields
function addCertificationField(data = {}) {
    certificationCount++;
    const container = document.getElementById('certifications-list');
    const entry = document.createElement('div');
    entry.className = 'entry-item';
    entry.dataset.id = certificationCount;
    entry.innerHTML = `
        <button type="button" class="remove-entry" onclick="removeEntry(this)" title="Remove">×</button>
        <div class="field-row">
            <label>Certification Name</label>
            <input type="text" name="cert_name[]" placeholder="AWS Certified Solutions Architect" value="${data.name || ''}">
        </div>
        <div class="field-row">
            <label>Issuing Organization</label>
            <input type="text" name="cert_org[]" placeholder="Amazon Web Services" value="${data.org || ''}">
        </div>
        <div class="field-row">
            <label>Date Obtained</label>
            <input type="text" name="cert_date[]" placeholder="June 2023" value="${data.date || ''}">
        </div>
    `;
    container.appendChild(entry);
}

// Project Fields
function addProjectField(data = {}) {
    projectCount++;
    const container = document.getElementById('projects-list');
    const entry = document.createElement('div');
    entry.className = 'entry-item';
    entry.dataset.id = projectCount;
    entry.innerHTML = `
        <button type="button" class="remove-entry" onclick="removeEntry(this)" title="Remove">×</button>
        <div class="field-row">
            <label>Project Name</label>
            <input type="text" name="proj_name[]" placeholder="AI Orchestration Platform" value="${data.name || ''}">
        </div>
        <div class="field-row">
            <label>Tech Stack (comma-separated)</label>
            <input type="text" name="proj_tech[]" placeholder="Python, Flask, OpenAI API" value="${data.tech || ''}">
        </div>
        <div class="field-row">
            <label>Description / Bullet Points</label>
            <textarea name="proj_description[]" rows="3" placeholder="Describe the project and your contributions...">${data.description || ''}</textarea>
        </div>
        <div class="field-row">
            <label>Result / Outcome (optional)</label>
            <input type="text" name="proj_result[]" placeholder="Reduced processing time by 40%" value="${data.result || ''}">
        </div>
    `;
    container.appendChild(entry);
}

// Competency Fields
function addCompetencyField(data = {}) {
    competencyCount++;
    const container = document.getElementById('competencies-list');
    const entry = document.createElement('div');
    entry.className = 'entry-item';
    entry.dataset.id = competencyCount;
    entry.innerHTML = `
        <button type="button" class="remove-entry" onclick="removeEntry(this)" title="Remove">×</button>
        <div class="field-row">
            <label>Competency Label</label>
            <input type="text" name="comp_label[]" placeholder="Operational Leadership" value="${data.label || ''}">
        </div>
        <div class="field-row">
            <label>Description</label>
            <input type="text" name="comp_desc[]" placeholder="15+ years managing complex field operations and retail teams" value="${data.description || ''}">
        </div>
    `;
    container.appendChild(entry);
}

// Community Involvement Fields
function addCommunityField(data = {}) {
    communityCount++;
    const container = document.getElementById('community-list');
    const entry = document.createElement('div');
    entry.className = 'entry-item';
    entry.dataset.id = communityCount;
    entry.innerHTML = `
        <button type="button" class="remove-entry" onclick="removeEntry(this)" title="Remove">×</button>
        <div class="field-row">
            <label>Event / Activity</label>
            <input type="text" name="comm_event[]" placeholder="Nacogdoches 1st Annual Jaycees Mud Run" value="${data.event || ''}">
        </div>
        <div class="field-row">
            <label>Organization (optional)</label>
            <input type="text" name="comm_org[]" placeholder="Nacogdoches Jaycees" value="${data.organization || ''}">
        </div>
    `;
    container.appendChild(entry);
}

// Remove Entry
function removeEntry(btn) {
    btn.closest('.entry-item').remove();
}

// Form Submission
async function handleFormSubmit(e) {
    e.preventDefault();
    
    const formData = new FormData(form);
    
    // Collect experience data
    const experience = [];
    const expTitles = form.querySelectorAll('input[name="exp_title[]"]');
    expTitles.forEach((_, index) => {
        const title = expTitles[index]?.value;
        if (title) {
            experience.push({
                title: title,
                company: form.querySelectorAll('input[name="exp_company[]"]')[index]?.value || '',
                state: form.querySelectorAll('select[name="exp_state[]"]')[index]?.value || '',
                city: form.querySelectorAll('input[name="exp_city[]"]')[index]?.value || '',
                dates: form.querySelectorAll('input[name="exp_dates[]"]')[index]?.value || '',
                phone: form.querySelectorAll('input[name="exp_phone[]"]')[index]?.value || '',
                address: form.querySelectorAll('input[name="exp_address[]"]')[index]?.value || '',
                description: form.querySelectorAll('textarea[name="exp_description[]"]')[index]?.value || ''
            });
        }
    });
    
    // Collect education data
    const education = [];
    const eduSchools = form.querySelectorAll('input[name="edu_school[]"]');
    eduSchools.forEach((_, index) => {
        const school = eduSchools[index]?.value;
        if (school) {
            education.push({
                school: school,
                degree: form.querySelectorAll('select[name="edu_degree[]"]')[index]?.value || '',
                field: form.querySelectorAll('input[name="edu_field[]"]')[index]?.value || '',
                dates: form.querySelectorAll('input[name="edu_dates[]"]')[index]?.value || ''
            });
        }
    });
    
    // Collect project data
    const projects = [];
    const projNames = form.querySelectorAll('input[name="proj_name[]"]');
    projNames.forEach((_, index) => {
        const name = projNames[index]?.value;
        if (name) {
            projects.push({
                name: name,
                tech: form.querySelectorAll('input[name="proj_tech[]"]')[index]?.value || '',
                description: form.querySelectorAll('textarea[name="proj_description[]"]')[index]?.value || '',
                result: form.querySelectorAll('input[name="proj_result[]"]')[index]?.value || ''
            });
        }
    });
    
    // Collect competency data
    const competencies = [];
    const compLabels = form.querySelectorAll('input[name="comp_label[]"]');
    compLabels.forEach((_, index) => {
        const label = compLabels[index]?.value;
        if (label) {
            competencies.push({
                label: label,
                description: form.querySelectorAll('input[name="comp_desc[]"]')[index]?.value || ''
            });
        }
    });
    
    // Collect community involvement data
    const community = [];
    const commEvents = form.querySelectorAll('input[name="comm_event[]"]');
    commEvents.forEach((_, index) => {
        const event = commEvents[index]?.value;
        if (event) {
            community.push({
                event: event,
                organization: form.querySelectorAll('input[name="comm_org[]"]')[index]?.value || ''
            });
        }
    });
    
    // Collect certification data
    const certifications = [];
    const certNames = form.querySelectorAll('input[name="cert_name[]"]');
    certNames.forEach((_, index) => {
        const name = certNames[index]?.value;
        if (name) {
            certifications.push({
                name: name,
                organization: form.querySelectorAll('input[name="cert_org[]"]')[index]?.value || '',
                date: form.querySelectorAll('input[name="cert_date[]"]')[index]?.value || ''
            });
        }
    });
    
    // Update form data with JSON
    formData.set('experience', JSON.stringify(experience));
    formData.set('education', JSON.stringify(education));
    formData.set('projects', JSON.stringify(projects));
    formData.set('competencies', JSON.stringify(competencies));
    formData.set('community', JSON.stringify(community));
    formData.set('certifications', JSON.stringify(certifications));
    // Pass voice session so the server builds authoritatively from stored data
    const _vsBuild = new URLSearchParams(window.location.search).get('voice_session');
    if (_vsBuild) formData.set('voice_session', _vsBuild);
    
    try {
        showLoading('Building your resume...');
        
        const response = await fetch('/api/build', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            showError(result.detail?.[0]?.msg || result.error || `Server error: ${response.status}`);
            return;
        }
        
        if (result.success) {
            currentResumeId = result.resume_id;
            previewContainer.innerHTML = result.preview_html;
            enableDownloadButtons();
            showSuccess('Resume built successfully!');
        } else {
            showError(result.error || 'Failed to build resume. Please try again.');
        }
    } catch (error) {
        console.error('[AIE ResuMaker] Build error:', error);
        showError('Error: ' + (error.message || 'Unknown error'));
    } finally {
        hideLoading();
    }
}

// Preview Generation with 3-Second Timer
async function generatePreview() {
    // Don't prevent default - this is called from button click, not form submit
    // e.preventDefault(); REMOVED
    
    // First build the resume
    const formData = new FormData(form);
    
    // Collect data (same as handleFormSubmit)
    const experience = [];
    const expTitles = form.querySelectorAll('input[name="exp_title[]"]');
    expTitles.forEach((_, index) => {
        const title = expTitles[index]?.value;
        if (title) {
            experience.push({
                title: title,
                company: form.querySelectorAll('input[name="exp_company[]"]')[index]?.value || '',
                state: form.querySelectorAll('select[name="exp_state[]"]')[index]?.value || '',
                city: form.querySelectorAll('input[name="exp_city[]"]')[index]?.value || '',
                dates: form.querySelectorAll('input[name="exp_dates[]"]')[index]?.value || '',
                phone: form.querySelectorAll('input[name="exp_phone[]"]')[index]?.value || '',
                address: form.querySelectorAll('input[name="exp_address[]"]')[index]?.value || '',
                description: form.querySelectorAll('textarea[name="exp_description[]"]')[index]?.value || ''
            });
        }
    });
    
    const education = [];
    const eduSchools = form.querySelectorAll('input[name="edu_school[]"]');
    eduSchools.forEach((_, index) => {
        const school = eduSchools[index]?.value;
        if (school) {
            education.push({
                school: school,
                degree: form.querySelectorAll('select[name="edu_degree[]"]')[index]?.value || '',
                field: form.querySelectorAll('input[name="edu_field[]"]')[index]?.value || '',
                dates: form.querySelectorAll('input[name="edu_dates[]"]')[index]?.value || ''
            });
        }
    });
    
    const projects = [];
    const projNames = form.querySelectorAll('input[name="proj_name[]"]');
    projNames.forEach((_, index) => {
        const name = projNames[index]?.value;
        if (name) {
            projects.push({
                name: name,
                tech: form.querySelectorAll('input[name="proj_tech[]"]')[index]?.value || '',
                description: form.querySelectorAll('textarea[name="proj_description[]"]')[index]?.value || '',
                result: form.querySelectorAll('input[name="proj_result[]"]')[index]?.value || ''
            });
        }
    });
    
    const competencies = [];
    const compLabels = form.querySelectorAll('input[name="comp_label[]"]');
    compLabels.forEach((_, index) => {
        const label = compLabels[index]?.value;
        if (label) {
            competencies.push({
                label: label,
                description: form.querySelectorAll('input[name="comp_desc[]"]')[index]?.value || ''
            });
        }
    });
    
    const community = [];
    const commEvents = form.querySelectorAll('input[name="comm_event[]"]');
    commEvents.forEach((_, index) => {
        const event = commEvents[index]?.value;
        if (event) {
            community.push({
                event: event,
                organization: form.querySelectorAll('input[name="comm_org[]"]')[index]?.value || ''
            });
        }
    });
    
    const certifications = [];
    const certNames = form.querySelectorAll('input[name="cert_name[]"]');
    certNames.forEach((_, index) => {
        const name = certNames[index]?.value;
        if (name) {
            certifications.push({
                name: name,
                organization: form.querySelectorAll('input[name="cert_org[]"]')[index]?.value || '',
                date: form.querySelectorAll('input[name="cert_date[]"]')[index]?.value || ''
            });
        }
    });
    
    formData.set('experience', JSON.stringify(experience));
    formData.set('education', JSON.stringify(education));
    formData.set('projects', JSON.stringify(projects));
    formData.set('competencies', JSON.stringify(competencies));
    formData.set('community', JSON.stringify(community));
    formData.set('certifications', JSON.stringify(certifications));
    // Pass voice session so the server builds authoritatively from stored data
    const _vsPreview = new URLSearchParams(window.location.search).get('voice_session');
    if (_vsPreview) formData.set('voice_session', _vsPreview);
    
    try {
        showLoading('Building preview...');
        
        const response = await fetch('/api/build', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            showError(result.detail?.[0]?.msg || result.error || `Server error: ${response.status}`);
            return;
        }
        
        if (result.success) {
            currentResumeId = result.resume_id;
            enableDownloadButtons();
            
            // Show CLEAN preview first
            previewContainer.innerHTML = result.preview_html;
            showSuccess('Preview loaded! Viewing for 3 seconds...');
            
            // Start 3-second timer
            let secondsLeft = 3;
            const timerElement = document.createElement('div');
            timerElement.className = 'preview-timer';
            timerElement.style.cssText = 'position:fixed;top:10px;right:10px;background:#ff6b6b;color:white;padding:8px 16px;border-radius:4px;font-weight:bold;z-index:10000;font-size:14px;';
            document.body.appendChild(timerElement);
            
            const timer = setInterval(() => {
                timerElement.textContent = `Clean preview: ${secondsLeft}s`;
                secondsLeft--;
                
                if (secondsLeft < 0) {
                    clearInterval(timer);
                    timerElement.remove();
                    degradePreview(currentResumeId);
                }
            }, 1000);
            
        } else {
            showError(result.error || 'Failed to build preview. Please try again.');
        }
    } catch (error) {
        showError('Network error. Please check your connection.');
    } finally {
        hideLoading();
    }
}

// Degrade preview after timer expires
async function degradePreview(resumeId) {
    try {
        showLoading('Securing preview...');
        
        const response = await fetch('/api/preview-timer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                resume_id: resumeId
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Keep the preview header/buttons, only replace the preview content
            const previewContainer = document.getElementById('preview-container');
            previewContainer.innerHTML = `
                <div style="position:relative;text-align:center;">
                    <img src="${result.watermarked_image}" 
                         style="max-width:100%;border:1px solid #ccc;"
                         oncontextmenu="return false;"
                         draggable="false">
                    <div style="margin-top:15px;padding:15px;background:#f8f9fa;border-radius:8px;">
                        <p style="font-size:16px;color:#333;margin-bottom:10px;">
                            <strong>👆 This is a watermarked sample</strong>
                        </p>
                        <p style="font-size:14px;color:#666;margin-bottom:15px;">
                            To get the highest quality format, click Purchase below
                        </p>
                        <p style="font-size:13px;color:#3b82f6;margin-bottom:10px;">
                            🎁 Give $5, Get $5! 💸 → Share & Save with Friends!
                        </p>
                        <button id="buy-premium-inline" class="btn-primary" style="font-size:16px;padding:12px 24px;">
                            🚀 Purchase Resume ($9.99)
                        </button>
                    </div>
                </div>
            `;
            
            // Re-attach payment handler for inline button - defaults to regular price
            document.getElementById('buy-premium-inline').addEventListener('click', () => initiatePayment('regular'));
            
            showSuccess('Preview secured. Upgrade for full quality!');
        } else {
            showError('Failed to secure preview. Please try again.');
        }
    } catch (error) {
        showError('Error securing preview.');
    } finally {
        hideLoading();
    }
}

// Download TXT (Free) - NOW REQUIRES PAYMENT
async function downloadTxt() {
    if (!currentResumeId) return;

    // Check if paid
    try {
        const response = await fetch(`/api/check-payment/${currentResumeId}`);
        const data = await response.json();

        if (!data.paid) {
            showError('Please upgrade to Premium to download your resume.');
            const buyBtn = document.getElementById('buy-premium');
            if (buyBtn) buyBtn.style.display = 'inline-block';
            return;
        }
    } catch (error) {
        console.error('Error checking payment:', error);
    }

    // Check edit count
    if (!canEdit()) {
        const shouldRepurchase = confirm('You have used all 5 edits. Would you like to repurchase for 5 more edits?');
        if (shouldRepurchase) {
            initiatePayment();
        }
        return;
    }

    // Use one edit
    if (!showEditDialog()) {
        return;
    }

    useEdit();

    // Generate plain text version
    const formData = new FormData(form);
    const text = generatePlainText(formData);

    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `resume_${currentResumeId}.txt`;
    a.click();
    URL.revokeObjectURL(url);

    showSuccess(`Downloaded! You have ${Math.max(0, MAX_EDITS - getEditCount())} edit${getEditCount() !== MAX_EDITS - 1 ? 's' : ''} remaining.`);
}

function generatePlainText(formData) {
    const name = formData.get('full_name');
    const email = formData.get('email');
    const phone = formData.get('phone');
    const location = formData.get('location');
    const summary = formData.get('summary');
    const skills = formData.get('skills');
    
    let text = `${name}\n`;
    text += `${email}${phone ? ' | ' + phone : ''}${location ? ' | ' + location : ''}\n`;
    text += `\nPROFESSIONAL SUMMARY\n${summary}\n`;
    text += `\nSKILLS\n${skills}\n`;
    
    // Add experience
    const expTitles = form.querySelectorAll('input[name="exp_title[]"]');
    if (expTitles.length > 0) {
        text += `\nEXPERIENCE\n`;
        expTitles.forEach((_, index) => {
            const title = expTitles[index]?.value;
            const company = form.querySelectorAll('input[name="exp_company[]"]')[index]?.value;
            const dates = form.querySelectorAll('input[name="exp_dates[]"]')[index]?.value;
            const phone = form.querySelectorAll('input[name="exp_phone[]"]')[index]?.value;
            const address = form.querySelectorAll('input[name="exp_address[]"]')[index]?.value;
            const desc = form.querySelectorAll('textarea[name="exp_description[]"]')[index]?.value;
            
            if (title) {
                text += `${title}${company ? ' | ' + company : ''}\n`;
                if (dates) text += `${dates}\n`;
                if (phone) text += `Phone: ${phone}\n`;
                if (address) text += `Address: ${address}\n`;
                if (desc) text += `${desc}\n`;
                text += `\n`;
            }
        });
    }
    
    // Add education
    const eduSchools = form.querySelectorAll('input[name="edu_school[]"]');
    if (eduSchools.length > 0) {
        text += `\nEDUCATION\n`;
        eduSchools.forEach((_, index) => {
            const school = eduSchools[index]?.value;
            const degree = form.querySelectorAll('input[name="edu_degree[]"]')[index]?.value;
            const dates = form.querySelectorAll('input[name="edu_dates[]"]')[index]?.value;
            
            if (school) {
                text += `${school}${degree ? ' | ' + degree : ''}\n`;
                if (dates) text += `${dates}\n`;
                text += `\n`;
            }
        });
    }
    
    return text;
}

// Stripe Payment
async function initiatePayment(tier = 'regular') {
    if (!currentResumeId) {
        showError('Please build your resume first');
        return;
    }
    
    // If clicking student button, show email input modal
    if (tier === 'student') {
        showStudentEmailModal();
        return;
    }
    
    // Proceed with regular or discount payment
    createCheckoutSession(tier);
}

function showStudentEmailModal() {
    const modal = document.createElement('div');
    modal.id = 'student-email-modal';
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.7); display: flex; align-items: center;
        justify-content: center; z-index: 10000;
    `;
    
    modal.innerHTML = `
        <div style="background: white; padding: 30px; border-radius: 12px; max-width: 450px; width: 90%; text-align: center; position: relative;">
            <button id="close-modal" style="position: absolute; top: 15px; right: 15px; background: none; border: none; font-size: 24px; cursor: pointer;">×</button>
            
            <div style="margin-bottom: 20px;">
                <img src="/static/images/logo-student.png" alt="Student" style="width: 80px; height: 80px;">
            </div>
            
            <h3 style="color: #1e3a8a; margin-bottom: 10px;">🎓 Student Verification</h3>
            <p style="color: #666; margin-bottom: 20px; font-size: 14px;">
                Enter your .edu email to unlock student pricing ($4.99)
            </p>
            
            <div id="email-step">
                <input type="email" id="student-email-input" placeholder="yourname@university.edu" 
                       style="width: 100%; padding: 12px; font-size: 16px; border: 2px solid #ddd; border-radius: 8px; margin-bottom: 15px;">
                <button id="send-link-btn" style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 14px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; width: 100%; font-weight: bold;">
                    Send Verification Link
                </button>
            </div>
            
            <div id="success-step" style="display: none;">
                <p style="color: #16a34a; font-size: 16px; margin-bottom: 15px;">
                    ✅ Verification link sent!
                </p>
                <p style="color: #666; font-size: 14px; margin-bottom: 10px;">
                    Check your .edu email inbox and click the verification link.
                </p>
                <p style="color: #dc2626; font-size: 13px; margin-bottom: 15px; font-weight: 600;">
                    ⚠️ Don't see it? Check your spam/junk folder!
                </p>
                <p style="color: #94a3b8; font-size: 12px;">
                    After verifying, return here and click Purchase again.
                </p>
            </div>
            
            <div id="error-msg" style="color: #dc2626; margin-top: 10px; font-size: 14px; display: none;"></div>
            
            <p style="margin-top: 15px; font-size: 13px; color: #94a3b8;">
                <a href="#" id="pay-regular-link" style="color: #64748b;">Pay full price ($9.99) instead</a>
            </p>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Close modal
    document.getElementById('close-modal').addEventListener('click', () => {
        document.body.removeChild(modal);
    });
    
    // Pay regular price link
    document.getElementById('pay-regular-link').addEventListener('click', (e) => {
        e.preventDefault();
        document.body.removeChild(modal);
        createCheckoutSession(false);
    });
    
    // Send verification link
    document.getElementById('send-link-btn').addEventListener('click', async () => {
        const emailInput = document.getElementById('student-email-input');
        const email = emailInput.value.trim().toLowerCase();
        const errorDiv = document.getElementById('error-msg');
        const btn = document.getElementById('send-link-btn');
        
        // Validate email (temporarily removed .edu check for testing)
        // if (!email.endsWith('.edu')) {
        //     errorDiv.textContent = 'Please enter a valid .edu email address';
        //     errorDiv.style.display = 'block';
        //     return;
        // }
        
        btn.disabled = true;
        btn.textContent = 'Sending...';
        
        try {
            const response = await fetch('/api/verify-edu', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            
            const data = await response.json();
            
            if (data.success) {
                document.getElementById('email-step').style.display = 'none';
                document.getElementById('success-step').style.display = 'block';
                
                // Store token for later use
                if (data.dev_token) {
                    localStorage.setItem('aie_student_token', data.dev_token);
                    console.log('DEV: Verification token:', data.dev_token);
                }
            } else {
                errorDiv.textContent = data.error || 'Failed to send verification link';
                errorDiv.style.display = 'block';
                btn.disabled = false;
                btn.textContent = 'Send Verification Link';
            }
        } catch (e) {
            errorDiv.textContent = 'Network error. Please try again.';
            errorDiv.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Send Verification Link';
        }
    });
}

async function createCheckoutSession(tier = 'regular', referralCode = '') {
    try {
        // If student purchase, check if verified
        let studentToken = null;
        if (tier === 'student') {
            studentToken = localStorage.getItem('aie_student_token');
            if (!studentToken) {
                showError('Please verify your student status first. Click the Student $4.99 button.');
                return;
            }
        }
        
        // Get referral code if not provided
        if (!referralCode) {
            referralCode = localStorage.getItem('aie_referral_code') || '';
        }
        
        const response = await fetch('/api/create-checkout-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                resume_id: currentResumeId,
                tier: tier,
                student_token: studentToken,
                referral_code: referralCode
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        // Redirect to Stripe Checkout
        window.location.href = data.url;
        
    } catch (error) {
        console.error('Payment error:', error);
        showError('Failed to initiate payment. Please try again.');
    }
}

// Student Verification Modal
let verifiedStudentEmail = null;

function showStudentVerificationModal(email) {
    const modal = document.createElement('div');
    modal.id = 'student-verification-modal';
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.7); display: flex; align-items: center;
        justify-content: center; z-index: 10000;
    `;
    
    modal.innerHTML = `
        <div style="background: white; padding: 30px; border-radius: 12px; max-width: 400px; width: 90%; text-align: center; position: relative;">
            <h3 style="color: #1e3a8a; margin-bottom: 10px;">🎁 Give $5, Get $5!</h3>
            <p style="margin-bottom: 20px; color: #666;">Share your link with a friend and you both save $5!</p>
            
            <div id="verification-step-1">
                <p style="font-size: 14px; margin-bottom: 15px;">We'll send a code to:<br><strong>${email}</strong></p>
                <button id="send-code-btn" style="background: #3b82f6; color: white; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; width: 100%;">
                    Send Verification Code
                </button>
                <button id="skip-verification" style="background: none; border: none; color: #666; margin-top: 15px; cursor: pointer; text-decoration: underline;">
                    Pay Full Price ($9.99)
                </button>
            </div>
            
            <div id="verification-step-2" style="display: none;">
                <p style="font-size: 14px; margin-bottom: 15px;">Enter the 6-digit code sent to <strong>${email}</strong></p>
                <input type="text" id="verification-code" maxlength="6" placeholder="000000" style="width: 100%; padding: 12px; font-size: 18px; text-align: center; letter-spacing: 8px; border: 2px solid #ddd; border-radius: 8px; margin-bottom: 15px;">
                <button id="verify-code-btn" style="background: #10b981; color: white; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; width: 100%;">
                    Verify & Get $4.99 Pricing
                </button>
                <p id="verification-error" style="color: #dc2626; margin-top: 10px; display: none;"></p>
            </div>
            
            <button id="close-modal" style="position: absolute; top: 15px; right: 15px; background: none; border: none; font-size: 24px; cursor: pointer;">&times;</button>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Close modal
    document.getElementById('close-modal').addEventListener('click', () => {
        document.body.removeChild(modal);
    });
    
    // Skip verification - pay full price
    document.getElementById('skip-verification').addEventListener('click', () => {
        document.body.removeChild(modal);
        createCheckoutSession(false);
    });
    
    // Send code
    document.getElementById('send-code-btn').addEventListener('click', async () => {
        const btn = document.getElementById('send-code-btn');
        btn.disabled = true;
        btn.textContent = 'Sending...';
        
        try {
            const response = await fetch('/api/verify-edu', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Auto-verified test email - skip to checkout
                if (data.auto_verified) {
                    document.body.removeChild(modal);
                    createCheckoutSession(true);
                    return;
                }
                
                document.getElementById('verification-step-1').style.display = 'none';
                document.getElementById('verification-step-2').style.display = 'block';
                
                // For development - show code
                if (data.dev_code) {
                    console.log('DEV: Verification code:', data.dev_code);
                }
            } else {
                alert(data.error || 'Failed to send code');
                btn.disabled = false;
                btn.textContent = 'Send Verification Code';
            }
        } catch (e) {
            alert('Error sending code. Please try again.');
            btn.disabled = false;
            btn.textContent = 'Send Verification Code';
        }
    });
    
    // Verify code
    document.getElementById('verify-code-btn').addEventListener('click', async () => {
        const code = document.getElementById('verification-code').value;
        const btn = document.getElementById('verify-code-btn');
        const errorEl = document.getElementById('verification-error');
        
        btn.disabled = true;
        btn.textContent = 'Verifying...';
        errorEl.style.display = 'none';
        
        try {
            const response = await fetch('/api/verify-edu-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, code })
            });
            
            const data = await response.json();
            
            if (data.verified) {
                verifiedStudentEmail = email;
                document.body.removeChild(modal);
                createCheckoutSession(true);
            } else {
                errorEl.textContent = data.error || 'Invalid code';
                errorEl.style.display = 'block';
                btn.disabled = false;
                btn.textContent = 'Verify & Get $4.99 Pricing';
            }
        } catch (e) {
            errorEl.textContent = 'Error verifying code. Please try again.';
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Verify & Get $4.99 Pricing';
        }
    });
}

// Referral System - Real Tracking
// Get user's email for referral tracking
function getUserEmail() {
    return document.querySelector('input[name="email"]')?.value || localStorage.getItem('aie_user_email') || '';
}

// Create or get referral code from backend
async function getOrCreateReferralCode() {
    let code = localStorage.getItem('aie_referral_code');
    
    if (!code) {
        try {
            const email = getUserEmail();
            const response = await fetch('/api/referral/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email || 'anonymous' })
            });
            
            const data = await response.json();
            if (data.success) {
                code = data.code;
                localStorage.setItem('aie_referral_code', code);
                localStorage.setItem('aie_referral_link', data.link);
            }
        } catch (error) {
            console.error('[REFERRAL] Error creating code:', error);
            // Fallback: generate client-side code
            code = Math.random().toString(36).substring(2, 10).toUpperCase();
            localStorage.setItem('aie_referral_code', code);
        }
    }
    
    return code;
}

// Validate referral code has visits
async function validateReferralCode(code) {
    if (!code) return false;
    
    try {
        const response = await fetch(`/api/referral/stats/${code}`);
        if (response.ok) {
            const data = await response.json();
            return data.visits > 0 || data.reward_unlocked;
        }
    } catch (error) {
        console.error('[REFERRAL] Error validating code:', error);
    }
    
    return false;
}

// Generate industry-specific share message
function getShareMessage(industry) {
    const messages = {
        'tech': "Just built my dev resume with AI in 10 mins — got callbacks in 2 days. Here's $5 off if you want to try it too: ",
        'healthcare': "Used this AI resume builder for my nursing resume — HR called back same day. $5 off for you: ",
        'finance': "Built a professional finance resume in minutes with AI. Way easier than Word templates. Here's $5 off: ",
        'education': "Created my teaching resume with AI — saved hours of formatting. $5 off if you want to try: ",
        'sales': "Just made a killer sales resume with AI. Took 10 mins and looks sharp. $5 off for you: ",
        'marketing': "Built a marketing resume that actually stands out. AI did the heavy lifting. $5 off: ",
        'engineering': "Engineering resume built with AI — formatted perfectly for ATS. Here's $5 off: ",
        'retail': "Made a professional retail management resume in 10 minutes with AI. $5 off if you need one too: ",
        'food_service': "Built a restaurant management resume with AI — looks way more professional. $5 off: ",
        'construction': "Created my construction resume with AI. Clean format, professional look. $5 off for you: ",
        'transportation': "Just built a CDL/professional driver resume with AI. Took no time at all. $5 off: ",
        'general': "Just built a professional resume with AI in 10 minutes — looks incredible. Here's $5 off if you want to try: "
    };
    
    return messages[industry] || messages['general'];
}

// Get user's industry from form
function getUserIndustry() {
    return document.querySelector('select[name="industry"]')?.value || 'general';
}

// New Referral Modal with Real Tracking
async function showReferralModal() {
    const code = await getOrCreateReferralCode();
    const referralLink = `${window.location.origin}/build?ref=${code}`;
    const industry = getUserIndustry();
    const shareMessage = getShareMessage(industry);
    const fullShareText = shareMessage + referralLink;
    
    // Get stats from backend
    let stats = { visits: 0, conversions: 0, reward_unlocked: false };
    try {
        const response = await fetch(`/api/referral/stats/${code}`);
        if (response.ok) {
            stats = await response.json();
        }
    } catch (e) {
        console.error('[REFERRAL] Error fetching stats:', e);
    }
    
    const modal = document.createElement('div');
    modal.id = 'referral-modal';
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.8); display: flex; align-items: center;
        justify-content: center; z-index: 10000;
    `;
    
    modal.innerHTML = `
        <div style="background: white; padding: 30px; border-radius: 16px; max-width: 500px; width: 90%; position: relative;">
            <button id="close-referral-modal" style="position: absolute; top: 15px; right: 15px; background: none; border: none; font-size: 24px; cursor: pointer;">×</button>
            
            <div style="text-align: center; margin-bottom: 20px;">
                <div style="font-size: 48px; margin-bottom: 10px;">🎁</div>
                <h3 style="color: #1e3a8a; margin-bottom: 5px;">Give $5, Get $5</h3>
                <p style="color: #666; font-size: 14px;">Share with a friend and you both save!</p>
            </div>
            
            <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
                <div style="display: flex; justify-content: space-around; text-align: center;">
                    <div>
                        <div style="font-size: 28px; font-weight: bold;">${stats.visits || 0}</div>
                        <div style="font-size: 12px; opacity: 0.9;">Link Views</div>
                    </div>
                    <div>
                        <div style="font-size: 28px; font-weight: bold;">${stats.conversions || 0}</div>
                        <div style="font-size: 12px; opacity: 0.9;">Friends Helped</div>
                    </div>
                    <div>
                        <div style="font-size: 28px; font-weight: bold;">${stats.reward_unlocked ? '✅' : '🔒'}</div>
                        <div style="font-size: 12px; opacity: 0.9;">$4.99 Unlocked</div>
                    </div>
                </div>
            </div>
            
            <div style="background: #f0f4ff; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <div style="font-size: 12px; color: #666; margin-bottom: 5px;">Your Referral Link:</div>
                <div style="display: flex; gap: 10px;">
                    <input type="text" id="referral-link" value="${referralLink}" readonly style="flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px;">
                    <button id="copy-referral-link" style="background: #1e3a8a; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; font-size: 13px;">Copy</button>
                </div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <div style="font-size: 13px; color: #666; margin-bottom: 10px; font-weight: 600;">Quick Share:</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
                    <button id="share-native" style="display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border: 2px solid #1e3a8a; background: white; color: #1e3a8a; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;">
                        <span>📱</span> Share
                    </button>
                    <button id="share-sms" style="display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border: 2px solid #25d366; background: white; color: #25d366; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;">
                        <span>✉️</span> SMS
                    </button>
                    <button id="share-whatsapp" style="display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border: 2px solid #25d366; background: white; color: #25d366; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;">
                        <span>💬</span> WhatsApp
                    </button>
                </div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <div style="font-size: 13px; color: #666; margin-bottom: 10px; font-weight: 600;">Social Media:</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <button id="share-x" style="display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border: 2px solid #000; background: #000; color: #fff; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;">
                        <span>🐦</span> X / Twitter
                    </button>
                    <button id="share-facebook" style="display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border: 2px solid #4267B2; background: white; color: #4267B2; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;">
                        <span>👥</span> Facebook
                    </button>
                    <button id="share-linkedin" style="display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border: 2px solid #0077b5; background: white; color: #0077b5; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;">
                        <span>💼</span> LinkedIn
                    </button>
                    <button id="share-email" style="display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border: 2px solid #ea4335; background: white; color: #ea4335; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600;">
                        <span>✉️</span> Email
                    </button>
                </div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <div style="font-size: 13px; color: #666; margin-bottom: 10px; font-weight: 600;">In-Person Share:</div>
                <button id="share-qr" style="width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px; border: 2px solid #1e3a8a; background: white; color: #1e3a8a; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600;">
                    <span>📱</span> Show QR Code
                </button>
                <div id="qr-code-container" style="display: none; text-align: center; margin-top: 15px;">
                    <div style="font-size: 12px; color: #666; margin-bottom: 8px;">Have your friend scan this:</div>
                    <div id="qr-code-display" style="display: inline-block; padding: 10px; background: white; border: 2px solid #1e3a8a; border-radius: 8px;">
                        <!-- QR code will be inserted here -->
                    </div>
                    <div style="margin-top: 8px; font-size: 12px; color: #666;">
                        <button id="download-qr" style="background: #f0f4ff; border: 1px solid #1e3a8a; color: #1e3a8a; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;">Save to Photos</button>
                    </div>
                </div>
            </div>
            
            <div style="background: #f8fafc; padding: 12px; border-radius: 8px; margin-bottom: 15px;">
                <div style="font-size: 12px; color: #475569; line-height: 1.5;">
                    <strong>How it works:</strong><br>
                    1. Share your link with a friend<br>
                    2. Friend visits the link (we track it)<br>
                    3. You unlock $4.99 pricing<br>
                    4. Friend also gets $5 off their purchase
                </div>
            </div>
            
            <div style="text-align: center; font-size: 12px; color: #94a3b8;">
                ${stats.visits > 0 && !stats.reward_unlocked ? 'Your link has been viewed! Make sure your friend builds a resume to unlock your discount.' : ''}
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';
    
    // Close modal
    document.getElementById('close-referral-modal').addEventListener('click', () => {
        document.body.removeChild(modal);
        document.body.style.overflow = '';
    });
    
    // Copy link
    document.getElementById('copy-referral-link').addEventListener('click', async () => {
        const linkInput = document.getElementById('referral-link');
        linkInput.select();
        document.execCommand('copy');
        const btn = document.getElementById('copy-referral-link');
        btn.textContent = '✓ Copied!';
        setTimeout(() => btn.textContent = 'Copy', 2000);
        
        // Track that user shared
        try {
            await fetch('/api/referral/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            });
        } catch (e) {
            console.error('[REFERRAL] Error tracking:', e);
        }
        
        showSuccess('Link copied! Share it with a friend to unlock $4.99.');
    });
    
    // Native Share (mobile)
    document.getElementById('share-native').addEventListener('click', async () => {
        if (navigator.share) {
            try {
                await navigator.share({
                    title: 'AI Resume Builder - $5 Off',
                    text: fullShareText,
                    url: referralLink
                });
                
                // Track share
                await fetch('/api/referral/track', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: code })
                });
                
                showSuccess('Shared! Your friend will get $5 off too.');
            } catch (err) {
                console.log('Share cancelled or failed:', err);
            }
        } else {
            showError('Native sharing not supported on this device. Try copying the link instead.');
        }
    });
    
    // SMS
    document.getElementById('share-sms').addEventListener('click', async () => {
        window.open(`sms:?body=${encodeURIComponent(fullShareText)}`);
        
        // Track
        try {
            await fetch('/api/referral/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            });
        } catch (e) {
            console.error('[REFERRAL] Error tracking SMS:', e);
        }
    });
    
    // WhatsApp
    document.getElementById('share-whatsapp').addEventListener('click', async () => {
        window.open(`https://wa.me/?text=${encodeURIComponent(fullShareText)}`);
        
        // Track
        try {
            await fetch('/api/referral/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            });
        } catch (e) {
            console.error('[REFERRAL] Error tracking WhatsApp:', e);
        }
    });
    
    // X / Twitter
    document.getElementById('share-x').addEventListener('click', async () => {
        window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(fullShareText)}`);
        
        try {
            await fetch('/api/referral/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            });
        } catch (e) {
            console.error('[REFERRAL] Error tracking X:', e);
        }
    });
    
    // Facebook
    document.getElementById('share-facebook').addEventListener('click', async () => {
        window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(referralLink)}&quote=${encodeURIComponent(shareMessage)}`);
        
        try {
            await fetch('/api/referral/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            });
        } catch (e) {
            console.error('[REFERRAL] Error tracking Facebook:', e);
        }
    });
    
    // LinkedIn
    document.getElementById('share-linkedin').addEventListener('click', async () => {
        window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(referralLink)}&summary=${encodeURIComponent(shareMessage)}`);
        
        try {
            await fetch('/api/referral/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            });
        } catch (e) {
            console.error('[REFERRAL] Error tracking LinkedIn:', e);
        }
    });
    
    // Email
    document.getElementById('share-email').addEventListener('click', async () => {
        const subject = "Give $5, Get $5 - AI Resume Builder";
        const body = `${shareMessage}\n\n${referralLink}\n\nThis link gives you $5 off when you build your resume. I get $5 off too — win-win!`;
        window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
        
        try {
            await fetch('/api/referral/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            });
        } catch (e) {
            console.error('[REFERRAL] Error tracking Email:', e);
        }
    });
    
    // QR Code
    document.getElementById('share-qr').addEventListener('click', async () => {
        const qrContainer = document.getElementById('qr-code-container');
        const qrDisplay = document.getElementById('qr-code-display');
        
        if (qrContainer.style.display === 'none') {
            qrContainer.style.display = 'block';
            
            // Generate QR code using Google Charts API
            const qrUrl = `https://chart.googleapis.com/chart?cht=qr&chs=200x200&chld=L|0&chl=${encodeURIComponent(referralLink)}`;
            qrDisplay.innerHTML = `<img src="${qrUrl}" alt="Referral QR Code" style="width: 200px; height: 200px;">`;
            
            // Track QR view
            try {
                await fetch('/api/referral/track', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: code })
                });
            } catch (e) {
                console.error('[REFERRAL] Error tracking QR:', e);
            }
            
            // Download QR handler
            document.getElementById('download-qr').addEventListener('click', () => {
                const link = document.createElement('a');
                link.href = qrUrl;
                link.download = `resumaker-referral-${code}.png`;
                link.click();
            });
        } else {
            qrContainer.style.display = 'none';
        }
    });
}

// Check referral on page load - track visits
async function checkReferral() {
    const urlParams = new URLSearchParams(window.location.search);
    const refCode = urlParams.get('ref');
    
    if (refCode) {
        console.log('[REFERRAL] Code detected:', refCode);
        
        // Track visit to backend
        try {
            const response = await fetch('/api/referral/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: refCode })
            });
            
            if (response.ok) {
                const data = await response.json();
                console.log('[REFERRAL] Visit tracked:', data);
            }
        } catch (error) {
            console.error('[REFERRAL] Error tracking visit:', error);
        }
        
        // Show welcome message to referred user
        setTimeout(() => {
            showSuccess('Welcome! You were referred by a friend. Build your resume and share your own link to save $5.');
        }, 1500);
    }
}

// Old functions removed - replaced with real tracking above

// UI Helpers
function showLoading(message) {
    previewContainer.innerHTML = `<div class="loading">${message}</div>`;
}

function hideLoading() {
    // Loading removed by other functions
}

function showSuccess(message) {
    // Could add toast notification
    console.log('Success:', message);
}

function showError(message) {
    // Could add toast notification
    console.error('Error:', message);
    alert(message);
}

function enableDownloadButtons() {
    // Enable premium button after build
    const buyBtn = document.getElementById('buy-premium');
    if (buyBtn) {
        buyBtn.disabled = false;
        buyBtn.style.display = 'inline-block';
    }
    const referralBtn = document.getElementById('buy-referral');
    if (referralBtn) {
        referralBtn.disabled = false;
    }
}

function toggleMobilePreview() {
    document.getElementById('preview-section').classList.toggle('active');
}

// O*NET Job Title Autocomplete
function setupJobAutocomplete() {
    // Setup job title autocomplete
    setupAutocomplete('job-title', 'job-suggestions', '/api/jobs/search', (item) => {
        return {
            text: item.title,
            value: item.title,
            extra: item.tags?.bright_outlook ? ' ★' : ''
        };
    }, (item, input) => {
        input.value = item.title;
        input.dataset.code = item.code;
        fetchJobDetails(item.code);
    });
    
    // Setup company autocomplete
    setupAutocomplete('company', 'company-suggestions', '/api/companies/search', (item) => {
        return {
            text: item,
            value: item,
            extra: ''
        };
    }, (item, input) => {
        input.value = item;
    });
}

// Generic autocomplete setup
function setupAutocomplete(inputId, suggestionsId, apiUrl, formatItem, onSelect) {
    const input = document.getElementById(inputId);
    const suggestions = document.getElementById(suggestionsId);
    let debounceTimer;
    
    if (!input || !suggestions) return;
    
    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const query = input.value.trim();
        
        if (query.length < 2) {
            suggestions.style.display = 'none';
            return;
        }
        
        debounceTimer = setTimeout(async () => {
            try {
                const response = await fetch(`${apiUrl}?query=${encodeURIComponent(query)}`);
                const data = await response.json();
                
                if (data.results && data.results.length > 0) {
                    suggestions.innerHTML = data.results.map(item => {
                        const formatted = formatItem(item);
                        return `
                            <div class="suggestion-item" data-value="${formatted.value}">
                                <strong>${formatted.text}</strong>
                                ${formatted.extra ? `<span style="color: green;">${formatted.extra}</span>` : ''}
                            </div>
                        `;
                    }).join('');
                    suggestions.style.display = 'block';
                    
                    suggestions.querySelectorAll('.suggestion-item').forEach(item => {
                        item.addEventListener('click', () => {
                            const selectedItem = data.results.find(r => {
                                const formatted = formatItem(r);
                                return formatted.value === item.dataset.value;
                            });
                            if (selectedItem) {
                                onSelect(selectedItem, input);
                            }
                            suggestions.style.display = 'none';
                        });
                    });
                } else {
                    suggestions.style.display = 'none';
                }
            } catch (error) {
                console.error('Error fetching suggestions:', error);
                suggestions.style.display = 'none';
            }
        }, 300);
    });
    
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !suggestions.contains(e.target)) {
            suggestions.style.display = 'none';
        }
    });
}

// Company autocomplete for dynamic experience fields
function setupCompanyAutocomplete(input, suggestions) {
    let debounceTimer;
    
    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const query = input.value.trim();
        
        if (query.length < 2) {
            suggestions.style.display = 'none';
            return;
        }
        
        debounceTimer = setTimeout(async () => {
            try {
                const response = await fetch(`/api/companies/search?query=${encodeURIComponent(query)}`);
                const data = await response.json();
                
                if (data.results && data.results.length > 0) {
                    suggestions.innerHTML = data.results.map(company => `
                        <div class="suggestion-item" data-value="${company}">
                            <strong>${company}</strong>
                        </div>
                    `).join('');
                    suggestions.style.display = 'block';
                    
                    suggestions.querySelectorAll('.suggestion-item').forEach(item => {
                        item.addEventListener('click', () => {
                            input.value = item.dataset.value;
                            suggestions.style.display = 'none';
                        });
                    });
                } else {
                    suggestions.style.display = 'none';
                }
            } catch (error) {
                console.error('Error fetching company suggestions:', error);
                suggestions.style.display = 'none';
            }
        }, 300);
    });
    
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !suggestions.contains(e.target)) {
            suggestions.style.display = 'none';
        }
    });
}


// State/City autocomplete for Experience entries
let allStates = null;

async function loadAllStates() {
    if (allStates) return allStates;
    try {
        const response = await fetch('/api/states');
        const data = await response.json();
        allStates = data.states || {};
        return allStates;
    } catch (error) {
        console.error('Error loading states:', error);
        return {};
    }
}

async function setupExperienceStateCity(stateSelect, cityInput, citySuggestions) {
    // Load states if not already loaded
    const states = await loadAllStates();
    
    // Populate state dropdown
    Object.entries(states).forEach(([code, name]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = name;
        stateSelect.appendChild(option);
    });
    
    let currentStateCities = [];
    
    // State change handler
    stateSelect.addEventListener('change', async () => {
        const stateCode = stateSelect.value;
        console.log('Experience state selected:', stateCode);
        
        if (!stateCode) {
            cityInput.disabled = true;
            cityInput.value = '';
            cityInput.placeholder = 'Select a state first';
            return;
        }
        
        // Load cities for selected state
        try {
            const response = await fetch(`/api/cities?state=${encodeURIComponent(stateCode)}`);
            const data = await response.json();
            currentStateCities = data.cities || [];
            cityInput.disabled = false;
            cityInput.placeholder = `Type to search ${currentStateCities.length} cities...`;
            console.log(`Loaded ${currentStateCities.length} cities for ${stateCode}`);
        } catch (error) {
            console.error('Error loading cities:', error);
            cityInput.placeholder = 'Error loading cities';
        }
    });
    
    // City autocomplete
    let debounceTimer;
    cityInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const query = cityInput.value.trim().toLowerCase();
        
        if (query.length < 2 || currentStateCities.length === 0) {
            citySuggestions.style.display = 'none';
            return;
        }
        
        debounceTimer = setTimeout(() => {
            const matches = currentStateCities.filter(city => 
                city.toLowerCase().includes(query)
            ).slice(0, 10);
            
            if (matches.length > 0) {
                citySuggestions.innerHTML = matches.map(city => `
                    <div class="suggestion-item" data-value="${city}">
                        <strong>${city}</strong>
                    </div>
                `).join('');
                citySuggestions.style.display = 'block';
                
                citySuggestions.querySelectorAll('.suggestion-item').forEach(item => {
                    item.addEventListener('click', () => {
                        cityInput.value = item.dataset.value;
                        citySuggestions.style.display = 'none';
                    });
                });
            } else {
                citySuggestions.style.display = 'none';
            }
        }, 150);
    });
    
    // Hide suggestions on click outside
    document.addEventListener('click', (e) => {
        if (!cityInput.contains(e.target) && !citySuggestions.contains(e.target)) {
            citySuggestions.style.display = 'none';
        }
    });
}


// Fetch job details and suggest skills
async function fetchJobDetails(jobCode) {
    try {
        const response = await fetch(`/api/jobs/${jobCode}/summary`);
        const data = await response.json();
        
        if (data.skills && data.skills.length > 0) {
            // Show suggested skills section
            showSuggestedSkills(data.skills);
        }
    } catch (error) {
        console.error('Error fetching job details:', error);
    }
}

// Show suggested skills that user can click to add
function showSuggestedSkills(suggestedSkills) {
    // Remove existing suggestions
    const existing = document.getElementById('suggested-skills');
    if (existing) existing.remove();
    
    const skillsSection = document.querySelector('.form-group:has(#skill-input)');
    if (!skillsSection) return;
    
    const suggestionDiv = document.createElement('div');
    suggestionDiv.id = 'suggested-skills';
    suggestionDiv.className = 'field-row';
    suggestionDiv.innerHTML = `
        <label>Suggested Skills (click to add)</label>
        <div class="tags-container" id="suggested-skills-tags">
            ${suggestedSkills.slice(0, 10).map(skill => `
                <span class="tag" style="background: #27ae60; cursor: pointer;" onclick="addSuggestedSkill('${skill.replace(/'/g, "\\'")}')">
                    + ${skill}
                </span>
            `).join('')}
        </div>
    `;
    
    skillsSection.appendChild(suggestionDiv);
}

// Add a suggested skill to the skills list
function addSuggestedSkill(skill) {
    if (!skills.includes(skill)) {
        skills.push(skill);
        renderSkills();
    }
}

// State & City Autocomplete
let currentStateCities = [];

async function setupStateCityAutocomplete() {
    const stateSelect = document.getElementById('state');
    const cityInput = document.getElementById('city');
    const citySuggestions = document.getElementById('city-suggestions');
    
    if (!stateSelect || !cityInput) return;
    
    // Load states
    try {
        const response = await fetch('/api/states');
        const data = await response.json();
        
        if (data.states) {
            Object.entries(data.states).forEach(([code, name]) => {
                const option = document.createElement('option');
                option.value = code;
                option.textContent = name;
                stateSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading states:', error);
    }
    
    // State change handler
    stateSelect.addEventListener('change', async () => {
        const stateCode = stateSelect.value;
        
        if (!stateCode) {
            cityInput.disabled = true;
            cityInput.value = '';
            return;
        }
        
        // Load cities for selected state
        try {
            const response = await fetch(`/api/cities?state=${encodeURIComponent(stateCode)}`);
            const data = await response.json();
            currentStateCities = data.cities || [];
            cityInput.disabled = false;
            cityInput.placeholder = `Type to search ${currentStateCities.length} cities...`;
        } catch (error) {
            console.error('Error loading cities:', error);
        }
    });
    
    // City autocomplete
    let debounceTimer;
    cityInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const query = cityInput.value.trim().toLowerCase();
        
        if (query.length < 2 || currentStateCities.length === 0) {
            citySuggestions.style.display = 'none';
            return;
        }
        
        debounceTimer = setTimeout(() => {
            const matches = currentStateCities.filter(city => 
                city.toLowerCase().includes(query)
            ).slice(0, 10);
            
            if (matches.length > 0) {
                citySuggestions.innerHTML = matches.map(city => `
                    <div class="suggestion-item" data-value="${city}">
                        <strong>${city}</strong>
                    </div>
                `).join('');
                citySuggestions.style.display = 'block';
                
                citySuggestions.querySelectorAll('.suggestion-item').forEach(item => {
                    item.addEventListener('click', () => {
                        cityInput.value = item.dataset.value;
                        citySuggestions.style.display = 'none';
                    });
                });
            } else {
                citySuggestions.style.display = 'none';
            }
        }, 150);
    });
    
    // Hide suggestions on click outside
    document.addEventListener('click', (e) => {
        if (!cityInput.contains(e.target) && !citySuggestions.contains(e.target)) {
            citySuggestions.style.display = 'none';
        }
    });
}


// Education Autocomplete
let allDegrees = [];
let allFields = [];

async function loadDegrees() {
    if (allDegrees.length > 0) return allDegrees;
    try {
        const response = await fetch('/api/degrees');
        const data = await response.json();
        allDegrees = data.degrees || [];
        return allDegrees;
    } catch (error) {
        console.error('Error loading degrees:', error);
        return [];
    }
}

async function populateDegreeDropdown(select, selectedValue = '') {
    const degrees = await loadDegrees();
    degrees.forEach(degree => {
        const option = document.createElement('option');
        option.value = degree;
        option.textContent = degree;
        if (degree === selectedValue) option.selected = true;
        select.appendChild(option);
    });
}

function setupUniversityAutocomplete(input, suggestions) {
    let debounceTimer;
    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const query = input.value.trim().toLowerCase();
        
        if (query.length < 2) {
            suggestions.style.display = 'none';
            return;
        }
        
        debounceTimer = setTimeout(async () => {
            try {
                const response = await fetch(`/api/universities?q=${encodeURIComponent(query)}`);
                const data = await response.json();
                const matches = data.results || [];
                
                if (matches.length > 0) {
                    suggestions.innerHTML = matches.map(uni => `
                        <div class="suggestion-item" data-value="${uni}">
                            <strong>${uni}</strong>
                        </div>
                    `).join('');
                    suggestions.style.display = 'block';
                    
                    suggestions.querySelectorAll('.suggestion-item').forEach(item => {
                        item.addEventListener('click', () => {
                            input.value = item.dataset.value;
                            suggestions.style.display = 'none';
                        });
                    });
                } else {
                    suggestions.style.display = 'none';
                }
            } catch (error) {
                console.error('Error searching universities:', error);
            }
        }, 150);
    });
    
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !suggestions.contains(e.target)) {
            suggestions.style.display = 'none';
        }
    });
}

function setupFieldAutocomplete(input, suggestions) {
    let debounceTimer;
    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const query = input.value.trim().toLowerCase();
        
        if (query.length < 2) {
            suggestions.style.display = 'none';
            return;
        }
        
        debounceTimer = setTimeout(async () => {
            try {
                const response = await fetch(`/api/fields?q=${encodeURIComponent(query)}`);
                const data = await response.json();
                const matches = data.results || [];
                
                if (matches.length > 0) {
                    suggestions.innerHTML = matches.map(field => `
                        <div class="suggestion-item" data-value="${field}">
                            <strong>${field}</strong>
                        </div>
                    `).join('');
                    suggestions.style.display = 'block';
                    
                    suggestions.querySelectorAll('.suggestion-item').forEach(item => {
                        item.addEventListener('click', () => {
                            input.value = item.dataset.value;
                            suggestions.style.display = 'none';
                        });
                    });
                } else {
                    suggestions.style.display = 'none';
                }
            } catch (error) {
                console.error('Error searching fields:', error);
            }
        }, 150);
    });
    
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !suggestions.contains(e.target)) {
            suggestions.style.display = 'none';
        }
    });
}
