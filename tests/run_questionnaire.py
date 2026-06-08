#!/usr/bin/env python3
"""
Universal Voice Questionnaire Runner

Usage:
    python run_questionnaire.py fixtures/clint-devops-ai.json
    python run_questionnaire.py fixtures/template-generic.json
"""

import sys
import json
import requests
import argparse
from typing import Dict, List, Any

BASE_URL = "http://localhost:8000"


def load_fixture(path: str) -> dict:
    """Load a test fixture JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def run_questionnaire(fixture: dict) -> dict:
    """Run the full voice questionnaire and return final state."""
    print(f"Running: {fixture['name']}")
    print(f"Target: {fixture['target_job']}")
    print(f"Answers: {len(fixture['answers'])}")
    print()

    # Start session
    r = requests.post(f"{BASE_URL}/api/voice/start", json={})
    session = r.json()
    sid = session["session_id"]
    print(f"Session: {sid}")

    errors = []
    
    # Process each answer
    for i, step in enumerate(fixture["answers"]):
        r = requests.post(f"{BASE_URL}/api/voice/turn", json={
            "session_id": sid,
            "action": "answer",
            "transcript": step["value"]
        })
        resp = r.json()
        
        if "error" in resp:
            err = f"ERROR at step {i} ({step['step']}): {resp['error']}"
            print(err)
            errors.append(err)
            break
        
        # Show key transitions
        field = resp.get("field", "")
        if field in ["summary_q1", "summary_q2", "summary_q3", "summary_q4", "skills"]:
            print(f"  {step['step']}: {field} → OK")

    # Get final state
    r = requests.post(f"{BASE_URL}/api/voice/save", json={"session_id": sid})
    state = r.json()["state"]
    
    return state, errors


def validate_results(state: dict, expected: dict) -> List[str]:
    """Validate results against expected values."""
    errors = []
    data = state.get("data", {})
    ctx = state.get("context", {})
    
    print(f"\n{'='*60}")
    print("VALIDATION")
    print(f"{'='*60}")
    
    # Check phase
    phase = ctx.get("phase", "")
    if phase != expected.get("phase_final", "done"):
        errors.append(f"Phase: expected '{expected['phase_final']}', got '{phase}'")
    else:
        print(f"  ✅ Phase: {phase}")
    
    # Check simple fields
    simple_count = len([k for k in data.keys() if k in [
        "full_name", "email", "phone", "city", "state",
        "industry", "job_title", "experience_level", "education_level"
    ]])
    if simple_count < expected.get("simple_fields_count", 9):
        errors.append(f"Simple fields: expected {expected['simple_fields_count']}, got {simple_count}")
    else:
        print(f"  ✅ Simple fields: {simple_count}")
    
    # Check experience
    import json as json_mod
    exp = data.get("experience", "[]")
    try:
        exp_list = json_mod.loads(exp) if isinstance(exp, str) else exp
        job_count = len(exp_list)
        if job_count != expected.get("jobs", 0):
            errors.append(f"Jobs: expected {expected['jobs']}, got {job_count}")
        else:
            print(f"  ✅ Jobs: {job_count}")
        
        # Check bullets per job
        for i, job in enumerate(exp_list):
            desc = job.get("description", [])
            if isinstance(desc, list):
                bullet_count = len(desc)
                expected_bullets = expected.get("bullets_per_job", 3)
                if bullet_count != expected_bullets:
                    errors.append(f"Job {i+1}: expected {expected_bullets} bullets, got {bullet_count}")
                else:
                    print(f"  ✅ Job {i+1}: {bullet_count} bullets")
            else:
                errors.append(f"Job {i+1}: description is not a list")
    except Exception as e:
        errors.append(f"Experience parsing error: {e}")
    
    # Check summary
    summary = data.get("summary", "")
    if summary:
        print(f"  ✅ Summary: {len(summary)} chars")
    else:
        errors.append("Summary: MISSING (Groq generation may have failed)")
    
    # Check keywords
    keywords = data.get("keywords", "")
    if keywords:
        print(f"  ✅ Keywords: {keywords[:60]}...")
    else:
        errors.append("Keywords: MISSING")
    
    # Check skills categorized
    if expected.get("skills_categorized", False):
        if "skills_categorized" in data:
            cats = data["skills_categorized"]
            print(f"  ✅ Skills categorized: {len(cats)} categories")
            
            if expected.get("validate_skills_weights", False):
                for cat, skills in cats.items():
                    for skill in skills:
                        if isinstance(skill, dict):
                            weight = skill.get("weight", 0)
                            if not (1 <= weight <= 100):
                                errors.append(f"Skill '{skill.get('name')}' has invalid weight: {weight}")
        else:
            errors.append("Skills categorized: MISSING")
    
    # Check skills text
    skills_text = data.get("skills", "")
    if skills_text:
        print(f"  ✅ Skills: {skills_text[:60]}...")
    else:
        errors.append("Skills: MISSING")
    
    return errors


def print_results(state: dict):
    """Print a summary of the final resume data."""
    data = state.get("data", {})
    ctx = state.get("context", {})
    
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    
    print(f"\nName: {data.get('full_name', 'N/A')}")
    print(f"Target: {data.get('job_title', 'N/A')}")
    print(f"Industry: {data.get('industry', 'N/A')}")
    
    print(f"\nSummary (first 100 chars):")
    summary = data.get("summary", "")
    print(f"  {summary[:100]}{'...' if len(summary) > 100 else ''}")
    
    print(f"\nSkills:")
    cats = data.get("skills_categorized", {})
    if cats:
        for cat, skills in cats.items():
            skill_names = []
            for s in skills:
                if isinstance(s, dict):
                    skill_names.append(f"{s['name']}({s.get('weight', 0)})")
                else:
                    skill_names.append(str(s))
            print(f"  {cat}: {', '.join(skill_names)}")
    else:
        print(f"  {data.get('skills', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(description="Run voice questionnaire test")
    parser.add_argument("fixture", help="Path to JSON fixture file")
    args = parser.parse_args()
    
    # Load fixture
    fixture = load_fixture(args.fixture)
    
    # Run test
    state, run_errors = run_questionnaire(fixture)
    
    # Validate
    validation_errors = validate_results(state, fixture.get("expected_results", {}))
    
    # Print results
    print_results(state)
    
    # Final report
    all_errors = run_errors + validation_errors
    print(f"\n{'='*60}")
    if all_errors:
        print(f"FAIL: {len(all_errors)} errors")
        for e in all_errors:
            print(f"  ❌ {e}")
        sys.exit(1)
    else:
        print("✅ PASS: All validations passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()