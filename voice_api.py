"""
Voice Chat API for AIE ResuMaker Hybrid — ADHD-Optimized with Back/Add buttons
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

voice_sessions: Dict[str, Any] = {}

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# =============================================================================
# STEP DEFINITIONS — each step is one micro-question
# =============================================================================

# Simple field steps
SIMPLE_STEPS = [
    {"field": "full_name", "question": "Hey! I'm AIe ResuMaker. Let's build your resume together. First — what's your full name?", "group": "personal"},
    {"field": "email", "question": "What's your email address?", "group": "personal"},
    {"field": "phone", "question": "What's your phone number?", "group": "personal"},
    {"field": "city", "question": "What city do you live in?", "group": "personal"},
    {"field": "state", "question": "What state?", "group": "personal"},
    {"field": "industry", "question": "What industry are you targeting?", "group": "target"},
    {"field": "job_title", "question": "What's your target job title?", "group": "target"},
    {"field": "experience_level", "question": "Experience level — entry, mid, senior, or executive?", "group": "target"},
    {"field": "education_level", "question": "Education level — high school, associate, bachelor's, master's, doctorate, or certification?", "group": "target"},
]

# Experience loop steps — bullets for description
EXPERIENCE_STEPS = [
    {"field": "company", "question": "What company did you work at?", "subfield": "company"},
    {"field": "title", "question": "What was your title there?", "subfield": "title"},
    {"field": "dates", "question": "When did you work there? Say '2020 to 2022'", "subfield": "dates"},
    {"field": "description", "question": "What did you do there? Say bullet 1.", "subfield": "description", "is_bullet": True},
]

# Education loop steps
EDUCATION_STEPS = [
    {"field": "school", "question": "School name?", "subfield": "school"},
    {"field": "degree", "question": "What degree? Say 'Bachelor of Science'", "subfield": "degree"},
    {"field": "field", "question": "Field of study?", "subfield": "field"},
    {"field": "dates", "question": "When? Say '2018 to 2022'", "subfield": "dates"},
]

# Optional section steps
PROJECT_STEPS = [
    {"field": "project_name", "question": "Project name?", "subfield": "name"},
    {"field": "project_description", "question": "Describe the project.", "subfield": "description"},
]

COMPETENCY_STEPS = [
    {"field": "competency", "question": "What competency?", "subfield": "name"},
]

COMMUNITY_STEPS = [
    {"field": "community_org", "question": "Organization name?", "subfield": "organization"},
    {"field": "community_role", "question": "Your role?", "subfield": "role"},
]

CERT_STEPS = [
    {"field": "cert_name", "question": "Certification name?", "subfield": "name"},
    {"field": "cert_date", "question": "When did you get it?", "subfield": "date"},
]

# =============================================================================
# STATE MACHINE
# =============================================================================

def get_next_step(session: dict) -> dict:
    """Determine the next question based on session state."""
    step_index = session["step_index"]
    context = session.get("context", {})
    
    # Phase 1: Simple fields (steps 0-8)
    if step_index < len(SIMPLE_STEPS):
        return SIMPLE_STEPS[step_index]
    
    # Phase 2: Experience loop
    exp_idx = step_index - len(SIMPLE_STEPS)
    if context.get("phase") == "experience":
        # Check if we're in the experience steps or at a decision point
        exp_count = len(context.get("experience", []))
        substep = context.get("exp_substep", 0)
        bullet_count = context.get("exp_bullet_count", 0)
        
        if substep < len(EXPERIENCE_STEPS) - 1:
            # Standard fields: company, title, dates
            step = EXPERIENCE_STEPS[substep].copy()
            step["context_label"] = f"Job {exp_count + 1}"
            step["show_add_job"] = True  # Show "Add Job" button
            return step
        elif substep == len(EXPERIENCE_STEPS) - 1:
            # Description/bullet field
            step = EXPERIENCE_STEPS[substep].copy()
            step["context_label"] = f"Job {exp_count + 1}"
            step["show_add_job"] = True
            if bullet_count > 0:
                step["question"] = f"Bullet {bullet_count + 1}?"
            return step
        else:
            # After all standard fields, check if we're in bullet loop
            in_bullet_loop = context.get("in_bullet_loop", False)
            if in_bullet_loop:
                # Ask for next bullet
                return {
                    "field": "_bullet",
                    "question": f"Bullet {bullet_count + 1}?",
                    "context_label": f"Job {exp_count}",
                    "show_add_job": True
                }
            else:
                # Decision: add another job?
                return {
                    "field": "_decision",
                    "question": f"Great! Job {exp_count} saved. Add another job? Say 'yes' or 'done'.",
                    "context_label": "Jobs",
                    "show_add_job": False
                }
    
    # Phase 3: Education loop
    if context.get("phase") == "education":
        edu_count = len(context.get("education", []))
        substep = context.get("edu_substep", 0)
        
        if substep < len(EDUCATION_STEPS):
            step = EDUCATION_STEPS[substep].copy()
            step["context_label"] = f"School {edu_count + 1}"
            return step
        else:
            return {"field": "_decision", "question": f"School {edu_count} saved. Add another school? Say 'yes' or 'done'.", "context_label": "Education"}
    
    # Phase 4: Skills
    if context.get("phase") == "skills":
        return {"field": "skills", "question": "What skills do you have? List them: 'Python, communication, Excel'", "group": "skills"}
    
    # Phase 5: Optional sections
    if context.get("phase") == "optional":
        opt_section = context.get("opt_section", "projects")
        
        if opt_section == "projects":
            proj_count = len(context.get("projects", []))
            substep = context.get("proj_substep", 0)
            if substep < len(PROJECT_STEPS):
                step = PROJECT_STEPS[substep].copy()
                step["context_label"] = f"Project {proj_count + 1}"
                return step
            else:
                return {"field": "_decision", "question": "Project saved. Add another project? Say 'yes', 'next', or 'skip'.", "context_label": "Projects"}
        
        elif opt_section == "competencies":
            comp_count = len(context.get("competencies", []))
            substep = context.get("comp_substep", 0)
            if substep < len(COMPETENCY_STEPS):
                step = COMPETENCY_STEPS[substep].copy()
                step["context_label"] = f"Competency {comp_count + 1}"
                return step
            else:
                return {"field": "_decision", "question": "Competency saved. Add another? Say 'yes', 'next', or 'skip'.", "context_label": "Competencies"}
        
        elif opt_section == "community":
            comm_count = len(context.get("community", []))
            substep = context.get("comm_substep", 0)
            if substep < len(COMMUNITY_STEPS):
                step = COMMUNITY_STEPS[substep].copy()
                step["context_label"] = f"Community {comm_count + 1}"
                return step
            else:
                return {"field": "_decision", "question": "Entry saved. Add another? Say 'yes', 'next', or 'skip'.", "context_label": "Community"}
        
        elif opt_section == "certifications":
            cert_count = len(context.get("certifications", []))
            substep = context.get("cert_substep", 0)
            if substep < len(CERT_STEPS):
                step = CERT_STEPS[substep].copy()
                step["context_label"] = f"Cert {cert_count + 1}"
                return step
            else:
                return {"field": "_decision", "question": "Cert saved. Add another? Say 'yes', 'next', or 'skip'.", "context_label": "Certifications"}
        
        elif opt_section == "links":
            return {"field": "linkedin", "question": "LinkedIn URL? Or say 'skip'.", "group": "links"}
        
        elif opt_section == "website":
            return {"field": "website", "question": "Website or portfolio? Or say 'skip'.", "group": "links"}
    
    # Phase 6: Summary
    if context.get("phase") == "summary":
        return {"field": "summary", "question": "I'll write a professional summary. Sound good? Say 'auto' or tell me what to highlight.", "group": "summary"}
    
    # Done
    return {"field": "done", "question": "Your resume is ready! Click 'View Resume' below.", "done": True}


def advance_state(session: dict, extracted: str) -> None:
    """Update session state based on current step and extracted value."""
    step_index = session["step_index"]
    context = session.setdefault("context", {})
    data = session["data"]
    
    # Phase 1: Simple fields
    if step_index < len(SIMPLE_STEPS):
        field = SIMPLE_STEPS[step_index]["field"]
        data[field] = extracted
        session["step_index"] += 1
        
        # Transition to experience phase after simple fields
        if session["step_index"] == len(SIMPLE_STEPS):
            context["phase"] = "experience"
            context["exp_substep"] = 0
            context["experience"] = []
        return
    
    # Phase 2: Experience
    if context.get("phase") == "experience":
        substep = context.get("exp_substep", 0)
        exp_list = context.setdefault("experience", [])
        bullet_count = context.get("exp_bullet_count", 0)
        in_bullet_loop = context.get("in_bullet_loop", False)
        
        # Handle "add_job" action — skip to new job immediately
        if extracted == "__ADD_JOB__":
            # Finalize current job if it has any data
            if exp_list and not any(k in exp_list[-1] for k in ["company", "title"]):
                exp_list.pop()
            context["exp_substep"] = 0
            context["exp_bullet_count"] = 0
            context["in_bullet_loop"] = False
            return
        
        if substep < len(EXPERIENCE_STEPS) - 1:
            # Standard fields: company, title, dates (indices 0, 1, 2)
            if not exp_list or len(exp_list[-1]) >= len(EXPERIENCE_STEPS):
                exp_list.append({})
            exp_list[-1][EXPERIENCE_STEPS[substep]["subfield"]] = extracted
            context["exp_substep"] = substep + 1
        elif substep == len(EXPERIENCE_STEPS) - 1:
            # Description field (index 3) — this is the first bullet
            if not exp_list or len(exp_list[-1]) >= len(EXPERIENCE_STEPS):
                exp_list.append({})
            exp_list[-1]["description"] = [extracted]
            context["in_bullet_loop"] = True
            context["exp_bullet_count"] = 1
            # Set substep past EXPERIENCE_STEPS so get_next_step enters bullet loop logic
            context["exp_substep"] = len(EXPERIENCE_STEPS)
        else:
            # substep >= len(EXPERIENCE_STEPS) — we're in bullet loop mode
            if not in_bullet_loop:
                # Shouldn't happen, but just in case
                if exp_list:
                    exp_list[-1]["description"] = [extracted]
                context["in_bullet_loop"] = True
                context["exp_bullet_count"] = 1
            else:
                # In bullet loop — check if user wants more bullets or is done
                if extracted.lower() in ["done", "no", "n", "finished", "complete", "that's it", "thats it"]:
                    # Done with bullets, move to "add another job?" decision
                    context["in_bullet_loop"] = False
                    context["exp_bullet_count"] = 0
                elif extracted.lower() in ["yes", "y", "add", "another", "more"]:
                    # User said yes to "add another bullet?" — ask for next bullet
                    context["exp_bullet_count"] = bullet_count + 1
                else:
                    # User provided another bullet
                    if exp_list and "description" in exp_list[-1]:
                        if isinstance(exp_list[-1]["description"], list):
                            exp_list[-1]["description"].append(extracted)
                        else:
                            exp_list[-1]["description"] = [exp_list[-1]["description"], extracted]
                    context["exp_bullet_count"] = bullet_count + 1
        return
    
    # Phase 3: Education
    if context.get("phase") == "education":
        substep = context.get("edu_substep", 0)
        edu_list = context.setdefault("education", [])
        
        if substep < len(EDUCATION_STEPS):
            if not edu_list or len(edu_list[-1]) >= len(EDUCATION_STEPS):
                edu_list.append({})
            edu_list[-1][EDUCATION_STEPS[substep]["subfield"]] = extracted
            context["edu_substep"] = substep + 1
        else:
            if extracted.lower() in ["yes", "y", "add", "another", "more"]:
                context["edu_substep"] = 0
            else:
                data["education"] = edu_list
                context["phase"] = "skills"
        return
    
    # Phase 4: Skills
    if context.get("phase") == "skills":
        data["skills"] = extracted
        context["phase"] = "optional"
        context["opt_section"] = "projects"
        context["proj_substep"] = 0
        context["projects"] = []
        return
    
    # Phase 5: Optional sections
    if context.get("phase") == "optional":
        opt_section = context.get("opt_section", "projects")
        
        if opt_section == "projects":
            substep = context.get("proj_substep", 0)
            proj_list = context.setdefault("projects", [])
            
            if substep < len(PROJECT_STEPS):
                if not proj_list or len(proj_list[-1]) >= len(PROJECT_STEPS):
                    proj_list.append({})
                proj_list[-1][PROJECT_STEPS[substep]["subfield"]] = extracted
                context["proj_substep"] = substep + 1
            else:
                if extracted.lower() in ["yes", "y", "add", "another"]:
                    context["proj_substep"] = 0
                elif extracted.lower() in ["next", "n", "done"]:
                    data["projects"] = proj_list
                    context["opt_section"] = "competencies"
                    context["comp_substep"] = 0
                    context["competencies"] = []
                else:  # skip
                    context["opt_section"] = "competencies"
                    context["comp_substep"] = 0
                    context["competencies"] = []
            return
        
        elif opt_section == "competencies":
            substep = context.get("comp_substep", 0)
            comp_list = context.setdefault("competencies", [])
            
            if substep < len(COMPETENCY_STEPS):
                if not comp_list or len(comp_list[-1]) >= len(COMPETENCY_STEPS):
                    comp_list.append({})
                comp_list[-1][COMPETENCY_STEPS[substep]["subfield"]] = extracted
                context["comp_substep"] = substep + 1
            else:
                if extracted.lower() in ["yes", "y", "add", "another"]:
                    context["comp_substep"] = 0
                elif extracted.lower() in ["next", "n", "done"]:
                    data["competencies"] = comp_list
                    context["opt_section"] = "community"
                    context["comm_substep"] = 0
                    context["community"] = []
                else:
                    context["opt_section"] = "community"
                    context["comm_substep"] = 0
                    context["community"] = []
            return
        
        elif opt_section == "community":
            substep = context.get("comm_substep", 0)
            comm_list = context.setdefault("community", [])
            
            if substep < len(COMMUNITY_STEPS):
                if not comm_list or len(comm_list[-1]) >= len(COMMUNITY_STEPS):
                    comm_list.append({})
                comm_list[-1][COMMUNITY_STEPS[substep]["subfield"]] = extracted
                context["comm_substep"] = substep + 1
            else:
                if extracted.lower() in ["yes", "y", "add", "another"]:
                    context["comm_substep"] = 0
                elif extracted.lower() in ["next", "n", "done"]:
                    data["community"] = comm_list
                    context["opt_section"] = "certifications"
                    context["cert_substep"] = 0
                    context["certifications"] = []
                else:
                    context["opt_section"] = "certifications"
                    context["cert_substep"] = 0
                    context["certifications"] = []
            return
        
        elif opt_section == "certifications":
            substep = context.get("cert_substep", 0)
            cert_list = context.setdefault("certifications", [])
            
            if substep < len(CERT_STEPS):
                if not cert_list or len(cert_list[-1]) >= len(CERT_STEPS):
                    cert_list.append({})
                cert_list[-1][CERT_STEPS[substep]["subfield"]] = extracted
                context["cert_substep"] = substep + 1
            else:
                if extracted.lower() in ["yes", "y", "add", "another"]:
                    context["cert_substep"] = 0
                elif extracted.lower() in ["next", "n", "done"]:
                    data["certifications"] = cert_list
                    context["opt_section"] = "links"
                else:
                    context["opt_section"] = "links"
            return
        
        elif opt_section == "links":
            if opt_section == "links" and context.get("current_link_field") == "website":
                data["website"] = extracted if extracted.lower() != "skip" else ""
                context["phase"] = "summary"
            else:
                data["linkedin"] = extracted if extracted.lower() != "skip" else ""
                context["current_link_field"] = "website"
            return
    
    # Phase 6: Summary
    if context.get("phase") == "summary":
        data["summary"] = extracted
        session["done"] = True
        return


def go_back(session: dict) -> dict:
    """Go back one step. Returns the step to re-ask."""
    step_index = session["step_index"]
    context = session.get("context", {})
    data = session["data"]
    
    # Simple fields
    if step_index <= len(SIMPLE_STEPS) and step_index > 0:
        session["step_index"] -= 1
        new_step = SIMPLE_STEPS[session["step_index"]]
        # Remove old answer
        if new_step["field"] in data:
            del data[new_step["field"]]
        return new_step
    
    # Experience phase
    if context.get("phase") == "experience":
        substep = context.get("exp_substep", 0)
        exp_list = context.get("experience", [])
        bullet_count = context.get("exp_bullet_count", 0)
        in_bullet_loop = context.get("in_bullet_loop", False)
        
        if in_bullet_loop and bullet_count > 0:
            # In bullet loop — go back one bullet
            context["exp_bullet_count"] = bullet_count - 1
            if exp_list and "description" in exp_list[-1]:
                if isinstance(exp_list[-1]["description"], list) and len(exp_list[-1]["description"]) > 0:
                    exp_list[-1]["description"].pop()
                    if len(exp_list[-1]["description"]) == 0:
                        del exp_list[-1]["description"]
                        context["in_bullet_loop"] = False
            return {
                "field": "_bullet",
                "question": f"Bullet {bullet_count}?" if bullet_count > 1 else "What did you do there? Say bullet 1.",
                "context_label": f"Job {len(exp_list)}",
                "show_add_job": True
            }
        
        if substep > 0:
            context["exp_substep"] = substep - 1
            # Remove the last field from current entry
            if exp_list:
                field = EXPERIENCE_STEPS[substep - 1]["subfield"]
                if field in exp_list[-1]:
                    del exp_list[-1][field]
            step = EXPERIENCE_STEPS[substep - 1].copy()
            step["context_label"] = f"Job {len(exp_list)}"
            step["show_add_job"] = True
            return step
        elif exp_list:
            # Going back to previous job's last field
            exp_list.pop()
            if exp_list:
                context["exp_substep"] = len(EXPERIENCE_STEPS) - 1
                context["in_bullet_loop"] = True
                context["exp_bullet_count"] = len(exp_list[-1].get("description", [])) if "description" in exp_list[-1] else 0
                return {
                    "field": "_bullet",
                    "question": f"Bullet {context['exp_bullet_count'] + 1}?",
                    "context_label": f"Job {len(exp_list)}",
                    "show_add_job": True
                }
            else:
                # Back to simple fields
                session["step_index"] = len(SIMPLE_STEPS) - 1
                context.pop("phase", None)
                context.pop("in_bullet_loop", None)
                context.pop("exp_bullet_count", None)
                return SIMPLE_STEPS[-1]
    
    # Add more back logic for other phases as needed
    # For now, return current step if can't go back
    return get_next_step(session)


# =============================================================================
# GROQ EXTRACTION
# =============================================================================

async def groq_extract(transcript: str, field: str) -> str:
    """Send transcript to Groq and extract single field."""
    if not GROQ_API_KEY:
        return transcript
    
    # Determine what to extract based on field
    if field == "_decision":
        prompt = "Classify as: yes, no, done, skip, next, add, another. Return ONLY one word."
    elif field in ["full_name", "email", "phone", "city", "state", "industry", "job_title", "experience_level", "education_level", "linkedin", "website"]:
        prompt = f"Extract the {field}. Return ONLY the value."
    elif field in ["company", "title", "school", "degree", "field", "project_name", "competency", "community_org", "cert_name"]:
        prompt = f"Extract the {field}. Return ONLY the value."
    elif field in ["dates", "cert_date"]:
        prompt = "Extract dates. Return ONLY the dates in format 'YYYY to YYYY' or 'Month YYYY to Month YYYY'."
    elif field == "_bullet":
        prompt = "Extract the achievement/responsibility bullet point. Return ONLY the bullet text."
    elif field in ["description", "project_description"]:
        prompt = "Extract the description. Return ONLY the description text."
    elif field == "skills":
        prompt = "Extract skills as comma-separated list. Return ONLY the list."
    elif field == "summary":
        prompt = "Write a 2-3 sentence professional summary. Return ONLY the summary."
    else:
        prompt = f"Extract the {field} from this transcript. Return ONLY the value."
    
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


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.post("/start")
async def voice_start():
    """Start a new voice session."""
    session_id = secrets.token_urlsafe(16)
    voice_sessions[session_id] = {
        "session_id": session_id,
        "step_index": 0,
        "data": {},
        "context": {},
        "history": [],
        "done": False
    }
    
    step = get_next_step(voice_sessions[session_id])
    return {
        "session_id": session_id,
        "question": step["question"],
        "field": step["field"],
        "context_label": step.get("context_label", ""),
        "step_index": 0,
        "done": False,
        "can_go_back": False,
        "show_add_job": step.get("show_add_job", False)
    }


@router.post("/turn")
async def voice_turn(request: Request):
    """Process a turn: transcript -> extract -> next question."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        transcript = body.get("transcript", "").strip()
        action = body.get("action", "answer")  # "answer", "back", "add"
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "Invalid session"}, status_code=400)
        
        session = voice_sessions[session_id]
        
        if session["done"]:
            return {
                "session_id": session_id,
                "question": "Your resume is ready! Click 'View Resume' below.",
                "field": "done",
                "done": True,
                "data": session["data"]
            }
        
        # Handle BACK action
        if action == "back":
            step = go_back(session)
            return {
                "session_id": session_id,
                "question": step["question"],
                "field": step["field"],
                "context_label": step.get("context_label", ""),
                "step_index": session["step_index"],
                "done": False,
                "can_go_back": session["step_index"] > 0 or session.get("context", {}).get("exp_substep", 0) > 0 or session.get("context", {}).get("in_bullet_loop", False),
                "show_add_job": step.get("show_add_job", False),
                "action": "back"
            }
        
        # Handle ADD action (force new entry in current loop)
        if action == "add":
            context = session.get("context", {})
            if context.get("phase") == "experience":
                # In bullet loop, "add" means "add another bullet"
                if context.get("in_bullet_loop", False):
                    # Just increment bullet count, ask for next bullet
                    context["exp_bullet_count"] = context.get("exp_bullet_count", 0) + 1
                else:
                    context["exp_substep"] = 0
            elif context.get("phase") == "education":
                context["edu_substep"] = 0
            elif context.get("phase") == "optional":
                opt = context.get("opt_section", "")
                if opt == "projects":
                    context["proj_substep"] = 0
                elif opt == "competencies":
                    context["comp_substep"] = 0
                elif opt == "community":
                    context["comm_substep"] = 0
                elif opt == "certifications":
                    context["cert_substep"] = 0
            
            # Get next step after add
            step = get_next_step(session)
            return {
                "session_id": session_id,
                "question": step["question"],
                "field": step["field"],
                "context_label": step.get("context_label", ""),
                "step_index": session["step_index"],
                "done": False,
                "can_go_back": True,
                "show_add_job": step.get("show_add_job", False),
                "action": "add"
            }
        
        # Handle ADD_JOB action — skip to new job immediately
        if action == "add_job":
            context = session.get("context", {})
            if context.get("phase") == "experience":
                advance_state(session, "__ADD_JOB__")
                step = get_next_step(session)
                return {
                    "session_id": session_id,
                    "question": step["question"],
                    "field": step["field"],
                    "context_label": step.get("context_label", ""),
                    "step_index": session["step_index"],
                    "done": False,
                    "can_go_back": True,
                    "show_add_job": step.get("show_add_job", False),
                    "action": "add_job"
                }
        
        # Normal answer flow
        if action not in ["back", "add"] and not transcript:
            return JSONResponse({"error": "Transcript is required"}, status_code=400)
        
        # For add action, we already returned above
        # For back action, we already returned above
        # So here action must be "answer" with transcript
        
        step = get_next_step(session)
        field = step["field"]
        
        # For bullet loop, use raw transcript (don't send "done" or bullet text to Groq)
        if field == "_bullet":
            # Check if user wants to stop adding bullets
            transcript_lower = transcript.lower().strip()
            if transcript_lower in ["done", "no", "n", "finished", "complete", "that's it", "thats it", "skip"]:
                extracted = "done"
            elif transcript_lower in ["yes", "y", "add", "another", "more"]:
                extracted = "yes"
            else:
                extracted = transcript  # Use raw bullet text
        else:
            # Extract with Groq for all other fields
            extracted = await groq_extract(transcript, field)
        
        # Store in history
        session["history"].append({
            "step_index": session["step_index"],
            "field": field,
            "transcript": transcript,
            "extracted": extracted
        })
        
        # Advance state
        advance_state(session, extracted)
        
        # Get next step
        next_step = get_next_step(session)
        
        return {
            "session_id": session_id,
            "question": next_step["question"],
            "field": next_step["field"],
            "context_label": next_step.get("context_label", ""),
            "step_index": session["step_index"],
            "done": next_step.get("done", False),
            "can_go_back": session["step_index"] > 0 or session.get("context", {}).get("exp_substep", 0) > 0 or session.get("context", {}).get("in_bullet_loop", False),
            "show_add_job": next_step.get("show_add_job", False),
            "data_preview": {k: v for k, v in session["data"].items() if k not in ["experience", "education", "projects", "competencies", "community", "certifications"]},
            "extracted": extracted
        }
        
    except Exception as e:
        print(f"[Voice Turn Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/finish")
async def voice_finish(request: Request):
    """Finish voice session and return structured resume data."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "Invalid session"}, status_code=400)
        
        session = voice_sessions[session_id]
        resume_data = session["data"].copy()
        
        # Parse skills
        if isinstance(resume_data.get("skills"), str):
            resume_data["skills"] = [s.strip() for s in resume_data["skills"].split(",") if s.strip()]
        
        return {
            "success": True,
            "session_id": session_id,
            "data": resume_data,
            "context": session.get("context", {})
        }
        
    except Exception as e:
        print(f"[Voice Finish Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
