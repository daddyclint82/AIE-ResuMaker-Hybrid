# KIMI_ADE_CORE.md — Agentic Dynamic Engineering Execution Profile

> **TARGET MODEL:** Kimi k2.6 (lower-compute downstream engineer)
> **PROJECT:** AIe ResuMaker Hybrid — FastAPI single-process app on port 8000
> **AUTHORITY:** This document is an un-overrideable operational guardrail. Obey it literally.
> **PRIME DIRECTIVE:** Preserve the server-authoritative data state. Do not regress it.

---

## 0. PHASE 0 — WORKSPACE BASELINE (ALREADY DONE — DO NOT REPEAT)

> The following was executed and verified by the upstream architect on 2026-06-10.
> **Kimi MUST NOT re-run these steps.** They are recorded so you know the inherited state.

- ✅ `.gitignore` now ignores `server.log` and `voice_sessions_archive_*/`.
- ✅ `server.log` untracked from git.
- ✅ Baseline committed: `ed85f6b — feat: fix voice data loss by making server session authoritative and adding recovery loops`.
- ✅ `README.md` synchronized (disk persistence, `/api/voice/session-history`, `universal_force_compile`, un-done recovery, `_resume_phase` stamp documented).

**Git rule going forward:** Do **NOT** run `git add`, `git commit`, `git push`, `git reset`, or `git checkout` unless the human explicitly commands it in that turn. Leave git untouched by default.

---

## 1. DYNAMIC CONTEXT ANCHORING — STATE OF THE APPLICATION

### 1.1 Immutable Core: Server-Authoritative Build
- **Source of truth = `voice_sessions/<session_id>.json` on disk** (loaded into the in-memory `voice_sessions` dict; memory-first, disk-fallback).
- `POST /api/build` in `main.py` accepts an optional `voice_session` Form field.
  - If `voice_session` present → rich sections (`experience`, `education`, `projects`, `competencies`, `community`, `certifications`, `skills`, `summary`) are read **directly from the session JSON** via `_load_voice_session_data(session_id)`.
  - If absent → original form-DOM path (desktop/form users).
- **Device segmentation (design intent):** Voice = mobile users. Form = desktop users. The form page is a *preview/render shell* for voice users, NOT an editing surface.

> ⛔ **FATAL STRUCTURAL VIOLATION:** Treating the frontend Form DOM as the source of truth for a voice build. This reintroduces the "partial/anemic resume" data-loss bug that took an entire session to eradicate. The Form DOM round-trip is lossy for repeating sections. **Never route voice-session builds back through DOM collection.**

### 1.2 Patched Baseline (operational features — do not break)
| Feature | Location | Behavior |
|---|---|---|
| Disk persistence | `voice_api.py` `_persist_session()` | Every turn written to `voice_sessions/*.json` |
| Transcript rehydration | `GET /api/voice/session-history` + `voice_chat.js checkForSavedSession()` | Repaints chat bubbles on reload via `localStorage['aie_voice_sid']` |
| `_resume_phase` bookmarking | `voice_api.py universal_force_compile` handler | Stamps `phase`/`step_index` before finalize so un-done recovery resumes deep flows precisely |
| Confirmation Guard | `voice_chat.js` compile button | `confirm()` before `universal_force_compile` fires |
| Un-done recovery | `voice_api.py _voice_turn_locked` | Real answer to a `done` session reopens flow; triggering control word ("skip"/"yes"/"done") is NOT stored as data |
| localStorage precedence | `static/app.js loadVoiceData()` | When `voice_session` in URL, server data wins over stale `aie_resume_progress` |
| Terms-gate preservation | `static/app.js checkTermsAcceptance()` + `templates/terms.html` | `/terms?return=...` round-trips the `voice_session` back to `/build` |
| Cache busting | `templates/index.html app.js?v=N`, `voice_chat.html voice_chat.js?v=N` | **Increment `?v=` on EVERY edit to that JS file** or the browser serves stale code |

---

## 2. BOUNDED EXECUTION PROTOCOL — "NO-FLY" ZONES

### 2.1 FREEZE-STATE DECLARATIONS (locked — do not modify)
```
FROZEN[questionnaire_structures]:
    SIMPLE_STEPS, SUMMARY_QUESTIONS, EXPERIENCE_FIELDS, SKILL_TIERS,
    optional-section field definitions in voice_api.py
    => DO NOT add/remove/reorder questions or fields.

FROZEN[conversation_loops]:
    process_answer(), _process_experience(), _process_summary(),
    _advance_optional_section(), go_back(), get_current_state()
    => DO NOT alter phase-transition logic or flag-check ordering.
    => CRITICAL INVARIANT: exp_done check MUST precede in_bullet_loop check.

FROZEN[core_css]:
    static/voice_chat.css, static/style.css
    => DO NOT edit. All voice-button style overrides stay inline in JS.

FROZEN[build_authority]:
    /api/build session-authoritative branch in main.py
    => DO NOT make the form DOM authoritative for voice sessions.
```

### 2.2 MODIFICATION SCHEMA (mandatory)
```
ALLOWED:
    - append-only additions (new function, new endpoint, new guarded branch)
    - clean line-by-replace diffs (exact oldText -> newText, minimal span)

FORBIDDEN:
    - full-file rewrites
    - sweeping refactors
    - reformatting unrelated lines
    - deleting existing comments or debug prints
    - editing > ~15 lines for a fix that a 5-line patch solves
```

---

## 3. STATIC COMPLIANCE DRILL — MANDATORY 3-STEP COGNITIVE LOOP

> Kimi MUST emit these three blocks, in order, BEFORE any code is written.

**STEP 1 — READ & ECHO**
- `grep`/read the live file. Echo the **exact line numbers** and **variable/function names** you will touch.
- Example: `voice_api.py:1683 — _voice_turn_locked, var: ctx, session["done"]`
- No echo = no edit. Never edit from memory or assumption.

**STEP 2 — IMPACT ANALYSIS**
- State every file touched and every state variable / session key affected.
- State which FROZEN zones are NOT touched (prove you stayed in bounds).
- Note if a `?v=` cache bump is required (any JS edit → YES).

**STEP 3 — THE COMPACT DIFF**
- Output only minimal, high-density, copy-pasteable diff blocks.
- ⛔ NO placeholders: no `// rest of code here`, no `...existing...`, no ellipses.
- Each diff must apply cleanly against the echoed lines from Step 1.

---

## 4. BUDGET DEFENSE INSTRUCTIONS

```
REMAINING_DEV_BUDGET = $4.75   # CRITICAL — treat as near-empty
```
- **Prioritize code safety over feature completeness.** A safe partial fix beats a risky full one.
- **NO trial-and-error loops.** Read first, reason once, patch once. Do not "try something and see."
- **Refuse to rewrite whole files** when a 5-line patch suffices. State the minimal patch and stop.
- **One verification per change**, not a battery of speculative tests. Use the existing server on :8000.
- If a request would require touching a FROZEN zone or exceed the budget safely, **STOP and ask the human** instead of guessing.
- Do not restart the server repeatedly; restart once after a verified batch of edits.

---

## QUICK REFERENCE — KEY PATHS

| Item | Path |
|---|---|
| FastAPI app + build + generators | `main.py` |
| Voice state machine + endpoints | `voice_api.py` |
| Form builder + prefill | `static/app.js` (bump `?v=` in `templates/index.html`) |
| Voice chat loop | `static/voice_chat.js` (bump `?v=` in `templates/voice_chat.html`) |
| Session store | `voice_sessions/<id>.json` |
| Start server | `./start.sh` → `uvicorn main:app --host 0.0.0.0 --port 8000` |

* **Anti-Duplicate Greeting Guard**: The frontend `addMessage()` function in `voice_chat.js` contains a strict text-deduplication guard, and the hardcoded HTML welcome div has been completely stripped. The greeting is generated dynamically by the server. You are strictly forbidden from modifying the deduplication logic in `addMessage()` or re-introducing hardcoded greeting blocks into the HTML templates, as this causes a severe double-rendering race condition on mobile layouts.

> **END OF MANUAL. Obey literally. When in doubt, READ the file and ASK the human.**
