"""The saved copy sealed inside every PDF.

Run: python tests/test_pdf_seal.py   (or pytest)

generate_pdf attaches the resume's own data to the PDF, encrypted, so a
customer who kept the file can bring the resume back after the server has
forgotten it. No server, no Stripe keys, no network.
"""
import io
import os
import sys
import tempfile
import zlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stripe  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfReader  # noqa: E402

import main  # noqa: E402

main.RESUME_STORAGE_DIR = tempfile.mkdtemp()  # keep test PDFs out of the repo
client = TestClient(main.app)

SESSION = "cs_test_a1B2c3D4e5F6g7H8"
RESUME = {
    "full_name": "Nguyễn Thị Rivera",
    "email": "rivera@example.com",
    "phone": "555-0100",
    "location": "Springfield, IL",
    "address": "742 Evergreen Terrace, Springfield, IL 62701",
    "summary": "Store manager with 8 years at AT&T retail; led the <Platform> rollout.",
    "experience": [{"company": "Acme", "title": "Store Manager", "description": ["Cut shrink by 12%"]}],
    "skills": ["Coaching", "Inventory"],
    "skills_categorized": {"Leadership": [{"name": "Coaching", "weight": 85}],
                           "Retail & Merchandising": [{"name": "Inventory", "weight": 70}]},
    "template_style": "modern",
    "paid": True,
    "stripe_session": SESSION,
}
SAVED = {k: v for k, v in RESUME.items() if k not in ("paid", "stripe_session")}


def _pdf(resume_id="seal-test", data=RESUME):
    with open(main.generate_pdf(resume_id, data), "rb") as f:
        return f.read()


def _blob(pdf):
    return PdfReader(io.BytesIO(pdf)).root_object[main._SEAL_ENTRY].get_object()._data


def _pages(pdf):
    return [p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages]


def test_the_pdf_gives_back_exactly_what_built_it():
    sealed = main.read_sealed_pdf(_pdf())
    assert sealed == {"v": 1, "resume_id": "seal-test", "stripe_session": SESSION, "resume": SAVED}, sealed
    # What reading the page could never recover: the style and each skill's weight.
    assert sealed["resume"]["template_style"] == "modern"
    assert sealed["resume"]["skills_categorized"]["Leadership"] == [{"name": "Coaching", "weight": 85}]


def test_paid_is_not_taken_from_the_file():
    assert "paid" not in main.read_sealed_pdf(_pdf())["resume"]


def test_the_copy_cannot_be_read_without_the_server():
    # The page never prints the street address, and the PDF goes to strangers.
    pdf, blob = _pdf(), _blob(_pdf())
    for secret in (b"Evergreen", SESSION.encode(), b"rivera@example.com"):
        assert secret not in blob, secret
    try:
        zlib.decompress(blob)
        raise AssertionError("the copy is only compressed")
    except zlib.error:
        pass
    assert b"Evergreen" not in pdf and SESSION.encode() not in pdf


def test_a_changed_copy_is_refused():
    blob = bytearray(_blob(_pdf()))
    blob[len(blob) // 2] ^= 1
    assert main.unseal_resume(bytes(blob)) is None
    for junk in (b"", b"not a seal", None, "text"):
        assert main.unseal_resume(junk) is None, junk


def test_a_copy_sealed_with_another_secret_is_refused():
    blob = _blob(_pdf())
    assert main.unseal_resume(blob) is not None
    try:
        main._seal_cipher.cache_clear()
        with mock.patch.object(main, "_REFERRAL_KEY", b"some other server's secret"):
            assert main.unseal_resume(blob) is None
    finally:
        main._seal_cipher.cache_clear()
    assert main.unseal_resume(blob) is not None


def test_the_reader_sees_the_same_pages():
    with mock.patch.object(main, "_seal_pdf", lambda *a: None):
        plain = _pdf("plain")
    sealed = _pdf("sealed")
    assert main.read_sealed_pdf(plain) is None  # a PDF with no copy
    assert _pages(sealed) == _pages(plain)
    # Nothing a viewer or a mail filter would call an attachment.
    assert not PdfReader(io.BytesIO(sealed)).attachments
    assert len(sealed) - len(plain) < 4096, len(sealed) - len(plain)


def test_files_that_are_not_ours_give_nothing():
    pdf = _pdf()
    for upload in (b"", b"not a pdf at all", pdf[:2000], pdf[2000:]):
        assert main.read_sealed_pdf(upload) is None, upload[:20]


def test_a_copy_someone_else_planted_is_not_unpacked():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter(clone_from=io.BytesIO(_pdf()))
    bomb = DecodedStreamObject()
    bomb.set_data(b"0" * 5_000_000)
    writer.root_object[NameObject(main._SEAL_ENTRY)] = writer._add_object(bomb.flate_encode())
    planted = io.BytesIO()
    writer.write(planted)
    assert len(planted.getvalue()) < 200_000  # small file, 5 MB once unpacked
    with mock.patch.object(main, "unseal_resume", lambda blob: len(blob)):
        assert main.read_sealed_pdf(planted.getvalue()) is None


def test_a_failed_seal_still_delivers_the_resume():
    def broken(*a):
        raise RuntimeError("no seal today")
    with mock.patch.object(main, "seal_resume", broken):
        pdf = _pdf("unsealed")
    assert pdf.startswith(b"%PDF-") and _pages(pdf)[0].strip()
    assert main.read_sealed_pdf(pdf) is None


def test_a_paid_download_points_back_to_its_payment():
    r = client.post("/api/build", data={"full_name": "Jordan Rivera", "email": "jordan@example.com"})
    rid = r.json()["resume_id"]

    def retrieve(sid):
        return stripe.checkout.Session.construct_from(
            {"id": sid, "object": "checkout.session", "payment_status": "paid",
             "metadata": {"resume_id": rid}}, "sk_test")

    with mock.patch.object(stripe.checkout.Session, "retrieve", retrieve):
        assert client.get(f"/success?session_id={SESSION}").status_code == 200
    r = client.get(f"/api/download/{rid}?format=pdf")
    assert r.status_code == 200, r.status_code
    sealed = main.read_sealed_pdf(r.content)
    assert sealed["resume_id"] == rid and sealed["stripe_session"] == SESSION, sealed
    assert sealed["resume"]["full_name"] == "Jordan Rivera"


def test_healthz_reports_the_seal():
    assert client.get("/healthz").json()["seal"] is True


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
