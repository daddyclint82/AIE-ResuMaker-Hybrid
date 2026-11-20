"""Resume access: random IDs, paid-only downloads, how a payment is recorded.

Run: python tests/test_resume_access.py   (or pytest)

Drives the real routes through FastAPI's TestClient with Stripe's create and
retrieve calls stubbed: no server, no Stripe keys, no network.
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stripe  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

main.RESUME_STORAGE_DIR = tempfile.mkdtemp()  # keep test resumes out of the repo
main.STRIPE_WEBHOOK_SECRET = "whsec_test_resume_access"
client = TestClient(main.app)

_checkouts = {}  # checkout session id -> the metadata Stripe stored with it


def _create(**kwargs):
    sid = f"cs_test_{len(_checkouts)}"
    _checkouts[sid] = kwargs["metadata"]
    return stripe.checkout.Session.construct_from({"id": sid, "url": f"https://checkout.test/{sid}"}, "sk_test")


def _retrieve(sid):
    # A real Stripe object, so the route runs against stripe's own types.
    return stripe.checkout.Session.construct_from(
        {"id": sid, "object": "checkout.session", "payment_status": "paid", "metadata": _checkouts[sid]},
        "sk_test")


stripe.checkout.Session.create = _create
stripe.checkout.Session.retrieve = _retrieve


def _build():
    r = client.post("/api/build", data={"full_name": "Jordan Rivera", "email": "jordan@example.com"})
    assert r.status_code == 200, r.text
    return r.json()["resume_id"]


def _checkout(resume_id):
    r = client.post("/api/create-checkout-session", json={"resume_id": resume_id})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def _signed(payload):
    ts = int(time.time())
    sig = hmac.new(main.STRIPE_WEBHOOK_SECRET.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={ts},v1={sig}"}


def test_ids_are_random():
    a, b = _build(), _build()
    assert a != b and main._RESUME_ID_RE.fullmatch(a), (a, b)


def test_preview_and_payment_status_work_with_the_id():
    rid = _build()
    r = client.post("/api/preview-timer", json={"resume_id": rid})
    assert r.status_code == 200 and "Jordan Rivera" in r.json()["clean_html"], r.text[:200]
    assert client.get(f"/api/check-payment/{rid}").json() == {"paid": False}


def test_download_requires_payment():
    rid = _build()
    for fmt in ("docx", "pdf"):
        assert client.get(f"/api/download/{rid}?format={fmt}").status_code == 402, fmt


def test_payment_unlocks_download():
    rid = _build()
    r = client.get(f"/success?session_id={_checkout(rid)}")
    assert r.status_code == 200 and f"/api/download/{rid}" in r.text, r.text[:200]
    assert client.get(f"/api/check-payment/{rid}").json() == {"paid": True}
    for fmt in ("docx", "pdf"):
        r = client.get(f"/api/download/{rid}?format={fmt}")
        assert r.status_code == 200, (fmt, r.status_code)
        assert f'filename="resume_jordan_rivera.{fmt}"' in r.headers["content-disposition"], r.headers


def test_payment_unlocks_only_its_own_resume():
    paid, other = _build(), _build()
    client.get(f"/success?session_id={_checkout(paid)}&resume_id={other}")
    assert client.get(f"/api/download/{other}").status_code == 402


def test_webhook_needs_a_valid_signature():
    rid = _build()
    payload = json.dumps({"object": "event", "type": "checkout.session.completed",
                          "data": {"object": {"object": "checkout.session", "metadata": {"resume_id": rid}}}})
    assert client.post("/api/webhook", content=payload).status_code == 400
    assert client.get(f"/api/download/{rid}").status_code == 402
    assert client.post("/api/webhook", content=payload, headers=_signed(payload)).status_code == 200
    assert client.get(f"/api/download/{rid}").status_code == 200

    secret, main.STRIPE_WEBHOOK_SECRET = main.STRIPE_WEBHOOK_SECRET, ""
    try:
        assert client.post("/api/webhook", content=payload).status_code == 503
    finally:
        main.STRIPE_WEBHOOK_SECRET = secret


def test_ids_we_never_issued_get_nothing():
    before = len(_checkouts)
    for rid in ("jordan_rivera_20261120_101010", "A" * 22, 123):
        assert client.post("/api/preview-timer", json={"resume_id": rid}).status_code == 404, rid
        assert client.post("/api/create-checkout-session", json={"resume_id": rid}).status_code == 404, rid
    assert len(_checkouts) == before  # no Stripe session for an unknown resume


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
