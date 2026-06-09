# Handoff — AIe ResuMaker File Generation

## Current Architecture State
- PDF/DOCX generators (`generate_docx`, `generate_pdf` in `main.py`) are **fully functional** and render all sections (Experience, Projects, Competencies, Education, Certifications, References) when fed clean data.
- **Upstream bug:** The voice state machine populates `skills` with project names and produces truncated `skills_categorized`. This corrupts the payload before it reaches the generators.
- The `generate_real_resume.py` script proves that feeding a complete, correctly structured payload produces 39 KB DOCX and 7.2 KB PDF files.

## Verified Filepaths
| File | Path |
|------|------|
| `main.py` | `/home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid/main.py` |
| `voice_api.py` | `/home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid/voice_api.py` |
| `voice_chat.js` | `/home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid/static/voice_chat.js` |
| Browser test | `/home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid/tests/test_voice_browser.py` |
| File gen test | `/home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid/tests/test_file_generation.py` |
| Manual script | `/home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid/generate_real_resume.py` |

## Next Session Target
Write and wire a **`sanitize_resume_data(raw_data)`** function into the `voice_preview()` route in `voice_api.py`. This function intercepts the malformed payload from the voice state machine and restructures it before passing to `generate_docx`/`generate_pdf`. Do not modify the voice state machine itself.
