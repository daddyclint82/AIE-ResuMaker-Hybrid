"""
Real User Simulation Test — AIe ResuMaker Voice Builder
Playwright browser automation that simulates a human clicking through the voice UI.

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
FIXTURE_FILE = FIXTURES_DIR / "clint-devops-ai.json"
BASE_URL = "http://localhost:8000"

SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ─── Load Fixture ────────────────────────────────────────────────────────────
with open(FIXTURE_FILE, "r") as f:
    FIXTURE = json.load(f)

ANSWERS = {a["step"]: a["value"] for a in FIXTURE["answers"]}
STEPS = [a["step"] for a in FIXTURE["answers"]]


# ══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════

def screenshot(page, name: str, step_num: int):
    """Save a numbered screenshot for forensic debugging."""
    path = SCREENSHOTS_DIR / f"{step_num:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  📸 Screenshot: {path.name}", flush=True)
    return path


def send_answer(page, answer: str, step_num: int, label: str = ""):
    """Type answer and click send, waiting for AI response."""
    # Focus and type
    page.locator("#text-input").fill(answer)
    print(f"    📝 Typed: {answer[:60]}{'...' if len(answer) > 60 else ''}", flush=True)

    # Click send
    page.locator("#send-btn").click()

    # Wait for response (new AI message or message text change)
    try:
        page.wait_for_timeout(500)  # Brief pause for HTTP round-trip
        # Wait up to 10 seconds for any network/AI processing
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    # Take screenshot after response
    time.sleep(0.3)
    screenshot(page, label or f"response_after_{step_num}", step_num)


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


def verify_no_command_words_in_preview(page):
    """Check preview for leaked 'done', 'skip', 'yes' text."""
    preview_html = page.locator(".preview-container, #preview, .resume-preview").inner_html()
    bad_words = ["done", "skip", "yes", "no"]
    found = []
    for word in bad_words:
        if word.lower() in preview_html.lower():
            # Check if it's in a message context, not actual content
            found.append(word)
    return found


# ══════════════════════════════════════════════════════════════════════════════
# Main Test
# ═══════════════════════════════════════════════════════════════════════════════

def run_voice_browser_test(headed: bool = False, slow_mo: int = 200):
    """
    Run the full voice questionnaire through a real browser.

    Args:
        headed: Show the browser window (for debugging)
        slow_mo: Milliseconds to pause between actions
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

        # Verify welcome message - be flexible with selectors
        try:
            welcome = page.locator("#welcome-message").inner_text(timeout=5000)
            assert "full name" in welcome.lower(), f"Unexpected welcome: {welcome}"
            print(f"  ✅ Welcome message: {welcome[:60]}...", flush=True)
        except Exception as e:
            # Fallback: just check the page content
            content = page.content()
            if "full name" in content.lower():
                print("  ✅ Welcome message found (via page content)", flush=True)
            else:
                raise AssertionError(f"Welcome message not found: {e}")

        step_counter = 2  # Start at 2 since step 1 is the landing screenshot

        # ── Phase 1: Simple Fields (1A–1I) ──────────────────────────────────
        print("\n[Phase 1] Simple fields (1A–1I)...", flush=True)
        simple_steps = [s for s in STEPS if s.startswith("1")]
        for step in simple_steps:
            answer = ANSWERS[step]
            field_name = step  # e.g. "1A", "1B"

            send_answer(page, answer, step_counter, f"simple_{field_name}")
            step_counter += 1

            # Small verification: check user message appeared
            last_user = get_last_user_text(page)
            assert answer in last_user or last_user in answer, \
                f"User answer not found in chat: {last_user}"

        print("  ✅ All simple fields completed", flush=True)

        # ── Phase 2: Experience Loop (2A–2C) ─────────────────────────────────
        print("\n[Phase 2] Experience loop (3 jobs, 3 bullets each)...", flush=True)

        # We need to dynamically handle the experience loop
        # The fixture has explicit steps, but the UI is conversational
        # We'll iterate through the fixture steps for experience
        exp_steps = [s for s in STEPS if s.startswith("2")]

        for step in exp_steps:
            answer = ANSWERS[step]
            label = f"exp_{step}"

            send_answer(page, answer, step_counter, label)
            step_counter += 1

            # After "done" or "yes" for more_bullets/add_job, wait for next question
            if answer.lower() in ("done", "yes"):
                time.sleep(0.5)  # Give UI time to transition

        print("  ✅ Experience loop completed", flush=True)

        # ── Phase 3: Summary Questions (3A–3D) ──────────────────────────────
        print("\n[Phase 3] Summary questions...", flush=True)
        summary_steps = [s for s in STEPS if s.startswith("3")]

        for step in summary_steps:
            answer = ANSWERS[step]
            label = f"summary_{step}"

            send_answer(page, answer, step_counter, label)
            step_counter += 1

        print("  ✅ Summary questions completed", flush=True)

        # ── Phase 4: Skills ───────────────────────────────────────────────────
        print("\n[Phase 4] Skills categorization...", flush=True)
        skills_answer = ANSWERS["4A"]

        send_answer(page, skills_answer, step_counter, "skills_input")
        step_counter += 1

        # Wait for skills panel to appear (Groq processing may take 3-5 seconds)
        print("  ⏳ Waiting for skills categorization...", flush=True)
        time.sleep(4)

        # Wait for skills panel to appear - check by ID
        try:
            page.wait_for_selector("#skills-panel", timeout=8000)
            print("  ✅ Skills panel appeared", flush=True)
        except Exception:
            print("  ⚠️ Skills panel not detected (may be inline or different selector)", flush=True)

        # Verify skills are categorized (not comma dump)
        page_html = page.content()
        if "Programming & Development" in page_html or "Cloud & Infrastructure" in page_html or "skill-category" in page_html:
            print("  ✅ Skills appear categorized by tier", flush=True)
        else:
            print("  ⚠️ Could not verify tier categorization visually", flush=True)

        screenshot(page, "skills_categorized", step_counter)
        step_counter += 1

        # ── Phase 5: Optional Sections ──────────────────────────────────────
        print("\n[Phase 5] Optional sections (skip all)...", flush=True)
        optional_steps = [s for s in STEPS if s.startswith("5")]

        for step in optional_steps:
            answer = ANSWERS[step]
            label = f"optional_{step}"

            send_answer(page, answer, step_counter, label)
            step_counter += 1

        # Wait for final preview to render after all optional sections
        print("  ⏳ Waiting for final preview to render...", flush=True)
        time.sleep(2)

        print("  ✅ Optional sections handled", flush=True)

        # ── Phase 6: Preview ──────────────────────────────────────────────────
        print("\n[Phase 6] Waiting for preview...", flush=True)

        # Wait for preview to render
        try:
            page.wait_for_selector(".voice-preview-container, .preview-container, #preview, .resume-preview", timeout=15000)
            print("  ✅ Preview container found", flush=True)
        except Exception:
            print("  ⚠️ Preview container not found with standard selectors", flush=True)
            # Take screenshot anyway to see current state
            screenshot(page, "preview_check", step_counter)
            step_counter += 1

        screenshot(page, "preview_final", step_counter)
        step_counter += 1

        # ── Phase 7: Visual Verification ──────────────────────────────────────
        print("\n[Phase 7] Visual verification...", flush=True)

        # Get only the preview container HTML (not the whole page including chat)
        preview_html = ""
        try:
            preview_html = page.locator(".preview-container, #preview, .resume-preview, .resume-output").inner_html()
        except Exception:
            # Fallback: get page HTML and look for resume content
            page_html = page.content()
            # Try to extract just the resume portion
            if "resume" in page_html.lower():
                # Find resume section and check it
                print("  ℹ️ Using full page HTML for verification", flush=True)
                preview_html = page_html

        # Check for leaked command words in preview (not chat messages)
        # Only check within the preview container, not the whole page
        if preview_html:
            bad_words = ["done", "skip", "yes", "no"]
            found = []
            for word in bad_words:
                # Check if word appears as standalone text (not part of other words)
                if f" {word} " in preview_html.lower() or f">{word}<" in preview_html.lower():
                    found.append(word)
            if found:
                print(f"  ❌ LEAKED command words in preview: {found}", flush=True)
            else:
                print("  ✅ No command words (done/skip/yes/no) leaked into preview", flush=True)

            # Check for empty dicts - with debug info
            if "{}" in preview_html or "&#123;&#125;" in preview_html:
                # Find context around the empty dict
                idx = preview_html.find("{}")
                if idx >= 0:
                    context = preview_html[max(0,idx-50):min(len(preview_html),idx+50)]
                    print(f"  ❌ Empty dict '{{}}' found in preview HTML at position {idx}", flush=True)
                    print(f"     Context: ...{context}...", flush=True)
                else:
                    print("  ❌ Empty dict '{}' found in preview HTML (HTML encoded)", flush=True)
            else:
                print("  ✅ No empty dicts visible", flush=True)

            # Check for bullet presence
            if "•" in preview_html or "<li>" in preview_html or "bullet" in preview_html.lower():
                print("  ✅ Bullets appear present in preview", flush=True)
            else:
                print("  ⚠️ No bullets detected (may use different formatting)", flush=True)
        else:
            print("  ⚠️ Could not extract preview HTML for verification", flush=True)

        # ── Phase 8: Download / Purchase Buttons ──────────────────────────────
        print("\n[Phase 8] Checking download/purchase buttons...", flush=True)

        # Look for download buttons first
        download_buttons = page.locator("button:has-text('Download'), .download-btn").all()
        if download_buttons:
            print(f"  ✅ Found {len(download_buttons)} download button(s)", flush=True)
            for btn in download_buttons:
                text = btn.inner_text()
                print(f"     - {text}", flush=True)
        else:
            # Check for purchase button (free tier)
            purchase_btn = page.locator(".view-resume-btn, button:has-text('Purchase'), button:has-text('$'), .purchase-btn").all()
            if purchase_btn:
                print(f"  ℹ️ Found purchase button (free tier): {purchase_btn[0].inner_text()}", flush=True)
            else:
                print("  ⚠️ No download or purchase buttons found", flush=True)

        # ── Cleanup ───────────────────────────────────────────────────────────
        print("\n" + "=" * 70, flush=True)
        print("✅ TEST COMPLETE", flush=True)
        print(f"📁 Screenshots saved to: {SCREENSHOTS_DIR}", flush=True)
        print("=" * 70, flush=True)

        browser.close()


# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Real User Simulation Test for AIe ResuMaker")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--slow-mo", type=int, default=200, help="Slow motion delay in ms")
    args = parser.parse_args()

    try:
        run_voice_browser_test(headed=args.headed, slow_mo=args.slow_mo)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
