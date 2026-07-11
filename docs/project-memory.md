# AIE ResuMaker — Project Memory Hub

Central index for project knowledge. Keep MEMORY.md lean; put durable details here.

## Quick Links

| Topic | Location |
|-------|----------|
| Architecture decisions, performance notes, key fixes | [`docs/architecture/decisions.md`](./architecture/decisions.md) |
| Active blockers, known test debt, risks | [`docs/known-blockers.md`](./known-blockers.md) |
| Setup, run, and testing commands | [`docs/setup-and-run.md`](./setup-and-run.md) |
| Prompt engineering notes | `docs/prompts/` (prompts documented here) |
| Internal historical logs | [`docs/internal/`](./internal/) |

## Project Snapshot

- **Status:** Active — in development
- **Location:** `/home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid/`
- **Started:** 2026-06-04
- **Stack:** Python 3.12, FastAPI, Uvicorn, Jinja2, vanilla JS/CSS, reportlab, python-docx, Stripe, Groq
- **Deployment:** Render (`render.yaml` present; `/healthz` smoke endpoint)

## What It Is

Conversational resume builder. Users answer micro-questions one at a time through a mobile-friendly chat UI. Voice input is native iOS/Android keyboard dictation — no custom mic button. Server-side state machine drives the questionnaire. Groq `llama-3.3-70b` generates professional summaries and categorized skills. Three resume themes, referral/student pricing, PDF/DOCX export.

## Recent Headlines

- Voice chat mode uses native mobile dictation; custom SpeechRecognition mic button removed.
- Server-authoritative build: `/api/build` reads from `voice_sessions/*.json` for voice/mobile sessions instead of relying on the form DOM.
- Terms gate enforced before chat flow begins.
- Optional sections have skip buttons; tech-stack question is conditional.

## Next Step

See [`docs/known-blockers.md`](./known-blockers.md) for current test debt and the next actionable fix.
