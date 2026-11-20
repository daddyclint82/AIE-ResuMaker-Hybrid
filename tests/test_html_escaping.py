"""User text in server-built HTML comes out escaped.

Run: python tests/test_html_escaping.py   (or pytest)

Covers the student verification page, the voice data /build embeds in the
form page, and the resume preview. No server, no network.
"""
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)
MARKUP = '<em class="x">Ann</em> & \'Co\''
VOICE_DATA = re.compile(r'<script id="voice-data" type="application/json">(.*?)</script>', re.S)


def test_verified_email_is_escaped():
    token = "test-escape-email"
    email = MARKUP + "@school.edu"
    main.student_verifications[token] = {
        "email": email, "verified": False, "expires": datetime.now() + timedelta(hours=1)}
    page = client.get("/verify-student", params={"token": token}).text
    assert html.escape(email) in page, page
    assert "<em" not in page, page
    assert main.student_verifications[token]["verified"] is True


def test_error_page_does_not_echo_the_error():
    token = "test-escape-error"
    # An expiry that can't be compared with now() makes the route raise.
    main.student_verifications[token] = {"email": "a@school.edu", "verified": False, "expires": "not-a-date"}
    page = client.get("/verify-student", params={"token": token}).text
    assert "We couldn't verify this link" in page, page
    assert "not supported" not in page, page


def test_build_embeds_voice_data_as_inert_json():
    sid = "test-escape-voice"
    data = {"full_name": "</script>" + MARKUP}
    main.voice_session_store[sid] = {"data": data}
    page = client.get("/build", params={"mode": "form", "voice_session": sid}).text
    assert "</script><em" not in page
    embedded = VOICE_DATA.search(page).group(1)
    assert "<" not in embedded and ">" not in embedded, embedded
    assert json.loads(embedded)["full_name"] == data["full_name"]

    page = client.get("/build", params={"mode": "form"}).text
    assert VOICE_DATA.search(page).group(1) == "null"


def test_preview_escapes_every_field():
    data = {
        "full_name": MARKUP,
        "email": MARKUP,
        "summary": MARKUP,
        "skills_categorized": {MARKUP: [MARKUP]},
        "experience": [{"title": MARKUP, "company": MARKUP, "bullets": [MARKUP]}],
        "education": [{"school": MARKUP, "degree": MARKUP}],
        "projects": [{"name": MARKUP, "tech": MARKUP}],
        "competencies": [{"label": MARKUP, "description": MARKUP}],
        "certifications": [{"name": MARKUP}],
        "community": [{"org": MARKUP, "description": MARKUP}],
    }
    before = json.dumps(data)
    page = main.generate_preview_html(data, template_style='"><em>')
    assert "<em" not in page, page
    assert html.escape(MARKUP) in page
    assert 'class="resume-preview professional"' in page
    assert json.dumps(data) == before  # the stored resume is not modified


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except Exception as e:
                failed += 1
                print("FAIL", name, "-", f"{type(e).__name__}: {e}"[:200])
    sys.exit(1 if failed else 0)
