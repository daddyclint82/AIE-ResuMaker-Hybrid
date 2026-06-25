# AIE ResuMaker — Known Blockers & Risks

## Active Blockers

None at the moment. The project runs locally and on Render with `/healthz` returning 200.

## Known Test Debt

- **`tests/run_questionnaire.py` fixtures are out of sync.**
  A `skills_review` panel now sits between the skills question and optional sections.
  Fixtures need to send a "done" action (or click equivalent) to exit skills review before optional sections will advance correctly.

## Known Issues / Risks

1. **Form builder auto-populate — partially broken**
   - Arrays do not populate correctly from voice sessions.
   - City/State split fails: "Austin, Texas" may dump entirely into the `city` field.

2. **Session persistence growth**
   - Disk-persisted sessions (`voice_sessions/*.json`) grow forever; no cleanup or retention policy.

3. **Route/filename legacy debt**
   - `/voice_chat`, `voice_chat.html`, `voice_chat.js`, `voice_chat.css` retain the old voice-first naming even though the custom mic button has been removed.

4. **Render preview limitations**
   - Playwright/Chromium is disabled on the free tier; previews use a CSS watermark fallback.

5. **Mobile testing gap**
   - Real-device validation for native dictation behavior is limited.

## Decision Log

See [`docs/architecture/decisions.md`](./architecture/decisions.md) for fixes and architectural changes that resolved earlier blockers.
