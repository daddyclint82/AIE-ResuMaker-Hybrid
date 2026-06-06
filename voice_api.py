"""
Voice Chat API for AIE ResuMaker Hybrid — ADHD-Optimized with Back/Add buttons
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

# Load .env BEFORE reading GROQ_API_KEY
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
# INPUT CLEANERS — strip conversational garbage from user inputs
# =============================================================================

def _clean_link_input(text: str) -> str:
    """Clean link inputs — strip 'skip', 'none', and conversational filler."""
    if not text:
        return ""
    lower = text.lower().strip()
    if lower in ["skip", "none", "no", "n/a", "na", "don't have one", "dont have one", "not applicable"]:
        return ""
    # Strip common conversational prefixes
    garbage_patterns = [
        r"^(there is no )",
        r"^(i don\'t have )",
        r"^(i dont have )",
        r"^(i do not have )",
        r"^(no, )",
        r"^(nope, )",
        r"^(sorry, )",
    ]
    cleaned = text.strip()
    for pattern in garbage_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


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

# Skills categories taxonomy (42 categories)
# Tiered taxonomy for industry-aware categorization
SKILL_TIERS = {
    "technology": ["Programming u0026 Development", "Frameworks u0026 Libraries", "AI/ML u0026 Data Science", "Cloud u0026 Infrastructure", "DevOps u0026 Automation", "Databases u0026 Data Storage", "Cybersecurity", "Testing u0026 Quality Assurance", "Mobile Development", "Embedded Systems", "Research u0026 Analysis", "Project u0026 Program Management"],
    "oil_gas_energy": ["Safety u0026 Risk Management", "Environmental u0026 Sustainability", "Heavy Equipment Operation", "Welding u0026 Metalwork", "Electrical Systems", "Machining u0026 Manufacturing", "Quality Control u0026 Inspection", "Project u0026 Program Management", "Research u0026 Analysis"],
    "healthcare": ["Healthcare u0026 Medical", "Research u0026 Analysis", "Safety u0026 Risk Management", "Administrative u0026 Operations", "Customer Service u0026 Hospitality", "Education u0026 Training"],
    "finance": ["Financial u0026 Accounting", "Research u0026 Analysis", "Legal u0026 Compliance", "Administrative u0026 Operations", "Project u0026 Program Management", "Cybersecurity"],
    "creative": ["Design u0026 Visual Arts", "Writing u0026 Content", "Media u0026 Broadcasting", "Music u0026 Performing Arts", "Marketing u0026 Communications", "Customer Service u0026 Hospitality"],
    "trades": ["Welding u0026 Metalwork", "Electrical Systems", "Plumbing u0026 Pipefitting", "HVAC u0026 Refrigeration", "Carpentry u0026 Woodworking", "Masonry u0026 Concrete", "Heavy Equipment Operation", "Machining u0026 Manufacturing", "Automotive u0026 Mechanical", "Agriculture u0026 Landscaping"],
    "general": ["Project u0026 Program Management", "Sales u0026 Business Development", "Marketing u0026 Communications", "HR u0026 Talent Management", "Customer Service u0026 Hospitality", "Education u0026 Training", "Administrative u0026 Operations"]
}

SKILL_CATEGORIES = SKILL_TIERS["technology"] + SKILL_TIERS["oil_gas_energy"] + SKILL_TIERS["healthcare"] + SKILL_TIERS["finance"] + SKILL_TIERS["creative"] + SKILL_TIERS["trades"] + [c for c in SKILL_TIERS["general"] if c not in SKILL_TIERS["technology"] + SKILL_TIERS["oil_gas_energy"] + SKILL_TIERS["healthcare"] + SKILL_TIERS["finance"] + SKILL_TIERS["creative"] + SKILL_TIERS["trades"]]

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


# Optional section steps
PROJECT_STEPS = [
    {"field": "project_name", "question": "Project name? (e.g., 'AI Resume Builder')", "subfield": "name"},
    {"field": "project_description", "question": "What did you build or accomplish?", "subfield": "description"},
]

COMPETENCY_STEPS = [
    {"field": "competency", "question": "Notable competency or strength? (e.g., 'Operational Leadership')", "subfield": "name"},
]

COMMUNITY_STEPS = [
    {"field": "community_org", "question": "Community group or organization name?", "subfield": "organization"},
    {"field": "community_role", "question": "What was your role or contribution?", "subfield": "role"},
]

CERT_STEPS = [
    {"field": "cert_name", "question": "Certification or license name?", "subfield": "name"},
    {"field": "cert_date", "question": "When did you earn it? (year or month/year)", "subfield": "date"},
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
        exp_list = context.get("experience", [])
        complete_count = sum(1 for e in exp_list if len(e) >= len(EXPERIENCE_STEPS))
        current_job_num = complete_count + 1
        substep = context.get("exp_substep", 0)
        bullet_count = context.get("exp_bullet_count", 0)
        
        if substep < len(EXPERIENCE_STEPS) - 1:
            # Standard fields: company, title, dates
            step = EXPERIENCE_STEPS[substep].copy()
            step["context_label"] = f"Job {current_job_num}"
            step["show_add_job"] = True  # Show "Add Job" button
            return step
        elif substep == len(EXPERIENCE_STEPS) - 1:
            # Description/bullet field — first bullet of this job
            return {
                "field": "_bullet",
                "question": "What did you do there? Say bullet 1.",
                "context_label": f"Job {current_job_num}",
                "show_add_job": True,
                "is_first_bullet": True,
                "bullet_count": 1,
                "job_count": complete_count
            }
        else:
            # After all standard fields, check if we're in bullet loop
            in_bullet_loop = context.get("in_bullet_loop", False)
            if in_bullet_loop:
                # Ask for next bullet (bullet 2, 3, 4...)
                return {
                    "field": "_bullet",
                    "question": f"Bullet {bullet_count + 1}?",
                    "context_label": f"Job {current_job_num - 1}",
                    "show_add_job": True,
                    "show_done_jobs": True,
                    "is_first_bullet": False,
                    "bullet_count": bullet_count + 1,
                    "job_count": complete_count
                }
            else:
                # Decision: add another job?
                return {
                    "field": "_decision",
                    "question": f"Great! Job {complete_count} saved. Add another job? Say 'yes' or 'done'.",
                    "context_label": "Jobs",
                    "show_add_job": False,
                    "show_done_jobs": True
                }
    
    # Phase 3: Education loop
    if context.get("phase") == "education":
        edu_list = context.get("education", [])
        complete_count = sum(1 for e in edu_list if len(e) >= len(EDUCATION_STEPS))
        current_num = complete_count + 1
        substep = context.get("edu_substep", 0)
        
        if substep < len(EDUCATION_STEPS):
            step = EDUCATION_STEPS[substep].copy()
            step["context_label"] = f"School {current_num}"
            return step
        else:
            return {"field": "_decision", "question": f"School {current_num - 1} saved. Add another school? Say 'yes' or 'done'.", "context_label": "Education"}
    
    # Phase 4: Skills collection
    if context.get("phase") == "skills":
        return {
            "field": "skills", 
            "question": "What skills do you have? List them all — 'Python, AI infrastructure, Discord bots, Stripe, project management...'", 
            "group": "skills",
            "show_done_jobs": True
        }
    
    # Phase 4b: Skills Review (after categorization)
    if context.get("phase") == "skills_review":
        return {
            "field": "skills_review",
            "question": "Here are your organized skills. Click + to add more or − to remove. Say 'done' when finished.",
            "context_label": "Skills Review",
            "show_add_job": False,
            "skills_categorized": context.get("skills_categorized", {})
        }
    
    # Phase 5: Optional sections
    if context.get("phase") == "optional":
        opt_section = context.get("opt_section", "projects")
        
        if opt_section == "projects":
            proj_list = context.get("projects", [])
            # Count COMPLETE projects (all fields filled)
            complete_count = sum(1 for p in proj_list if len(p) >= len(PROJECT_STEPS))
            # Current project number = complete + 1
            current_proj_num = complete_count + 1
            substep = context.get("proj_substep", 0)
            if substep < len(PROJECT_STEPS):
                step = PROJECT_STEPS[substep].copy()
                step["context_label"] = f"Project {current_proj_num}"
                return step
            else:
                return {"field": "_decision", "question": "Project saved. Add another project? Say 'yes', 'next', or 'skip'.", "context_label": "Projects"}
        
        elif opt_section == "competencies":
            comp_list = context.get("competencies", [])
            complete_count = sum(1 for c in comp_list if len(c) >= len(COMPETENCY_STEPS))
            current_num = complete_count + 1
            substep = context.get("comp_substep", 0)
            if substep < len(COMPETENCY_STEPS):
                step = COMPETENCY_STEPS[substep].copy()
                step["context_label"] = f"Competency {current_num}"
                return step
            else:
                return {"field": "_decision", "question": "Competency saved. Add another? Say 'yes', 'next', or 'skip'.", "context_label": "Competencies"}
        
        elif opt_section == "community":
            comm_list = context.get("community", [])
            complete_count = sum(1 for c in comm_list if len(c) >= len(COMMUNITY_STEPS))
            current_num = complete_count + 1
            substep = context.get("comm_substep", 0)
            if substep < len(COMMUNITY_STEPS):
                step = COMMUNITY_STEPS[substep].copy()
                step["context_label"] = f"Community {current_num}"
                return step
            else:
                return {"field": "_decision", "question": "Entry saved. Add another? Say 'yes', 'next', or 'skip'.", "context_label": "Community"}
        
        elif opt_section == "certifications":
            cert_list = context.get("certifications", [])
            complete_count = sum(1 for c in cert_list if len(c) >= len(CERT_STEPS))
            current_num = complete_count + 1
            substep = context.get("cert_substep", 0)
            if substep < len(CERT_STEPS):
                step = CERT_STEPS[substep].copy()
                step["context_label"] = f"Cert {current_num}"
                return step
            else:
                return {"field": "_decision", "question": "Cert saved. Add another? Say 'yes', 'next', or 'skip'.", "context_label": "Certifications"}
        
        elif opt_section == "links":
            link_step = context.get("link_step", 0)
            if link_step == 0:
                return {"field": "website", "question": "Website or portfolio? Or say 'skip'.", "group": "links", "context_label": "Links"}
            elif link_step == 1:
                return {"field": "linkedin", "question": "LinkedIn URL? Or say 'skip'.", "group": "links", "context_label": "Links"}
            else:
                # After both links, go to done (summary already done earlier)
                return {"field": "done", "question": "Your resume is ready! Click 'View Resume' below.", "done": True}
    
    # Phase 3: Summary Interview (moved BEFORE skills - now right after experience)
    if context.get("phase") == "summary_interview":
        summary_step = context.get("summary_step", 0)
        
        if summary_step == 0:
            # Question 1: Core edge/value proposition
            return {
                "field": "summary_q1",
                "question": "I'll write your professional summary. First — what's your core edge? Why hire YOU over anyone else? (e.g., '10 years drilling ops + self-taught AI builder')",
                "context_label": "Summary — Your Edge",
                "group": "summary"
            }
        elif summary_step == 1:
            # Question 2: Business problems solved
            return {
                "field": "summary_q2",
                "question": "What business problems do you solve? How do you help companies scale, save money, or streamline? (e.g., 'I keep critical systems running under pressure — from $500k/day rigs to 24/7 AI bots')",
                "context_label": "Summary — Impact",
                "group": "summary"
            }
        elif summary_step == 2:
            # Question 3: Hard metrics
            return {
                "field": "summary_q3",
                "question": "Any hard numbers to back it up? Headcount managed, revenue, project turnaround? (e.g., 'Maintained 99.9% uptime on production bot, managed 20-person crews')",
                "context_label": "Summary — Metrics",
                "group": "summary"
            }
        elif summary_step == 3:
            # Question 4: Keywords
            return {
                "field": "summary_q4",
                "question": "Keywords from the job posting you want to hit? (e.g., 'MLOps', 'LLM deployment', 'infrastructure automation') Say 'none' if you don't have any.",
                "context_label": "Summary — Keywords",
                "group": "summary"
            }
        else:
            # Step 4: Generate summary
            return {
                "field": "summary",
                "question": "Great! Now I'll write your summary. Say 'auto' to generate from your answers, or type your own summary.",
                "context_label": "Summary",
                "group": "summary"
            }
    
    # Done
    return {"field": "done", "question": "Your resume is ready! Click 'View Resume' below.", "done": True}


async def advance_state(session: dict, extracted: str) -> None:
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
            # substep >= len(EXPERIENCE_STEPS) — we're in bullet loop mode or at decision point
            print(f"[DEBUG] Else branch. substep={substep}, len_steps={len(EXPERIENCE_STEPS)}, in_bullet_loop={in_bullet_loop}")
            if not in_bullet_loop:
                # At decision point between jobs
                print(f"[DEBUG] At decision point. extracted='{extracted}'")
                if extracted.lower() in ["done", "no", "n", "finished", "complete", "that's it", "thats it", "skip", "next"]:
                    # Done with jobs — transition to summary interview
                    exp_list = context.get("experience", [])
                    if exp_list:
                        data["experience"] = exp_list
                    context["phase"] = "summary_interview"
                    context["summary_step"] = 0
                    context["exp_substep"] = 0
                    context["exp_bullet_count"] = 0
                    context["in_bullet_loop"] = False
                    print(f"[DEBUG] User said done, transitioning to summary_interview")
                    return
                elif extracted.lower() in ["yes", "y", "add", "another", "more"]:
                    # Add another job
                    context["exp_substep"] = 0
                    context["exp_bullet_count"] = 0
                    context["in_bullet_loop"] = False
                    print(f"[DEBUG] User said yes, resetting for new job. exp_substep={context['exp_substep']}")
                    print(f"[DEBUG] Context after yes: exp_substep={context.get('exp_substep')}, in_bullet_loop={context.get('in_bullet_loop')}")
                else:
                    # Unexpected input at decision point — treat as done and move on
                    exp_list = context.get("experience", [])
                    if exp_list:
                        data["experience"] = exp_list
                    context["phase"] = "summary_interview"
                    context["summary_step"] = 0
                    context["exp_substep"] = 0
                    context["exp_bullet_count"] = 0
                    context["in_bullet_loop"] = False
                    print(f"[DEBUG] Unexpected input at decision, moving to summary_interview")
                    return
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

    # Phase 2b: Experience done, transition to SUMMARY INTERVIEW (reordered - before skills)
    if context.get("phase") == "experience" and extracted == "__DONE_WITH_JOBS__":
        # Save experience data
        exp_list = context.get("experience", [])
        if exp_list:
            data["experience"] = exp_list
        # Transition to summary interview FIRST (before skills)
        context["phase"] = "summary_interview"
        context["summary_step"] = 0
        return
    
    # Phase 2c: Summary Interview (4 questions) — moved before skills
    if context.get("phase") == "summary_interview":
        step = context.get("summary_step", 0)
        if step == 0:
            data["summary_q1"] = extracted
            context["summary_step"] = 1
        elif step == 1:
            data["summary_q2"] = extracted
            context["summary_step"] = 2
        elif step == 2:
            data["summary_q3"] = extracted
            context["summary_step"] = 3
        elif step == 3:
            data["summary_q4"] = extracted
            context["summary_step"] = 4
        elif step == 4:
            # User typed custom summary or said "auto"
            if extracted == "__AUTO_GENERATE__":
                summary = await generate_summary_from_session(session)
                data["summary"] = summary
            else:
                data["summary"] = extracted
            # Transition to skills AFTER interview
            context["phase"] = "skills"
            context["summary_step"] = 0

            context["skills_categorized"] = {}
            context["skills_raw"] = ""
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
            context["summary_step"] = 0

        return
    
    # Phase 4: Skills
    if context.get("phase") == "skills":
        data["skills"] = extracted
        context["phase"] = "skills_review"
        # Don't categorize here — let the turn handler do it async
        return
    
    # Phase 4b: Skills Review
    if context.get("phase") == "skills_review":
        print(f"[DEBUG] Skills review - extracted: {repr(extracted)}")
        if extracted.lower() in ["done", "yes", "y", "finished", "next"]:
            print(f"[DEBUG] Moving to optional phase")
            # Move to optional phase
            context["phase"] = "optional"
            context["opt_section"] = "projects"
            context["proj_substep"] = 0
            context["projects"] = []
            # Save categorized skills to data
            if "skills_categorized" in context:
                data["skills_categorized"] = context["skills_categorized"]
        elif extracted and not any(extracted.lower() == x for x in ["done", "yes", "y", "finished", "next"]):
            print(f"[DEBUG] Adding more skills: {extracted}")
            # User is adding more skills — append to Other Skills
            if "skills_categorized" not in context:
                context["skills_categorized"] = {}
            if "Other Skills" not in context["skills_categorized"]:
                context["skills_categorized"]["Other Skills"] = []
            new_skills = [s.strip() for s in extracted.split(",") if s.strip()]
            context["skills_categorized"]["Other Skills"].extend(new_skills)
            # Also update flat list
            all_skills = []
            for cat_skills in context["skills_categorized"].values():
                all_skills.extend(cat_skills)
            data["skills"] = ", ".join(all_skills)
        print(f"[DEBUG] After skills_review - phase: {context['phase']}")
        return
    
    # Phase 5: Optional sections
    if context.get("phase") == "optional":
        opt_section = context.get("opt_section", "projects")
        
        if opt_section == "links":
            link_step = context.get("link_step", 0)
            if link_step == 0:
                data["website"] = extracted if extracted.lower() != "skip" else ""
                context["link_step"] = 1
            elif link_step == 1:
                data["linkedin"] = extracted if extracted.lower() != "skip" else ""
                context["link_step"] = 2
                # After links, go to done (summary already generated earlier)
                context["phase"] = "done"
            else:
                context["phase"] = "done"
            return
        
        if opt_section == "projects":
            substep = context.get("proj_substep", 0)
            proj_list = context.setdefault("projects", [])
            
            # Check skip at entry point
            if substep == 0 and extracted.lower() in ["skip", "none", "n/a", "no", "n"]:
                context["opt_section"] = "competencies"
                context["comp_substep"] = 0
                context["competencies"] = []
                return
            
            if substep < len(PROJECT_STEPS):
                if not proj_list or len(proj_list[-1]) >= len(PROJECT_STEPS):
                    proj_list.append({})
                proj_list[-1][PROJECT_STEPS[substep]["subfield"]] = extracted
                context["proj_substep"] = substep + 1
            else:
                if extracted.lower() in ["yes", "y", "add", "another"]:
                    context["proj_substep"] = 0
                elif extracted.lower() in ["next", "n", "done", "skip"]:
                    data["projects"] = proj_list
                    context["opt_section"] = "competencies"
                    context["comp_substep"] = 0
                    context["competencies"] = []
                else:
                    context["opt_section"] = "competencies"
                    context["comp_substep"] = 0
                    context["competencies"] = []
            return
        
        elif opt_section == "competencies":
            substep = context.get("comp_substep", 0)
            comp_list = context.setdefault("competencies", [])
            
            # Check skip at entry point
            if substep == 0 and extracted.lower() in ["skip", "none", "n/a", "no", "n"]:
                context["opt_section"] = "community"
                context["comm_substep"] = 0
                context["community"] = []
                return
            
            if substep < len(COMPETENCY_STEPS):
                if not comp_list or len(comp_list[-1]) >= len(COMPETENCY_STEPS):
                    comp_list.append({})
                comp_list[-1][COMPETENCY_STEPS[substep]["subfield"]] = extracted
                context["comp_substep"] = substep + 1
            else:
                if extracted.lower() in ["yes", "y", "add", "another"]:
                    context["comp_substep"] = 0
                elif extracted.lower() in ["next", "n", "done", "skip"]:
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
            
            # Check skip at entry point
            if substep == 0 and extracted.lower() in ["skip", "none", "n/a", "no", "n"]:
                context["opt_section"] = "certifications"
                context["cert_substep"] = 0
                context["certifications"] = []
                return
            
            if substep < len(COMMUNITY_STEPS):
                if not comm_list or len(comm_list[-1]) >= len(COMMUNITY_STEPS):
                    comm_list.append({})
                cleaned = extracted.strip()
                if cleaned.lower() in ["skip", "none", "n/a", ""]:
                    cleaned = ""
                comm_list[-1][COMMUNITY_STEPS[substep]["subfield"]] = cleaned
                context["comm_substep"] = substep + 1
            else:
                if extracted.lower() in ["yes", "y", "add", "another"]:
                    context["comm_substep"] = 0
                elif extracted.lower() in ["next", "n", "done", "skip"]:
                    comm_list[:] = [c for c in comm_list if c.get("organization") or c.get("role")]
                    data["community"] = comm_list
                    context["opt_section"] = "certifications"
                    context["cert_substep"] = 0
                    context["certifications"] = []
                else:
                    comm_list[:] = [c for c in comm_list if c.get("organization") or c.get("role")]
                    data["community"] = comm_list
                    context["opt_section"] = "certifications"
                    context["cert_substep"] = 0
                    context["certifications"] = []
            return
        
        elif opt_section == "certifications":
            substep = context.get("cert_substep", 0)
            cert_list = context.setdefault("certifications", [])
            
            # Check skip at entry point
            if substep == 0 and extracted.lower() in ["skip", "none", "n/a", "no", "n"]:
                context["opt_section"] = "links"
                context["link_step"] = 0
                return
            
            if substep < len(CERT_STEPS):
                if not cert_list or len(cert_list[-1]) >= len(CERT_STEPS):
                    cert_list.append({})
                cert_list[-1][CERT_STEPS[substep]["subfield"]] = extracted
                context["cert_substep"] = substep + 1
            else:
                if extracted.lower() in ["yes", "y", "add", "another"]:
                    context["cert_substep"] = 0
                elif extracted.lower() in ["next", "n", "done", "skip"]:
                    data["certifications"] = cert_list
                    context["opt_section"] = "links"
                else:
                    context["opt_section"] = "links"
            return
        
        elif opt_section == "links":
            link_step = context.get("link_step", 0)
            if link_step == 0:
                cleaned = _clean_link_input(extracted)
                data["website"] = cleaned if cleaned else ""
                context["link_step"] = 1
                print(f"[DEBUG] Set website: {data['website']}")
            elif link_step == 1:
                cleaned = _clean_link_input(extracted)
                data["linkedin"] = cleaned if cleaned else ""
                context["link_step"] = 2
                # After links, go to done (summary already generated earlier)
                context["phase"] = "done"
                print(f"[DEBUG] Set linkedin: {data['linkedin']}")
            else:
                context["phase"] = "done"
                print(f"[DEBUG] Transitioned to done (fallback)")
            return
    
    # Phase 6: Pre-summary interview
    if context.get("phase") == "summary":
        summary_step = context.get("summary_step", 0)
        
        if summary_step == 0:
            data["summary_q1"] = extracted  # Core edge
            context["summary_step"] = 1
        elif summary_step == 1:
            data["summary_q2"] = extracted  # Business problems
            context["summary_step"] = 2
        elif summary_step == 2:
            data["summary_q3"] = extracted  # Hard metrics
            context["summary_step"] = 3
        elif summary_step == 3:
            data["summary_q4"] = extracted if extracted.lower() != "none" else ""  # Keywords
            context["summary_step"] = 4
        elif summary_step >= 4:
            if extracted.lower() in ["auto", "yes", "y", "generate"]:
                generated_summary = await generate_summary_from_session(session)
                data["summary"] = generated_summary
            else:
                data["summary"] = extracted
            # After summary, transition to skills (reordered flow)
            context["phase"] = "skills"
            context["summary_step"] = 0

            context["skills_categorized"] = {}
            context["skills_raw"] = ""
        return


# =============================================================================
# PROFESSIONAL SUMMARY GENERATION — v2 (Robust, Multi-Model, Validated)
# =============================================================================

# Banned generic phrases that make summaries sound like AI slop
_BANNED_PHRASES = [
    "results-driven", "passionate", "detail-oriented", "self-motivated",
    "team player", "hardworking", "dedicated", "proven track record",
    "excellent communication", "strong work ethic", "go-getter",
    "synergy", "leverage", "utilize", "empower", "disrupt",
    "dynamic", "proactive", "strategic thinker", "thought leader",
    "outside the box", "best-in-class", "world-class", "cutting-edge",
    "in today's fast-paced", "ever-changing landscape", "digital transformation",
]

# Model preference for summary generation (higher quality = better summaries)
_SUMMARY_MODEL = os.environ.get("GROQ_SUMMARY_MODEL", "llama-3.3-70b-versatile")


def _extract_skills_flat(session: dict) -> List[str]:
    """Extract a clean flat list of skill names from session."""
    data = session.get("data", {})
    context = session.get("context", {})
    skills_categorized = context.get("skills_categorized", {})
    flat = []
    
    if skills_categorized:
        for cat_name, cat_skills in skills_categorized.items():
            for skill in cat_skills:
                if isinstance(skill, dict):
                    name = skill.get("name", "").strip()
                elif isinstance(skill, str):
                    name = skill.strip()
                else:
                    continue
                if name and name not in flat:
                    flat.append(name)
    elif data.get("skills"):
        flat = [s.strip() for s in data["skills"].split(",") if s.strip()]
    
    return flat


def _extract_experience_narrative(session: dict) -> str:
    """Build a narrative paragraph from experience entries for the prompt."""
    context = session.get("context", {})
    exp_list = context.get("experience", [])
    if not exp_list:
        return ""
    
    parts = []
    for job in exp_list:
        company = job.get("company", "").strip()
        title = job.get("title", "").strip()
        dates = job.get("dates", "").strip()
        bullets = job.get("description", [])
        
        if isinstance(bullets, str):
            bullets = [bullets]
        if not isinstance(bullets, list):
            bullets = []
        
        job_line = f"- {title} at {company}" if title and company else f"- {title or company}"
        if dates:
            job_line += f" ({dates})"
        parts.append(job_line)
        
        for b in bullets:
            b = b.strip()
            if b and b.lower() not in ["done", "no", "yes", "skip", "none"]:
                parts.append(f"  • {b}")
    
    return "\n".join(parts)


def _extract_education_narrative(session: dict) -> str:
    """Build education narrative."""
    data = session.get("data", {})
    context = session.get("context", {})
    edu_list = context.get("education", [])
    
    if not edu_list and not data.get("education_level"):
        return ""
    
    parts = []
    if data.get("education_level"):
        parts.append(f"Education Level: {data['education_level']}")
    
    for edu in edu_list:
        school = edu.get("school", "").strip()
        degree = edu.get("degree", "").strip()
        field = edu.get("field", "").strip()
        dates = edu.get("dates", "").strip()
        
        line = f"- {degree}" if degree else "- Education"
        if field:
            line += f" in {field}"
        if school:
            line += f" from {school}"
        if dates:
            line += f" ({dates})"
        parts.append(line)
    
    return "\n".join(parts)


def _is_generic_summary(summary: str) -> bool:
    """Check if summary is generic AI slop."""
    if not summary or len(summary) < 40:
        return True
    
    lower = summary.lower()
    
    # Check banned phrases
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            return True
    
    # Check for cookie-cutter patterns
    generic_starts = [
        "is a ", "is an ", "has ", "with over ", "with more than",
        "bringing ", "offering ", "seeking ", "looking for",
    ]
    for start in generic_starts:
        if lower.startswith(start):
            return True
    
    return False


def _build_fallback_summary(session: dict) -> str:
    """Build a non-generic fallback using user's actual words."""
    data = session.get("data", {})
    context = session.get("context", {})
    
    full_name = data.get("full_name", "").strip()
    job_title = data.get("job_title", "").strip()
    industry = data.get("industry", "").strip()
    core_edge = data.get("summary_q1", "").strip()
    business_impact = data.get("summary_q2", "").strip()
    hard_metrics = data.get("summary_q3", "").strip()
    keywords = data.get("summary_q4", "").strip()
    
    skills = _extract_skills_flat(session)[:6]
    exp_narrative = _extract_experience_narrative(session)
    edu_narrative = _extract_education_narrative(session)
    
    # Build from the strongest pieces of info
    pieces = []
    
    # Name + identity anchor
    if full_name and job_title:
        pieces.append(f"{full_name} is a {job_title}")
        if industry:
            pieces[-1] += f" in {industry}"
        pieces[-1] += "."
    elif full_name:
        pieces.append(f"{full_name} brings hands-on expertise to the table.")
    
    # Core edge (the WHY)
    if core_edge and len(core_edge) > 5:
        pieces.append(core_edge[0].upper() + core_edge[1:] if not core_edge[0].isupper() else core_edge)
    
    # Business impact
    if business_impact and len(business_impact) > 5:
        pieces.append(business_impact[0].upper() + business_impact[1:] if not business_impact[0].isupper() else business_impact)
    
    # Hard metrics
    if hard_metrics and len(hard_metrics) > 5:
        pieces.append(f"Proven results include {hard_metrics[0].lower() + hard_metrics[1:]}" if not hard_metrics.startswith("Proven") else hard_metrics)
    
    # Skills bridge
    if skills:
        skill_str = ", ".join(skills)
        pieces.append(f"Technical toolkit: {skill_str}.")
    
    # Keywords
    if keywords and len(keywords) > 2:
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()][:3]
        if keyword_list:
            pieces.append(f"Aligned with {', '.join(keyword_list)}.")
    
    # Combine into flowing paragraph
    summary = " ".join(pieces)
    
    # Clean up
    summary = summary.replace("  ", " ").strip()
    if not summary.endswith("."):
        summary += "."
    
    return summary


async def generate_summary_from_session(session: dict) -> str:
    """Generate a professional summary using session data.
    
    Strategy:
    1. Collect ALL user data (experience bullets, skills, interview answers)
    2. Build a rich prompt with the user's actual words
    3. Try high-quality model first, fall back to fast model
    4. Validate output — if generic, use template-based fallback
    5. Return the best summary we can produce
    """
    data = session.get("data", {})
    context = session.get("context", {})
    
    # --- COLLECT ALL DATA ---
    full_name = data.get("full_name", "").strip()
    job_title = data.get("job_title", "").strip()
    industry = data.get("industry", "").strip()
    experience_level = data.get("experience_level", "").strip()
    
    skills = _extract_skills_flat(session)
    top_skills = skills[:6]
    
    # Experience
    exp_list = context.get("experience", [])
    recent_job = exp_list[-1].get("title", "") if exp_list else ""
    exp_narrative = _extract_experience_narrative(session)
    
    # Education
    edu_narrative = _extract_education_narrative(session)
    
    # Interview answers
    core_edge = data.get("summary_q1", "").strip()
    business_impact = data.get("summary_q2", "").strip()
    hard_metrics = data.get("summary_q3", "").strip()
    keywords = data.get("summary_q4", "").strip()
    
    # Build keyword list
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
    
    # --- BUILD RICH PROMPT ---
    prompt = f"""Write a professional summary (2-4 sentences, 40-80 words) for this person.

IDENTITY:
Name: {full_name}
Target Role: {job_title}
Industry: {industry}
Experience Level: {experience_level}

WORK HISTORY:
{exp_narrative if exp_narrative else "(No work history provided)"}

EDUCATION:
{edu_narrative if edu_narrative else "(No education details provided)"}

KEY SKILLS:
{', '.join(top_skills) if top_skills else '(No skills listed)'}

INTERVIEW ANSWERS:
- What makes them unique? "{core_edge}"
- Problems they solve: "{business_impact}"
- Proof/metrics: "{hard_metrics}"
- Target job keywords: "{keywords}"

INSTRUCTIONS — FOLLOW EXACTLY:
1. OPEN WITH their unique edge or story. Never start "[Name] is a [level] professional..."
2. USE THEIR EXACT WORDS from the interview answers. Quote them naturally.
3. WEAVE metrics into the narrative: "maintained 99.9% uptime on production rigs" not "has experience with uptime."
4. MENTION 1-2 target keywords ONLY if they fit the story.
5. END with forward momentum: "now applying that to X" or "ready to drive Y."
6. TONE: confident, human, specific. No corporate buzzwords.
7. LENGTH: 2-4 sentences. Punchy, not a paragraph.

FORBIDDEN WORDS: results-driven, passionate, detail-oriented, self-motivated, team player, proven track record, excellent communication, dynamic, proactive, synergy, leverage, ever-changing landscape, cutting-edge

GOOD EXAMPLE:
"Clinton Singleton kept $500k/day drilling rigs running through hurricanes and supply chain chaos — then taught himself to automate that same operational rigor through AI bots and MLOps pipelines. He brings a decade of mission-critical systems thinking to infrastructure roles where downtime isn't an option."

BAD EXAMPLE:
"Clinton Singleton is a results-driven professional with a proven track record in operations and technology..."

OUTPUT ONLY the summary text. No quotes around it. No intro."""

    # --- TRY LLM GENERATION ---
    if GROQ_API_KEY:
        models_to_try = [_SUMMARY_MODEL, GROQ_MODEL]  # Prefer quality, fallback to speed
        
        for model in models_to_try:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {GROQ_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": "You are an elite resume writer. You write summaries that sound like a human wrote them — specific, confident, story-driven. NEVER use generic phrases. ALWAYS use the person's own words and metrics."},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.4,
                            "max_tokens": 400
                        }
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        raw_summary = result["choices"][0]["message"]["content"].strip()
                        
                        # Strip quotes if wrapped
                        if raw_summary.startswith('"') and raw_summary.endswith('"'):
                            raw_summary = raw_summary[1:-1].strip()
                        
                        # Strip garbage prefixes
                        garbage_prefixes = [
                            "i'm happy to help", "here is", "here are", "sure!",
                            "certainly!", "of course!", "i'd be glad", "summary:",
                            "professional summary:", "here's",
                        ]
                        lower_summary = raw_summary.lower()
                        for prefix in garbage_prefixes:
                            if lower_summary.startswith(prefix):
                                for break_char in ['.\n', '. ', '\n', '? ', '! ', ': ']:
                                    idx = raw_summary.find(break_char, len(prefix))
                                    if idx != -1:
                                        raw_summary = raw_summary[idx + len(break_char):].strip()
                                        break
                                break
                        
                        # Validate
                        if not _is_generic_summary(raw_summary) and len(raw_summary) >= 40:
                            print(f"[Summary] Generated with {model}: {raw_summary[:80]}...")
                            return raw_summary
                        else:
                            print(f"[Summary] {model} output too generic, trying fallback...")
                            
            except Exception as e:
                print(f"[Summary Gen Error with {model}] {e}")
                continue
    
    # --- FALLBACK: TEMPLATE-BASED ---
    print("[Summary] Using template fallback")
    fallback = _build_fallback_summary(session)
    
    # Validate fallback too
    if not _is_generic_summary(fallback) and len(fallback) >= 30:
        return fallback
    
    # Ultimate fallback
    if full_name and job_title:
        return f"{full_name} brings practical expertise as a {job_title}, with skills in {', '.join(top_skills[:4]) if top_skills else 'relevant technical areas'}."
    elif full_name:
        return f"{full_name} brings practical expertise and a hands-on approach to solving real problems."
    else:
        return "Experienced professional with practical expertise and a hands-on approach to delivering results."


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
    remaining_cats = prioritized_cats[15:]
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
    return {"Other Skills": skills_list}


# =============================================================================
# GROQ EXTRACTION
# =============================================================================

async def groq_extract(transcript: str, field: str) -> str:
    """Send transcript to Groq and extract single field."""
    if not GROQ_API_KEY:
        return transcript
    
    # Determine what to extract based on field
    if field == "_decision":
        prompt = "The user is answering 'Add another job?' Classify their response. If they want to add another job, return 'yes'. If they're done adding jobs, return 'done'. Return ONLY one word: yes or done."
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
    elif field == "skills" or field == "skills_review":
        prompt = "Extract skills as comma-separated list. Return ONLY the list."
    elif field.startswith("summary_q"):
        prompt = "Extract the user's answer exactly as they wrote it. Return ONLY their text, no modifications."
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
        
        # Handle BACK action — ONLY allowed during simple steps and experience
        # (education, skills, optional phases have broken go_back logic — disable for now)
        context = session.get("context", {})
        phase = context.get("phase", "")
        in_safe_back_phase = (
            not phase or  # simple steps before experience
            phase == "experience" or
            (session["step_index"] <= len(SIMPLE_STEPS) and session["step_index"] > 0)
        )
        
        if action == "back" and in_safe_back_phase:
            step = go_back(session)
            return {
                "session_id": session_id,
                "question": step["question"],
                "field": step["field"],
                "context_label": step.get("context_label", ""),
                "step_index": session["step_index"],
                "done": False,
                "can_go_back": session["step_index"] > 0 or context.get("exp_substep", 0) > 0 or context.get("in_bullet_loop", False),
                "show_add_job": step.get("show_add_job", False),
                "action": "back"
            }
        elif action == "back":
            # Back is broken for education/skills/optional phases — just stay put
            current_step = get_next_step(session)
            return {
                "session_id": session_id,
                "question": current_step["question"] + " (Note: Back navigation is not available here. Just answer or say 'skip' to continue.)",
                "field": current_step["field"],
                "context_label": current_step.get("context_label", ""),
                "step_index": session["step_index"],
                "done": False,
                "can_go_back": False,
                "show_add_job": current_step.get("show_add_job", False),
                "action": "answer"
            }

        # Handle FINISH_JOBS action — done with all jobs, move to summary interview
        if action == "finish_jobs":
        
            context = session.get("context", {})
            if context.get("phase") == "experience":
                # Save current experience data
                exp_list = context.get("experience", [])
                if exp_list:
                    session["data"]["experience"] = exp_list
                # Transition to summary interview (reordered - before skills)
                context["phase"] = "summary_interview"
                context["summary_step"] = 0
                step = get_next_step(session)
                return {
                    "session_id": session_id,
                    "question": step["question"],
                    "field": step["field"],
                    "context_label": step.get("context_label", ""),
                    "step_index": session["step_index"],
                    "done": False,
                    "can_go_back": True,
                    "show_add_job": False,
                    "action": "finish_jobs"
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
                await advance_state(session, "__ADD_JOB__")
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
        
        print(f"[DEBUG] /turn: action={action}, transcript='{transcript}', phase={session.get('context', {}).get('phase')}, exp_substep={session.get('context', {}).get('exp_substep')}, in_bullet_loop={session.get('context', {}).get('in_bullet_loop')}")

        
        step = get_next_step(session)
        field = step["field"]
        
        # Special case: summary field with "auto" — bypass Groq and generate directly
        if field == "summary" and transcript.lower().strip() == "auto":
            extracted = "__AUTO_GENERATE__"
        # For bullet loop, use raw transcript (don't send "done" or bullet text to Groq)
        elif field == "_bullet":
            # Check if user wants to stop adding bullets
            transcript_lower = transcript.lower().strip()
            if transcript_lower in ["done", "no", "n", "finished", "complete", "that's it", "thats it", "skip"]:
                extracted = "done"
            elif transcript_lower in ["yes", "y", "add", "another", "more"]:
                extracted = "yes"
            else:
                extracted = transcript  # Use raw bullet text
        # For skills_review, handle control words directly
        elif field == "skills_review":
            transcript_lower = transcript.lower().strip()
            if transcript_lower in ["done", "yes", "y", "finished", "next", "skip"]:
                extracted = "done"
            else:
                # Extract with Groq for adding new skills
                extracted = await groq_extract(transcript, field)
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
        await advance_state(session, extracted)
        
        # Get updated context after advance
        context = session.get("context", {})
        
        # If we just transitioned to skills_review, categorize skills with Groq
        if context.get("phase") == "skills_review" and not context.get("skills_categorized"):
            skills_raw = session["data"].get("skills", "")
            if skills_raw:
                categorized = await groq_categorize_skills(skills_raw, session)
                context["skills_categorized"] = categorized
        
        # Get next step
        next_step = get_next_step(session)
        
        # Build response
        response = {
            "session_id": session_id,
            "question": next_step["question"],
            "field": next_step["field"],
            "context_label": next_step.get("context_label", ""),
            "step_index": session["step_index"],
            "done": next_step.get("done", False),
            "can_go_back": session["step_index"] > 0 or session.get("context", {}).get("exp_substep", 0) > 0 or session.get("context", {}).get("in_bullet_loop", False),
            "show_add_job": next_step.get("show_add_job", False),
            "is_first_bullet": next_step.get("is_first_bullet", False),
            "bullet_count": next_step.get("bullet_count", 0),
            "job_count": next_step.get("job_count", 0),
            "data_preview": {k: v for k, v in session["data"].items() if k not in ["experience", "education", "projects", "competencies", "community", "certifications"]},
            "extracted": extracted
        }
        
        # Include categorized skills if in skills_review phase
        if next_step["field"] == "skills_review" and context.get("skills_categorized"):
            # Sort skills by weight within each category (highest first)
            sorted_categorized = {}
            for cat, skills in context["skills_categorized"].items():
                if isinstance(skills, list) and skills:
                    # Check if items are dicts (new weighted format) or strings (old format)
                    if isinstance(skills[0], dict):
                        sorted_skills = sorted(skills, key=lambda x: x.get("weight", 50), reverse=True)
                    else:
                        # Legacy format: convert to weighted dicts with neutral weight
                        sorted_skills = [{"name": s, "weight": 50} for s in skills]
                    sorted_categorized[cat] = sorted_skills
            response["skills_categorized"] = sorted_categorized
        
        return response
        
    except Exception as e:
        print(f"[Voice Turn Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/save")
async def voice_save(request: Request):
    """Save session state for later resumption."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "Invalid session"}, status_code=400)
        
        session = voice_sessions[session_id]
        
        # Return full session state for client storage
        return {
            "success": True,
            "session_id": session_id,
            "state": {
                "session_id": session_id,
                "step_index": session["step_index"],
                "data": session["data"],
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
        
        # Restore session
        voice_sessions[session_id] = {
            "session_id": session_id,
            "step_index": state.get("step_index", 0),
            "data": state.get("data", {}),
            "context": state.get("context", {}),
            "history": state.get("history", []),
            "done": state.get("done", False)
        }
        
        session = voice_sessions[session_id]
        step = get_next_step(session)
        
        return {
            "success": True,
            "session_id": session_id,
            "question": step["question"],
            "field": step["field"],
            "context_label": step.get("context_label", ""),
            "step_index": session["step_index"],
            "done": step.get("done", False),
            "can_go_back": session["step_index"] > 0 or session.get("context", {}).get("exp_substep", 0) > 0 or session.get("context", {}).get("in_bullet_loop", False),
            "show_add_job": step.get("show_add_job", False),
            "is_first_bullet": step.get("is_first_bullet", False),
            "bullet_count": step.get("bullet_count", 0),
            "job_count": step.get("job_count", 0),
            "skills_categorized": session.get("context", {}).get("skills_categorized", {})
        }
        
    except Exception as e:
        print(f"[Voice Load Error] {e}")
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
        context = session.get("context", {})
        
        # Parse skills
        if isinstance(resume_data.get("skills"), str):
            resume_data["skills"] = [s.strip() for s in resume_data["skills"].split(",") if s.strip()]
        
        # Build weighted skills list for resume output
        weighted_skills = []
        skills_categorized = context.get("skills_categorized", {})
        if skills_categorized:
            for cat_skills in skills_categorized.values():
                for skill in cat_skills:
                    if isinstance(skill, dict):
                        weighted_skills.append(skill)
                    else:
                        weighted_skills.append({"name": skill, "weight": 50, "category": "Other Skills"})
        
        # Sort by weight descending
        if weighted_skills:
            weighted_skills.sort(key=lambda x: x.get("weight", 50), reverse=True)
            resume_data["skills_weighted"] = weighted_skills
            resume_data["skills_ordered"] = [s["name"] for s in weighted_skills]
        else:
            resume_data["skills_weighted"] = []
            resume_data["skills_ordered"] = resume_data.get("skills", [])
        
        return {
            "success": True,
            "session_id": session_id,
            "data": resume_data,
            "context": context
        }
        
    except Exception as e:
        print(f"[Voice Finish Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/preview")
async def voice_preview(request: Request):
    """Generate resume preview HTML from voice session data."""
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        template_style = body.get("template_style", "professional")
        
        if not session_id or session_id not in voice_sessions:
            return JSONResponse({"error": "Invalid session"}, status_code=400)
        
        session = voice_sessions[session_id]
        resume_data = session["data"].copy()
        context = session.get("context", {})
        
        # Ensure skills are flat list for preview
        if isinstance(resume_data.get("skills"), str):
            resume_data["skills"] = [s.strip() for s in resume_data["skills"].split(",") if s.strip()]
        
        # Add experience from context if not in data
        if not resume_data.get("experience") and context.get("experience"):
            resume_data["experience"] = context.get("experience", [])
        
        # Add education from context if not in data
        if not resume_data.get("education") and context.get("education"):
            resume_data["education"] = context.get("education", [])
        
        # Add projects from context if not in data
        if not resume_data.get("projects") and context.get("projects"):
            resume_data["projects"] = context.get("projects", [])
        
        # Add competencies from context if not in data
        if not resume_data.get("competencies") and context.get("competencies"):
            resume_data["competencies"] = context.get("competencies", [])
        
        # Add community from context if not in data
        if not resume_data.get("community") and context.get("community"):
            resume_data["community"] = context.get("community", [])
        
        # Add certifications from context if not in data
        if not resume_data.get("certifications") and context.get("certifications"):
            resume_data["certifications"] = context.get("certifications", [])
        
        # Categorize skills for display
        skills_list = resume_data.get("skills", [])
        
        # Lazy import to avoid circular dependency
        from main import generate_preview_html, categorize_skills
        resume_data["skills_categorized"] = categorize_skills(skills_list)
        
        # Generate preview HTML
        preview_html = generate_preview_html(resume_data, template_style)
        
        return {
            "success": True,
            "session_id": session_id,
            "preview_html": preview_html,
            "template_style": template_style
        }
        
    except Exception as e:
        print(f"[Voice Preview Error] {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


# =============================================================================
# VOICE ROUTER SETUP
# =============================================================================

router.include_in_schema = True
