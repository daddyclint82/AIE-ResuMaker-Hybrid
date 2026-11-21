"""Edits: a purchase includes five saved changes, counted on Stripe.

Run: python tests/test_edits.py   (or pytest)

Drives the real routes through FastAPI's TestClient. Stripe is a small fake
that keeps checkout sessions in a dict, patched in per call: no server, no
Stripe keys, no network.
"""
import contextlib
import glob
import json
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

_sessions = {}   # what Stripe remembers: session id -> {"payment_status", "metadata"}
_stripe_up = [True]


def _retrieve(sid):
    if not _stripe_up[0]:
        raise stripe.APIConnectionError("network")
    if sid not in _sessions:
        raise stripe.InvalidRequestError("No such checkout.session", "id")
    return stripe.checkout.Session.construct_from({"id": sid, "object": "checkout.session", **_sessions[sid]}, "sk_test")


def _modify(sid, metadata):
    if not _stripe_up[0]:
        raise stripe.APIConnectionError("network")
    _sessions[sid]["metadata"].update(metadata)
    return _retrieve(sid)


def _create(**kwargs):
    sid = f"cs_test_edits_{len(_sessions)}"
    _sessions[sid] = {"payment_status": "paid", "metadata": dict(kwargs["metadata"])}
    return stripe.checkout.Session.construct_from({"id": sid, "url": f"https://checkout.test/{sid}"}, "sk_test")


@contextlib.contextmanager
def _stripe():
    with mock.patch.object(stripe.checkout.Session, "retrieve", _retrieve), \
         mock.patch.object(stripe.checkout.Session, "modify", _modify), \
         mock.patch.object(stripe.checkout.Session, "create", _create):
        yield


def _build(**fields):
    form = {"full_name": "Jordan Rivera", "email": "jordan@example.com", "city": "Springfield", "state": "IL",
            "summary": "Store manager.", "skills": "Coaching|Inventory",
            "experience": json.dumps([{"title": "Store Manager", "company": "Acme", "description": "Cut shrink"}]),
            **fields}
    r = client.post("/api/build", data=form)
    assert r.status_code == 200, r.text
    return r.json()["resume_id"]


def _buy(**fields):
    """Build and pay; returns (resume_id, Stripe session id)."""
    rid = _build(**fields)
    with _stripe():
        sid = client.post("/api/create-checkout-session", json={"resume_id": rid}).json()["sessionId"]
        assert client.get(f"/success?session_id={sid}").status_code == 200
    return rid, sid


def _save(paid_id, new_id):
    with _stripe():
        return client.post("/api/edit/save", json={"paid_resume_id": paid_id, "resume_id": new_id})


def _open(rid):
    with _stripe():
        return client.post("/api/edit/open", json={"resume_id": rid})


def _server_forgets():
    main.resumes.clear()
    for path in glob.glob(os.path.join(main.RESUME_STORAGE_DIR, "*")):
        os.remove(path)


def _pdf(rid):
    r = client.get(f"/api/download/{rid}?format=pdf")
    assert r.status_code == 200, r.status_code
    return r.content


def test_a_paid_resume_opens_in_the_editor_with_its_contents():
    rid, _ = _buy()
    r = _open(rid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["edits_left"] == 5 and body["max_edits"] == 5
    resume = body["resume"]
    assert resume["full_name"] == "Jordan Rivera" and resume["city"] == "Springfield" and resume["state"] == "IL"
    assert resume["skills"] == ["Coaching", "Inventory"] and resume["experience"][0]["company"] == "Acme"
    assert "paid" not in resume and "stripe_session" not in resume


def test_an_unpaid_or_unknown_resume_does_not_open():
    unpaid = _build()
    for rid in (unpaid, "", "nope", "A" * 22):
        r = _open(rid)
        assert r.status_code == 404 and r.json().get("reopen") is True, (rid, r.status_code)


def test_saving_changes_uses_one_edit_and_needs_no_second_payment():
    rid, sid = _buy()
    changed = _build(summary="Store manager who cut shrink 12%.")
    assert client.get(f"/api/download/{changed}?format=pdf").status_code == 402  # a preview, not paid for
    r = _save(rid, changed)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resume_id"] == changed and body["edits_left"] == 4, body
    assert "cut shrink 12%" in body["preview_html"]
    assert _sessions[sid]["metadata"]["edits_used"] == "1"
    assert client.get(body["download_url_docx"]).status_code == 200
    sealed = main.read_sealed_pdf(_pdf(changed))
    assert sealed["resume"]["summary"] == "Store manager who cut shrink 12%."
    assert sealed["stripe_session"] == sid and sealed["resume"]["purchase_id"] == rid


def test_five_edits_then_no_more():
    rid, sid = _buy()
    latest = rid
    for n in range(1, 6):
        new = _build(summary=f"Version {n}.")
        r = _save(latest, new)
        assert r.status_code == 200 and r.json()["edits_left"] == 5 - n, (n, r.text)
        latest = new
    sixth = _build(summary="Version 6.")
    r = _save(latest, sixth)
    assert r.status_code == 402 and r.json()["edits_left"] == 0, r.text
    assert _sessions[sid]["metadata"]["edits_used"] == "5"
    assert client.get(f"/api/download/{sixth}?format=pdf").status_code == 402
    assert _open(latest).json()["edits_left"] == 0


def test_saving_the_same_preview_twice_costs_one_edit():
    rid, sid = _buy()
    new = _build(summary="Once.")
    assert _save(rid, new).json()["edits_left"] == 4
    assert _save(rid, new).json()["edits_left"] == 4
    assert _sessions[sid]["metadata"]["edits_used"] == "1"


def test_the_count_survives_the_server_forgetting_and_an_old_pdf_gives_no_edits_back():
    rid, sid = _buy()
    original_pdf = _pdf(rid)
    edited = _build(summary="Edited.")
    assert _save(rid, edited).status_code == 200
    edited_pdf = _pdf(edited)
    key = main.resume_key(rid)  # one key per purchase, whichever version is uploaded
    for pdf, summary, restored_id in ((edited_pdf, "Edited.", edited), (original_pdf, "Store manager.", rid)):
        _server_forgets()
        with _stripe():
            r = client.post("/api/restore", files={"pdf": ("r.pdf", pdf, "application/pdf")}, data={"key": key})
        assert r.status_code == 200, r.text
        assert r.json()["resume_id"] == restored_id and r.json()["edits_left"] == 4, r.json()
        opened = _open(restored_id).json()
        assert opened["resume"]["summary"] == summary and opened["edits_left"] == 4
    # and an edit made from the restored old copy still counts against the same purchase
    again = _build(summary="Edited again.")
    assert _save(rid, again).json()["edits_left"] == 3
    assert _sessions[sid]["metadata"]["edits_used"] == "2"


def test_an_edit_keeps_what_the_form_does_not_carry():
    rid, _ = _buy()
    ai_groups = {"Leadership": [{"name": "Coaching", "weight": 91}], "Retail": [{"name": "Inventory", "weight": 64}]}
    main.resumes[rid]["skills_categorized"] = ai_groups
    main.resumes[rid]["address"] = "742 Evergreen Terrace, Springfield, IL 62701"
    same_skills = _build(summary="New summary.", skills="Inventory|Coaching")
    assert _save(rid, same_skills).status_code == 200
    kept = main.resumes[same_skills]
    assert kept["skills_categorized"] == ai_groups and kept["address"].startswith("742 Evergreen")
    moved = _build(skills="Coaching|Inventory|Scheduling", city="Chicago")
    assert _save(same_skills, moved).status_code == 200
    assert main.resumes[moved]["skills_categorized"] != ai_groups and main.resumes[moved]["address"] == ""


def test_edits_need_a_paid_resume_and_a_real_preview():
    rid, sid = _buy()
    unpaid, preview = _build(), _build()
    assert _save(unpaid, preview).status_code == 404
    assert _save("A" * 22, preview).status_code == 404
    assert _save(rid, "A" * 22).status_code == 404
    assert _sessions[sid]["metadata"]["edits_used"] == "0"
    assert client.get(f"/api/download/{preview}?format=pdf").status_code == 402


def test_one_purchase_cannot_spend_another_purchases_edits():
    a, sid_a = _buy()
    b, sid_b = _buy()
    assert _save(a, _build(summary="A's edit.")).json()["edits_left"] == 4
    assert _sessions[sid_a]["metadata"]["edits_used"] == "1" and _sessions[sid_b]["metadata"]["edits_used"] == "0"
    assert _open(b).json()["edits_left"] == 5


def test_stripe_being_down_spends_nothing_and_saves_nothing():
    rid, sid = _buy()
    new = _build(summary="While Stripe is down.")
    _stripe_up[0] = False
    try:
        assert _save(rid, new).status_code == 503 and _open(rid).status_code == 503
    finally:
        _stripe_up[0] = True
    assert _sessions[sid]["metadata"]["edits_used"] == "0"
    assert client.get(f"/api/download/{new}?format=pdf").status_code == 402
    assert _save(rid, new).json()["edits_left"] == 4


def test_a_purchase_from_before_the_count_has_all_its_edits():
    rid, sid = _buy()
    del _sessions[sid]["metadata"]["edits_used"]
    assert _open(rid).json()["edits_left"] == 5
    assert _save(rid, _build(summary="First."))  .json()["edits_left"] == 4
    assert _sessions[sid]["metadata"]["edits_used"] == "1"


def test_a_resume_stored_before_city_and_state_were_kept_still_fills_them():
    assert main.resume_for_editor({"location": "Springfield, IL"})["city"] == "Springfield"
    assert main.resume_for_editor({"location": "Springfield, IL"})["state"] == "IL"
    assert main.resume_for_editor({"location": "Springfield"}) == {"city": "Springfield", "state": ""}
    assert main.resume_for_editor({}) == {"city": "", "state": ""}


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", str(e)[:200])
    sys.exit(1 if failed else 0)
