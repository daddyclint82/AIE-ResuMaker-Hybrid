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

**Simple:** full_name, email, phone, address, city, state, industry, job_title, experience_level, education_level (city and state are read from the address and asked only if it lacks them)

**Experience:** For each job: company → title → dates → location → bullets (loop: "Add another bullet?") → "Add another job?"

**Summary:** 4 interview questions → the LLM auto-generates professional summary

**Skills:** Comma-separated list → the LLM categorizes into weighted categories

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
2. Build top-15 category list to reduce model noise.
3. The LLM returns JSON: `{"Category": [{"name": "Python", "weight": 95}]}`.

### Server-Authoritative Build

`POST /api/build` accepts an optional `voice_session` field.

- **When present (voice/mobile path):** rich repeating sections are pulled directly from `voice_sessions/*.json`, bypassing the lossy form-DOM round-trip.
- **When absent (desktop/form path):** the original form-DOM build runs unchanged.

Treating the frontend form DOM as the source of truth for voice builds is a fatal structural violation that reintroduces the partial/anemic resume bug.

### Voice Input Strategy

- No custom microphone button or in-browser `SpeechRecognition` integration.
- Users dictate via native iOS/Android keyboard voice input.
- The UI is the **Resume Chat Assistant** (`index.html` has the mode-switch button; `voice_chat.html` is the mobile chat route).

### Static Asset Caching

- Templates link static files with `{{ asset_url('app.js') }}`, which appends `?v=` + the first 12 hex chars of the file's SHA-256.
- A `/static` request whose `v` matches is served `Cache-Control: public, max-age=31536000, immutable`; any other `/static` request gets `no-cache` (ETag revalidation, a 304 when unchanged).
- Editing a file changes its URL on the next deploy, so there are no `?v=NN` numbers to bump and no reason to send `no-store` (which made phones re-download every script on every page).
- Render's edge already Brotli-compresses responses, so the app does not add gzip middleware.

### Terms Gate

Legal acceptance is enforced before the chat flow begins. `/terms` carries a `return` param so accepting terms routes back to `/build?...voice_session=X` without dropping the session.

### Pricing & Referrals

- Pricing tiers: $9.99 regular, $4.99 referral/student.
- Referral system: real backend tracking for $4.99 discount with "Give $5, Get $5" messaging.
- The server decides the price. `tier: "discount"` gets the student price only with a referral code the server issued whose link has a recorded visit (the Share & Save rule, terms 5.4); otherwise checkout answers 403.
- Referral codes vouch for themselves: 5 random bytes plus the first 5 bytes of their HMAC-SHA256 under `REFERRAL_SECRET`, base32, 16 characters. Visit counts stay in memory, which Render's free tier empties on every deploy, restart and idle spin-down, so an issued code starts again at zero instead of being refused. The browser forgets a stored code the server answers 404 for and gets a new one. Without `REFERRAL_SECRET` each process signs with a random key, and codes last until the next restart.
- Guarded by `tests/test_referral_pricing.py` (no server, no network).

### Resume Access & Payment

- A resume ID is the only key to a resume, so it is random: `secrets.token_urlsafe(16)`, 128 bits. `get_resume()` rejects anything not in that format before it touches storage.
- `/api/preview-timer` and `/api/check-payment` need only the ID. Only the browser that built the resume, which already received the full preview from `/api/build`, and Stripe ever hold it.
- `/api/download` serves paid resumes only (402 otherwise). `/success` and the Stripe webhook record the payment for the resume stored in the checkout session's metadata. The webhook needs `STRIPE_WEBHOOK_SECRET` (503 without it).
- Stripe 15 objects have no dict `.get()`, so these routes call `.to_dict()` first.
- The `/success` page links both files, the PDF first. Until 2026-11-20 it linked only the `.docx` and nothing on the site linked the PDF.
- Guarded by `tests/test_resume_access.py` (no server, no network).

### Resume Themes

- Professional, Modern, Minimal with distinct CSS.
- The theme styles the HTML preview only. The PDF and DOCX downloads have one layout each.

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
  skills → store + categorize with the LLM
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
        "summary": "...",           # LLM-generated
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

## LLM Integration (3 Points)

1. **Summary Generation** — MiniMax M3.1 Flash on Ollama Cloud (`LLM_MODEL`, `LLM_BASE_URL`), 2-3 sentences from 4 interview answers.
2. **Skills Categorization** — Same model, returns weighted JSON with 15 prioritized categories.
3. **Fallback** — If no key or the call fails, uses template concatenation for summary, flat list for skills.

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

### 2026-11-20 — Two Loops in the Mobile Flow

- **"Done" at "Add another job?" re-asked forever.** The global "done" safety check in `process_answer` and the hard stop in `_process_experience` caught the word before the `exp_done` branch could move to the summary (a regression of Fix 4). Both now step aside when `exp_done` is set.
- **The tech-stack project question shifted answers and looped.** Display asked 4 project questions while storage and back used the 3 `PROJECT_FIELDS`, so tech was saved as description, description as result, and "What was the outcome or result?" repeated. `get_current_state`, `_process_optional` and `_go_back_optional` now all use `_project_fields(session)`.
- Guarded by `tests/test_voice_flow_regressions.py` (no server, no network).

### 2026-11-20 — Summary and Skills Model: MiniMax M3.1 Flash on Ollama Cloud

- Groq retired `llama-3.3-70b-versatile` for non-enterprise keys, so production was writing template summaries. On the app's real prompts for six made-up candidates, MiniMax M3.1 Flash beat GPT-OSS 20B (`docs/review/llm-model-test/`).
- The provider is env-only: `LLM_BASE_URL` (default `https://ollama.com/v1`), `LLM_API_KEY` (or Ollama's usual `OLLAMA_API_KEY`, which production uses), `LLM_MODEL` (default `minimax-m3.1-flash`). Any OpenAI-compatible API works if the model accepts `reasoning_effort`.
- Both calls send `reasoning_effort: "low"` with room for reasoning tokens (summary 1024, skills 3000). At default effort the old 300-token summary budget went on thinking and the summary came back cut off.
- Both calls wait up to 45 s (`LLM_TIMEOUT`). On 2026-11-20 about 1 call in 5 sat ~20 s at Ollama before answering, and the old 15 s / 20 s limits (sized for Groq) sent those to the template; on production the summary and the skills each fell back once that way. The chat shows its typing indicator while it waits.
- Ollama caps concurrent requests per account, so the site sends one LLM request at a time.
- The skills prompt read the core edge and job keywords from `data`, where they never are, so both were always blank. It now reads `context["summary_answers"]`. With the keywords filled in, the model started adding them as skills the user never listed, so the skills prompt now allows only the user's skills, each once.
- The summary prompt now rules out "I"/"my" and names the buzzwords to skip: in the model test MiniMax wrote in first person in 1 of 6 summaries and used buzzwords in 2; on the final code, 0 of 6 for both.
- Model text is kept as written. It was NFKC-normalized while the PDF's built-in fonts printed "H₂S" as a black box; once the PDF embedded Liberation fonts, NFKC only degraded it (H₂S to H2S, ™ to TM, m² to m2). The one character it saved, the non-breaking hyphen, the PDF now folds itself (below).
- `/healthz` reports `"llm": true` once a key is set. Failed calls log `[LLM]` warnings instead of failing silently.
- Guarded by `tests/test_voice_flow_regressions.py` (no server, no network).

### 2026-11-20 — The Address Fills City and State

- The chat asked for the full address and then for city and state again. `city_state_from_address` in `voice_api.py` reads both from the address answer (commas or dictation without them, full state names or codes, ZIP+4, a trailing "USA"); only a part it can't read is asked. Back steps over the skipped questions to the address and clears what it filled.
- A typed state answer is stored as its code ("illinois" to "IL"): the form's State list uses codes.
- The review form lost both: `loadVoiceData` ran before `/api/states` had filled the State list, so no state was selected, the City box stayed disabled, and a disabled field is left out of the build. The PDF and preview header had no location. The form now applies the state once the options exist and enables City; its duplicate address parsing is gone.
- Guarded by `tests/test_voice_flow_regressions.py` (no server, no network).

### 2026-11-20 — PDF Text Outside cp1252: Embedded Liberation Fonts

- reportlab's built-in Times/Helvetica cover only cp1252 and drew everything else as a black box, so user-typed text came out as "Nguy■n", "■à N■ng", "H■S".
- `generate_pdf` now embeds Liberation Serif (Regular, Bold, Italic) and, for the contact line, Liberation Sans, from `fonts/` (2.1.5, SIL OFL 1.1). They are metric-compatible with Times New Roman/Arial: on a 3-page resume every line breaks at the same word and no word moves more than 0.11 pt (`docs/review/pdf-unicode-fonts/`). Each PDF grows by about 85 KB of embedded font subsets.
- Text is NFC-composed first. reportlab can't position combining marks, so accents typed as separate marks (as the Windows Vietnamese keyboard does) landed on the next letter.
- About 225 symbols the Liberation fonts lack (✓ ★ ⇒ ① ❖ ➤ …) still go to the standard Symbol/ZapfDingbats fonts that drew them before. CJK and emoji have no glyph in either and still print as boxes.
- A character neither has prints as its NFKC form when Liberation has that. The non-breaking hyphen (U+2011) that GPT-style models and ChatGPT put in words like "high-performance" printed as a black box; it now prints as a hyphen, and ℃ as °C. The folded text is XML-escaped, so fullwidth ＜ and ＆ stay text instead of becoming Paragraph markup.
- Guarded by `tests/test_pdf_fonts.py`.

### 2026-11-20 — PDF: User Text Is Escaped Before It Enters reportlab Markup

- `generate_pdf` builds reportlab Paragraph markup with its own `<b>`/`<i>` tags and inserted user values into it raw. "AT&T" and "R&D" printed as "AT&T;" and "R&D;", a literal "&amp;" printed as "&", and text that parsed as a tag made `generate_pdf` raise, so `/api/download/{id}?format=pdf` returned 500.
- Every user value now goes through `_pdf_text` where it is inserted: NFC, then `xml.sax.saxutils.escape`. The code's tags stay markup. The name is upper-cased first, because "&amp;".upper() is not an entity.
- NFC moved out of `_pdf_markup`, which runs on the finished markup. There it could fuse a combining mark at the start of a value with the ">" of the tag before it and break the tag. `_pdf_markup` now only sends glyphs the fonts lack to Symbol/ZapfDingbats.
- The DOCX export writes plain text through python-docx and needs no escaping.
- Guarded by `tests/test_pdf_markup_escape.py`.

### 2026-11-20 — No API Docs in Production; Job Titles from the O*NET Download

- In production, `/docs`, `/redoc` and `/openapi.json` listed every endpoint. `FastAPI(openapi_url=None)` turns all three off when `APP_ENV` is `production`; development keeps them.
- The O*NET job-title search had no caller: nothing invoked `setupJobAutocomplete()` in `app.js`. Removed:
  - its three relay endpoints (`/api/jobs/search`, `/api/jobs/{code}` and `/api/jobs/{code}/summary`);
  - the API key that was hard-coded as their default;
  - the unused front-end code behind them.
- **What replaced it.** The form's Job Title box and each job entry's title now suggest titles from `data/job_titles.json`, served by `GET /api/job-titles?q=`.
  - The file holds O*NET 31.0's 48,332 job titles and short forms, built by `scripts/build_job_titles.py` from the free download (CC BY 4.0).
  - Why the download and not the API: the API's Database Services serve the same database. Its keyword search returns the 1,016 official occupation names ("General and Operations Managers" for "store manager"), not the titles people write.
  - Matching: every typed word must start a word of the title. The exact title ranks first, then titles that start with or contain the typed text, shortest first.
  - To refresh for a new O*NET release, run `python scripts/build_job_titles.py <version>`. The footer's credit reads the version from the file.
- Company, university and field-of-study suggestions share the new `setupListAutocomplete` instead of three copies of the same code.
- Guarded by `tests/test_production_config.py` and `tests/test_job_titles.py`.

### 2026-11-21 — Every PDF Carries Its Own Saved Copy

- Render's free tier wipes resumes on every deploy, restart and idle spin-down, but the customer keeps the PDF. `generate_pdf` now puts the resume's data inside the PDF so a later upload page can bring it back exactly, including what reading the page never could (the style, each skill's weight).
- **What is sealed:** the stored resume dict, its `resume_id`, and the Stripe checkout session that paid for it (`mark_resume_paid` now records it). Not `paid`: Stripe says what was paid, never the file.
- **Encrypted, not just signed.** The data holds things the page does not print (the street address, the Stripe session), and resumes are sent to strangers. Fernet (`cryptography`) encrypts and authenticates, so a copy that opens is one this server wrote. The key is derived from `REFERRAL_SECRET` under its own label; without that secret, copies stop opening at the next restart, like referral codes.
- **Where it sits:** an uncompressed stream under a private catalog entry, `/AIEResumeCopy`, added with `pypdf` after reportlab writes the file. Viewers ignore it and the pages are identical. A file attachment was tried first and dropped: it shows as a paperclip in the reader's viewer, and mail filters are wary of PDFs with attachments. About 1 KB per PDF.
- `read_sealed_pdf` returns the copy or `None`. It refuses a compressed or oversized entry without unpacking it, since any file can be handed in.
- If sealing fails, the customer still gets the PDF; the failure is logged and `/healthz` reports `"seal": false`. `/healthz` `"seal": true` means this process sealed a PDF and read it back.
- Nothing reads an uploaded PDF yet; the upload page is a later step.
- Guarded by `tests/test_pdf_seal.py` (no server, no network).

### 2026-11-21 — The Resume Key, and Edits Counted on Stripe

- **The key.** Each purchase has a key like `K7QMA-2XWTB`: 50 bits of HMAC-SHA256 over the purchased resume's ID under `REFERRAL_SECRET` (label `resume-key:`), base32. Reopening a resume will take the PDF and the key, because resumes are sent to strangers and the file alone must not let one of them spend the buyer's edits. The key is not in the PDF.
- The server stores nothing: the saved copy in the PDF names the Stripe session, the session's metadata names the purchased `resume_id`, and the key is recomputed from that.
- The customer sees it on `/success` (with a copy button) and on Stripe's receipt: `payment_intent_data.description` carries it.
- **Edits.** The checkout session's metadata starts `edits_used` at `"0"`. Stripe's record of the purchase is the one place a deploy, restart or idle spin-down doesn't wipe. Sessions created before this have no `edits_used`; read a missing value as 0.
- Proved on Stripe test mode, 2026-11-21: a paid, completed Checkout Session accepts `Session.modify(metadata=...)` and a fresh `retrieve` returns the new value; the description appears on the charge and on Stripe's hosted receipt page.
- Nothing spends an edit or checks a key yet; the upload page and server-side edits are later steps.
- Guarded by `tests/test_resume_key.py` (no server, no network).

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

- LLM calls dominate latency; summary and skills categorization are the expensive points.
- PDF/DOCX export uses reportlab and python-docx locally; on Render, Playwright/Chromium is disabled — CSS watermark fallback keeps previews lightweight.
- Disk session writes happen per turn; growth is unbounded — see [`docs/known-blockers.md`](../known-blockers.md).
