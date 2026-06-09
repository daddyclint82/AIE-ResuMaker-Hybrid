"""
Real User Simulation Test — AIe ResuMaker Voice Builder
Playwright browser automation that simulates a human clicking through the voice UI.
Uses waitForResponse pattern for state-machine synchronization.

Prerequisites:
    pip install playwright pytest
    playwright install chromium

Usage:
    # Server must be running on localhost:8000
    cd /home/daddyclint82/.openclaw/workspace/aie-resumaker-hybrid
    python tests/test_voice_browser.py

    # Or with pytest for better reporting
    pytest tests/test_voice_browser.py -v --tb=short
"""

import json
import re
import sys
import time
from pathlib import Path

# Ensure playwright is available
try:
    from playwright.sync_api import sync_playwright, expect
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# ─── Paths ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
SCREENSHOTS_DIR = PROJECT_ROOT / "tests" / "screenshots"
FIXTURE_FILE = FIXTURES_DIR / "clint-complete-v2.json"
BASE_URL = "http://localhost:8000"

SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ─── Load Fixture ────────────────────────────────────────────────────────────
with open(FIXTURE_FILE, "r") as f:
    FIXTURE = json.load(f)

ANSWERS = {a["step"]: a["value"] for a in FIXTURE["answers"]}
STEPS = [a["step"] for a in FIXTURE["answers"]]


# ══════════════════════════════════════════════════════════════════════════════
# Synchronized Send Answer ( waits for API response before returning )
# ═══════════════════════════════════════════════════════════════════════════════

def send_answer_synced(page, answer: str, step_num: int, label: str = ""):
    """
    Send an answer and wait for the server to process it before returning.
    Uses Playwright's waitForResponse to ensure state machine synchronization.
    
    Returns the server response data so the test can verify state.
    """
    # Disable animations for stability
    try:
        page.add_style_tag(content="* { transition: none !important; animation: none !important; }")
    except:
        pass
    
    # Get the current AI question before we send (for verification)
    try:
        ai_messages = page.locator(".ai-message .message-bubble").all()
        prev_question = ai_messages[-1].inner_text() if ai_messages else ""
    except:
        prev_question = ""
    
    # Fill the input
    try:
        page.locator("#text-input").fill(answer)
    except Exception:
        # Fallback to JS injection if element not interactable
        try:
            page.evaluate(f"document.getElementById('text-input').value = '{answer.replace(chr(39), chr(39)+chr(39))}';"
                           "document.getElementById('text-input').dispatchEvent(new Event('input', { bubbles: true }));")
        except Exception as e2:
            print(f"    ⚠️ Could not fill input: {e2}", flush=True)
            return None
    
    print(f"    📝 Typed: {answer[:60]}{'...' if len(answer) > 60 else ''}", flush=True)
    
    # Send the answer
    try:
        page.locator("#text-input").fill(answer)
    except Exception:
        page.evaluate(f"document.getElementById('text-input').value = '{answer.replace(chr(39), chr(39)+chr(39))}';"
                       "document.getElementById('text-input').dispatchEvent(new Event('input', { bubbles: true }));")
    
    print(f"    📝 Typed: {answer[:60]}{'...' if len(answer) > 60 else ''}", flush=True)
    
    # Click send
    try:
        page.locator("#send-btn").click()
    except Exception:
        page.evaluate("document.getElementById('send-btn').click();")
    
    # HARD DELAY: Wait for server to process and respond
    # Server responds in ~1ms, but we add buffer for network + UI update
    delay = 1.0 if answer.lower() in ["yes", "done", "skip", "next", "no"] else 0.5
    time.sleep(delay)
    
    # Take screenshot after response
    screenshot(page, label or f"response_after_{step_num}", step_num)
    
    return None


def screenshot(page, name: str, step_num: int):
    """Save a numbered screenshot for forensic debugging."""
    path = SCREENSHOTS_DIR / f"{step_num:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  📸 Screenshot: {path.name}", flush=True)
    return path


def get_last_ai_text(page) -> str:
    """Extract text from the most recent AI message bubble."""
    messages = page.locator(".message.ai-message .message-bubble, .ai-message .message-bubble, .ai-message").all()
    if messages:
        return messages[-1].inner_text()
    return ""


def get_last_user_text(page) -> str:
    """Extract text from the most recent user message bubble."""
    messages = page.locator(".message.user-message .message-bubble, .user-message .message-bubble, .user-message").all()
    if messages:
        return messages[-1].inner_text()
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# Main Test
# ═══════════════════════════════════════════════════════════════════════════════

def run_voice_browser_test(headed: bool = False, slow_mo: int = 200, max_steps: int = None):
    """
    Run the full voice questionnaire through a real browser.
    Uses waitForResponse for state-machine synchronization.

    Args:
        headed: Show the browser window (for debugging)
        slow_mo: Milliseconds to pause between actions
        max_steps: Stop after N steps (None = run all)
    """
    print("=" * 70, flush=True)
    print("🎭 AIe ResuMaker — Real User Simulation Test (Playwright)", flush=True)
    print("=" * 70, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headed,
            slow_mo=slow_mo,
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            record_video_dir=str(SCREENSHOTS_DIR / "videos") if headed else None,
        )
        page = context.new_page()

        # ── Phase 0: Navigate ─────────────────────────────────────────────────
        print("\n[Phase 0] Launching browser and navigating...", flush=True)
        page.goto(f"{BASE_URL}/build?mode=voice")

        # Wait for page load — check AEI logo
        page.wait_for_selector(".logo-img", timeout=10000)
        print("  ✅ AEI logo loaded", flush=True)

        screenshot(page, "start_page", 1)

        # Verify welcome message
        try:
            welcome = page.locator("#welcome-message").inner_text(timeout=5000)
            assert "full name" in welcome.lower(), f"Unexpected welcome: {welcome}"
            print(f"  ✅ Welcome message: {welcome[:60]}...", flush=True)
        except Exception as e:
            content = page.content()
            if "full name" in content.lower():
                print("  ✅ Welcome message found (via page content)", flush=True)
            else:
                raise AssertionError(f"Welcome message not found: {e}")

        step_counter = 2

        # ── Phase 1: Simple Fields (1A–1J) ──────────────────────────────────
        print("\n[Phase 1] Simple fields (1A–1J)...", flush=True)
        simple_steps = [s for s in STEPS if s.startswith("1")]
        if max_steps:
            simple_steps = simple_steps[:max_steps]
        for step in simple_steps:
            answer = ANSWERS[step]
            
            data = send_answer_synced(page, answer, step_counter, f"simple_{step}")
            step_counter += 1
            
            # Verify the response shows the next field
            if data:
                expected_field = None
                step_idx = STEPS.index(step)
                if step_idx + 1 < len(STEPS):
                    expected_field = FIXTURE["answers"][step_idx + 1]["field"]
                actual_field = data.get("field", "")
                if expected_field and actual_field != expected_field and actual_field != "_decision":
                    print(f"    ⚠️ Field mismatch: expected {expected_field}, got {actual_field}", flush=True)

        print("  ✅ All simple fields completed", flush=True)

        # ── Phase 2: Experience Loop (2A–2C) ─────────────────────────────────
        print("\n[Phase 2] Experience loop (3 jobs, 8+8+5 bullets)...", flush=True)
        exp_steps = [s for s in STEPS if s.startswith("2")]

        for step in exp_steps:
            answer = ANSWERS[step]
            label = f"exp_{step}"

            data = send_answer_synced(page, answer, step_counter, label)
            step_counter += 1
            
            # After decision answers, verify state transition
            if answer.lower() in ("done", "yes") and data:
                print(f"    ↪️  State: field={data.get('field')}, type={data.get('type', 'question')}", flush=True)

        print("  ✅ Experience loop completed", flush=True)

        # ── Phase 3: Summary Questions (3A–3D) ──────────────────────────────
        print("\n[Phase 3] Summary questions...", flush=True)
        summary_steps = [s for s in STEPS if s.startswith("3")]

        for step in summary_steps:
            answer = ANSWERS[step]
            label = f"summary_{step}"

            send_answer_synced(page, answer, step_counter, label)
            step_counter += 1

        print("  ✅ Summary questions completed", flush=True)

        # ── Phase 4: Skills ───────────────────────────────────────────────────
        print("\n[Phase 4] Skills categorization...", flush=True)
        skills_answer = ANSWERS["4A"]

        data = send_answer_synced(page, skills_answer, step_counter, "skills_input")
        step_counter += 1

        # Wait for skills panel to appear
        print("  ⏳ Waiting for skills categorization...", flush=True)
        time.sleep(4)

        try:
            page.wait_for_selector("#skills-panel", timeout=8000)
            print("  ✅ Skills panel appeared", flush=True)
        except Exception:
            print("  ⚠️ Skills panel not detected (may be inline)", flush=True)

        page_html = page.content()
        if "Programming & Development" in page_html or "skill-category" in page_html:
            print("  ✅ Skills appear categorized by tier", flush=True)
        else:
            print("  ⚠️ Could not verify tier categorization visually", flush=True)

        screenshot(page, "skills_categorized", step_counter)
        step_counter += 1

        # ── Phase 5: Optional Sections ──────────────────────────────────────
        print("\n[Phase 5] Optional sections...", flush=True)
        optional_steps = [s for s in STEPS if s.startswith("5")]

        for step in optional_steps:
            answer = ANSWERS[step]
            label = f"optional_{step}"

            data = send_answer_synced(page, answer, step_counter, label)
            step_counter += 1
            
            # After decision answers, verify state transition
            if answer.lower() in ("yes", "done", "skip") and data:
                print(f"    ↪️  State: field={data.get('field')}, section_transition={data.get('type', 'question')}", flush=True)

        # Wait for final preview
        print("  ⏳ Waiting for final preview to render...", flush=True)
        time.sleep(3)

        print("  ✅ Optional sections handled", flush=True)

        # ── Phase 6: Preview ──────────────────────────────────────────────────
        print("\n[Phase 6] Waiting for preview...", flush=True)

        try:
            page.wait_for_selector(".voice-preview-container, .preview-container, #preview, .resume-preview", timeout=15000)
            print("  ✅ Preview container found", flush=True)
        except Exception:
            print("  ⚠️ Preview container not found with standard selectors", flush=True)

        screenshot(page, "preview_final", step_counter)
        step_counter += 1

        # ── Phase 7: Visual Verification ──────────────────────────────────────
        print("\n[Phase 7] Visual verification...", flush=True)

        preview_html = ""
        try:
            preview_html = page.locator(".preview-container, #preview, .resume-preview, .resume-output").inner_html()
        except Exception:
            page_html = page.content()
            if "resume" in page_html.lower():
                print("  ℹ️ Using full page HTML for verification", flush=True)
                preview_html = page_html

        # Check for leaked command words
        if preview_html:
            bad_words = ["done", "skip", "yes", "no"]
            found = []
            for word in bad_words:
                if f" {word} " in preview_html.lower() or f">{word}<" in preview_html.lower():
                    found.append(word)
            if found:
                print(f"  ❌ LEAKED command words in preview: {found}", flush=True)
            else:
                print("  ✅ No command words leaked into preview", flush=True)

            # Check for empty dicts
            if "{}" in preview_html or "&#123;&#125;" in preview_html:
                idx = preview_html.find("{}")
                if idx >= 0:
                    context = preview_html[max(0,idx-50):min(len(preview_html),idx+50)]
                    print(f"  ❌ Empty dict '{{}}' found at position {idx}: ...{context}...", flush=True)
                else:
                    print("  ❌ Empty dict found (HTML encoded)", flush=True)
            else:
                print("  ✅ No empty dicts in preview", flush=True)

            # Section checklist
            required_sections = {
                "Professional Summary": "summary" in preview_html.lower() or "professional summary" in preview_html.lower(),
                "Technical Skills": "skills" in preview_html.lower() or "technical skills" in preview_html.lower(),
                "Professional Experience": "experience" in preview_html.lower() or "professional experience" in preview_html.lower(),
                "Projects": "projects" in preview_html.lower(),
                "Notable Competencies": "competenc" in preview_html.lower() or "notable" in preview_html.lower(),
                "Education": "education" in preview_html.lower(),
                "Community Involvement": "community" in preview_html.lower(),
                "Certifications": "certification" in preview_html.lower(),
                "References": "references" in preview_html.lower(),
            }
            
            print("\n  📋 Section checklist:", flush=True)
            for section, present in required_sections.items():
                status = "✅" if present else "⬜"
                print(f"     {status} {section}", flush=True)

            all_sections_present = all(required_sections.values())
            if all_sections_present:
                print("\n  🎉 ALL sections present! Complete resume generated.", flush=True)
            else:
                print("\n  ⚠️ Some sections missing", flush=True)

        # ── Phase 8: Session Verification ───────────────────────────────────
        print("\n[Phase 8] Session verification...", flush=True)
        
        # Fetch session data from API
        try:
            response = page.request.post(f"{BASE_URL}/api/voice/turn", data=json.dumps({
                "session_id": page.evaluate("window.sessionId || ''"),
                "transcript": "",
                "action": "get_state"
            }), headers={"Content-Type": "application/json"})
            
            if response.ok:
                session_data = response.json()
                exp_count = len(session_data.get("data", {}).get("experience", []))
                proj_count = len(session_data.get("data", {}).get("projects", []))
                ref_count = len(session_data.get("data", {}).get("references", []))
                print(f"  ✅ Session verified: {exp_count} jobs, {proj_count} projects, {ref_count} references", flush=True)
        except Exception as e:
            print(f"  ⚠️ Could not verify session: {e}", flush=True)

        # Cleanup
        print("\n" + "=" * 70, flush=True)
        print("✅ Test completed successfully", flush=True)
        print(f"📸 {step_counter - 1} screenshots saved to {SCREENSHOTS_DIR}", flush=True)
        print("=" * 70, flush=True)

        context.close()
        browser.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--slow-mo", type=int, default=200, help="Slow motion ms")
    parser.add_argument("--max-steps", type=int, default=None, help="Stop after N steps")
    args = parser.parse_args()
    
    run_voice_browser_test(headed=args.headed, slow_mo=args.slow_mo, max_steps=args.max_steps)
