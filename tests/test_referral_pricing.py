"""Referral pricing: which Stripe price each checkout tier gets.

Run: python tests/test_referral_pricing.py   (or pytest)

Drives the real routes through FastAPI's TestClient with Stripe's session
create call stubbed: no server, no Stripe keys, no network.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stripe  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

main.RESUME_STORAGE_DIR = tempfile.mkdtemp()  # keep test resumes out of the repo
main.STRIPE_PRICE_ID = "price_regular"
main.STRIPE_STUDENT_PRICE_ID = "price_reduced"
client = TestClient(main.app)

_r = client.post("/api/build", data={"full_name": "Jordan Rivera", "email": "jordan@example.com"})
assert _r.status_code == 200, _r.text
RESUME_ID = _r.json()["resume_id"]


def _checkout(**body):
    """POST a checkout. Returns (status, JSON body, price charged or None if no session was made).

    Stripe's create is stubbed only for this call, so other test modules' stubs survive."""
    prices = []

    def create(**kwargs):
        prices.append(kwargs["line_items"][0]["price"])
        return stripe.checkout.Session.construct_from(
            {"id": "cs_test_pricing", "url": "https://checkout.test/cs_test_pricing"}, "sk_test")

    with mock.patch.object(stripe.checkout.Session, "create", create):
        r = client.post("/api/create-checkout-session", json={"resume_id": RESUME_ID, **body})
    return r.status_code, r.json(), (prices[0] if prices else None)


def _new_code():
    r = client.post("/api/referral/create", json={"email": "jordan@example.com"})
    assert r.status_code == 200, r.text
    return r.json()["code"]


def _assert_charged(result, price):
    status, body, charged = result
    assert status == 200 and charged == price, result
    assert set(body) == {"sessionId", "url"}, body  # the shape app.js redirects with


def _assert_refused(result):
    status, body, charged = result
    assert status == 403 and charged is None, result
    assert set(body) == {"error"}, body  # app.js shows body.error


def test_regular_and_unknown_tiers_pay_full_price():
    _assert_charged(_checkout(), "price_regular")
    _assert_charged(_checkout(tier="regular"), "price_regular")
    _assert_charged(_checkout(tier="vip"), "price_regular")


def test_student_price_needs_a_verified_student():
    _assert_refused(_checkout(tier="student"))
    main.student_verifications["tok-verified"] = {
        "email": "student@example.edu", "verified": True, "expires": datetime.now() + timedelta(hours=1)}
    _assert_charged(_checkout(tier="student", student_token="tok-verified"), "price_reduced")


def test_referral_price_needs_a_code_we_issued():
    for code in (None, "", "ABCD_EFG-1", "A" * 16, 42, ["x"]):
        _assert_refused(_checkout(tier="discount", referral_code=code))


def test_referral_price_unlocks_after_a_visit():
    code = _new_code()
    assert main._REFERRAL_CODE_RE.fullmatch(code), code
    _assert_refused(_checkout(tier="discount", referral_code=code))

    assert client.get(f"/build?ref={code}").status_code == 200  # a friend opens the link
    assert client.get(f"/api/referral/stats/{code}").json()["visits"] == 1
    _assert_charged(_checkout(tier="discount", referral_code=code), "price_reduced")


def test_codes_outlive_a_restart():
    code = _new_code()
    main.referral_codes.clear()  # what a restart does to the in-memory stats
    r = client.get(f"/api/referral/stats/{code}")
    assert r.status_code == 200 and r.json()["visits"] == 0, r.text
    _assert_refused(_checkout(tier="discount", referral_code=code))

    assert client.post("/api/referral/track", json={"code": code}).status_code == 200
    _assert_charged(_checkout(tier="discount", referral_code=code), "price_reduced")


def test_codes_signed_with_another_key_are_refused():
    key, main._REFERRAL_KEY = main._REFERRAL_KEY, b"another key"
    try:
        code = _new_code()
    finally:
        main._REFERRAL_KEY = key
    assert client.post("/api/referral/track", json={"code": code}).status_code == 400
    assert client.get(f"/api/referral/stats/{code}").status_code == 404
    _assert_refused(_checkout(tier="discount", referral_code=code))


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
