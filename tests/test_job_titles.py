"""Job-title type-ahead: the bundled O*NET list and GET /api/job-titles.

Run: python tests/test_job_titles.py   (or pytest)

Drives the real route through FastAPI's TestClient over the real
data/job_titles.json: no server, no network.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)


def titles_for(q):
    r = client.get("/api/job-titles", params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()["results"]


def test_bundled_list_is_one_sorted_copy_of_each_title():
    with open(os.path.join(ROOT, "data", "job_titles.json"), encoding="utf-8") as f:
        data = json.load(f)
    titles = data["titles"]
    assert data["onet_version"] and len(titles) > 40000, (data["onet_version"], len(titles))
    assert len({t.casefold() for t in titles}) == len(titles)
    assert titles == sorted(titles, key=str.casefold)


def test_typed_title_comes_first_and_words_match_in_any_order():
    assert titles_for("store man")[0] == "Store Manager"
    assert titles_for("CNA")[0] == "CNA"
    assert titles_for("Barista")[0] == "Barista"
    assert "Registered Nurse (RN)" in titles_for("nurse reg")       # word order doesn't matter
    assert titles_for("c++")[0].startswith("C++")                    # text typed as-is ranks first
    assert "Registered Nurses" not in titles_for("registered nurse")  # occupation names aren't titles


def test_short_or_unknown_input_gets_nothing_and_at_most_ten():
    assert titles_for("s") == [] and titles_for("  ") == [] and titles_for("--") == []
    assert titles_for("prompt engineer") == []
    assert len(titles_for("manager")) == 10


def test_form_credits_the_onet_version_it_uses():
    page = client.get("/build").text
    assert f"O*NET {main._job_titles_data['onet_version']} Database" in page
    assert "Used under the" in page and "CC BY 4.0" in page and "O*NET&reg; is a trademark of USDOL/ETA" in page


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
