"""The come-back page: a forgotten resume returns from its PDF and key.

Run: python tests/test_restore.py   (or pytest)

Drives the real routes through FastAPI's TestClient with Stripe's retrieve
stubbed per call: no server, no Stripe keys, no network.
"""
import glob
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stripe  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

main.RESUME_STORAGE_DIR = tempfile.mkdtemp()  # keep test resumes out of the repo
client = TestClient(main.app)
SESSION = "cs_test_restore"


def _stripe_says(resume_id, payment_status="paid", calls=None):
    def retrieve(sid):
        if calls is not None:
            calls.append(sid)
        return stripe.checkout.Session.construct_from(
            {"id": sid, "object": "checkout.session", "payment_status": payment_status,
             "metadata": {"resume_id": resume_id, "edits_used": "0"}}, "sk_test")
    return mock.patch.object(stripe.checkout.Session, "retrieve", retrieve)


def _bought():
    """Build and pay for a resume; returns (resume_id, the PDF the customer keeps)."""
    r = client.post("/api/build", data={"full_name": "Jordan Rivera", "email": "jordan@example.com",
                                        "summary": "Store manager at AT&T retail."})
    rid = r.json()["resume_id"]
    with _stripe_says(rid):
        assert client.get(f"/success?session_id={SESSION}").status_code == 200
    r = client.get(f"/api/download/{rid}?format=pdf")
    assert r.status_code == 200, r.status_code
    return rid, r.content


def _server_forgets():
    """What every deploy, restart and idle spin-down does on Render's free tier."""
    main.resumes.clear()
    for path in glob.glob(os.path.join(main.RESUME_STORAGE_DIR, "*")):
        os.remove(path)


def _restore(pdf, key, name="resume.pdf"):
    return client.post("/api/restore", files={"pdf": (name, pdf, "application/pdf")}, data={"key": key})


def _is_gone(rid):
    return client.get(f"/api/download/{rid}?format=pdf").status_code == 404


def test_a_forgotten_resume_comes_back_from_its_pdf_and_key():
    rid, pdf = _bought()
    _server_forgets()
    assert _is_gone(rid)
    with _stripe_says(rid):
        r = _restore(pdf, main.resume_key(rid))
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True, "name": "Jordan Rivera",
                        "download_url_pdf": f"/api/download/{rid}?format=pdf",
                        "download_url_docx": f"/api/download/{rid}?format=docx"}
    again = client.get(f"/api/download/{rid}?format=pdf")
    assert again.status_code == 200 and again.content.startswith(b"%PDF-")
    assert client.get(f"/api/download/{rid}?format=docx").status_code == 200
    # The PDF it hands back is itself a saved copy of the same resume.
    assert main.read_sealed_pdf(again.content) == main.read_sealed_pdf(pdf)


def test_the_key_is_forgiving_about_how_it_is_typed():
    rid, pdf = _bought()
    key = main.resume_key(rid)
    typed = [key.lower(), key.replace("-", ""), f"  {key[:5]} {key[6:]}  ", key.replace("O", "0").replace("I", "1")]
    for attempt in typed:
        _server_forgets()
        with _stripe_says(rid):
            assert _restore(pdf, attempt).status_code == 200, attempt


def test_a_wrong_key_gets_nothing_and_stripe_is_not_asked():
    rid, pdf = _bought()
    other, _ = _bought()
    _server_forgets()
    for wrong in ("", "AAAAA-AAAAA", main.resume_key(other), main.resume_key(rid)[:-1]):
        calls = []
        with _stripe_says(rid, calls=calls):
            r = _restore(pdf, wrong)
        assert r.status_code == 403 and "error" in r.json(), (wrong, r.status_code)
        assert calls == [] and _is_gone(rid), wrong


def test_the_pdf_alone_is_not_enough():
    # What a recruiter holds: the file, not the key.
    rid, pdf = _bought()
    _server_forgets()
    with _stripe_says(rid):
        assert client.post("/api/restore", files={"pdf": ("r.pdf", pdf, "application/pdf")}).status_code == 403
    assert _is_gone(rid)


def test_stripe_decides_what_was_paid():
    rid, pdf = _bought()
    other, _ = _bought()
    key = main.resume_key(rid)
    _server_forgets()
    with _stripe_says(rid, payment_status="unpaid"):
        assert _restore(pdf, key).status_code == 402
    with _stripe_says(other):  # a real payment, for a different resume
        assert _restore(pdf, key).status_code == 402

    def no_such_session(sid):
        raise stripe.InvalidRequestError("No such checkout.session", "id")
    with mock.patch.object(stripe.checkout.Session, "retrieve", no_such_session):
        assert _restore(pdf, key).status_code == 402
    assert _is_gone(rid)


def test_stripe_being_down_is_not_a_refusal():
    rid, pdf = _bought()
    _server_forgets()

    def down(sid):
        raise stripe.APIConnectionError("network")
    with mock.patch.object(stripe.checkout.Session, "retrieve", down):
        r = _restore(pdf, main.resume_key(rid))
    assert r.status_code == 503 and "try again" in r.json()["error"], r.text
    with _stripe_says(rid):  # and the same upload works once Stripe is back
        assert _restore(pdf, main.resume_key(rid)).status_code == 200


def test_files_without_our_saved_copy_get_nothing():
    rid, pdf = _bought()
    with mock.patch.object(main, "_seal_pdf", lambda *a: None):
        plain = open(main.generate_pdf("plain", {"full_name": "Jordan Rivera"}), "rb").read()
    try:
        main._seal_cipher.cache_clear()
        with mock.patch.object(main, "_REFERRAL_KEY", b"some other server's secret"):
            foreign = open(main.generate_pdf("foreign", {"full_name": "J", "stripe_session": SESSION}), "rb").read()
    finally:
        main._seal_cipher.cache_clear()
    _server_forgets()
    for upload in (plain, foreign, b"not a pdf at all", pdf[:3000], b""):
        calls = []
        with _stripe_says(rid, calls=calls):
            r = _restore(upload, main.resume_key(rid))
        assert r.status_code == 422 and calls == [], (upload[:12], r.status_code)


def test_an_oversized_upload_is_turned_away():
    rid, pdf = _bought()
    _server_forgets()
    calls = []
    with _stripe_says(rid, calls=calls):
        r = _restore(pdf + b"\0" * main.RESTORE_MAX_BYTES, main.resume_key(rid))
    assert r.status_code == 413 and calls == [] and _is_gone(rid), r.status_code


def test_the_come_back_page_is_there_and_linked():
    page = client.get("/restore")
    assert page.status_code == 200
    for needed in ('id="restore-pdf"', 'id="restore-key"', "/api/restore"):
        assert needed in page.text, needed
    assert 'href="/restore"' in client.get("/").text
    rid, _ = _bought()
    with _stripe_says(rid):
        assert 'href="/restore"' in client.get(f"/success?session_id={SESSION}").text


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", str(e)[:160])
    sys.exit(1 if failed else 0)
