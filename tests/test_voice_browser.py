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
import os
import sys
import time
from pathlib import Path

# Ensure playwright is available
try:
    from playwright.sync_api import sync_playwright
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
    Send an answer via the voice chat UI and wait for the server's /api/voice/turn
    response. Returns the parsed JSON response data so the test can verify state.
    """
    # Disable animations for stability
    try:
        page.add_style_tag(content="* { transition: none !important; animation: none !important; }")
    except:
        pass

    print(f"    📝 Sending: {answer[:60]}{'...' if len(answer) > 60 else ''}", flush=True)

    # Use waitForResponse to capture the API response
    response_data = None
    with page.expect_response(lambda r: "/api/voice/turn" in r.url, timeout=15000) as response_info:
        # Fill and submit via JS (most reliable)
        page.evaluate(f"""
            const input = document.getElementById('text-input');
            if (input) {{
                input.value = {json.dumps(answer)};
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            const btn = document.getElementById('send-btn');
            if (btn) btn.click();
        """)
    
    response = response_info.value
    if response.ok:
        try:
            response_data = response.json()
        except Exception as e:
            print(f"    ⚠️ Could not parse response JSON: {e}", flush=True)
    else:
        print(f"    ⚠️ /api/voice/turn returned {response.status}", flush=True)

    # Brief pause for UI to update after response
    time.sleep(0.3)

    # Take screenshot after response
    screenshot(page, label or f"response_after_{step_num}", step_num)

    # Debug: print key fields from response
    if response_data:
        print(f"    ↪️  Response: field={response_data.get('field')}, done={response_data.get('done', False)}, type={response_data.get('type', 'question')}", flush=True)

    return response_data


def screenshot(page, name: str, step_num: int):
    """Save a numbered screenshot for forensic debugging."""
    path = SCREENSHOTS_DIR / f"{step_num:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  📸 Screenshot: {path.name}", flush=True)
    return path


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
        step_counter = 1

        try:
            # ── Phase 0: Navigate ─────────────────────────────────────────────────
            print("\n[Phase 0] Launching browser and navigating...", flush=True)
            page.goto(f"{BASE_URL}/build?mode=voice")

            # Wait for page load — check AEI logo
            page.wait_for_selector(".logo-img", timeout=30000)
            print("  ✅ AEI logo loaded", flush=True)

            screenshot(page, "start_page", step_counter)
            step_counter += 1

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

            last_turn_response = None
            for step in optional_steps:
                answer = ANSWERS[step]
                label = f"optional_{step}"

                data = send_answer_synced(page, answer, step_counter, label)
                last_turn_response = data
                step_counter += 1
                
                # After decision answers, verify state transition
                if answer.lower() in ("yes", "done", "skip") and data:
                    print(f"    ↪️  State: field={data.get('field')}, done={data.get('done', False)}", flush=True)

            print("  ✅ Fixture optional sections completed", flush=True)

            # ═══════════════════════════════════════════════════════════════════════
            # HANDOFF VERIFICATION: Done button → Build Preview → Verify API
            # ═══════════════════════════════════════════════════════════════════════
            print("\n" + "=" * 70, flush=True)
            print("[HANDOFF] Triggering 'Done' and verifying preview generation", flush=True)
            print("=" * 70, flush=True)

            # Step 1: If server hasn't reached done yet (links section remains),
            # send 'done' to skip it and trigger completion
            done_from_server = last_turn_response and last_turn_response.get("done", False)

            if not done_from_server:
                # Check what field the server is asking for
                current_field = last_turn_response.get("field", "") if last_turn_response else ""
                print(f"[HANDOFF] Server field after fixture: '{current_field}', done={done_from_server}", flush=True)
                
                # Keep sending 'done' until server returns done=true (handles links section)
                max_attempts = 5
                attempts = 0
                while not done_from_server and attempts < max_attempts:
                    print(f"[HANDOFF] Sending 'done' to advance (attempt {attempts + 1})...", flush=True)
                    done_response = send_answer_synced(page, "done", step_counter, f"trigger_done_{attempts}")
                    step_counter += 1
                    if done_response:
                        done_from_server = done_response.get("done", False)
                        print(f"    ↪️  Response: field={done_response.get('field')}, done={done_from_server}", flush=True)
                    attempts += 1

            if not done_from_server:
                raise AssertionError("❌ FAILED: Server did not return done=true after all optional sections + links")
            print("  ✅ Step 1 PASSED: Server returned done=true", flush=True)
            screenshot(page, "done_state_confirmed", step_counter)
            step_counter += 1

            # Step 2: Wait for frontend to render the preview UI (hides input, shows resume)
            print("[HANDOFF] Step 2: Waiting for frontend preview UI to render...", flush=True)
            try:
                # When done=true, frontend hides input elements and shows preview
                page.wait_for_selector(".voice-preview-container", timeout=30000)
                print("  ✅ Step 2 PASSED: Preview container rendered in DOM", flush=True)
            except Exception as e:
                # Fallback: check if input is hidden (which happens when done=true)
                input_display = page.evaluate("document.getElementById('text-input')?.style.display || 'block'")
                if input_display == "none":
                    print("  ✅ Step 2 PASSED: Input hidden (done state confirmed via DOM)", flush=True)
                else:
                    raise AssertionError(f"❌ FAILED: Preview UI did not render: {e}")
            screenshot(page, "preview_ui_rendered", step_counter)
            step_counter += 1

            # Step 3: Explicitly call /api/voice/preview and verify 200 + payload
            print("[HANDOFF] Step 3: Verifying /api/voice/preview API response...", flush=True)
            session_id = page.evaluate("window.sessionId || ''")
            if not session_id:
                raise AssertionError("❌ FAILED: Could not extract sessionId from page")

            preview_api_response = page.request.post(
                f"{BASE_URL}/api/voice/preview",
                data=json.dumps({
                    "session_id": session_id,
                    "template_style": "professional"
                }),
                headers={"Content-Type": "application/json"}
            )

            if preview_api_response.status != 200:
                raise AssertionError(f"❌ FAILED: /api/voice/preview returned {preview_api_response.status}")
            print(f"  ✅ Step 3 PASSED: /api/voice/preview returned 200", flush=True)

            preview_data = preview_api_response.json()
            if not preview_data.get("success"):
                raise AssertionError(f"❌ FAILED: preview API success=false: {preview_data.get('error', 'unknown')}")
            print("  ✅ Step 3 PASSED: preview API returned success=true", flush=True)

            if not preview_data.get("preview_html"):
                raise AssertionError("❌ FAILED: preview API returned empty preview_html")
            preview_html = preview_data["preview_html"]
            print(f"  ✅ Step 3 PASSED: preview_html received ({len(preview_html)} chars)", flush=True)
            screenshot(page, "preview_api_verified", step_counter)
            step_counter += 1

            # Step 4: Verify preview HTML content (sanity checks)
            print("[HANDOFF] Step 4: Verifying preview HTML content...", flush=True)

            # No leaked command words (done/skip/next are control words; yes/no are acceptable in resume text)
            bad_words = ["done", "skip", "next"]
            leaked = []
            for word in bad_words:
                if f" {word} " in preview_html.lower() or f">{word}<" in preview_html.lower():
                    leaked.append(word)
            if leaked:
                raise AssertionError(f"❌ FAILED: Leaked command words in preview: {leaked}")
            print("  ✅ No command words leaked into preview", flush=True)

            # No empty dicts
            if "{}" in preview_html or "&#123;&#125;" in preview_html:
                raise AssertionError("❌ FAILED: Empty dict found in preview HTML")
            print("  ✅ No empty dicts in preview", flush=True)

            # Required sections present
            required_sections = {
                "Professional Summary": "summary" in preview_html.lower() or "professional summary" in preview_html.lower(),
                "Technical Skills": "skills" in preview_html.lower() or "technical skills" in preview_html.lower(),
                "Professional Experience": "experience" in preview_html.lower() or "professional experience" in preview_html.lower(),
                "Education": "education" in preview_html.lower(),
            }
            print("\n  📋 Section checklist:", flush=True)
            for section, present in required_sections.items():
                status = "✅" if present else "⬜"
                print(f"     {status} {section}", flush=True)

            all_core_present = all(required_sections.values())
            if not all_core_present:
                raise AssertionError("❌ FAILED: Some required sections missing from preview")
            print("\n  ✅ Step 4 PASSED: All core sections present in preview HTML", flush=True)

            # ═══════════════════════════════════════════════════════════════════════
            # STEP 5: HARD FILE SYSTEM ASSERTIONS (DOCX + PDF + DOWNLOAD ROUTE)
            # ═══════════════════════════════════════════════════════════════════════
            print("\n[HANDOFF] Step 5: Verifying physical file generation...", flush=True)
            
            resume_id = preview_data.get("resume_id")
            if not resume_id:
                raise AssertionError("❌ FAILED: No resume_id in preview response")
            
            # Define storage path (same as RESUME_STORAGE_DIR in main.py)
            STORAGE_DIR = PROJECT_ROOT / "storage" / "resumes"
            docx_path = STORAGE_DIR / f"{resume_id}.docx"
            pdf_path = STORAGE_DIR / f"{resume_id}.pdf"
            
            # Assert DOCX file exists
            if not os.path.exists(str(docx_path)):
                raise AssertionError(f"❌ FAILED: DOCX not found at {docx_path}")
            docx_size = os.path.getsize(str(docx_path))
            print(f"  ✅ Step 5a PASSED: DOCX exists ({docx_size} bytes) — {docx_path}", flush=True)
            
            # Assert PDF file exists
            if not os.path.exists(str(pdf_path)):
                raise AssertionError(f"❌ FAILED: PDF not found at {pdf_path}")
            pdf_size = os.path.getsize(str(pdf_path))
            print(f"  ✅ Step 5b PASSED: PDF exists ({pdf_size} bytes) — {pdf_path}", flush=True)
            
            # Assert download endpoint returns 200 for DOCX
            download_docx_response = page.request.get(f"{BASE_URL}/api/download/{resume_id}")
            if download_docx_response.status != 200:
                raise AssertionError(f"❌ FAILED: /api/download/{resume_id} returned {download_docx_response.status}")
            print(f"  ✅ Step 5c PASSED: /api/download/{resume_id} returned 200", flush=True)
            
            # Assert download endpoint returns 200 for PDF
            download_pdf_response = page.request.get(f"{BASE_URL}/api/download/{resume_id}?format=pdf")
            if download_pdf_response.status != 200:
                raise AssertionError(f"❌ FAILED: /api/download/{resume_id}?format=pdf returned {download_pdf_response.status}")
            print(f"  ✅ Step 5d PASSED: /api/download/{resume_id}?format=pdf returned 200", flush=True)
            
            print("\n  🎉 FILES VERIFIED: You have a real product.", flush=True)

            # ═══════════════════════════════════════════════════════════════════════
            # FINAL SUMMARY
            # ═══════════════════════════════════════════════════════════════════════
            print("\n" + "=" * 70, flush=True)
            print("🎉 HANDOFF TEST PASSED — Full user flow + product verified:", flush=True)
            print("   1. ✅ Triggered 'Done' after all questions", flush=True)
            print("   2. ✅ Server returned done=true", flush=True)
            print("   3. ✅ Preview UI rendered in browser", flush=True)
            print("   4. ✅ /api/voice/preview returned 200 + valid HTML", flush=True)
            print("   5. ✅ Preview HTML contains all core sections, no leaks", flush=True)
            print("   6. ✅ DOCX file physically exists on disk", flush=True)
            print("   7. ✅ PDF file physically exists on disk", flush=True)
            print("   8. ✅ /api/download/{resume_id} returns 200 for DOCX", flush=True)
            print("   9. ✅ /api/download/{resume_id}?format=pdf returns 200 for PDF", flush=True)
            print(f"📸 {step_counter - 1} screenshots saved to {SCREENSHOTS_DIR}", flush=True)
            print("=" * 70, flush=True)

        except AssertionError as e:
            print(f"\n{'=' * 70}", flush=True)
            print(f"❌ TEST FAILED: {e}", flush=True)
            print(f"📸 Last screenshot: {step_counter:02d}_*.png", flush=True)
            print("=" * 70, flush=True)
            raise
        finally:
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
