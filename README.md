# AIE ResuMaker Hybrid — README

A conversational, voice-first resume builder that works on mobile and desktop. Users can speak their resume into existence through a chat interface, or fill out a traditional form on desktop.

## Status: In Development — Functional, Not Deployed

This is a **separate project** from the live [AIE ResuMaker](https://aie-resumaker.onrender.com). It lives in `aie-resumaker-hybrid/` and is **not yet pushed to GitHub or deployed.**

---

## What Works

### Voice Chat Mode (`/build?mode=voice`)
- **Conversational flow** — AI asks questions one at a time
- **Speech recognition** — Browser-native `SpeechRecognition` API, continuous listening
- **Pause-safe** — Pausing mid-sentence no longer overwrites text
- **Text fallback** — Type if you don't want to use mic
- **Clear button** — ✕ wipes text + accumulated transcript
- **"I had more to say"** — After sending, tap ↩️ to append more info
- **Progress bar** — Shows % complete at top
- **Mode toggle** — ✏️ Type button switches to form mode

### Form Builder Mode (`/build?mode=form`)
- **Full form** — All fields from original AIE ResuMaker
- **Auto-populate from voice** — Partially works (simple fields OK, arrays buggy)
- **Mode toggle** — 🎤 Voice button switches back to voice mode
- **localStorage persistence** — Saves progress every 10 seconds

### Landing Page (`/`)
- **Auto-detects device** — Mobile (`< 768px`) → voice mode, Desktop → form mode
- **User preference override** — Stores `aie_mode` in localStorage
- **Manual switch** — User can toggle between modes anytime

### Backend
- **Voice endpoints:**
  - `POST /api/voice/start` — Creates session, returns first question
  - `POST /api/voice/turn` — Accepts transcript, returns next question + extracted data
  - `POST /api/voice/save` / `POST /api/voice/load` — Persist / restore session state
  - `GET  /api/voice/session-history?sessionId=...` — Returns stored transcript turns (transcript rehydration)
- **Groq integration** — `llama-3.1-8b-instant` for extraction, `llama-3.3-70b` for summary
- **Fallback** — If no Groq key or API error, uses raw transcript
- **Disk-persisted sessions** — Each turn is written to `voice_sessions/<session_id>.json`
  (loaded from memory first, then disk). Sessions survive restarts; transcripts can be rehydrated.
- **`progress_pct`** — Server now returns `progress_pct` (0–100) instead of raw `step_index`.
  Frontend `updateProgress()` uses this directly, eliminating manual step counting.

### Server-Authoritative Build (CRITICAL ARCHITECTURE)
- `POST /api/build` accepts an optional `voice_session` field.
- **When `voice_session` is present (voice/mobile path):** the rich repeating sections
  (experience/education/projects/competencies/community/certifications) are pulled
  **directly from `voice_sessions/*.json`**, bypassing the lossy form-DOM round-trip.
  The stored session `data` is the source of truth.
- **When absent (desktop/form path):** the original form-DOM build runs unchanged.
- ⚠️ Treating the frontend form DOM as the source of truth for voice builds is a fatal
  structural violation — it reintroduces the "partial/anemic resume" data-loss bug.

### Resilience / Recovery Features (added 2026-06-10, hardened 2026-06-11)
- **Transcript rehydration** — `voice_chat.js` fetches `/api/voice/session-history` on load
  (keyed by `localStorage['aie_voice_sid']`) and repaints prior chat bubbles after reload/back-nav.
- **Anti-duplicate greeting guard** — `addMessage()` deduplication: if an AI message with
  identical text already exists in the DOM, the duplicate is silently skipped. Prevents
  double-rendering of the first question after race conditions between `/start` responses
  and `addMessage` calls.
- **`universal_force_compile`** — "⚙️ COMPILE RESUME NOW" action finalizes the session
  (`done=True`, `phase=done`) and redirects to the build page. Guarded by a `confirm()` dialog.
  Stamps `_resume_phase` before finalizing so un-done recovery resumes at the right phase.
- **Un-done recovery** — submitting a real answer to a `done` session auto-reopens the flow
  at the correct field; the triggering control word (e.g. "skip") is NOT stored as data.
- **`_resume_phase` bookmarking** — force-compile stamps the phase/step before finalizing so
  un-done recovery can resume deep flows (experience/optional) precisely.
- **`progress_pct`** — Server computes `progress_pct` (0–100) per turn instead of exposing raw
  `step_index`. Frontend uses `progress_pct` directly, eliminating step-count drift.
- **localStorage precedence** — when a `voice_session` is in the URL, fresh server data wins
  over stale `aie_resume_progress`; the form build POST forwards `voice_session` to the server.
- **Terms-gate session preservation** — `/terms` carries a `return` param so accepting terms
  routes back to `/build?...voice_session=X` without dropping the session.

---

## Known Issues

### Major: Form Builder Auto-Populate (Partially Broken)
**User reported:** "does not work that well"
**Suspected problems:**
- City/State split fails — "Austin, Texas" probably dumps into `city` field only
- Experience array — Logic tries to find `.experience-entry` class but dynamic fields may not exist yet
- Function name mismatch — `addExperienceEntry()` / `addEducationEntry()` may not exist in `app.js`
- **Needs:** Real browser test to see which fields fill correctly

### Major: Voice Question Flow (Needs Redesign for ADHD)
**Current:** Big chunky questions like "Tell me about your work history — company, title, dates, description"
**Problem:** Overwhelming for users with ADHD
**User requirement:** Break into micro-questions for incremental wins. This is core to product strategy.

### Minor
- SpeechRecognition only works in Chrome/Safari (not Firefox)
- Voice sessions stay in memory forever (no cleanup)
- Untested on actual mobile devices
- Not deployed or pushed to GitHub

---

## Project Structure

```
aie-resumaker-hybrid/
├── main.py                    # FastAPI app + voice router mount
├── voice_api.py               # Voice endpoints + Groq integration
├── .env                       # Groq API key (not committed)
├── templates/
│   ├── landing.html           # Auto-detect + mode redirect
│   ├── voice_chat.html       # Chat UI
│   └── index.html            # Form builder + voice_data embed
├── static/
│   ├── voice_chat.js         # SpeechRecognition + chat logic
│   ├── voice_chat.css        # Mobile-first chat styles
│   ├── app.js               # Form builder + loadVoiceData()
│   └── style.css            # Form styles (from original)
└── README.md                # This file
```

---

## Quick Start

```bash
cd /home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid

# Start server
nohup ./venv/bin/python main.py > /tmp/hybrid_server.log 2>&1 &
echo $! > /tmp/hybrid.pid

# Test
curl -s http://127.0.0.1:8000/healthz
curl -s -X POST http://127.0.0.1:8000/api/voice/start

# Stop
kill $(cat /tmp/hybrid.pid)
```

---

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `GROQ_API_KEY` | No (falls back to raw) | None |
| `GROQ_MODEL` | No | `llama-3.1-8b-instant` |

---

## Next Steps (Priority Order)

### 1. Redesign Voice Flow for ADHD Users (HIGHEST PRIORITY)
**User's explicit direction:** "Breaking down questions little by little so they get little wins is key to making this app addicting."

**New architecture:**
- Each work history entry = 4 separate micro-questions (company → title → dates → description)
- Each education entry = 4 separate micro-questions
- After each entry, ask "Add another? Say 'yes' or 'done'"
- Show context: "Job 1 — Company" so user knows where they are
- Celebrate each step: "Great! Now the title." → "Perfect! When were you there?"

**Backend changes:**
- `VOICE_QUESTIONS` becomes a state machine, not static array
- Track which field and which array index
- Handle "yes"/"done" for loop control
- Store partial experience/education objects

### 2. Fix Form Builder Auto-Populate
**Test first:** Complete voice session → click "View Resume" → inspect which fields filled
**Likely fixes:** City/state split, create dynamic entries before populating, add error handling

### 3. Continue Testing
- Real mobile browser test
- Verify all questions flow smoothly
- Check mode toggles work both ways
- Push to GitHub when stable

---

## Git History

| Commit | What |
|--------|------|
| `80877d4` | Initial: copy from aie-resumaker, strip broken voice code |
| `c886396` | Voice API backend |
| `9c3f5e4` | Voice chat frontend |
| `6a238aa` | Landing page mode detection |
| `972be36` | Wire voice data into form builder |
| `e83e4f1` | Mode toggle buttons |
| `0d77c9b` | Fix speech accumulation on pause |
| `832149d` | Clear input after each question |
| `099e876` | Fix accumulator scope bug |
| `a09d05d` | Add clear button |
| `8d836ee` | Add "I had more to say" button |
| `a8593be` | Add README and PROJECT_LOG |
| `3f9e50f` | feat: patch double-render race condition via addMessage text-dedup guard [2026.06.11 - Sequence v2] |
| `8dc5e57` | feat: clickable action buttons + sanitize_resume_data for clean resume output |
| `5f2ee99` | chore: add Render deploy artifacts, session-authoritative build polish, and engineering docs |
| `e25138f` | feat: fix voice data loss by making server session authoritative and adding recovery loops |
| `6d9369b` | feat: complete universal override compiler, save button layout handoff.md |
| `TBD` | **Fix 4 critical voice state machine bugs** (see below) |

---

## Critical Fixes Applied (2026-06-08)

All four fixes targeted the voice state machine in `voice_api.py`. These were found via systematic debug logging + automated test script.

### Fix 1: Skills "yes" Bug
- **File:** `voice_api.py` (skills phase handler)
- **Problem:** Skills field contained "yes" from bullet-loop decision prompts
- **Solution:** Filter control words in skills phase: reject "yes"/"done"/"next"

### Fix 2: Summary Data Pollution
- **File:** `voice_api.py` (summary phase handler)
- **Problem:** Summary answers stored in `session["data"]` alongside job data
- **Solution:** Isolate summary answers in `ctx["summary_answers"]` sub-dict

### Fix 3: Optional Sections State Bleed
- **File:** `voice_api.py` (`_advance_optional_section`)
- **Problem:** Flags (`awaiting_more_bullets`, `exp_done`) leaked between sections
- **Solution:** Explicitly pop flags on section transition

### Fix 4: Phase Transition experience→summary (CRITICAL)
- **File:** `voice_api.py` (`_process_experience`)
- **Problem:** After "done" at "Add another job?", flow stayed in experience forever
- **Root cause:** `in_bullet_loop` check preceded `exp_done` check
- **Solution:** Changed guard from `if not in_bullet_loop` to `if not in_bullet_loop and not exp_done`
- **Impact:** This single-line fix unblocked the entire voice flow

### Fix 5: Summary Generation Skipped (CRITICAL - 2026-06-08)
- **File:** `voice_api.py` (`get_current_state` + `_process_summary`)
- **Problem:** After answering all 4 summary questions, `get_current_state` checked if summary_answers existed (they did) and immediately transitioned to skills phase WITHOUT generating summary
- **Root cause:** `get_current_state` had a check `if not summary_answers.get("summary_q1") and not summary_answers.get("summary_q2")` that only showed the "auto/type your own" prompt when BOTH were empty. Since they were filled, it skipped to skills.
- **Solution:** 
  1. Modified `_process_summary` to detect when the LAST question is answered (q_idx + 1 >= len(SUMMARY_QUESTIONS))
  2. Generate summary via Groq BEFORE returning `get_current_state`
  3. Store summary in `data["summary"]` and transition to skills phase
  4. Removed the broken "auto or type your own" decision prompt entirely — summary is always auto-generated
- **Impact:** Professional summary now generates correctly from user answers via Groq LLM

**Testing method:** Automated Python script (`test_summary_fix.py`) simulates full voice session + verifies summary generation.

**Verification criteria:**
- `experience[].description` has 3 bullets, no "yes"/"done" strings
- `summary` contains actual sentences, not job titles
- `skills` is comma-separated actual skills, not "yes"
- Optional sections start empty (no job bullet leakage)

---

## Development Notes

### Pitfalls We Hit
1. **Context loss** — Use `update_plan`, restart if garbled
2. **Subagent fork** — Always `context="isolated"`
3. **Forward reference crash** — Use plain `dict = {}`
4. **Overengineering** — Dicts first, classes later
5. **JS scope** — Module-level vs function-level variables
6. **Git repo confusion** — `cd` into project first
7. **Server crashes** — Use `nohup`, write PID file
8. **State machine flag ordering** — CRITICAL: `exp_done` check must come before `in_bullet_loop` check (see Architecture Notes below)
9. **Control word leakage** — "yes"/"done"/"next" from bullet loops leak into skills — must filter in skills phase
10. **Summary data pollution** — Job data overwrites summary answers if stored in same `session["data"]` dict
11. **Summary generation skipped** — `get_current_state` transitioned to skills before `_process_summary` could generate (see Summary Generation Bug below)
12. **Async context** — Always `await` async functions; don't call `asyncio.run()` inside FastAPI handlers

### Critical Architecture Notes (Read Before Modifying)

#### State Machine Flags & Their Meanings
The voice backend uses a flat state machine with context flags. **Order of checks matters.**

| Flag | Set When | Cleared When | Danger |
|------|----------|--------------|--------|
| `phase` | Always | Phase transitions | Determines which handler runs |
| `in_bullet_loop` | First bullet entered | Job done + "done" said | If checked before `exp_done`, second "done" treated as first bullet |
| `exp_done` | User says "done" after bullets | New job started | If NOT checked before `in_bullet_loop`, phase never transitions to summary |
| `awaiting_more_bullets` | After "yes" to "more bullets?" | After collecting bullet | Can leak into next optional section if not cleared |
| `summary_idx` | Summary phase starts | After q3 answered | If `None`, summary questions not yet asked |
| `summary_answers` | Dict in ctx | Never (populated progressively) | Prevents job data from overwriting summary answers |

#### The Summary Generation Bug (Fixed 2026-06-08)
**Symptom:** After answering all 4 summary questions, flow transitioned to skills phase but `data["summary"]` was empty.

**Root cause:** Two problems:
1. `get_current_state` checked `if not summary_answers.get("summary_q1") and not summary_answers.get("summary_q2")` — since answers existed, it skipped the "auto/type your own" prompt and went straight to skills
2. Even if the prompt had shown, `_process_summary` only generated after q_idx >= len(QUESTIONS), but by then `get_current_state` had already transitioned to skills

**Fix:** Modified `_process_summary` to detect the last question and generate BEFORE returning:
```python
# In _process_summary, after storing answer:
if q_idx + 1 >= len(SUMMARY_QUESTIONS):
    # This was the LAST question — generate now!
    summary = await generate_summary_with_groq(session)
    data["summary"] = summary
    ctx["phase"] = "skills"  # Transition AFTER generation
```

**Lesson:** State transitions in `get_current_state` must not skip generation steps. Generate data BEFORE changing phase, or the generation code becomes unreachable.

#### The Phase Transition Bug (Fixed 2026-06-08)
**Symptom:** After completing bullets and saying "done" at "Add another job?", flow stayed in experience phase showing `_add_job` forever.

**Root cause:** In `_process_experience`, the `in_bullet_loop` check came BEFORE the `exp_done` check:
```python
# BROKEN:
if not ctx.get("in_bullet_loop", False):  # TRUE because previous "done" set it False
    # Treats "done" as FIRST BULLET — adds it to job description!
```

**Fix:** Added `and not ctx.get("exp_done", False)` to the guard:
```python
# FIXED:
if not ctx.get("in_bullet_loop", False) and not ctx.get("exp_done", False):
    # Only enters here when genuinely starting first bullet
```

**Lesson:** When a flag's negation (`not in_bullet_loop`) has two meanings ("never started" vs "just finished"), you need a second flag (`exp_done`) to disambiguate.

#### Skills "yes" Bug (Fixed 2026-06-08)
**Symptom:** Skills field contained "yes" instead of actual skills.
**Root cause:** "yes" from bullet-loop "Add another?" leaked into skills phase.
**Fix:** Filter control words in skills phase:
```python
if lower in ["skip", "none", "n/a", "yes", "done", "next"]:
    data["skills"] = ""
```

#### Summary Data Pollution (Fixed 2026-06-08)
**Symptom:** Summary contained job titles/dates instead of professional summary text.
**Root cause:** Summary answers stored in `session["data"]` which was also used for job data.
**Fix:** Store summary answers in isolated `ctx["summary_answers"]` dict:
```python
ctx["summary_answers"] = ctx.get("summary_answers", {})
ctx["summary_answers"]["summary_q1"] = extracted
```

#### Optional Sections State Bleed (Fixed 2026-06-08)
**Symptom:** Optional sections showed job bullets or previous section data.
**Root cause:** Flags like `awaiting_more_bullets` and `exp_done` not cleared on section transition.
**Fix:** `_advance_optional_section` explicitly pops these flags:
```python
for flag in ["awaiting_more_bullets", "exp_done", "in_bullet_loop"]:
    ctx.pop(flag, None)
```

### User Requirements (Locked In)
- Mobile users: voice chat only (no form fields)
- Desktop users: form default, can switch to voice
- ADHD-friendly: incremental micro-questions, little wins
- Separate from live app until merge-ready

---

## Architecture Deep Dive

### Voice State Machine Overview

The voice backend uses a **flat state machine** with a single `phase` field plus context flags. No classes, no objects — just plain dicts.

```
User Answer → process_answer() → get_current_state() → Next Question
                    ↓
            Phase Router (simple/experience/summary/skills/optional)
```

### Phase Flow

```
simple → experience → summary → skills → optional → done
  │         │           │         │        │
  9 fields  jobs loop   4 Qs     list    projects→competencies→community→certifications→links
  (name,   (company,   (edge,    (comma   (name,        (name,       (org,        (name,     (website,
   email,   title,      impact,   sep)    desc)         desc)        )            )          linkedin)
   etc.)    dates,
            bullets,
            add_more?)
```

### Key Data Structures

**Session Object:**
```python
{
    "session_id": "abc123",
    "step_index": 0,           # For simple phase only
    "data": {                    # Final resume data
        "full_name": "Clint Singleton",
        "email": "clint@example.com",
        "experience": [...],     # Flattened on finish
        "summary": "...",         # Generated by Groq
        "skills": "Python, AI...",
        "skills_categorized": {...},
        "projects": [...],
        # ... etc
    },
    "context": {                 # State machine context
        "phase": "experience",   # Current phase
        "exp_idx": 0,            # Current job index
        "exp_field_idx": 0,      # Current field within job
        "experience": [...],       # In-progress job data
        "in_bullet_loop": False,
        "exp_done": False,
        "summary_idx": 0,        # Current summary question
        "summary_answers": {},   # Isolated from data dict
        "opt_section": "projects", # Current optional section
        "opt_idx": 0,
        "opt_field_idx": 0,
    },
    "history": [],
    "done": False
}
```

### Question Types

| Type | Purpose | Example |
|------|---------|---------|
| `question` | Collect data | "What company did you work at?" |
| `decision` | Branching | "Add another job? Say 'yes' or 'done'" |
| `done` | Flow complete | "Your resume is ready!" |

### The Experience Loop (Most Complex)

```
Collect Fields: company → title → dates
       ↓
First Bullet: "What did you do? Say bullet 1."
       ↓
Decision: "Add another bullet? Say 'yes', 'next', or 'done'."
       ↓
  ┌─ "yes" → Next Bullet
  │     ↓
  │   Decision (loop)
  │
  └─ "done" → Decision: "Add another job?"
          ↓
    ┌─ "yes" → New Job (reset flags)
    │
    └─ "done" → Phase = summary
```

**Critical Flags:**
- `in_bullet_loop`: True when collecting bullets (not standard fields)
- `exp_done`: True when user says "done" at "Add another job?" prompt
- `awaiting_more_bullets`: True when user said "yes" to more bullets, next input is the bullet text

**Why `exp_done` is necessary:**
When `in_bullet_loop` becomes `False` (after "done"), it has TWO meanings:
1. "Never started bullets" (first time)
2. "Just finished bullets" (after "done")

Without `exp_done`, the second "done" at "Add another job?" gets treated as a first bullet.

### Summary Generation Flow

```
Q1: "What's your core edge? Why hire YOU?"
Q2: "What business problems do you solve?"
Q3: "Any hard numbers? Headcount, revenue, uptime?"
Q4: "Keywords from the job posting? Say 'none' if you don't have any."
       ↓
_process_summary detects q_idx + 1 >= len(SUMMARY_QUESTIONS)
       ↓
generate_summary_with_groq(session)
  → Builds prompt from summary_answers + job_title
  → Calls Groq API (llama-3.3-70b-versatile)
  → Returns 2-3 sentence professional summary
       ↓
Store in data["summary"]
       ↓
Transition to skills phase
```

### Skills Categorization

**Two-step process:**
1. **Prioritized category list** based on industry + job keywords
   - Maps "technology", "oil & gas", "healthcare", etc. to tiered categories
   - Blends primary + secondary tiers
2. **Groq categorization** with weights (1-100)
   - Sends top 15 most relevant categories to reduce noise
   - Returns JSON: `{"Programming & Development": [{"name": "Python", "weight": 95}]}`

### Optional Sections Pattern

All optional sections use the same repeatable pattern:

```
Collect Fields → "Add another? Say 'yes', 'next', or 'skip'."
       ↓
  ┌─ "yes" → New item (increment opt_idx, reset opt_field_idx)
  │
  └─ "skip"/"next"/"done" → Save & advance to next section
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/voice/start` | POST | Creates session, returns first question |
| `/api/voice/turn` | POST | Accepts transcript, returns next step |
| `/api/voice/save` | POST | Returns full session state for persistence |
| `/api/voice/load` | POST | Restores session from saved state |

### Groq Integration Points

1. **Summary Generation** — After 4 interview questions
2. **Skills Categorization** — After skills list collected
3. **Fallback** — If no API key or error, uses template concatenation

---

*Project started: 2026-06-04*
*Last updated: 2026-06-11 02:56 CDT*
*Next focus: Terms-gate UX (accept up front), form-edit write-back to session, README/test sync*
