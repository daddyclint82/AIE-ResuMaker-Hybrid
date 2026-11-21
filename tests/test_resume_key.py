"""The resume key, and the edit count that starts on Stripe's record.

Run: python tests/test_resume_key.py   (or pytest)

Drives the real routes through FastAPI's TestClient with Stripe's calls
stubbed per call: no server, no Stripe keys, no network.
"""
import os
import re
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stripe  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

main.RESUME_STORAGE_DIR = tempfile.mkdtemp()  # keep test resumes out of the repo
client = TestClient(main.app)
KEY_RE = re.compile(r"[A-Z2-7]{5}-[A-Z2-7]{5}")


def _build():
    r = client.post("/api/build", data={"full_name": "Jordan Rivera", "email": "jordan@example.com"})
    assert r.status_code == 200, r.text
    return r.json()["resume_id"]


def _checkout(resume_id):
    """POST a checkout; returns what the route sent to Stripe."""
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return stripe.checkout.Session.construct_from(
            {"id": "cs_test_key", "url": "https://checkout.test/cs_test_key"}, "sk_test")

    with mock.patch.object(stripe.checkout.Session, "create", create):
        r = client.post("/api/create-checkout-session", json={"resume_id": resume_id})
    assert r.status_code == 200, r.text
    return sent


def _success_page(resume_id):
    def retrieve(sid):
        return stripe.checkout.Session.construct_from(
            {"id": sid, "object": "checkout.session", "payment_status": "paid",
             "metadata": {"resume_id": resume_id}}, "sk_test")

    with mock.patch.object(stripe.checkout.Session, "retrieve", retrieve):
        r = client.get("/success?session_id=cs_test_key")
    assert r.status_code == 200, r.status_code
    return r.text


def test_a_key_is_short_stable_and_its_own():
    a, b = _build(), _build()
    assert KEY_RE.fullmatch(main.resume_key(a)), main.resume_key(a)
    assert main.resume_key(a) == main.resume_key(a)
    assert main.resume_key(a) != main.resume_key(b)


def test_a_key_cannot_be_worked_out_without_the_secret():
    rid = _build()
    ours = main.resume_key(rid)
    with mock.patch.object(main, "_REFERRAL_KEY", b"some other server's secret"):
        assert main.resume_key(rid) != ours


def test_the_receipt_carries_the_key():
    rid = _build()
    description = _checkout(rid)["payment_intent_data"]["description"]
    assert main.resume_key(rid) in description, description


def test_the_purchase_starts_with_no_edits_used():
    rid = _build()
    metadata = _checkout(rid)["metadata"]
    assert metadata["edits_used"] == "0" and metadata["resume_id"] == rid, metadata
    assert all(isinstance(v, str) for v in metadata.values()), metadata  # Stripe metadata is strings


def test_the_success_page_shows_the_same_key_as_the_receipt():
    rid = _build()
    description = _checkout(rid)["payment_intent_data"]["description"]
    shown = re.search(r'id="resume-key">([^<]+)<', _success_page(rid)).group(1)
    assert shown == main.resume_key(rid) and shown in description, (shown, description)


def test_the_key_is_not_in_the_pdf():
    # PDF plus key: a recruiter holding only the file must not have both.
    rid = _build()
    page = _success_page(rid)  # marks it paid
    assert main.resume_key(rid) in page
    pdf = client.get(f"/api/download/{rid}?format=pdf").content
    assert pdf.startswith(b"%PDF-") and main.resume_key(rid).encode() not in pdf
    sealed = main.read_sealed_pdf(pdf)
    assert main.resume_key(rid) not in str(sealed), sealed


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
