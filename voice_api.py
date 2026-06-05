"""
Voice Chat API for AIE ResuMaker Hybrid
Simple conversational resume builder using Groq LLM
"""

import os
import json
import secrets
from datetime import datetime
from typing import Dict, List, Any, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/voice")

# Simple in-memory sessions (no classes)
voice_sessions: Dict[str, Any] = {}

# Groq config
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# Question flow
VOICE_QUESTIONS = [
    {"field": "full_name", "question": "Hey! I'm AIe ResuMaker. Let's build your resume together. First — what's your full name?"},
    {"field": "email", "question": "What's your email address?"},
    {"field": "phone", "question": "What's your phone number?"},
    {"field": "industry", "question": "What industry are you targeting? For example: Technology, Healthcare, Finance, Retail, etc."},
    {"field": "job_title", "question": "What's your target job title?"},
    {"field": "experience_level", "question": "What's your experience level — entry, mid, senior, or executive?"},
    {"field": "city", "question": "What city and state are you in?"},
    {"field": "experience", "question": "Tell me about your work history. Start with your most recent job — company name, your title, dates, and what you did."},
    {"field": "education", "question": "Any education? School name, degree, field of study, and dates."},
    {"field": "skills", "question": "What skills do you have? Technical, soft skills, tools — list them out."},
    {"field": "summary", "question": "I'll write a professional summary based on everything. Or tell me what you want to highlight about yourself."},
    {"field": "optional", "question": "Almost done! Any LinkedIn, website, certifications, or projects to add?"}
]


async def groq_extract(transcript: str, field: str) -> str:
    """Send transcript to Groq and extract single field."""
    if not GROQ_API_KEY:
        return transcript
    
    field_prompts = {
        "full_name": "Extract the person's full name. Return ONLY the name.",
        "email": "Extract the email address. Return ONLY the email.",
        "phone": "Extract the phone number. Return ONLY the number.",
        "industry": "Extract the industry. Return ONLY the industry name.",
        "job_title": "Extract the job title. Return ONLY the title.",
        "experience_level": "Classify as: entry, mid, senior, or executive. Return ONLY one word.",
        "city": "Extract city and state. Return 'City, State'.",
        "experience": "Extract work experience as JSON array: [{\"title\": \"...\", \"company\": \"...\", \"dates\": \"...\", \"description\": \"...\"}]. Return ONLY valid JSON.",
        "education": "Extract education as JSON array: [{\"school\": \"...\", \"degree\": \"...\", \"field\": \"...\", \"dates\": \"...\"}]. Return ONLY valid JSON.",
        "skills": "Extract skills as comma-separated list. Return ONLY the list.",
        "summary": "Write a 2-3 sentence professional summary. Return ONLY the summary.",
        "optional": "Extract any optional info (LinkedIn, website, certs). Return as plain text or 'none'."
    }
    
    prompt = field_prompts.get(field, f"Extract the {field} from this transcript. Return ONLY the value.")
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": transcript}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[Groq Error] {e}")
    
    return transcript


@router.post("/start")
async def voice_start():
    """Start a new voice session. Returns first question."""
    session_id = secrets.token_urlsafe(16)
    voice_sessions[session_id] = {
        "session_id": session_id,
        "turn": 0,
        "data": {},
        "history": [],
        "done": False
    }
    
    first_q = VOICE_QUESTIONS[0]
    return {
        "session_id": session_id,
        "question": first_q["question"],
        "field": first_q["field"],
        "turn": 0,
        "done": False
    }


@router.post("/turn")
async def voice_turn(request: Request):
    """Process a turn: transcript -> extract -> next question."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        transcript = body.get("transcript", "").strip()
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "Invalid session"}, status_code=400)
        
        if not transcript:
            return JSONResponse({"error": "Transcript is required"}, status_code=400)
        
        session = voice_sessions[session_id]
        
        if session["done"]:
            return {
                "session_id": session_id,
                "question": "Your resume is ready! Click 'View Resume'.",
                "field": "done",
                "turn": session["turn"],
                "done": True,
                "data": session["data"]
            }
        
        # Get current field
        current_turn = session["turn"]
        if current_turn >= len(VOICE_QUESTIONS):
            session["done"] = True
            return {
                "session_id": session_id,
                "question": "Your resume is ready! Click 'View Resume'.",
                "field": "done",
                "turn": current_turn,
                "done": True,
                "data": session["data"]
            }
        
        current_q = VOICE_QUESTIONS[current_turn]
        current_field = current_q["field"]
        
        # Parse with Groq
        extracted = await groq_extract(transcript, current_field)
        
        # Store in session
        session["data"][current_field] = extracted
        session["history"].append({
            "turn": current_turn,
            "field": current_field,
            "transcript": transcript,
            "extracted": extracted
        })
        
        # Advance
        session["turn"] += 1
        next_turn = session["turn"]
        
        # Check if done
        if next_turn >= len(VOICE_QUESTIONS):
            session["done"] = True
            return {
                "session_id": session_id,
                "question": "Your resume is ready! Click 'View Resume'.",
                "field": "done",
                "turn": next_turn,
                "done": True,
                "data": session["data"],
                "extracted": extracted
            }
        
        # Next question
        next_q = VOICE_QUESTIONS[next_turn]
        return {
            "session_id": session_id,
            "question": next_q["question"],
            "field": next_q["field"],
            "turn": next_turn,
            "done": False,
            "data": session["data"],
            "extracted": extracted
        }
        
    except Exception as e:
        print(f"[Voice Turn Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/finish")
async def voice_finish(request: Request):
    """Finish voice session and create resume."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "Invalid session"}, status_code=400)
        
        session = voice_sessions[session_id]
        resume_data = session["data"].copy()
        
        # Parse arrays
        if isinstance(resume_data.get("experience"), str):
            try:
                resume_data["experience"] = json.loads(resume_data["experience"])
            except:
                resume_data["experience"] = []
        
        if isinstance(resume_data.get("education"), str):
            try:
                resume_data["education"] = json.loads(resume_data["education"])
            except:
                resume_data["education"] = []
        
        if isinstance(resume_data.get("skills"), str):
            resume_data["skills"] = [s.strip() for s in resume_data["skills"].split(",") if s.strip()]
        
        return {
            "success": True,
            "session_id": session_id,
            "data": resume_data
        }
        
    except Exception as e:
        print(f"[Voice Finish Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
