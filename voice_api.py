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

voice_sessions: Dict[str, Any] = {}

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# =============================================================================
# STEP DEFINITIONS
# =============================================================================

SIMPLE_STEPS = [
    {"field": "full_name", "question": "Hey! I'm AIe ResuMaker. Let's build your resume together. First — what's your full name?"},
    {"field": "email", "question": "What's your email address?"},
    {"field": "phone", "question": "What's your phone number?"},
    {"field": "city", "question": "What city do you live in?"},
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
]

PROJECT_FIELDS = [
    {"field": "name", "question": "Project name? (e.g., 'AI Resume Builder')"},
    {"field": "description", "question": "What did you build or accomplish?"},
]

COMPETENCY_FIELDS = [
    {"field": "name", "question": "Notable competency or strength? (e.g., 'Operational Leadership')"},
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
                "question": "Add another job? Say 'yes', 'next', or 'done'.",
                "context_label": f"Job {job_idx + 1}",
            }
        
        if not awaiting_more and bullet_count == 0:
            # First bullet just collected - ask if they want more
            return {
                "type": "decision",
                "field": "_more_bullets",
                "question": f"Got it. Add another bullet? Say 'yes', 'next', or 'done'.",
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
            "question": "Add another job? Say 'yes', 'next', or 'done'.",
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
        
        if section == "projects":
            return _handle_optional_section(session, "projects", PROJECT_FIELDS, "Project")
        elif section == "competencies":
            return _handle_optional_section(session, "competencies", COMPETENCY_FIELDS, "Competency")
        elif section == "community":
            return _handle_optional_section(session, "community", [{"field": "org", "question": "Community group or organization?"}], "Community")
        elif section == "certifications":
            return _handle_optional_section(session, "certifications", [{"field": "name", "question": "Certification name?"}], "Cert")
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
    return {
        "type": "decision",
        "field": f"_add_{section_name}",
        "question": f"{label} saved. Add another? Say 'yes', 'next', or 'skip'.",
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
    
    # Ensure current job exists
    while len(exp_list) <= job_idx:
        exp_list.append({})
    
    # Still collecting standard fields
    if field_idx < len(EXPERIENCE_FIELDS):
        field_name = EXPERIENCE_FIELDS[field_idx]["field"]
        exp_list[job_idx][field_name] = extracted
        ctx["exp_field_idx"] = field_idx + 1
        ctx["experience"] = exp_list
        session["context"] = ctx
        return get_current_state(session)
    
    # In bullet collection mode
    if not ctx.get("in_bullet_loop", False) and not ctx.get("exp_done", False):
        # First bullet - collect it and then ask if they want more
        ctx["in_bullet_loop"] = True
        ctx["bullet_count"] = 0  # Will be incremented after first bullet
        if not exp_list[job_idx].get("description"):
            exp_list[job_idx]["description"] = []
        if isinstance(exp_list[job_idx]["description"], list):
            exp_list[job_idx]["description"].append(extracted)
        else:
            exp_list[job_idx]["description"] = [exp_list[job_idx]["description"], extracted]
        ctx["experience"] = exp_list
        session["context"] = ctx
        return get_current_state(session)
    
    bullet_count = ctx.get("bullet_count", 0)
    
    # Handle "Add another job?" decision
    if ctx.get("exp_done", False):
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
            session["context"] = ctx
            return get_current_state(session)
    
    # Check if user wants more bullets (after decision prompt)
    if lower in ["yes", "y", "add", "more"]:
        # User wants to add another bullet - set flag and return bullet prompt
        ctx["awaiting_more_bullets"] = True
        session["context"] = ctx
        return get_current_state(session)
    
    # Check if user is done with bullets
    if lower in ["done", "no", "n", "finished", "next", "skip"]:
        # Move to "add another job?" decision
        ctx["in_bullet_loop"] = False
        ctx["bullet_count"] = 0
        ctx["awaiting_more_bullets"] = False
        ctx["exp_done"] = True  # Mark that we're done with this job's bullets
        session["context"] = ctx
        return get_current_state(session)
    
    # User provided another bullet
    if "description" not in exp_list[job_idx]:
        exp_list[job_idx]["description"] = []
    if isinstance(exp_list[job_idx]["description"], list):
        exp_list[job_idx]["description"].append(extracted)
    else:
        exp_list[job_idx]["description"] = [exp_list[job_idx]["description"], extracted]
    
    ctx["bullet_count"] = bullet_count + 1
    ctx["experience"] = exp_list
    session["context"] = ctx
    
    # After collecting a bullet, ask if they want more
    return {
        "type": "decision",
        "field": "_more_bullets",
        "question": f"Bullet saved. Add another? Say 'yes', 'next', or 'done'.",
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
    
    item_list = ctx.get(section, [])
    while len(item_list) <= item_idx:
        item_list.append({})
    
    fields = {
        "projects": PROJECT_FIELDS,
        "competencies": COMPETENCY_FIELDS,
        "community": [{"field": "org", "question": "Community group or organization?"}],
        "certifications": [{"field": "name", "question": "Certification name?"}],
    }.get(section, [])
    
    # Decision to add more items (field_idx >= len(fields) means we're at decision point)
    if field_idx >= len(fields):
        if lower in ["yes", "y", "add", "more"]:
            # Add another item - reset field index for new item
            ctx["opt_idx"] = item_idx + 1
            ctx["opt_field_idx"] = 0
            session["context"] = ctx
            return get_current_state(session)
        elif lower in ["next", "n", "done", "skip", "no"]:
            # Done with this section - save data and move to next
            if item_list and any(item for item in item_list):
                data[section] = item_list
                session["data"] = data
            _advance_optional_section(session)
            return get_current_state(session)
        else:
            # Unrecognized input - treat as done with section
            if item_list and any(item for item in item_list):
                data[section] = item_list
                session["data"] = data
            _advance_optional_section(session)
            return get_current_state(session)
    
    # First field of first item - check skip
    if item_idx == 0 and field_idx == 0:
        if lower in ["skip", "none", "n/a", "no", "next"]:
            # Skip this entire section
            _advance_optional_section(session)
            return get_current_state(session)
    
    # Collecting field data
    field_name = fields[field_idx]["field"]
    item_list[item_idx][field_name] = extracted
    ctx[section] = item_list
    ctx["opt_field_idx"] = field_idx + 1
    session["context"] = ctx
    return get_current_state(session)


def _advance_optional_section(session: dict):
    """Move to next optional section."""
    ctx = session.get("context", {})
    sections = ["projects", "competencies", "community", "certifications", "links", "done"]
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
    sections = ["projects", "competencies", "community", "certifications", "links"]
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
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "Invalid session. Please try again."}, status_code=400)
        
        session = voice_sessions[session_id]
        
        if action == "back":
            step = go_back(session)
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
                data["experience"] = json.dumps(exp_list)
            for section in ["projects", "competencies", "community", "certifications"]:
                if section in ctx:
                    data[section] = ctx[section]
            session["data"] = data
        
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
        
    except Exception as e:
        print(f"[Voice Turn Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/save")
async def voice_save(request: Request):
    """Save session state for later."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "No session"}, status_code=400)
        
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
