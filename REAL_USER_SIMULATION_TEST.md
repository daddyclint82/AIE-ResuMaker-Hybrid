# Real User Simulation Test — AIe ResuMaker Voice Builder

## Purpose
This document defines how to perform end-to-end testing of the AIe ResuMaker voice-first resume builder using **browser automation** that simulates a real human user interacting with the actual UI.

**Why this matters:** Previous testing used raw HTTP requests (`requests.post()`) to the API endpoints, bypassing the UI entirely. This missed visual/layout bugs like missing bullets, "done"/"skip" text in sections, and empty competencies showing as `{}`. Real user simulation catches what API-only tests cannot.

---

## Test Overview

**Test Name:** `test_voice_browser.py`
**Technology:** Playwright (Python) — automates real Chrome/Firefox
**Target URL:** `http://localhost:8000/build?mode=voice`
**What it simulates:** A human clicking the mic button, typing answers, and viewing the preview

---

## What Gets Created

| File | Purpose | Affects App? |
|------|---------|------------|
| `tests/test_voice_browser.py` | Main test script — opens browser, runs questionnaire | ❌ No |
| `tests/screenshots/` | Visual evidence of each step (for debugging) | ❌ No |
| `.gitignore` | May add `__pycache__`, `screenshots/` | ❌ No |

## What Stays Untouched

| File | Why Untouched |
|------|---------------|
| `voice_api.py` | Backend logic — test uses it via HTTP, doesn't modify it |
| `static/voice_chat.js` | Frontend JS — test interacts with it, doesn't change it |
| `static/voice_chat.css` | Styles — test verifies them visually |
| `templates/voice_chat.html` | Template — test renders it in browser |
| `main.py` | Form builder — separate from voice test |
| `voice-questionnaire.json` | Rules — test follows them, doesn't modify them |

---

## How It Works (Step-by-Step)

### Phase 1: Browser Launch
```
1. Playwright launches headless Chromium (or headed for debugging)
2. Browser navigates to http://localhost:8000/build?mode=voice
3. Waits for page load — checks custom AEI icon is visible
```

### Phase 2: Questionnaire Walkthrough
```
For each question in voice-questionnaire.json:
  1. Wait for AI question to appear in chat
  2. Click mic button (AEI logo image in .mic-btn)
  3. Type answer in text input (#text-input)
  4. Click send button (.send-btn, green arrow)
  5. Wait for AI response (HTTP request + DOM update)
  6. Take screenshot of current state
  7. Verify expected text appears in chat bubble
```

### Phase 3: Decision Points
```
When "Add another bullet?" appears:
  1. Type "yes" or "done"
  2. Click send
  3. Verify next question appears (or section ends)

When "Add another job?" appears:
  1. Type "yes" or "done"
  2. Click send
  3. Verify next job starts (or transitions to summary)
```

### Phase 4: Summary (Rules-Based)
```
Q13 (summary_q1):
  Input: First 2 sentences from user's resume professional summary
  Verification: Check summary_q1 content in session data

Q14 (summary_q2):
  Input: 2+ problem-solving instances from resume
  Verification: Check for keywords like "reduced", "improved", "fixed"

Q15 (summary_q3):
  Input: 1 outcome-changing evidence with metrics
  Verification: Check for numbers, percentages, dollar amounts

Q16 (summary_q4):
  Input: AI Infrastructure Engineer keywords
  Verification: Check for Kubernetes, Docker, AWS, Terraform, LLM, etc.
```

### Phase 5: Skills
```
1. Wait for skills question
2. Type comma-separated skills
3. Click send
4. Wait for Groq categorization (may take 2-3 seconds)
5. Verify categorized skills panel appears with 7 tiers
```

### Phase 6: Optional Sections
```
For each optional section (Projects, Competencies, Education, Community, Certifications):
  1. Type "skip" to skip (or provide data to test)
  2. Click send
  3. Verify section header doesn't show command words ("done"/"skip")
```

### Phase 7: Preview Verification
```
1. Wait for preview to render (inline or modal)
2. Take screenshot of full preview
3. Verify sections:
   - Name, contact info at top
   - Professional Summary (2-3 sentences)
   - Technical Skills (categorized, not comma dump)
   - Professional Experience (job title, company, dates, 3 bullets each)
   - Optional sections (only if provided, no "done"/"skip" text)
4. Check no empty sections render as `{}` or blank
5. Verify download button appears and links work
```

### Phase 8: File Download Check
```
1. Click "Download DOCX" button
2. Verify file downloads (check Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document)
3. Click "Download PDF" button
4. Verify file downloads (check Content-Type: application/pdf)
5. Verify PDF is actual PDF (magic bytes %PDF-1.4)
```

---

## Key Selectors (for Playwright)

| Element | Selector |
|---------|----------|
| Mic button | `#mic-btn` or `.mic-btn img` (AEI logo) |
| Text input | `#text-input` |
| Send button | `.send-btn` |
| Chat messages | `.chat-message` or `.message` |
| AI question | `.ai-message` or `.message.ai` |
| User answer | `.user-message` or `.message.user` |
| Preview container | `.preview-container` or `#preview` |
| Download buttons | `.download-btn` or `button:has-text("Download")` |
| Skills panel | `.skills-panel` |
| Nav buttons (Back, Add, Done, Save) | `.nav-btn` |

---

## Expected Visual States

### Before Test
- Header shows AEI logo (not 🎓)
- Mic button shows custom icon (not 🎤)
- No "✏️ Type" button in top-right
- All nav buttons are blue `#2563eb`
- Font weight consistent (600)

### During Test
- Questions appear in AI chat bubbles
- User answers appear in user chat bubbles
- Context label shows phase ("Job 1", "Summary 2/4", etc.)
- Progress bar fills as steps complete
- Skills panel slides up when skills are entered

### After Test (Preview)
- Resume formatted with proper spacing
- Job bullets visible (not missing)
- Skills categorized by tier
- No "done" or "skip" text in any section
- No empty `{}` dicts visible
- Download buttons functional

---

## Debugging with Screenshots

If a test fails, screenshots are saved to `tests/screenshots/`:

```
tests/screenshots/
├── 01_start_page.png
├── 02_q1_full_name.png
├── 03_q2_email.png
├── ...
├── 45_preview_final.png
└── 46_download_modal.png
```

**Naming convention:** `{step_number}_{phase}_{question_or_action}.png`

---

## Side Effects (What Changes on Server)

| What | Effect |
|------|--------|
| Browser console logs | More activity (normal) |
| Server logs (`uvicorn`) | Normal HTTP requests (same as real user) |
| Session files | Created in `voice_sessions/` (same as before) |
| Temp resume files | Created in `/tmp/resumes/` (same as before) |
| App code | **No changes** |

---

## Running the Test

### Prerequisites
```bash
# Ensure server is running
cd /home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid
./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# In another terminal, run test
cd /home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid
python tests/test_voice_browser.py
```

### With Headed Browser (visible)
```python
# In test file, set:
browser = playwright.chromium.launch(headed=True, slow_mo=500)  # 500ms pause between actions
```

### Headless (CI/automation)
```python
# Default — runs in background
browser = playwright.chromium.launch(headless=True)
```

---

## Comparison: HTTP Test vs Browser Test

| Aspect | HTTP Test (`requests.post`) | Browser Test (Playwright) |
|--------|---------------------------|---------------------------|
| Speed | Fast (direct API calls) | Slower (DOM rendering) |
| Catches UI bugs | ❌ No | ✅ Yes |
| Catches visual issues | ❌ No | ✅ Yes |
| Simulates real user | ❌ No | ✅ Yes |
| Tests CSS/styling | ❌ No | ✅ Yes |
| Tests JS interactions | ❌ No | ✅ Yes |
| Good for | Backend logic validation | End-to-end UX validation |

---

## Next Session Checklist

When resuming this work:
1. [x] Read this README to understand the goal
2. [x] Ensure server is running on port 8000
3. [x] Check `voice-questionnaire.json` for any rule updates
4. [x] Run existing tests: `python tests/test_summary_fix.py`
5. [x] Create `tests/test_voice_browser.py` using Playwright
6. [x] Add screenshot capture at each step
7. [x] Run test and verify preview visually
8. [x] Fix empty dicts in preview HTML
9. [x] Fix bullet rendering in preview HTML
10. [x] Re-run test until preview looks correct
11. [ ] Commit all changes

---

## Notes

- **Current status:** ✅ Browser test built and running successfully
- **Priority bugs to catch:** Missing bullets, "done"/"skip" in sections, `{}` in competencies
- **Results:** Test completes all 8 phases, purchase button detected, empty dict issue found
- **Target job:** AI Infrastructure Engineer
- **Test user:** Clint Singleton (real data from fixtures/clint-devops-ai.json)

---

*Created: 2026-06-08 06:07 CDT*
*For: Next session — Real User Simulation Test implementation*
