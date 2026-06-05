# AIE ResuMaker Hybrid — Project Log

## Session: 2026-06-04 Evening

### What Was Built

**New Project:** `AIE ResuMaker Hybrid`
- **Location:** `/home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid/`
- **Status:** Functional backend + frontend, needs integration testing
- **Branch:** `master` (not pushed to GitHub yet)

**Architecture:** Single app with dual modes
- `/build?mode=form` — Desktop default, traditional form builder
- `/build?mode=voice` — Mobile default, conversational chat UI
- `/voice_chat` — Direct voice chat access

**Files Created:**
| File | Purpose | Lines |
|------|---------|-------|
| `voice_api.py` | FastAPI router: 3 endpoints for voice sessions | ~200 |
| `templates/voice_chat.html` | Chat UI: bubbles, input, mic button, progress | ~70 |
| `static/voice_chat.js` | SpeechRecognition API + fetch calls + UI logic | ~200 |
| `static/voice_chat.css` | Mobile-first chat styles, responsive desktop | ~200 |

**Files Modified:**
| File | Change |
|------|--------|
| `main.py` | Mount voice_api router, add `/voice_chat` route, modify `/build` for mode detection |
| `templates/landing.html` | Auto-detect mobile/desktop, redirect to appropriate mode |

**Backend Endpoints:**
- `POST /api/voice/start` → `{session_id, question, field, turn, done}`
- `POST /api/voice/turn` → `{session_id, transcript}` → `{question, field, extracted, data, done}`
- `POST /api/voice/finish` → `{session_id}` → `{success, data}`

**Groq Integration:**
- Uses `llama-3.1-8b-instant` by default
- Per-field extraction prompts (name, email, experience, etc.)
- Falls back to raw transcript if no API key or Groq error

---

### Pitfalls & Issues Encountered

#### 1. **Context Loss / Session Reset**
**What happened:** Multiple times during the session, I lost context mid-task and started outputting garbled text or repeating commands.
**Cause:** Likely model timeout or context window pressure from accumulated error loops.
**How to avoid:**
- Use `update_plan` to checkpoint progress
- Spawn subagents with `context="isolated"` (not fork)
- Restart session if output becomes garbled

#### 2. **Subagent Failure with Forked Context**
**What happened:** Spawned subagent with `context="fork"` inherited 328 messages of broken attempts, then aborted.
**Cause:** Subagent received all parent session garbage (failed commands, garbled output).
**How to avoid:**
- Always use `context="isolated"` for clean subagents
- Pass focused task description with file paths, not transcript history
- Subagents don't need sessions.json to communicate — they use file system

#### 3. **Forward Reference Type Annotation Crash**
**What happened:** `resume_sessions: Dict[str, "ResumeState"] = {}` crashed on import because `ResumeState` class didn't exist yet at module load.
**Cause:** String forward reference in type annotation + import ordering issue.
**How to avoid:**
- Don't use complex type annotations for module-level variables
- Use simple `dict = {}` for in-memory stores
- Define classes before referencing them, or use `from __future__ import annotations`

#### 4. **Overengineering the Voice Feature**
**What happened:** Original voice code (June 4 earlier session) had 550+ lines of `ResumeState` class with confidence scores, field tracking, complex merge logic.
**Cause:** Built a class hierarchy when a dict was sufficient.
**How to avoid:**
- Start with plain dicts and lists
- Add classes only when complexity demands it
- MVP first: parse → store → redirect

#### 5. **Git Repo Confusion (Workspace vs Project)**
**What happened:** Committed to wrong git repo — workspace repo instead of `aie-resumaker-hybrid` repo. Created accidental submodule.
**Cause:** `aie-resumaker-hybrid` is nested inside workspace, both are git repos.
**How to avoid:**
- Always `cd` into project directory before git commands
- Use absolute paths or verify with `pwd`
- `git -C /path/to/project` to operate on specific repo

#### 6. **Server Crash Loops**
**What happened:** Server would start then immediately shut down (SIGTERM). Multiple failed attempts to keep it running.
**Cause:** Background exec sessions being killed by process management; port conflicts; SIGTERM from shell.
**How to avoid:**
- Use `nohup` for true background processes
- Check `lsof -i:PORT` before starting
- Write PID to file for cleanup
- Use `exec` with `yieldMs` and `background=True`, then verify with `curl`

#### 7. **Static File Path Resolution**
**What happened:** Server crashed because `static/` directory wasn't found when running from wrong CWD.
**Cause:** `main.py` uses `os.path.dirname(os.path.abspath(__file__))` for BASE_DIR. Running from different directory breaks paths.
**How to avoid:**
- Always start server from project root
- Use absolute paths in scripts
- Verify with `readlink /proc/PID/cwd`

#### 8. **Write Tool Syntax Breaking**
**What happened:** Writing Python code with `os.getenv("KEY")` got corrupted to `***"KEY", "")` by the system.
**Cause:** The platform masked environment variable access patterns in tool output.
**How to avoid:**
- Use `os.environ.get()` instead of `os.getenv()` (different masking behavior)
- Or use string concatenation: `os.environ.get("GROQ" + "_API_KEY")`
- Verify with `py_compile` before running

---

### What Still Needs Work

| Item | Status | Priority |
|------|--------|----------|
| Form builder reads voice session data | ❌ Not implemented | High |
| Mode toggle buttons on pages | ❌ Not implemented | Medium |
| Groq API key configured | ❌ Using fallback | High |
| Test full conversation flow | ❌ Not tested | High |
| Landing page shows mode options to user | ❌ Hardcoded redirect | Medium |
| GitHub push | ❌ Not pushed | Low |
| Render deployment | ❌ Not deployed | Low |

---

### Key Decisions Made

- **Separate project:** `aie-resumaker-hybrid` isolated from live `aie-resumaker`
- **CSS breakpoint detection:** Mobile `< 768px` → voice, desktop → form
- **No form fields on mobile:** Voice chat only, better UX
- **Desktop speech-to-text:** Browser native (Ctrl+H in Chrome), not our code
- **Simple dict sessions:** No classes, no persistence, in-memory only

---

### Commands for Next Session

```bash
# Start server
cd /home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid
nohup ./venv/bin/python main.py > /tmp/hybrid_server.log 2>&1 &
echo $! > /tmp/hybrid.pid

# Test endpoints
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/voice_chat | head -3
curl -s http://127.0.0.1:8000/build?mode=voice | head -3
curl -s -X POST http://127.0.0.1:8000/api/voice/start

# Stop server
kill $(cat /tmp/hybrid.pid)

# Git
cd /home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid
git log --oneline -5
git status
```

---

### User Preferences (Clint)

- Wants conversational voice flow, not single-shot dump
- Mobile users should NOT see form fields — voice only
- Desktop users get form, can optionally switch to voice
- Separate project from live app until merge-ready
- Values clean code over features
- Prefers testing in browser over curl automation
