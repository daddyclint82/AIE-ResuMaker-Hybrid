# AIE ResuMaker — Setup & Run

## Local Run

```bash
cd /home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid
./venv/bin/python main.py
```

Server starts on `http://127.0.0.1:8000`.

## Health Check

```bash
curl -s http://127.0.0.1:8000/healthz
```

## Background Run

```bash
nohup ./venv/bin/python main.py > /tmp/hybrid_server.log 2>&1 &
echo $! > /tmp/hybrid.pid
```

Stop with:

```bash
kill $(cat /tmp/hybrid.pid)
```

## Environment Variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `GROQ_API_KEY` | No | None | Used for summary generation and skills categorization; falls back to templates if missing. |
| `GROQ_MODEL` | No | `llama-3.1-8b-instant` | Extraction model. |

Keep `.env` out of Git (`git status` should not show it).

## Testing

### Fast backend regression

```bash
./venv/bin/python tests/test_optional_boundary_patch.py
```

### Full end-to-end (requires server on localhost:8000)

```bash
./venv/bin/python tests/test_battle_full.py
```

### Manual smoke test

```bash
# Start server, then:
curl -s -X POST http://127.0.0.1:8000/api/voice/start
```

## Deployment

- Render config: `render.yaml`
- Health endpoint served at `/healthz`
- Playwright/Chromium preview generation is disabled on Render free tier — CSS watermark fallback is used.

## Logs & Session Files

- Server log: `server.log` (project root)
- Session storage: `voice_sessions/*.json`
- No automatic cleanup currently exists — see [`docs/known-blockers.md`](./known-blockers.md).
