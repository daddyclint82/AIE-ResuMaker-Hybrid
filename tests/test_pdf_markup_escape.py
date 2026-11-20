"""User text prints in the PDF exactly as typed.

Run: python tests/test_pdf_markup_escape.py   (or pytest)

generate_pdf builds reportlab Paragraph markup and used to insert user values
into it raw: "AT&T" printed as "AT&T;", a literal "&amp;" as "&", and text that
parsed as a tag ("<script>") made generate_pdf raise, so the PDF download
returned 500. Each value now goes through main._pdf_text where it is inserted.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402

main.RESUME_STORAGE_DIR = tempfile.mkdtemp()  # keep test PDFs out of the repo

VALUES = ["AT&T", "R&D", "a < b > c", "<script>", "&amp;", "Tom & Jerry's"]


def _pdf(value):
    """Render value as the name, in the summary and as a company; return the PDF path."""
    data = {"full_name": value, "summary": f"Summary {value} end",
            "experience": [{"title": "Engineer", "company": f"Company {value} end", "dates": "2019 - 2024"}]}
    try:
        return main.generate_pdf("test", data)
    except Exception as e:
        raise AssertionError(f"generate_pdf raised on {value!r}: {e}") from e


def test_markup_characters_do_not_break_the_pdf():
    for value in VALUES:
        _pdf(value)


def _squash(s):
    # pdftotext drops some spaces: the 18 pt name "X - Y - Z" comes out "X-Y-Z".
    return "".join(s.split())


def test_markup_characters_print_as_typed():
    if not shutil.which("pdftotext"):
        print("SKIP test_markup_characters_print_as_typed: pdftotext (poppler-utils) not installed")
        return
    for value in VALUES:
        text = subprocess.run(["pdftotext", "-enc", "UTF-8", _pdf(value), "-"],
                              capture_output=True, text=True, check=True).stdout
        lines = [_squash(line) for line in text.splitlines()]
        assert _squash(value.upper()) in lines, (value, text)                      # name: upper-cased, then escaped
        assert _squash(f"Summary {value} end") in lines, (value, text)
        assert _squash(f"Engineer — Company {value} end") in lines, (value, text)  # <b> renders, not prints
        assert "2019-2024" in lines, (value, text)                                  # and so does <i>


def test_combining_mark_at_the_start_of_a_value_leaves_the_tag_before_it_intact():
    # NFC used to run on the finished markup and fused U+0338 with the ">" of "<b>".
    main.generate_pdf("test", {"full_name": "T", "experience": [{"title": "̸Lead", "company": "X"}]})


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except Exception as e:
                failed += 1
                print("FAIL", name, "-", type(e).__name__, str(e)[:300])
    sys.exit(1 if failed else 0)
