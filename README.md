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
- **3 voice endpoints:**
  - `POST /api/voice/start` — Creates session, returns first question
  - `POST /api/voice/turn` — Accepts transcript, returns next question + extracted data
  - `POST /api/voice/finish` — Returns all collected data
- **Groq integration** — `llama-3.1-8b-instant` for per-field extraction
- **Fallback** — If no Groq key or API error, uses raw transcript
- **Simple dict sessions** — No classes, no persistence, in-memory only

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

### User Requirements (Locked In)
- Mobile users: voice chat only (no form fields)
- Desktop users: form default, can switch to voice
- ADHD-friendly: incremental micro-questions, little wins
- Separate from live app until merge-ready

---

*Project started: 2026-06-04*
*Last updated: 2026-06-04 22:30 CDT*
*Next focus: Redesign voice flow for incremental ADHD-friendly questions*
