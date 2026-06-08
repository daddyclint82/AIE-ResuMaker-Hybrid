# AIE ResuMaker Hybrid — Architecture Summary

## What It Is
A conversational, voice-first resume builder with ADHD-friendly micro-question design. Users speak or type their resume one field at a time.

## Core Flow (6 Phases)

```
┌─────────┐    ┌──────────┐    ┌─────────┐    ┌────────┐    ┌──────────┐    ┌──────┐
│  Simple │───▶│ Experience│───▶│ Summary │───▶│ Skills │───▶│ Optional │───▶│ Done │
│ 9 fields│    │ Jobs loop │    │  4 Qs   │    │ Categorize│   │ Sections │    │      │
└─────────┘    └──────────┘    └─────────┘    └────────┘    └──────────┘    └──────┘
```

**Simple:** full_name, email, phone, city, state, industry, job_title, experience_level, education_level

**Experience:** For each job: company → title → dates → bullets (loop: "Add another bullet?") → "Add another job?"

**Summary:** 4 interview questions → Groq auto-generates professional summary

**Skills:** Comma-separated list → Groq categorizes into weighted categories

**Optional:** projects → competencies → community → certifications → links (each: collect fields → "Add another?")

## Key Technical Decisions

### Flat Dict State Machine
- No classes, no ORM — plain dicts for sessions
- Context flags track progress within phases
- Phase transitions happen in `_process_*` functions, NOT in `get_current_state`

### Critical Flag: `exp_done`
When `in_bullet_loop` becomes `False`, it has two meanings:
1. "Never started bullets" (first bullet entry)
2. "Just finished bullets" (user said "done")

`exp_done` disambiguates — without it, "done" at "Add another job?" gets treated as a first bullet.

### Summary Generation Timing
**Before fix:** `get_current_state` transitioned to skills before `_process_summary` could generate

**After fix:** `_process_summary` detects last question (q_idx + 1 >= len(QUESTIONS)) and generates summary BEFORE returning state

### Skills Categorization Pipeline
1. Determine priority tier from industry + job keywords (7 tiers: technology, oil_gas, healthcare, finance, creative, trades, general)
2. Build top-15 category list to reduce Groq noise
3. Groq returns JSON: `{"Category": [{"name": "Python", "weight": 95}]}`

## Data Flow

```
User Input (voice/text)
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

1. **Summary Generation** — `llama-3.3-70b-versatile`, 2-3 sentences from 4 interview answers
2. **Skills Categorization** — Same model, returns weighted JSON with 15 prioritized categories
3. **Fallback** — If no API key, uses template concatenation for summary, flat list for skills

## Testing Strategy

- `test_summary_fix.py` — Full voice session simulation, validates summary generation
- `tests/run_questionnaire.py` — Skills categorization with JSON fixtures
- Manual: Browser SpeechRecognition, mobile viewport testing

## Known Issues

1. **Form builder auto-populate** — Partially broken (arrays don't populate correctly)
2. **City/State split** — "Austin, Texas" dumps into city field
3. **Browser support** — SpeechRecognition only works in Chrome/Safari
4. **Session persistence** — In-memory only, no cleanup (sessions grow forever)
5. **Not deployed** — Still local development only

## Architecture Principles

1. **Dicts first, classes later** — Avoid overengineering until necessary
2. **Phase transition AFTER generation** — Never transition before data is ready
3. **Flag ordering matters** — Check terminal flags before loop flags
4. **Isolate data domains** — `summary_answers` separate from `session["data"]`
5. **Filter control words** — "yes"/"done"/"next" from previous phases must be rejected
6. **Always await async** — No `asyncio.run()` inside FastAPI handlers

---

*Generated: 2026-06-08*
*Next: Full end-to-end test → GitHub commit → Deploy*
