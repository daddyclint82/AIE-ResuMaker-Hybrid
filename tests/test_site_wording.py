"""The pages say what the product does: PDF and Word, keep your file and key,
what is stored and for how long."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("REFERRAL_SECRET", "test-secret-for-wording")

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_landing_makes_no_claim_the_product_does_not_keep():
    page = client.get("/").text
    assert "stays in your browser" not in page
    assert "pick a template" not in page
    assert "you both save" not in page
    assert "your PDF is your saved copy" in page
    assert "5 edits included" in page


def test_terms_describe_the_files_the_storage_and_the_key():
    page = client.get("/terms").text
    assert "(.docx)" not in page
    assert "No Email Collection" not in page
    assert "We do not retain your data after you close your session" not in page
    assert "PDF and Word" in page
    assert "We do not keep your resume on file" in page
    assert "AI service provider" in page
    assert "5.5 What You Receive" in page
    assert "5.6 Keeping Your Resume" in page
    assert "November 21, 2026" in page


def test_success_page_tells_the_customer_to_keep_the_pdf():
    page = open(os.path.join(os.path.dirname(__file__), "..", "templates", "success.html"),
                encoding="utf-8").read()
    assert "Your PDF is your saved copy" in page
    assert "Premium" not in page


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
