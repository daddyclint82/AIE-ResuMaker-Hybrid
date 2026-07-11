# AIE ResuMaker — Architecture Decisions & Key Fixes

## What It Is

Conversational resume builder with ADHD-friendly micro-question design. Users answer one question at a time through a mobile-optimized chat interface. Voice input comes from native iOS/Android keyboard dictation — the app does not provide a custom microphone button.

## Core Flow (6 Phases)

```
┌─────────┐    ┌──────────┐    ┌─────────┐    ┌────────┐    ┌──────────┐    ┌──────┐
│  Simple │───▶│ Experience│───▶│ Summary │───▶│ Skills │───▶│ Optional │───▶│ Done │
│ 9 fields│    │ Jobs loop │    │  4 Qs   │    │ Categorize│   │ Sections │    │      │
└─────────┘    └──────────┘    └─────────┘    └────────┘    └──────────┘    └──────┘
```

**Simple:** full_name, email, phone, address, city, state, industry, job_title, experience_level, education_level

**Experience:** For each job: company → title → dates → location → bullets (loop: "Add another bullet?") → "Add another job?"

**Summary:** 4 interview questions → Groq auto-generates professional summary

**Skills:** Comma-separated list → Groq categorizes into weighted categories

**Optional:** projects → competencies → community → certifications → links (each: collect fields → "Add another?")

## Key Technical Decisions

### Flat Dict State Machine

- No classes, no ORM — plain dicts for sessions.
- Context flags track progress within phases.
- Phase transitions happen in `_process_*` functions, NOT in `get_current_state`.

### Critical Flag: `exp_done`

When `in_bullet_loop` becomes `False`, it has two meanings:

1. "Never started bullets" (first bullet entry)
2. "Just finished bullets" (user said "done")

`exp_done` disambiguates — without it, "done" at "Add another job?" gets treated as a first bullet.

### Summary Generation Timing

**Before fix:** `get_current_state` transitioned to skills before `_process_summary` could generate.

**After fix:** `_process_summary` detects the last question (`q_idx + 1 >= len(QUESTIONS)`) and generates the summary BEFORE returning state.

### Skills Categorization Pipeline

1. Determine priority tier from industry + job keywords (7 tiers: technology, oil_gas, healthcare, finance, creative, trades, general).
2. Build top-15 category list to reduce Groq noise.
3. Groq returns JSON: `{"Category": [{"name": "Python", "weight": 95}]}`.

### Server-Authoritative Build

`POST /api/build` accepts an optional `voice_session` field.

- **When present (voice/mobile path):** rich repeating sections are pulled directly from `voice_sessions/*.json`, bypassing the lossy form-DOM round-trip.
- **When absent (desktop/form path):** the original form-DOM build runs unchanged.

Treating the frontend form DOM as the source of truth for voice builds is a fatal structural violation that reintroduces the partial/anemic resume bug.

### Voice Input Strategy

- No custom microphone button or in-browser `SpeechRecognition` integration.
- Users dictate via native iOS/Android keyboard voice input.
- The UI is the **Resume Chat Assistant** (`index.html` has the mode-switch button; `voice_chat.html` is the mobile chat route).

### Terms Gate

Legal acceptance is enforced before the chat flow begins. `/terms` carries a `return` param so accepting terms routes back to `/build?...voice_session=X` without dropping the session.

### Pricing & Referrals

- Pricing tiers: $9.99 regular, $4.99 referral/student.
- Referral system: real backend tracking for $4.99 discount with "Give $5, Get $5" messaging.

### Resume Themes

- Professional, Modern, Minimal with distinct CSS.

## Data Flow

```
User Input (text, usually via native mobile dictation)
    ↓
POST /api/voice/turn {session_id, transcript}
    ↓
process_answer(session, transcript)
    ↓
Phase Router:
  simple → store field, increment step_index
  experience → _process_experience (complex bullet/job loop)
  summary → _process_summary (store answers, generate on last)
  skills → store + categorize with Groq
  optional → _process_optional (repeatable sections)
    ↓
get_current_state(session) → next question/decision/done
    ↓
JSON response {question, field, context_label, done}
```

## Session Structure

```python
session = {
    "session_id": "abc123",
    "step_index": 0,              # Simple phase progress
    "data": {                       # Final resume data
        "full_name": "...",
        "experience": [...],        # Jobs with descriptions
        "summary": "...",           # Groq-generated
        "skills_categorized": {...}, # Weighted categories
        "projects": [...],
        # ... etc
    },
    "context": {                    # State machine flags
        "phase": "experience",
        "exp_idx": 0,               # Current job index
        "exp_field_idx": 0,         # Current field index
        "in_bullet_loop": False,
        "exp_done": False,
        "summary_idx": 0,
        "summary_answers": {},
        "opt_section": "projects",
        # ... etc
    }
}
```

## Groq Integration (3 Points)

1. **Summary Generation** — `llama-3.3-70b-versatile`, 2-3 sentences from 4 interview answers.
2. **Skills Categorization** — Same model, returns weighted JSON with 15 prioritized categories.
3. **Fallback** — If no API key, uses template concatenation for summary, flat list for skills.

## Critical Fixes Applied

### 2026-06-08 — Core Voice State Machine Stabilization

Fixed 6 deadlocks: Groq summary auto-gen, experience loop flags, 42-category taxonomy, empty dict leaks, multi-format bullet rendering.

### Fix 1: Skills "yes" Bug

- **File:** `voice_api.py`
- **Problem:** Skills field contained "yes" from bullet-loop decision prompts.
- **Solution:** Filter control words in skills phase: reject "yes", "done", "next", etc.

### Fix 2: Summary Data Pollution

- **File:** `voice_api.py`
- **Problem:** Summary answers stored in `session["data"]` alongside job data.
- **Solution:** Isolate summary answers in `ctx["summary_answers"]` sub-dict.

### Fix 3: Optional Sections State Bleed

- **File:** `voice_api.py` (`_advance_optional_section`)
- **Problem:** Flags (`awaiting_more_bullets`, `exp_done`) leaked between sections.
- **Solution:** Explicitly pop flags on section transition.

### Fix 4: Phase Transition experience → summary (CRITICAL)

- **File:** `voice_api.py` (`_process_experience`)
- **Problem:** After "done" at "Add another job?", flow stayed in experience forever.
- **Root cause:** `in_bullet_loop` check preceded `exp_done` check.
- **Solution:** Changed guard from `if not in_bullet_loop` to `if not in_bullet_loop and not exp_done`.
- **Impact:** This single-line fix unblocked the entire voice flow.

### Fix 5: Summary Generation Skipped (CRITICAL)

- **File:** `voice_api.py` (`get_current_state` + `_process_summary`)
- **Problem:** After answering all 4 summary questions, flow transitioned to skills phase without generating the summary.
- **Solution:** `_process_summary` detects the last question and generates the summary before returning state; `data["summary"]` is populated and phase transitions to skills AFTER generation.

### 2026-06-11 — Skills Sanitization

- Filters project names, control words, and long phrases from all skill categories.

### 2026-06-23 — Skip Button + Conditional Tech Stack

- Optional sections show a skip button on first field.
- Tech stack question appears only if skills/job/industry contain programming/technology/computer keywords (`TECH_KEYWORDS` / `TECH_CATEGORIES` in `voice_api.py`).

## Resilience / Recovery Features

- **Transcript rehydration** — `voice_chat.js` fetches `/api/voice/session-history` on load and repaints prior chat bubbles after reload/back-nav.
- **Anti-duplicate greeting guard** — `addMessage()` deduplication skips duplicate AI messages.
- **`universal_force_compile`** — "⚙️ COMPILE RESUME NOW" action finalizes the session and redirects to build.
- **Un-done recovery** — submitting a real answer to a `done` session re-opens the flow at the correct field.
- **`_resume_phase` bookmarking** — force-compile stamps phase/step before finalizing so recovery can resume deep flows precisely.
- **`progress_pct`** — Server computes 0–100 progress per turn instead of exposing raw `step_index`.
- **localStorage precedence** — when a `voice_session` is in the URL, fresh server data wins over stale `aie_resume_progress`.

## Architecture Principles

1. **Dicts first, classes later** — Avoid overengineering until necessary.
2. **Phase transition AFTER generation** — Never transition before data is ready.
3. **Flag ordering matters** — Check terminal flags before loop flags.
4. **Isolate data domains** — `summary_answers` separate from `session["data"]`.
5. **Filter control words** — "yes"/"done"/"next" from previous phases must be rejected.
6. **Always await async** — No `asyncio.run()` inside FastAPI handlers.

## Performance Notes

- Groq calls dominate latency; summary and skills categorization are the expensive points.
- PDF/DOCX export uses reportlab and python-docx locally; on Render, Playwright/Chromium is disabled — CSS watermark fallback keeps previews lightweight.
- Disk session writes happen per turn; growth is unbounded — see [`docs/known-blockers.md`](../known-blockers.md).
