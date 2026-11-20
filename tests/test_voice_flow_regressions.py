"""Regression tests for two voice-flow loops.

Run: python tests/test_voice_flow_regressions.py   (or pytest)

1. "Done" at "Add another job?" must move on to the summary, not re-ask.
2. For tech resumes the project questions (name, tech, description, result)
   must be stored under the field that was asked, and the result answer must
   not loop.

Drives the state machine directly: no server, no Groq key, no network.
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice_api as va  # noqa: E402

va.GROQ_API_KEY = ""                  # template fallbacks, no network
va.SESSIONS_DIR = tempfile.mkdtemp()  # keep test sessions out of the repo

SIMPLE = ["Jordan Rivera", "jordan@example.com", "555-0100", "100 Example Ave, Springfield, IL 62701",
          "Springfield", "Illinois", "Technology", "Software Engineer", "mid", "bachelor's"]


def _session(name):
    s = {"session_id": name, "step_index": 0, "data": {}, "context": {"phase": "simple"},
         "history": [], "done": False}
    va.voice_sessions[name] = s
    return s


def say(s, text):
    return asyncio.run(va.process_answer(s, text))


def _through_one_job(s, industry="Technology", title="Software Engineer"):
    answers = list(SIMPLE)
    answers[6], answers[7] = industry, title
    for a in answers:
        step = say(s, a)
    for a in ("Acme Corp", "Engineer", "2021 to 2024", "Remote", "Cut latency 40%"):
        step = say(s, a)
    assert step["field"] == "_more_bullets", step
    step = say(s, "done")                     # [Done] on "Add another bullet?"
    assert step["field"] == "_add_job", step
    return step


def test_done_at_add_another_job_reaches_summary():
    for word in ("done", "no"):
        s = _session(f"job-{word}")
        _through_one_job(s)
        step = say(s, word)                   # [Done] on "Add another job?"
        assert step["field"] == "summary_q1", step
        assert s["context"]["phase"] == "summary"
        assert [j["company"] for j in s["data"]["experience"]] == ["Acme Corp"]


def test_yes_at_add_another_job_still_starts_job_two():
    s = _session("job-yes")
    _through_one_job(s)
    step = say(s, "yes")
    assert step["field"] == "company" and step["context_label"] == "Job 2", step


def _to_projects(s, skills, industry, title):
    _through_one_job(s, industry, title)
    say(s, "done")
    for a in ("Fast shipper", "Slow APIs", "40% faster", "none"):
        step = say(s, a)
    assert step["field"] == "skills", step
    return say(s, skills)


def test_tech_project_answers_land_in_the_asked_field():
    s = _session("proj-tech")
    step = _to_projects(s, "Python, FastAPI, Docker", "Technology", "Software Engineer")
    asked = []
    for answer in ("Resume Builder", "Python, FastAPI | 2025", "Voice-first resume app", "500 users"):
        asked.append(step["field"])
        step = say(s, answer)
    assert asked == ["name", "tech", "description", "result"], asked
    assert step["field"] == "_add_projects", step          # the decision, not "result" again
    assert s["context"]["projects"][0] == {"name": "Resume Builder", "tech": "Python, FastAPI | 2025",
                                           "description": "Voice-first resume app", "result": "500 users"}


def test_back_inside_a_tech_project():
    s = _session("proj-back")
    _to_projects(s, "Python, FastAPI, Docker", "Technology", "Software Engineer")
    say(s, "Resume Builder")
    say(s, "Python | 2025")
    assert va.go_back(s)["field"] == "tech"
    assert say(s, "Go | 2024")["field"] == "description"
    assert s["context"]["projects"][0] == {"name": "Resume Builder", "tech": "Go | 2024"}


def test_non_tech_project_skips_tech_question():
    s = _session("proj-retail")
    step = _to_projects(s, "Customer service, Scheduling, Inventory", "Retail", "Store Manager")
    asked = []
    for answer in ("Holiday staffing plan", "Cut overtime", "Saved $20k"):
        asked.append(step["field"])
        step = say(s, answer)
    assert asked == ["name", "description", "result"], asked
    assert step["field"] == "_add_projects", step


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
