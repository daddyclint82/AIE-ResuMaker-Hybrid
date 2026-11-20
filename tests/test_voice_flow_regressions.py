"""Regression tests for the voice flow.

Run: python tests/test_voice_flow_regressions.py   (or pytest)

1. "Done" at "Add another job?" must move on to the summary, not re-ask.
2. For tech resumes the project questions (name, tech, description, result)
   must be stored under the field that was asked, and the result answer must
   not loop.
3. The LLM gets the job context (core edge, keywords) and its answers are
   used; when it fails, the summary and skills fall back to templates.
4. The skills prompt's categories fit the industry: retail gets the retail
   tier, and no non-tech list is filled out with tech categories.

Drives the state machine directly: no server, no LLM key, no network.
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice_api as va  # noqa: E402

va.LLM_API_KEY = ""                   # template fallbacks, no network
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



class _FakeLLM:
    """Stands in for the pooled http_client: records requests, answers like the chat API."""

    def __init__(self, replies, status=200):
        self.replies, self.status, self.calls = list(replies), status, []

    async def post(self, url, **kw):
        self.calls.append({"url": url, **kw})
        content, status = self.replies.pop(0), self.status

        class _Response:
            status_code = status
            text = "upstream error"

            def json(self):
                return {"choices": [{"message": {"content": content}}]}
        return _Response()


def _summary_and_skills_with(fake, name):
    real_client, real_key = va.http_client, va.LLM_API_KEY
    va.http_client, va.LLM_API_KEY = fake, "test-key"
    try:
        s = _session(name)
        _through_one_job(s)
        say(s, "done")
        for a in ("Fast shipper", "Slow APIs", "40% faster", "Kubernetes, Terraform"):
            step = say(s, a)
        assert step["field"] == "skills", step
        say(s, "Python, Docker")
        return s
    finally:
        va.http_client, va.LLM_API_KEY = real_client, real_key


def test_llm_gets_the_job_context_and_its_answers_are_used():
    skills = '{"Programming & Development": [{"name": "Python", "weight": 95}], "Other Skills": []}'
    fake = _FakeLLM(["Backend engineer who cut H\u2082S alarms.", skills])
    s = _summary_and_skills_with(fake, "llm-ok")
    summary_req, skills_req = fake.calls
    for req in (summary_req, skills_req):
        assert req["url"] == f"{va.LLM_BASE_URL}/chat/completions", req["url"]
        assert req["headers"]["Authorization"] == "Bearer test-key"
        assert req["json"]["model"] == va.LLM_MODEL and req["json"].get("reasoning_effort") == "low", req["json"]
    assert summary_req["json"]["max_tokens"] >= 1024           # reasoning tokens count against it
    assert skills_req["json"]["response_format"] == {"type": "json_object"}
    prompt = skills_req["json"]["messages"][1]["content"]
    assert "User's Core Edge: Fast shipper" in prompt, prompt[:400]
    assert "Target Keywords from Job Posting: Kubernetes, Terraform" in prompt, prompt[:400]
    assert s["data"]["summary"] == "Backend engineer who cut H2S alarms."   # NFKC: no black box in the PDF
    assert s["data"]["skills_categorized"] == {"Programming & Development": [{"name": "Python", "weight": 95}]}


def test_llm_failure_falls_back_to_templates():
    s = _summary_and_skills_with(_FakeLLM(["", ""], status=429), "llm-down")
    assert s["data"]["summary"] == "Fast shipper Slow APIs 40% faster", s["data"]["summary"]
    assert s["data"]["skills_categorized"] == {"Other Skills": [{"name": "Python", "weight": 50},
                                                                {"name": "Docker", "weight": 50}]}


def test_retail_gets_retail_skill_categories():
    # "ai" inside "retail" (and "it" inside "hospitality") used to pick the tech tier.
    retail = va.SKILL_TIERS["retail_hospitality"]
    for industry, keywords in (("Retail", "retail management, P&L, inventory"), ("Hospitality", "")):
        cats = va.get_relevant_tiers(industry, keywords)[:15]       # the skills prompt gets 15
        assert cats[:len(retail)] == retail, (industry, cats)
        assert not va.TECH_CATEGORIES & set(cats), (industry, cats)


def test_non_tech_lists_are_not_filled_with_tech_categories():
    for industry, keywords in (("Nonprofit", ""), ("Healthcare", "patient advocacy, training"),
                               ("Construction", "NEC, conduit bending, safety")):
        cats = va.get_relevant_tiers(industry, keywords)[:15]
        assert not va.TECH_CATEGORIES & set(cats), (industry, cats)
        assert len(set(cats)) == 15, (industry, cats)                # no duplicates taking slots
    assert va.get_relevant_tiers("Nonprofit")[:14] == va.SKILL_TIERS["general"]
    assert va.get_relevant_tiers("Information Security")[:12] == va.SKILL_TIERS["technology"]


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
