# AIE ResuMaker Hybrid — README

A conversational, voice-first resume builder that works on mobile and desktop. Users can speak their resume into existence through a chat interface, or fill out a traditional form on desktop.

## Status: In Development — Functional, Not Deployed

This is a **separate project** from the live [AIE ResuMaker](https://aie-resumaker.onrender.com). It lives in `aie-resumaker-hybrid/` and is **not yet pushed to GitHub or deployed.**

---

## What Works

### Voice Chat Mode (`/build?mode=voice`)
- **Conversational flow** — AI asks 12 questions one at a time (name, email, jobs, education, skills, etc.)
- **Speech recognition** — Browser-native `SpeechRecognition` API, continuous listening
- **Pause-safe** — Pausing mid-sentence no longer overwrites text (accumulates finalized transcripts)
- **Text fallback** — Type if you don't want to use mic
- **Clear button** — ✕ wipes text + accumulated transcript if speech recognition messes up
- **"I had more to say"** — After sending, tap ↩️ to append more info without advancing to next question
- **Progress bar** — Shows % complete at top
- **Mode toggle** — ✏️ Type button switches to form mode

### Form Builder Mode (`/build?mode=form`)
- **Full form** — All fields from original AIE ResuMaker
- **Auto-populate from voice** — When user clicks "View Resume" after voice chat, all collected data fills the form
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
- **Groq integration** — `llama-3.1-8b-instant` for per-field extraction (name, email, experience, etc.)
- **Fallback** — If no Groq key or API error, uses raw transcript
- **Simple dict sessions** — No classes, no persistence, in-memory only

---

## What Has Stumped Us

### 1. Context Loss During Development
Multiple times the assistant lost context mid-task, outputting garbled text or repeating failed commands. This burned a lot of session time.

**Workaround:** Use `update_plan` to checkpoint progress, restart if output becomes garbled.

### 2. Subagent Failed with Forked Context
Spawned subagent with `context="fork"` inherited 328 messages of broken attempts, then aborted.

**Lesson:** Always use `context="isolated"` for clean subagents.

### 3. Forward Reference Type Annotation Crash
`resume_sessions: Dict[str, "ResumeState"] = {}` crashed at module load because `ResumeState` class didn't exist yet.

**Fix:** Moved class before variable, then later stripped all ResumeState code entirely.

### 4. Overengineering the First Voice Attempt
Original voice code (June 4 early session) had 550+ lines of `ResumeState` class with confidence scores, complex merge logic. It never worked.

**Lesson:** Start with dicts, add classes only when complexity demands.

### 5. Speech Recognition Overwriting on Pause
Browser `SpeechRecognition` finalizes segments on pause, then restarts fresh — which overwrote the previous text.

**Fix:** Accumulate finalized transcripts in module-level `accumulatedFinal` variable.

### 6. Scope Bugs in JavaScript
`accumulatedFinal` was declared inside `setupSpeechRecognition()` function scope, so `sendMessage()` couldn't clear it.

**Fix:** Moved to module-level scope.

---

## Future Hurdles

### High Priority
| Hurdle | Why It Matters |
|--------|---------------|
| **Browser testing** | SpeechRecognition only works in Chrome/Safari. Need real device testing. |
| **Field mapping accuracy** | Groq sometimes returns weird formats for experience/education arrays. Need robust parsing. |
| **Mobile UX polish** | Chat bubbles, progress bar, buttons need real-world mobile testing. |
| **Error recovery** | Network failures, Groq timeouts, mic permission denials need graceful handling. |

### Medium Priority
| Hurdle | Why It Matters |
|--------|---------------|
| **GitHub push** | Project is local only. Needs remote repo. |
| **Render deployment** | Need separate Render instance from live app. |
| **Stripe integration** | Payment flow exists but untested in hybrid context. |
| **Resume preview** | Watermarked preview generation needs testing with voice-collected data. |

### Low Priority
| Hurdle | Why It Matters |
|--------|---------------|
| **Multi-language support** | SpeechRecognition defaults to `en-US`. |
| **Voice session timeout** | Sessions stay in memory forever. Need cleanup. |
| **Conversation history** | No way to review/edit previous answers in chat. |
| **Skip questions** | No "skip this question" button yet. |

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

## Git History

| Commit | What |
|--------|------|
| `80877d4` | Initial: copy from aie-resumaker, strip broken voice code |
| `c886396` | Voice API backend: 3 endpoints, Groq integration |
| `9c3f5e4` | Voice chat frontend: HTML/JS/CSS |
| `6a238aa` | Landing page mode detection |
| `972be36` | Wire voice data into form builder |
| `e83e4f1` | Mode toggle buttons |
| `0d77c9b` | Fix speech accumulation on pause |
| `832149d` | Clear input after each question |
| `099e876` | Fix accumulator scope bug |
| `a09d05d` | Add clear button |
| `8d836ee` | Add "I had more to say" button |

---

## Known Issues

1. **SpeechRecognition browser support** — Only Chrome, Safari, Edge. Firefox not supported.
2. **No session cleanup** — Voice sessions stay in memory forever. Server restart wipes all.
3. **Experience/education array parsing** — Groq sometimes returns malformed JSON. Needs better error handling.
4. **Untested on actual mobile** — All testing done via curl and desktop browser.
5. **Not deployed** — Local development only.

---

## Next Steps (Priority Order)

1. Test full voice→form flow on real phone with Chrome
2. Fix any field mapping bugs found during testing
3. Push to GitHub repo
4. Deploy to Render (separate instance from live app)
5. Add "skip question" button
6. Add conversation history / review previous answers

---

*Project started: 2026-06-04*
*Last updated: 2026-06-04 22:24 CDT*
