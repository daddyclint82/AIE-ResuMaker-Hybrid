"""PDF export draws text outside cp1252 with real glyphs.

Run: python tests/test_pdf_fonts.py   (or pytest)

reportlab's built-in Times/Helvetica cover only cp1252 and drew anything else
as a black box from ZapfDingbats ("H■S", "Nguy■n"). generate_pdf now embeds
the Liberation fonts in fonts/.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402

main.RESUME_STORAGE_DIR = tempfile.mkdtemp()  # keep test PDFs out of the repo

TEXT = "H₂S safety, Nguyễn, naïve – €40,000, SafeStart™"


def _pdf(data):
    with open(main.generate_pdf("test", data), "rb") as f:
        return f.read()


def test_text_outside_cp1252_comes_from_the_embedded_fonts():
    pdf = _pdf({"full_name": "Minh Nguyễn", "location": "Đà Nẵng", "summary": TEXT, "skills": [TEXT],
                "experience": [{"title": "Safety Lead", "company": "Nguyễn Field Services",
                                "dates": "2019 – 2024", "bullets": [TEXT]}],
                "education": [{"school": "Example State University", "degree": TEXT}]})
    assert b"/FontFile2" in pdf                               # TrueType, embedded
    for std in (b"/Times-", b"/Symbol", b"/ZapfDingbats"):    # ZapfDingbats drew the black box
        assert std not in pdf, std


def test_accents_typed_as_combining_marks_are_composed():
    assert main._pdf_markup("Nguyễn", main._register_pdf_fonts()) == "Nguyễn"


def test_characters_the_fonts_lack_keep_their_old_glyphs():
    assert main._pdf_markup("✓ H₂S", main._register_pdf_fonts()) == '<font name="Times-Roman">✓</font> H₂S'
    assert b"/ZapfDingbats" in _pdf({"full_name": "Test", "skills": ["✓ OSHA 30", "★ Python"]})


def test_characters_no_font_has_print_as_their_nfkc_form():
    covered = main._register_pdf_fonts()
    assert main._pdf_markup("high‑performance", covered) == "high‐performance"  # non-breaking hyphen
    assert main._pdf_markup("＜R＆D＞", covered) == "&lt;R&amp;D&gt;"        # fullwidth: text, not markup
    assert main._pdf_markup("①", covered) == '<font name="Times-Roman">①</font>'          # ZapfDingbats draws it
    assert b"/ZapfDingbats" not in _pdf({"full_name": "Test", "summary": "Cross‑functional, 40℃"})


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
