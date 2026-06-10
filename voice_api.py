"""
Clean Voice Chat API for AIE ResuMaker — simplified, correct state machine.
"""

import os
import json
import secrets
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from dotenv import load_dotenv
env_file = ".env.development" if os.path.exists(".env.development") else ".env"
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    load_dotenv()

router = APIRouter(prefix="/api/voice")

import asyncio

voice_sessions: Dict[str, Any] = {}

# Per-session async locks to enforce strict sequential processing
session_locks: Dict[str, asyncio.Lock] = {}

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "voice_sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

# In-memory session storage with disk persistence
voice_sessions: Dict[str, Any] = {}

# Load any existing persisted sessions on startup
for fname in os.listdir(SESSIONS_DIR):
    if fname.endswith(".json"):
        sid = fname[:-5]
        try:
            with open(os.path.join(SESSIONS_DIR, fname), "r") as f:
                voice_sessions[sid] = json.load(f)
        except Exception:
            pass

def _persist_session(session_id: str):
    """Save session to disk immediately."""
    session = voice_sessions.get(session_id)
    if not session:
        return
    try:
        with open(os.path.join(SESSIONS_DIR, f"{session_id}.json"), "w") as f:
            json.dump(session, f, default=str)
    except Exception as e:
        print(f"[Session Persist Error] {e}")

# =============================================================================
# STEP DEFINITIONS
# =============================================================================

SIMPLE_STEPS = [
    {"field": "full_name", "question": "Hey! I'm AIe ResuMaker. Let's build your resume together. First — what's your full name?"},
    {"field": "email", "question": "What's your email address?"},
    {"field": "phone", "question": "What's your phone number?"},
    {"field": "address", "question": "What's your full address? Say 'street, city, state zip' — like '227 Crestwood, Nacogdoches, TX 75961'."},
    {"field": "city", "question": "What city?"},
    {"field": "state", "question": "What state?"},
    {"field": "industry", "question": "What industry are you targeting?"},
    {"field": "job_title", "question": "What's your target job title?"},
    {"field": "experience_level", "question": "Experience level — entry, mid, senior, or executive?"},
    {"field": "education_level", "question": "Education level — high school, associate, bachelor's, master's, doctorate, or certification?"},
]

# Skills categories taxonomy (42 categories across 7 tiers)
# Tiered taxonomy for industry-aware categorization
SKILL_TIERS = {
    "technology": [
        "Programming & Development", "Frameworks & Libraries", "AI/ML & Data Science",
        "Cloud & Infrastructure", "DevOps & Automation", "Databases & Data Storage",
        "Cybersecurity", "Testing & Quality Assurance", "Mobile Development",
        "Embedded Systems", "Research & Analysis", "Project & Program Management"
    ],
    "oil_gas_energy": [
        "Safety & Risk Management", "Environmental & Sustainability", "Heavy Equipment Operation",
        "Welding & Metalwork", "Electrical Systems", "Machining & Manufacturing",
        "Quality Control & Inspection", "Project & Program Management", "Research & Analysis"
    ],
    "healthcare": [
        "Healthcare & Medical", "Research & Analysis", "Safety & Risk Management",
        "Administrative & Operations", "Customer Service & Hospitality", "Education & Training"
    ],
    "finance": [
        "Financial & Accounting", "Research & Analysis", "Legal & Compliance",
        "Administrative & Operations", "Project & Program Management", "Cybersecurity"
    ],
    "creative": [
        "Design & Visual Arts", "Writing & Content", "Media & Broadcasting",
        "Music & Performing Arts", "Marketing & Communications", "Customer Service & Hospitality"
    ],
    "trades": [
        "Welding & Metalwork", "Electrical Systems", "Plumbing & Pipefitting",
        "HVAC & Refrigeration", "Carpentry & Woodworking", "Masonry & Concrete",
        "Heavy Equipment Operation", "Machining & Manufacturing", "Automotive & Mechanical",
        "Agriculture & Landscaping"
    ],
    "general": [
        "Project & Program Management", "Sales & Business Development", "Marketing & Communications",
        "HR & Talent Management", "Customer Service & Hospitality", "Education & Training",
        "Administrative & Operations"
    ]
}

# Flatten all unique categories
SKILL_CATEGORIES = []
seen = set()
for tier in SKILL_TIERS.values():
    for cat in tier:
        if cat not in seen:
            SKILL_CATEGORIES.append(cat)
            seen.add(cat)

EXPERIENCE_FIELDS = [
    {"field": "company", "question": "What company did you work at?"},
    {"field": "title", "question": "What was your title there?"},
    {"field": "dates", "question": "When did you work there? Say '2020 to 2022'"},
    {"field": "location", "question": "Where was this job? City, state, or remote."},
]

PROJECT_FIELDS = [
    {"field": "name", "question": "Project name? (e.g., 'AI Resume Builder')"},
    {"field": "tech", "question": "Tech stack? Say 'Python, FastAPI, Stripe | 2025'"},
    {"field": "description", "question": "What did you build or accomplish?"},
    {"field": "result", "question": "What was the outcome or result?"},
]

COMPETENCY_FIELDS = [
    {"field": "label", "question": "Competency name? (e.g., 'Operational Leadership')"},
    {"field": "description", "question": "Describe this competency briefly."},
]

SUMMARY_QUESTIONS = [
    {"field": "summary_q1", "question": "What's your core edge? Why hire YOU?"},
    {"field": "summary_q2", "question": "What business problems do you solve?"},
    {"field": "summary_q3", "question": "Any hard numbers? Headcount, revenue, uptime?"},
    {"field": "summary_q4", "question": "Keywords from the job posting? Say 'none' if you don't have any."},
]

# =============================================================================
# SKILL CATEGORIZATION
# =============================================================================

def get_relevant_tiers(industry: str, summary_q4: str = "") -> List[str]:
    """Return prioritized category list based on industry and keywords."""
    industry_lower = industry.lower()
    if any(x in industry_lower for x in ["tech", "software", "ai", "data", "it", "comput"]):
        primary = "technology"
    elif any(x in industry_lower for x in ["oil", "gas", "energy", "drill", "mining", "petro"]):
        primary = "oil_gas_energy"
    elif any(x in industry_lower for x in ["health", "medical", "clinical", "patient", "care"]):
        primary = "healthcare"
    elif any(x in industry_lower for x in ["finance", "bank", "invest", "account", "fintech"]):
        primary = "finance"
    elif any(x in industry_lower for x in ["creative", "design", "media", "art", "studio", "market"]):
        primary = "creative"
    elif any(x in industry_lower for x in ["trade", "construc", "manufact", "mechanic", "weld"]):
        primary = "trades"
    else:
        primary = "general"
    
    keywords = summary_q4.lower()
    secondary = None
    if any(x in keywords for x in ["mlops", "llm", "ai", "inference", "cloud", "docker", "kubernet", "python"]):
        secondary = "technology"
    elif any(x in keywords for x in ["safety", "rig", "drill", "mud", "fluids", "petro"]):
        secondary = "oil_gas_energy"
    elif any(x in keywords for x in ["health", "clinical", "patient", "care"]):
        secondary = "healthcare"
    elif any(x in keywords for x in ["finance", "account", "audit", "invest"]):
        secondary = "finance"
    
    ordered = []
    if primary in SKILL_TIERS:
        ordered.extend(SKILL_TIERS[primary])
    if secondary and secondary in SKILL_TIERS and secondary != primary:
        ordered.extend(SKILL_TIERS[secondary])
    for tier_name, tier_cats in SKILL_TIERS.items():
        if tier_name not in [primary, secondary]:
            for cat in tier_cats:
                if cat not in ordered:
                    ordered.append(cat)
    return ordered

# =============================================================================
# STATE MACHINE
# =============================================================================

def get_current_state(session: dict) -> dict:
    """Determine exactly where we are in the flow and what question to ask."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    
    phase = ctx.get("phase", "simple")
    
    # DIAGNOSTIC: Print full state when in optional/community phase
    if phase == "optional":
        section = ctx.get("opt_section", "unknown")
        opt_idx = ctx.get("opt_idx", 0)
        opt_field_idx = ctx.get("opt_field_idx", 0)
        print(f"[STATE MACHINE FATAL] phase={phase} | section={section} | opt_idx={opt_idx} | opt_field_idx={opt_field_idx}")
    
    # Phase 1: Simple fields
    if phase == "simple":
        idx = session.get("step_index", 0)
        if idx < len(SIMPLE_STEPS):
            return {"type": "question", **SIMPLE_STEPS[idx]}
        # Transition to experience
        ctx["phase"] = "experience"
        ctx["exp_idx"] = 0  # current job index
        ctx["exp_field_idx"] = 0  # current field within job
        ctx["experience"] = []
        session["context"] = ctx
        return get_current_state(session)
    
    # Phase 2: Experience (jobs)
    if phase == "experience":
        exp_list = ctx.get("experience", [])
        job_idx = ctx.get("exp_idx", 0)
        field_idx = ctx.get("exp_field_idx", 0)
        
        # Ensure current job exists
        while len(exp_list) <= job_idx:
            exp_list.append({})
        ctx["experience"] = exp_list
        
        # Still collecting fields for current job
        if field_idx < len(EXPERIENCE_FIELDS):
            step = EXPERIENCE_FIELDS[field_idx].copy()
            step["context_label"] = f"Job {job_idx + 1}"
            return {"type": "question", **step}
        
        # Done with fields, ask for bullets
        if not ctx.get("in_bullet_loop", False) and not ctx.get("exp_done", False):
            ctx["in_bullet_loop"] = True
            ctx["bullet_count"] = 0
            return {
                "type": "question",
                "field": "_bullet",
                "question": f"What did you do at {exp_list[job_idx].get('company', 'this job')}? Say bullet 1.",
                "context_label": f"Job {job_idx + 1}",
                "show_add_job": True
            }
        
        # In bullet loop - ask for next bullet or decision
        bullet_count = ctx.get("bullet_count", 0)
        awaiting_more = ctx.get("awaiting_more_bullets", False)
        exp_done = ctx.get("exp_done", False)
        
        # If exp_done is set, we're at the "add another job?" decision
        if exp_done:
            return {
                "type": "decision",
                "field": "_add_job",
                "question": "Add another job? Say yes or done.",
                "context_label": f"Job {job_idx + 1}",
            }
        
        if not awaiting_more and bullet_count == 0:
            # First bullet just collected - ask if they want more
            return {
                "type": "decision",
                "field": "_more_bullets",
                "question": f"Got it. Add another bullet? Say yes or done.",
                "context_label": f"Job {job_idx + 1}",
                "show_add_job": True
            }
        
        # After user said yes to more bullets, or after subsequent bullets
        if awaiting_more:
            # User said they want more bullets - ask for the next bullet
            ctx["awaiting_more_bullets"] = False
            session["context"] = ctx
            return {
                "type": "question",
                "field": "_bullet",
                "question": f"What else did you do at {exp_list[job_idx].get('company', 'this job')}? Say bullet {bullet_count + 1}.",
                "context_label": f"Job {job_idx + 1}",
                "show_add_job": True
            }
        
        # bullet_count > 0 means we've collected 2+ bullets - ask to add another job
        return {
            "type": "decision",
            "field": "_add_job",
            "question": "Add another job? Say yes or done.",
            "context_label": f"Job {job_idx + 1}",
        }
    
    # Phase 3: Summary interview
    if phase == "summary":
        q_idx = ctx.get("summary_idx", 0)
        if q_idx < len(SUMMARY_QUESTIONS):
            step = SUMMARY_QUESTIONS[q_idx].copy()
            step["context_label"] = f"Summary {q_idx + 1}/{len(SUMMARY_QUESTIONS)}"
            return {"type": "question", **step}
        
        # After all questions answered, summary should have been generated in _process_summary
        # If we reach here without a summary, generate it now
        if not data.get("summary"):
            # This shouldn't happen normally, but handle it gracefully
            ctx["phase"] = "skills"
            session["context"] = ctx
            return get_current_state(session)
        
        # Move to skills
        ctx["phase"] = "skills"
        session["context"] = ctx
        return get_current_state(session)
    
    # Phase 4: Skills
    if phase == "skills":
        if not data.get("skills"):
            return {
                "type": "question",
                "field": "skills",
                "question": "What skills do you have? List them all — 'Python, AI infrastructure, Discord bots...'"
            }
        
        # Move to optional sections
        ctx["phase"] = "optional"
        ctx["opt_section"] = "projects"
        ctx["opt_idx"] = 0
        ctx["opt_field_idx"] = 0
        session["context"] = ctx
        return get_current_state(session)
    
    # Phase 5: Optional sections (projects, competencies, community, certs, links)
    if phase == "optional":
        section = ctx.get("opt_section", "projects")
        print(f"[STATE MACHINE FATAL] optional section={section}, opt_idx={ctx.get('opt_idx', 0)}, opt_field_idx={ctx.get('opt_field_idx', 0)}")
        
        if section == "projects":
            return _handle_optional_section(session, "projects", PROJECT_FIELDS, "Project")
        elif section == "competencies":
            return _handle_optional_section(session, "competencies", COMPETENCY_FIELDS, "Competency")
        elif section == "education":
            return _handle_optional_section(session, "education", [
                {"field": "school", "question": "School name?"},
                {"field": "location", "question": "City and state?"},
                {"field": "degree", "question": "Degree earned?"},
                {"field": "honors", "question": "Honors or awards? Say skip if none."},
            ], "Education")
        elif section == "community":
            return _handle_optional_section(session, "community", [
                {"field": "org", "question": "Organization or event?"},
                {"field": "description", "question": "What was your involvement?"},
            ], "Community")
        elif section == "certifications":
            return _handle_optional_section(session, "certifications", [
                {"field": "name", "question": "Certification name?"},
                {"field": "issuer", "question": "Issuing organization?"},
                {"field": "date", "question": "Year earned? Say skip if none."},
            ], "Cert")
        elif section == "references":
            return _handle_optional_section(session, "references", [
                {"field": "name", "question": "Reference name?"},
                {"field": "phone", "question": "Phone number?"},
            ], "Reference")
        elif section == "links":
            link_idx = ctx.get("link_idx", 0)
            if link_idx == 0:
                return {"type": "question", "field": "website", "question": "Website or portfolio? Say 'skip'.", "context_label": "Links"}
            elif link_idx == 1:
                return {"type": "question", "field": "linkedin", "question": "LinkedIn URL? Say 'skip'.", "context_label": "Links"}
            else:
                ctx["phase"] = "done"
                session["context"] = ctx
                return get_current_state(session)
        else:
            ctx["phase"] = "done"
            session["context"] = ctx
            return get_current_state(session)
    
    # Phase 6: Done
    if phase == "done":
        return {
            "type": "done",
            "field": "done",
            "question": "Your resume is ready! Click 'View Resume' below.",
            "done": True
        }
    
    # Fallback
    return {"type": "question", "field": "done", "question": "Your resume is ready!", "done": True}


def _handle_optional_section(session, section_name, fields, label):
    """Handle any optional repeatable section."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    
    item_list = ctx.get(section_name, [])
    item_idx = ctx.get("opt_idx", 0)
    field_idx = ctx.get("opt_field_idx", 0)
    
    # Ensure current item exists
    while len(item_list) <= item_idx:
        item_list.append({})
    ctx[section_name] = item_list
    
    # Still collecting fields
    if field_idx < len(fields):
        step = fields[field_idx].copy()
        step["context_label"] = f"{label} {item_idx + 1}"
        step["show_add_job"] = True  # Allow adding more items
        return {"type": "question", **step}
    
    # Done with this item, ask to add another (decision prompt)
    # CRITICAL: Preserve phase="optional" here — user must explicitly answer "no"
    # to this decision prompt before _advance_optional_section() can ever be called.
    return {
        "type": "decision",
        "field": f"_add_{section_name}",
        "question": f"{label} saved. Add another? Say yes or skip.",
        "context_label": f"{label}s",
        "show_add_job": True
    }


async def process_answer(session: dict, transcript: str) -> dict:
    """Process user answer and advance state. Returns the next step."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    phase = ctx.get("phase", "simple")
    extracted = transcript.strip()
    
    # Handle skip/none for optional things
    lower = extracted.lower()
    
    # === INTERCEPT: Global decision-word sanitization ===
    # If user sends a control word at ANY decision point, do NOT store it as data.
    # Decision fields start with underscore: _more_bullets, _add_job, _add_projects, etc.
    current_field = ctx.get("field", "")
    if isinstance(current_field, str) and current_field.startswith("_") and lower in ("yes", "done", "no", "skip", "next"):
        print(f"[INTERCEPT] Blocked control word '{lower}' from being stored at decision field '{current_field}'")
        # Return next state WITHOUT storing the control word as data
        return get_current_state(session)
    # === END INTERCEPT ===
    
    # GLOBAL SAFETY CHECK: If user says "done" in experience phase past field collection,
    # force bullet loop exit regardless of internal flags
    if phase == "experience":
        field_idx = ctx.get("exp_field_idx", 0)
        if lower in ["done", "no", "stop", "finished"] and field_idx >= len(EXPERIENCE_FIELDS):
            # Force exit bullet loop and mark job as done
            ctx["in_bullet_loop"] = False
            ctx["exp_done"] = True
            ctx["bullet_count"] = 0
            ctx["awaiting_more_bullets"] = False
            session["context"] = ctx
            _persist_session(session.get("session_id"))
            print(f"[GLOBAL SAFETY] Forced bullet loop exit for '{lower}'")
            return get_current_state(session)
    
    # Phase 1: Simple fields
    if phase == "simple":
        idx = session.get("step_index", 0)
        if idx < len(SIMPLE_STEPS):
            field = SIMPLE_STEPS[idx]["field"]
            data[field] = extracted
            session["data"] = data
            session["step_index"] = idx + 1
        return get_current_state(session)
    
    # Phase 2: Experience
    if phase == "experience":
        return _process_experience(session, extracted)
    
    # Phase 3: Summary
    if phase == "summary":
        return await _process_summary(session, extracted)
    
    # Phase 4: Skills
    if phase == "skills":
        # Filter out control words that leaked from previous bullet loops
        if lower in ["skip", "none", "n/a", "yes", "done", "next"]:
            data["skills"] = ""
        else:
            data["skills"] = extracted
        session["data"] = data
        
        # Categorize skills with Groq
        skills_text = data.get("skills", "")
        if skills_text:
            try:
                categorized = await groq_categorize_skills(skills_text, session)
                data["skills_categorized"] = categorized
                session["data"] = data
            except Exception as e:
                print(f"[Skills Categorize Error] {e}")
        
        # Move to optional sections after skills
        ctx["phase"] = "optional"
        ctx["opt_section"] = "projects"
        ctx["opt_idx"] = 0
        ctx["opt_field_idx"] = 0
        session["context"] = ctx
        return get_current_state(session)
    
    # Phase 5: Optional sections
    if phase == "optional":
        return _process_optional(session, extracted)
    
    return get_current_state(session)


def _process_experience(session: dict, extracted: str) -> dict:
    """Process experience phase answers."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    lower = extracted.lower()
    
    exp_list = ctx.get("experience", [])
    job_idx = ctx.get("exp_idx", 0)
    field_idx = ctx.get("exp_field_idx", 0)
    
    print(f"DEBUG _process_experience: extracted='{extracted}', field_idx={field_idx}, in_bullet_loop={ctx.get('in_bullet_loop', False)}, exp_done={ctx.get('exp_done', False)}, bullet_count={ctx.get('bullet_count', 0)}")
    
    # Ensure current job exists
    while len(exp_list) <= job_idx:
        exp_list.append({})
    
    # 1. Force absolute sanitation of the incoming control command
    sanitized_text = str(extracted).strip().lower()
    
    # 2. Add explicit debug hooks to isolate the exact evaluation failure
    print(f"[STATE DB DEBUG] Input: '{sanitized_text}' | field_idx: {field_idx} | in_bullet_loop: {ctx.get('in_bullet_loop', False)} | exp_done: {ctx.get('exp_done', False)}")
    
    # 3. Hard stop: if user sends "done" at ANY point in experience phase,
    # force exit immediately and do NOT let it leak into field or bullet storage.
    if sanitized_text in ["done", "no", "stop", "finished"]:
        print(f"[STATE DB DEBUG] MATCHED BREAK LOOP COMMAND. Forcing state mutation and early return.")
        # If still collecting fields, fast-forward past them
        if field_idx < len(EXPERIENCE_FIELDS):
            print(f"[STATE DB DEBUG] Fast-forwarding fields from {field_idx} to {len(EXPERIENCE_FIELDS)}")
            ctx["exp_field_idx"] = len(EXPERIENCE_FIELDS)
        ctx["in_bullet_loop"] = False
        ctx["exp_done"] = True
        ctx["bullet_count"] = 0
        ctx["awaiting_more_bullets"] = False
        session["context"] = ctx
        # Commit changes to disk/session cache immediately
        _persist_session(session.get("session_id"))
        # EARLY RETURN: Stop processing to prevent "done" from leaking into field values!
        return get_current_state(session)
    
    # Still collecting standard fields
    if field_idx < len(EXPERIENCE_FIELDS):
        field_name = EXPERIENCE_FIELDS[field_idx]["field"]
        exp_list[job_idx][field_name] = extracted
        ctx["exp_field_idx"] = field_idx + 1
        ctx["experience"] = exp_list
        session["context"] = ctx
        print(f"DEBUG: Stored field {field_name}={extracted}, new field_idx={field_idx+1}")
        return get_current_state(session)
    
    # In bullet collection mode
    print(f"DEBUG: Checking first bullet branch: not in_bullet_loop={not ctx.get('in_bullet_loop', False)}, not exp_done={not ctx.get('exp_done', False)}")
    if not ctx.get("in_bullet_loop", False) and not ctx.get("exp_done", False):
        # First bullet - initialize bullet loop state properly
        ctx["in_bullet_loop"] = True
        ctx["bullet_count"] = 0
        ctx["exp_done"] = False  # Ensure exp_done is reset for this job
        if not exp_list[job_idx].get("description"):
            exp_list[job_idx]["description"] = []
        if not exp_list[job_idx].get("bullets"):
            exp_list[job_idx]["bullets"] = []
        # Store the first bullet
        if isinstance(exp_list[job_idx]["description"], list):
            exp_list[job_idx]["description"].append(extracted)
        else:
            exp_list[job_idx]["description"] = [exp_list[job_idx]["description"], extracted]
        exp_list[job_idx]["bullets"].append(extracted)
        ctx["bullet_count"] = 1
        ctx["experience"] = exp_list
        session["context"] = ctx
        print(f"DEBUG: First bullet stored, bullet_count=1")
        return get_current_state(session)
    
    bullet_count = ctx.get("bullet_count", 0)
    
    # Handle "Add another job?" decision
    print(f"DEBUG: Checking exp_done branch: exp_done={ctx.get('exp_done', False)}")
    if ctx.get("exp_done", False):
        print(f"DEBUG: In exp_done branch, lower='{lower}'")
        if lower in ["yes", "y", "add", "more"]:
            # Start new job
            ctx["exp_done"] = False
            ctx["exp_idx"] = job_idx + 1
            ctx["exp_field_idx"] = 0
            ctx["in_bullet_loop"] = False
            ctx["bullet_count"] = 0
            ctx["awaiting_more_bullets"] = False
            session["context"] = ctx
            return get_current_state(session)
        else:
            # Done with experience, move to summary
            data["experience"] = exp_list
            session["data"] = data
            ctx["phase"] = "summary"
            ctx["summary_idx"] = 0
            # CRITICAL FIX: Clear all experience flags to prevent state leakage into summary
            ctx["exp_done"] = False
            ctx["in_bullet_loop"] = False
            ctx["bullet_count"] = 0
            ctx["awaiting_more_bullets"] = False
            session["context"] = ctx
            return get_current_state(session)
    
    # Check if user wants more bullets (after decision prompt)
    print(f"DEBUG: Checking 'yes' branch: lower='{lower}'")
    if lower in ["yes", "y", "add", "more"]:
        # User wants to add another bullet - set flag and return bullet prompt
        ctx["awaiting_more_bullets"] = True
        session["context"] = ctx
        return get_current_state(session)
    
    # Check if user is done with bullets
    print(f"DEBUG: Checking 'done' branch: lower='{lower}', in list={lower in ['done', 'no', 'n', 'finished', 'next', 'skip']}")
    if lower in ["done", "no", "n", "finished", "next", "skip"]:
        # Move to "add another job?" decision
        ctx["in_bullet_loop"] = False
        ctx["bullet_count"] = 0
        ctx["awaiting_more_bullets"] = False
        ctx["exp_done"] = True  # Mark that we're done with this job's bullets
        session["context"] = ctx
        print(f"DEBUG: Set exp_done=True, in_bullet_loop=False")
        return get_current_state(session)
    
    # User provided another bullet
    print(f"DEBUG: Storing as bullet")
    if "description" not in exp_list[job_idx]:
        exp_list[job_idx]["description"] = []
    if "bullets" not in exp_list[job_idx]:
        exp_list[job_idx]["bullets"] = []
    if isinstance(exp_list[job_idx]["description"], list):
        exp_list[job_idx]["description"].append(extracted)
    else:
        exp_list[job_idx]["description"] = [exp_list[job_idx]["description"], extracted]
    exp_list[job_idx]["bullets"].append(extracted)
    
    ctx["bullet_count"] = bullet_count + 1
    ctx["experience"] = exp_list
    session["context"] = ctx
    
    print(f"DEBUG: Bullet stored, bullet_count={bullet_count+1}")
    # After collecting a bullet, ask if they want more
    return {
        "type": "decision",
        "field": "_more_bullets",
        "question": f"Bullet saved. Add another? Say yes or done.",
        "context_label": f"Job {job_idx + 1}",
        "show_add_job": True
    }


async def _process_summary(session: dict, extracted: str) -> dict:
    """Process summary interview answers."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    lower = extracted.lower()
    
    q_idx = ctx.get("summary_idx", 0)
    
    # Use dedicated summary dict to avoid data pollution
    if "summary_answers" not in ctx:
        ctx["summary_answers"] = {}
    summary_answers = ctx["summary_answers"]
    
    if q_idx < len(SUMMARY_QUESTIONS):
        field = SUMMARY_QUESTIONS[q_idx]["field"]
        summary_answers[field] = extracted
        ctx["summary_answers"] = summary_answers
        ctx["summary_idx"] = q_idx + 1
        session["context"] = ctx
        
        # Check if this was the LAST question - generate summary immediately
        if q_idx + 1 >= len(SUMMARY_QUESTIONS):
            # Generate summary before transitioning to skills
            summary = await generate_summary_with_groq(session)
            data["summary"] = summary
            
            # Store keywords separately
            if "summary_q4" in summary_answers:
                data["keywords"] = summary_answers["summary_q4"]
            
            session["data"] = data
            ctx["phase"] = "skills"
            session["context"] = ctx
        
        return get_current_state(session)
    
    # Fallback: should not reach here normally
    summary = await generate_summary_with_groq(session)
    data["summary"] = summary
    
    # Store keywords separately
    if "summary_q4" in summary_answers:
        data["keywords"] = summary_answers["summary_q4"]
    
    session["data"] = data
    ctx["phase"] = "skills"
    session["context"] = ctx
    return get_current_state(session)


def _process_optional(session: dict, extracted: str) -> dict:
    """Process optional section answers."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    lower = extracted.lower()
    
    section = ctx.get("opt_section", "projects")
    item_idx = ctx.get("opt_idx", 0)
    field_idx = ctx.get("opt_field_idx", 0)
    
    print(f"[OPTIONAL DEBUG] section={section}, item_idx={item_idx}, field_idx={field_idx}, extracted='{extracted}'")
    print(f"[OPTIONAL DEBUG] BEFORE: opt_idx={ctx.get('opt_idx')}, opt_field_idx={ctx.get('opt_field_idx')}")
    
    item_list = ctx.get(section, [])
    while len(item_list) <= item_idx:
        item_list.append({})
    
    fields = {
        "projects": PROJECT_FIELDS,
        "competencies": COMPETENCY_FIELDS,
        "education": [
            {"field": "school", "question": "School name?"},
            {"field": "location", "question": "City and state?"},
            {"field": "degree", "question": "Degree earned?"},
            {"field": "honors", "question": "Honors or awards? Say skip if none."},
        ],
        "community": [
            {"field": "org", "question": "Organization or event?"},
            {"field": "description", "question": "What was your involvement?"},
        ],
        "certifications": [
            {"field": "name", "question": "Certification name?"},
            {"field": "issuer", "question": "Issuing organization?"},
            {"field": "date", "question": "Year earned? Say skip if none."},
        ],
        "references": [
            {"field": "name", "question": "Reference name?"},
            {"field": "phone", "question": "Phone number?"},
        ],
    }.get(section, [])
    
    # Decision to add more items (field_idx >= len(fields) means we're at decision point)
    if field_idx >= len(fields):
        print(f"[OPTIONAL DEBUG] DECISION POINT: lower='{lower}', item_idx={item_idx}")
        if lower in ["yes", "y", "add", "more"]:
            # Add another item - reset field index for new item
            print(f"[OPTIONAL DEBUG] Adding another item: opt_idx={item_idx + 1}, opt_field_idx=0")
            ctx["opt_idx"] = item_idx + 1
            ctx["opt_field_idx"] = 0
            session["context"] = ctx
            return get_current_state(session)
        elif lower in ["next", "done", "skip", "no"]:
            # Done with this section - save data and move to next
            print(f"[OPTIONAL DEBUG] Done with section {section}, advancing to next")
            # Filter out empty dicts before saving AND strip control words
            CONTROL_WORDS = {"yes", "skip", "done", "next", "no", "add", "more", "stop", "finished"}
            filtered_items = []
            for item in item_list:
                if not item or not isinstance(item, dict):
                    continue
                # Strip control words from all fields
                cleaned_item = {}
                has_real_data = False
                for k, v in item.items():
                    if isinstance(v, str) and v.strip().lower() in CONTROL_WORDS:
                        cleaned_item[k] = ""
                    else:
                        cleaned_item[k] = v
                        if v:  # truthy non-empty value
                            has_real_data = True
                if has_real_data:
                    filtered_items.append(cleaned_item)
            if filtered_items:
                data[section] = filtered_items
                session["data"] = data
            _advance_optional_section(session)
            return get_current_state(session)
        else:
            # Unrecognized input - REPEAT the decision prompt (stay in phase="optional")
            print(f"[OPTIONAL DEBUG] Unrecognized '{lower}', staying in section {section}")
            # Do NOT advance section; re-ask the same decision
            ctx["opt_field_idx"] = field_idx  # stay at decision boundary
            session["context"] = ctx
            return get_current_state(session)
    
    # First field of first item - check skip
    if item_idx == 0 and field_idx == 0:
        if lower in ["skip", "none", "n/a", "no", "next"]:
            # Skip this entire section - remove the empty item we may have created
            if item_list and not any(item_list[-1].values() if isinstance(item_list[-1], dict) else True):
                item_list.pop()
            ctx[section] = item_list
            session["context"] = ctx
            # Skip this entire section
            _advance_optional_section(session)
            return get_current_state(session)
    
    # Collecting field data
    field_name = fields[field_idx]["field"]
    # SANITIZE: strip control words from non-decision fields
    CONTROL_WORDS = {"yes", "done", "no", "skip", "next", "add", "more", "stop", "finished"}
    if lower in CONTROL_WORDS:
        stored_value = ""
        print(f"[SANITIZE] Stripped control word '{lower}' from {section}.{field_name}")
    else:
        stored_value = extracted
    item_list[item_idx][field_name] = stored_value
    ctx[section] = item_list
    ctx["opt_field_idx"] = field_idx + 1
    session["context"] = ctx
    print(f"[OPTIONAL DEBUG] AFTER STORE: opt_idx={ctx.get('opt_idx')}, opt_field_idx={ctx.get('opt_field_idx')}, field={field_name}")
    return get_current_state(session)


def _advance_optional_section(session: dict):
    """Move to next optional section."""
    ctx = session.get("context", {})
    sections = ["projects", "competencies", "education", "community", "certifications", "references", "links", "done"]
    current = ctx.get("opt_section", "projects")
    
    try:
        idx = sections.index(current)
        next_section = sections[idx + 1] if idx + 1 < len(sections) else "done"
    except ValueError:
        next_section = "done"
    
    ctx["opt_section"] = next_section
    ctx["opt_idx"] = 0
    ctx["opt_field_idx"] = 0
    # Clear any leftover flags from previous sections
    for flag in ["awaiting_more_bullets", "exp_done", "in_bullet_loop"]:
        ctx.pop(flag, None)
    session["context"] = ctx


def go_back(session: dict) -> dict:
    """Go back one logical step."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    phase = ctx.get("phase", "simple")
    
    # Simple fields
    if phase == "simple":
        idx = session.get("step_index", 0)
        if idx > 0:
            session["step_index"] = idx - 1
            field = SIMPLE_STEPS[idx - 1]["field"]
            if field in data:
                del data[field]
            session["data"] = data
        return get_current_state(session)
    
    # Experience
    if phase == "experience":
        return _go_back_experience(session)
    
    # Summary
    if phase == "summary":
        q_idx = ctx.get("summary_idx", 0)
        if q_idx > 0:
            ctx["summary_idx"] = q_idx - 1
            field = SUMMARY_QUESTIONS[q_idx - 1]["field"]
            if field in data:
                del data[field]
            session["context"] = ctx
            session["data"] = data
        else:
            # Back to experience
            ctx["phase"] = "experience"
            session["context"] = ctx
        return get_current_state(session)
    
    # Skills
    if phase == "skills":
        if "skills" in data:
            del data["skills"]
            session["data"] = data
        ctx["phase"] = "summary"
        ctx["summary_idx"] = len(SUMMARY_QUESTIONS)
        session["context"] = ctx
        return get_current_state(session)
    
    # Optional sections
    if phase == "optional":
        return _go_back_optional(session)
    
    # Done - go back to links
    if phase == "done":
        ctx["phase"] = "optional"
        ctx["opt_section"] = "links"
        ctx["link_idx"] = 2
        session["context"] = ctx
        return get_current_state(session)
    
    return get_current_state(session)


def _go_back_experience(session: dict) -> dict:
    """Go back within experience phase."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    
    exp_list = ctx.get("experience", [])
    job_idx = ctx.get("exp_idx", 0)
    field_idx = ctx.get("exp_field_idx", 0)
    in_bullet = ctx.get("in_bullet_loop", False)
    
    # In bullet loop
    if in_bullet:
        bullets = exp_list[job_idx].get("description", [])
        if isinstance(bullets, list) and len(bullets) > 0:
            # Remove last bullet
            bullets.pop()
            if not bullets:
                exp_list[job_idx].pop("description", None)
                ctx["in_bullet_loop"] = False
                ctx["bullet_count"] = 0
                # Back to last standard field
                ctx["exp_field_idx"] = len(EXPERIENCE_FIELDS) - 1
                field = EXPERIENCE_FIELDS[-1]["field"]
                if field in exp_list[job_idx]:
                    del exp_list[job_idx][field]
            else:
                ctx["bullet_count"] = len(bullets)
        else:
            ctx["in_bullet_loop"] = False
            ctx["bullet_count"] = 0
            ctx["exp_field_idx"] = len(EXPERIENCE_FIELDS) - 1
        
        ctx["experience"] = exp_list
        session["context"] = ctx
        return get_current_state(session)
    
    # In standard fields
    if field_idx > 0:
        ctx["exp_field_idx"] = field_idx - 1
        field = EXPERIENCE_FIELDS[field_idx - 1]["field"]
        if exp_list and job_idx < len(exp_list) and field in exp_list[job_idx]:
            del exp_list[job_idx][field]
        ctx["experience"] = exp_list
        session["context"] = ctx
        return get_current_state(session)
    
    # At first field of a job
    if job_idx > 0:
        # Go back to previous job's bullets
        ctx["exp_idx"] = job_idx - 1
        ctx["exp_field_idx"] = len(EXPERIENCE_FIELDS)
        ctx["in_bullet_loop"] = True
        prev_bullets = exp_list[job_idx - 1].get("description", [])
        ctx["bullet_count"] = len(prev_bullets) if isinstance(prev_bullets, list) else 1
        session["context"] = ctx
        return get_current_state(session)
    
    # At first job, first field - go back to simple steps
    ctx["phase"] = "simple"
    session["step_index"] = len(SIMPLE_STEPS) - 1
    session["context"] = ctx
    return get_current_state(session)


def _go_back_optional(session: dict) -> dict:
    """Go back within optional sections."""
    ctx = session.get("context", {})
    
    section = ctx.get("opt_section", "projects")
    item_idx = ctx.get("opt_idx", 0)
    field_idx = ctx.get("opt_field_idx", 0)
    
    item_list = ctx.get(section, [])
    
    fields = {
        "projects": PROJECT_FIELDS,
        "competencies": COMPETENCY_FIELDS,
        "community": [{"field": "org"}],
        "certifications": [{"field": "name"}],
    }.get(section, [])
    
    # In field collection
    if field_idx > 0:
        ctx["opt_field_idx"] = field_idx - 1
        field = fields[field_idx - 1]["field"]
        if item_list and item_idx < len(item_list) and field in item_list[item_idx]:
            del item_list[item_idx][field]
        session["context"] = ctx
        return get_current_state(session)
    
    # At first field of an item
    if item_idx > 0:
        ctx["opt_idx"] = item_idx - 1
        ctx["opt_field_idx"] = len(fields) - 1
        session["context"] = ctx
        return get_current_state(session)
    
    # At first item of a section - go back to previous section
    sections = ["projects", "competencies", "education", "community", "certifications", "references"]
    try:
        idx = sections.index(section)
        if idx > 0:
            prev_section = sections[idx - 1]
            ctx["opt_section"] = prev_section
            prev_list = ctx.get(prev_section, [])
            ctx["opt_idx"] = len(prev_list) - 1 if prev_list else 0
            ctx["opt_field_idx"] = 0  # Will be at decision point
        else:
            # Back to skills
            ctx["phase"] = "skills"
            if "skills" in session.get("data", {}):
                del session["data"]["skills"]
    except ValueError:
        ctx["phase"] = "skills"
    
    session["context"] = ctx
    return get_current_state(session)


# =============================================================================
# GROQ SKILL CATEGORIZATION
# =============================================================================

async def groq_categorize_skills(skills_text: str, session: dict = None) -> Dict[str, List[Dict]]:
    """Send skills to Groq and get categorized JSON with weights back."""
    if not GROQ_API_KEY:
        # Fallback: put all skills in "Other Skills" with neutral weight
        skills_list = [s.strip() for s in skills_text.split(",") if s.strip()]
        return {"Other Skills": [{"name": s, "weight": 50} for s in skills_list]}
    
    # Get career context from session if available
    data = session.get("data", {}) if session else {}
    job_title = data.get("job_title", "")
    industry = data.get("industry", "")
    target_keywords = data.get("summary_q4", "")
    core_edge = data.get("summary_q1", "")
    
    # Get prioritized category list based on industry + keywords
    prioritized_cats = get_relevant_tiers(industry, target_keywords)
    # Send top 15 categories first (reduce noise for Groq)
    primary_cats = prioritized_cats[:15]
    categories_text = ", ".join(primary_cats)
    
    prompt = f"""You are a resume skill organizer with expertise in career alignment.

JOB CONTEXT:
- Target Role: {job_title}
- Industry: {industry}
- User's Core Edge: {core_edge}
- Target Keywords from Job Posting: {target_keywords}

CATEGORIZE AND WEIGHT these skills (1-100):
- 90-100: Critical for the target role (matches job title and keywords directly)
- 70-89: Highly relevant (supports the core edge or industry)
- 50-69: Moderately relevant (transferable but not core)
- 30-49: Nice-to-have (adjacent skills)
- 1-29: Legacy or minimally relevant (only include if user explicitly listed them)

PRIORITIZED CATEGORIES (most relevant first):
{categories_text}

Use ONLY these categories. If a skill does not fit, put it in "Other Skills".

Return ONLY a JSON object where keys are category names and values are arrays of objects with "name" and "weight" fields.

Example output:
{{"Programming & Development": [{{"name": "Python", "weight": 95}}, {{"name": "JavaScript", "weight": 70}}], "Other Skills": [{{"name": "public speaking", "weight": 40}}]}}

User skills: {skills_text}"""
    
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a resume skill organizer. Output valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1500,
                    "response_format": {"type": "json_object"}
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                parsed = json.loads(content)
                # Remove empty categories
                return {k: v for k, v in parsed.items() if v}
    except Exception as e:
        print(f"[Groq Categorize Error] {e}")
    
    # Fallback
    skills_list = [s.strip() for s in skills_text.split(",") if s.strip()]
    return {"Other Skills": [{"name": s, "weight": 50} for s in skills_list]}


async def generate_summary_with_groq(session: dict) -> str:
    """Generate professional summary from summary_answers using Groq."""
    ctx = session.get("context", {})
    data = session.get("data", {})
    summary_answers = ctx.get("summary_answers", {})
    
    if not summary_answers.get("summary_q1") and not summary_answers.get("summary_q2"):
        return "Experienced professional with proven track record."
    
    q1 = summary_answers.get("summary_q1", "")
    q2 = summary_answers.get("summary_q2", "")
    q3 = summary_answers.get("summary_q3", "")
    q4 = summary_answers.get("summary_q4", "")
    job_title = data.get("job_title", "")
    
    if not GROQ_API_KEY:
        # Fallback: concatenate answers
        return f"{q1} {q2} {q3}".strip()
    
    prompt = f"""Write a 2-3 sentence professional summary for a resume.

TARGET ROLE: {job_title}

USER INPUTS:
- Core edge / why hire them: {q1}
- Business problems they solve: {q2}
- Hard numbers / achievements: {q3}
- Keywords from job posting: {q4}

Write a concise, compelling professional summary that incorporates the keywords and targets the role. Use active voice. Avoid generic buzzwords. Return ONLY the summary text, no quotes or explanations."""
    
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
                        {"role": "system", "content": "You are an expert resume writer. Write concise, compelling professional summaries."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 300
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"].strip()
            else:
                print(f"[Groq Summary API Error] {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[Groq Summary Error] {e}")
    
    # Fallback
    return f"{q1} {q2} {q3}".strip()


# =============================================================================
# SANITIZATION LAYER
# =============================================================================

def sanitize_resume_data(raw_data: dict, ctx: dict) -> dict:
    """
    Sanitize and reconstruct a clean resume payload from the raw session data.
    
    Fixes known upstream corruption:
    - skills field polluted with project names / control words
    - skills_categorized truncated or missing
    - experience bullets lost in string/list mismatches
    - optional sections partially stored in ctx vs data
    
    Returns a pristine payload ready for generate_docx / generate_pdf.
    """
    import re
    
    # ── Base identity fields ──
    full_name = raw_data.get("full_name", "")
    
    # ── Location ──
    location = raw_data.get("location", "")
    if not location:
        city = raw_data.get("city", "")
        state = raw_data.get("state", "")
        if city and state:
            location = f"{city}, {state}"
        elif city:
            location = city
        elif state:
            location = state
    
    # ── Experience (primary source: ctx, fallback: raw_data) ──
    exp_list = []
    
    # Try ctx first (has the full objects with bullets)
    ctx_exp = ctx.get("experience", [])
    if ctx_exp:
        for exp in ctx_exp:
            if not isinstance(exp, dict):
                continue
            
            # Get bullets from multiple possible sources
            bullets = []
            if "bullets" in exp and isinstance(exp["bullets"], list):
                bullets = [b for b in exp["bullets"] if b and isinstance(b, str)]
            elif "description" in exp and isinstance(exp["description"], list):
                bullets = [b for b in exp["description"] if b and isinstance(b, str)]
            elif "description" in exp and isinstance(exp["description"], str):
                desc = exp["description"].strip()
                if desc:
                    bullets = [desc]
            
            # Skip empty jobs
            if not exp.get("company") and not exp.get("title") and not bullets:
                continue
            
            exp_list.append({
                "company": str(exp.get("company", "")),
                "title": str(exp.get("title", "")),
                "dates": str(exp.get("dates", "")),
                "location": str(exp.get("location", "")),
                "bullets": bullets,
                "description": bullets  # backward compat
            })
    
    # Fallback to raw_data experience
    if not exp_list and "experience" in raw_data:
        exp_data = raw_data["experience"]
        if isinstance(exp_data, str):
            try:
                exp_data = json.loads(exp_data)
            except:
                exp_data = []
        if isinstance(exp_data, list):
            for exp in exp_data:
                if isinstance(exp, dict):
                    bullets = []
                    if "bullets" in exp and isinstance(exp["bullets"], list):
                        bullets = [b for b in exp["bullets"] if b and isinstance(b, str)]
                    elif "description" in exp and isinstance(exp["description"], list):
                        bullets = [b for b in exp["description"] if b and isinstance(b, str)]
                    elif "description" in exp and isinstance(exp["description"], str):
                        desc = exp["description"].strip()
                        if desc:
                            bullets = [desc]
                    
                    if exp.get("company") or exp.get("title") or bullets:
                        exp_list.append({
                            "company": str(exp.get("company", "")),
                            "title": str(exp.get("title", "")),
                            "dates": str(exp.get("dates", "")),
                            "location": str(exp.get("location", "")),
                            "bullets": bullets,
                            "description": bullets
                        })
    
    # ── Skills sanitization ──
    # CORRUPTION DETECTION: skills field may contain project names, control words, or be truncated
    # The real skills are in skills_categorized (from Groq) or must be reconstructed
    
    skills_categorized_raw = raw_data.get("skills_categorized", {})
    skills_raw = raw_data.get("skills", "")
    
    # Known project name patterns that leaked into skills
    PROJECT_NAME_PATTERNS = [
        r"resume", r"forge", r"builder", r"voice", r"chat", r"bot",
        r"discord", r"openclaw", r"ollama", r"platform", r"infrastructure",
        r"orchestration", r"education", r"community", r"tutorial", r"documentation"
    ]
    
    # Control words that should never be in skills
    CONTROL_WORDS = {"done", "skip", "next", "yes", "no", "add", "more", "stop", "finished"}
    
    def _is_corrupted_skills(skills_text: str) -> bool:
        """Detect if skills field contains project names or control words."""
        if not skills_text or not isinstance(skills_text, str):
            return True  # Empty/missing skills is corrupted
        skills_lower = skills_text.lower()
        # Check for project names
        for pattern in PROJECT_NAME_PATTERNS:
            if pattern in skills_lower:
                return True
        # Check for control words as standalone words
        words = set(re.findall(r'\b\w+\b', skills_lower))
        if words & CONTROL_WORDS:
            return True
        # If skills is very short (under 20 chars), likely corrupted/truncated
        if len(skills_text.strip()) < 20:
            return True
        return False
    
    def _is_corrupted_categorized(categorized: dict) -> bool:
        """Detect if skills_categorized only contains garbage like project names in 'Other Skills'."""
        if not categorized or not isinstance(categorized, dict):
            return True
        # If the ONLY category is "Other Skills", it's likely Groq failed to categorize properly
        keys = list(categorized.keys())
        if len(keys) == 1 and keys[0].lower() in ("other skills", "other"):
            skills = categorized.get(keys[0], [])
            if not skills:
                return True
            # Check if the skills in "Other Skills" look like project names
            for s in skills:
                name = s.get("name", "") if isinstance(s, dict) else str(s)
                name_lower = name.lower()
                for pattern in PROJECT_NAME_PATTERNS:
                    if pattern in name_lower:
                        return True
                # If it's a long phrase (more than 3 words), it's likely a project description
                if len(name.split()) > 3:
                    return True
        return False
    
    def _extract_skills_from_categorized(categorized: dict) -> tuple:
        """Extract flat skill list and normalized categorized dict."""
        flat_skills = []
        normalized = {}
        if not categorized or not isinstance(categorized, dict):
            return flat_skills, normalized
        
        for cat, skills in categorized.items():
            if not skills or not isinstance(skills, list):
                continue
            norm_list = []
            for s in skills:
                if isinstance(s, str) and s.strip():
                    norm_list.append(s.strip())
                    flat_skills.append(s.strip())
                elif isinstance(s, dict) and s.get("name"):
                    name = s["name"].strip()
                    norm_list.append(name)
                    flat_skills.append(name)
            if norm_list:
                normalized[cat] = norm_list
        
        return flat_skills, normalized
    
    # ── Determine best skills source ──
    # Priority: 1) Valid skills_categorized, 2) Valid raw skills, 3) keywords/summary_q4 fallback
    
    final_skills = []
    final_skills_categorized = {}
    
    # Source 1: Try skills_categorized if it's not corrupted
    if skills_categorized_raw and isinstance(skills_categorized_raw, dict) and not _is_corrupted_categorized(skills_categorized_raw):
        cat_skills, cat_normalized = _extract_skills_from_categorized(skills_categorized_raw)
        if cat_skills:
            final_skills = cat_skills
            final_skills_categorized = cat_normalized
    
    # Source 2: Try raw skills if categorized failed or was empty
    if not final_skills:
        if isinstance(skills_raw, str):
            if not _is_corrupted_skills(skills_raw):
                # Parse comma-separated skills
                final_skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
        elif isinstance(skills_raw, list):
            final_skills = [s for s in skills_raw if s and isinstance(s, str)]
    
    # Source 3: EMERGENCY FALLBACK — keywords from summary_q4 (most reliable when upstream is corrupted)
    if not final_skills:
        keywords = raw_data.get("keywords", "") or raw_data.get("summary_q4", "")
        if keywords and isinstance(keywords, str) and not _is_corrupted_skills(keywords):
            # Parse comma-separated technical keywords
            final_skills = [s.strip() for s in keywords.split(",") if s.strip() and len(s.strip()) > 1]
    
    # Source 4: Ultimate fallback — extract individual tech keywords from summary_q4
    if not final_skills:
        keywords = raw_data.get("keywords", "") or raw_data.get("summary_q4", "")
        if keywords and isinstance(keywords, str):
            # Extract technical keywords using regex
            tech_keywords = re.findall(r'[A-Z][a-zA-Z]*(?:\.[A-Z][a-zA-Z]*)*|[a-z]+(?:\+[a-z]+)*|\d+', keywords)
            final_skills = [k for k in tech_keywords if len(k) > 1 and k.lower() not in CONTROL_WORDS]
    
    # If we had to fall back to keywords but don't have a categorized version,
    # build a simple categorized structure using the built-in categorization logic
    if final_skills and not final_skills_categorized:
        from main import categorize_skills
        try:
            final_skills_categorized = categorize_skills(final_skills)
        except Exception:
            # Fallback: put all skills in "Technical Skills"
            final_skills_categorized = {"Technical Skills": final_skills}
    
    # Deduplicate
    seen = set()
    deduped = []
    for s in final_skills:
        s_lower = s.lower()
        if s_lower not in seen:
            seen.add(s_lower)
            deduped.append(s)
    final_skills = deduped
    
    # ── Optional sections (ctx first, then raw_data) ──
    def _get_optional_section(section_name: str) -> list:
        """Get optional section data from ctx or raw_data."""
        # Try ctx first
        ctx_data = ctx.get(section_name, [])
        if ctx_data and isinstance(ctx_data, list):
            # Filter empty dicts
            filtered = []
            for item in ctx_data:
                if item and isinstance(item, dict) and any(item.values()):
                    filtered.append(item)
            if filtered:
                return filtered
        
        # Fallback to raw_data
        raw_val = raw_data.get(section_name, "")
        if isinstance(raw_val, list):
            return [item for item in raw_val if item and isinstance(item, dict) and any(item.values())]
        if isinstance(raw_val, str) and raw_val.strip():
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, list):
                    return [item for item in parsed if item and isinstance(item, dict) and any(item.values())]
                return [parsed] if parsed else []
            except:
                return []
        return []
    
    def _strip_control_words(section_items: list, field_map: dict) -> list:
        """Strip leaked control words from specific fields in optional sections.
        
        field_map: {field_name: set_of_bad_values} — any string matching a bad value
        (case-insensitive) will be replaced with an empty string.
        """
        CONTROL_VALUES = {"yes", "skip", "done", "next", "no", "add", "more"}
        cleaned = []
        for item in section_items:
            if not isinstance(item, dict):
                cleaned.append(item)
                continue
            cleaned_item = dict(item)
            for field in cleaned_item.keys():
                if field in cleaned_item:
                    val = str(cleaned_item[field]).strip()
                    if val.lower() in CONTROL_VALUES:
                        cleaned_item[field] = ""
            cleaned.append(cleaned_item)
        return cleaned
    
    projects = _get_optional_section("projects")
    # Strip "yes" from project result fields
    projects = _strip_control_words(projects, {"__all__": ["result"]})
    
    competencies = _get_optional_section("competencies")
    community = _get_optional_section("community")
    
    certifications = _get_optional_section("certifications")
    # Strip "skip" from certification date fields
    certifications = _strip_control_words(certifications, {"__all__": ["date"]})
    
    # Education special handling
    education = []
    ctx_edu = ctx.get("education", [])
    if ctx_edu and isinstance(ctx_edu, list):
        for item in ctx_edu:
            if item and isinstance(item, dict) and any(item.values()):
                education.append(item)
    if not education and "education" in raw_data:
        edu_data = raw_data["education"]
        if isinstance(edu_data, list):
            education = [item for item in edu_data if item and isinstance(item, dict) and any(item.values())]
        elif isinstance(edu_data, str) and edu_data.strip():
            try:
                parsed = json.loads(edu_data)
                if isinstance(parsed, list):
                    education = [item for item in parsed if item and isinstance(item, dict) and any(item.values())]
            except:
                pass
    
    # References
    references = _get_optional_section("references")
    
    # ── Summary ──
    summary = raw_data.get("summary", "")
    
    # ── Build clean payload ──
    clean_data = {
        "full_name": full_name,
        "email": raw_data.get("email", ""),
        "phone": raw_data.get("phone", ""),
        "location": location,
        "linkedin": raw_data.get("linkedin", ""),
        "website": raw_data.get("website", ""),
        "summary": summary,
        "experience": exp_list,
        "education": education,
        "skills": final_skills,
        "skills_categorized": final_skills_categorized,
        "projects": projects,
        "competencies": competencies,
        "community": community,
        "certifications": certifications,
        "references": references,
        "industry": raw_data.get("industry", ""),
        "job_title": raw_data.get("job_title", ""),
        "experience_level": raw_data.get("experience_level", ""),
        "education_level": raw_data.get("education_level", ""),
        "template_style": raw_data.get("template_style", "professional"),
        "created_at": datetime.now().isoformat()
    }
    
    return clean_data


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.post("/start")
async def voice_start(request: Request):
    """Start a new voice session."""
    session_id = secrets.token_urlsafe(16)
    session = {
        "session_id": session_id,
        "step_index": 0,
        "data": {},
        "context": {"phase": "simple"},
        "history": [],
        "done": False
    }
    voice_sessions[session_id] = session
    _persist_session(session_id)
    
    # Defensive: ensure all context flags are initialized for new sessions
    ctx = session.get("context", {})
    for flag in ["exp_field_idx", "in_bullet_loop", "bullet_count", "exp_done", "awaiting_more_bullets", "exp_idx", "summary_idx", "opt_idx", "opt_field_idx"]:
        if flag not in ctx:
            ctx[flag] = 0 if "idx" in flag or "count" in flag else False
    session["context"] = ctx
    _persist_session(session_id)
    
    step = get_current_state(session)
    return {
        "session_id": session_id,
        "question": step["question"],
        "field": step["field"],
        "context_label": step.get("context_label", ""),
        "step_index": 0,
        "done": step.get("done", False),
        "can_go_back": False,
        "show_add_job": False
    }


@router.post("/turn")
async def voice_turn(request: Request):
    """Process a voice turn (answer or back)."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        action = body.get("action", "answer")
        transcript = body.get("transcript", "").strip()
        
        print(f"[HTTP REQUEST] session_id={session_id[:8] if session_id else 'NONE'} | action={action} | transcript='{transcript}'")
        
        # Acquire per-session lock to enforce strict sequential processing
        if session_id not in session_locks:
            session_locks[session_id] = asyncio.Lock()
        
        async with session_locks[session_id]:
            return await _voice_turn_locked(session_id, action, transcript)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": f"Server error: {str(e)}"}, status_code=500)

async def _voice_turn_locked(session_id: str, action: str, transcript: str):
    """Actual voice turn processing - called inside the session lock."""
    
    # Try to load from memory first, then disk
    if session_id not in voice_sessions:
        session_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.exists(session_path):
            try:
                with open(session_path, "r") as f:
                    loaded_session = json.load(f)
                    # DEFENSIVE: Ensure all volatile state machine flags are present and typed correctly
                    ctx = loaded_session.get("context", {})
                    ctx.setdefault("exp_field_idx", 0)
                    ctx.setdefault("in_bullet_loop", False)
                    ctx.setdefault("bullet_count", 0)
                    ctx.setdefault("exp_done", False)
                    ctx.setdefault("awaiting_more_bullets", False)
                    ctx.setdefault("exp_idx", 0)
                    ctx.setdefault("summary_idx", 0)
                    ctx.setdefault("opt_idx", 0)
                    ctx.setdefault("opt_field_idx", 0)
                    loaded_session["context"] = ctx
                    voice_sessions[session_id] = loaded_session
                    print(f"[Session Load] Hydrated session {session_id[:8]}... with flags: exp_field_idx={ctx['exp_field_idx']}, in_bullet_loop={ctx['in_bullet_loop']}, bullet_count={ctx['bullet_count']}, exp_done={ctx['exp_done']}")
            except Exception as e:
                print(f"[Session Load Error] {e}")
                pass
    
    if not session_id or session_id not in voice_sessions:
        return JSONResponse({"error": "Invalid session. Please try again."}, status_code=400)
    
    session = voice_sessions[session_id]
    
    # Extra defensive: ensure flags exist even for in-memory sessions
    ctx = session.get("context", {})
    for flag in ["exp_field_idx", "in_bullet_loop", "bullet_count", "exp_done", "awaiting_more_bullets", "exp_idx", "summary_idx", "opt_idx", "opt_field_idx"]:
        if flag not in ctx:
            ctx[flag] = 0 if "idx" in flag or "count" in flag else False
    session["context"] = ctx
    
    if action == "back":
        step = go_back(session)
    elif action in ["add", "add_job"]:
        # Handle "add another" action from frontend
        step = await process_answer(session, "yes")
    else:
        step = await process_answer(session, transcript)
    
    # Build response
    ctx = session.get("context", {})
    phase = ctx.get("phase", "simple")
    
    can_go_back = True
    if phase == "simple" and session.get("step_index", 0) == 0:
        can_go_back = False
    
    show_add_job = step.get("show_add_job", False)
    
    # If we're done, copy data to top level
    if step.get("done"):
        session["done"] = True
        # Flatten experience for compatibility
        data = session.get("data", {})
        exp_list = ctx.get("experience", [])
        if exp_list:
            data["experience"] = exp_list  # Store as Python list, not JSON string
        for section in ["projects", "competencies", "community", "certifications", "education", "references"]:
            if section in ctx:
                data[section] = ctx[section]
        session["data"] = data
    
    # Persist after every turn
    _persist_session(session_id)
    
    return {
        "session_id": session_id,
        "question": step["question"],
        "field": step["field"],
        "context_label": step.get("context_label", ""),
        "step_index": session.get("step_index", 0),
        "done": step.get("done", False),
        "can_go_back": can_go_back,
        "show_add_job": show_add_job,
        "data_preview": session.get("data", {})
    }


@router.post("/save")
async def voice_save(request: Request):
    """Save session state for later."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "No session"}, status_code=400)
        
        # Acquire lock to ensure consistent read
        if session_id not in session_locks:
            session_locks[session_id] = asyncio.Lock()
        
        async with session_locks[session_id]:
            session = voice_sessions[session_id]
            
            return {
                "success": True,
                "session_id": session_id,
                "state": {
                    "session_id": session_id,
                    "step_index": session.get("step_index", 0),
                    "data": session.get("data", {}),
                    "context": session.get("context", {}),
                    "history": session.get("history", []),
                    "done": session.get("done", False)
                }
            }
        
    except Exception as e:
        print(f"[Voice Save Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/load")
async def voice_load(request: Request):
    """Restore session from saved state."""
    try:
        body = await request.json()
        state = body.get("state", {})
        session_id = state.get("session_id", "")
        
        if not session_id:
            return JSONResponse({"error": "No session ID"}, status_code=400)
        
        # Acquire lock for write
        if session_id not in session_locks:
            session_locks[session_id] = asyncio.Lock()
        
        async with session_locks[session_id]:
            voice_sessions[session_id] = {
                "session_id": session_id,
                "step_index": state.get("step_index", 0),
                "data": state.get("data", {}),
                "context": state.get("context", {}),
                "history": state.get("history", []),
                "done": state.get("done", False)
            }
            
            session = voice_sessions[session_id]
            step = get_current_state(session)
            
            ctx = session.get("context", {})
            phase = ctx.get("phase", "simple")
            can_go_back = not (phase == "simple" and session.get("step_index", 0) == 0)
            
            return {
                "success": True,
                "session_id": session_id,
                "question": step["question"],
                "field": step["field"],
                "context_label": step.get("context_label", ""),
                "step_index": session.get("step_index", 0),
                "done": step.get("done", False),
                "can_go_back": can_go_back,
                "show_add_job": step.get("show_add_job", False),
                "data_preview": session.get("data", {})
            }
        
    except Exception as e:
        print(f"[Voice Load Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/preview")
async def voice_preview(request: Request):
    """Generate preview and download URLs from voice session data."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        
        # Try to load from memory first, then disk
        if session_id not in voice_sessions:
            session_path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
            if os.path.exists(session_path):
                try:
                    with open(session_path, "r") as f:
                        voice_sessions[session_id] = json.load(f)
                except Exception:
                    pass
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "Invalid session"}, status_code=400)
        
        session = voice_sessions[session_id]
        data = session.get("data", {})
        ctx = session.get("context", {})
        
        # ── SANITIZATION LAYER ──
        # Reconstruct a clean payload from whatever the state machine produced
        resume_data = sanitize_resume_data(data, ctx)
        
        # Build resume_id from sanitized name
        full_name = resume_data["full_name"]
        resume_id = f"{full_name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Store in resumes dict for download - use lazy import to avoid circular dependency
        from main import resumes, generate_preview_html, generate_docx, generate_pdf
        resumes[resume_id] = resume_data
        
        # Generate DOCX and PDF files for download
        try:
            docx_path = generate_docx(resume_id, resume_data)
            pdf_path = generate_pdf(resume_id, resume_data)
            print(f"[Voice Preview] Generated files: DOCX={docx_path}, PDF={pdf_path}")
        except Exception as gen_err:
            print(f"[Voice Preview] File generation warning: {gen_err}")
        
        # Generate preview HTML
        preview_html = generate_preview_html(resume_data, resume_data["template_style"])
        
        return {
            "success": True,
            "resume_id": resume_id,
            "preview_html": preview_html,
            "download_url": f"/api/download/{resume_id}",
            "download_url_pdf": f"/api/download/{resume_id}?format=pdf",
            "data": resume_data
        }
        
    except Exception as e:
        print(f"[Voice Preview Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)
