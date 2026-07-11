#!/usr/bin/env python3
"""Test script to verify professional summary generation fix."""

import asyncio
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_api import (
    voice_start,
    process_answer,
    get_current_state,
    generate_summary_with_groq,
    voice_sessions
)


async def test_summary_generation():
    """Test that summary is automatically generated after 4 questions."""
    print("=" * 60)
    print("Testing Professional Summary Generation Fix")
    print("=" * 60)
    
    # Create a mock request
    class MockRequest:
        async def json(self):
            return {}
    
    # Start session
    req = MockRequest()
    result = await voice_start(req)
    session_id = result["session_id"]
    session = voice_sessions[session_id]
    
    print(f"\n1. Started session: {session_id[:16]}...")
    print(f"   First question: {result['question']}")
    
    # Fill in simple fields quickly
    simple_answers = [
        "Clint Singleton",
        "clint@example.com",
        "555-1234",
        "Austin",
        "Texas",
        "Technology",
        "Software Engineer",
        "senior",
        "bachelor's"
    ]
    
    print("\n2. Filling simple fields...")
    for i, answer in enumerate(simple_answers):
        result = await process_answer(session, answer)
    
    print(f"   Phase: {session['context']['phase']}")
    print(f"   Current question: {result['question'][:50]}...")
    
    # Add one job with 3 bullets
    print("\n3. Adding experience...")
    job_data = ["TechCorp", "Senior Developer", "2020 to 2023"]
    for answer in job_data:
        result = await process_answer(session, answer)
        print(f"   Field: {result['field']}")
    
    # First bullet
    result = await process_answer(session, "Built REST APIs serving 10k requests/day")
    print(f"   After bullet 1: field={result['field']}, type={result.get('type', 'unknown')}")
    
    # Say yes to more bullets
    result = await process_answer(session, "yes")
    
    # Second bullet
    result = await process_answer(session, "Migrated database reducing latency by 40%")
    print(f"   After bullet 2: field={result['field']}, type={result.get('type', 'unknown')}")
    
    # Say yes to more bullets
    result = await process_answer(session, "yes")
    
    # Third bullet
    result = await process_answer(session, "Led team of 5 engineers on core product")
    print(f"   After bullet 3: field={result['field']}, type={result.get('type', 'unknown')}")
    
    # Say done with bullets
    result = await process_answer(session, "done")
    print(f"   After done: field={result['field']}, type={result.get('type', 'unknown')}")
    
    # Say no more jobs
    result = await process_answer(session, "done")
    print(f"\n4. After experience complete:")
    print(f"   Phase: {session['context']['phase']}")
    print(f"   Question: {result['question'][:60]}...")
    
    # Answer summary questions
    summary_answers = [
        "I specialize in building scalable backend systems",
        "I solve API performance and database optimization problems",
        "I reduced API latency by 60% and handled 1M daily requests",
        "Python, Kubernetes, microservices"
    ]
    
    print("\n5. Answering summary questions...")
    for i, answer in enumerate(summary_answers):
        result = await process_answer(session, answer)
        print(f"   Q{i+1} answered. Next: {result['question'][:50]}...")
    
    # After all 4 summary questions, summary should be generated
    print(f"\n6. After all summary questions:")
    print(f"   Phase: {session['context']['phase']}")
    print(f"   Summary_answers: {session['context'].get('summary_answers', {})}")
    
    # Check if summary was generated
    data = session.get("data", {})
    summary = data.get("summary", "")
    
    print(f"\n7. Generated Summary:")
    print(f"   '{summary}'")
    
    if summary and summary != "Experienced professional with proven track record.":
        print("\n✅ SUCCESS: Summary was generated!")
        if len(summary) > 50:
            print("   Summary is substantial (good length)")
        return True
    else:
        print("\n❌ FAILURE: Summary was NOT generated properly")
        print(f"   Expected custom summary, got: '{summary}'")
        return False


async def test_generate_summary_directly():
    """Test the generate_summary_with_groq function directly."""
    print("\n" + "=" * 60)
    print("Testing generate_summary_with_groq Directly")
    print("=" * 60)
    
    # Create mock session with summary answers
    session = {
        "context": {
            "summary_answers": {
                "summary_q1": "I build AI-powered developer tools",
                "summary_q2": "I solve code review bottlenecks and deployment delays",
                "summary_q3": "I shipped features 3x faster by automating CI/CD",
                "summary_q4": "Python, TypeScript, Docker, AWS"
            }
        },
        "data": {
            "job_title": "Senior Software Engineer"
        }
    }
    
    summary = await generate_summary_with_groq(session)
    
    print(f"\nGenerated summary: '{summary}'")
    
    if summary and "AI" in summary or "developer" in summary or "engineer" in summary:
        print("\n✅ Direct test PASSED")
        return True
    else:
        print("\n❌ Direct test FAILED - summary doesn't contain expected content")
        return False


async def main():
    print("Starting summary generation tests...\n")
    
    test1_passed = await test_summary_generation()
    test2_passed = await test_generate_summary_directly()
    
    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)
    print(f"Full Flow Test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Direct Function Test: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 All tests passed! Summary generation is working.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
