# DOCS_POST_MORTEM.md — Marathon Session Engineering Summary

**Date:** 2026-06-10
**Project:** AIe ResuMaker Hybrid (FastAPI single-process, port 8000)
**Baseline commit:** `feat: fix voice data loss by making server session authoritative and adding recovery loops`
**Scope:** Cure the "partial/anemic resume" data-loss bug + harden the voice flow + prep for Render deploy.

---

## 1. Root Cause Analysis — The "Partial Resume Saga"

### Symptom
A completed voice session would render a resume containing only **Summary + Technical Skills**. Experience, Education, Projects, Competencies, Community, and Certifications were **silently dropped**, despite all that data being present and correct in the stored session JSON.

### The architectural flaw: the voice → form → DOM → build round-trip
The build path was structured as:

```
voice session JSON  →  /build?mode=form embeds it as #voice-data
                    →  app.js loadVoiceData() prefills the form DOM
                    →  user clicks Build
                    →  app.js collects values FROM THE FORM DOM
                    →  POST /api/build  (form fields)
                    →  generate_pdf / generate_preview_html
```

The fatal property: **`/api/build` rebuilt the resume from whatever was physically present in the form DOM at submit time** — `form.querySelectorAll('input[name="exp_title[]"]')` etc. The repeating sections (experience/education/...) only made it into the payload if the DOM was correctly populated *and* re-serialized.

Three independent failure modes fed this single flaw:
1. **localStorage shadowing** — `loadVoiceData()` bailed out (`return`) when stale `aie_resume_progress` had a `full_name`, so the fresh session never prefilled the DOM; the build then serialized empty arrays.
2. **Prefill/collection fragility** — array sections depended on dynamic DOM nodes existing with exact `name="exp_*[]"` attributes; any timing or mapping mismatch produced empty `[]`.
3. **Terms-gate session loss** — the `/terms` redirect returned to a bare `/build` (no `voice_session`), so the subsequent build had no session reference and fell through to the empty-form path.

### The cure: server-side authoritative compilation
`/api/build` now accepts an optional `voice_session`. When present, the rich sections are read **directly from `voice_sessions/<id>.json`** (memory-first, disk-fallback) via `_load_voice_session_data()`, **completely bypassing the DOM round-trip**. Proven: a build POST with empty form arrays + a valid `voice_session` rendered the full resume (3 experience, 2 education, all sections). Desktop/form users (no `voice_session`) keep the original DOM path unchanged — matching the device-segmented design (voice = mobile, form = desktop).

---

## 2. Completed Fix Diffs — Files Touched

| File | Logic injected |
|------|----------------|
| **`main.py`** | Added `_load_voice_session_data(session_id)` (memory→disk session reader). Added `voice_session` Form param + a **session-authoritative branch** in `/api/build` that pulls experience/education/projects/competencies/community/certifications/skills/summary straight from session JSON. Added `address` passthrough. Made the **Playwright import lazy** (inside `render_preview_to_image`) so the app boots without Chromium. Made `uvicorn.run` honor `$PORT` and disable `--reload` in production. Added `import re`. |
| **`voice_api.py`** | Added per-turn **transcript recording** into `session["history"]` (incl. opening question) and back-button alignment (pops the AI+user pair). Added **`GET /api/voice/session-history`** endpoint. Added **`_resume_phase`/`_resume_step_index` bookmarking** stamped at `universal_force_compile`. Added **un-done recovery**: a real answer to a `done` session reopens the flow at the correct field and **does not store the triggering control word** ("skip"/"yes"/"done") as data. |
| **`static/voice_chat.js`** | Persist `sessionId` to `localStorage['aie_voice_sid']`. **Transcript rehydration** on init (fetch `/api/voice/session-history`, repaint bubbles, scroll). **Confirmation guard** (`confirm()`) on the "⚙️ COMPILE RESUME NOW" button before `universal_force_compile`. Defined the missing **`isDecisionPoint`** variable in `updateNavButtons()` (was a `ReferenceError` crashing nav rendering). |
| **`static/app.js`** | **localStorage precedence fix** — when a `voice_session` is in the URL, server data wins; stale `aie_resume_progress` is cleared instead of shadowing. **Forward `voice_session`** in both `/api/build` POST paths. **Terms-gate preservation** — carry `?return=/build?...voice_session=X` into the `/terms` redirect. |
| **`templates/index.html`** | Cache-bust bumps `app.js?v=4 → 5 → 6 → 7` across the session. |
| **`templates/voice_chat.html`** | Cache-bust bump `voice_chat.js?v=24 → 25`. |
| **`templates/terms.html`** | On accept, read `return` param and redirect back to it (preserves `voice_session`) instead of bare `/build`. |
| **`README.md`** | De-staled: documented disk persistence, `/api/voice/session-history`, `universal_force_compile`, un-done recovery, `_resume_phase`, server-authoritative build, terms-gate preservation. |
| **`MIGRATION_NOTES.md`** | Secrets scrubbed to placeholders; SMTP marked deprecated. |
| **`requirements.txt`** (new) | Clean, pinned app deps (no OS-package pollution). |
| **`render.yaml`** (new) | Render blueprint: build `pip install + playwright install --with-deps chromium`, start `uvicorn ... --port $PORT`, `/healthz`, secrets `sync:false`. |
| **`runtime.txt`** (new) | Pins Python 3.12.3. |
| **`KIMI_ADE_CORE.md`** (new) | Operational guardrail manual for downstream model. |

---

## 3. State Machine Blueprint — Updated Voice Session Lifecycle

```
START  POST /api/voice/start
  → session = { step_index:0, data:{}, context:{phase:"simple"}, history:[], done:false }
  → opening AI question recorded into history; persisted to disk

SIMPLE PHASE   phase="simple"
  → each answer stored in data[field]; step_index advances; turn recorded to history
  → fields: full_name, email, phone, address, city, state, industry,
            job_title, experience_level, education_level

EXPERIENCE PHASE   phase="experience"
  → loop per job: company → title → dates → location → bullets
  → flags: in_bullet_loop, exp_done, awaiting_more_bullets, exp_idx, exp_field_idx
  → INVARIANT: exp_done is checked BEFORE in_bullet_loop (disambiguates
    "never started bullets" vs "just finished bullets")

SUMMARY PHASE   phase="summary"
  → 4 Q&A stored in context.summary_answers (ISOLATED from data)
  → on last answer: Groq generates data["summary"]; transition to skills

SKILLS PHASE   phase="skills"
  → control words ("yes"/"done"/"next") filtered out; skills_categorized built

OPTIONAL PHASE   phase="optional"
  → sections: projects→competencies→education→community→certifications→links→done
  → "skip"/"next"/"done" advance; flags popped on section transition

COMPILATION
  (a) Natural completion → step.done=True → data flattened (experience/sections copied up) → done=True
  (b) universal_force_compile → stamps _resume_phase/_resume_step_index →
      phase="done", current_field="complete", done=True → persist → redirect /build

DONE   phase="done", done=true
  → /build?mode=form&voice_session=X
  → /api/build with voice_session → SESSION DATA IS AUTHORITATIVE

UN-DONE RECOVERY  (safety net)
  → real answer arrives while done=true →
    done=false; if simple fields incomplete → phase="simple", step_index=#answered;
    else → phase=_resume_phase (precise resume via stamp);
    triggering control word NOT stored; current question re-asked
```

**Authoritative-data rule:** Once a session is built via `/api/build` **with** `voice_session`, the `session["data"]` dict on disk is the single source of truth. The form DOM is a render/preview shell only.

---

## 4. Architectural Warnings for Future Models

> **READ BEFORE TOUCHING THIS CODEBASE.**

1. ⛔ **NEVER make the form DOM authoritative for a voice build.** `/api/build` must read repeating sections from the session JSON when `voice_session` is present. Re-routing voice builds through DOM collection reintroduces the partial-resume data-loss bug that took an entire session to kill.
2. 🧊 **FROZEN — questionnaire structures:** `SIMPLE_STEPS`, `SUMMARY_QUESTIONS`, `EXPERIENCE_FIELDS`, `SKILL_TIERS`, optional-section field defs. Do not add/remove/reorder.
3. 🧊 **FROZEN — conversation loops:** `process_answer`, `_process_experience`, `_process_summary`, `_advance_optional_section`, `go_back`, `get_current_state`. Do not alter phase-transition logic.
4. ⚠️ **INVARIANT:** In `_process_experience`, the `exp_done` check **must precede** the `in_bullet_loop` check. Reversing it makes the flow never transition out of experience.
5. ⚠️ **Control-word leakage:** "yes"/"done"/"skip"/"next" must never be stored as field data. Un-done recovery and skills/summary handlers all defend against this — keep those guards.
6. ⚠️ **Cache busting:** Any edit to `app.js` or `voice_chat.js` REQUIRES incrementing the `?v=N` query string in the corresponding template, or browsers serve stale code. (Multiple bugs this session were actually "old cached JS still running.")
7. 🧊 **FROZEN — core CSS:** `voice_chat.css`, `style.css`. Voice-button overrides stay inline in JS.
8. ⚠️ **Secrets:** never in any tracked file. `.env` is gitignored AND purged from history. Live keys live only in the Render dashboard.
9. 🔧 **Modification schema:** append-only or minimal clean line-replace diffs. No full-file rewrites. READ & ECHO exact lines before editing.

---

## 5. Operational Edge-Cases & Secondary Fixes Audit

### 5.1 Manual session-data correction (`"skip"` poisoning)
- **Session `yv5vguFxvxYjUDaZ_j596A`** had `experience[0].company == "skip"` — the literal control word was stored as a company name because (pre-fix) un-done recovery reopened into `experience` and the next answer ("skip") was consumed as field data.
- **Action:** Backed up the file (`.bak_skipclean`), then programmatically replaced `company` values matching `skip|none|n/a|""` with `"Self-Employed / Independent"` in **both** `data.experience` and `context.experience`. Restored `done=True`, `phase="done"`. Verified full server-side render afterward.
- **Earlier session `h2UId58a`** was similarly un-stuck: a premature `universal_force_compile` left it `done=True` at ~step 5; manually flipped `done=False`, `phase="simple"`, `current_field="state"`, `step_index=5`, then restarted to clear the in-memory cache. Backup `.bak_predoneflip` saved.
- **Root fix** (so this never recurs): un-done recovery now re-asks the current question and does **not** store the triggering control word.

### 5.2 Non-bugs confirmed as intended behavior
- **`/terms` navigation:** `templates/index.html` has a footer `<a href="/terms" target="_blank">Terms of Service</a>` and `app.js checkTermsAcceptance()` redirects unaccepted users to `/terms`. Confirmed working-as-designed. The *real* bug was that the terms redirect dropped `voice_session` — fixed via `return` param round-trip.
- **"No preview on form load":** `/build?mode=form` (`index.html`) does **not** auto-render a preview; it requires a **Build** click to call `/api/build`. Confirmed intended.
- **`favicon.ico 404`:** Browser auto-requests a favicon that doesn't exist. Cosmetic, harmless, no fix.

### 5.3 Ad-hoc debugging / session-management actions
- **Transcript rehydration discovery:** found `session["history"]` was initialized `[]` but never written; added per-turn recording so rehydration has data.
- **Workspace cleanup:** archived 100 stale session files to `voice_sessions_archive_<ts>/` (656K) to start fresh; later added `voice_sessions_archive_*/` to `.gitignore`.
- **Server lifecycle:** repeated `fuser -k 8000/tcp` → relaunch `uvicorn` to clear in-memory session cache after on-disk edits (memory-first load means disk edits need a restart to take effect).
- **Cache-busting bumps:** `app.js v4→5→6→7`, `voice_chat.js v24→25` to force browsers off stale code.
- **Security remediation:** purged `.env` and secret-bearing `MIGRATION_NOTES.md` from all 39 commits via `git filter-branch`; stripped an old embedded GitHub PAT from the archived original repo's remote URL; full history secret-scan came back clean.
- **Deploy prep verification:** prod-mode boot test (`APP_ENV=production PORT=9999`) → `/healthz` returned `{"status":"ok","env":"production"}`.

---

*Compiled 2026-06-10. Save as internal engineering reference.*
