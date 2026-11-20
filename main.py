# ================================================
# ARCHITECTURE REFERENCE
# See: docs/architecture/decisions.md
# Key decisions: Server-authoritative builds, flat-dict state machine,
# voice session persistence, PDF/DOCX export, Render deployment config.
#
# Known issues: docs/known-blockers.md
# Setup & run: docs/setup-and-run.md
# Project hub: docs/project-memory.md
# ================================================

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import functools
import hashlib
import json
import logging
import os
import re
import smtplib
import unicodedata
import httpx
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from typing import Dict, Any
from xml.sax.saxutils import escape as xml_escape
# python-docx and reportlab are imported inside generate_docx()/generate_pdf():
# they are only needed at download time and cost ~60 ms of every cold start.

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Environment detection
APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production"

# Load the appropriate .env file
if IS_PRODUCTION:
    env_file = ".env.production"
else:
    # Development: prefer .env.development, fallback to .env
    env_file = ".env.development" if os.path.exists(".env.development") else ".env"

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), env_file)

if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Persistent resume storage (NOT temp — survives restarts)
RESUME_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "resumes")
os.makedirs(RESUME_STORAGE_DIR, exist_ok=True)

import stripe

# Stripe Configuration — loaded from environment
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_STUDENT_PRICE_ID = os.getenv("STRIPE_STUDENT_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

stripe.api_key = STRIPE_SECRET_KEY

# Base URL for redirects — must be set in production
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Email Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

def send_verification_email(to_email: str, token: str, base_url: str) -> bool:
    """Send student verification email with unique link"""
    try:
        if not SMTP_USER or not SMTP_PASS:
            return False
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Verify Your Student Status - AIE ResuMaker'
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        
        # Verification link
        verify_link = f"{base_url}/verify-student?token={token}"
        
        # HTML email body
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 30px; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">🎓 AIE ResuMaker</h1>
                <p style="color: #e0e7ff; margin: 10px 0 0 0;">Student Verification</p>
            </div>
            
            <div style="background: #f8fafc; padding: 30px; border-radius: 0 0 12px 12px; border: 1px solid #e2e8f0; border-top: none;">
                <p style="font-size: 16px; color: #334155; margin-bottom: 20px;">
                    Hello,
                </p>
                
                <p style="font-size: 16px; color: #334155; margin-bottom: 20px;">
                    You requested student pricing ($4.99) for AIE ResuMaker. Click the button below to verify your student status:
                </p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verify_link}" 
                       style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); 
                              color: white; padding: 14px 32px; text-decoration: none; 
                              border-radius: 8px; font-size: 16px; font-weight: bold; 
                              display: inline-block;">
                        ✅ Verify Student Status
                    </a>
                </div>
                
                <p style="font-size: 14px; color: #64748b; margin-bottom: 20px;">
                    Or copy and paste this link:
                </p>
                
                <p style="font-size: 13px; color: #475569; background: #f1f5f9; padding: 12px; border-radius: 6px; word-break: break-all;">
                    {verify_link}
                </p>
                
                <p style="font-size: 14px; color: #94a3b8; margin-top: 30px;">
                    This link expires in 24 hours. If you didn't request this, please ignore this email.
                </p>
                
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
                
                <p style="font-size: 12px; color: #94a3b8; text-align: center;">
                    AIE ResuMaker | Built in the US for US students and job seekers
                </p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
        
        return True
        
    except Exception:
        logger.exception("[Student Email] verification email not sent")
        return False


from voice_api import router as voice_router, voice_sessions as voice_session_store, http_client, LLM_API_KEY

app = FastAPI(title="AIE ResuMaker", version="1.0")
app.include_router(voice_router)

@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    """URLs from asset_url() carry the file's content hash, so they can never go
    stale: cache them for a year. Any other /static request must revalidate,
    which costs a 304, not a re-download."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/") and response.status_code in (200, 304):
        version = _asset_versions.get(path[len("/static/"):])
        if version and request.query_params.get("v") == version:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
    return response

@app.head("/")
@app.get("/healthz")
async def health_check():
    return {"status": "ok", "env": APP_ENV, "llm": bool(LLM_API_KEY)}

# O*NET API Configuration
ONET_API_KEY = os.getenv("ONET_API_KEY", "AYRvP-2AaMc-2BKqY-4UFda")
ONET_BASE_URL = "https://api-v2.onetcenter.org"

# Setup templates and static
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(BASE_DIR, "templates")
static_dir = os.path.join(BASE_DIR, "static")

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Setup templates
templates = Jinja2Templates(directory=templates_dir)

# Link static files with {{ asset_url('app.js') }}: the ?v= is a hash of the
# file's bytes, so editing a file changes its URL on the next deploy and there
# is nothing to bump by hand.
_asset_versions: Dict[str, str] = {}


def asset_url(path: str) -> str:
    version = _asset_versions.get(path)
    if version is None:
        try:
            with open(os.path.join(static_dir, path), "rb") as f:
                version = hashlib.sha256(f.read()).hexdigest()[:12]
        except OSError:
            return f"/static/{path}"
        _asset_versions[path] = version
    return f"/static/{path}?v={version}"


templates.env.globals["asset_url"] = asset_url



# Load Fortune 1000 companies
COMPANIES_FILE = os.path.join(BASE_DIR, "data", "companies.json")
companies = []
try:
    with open(COMPANIES_FILE, 'r') as f:
        companies = json.load(f)
except:
    # Fallback list if file not found
    companies = [
        "Walmart", "Amazon", "Apple", "Costco", "JPMorgan Chase",
        "Microsoft", "Google", "Meta", "Berkshire Hathaway",
        "Johnson & Johnson", "UnitedHealth Group", "Exxon Mobil",
        "Chevron", "Home Depot", "Bank of America", "Wells Fargo",
        "Citigroup", "Goldman Sachs", "Morgan Stanley",
        "Procter & Gamble", "AT&T", "Verizon", "Comcast",
        "CVS Health", "Cardinal Health", "McKesson", "Cigna",
        "Anthem", "Lowe's", "Intel", "IBM", "Oracle", "Cisco",
        "Qualcomm", "HP", "Dell Technologies", "General Electric",
        "Ford Motor", "General Motors", "Tesla", "PepsiCo",
        "Coca-Cola", "Kraft Heinz", "Mondelez", "Colgate-Palmolive",
        "Nike", "Starbucks", "McDonald's", "Chipotle", "Target",
        "Best Buy", "Kroger", "Whole Foods", "Gap", "Nordstrom",
        "Macy's", "Kohl's", "Dollar General", "Walgreens",
        "Rite Aid", "HCA Healthcare", "Tenet Healthcare",
        "LabCorp", "Quest Diagnostics", "3M", "Honeywell",
        "Lockheed Martin", "Boeing", "Raytheon", "General Dynamics",
        "Northrop Grumman", "AECOM", "Jacobs Engineering", "Fluor",
        "Bechtel", "Turner Construction", "PulteGroup", "Lennar",
        "D.R. Horton", "Toll Brothers", "Prologis", "Simon Property",
        "Equinix", "Digital Realty", "American Tower", "Crown Castle"
    ]


# Load US cities data
CITIES_FILE = os.path.join(BASE_DIR, "data", "cities.json")
us_cities_data = {"states": {}, "cities_by_state": {}}
try:
    with open(CITIES_FILE, 'r') as f:
        us_cities_data = json.load(f)
except:
    pass


# Load education data
UNIVERSITIES_FILE = os.path.join(BASE_DIR, "data", "universities.json")
DEGREES_FILE = os.path.join(BASE_DIR, "data", "degrees.json")
FIELDS_FILE = os.path.join(BASE_DIR, "data", "fields_of_study.json")

universities = []
degrees = []
fields_of_study = []

try:
    with open(UNIVERSITIES_FILE, 'r') as f:
        universities = json.load(f)
except:
    pass

try:
    with open(DEGREES_FILE, 'r') as f:
        degrees = json.load(f)
except:
    pass

try:
    with open(FIELDS_FILE, 'r') as f:
        fields_of_study = json.load(f)
except:
    pass

# Load skill categories for auto-grouping
SKILL_CATEGORIES_FILE = os.path.join(BASE_DIR, "data", "skill_categories.json")
skill_categories = {}
skill_to_category = {}

def _load_skill_categories():
    """Load skill categories from JSON and build reverse lookup map"""
    global skill_categories, skill_to_category
    try:
        with open(SKILL_CATEGORIES_FILE, 'r') as f:
            data = json.load(f)
            skill_categories = data.get("categories", {})
            # Build reverse lookup: skill_lower -> category_name
            for category, skills in skill_categories.items():
                if category == "Other":
                    continue
                for skill in skills:
                    skill_to_category[skill.lower()] = category
    except Exception as e:
        skill_categories = {}
        skill_to_category = {}

_load_skill_categories()

def categorize_skills(skills_list):
    """Categorize a flat list of skills into grouped dict.
    
    Returns dict like {"Languages": ["Python", "JavaScript"], "Cloud & DevOps": ["AWS"]}
    Unmatched skills go into "Other" category.
    """
    if not skills_list:
        return {}
    
    grouped = {cat: [] for cat in skill_categories.keys() if cat != "Other"}
    grouped["Other"] = []
    matched = set()
    
    for user_skill in skills_list:
        user_skill_stripped = user_skill.strip()
        user_skill_lower = user_skill_stripped.lower()
        found = False
        
        # 1. Exact match in reverse lookup
        if user_skill_lower in skill_to_category:
            category = skill_to_category[user_skill_lower]
            if user_skill_lower not in matched:
                grouped[category].append(user_skill_stripped)
                matched.add(user_skill_lower)
            found = True
        
        # 2. Substring match: user_skill is contained in a known skill
        if not found:
            for known_skill, category in skill_to_category.items():
                if user_skill_lower in known_skill or known_skill in user_skill_lower:
                    if user_skill_lower not in matched:
                        grouped[category].append(user_skill_stripped)
                        matched.add(user_skill_lower)
                    found = True
                    break
        
        # 3. Word-by-word partial match for multi-word skills
        if not found and " " in user_skill_lower:
            words = user_skill_lower.split()
            for word in words:
                if len(word) > 2 and word in skill_to_category:
                    category = skill_to_category[word]
                    if user_skill_lower not in matched:
                        grouped[category].append(user_skill_stripped)
                        matched.add(user_skill_lower)
                    found = True
                    break
        
        if not found:
            grouped["Other"].append(user_skill_stripped)
    
    # Remove empty categories
    return {k: v for k, v in grouped.items() if v}

import secrets

# In-memory storage for demo (use Redis/DB in production)
resumes = {}

def save_resume_json(resume_id: str, data: dict):
    """Persist resume data to disk as JSON sidecar so it survives restarts."""
    try:
        filepath = os.path.join(RESUME_STORAGE_DIR, f"{resume_id}.json")
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def load_resume_from_disk(resume_id: str) -> dict | None:
    """Load resume data from JSON sidecar. Returns None if not found."""
    try:
        filepath = os.path.join(RESUME_STORAGE_DIR, f"{resume_id}.json")
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None

def get_resume(resume_id: str) -> dict | None:
    """Get resume data from memory, falling back to disk."""
    if resume_id in resumes:
        return resumes[resume_id]
    # Disk fallback
    data = load_resume_from_disk(resume_id)
    if data:
        resumes[resume_id] = data  # restore to memory
        return data
    return None

# Student verification tokens: {token: {email: str, verified: bool, expires: datetime}}
student_verifications = {}

# Referral tracking: {code: {created_by: str, created_at: datetime, visits: int, conversions: int}}
referral_codes = {}

# Referral visits log: [{code: str, ip: str, timestamp: datetime, converted: bool}]
referral_visits = []


def is_edu_email(email: str) -> bool:
    """Check if email is a .edu address"""
    return email.lower().endswith('.edu')


# Test mode bypass for student verification
TEST_EDU_EMAILS = ["studentprice@test.edu", "test@student.edu", "demo@edu.test"]


def is_test_edu_email(email: str) -> bool:
    """Check if email is a test .edu email for development"""
    return email.lower() in TEST_EDU_EMAILS


def generate_verification_token() -> str:
    """Generate a unique verification token"""
    return secrets.token_urlsafe(32)


@app.post("/api/verify-edu")
async def verify_edu_email(request: Request):
    """Send verification link to .edu email"""
    try:
        data = await request.json()
        email = data.get("email", "").strip().lower()

        if not email:
            return JSONResponse({"error": "Email is required"}, status_code=400)

        # Temporarily removed .edu check for testing
        # if not is_edu_email(email):
        #     return JSONResponse({"error": "Must be a .edu email address"}, status_code=400)

        # Test mode: auto-verify test emails
        if APP_ENV == "development" and is_test_edu_email(email):
            token = generate_verification_token()
            student_verifications[token] = {
                "email": email,
                "verified": True,
                "expires": datetime.now() + timedelta(hours=24)
            }
            return {
                "success": True,
                "message": "Test email auto-verified!",
                "dev_token": token,
                "auto_verified": True
            }

        # Generate verification token
        token = generate_verification_token()
        expires = datetime.now() + timedelta(hours=24)

        student_verifications[token] = {
            "email": email,
            "verified": False,
            "expires": expires
        }

        # Send verification email
        email_sent = send_verification_email(email, token, BASE_URL)

        if email_sent:
            return {
                "success": True,
                "message": "Verification link sent to your .edu email",
                "dev_token": token if APP_ENV == "development" else None
            }
        else:
            return {
                "success": True,
                "message": "Email configured. Check your inbox.",
                "dev_token": token if APP_ENV == "development" else None,
                "warning": "If email doesn't arrive, use dev token for testing"
            }

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/verify-student")
async def verify_student_token(request: Request, token: str = ""):
    """Verify student status via email link"""
    try:
        if not token:
            return HTMLResponse("""
            <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h2 style="color: #dc2626;">❌ Missing Token</h2>
                <p>No verification token provided.</p>
            </body></html>
            """)

        if token not in student_verifications:
            return HTMLResponse("""
            <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h2 style="color: #dc2626;">❌ Invalid Link</h2>
                <p>This verification link is invalid or has already been used.</p>
            </body></html>
            """)

        verification = student_verifications[token]

        # Check if expired
        if datetime.now() > verification["expires"]:
            del student_verifications[token]
            return HTMLResponse("""
            <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                <h2 style="color: #dc2626;">⏰ Link Expired</h2>
                <p>This verification link has expired. Please request a new one.</p>
            </body></html>
            """)

        # Mark as verified
        verification["verified"] = True

        return HTMLResponse(f"""
        <html><body style="font-family: Arial; text-align: center; padding: 50px; background: #f0fdf4;">
            <h2 style="color: #16a34a;">✅ Student Status Verified!</h2>
            <p>Your .edu email <strong>{verification["email"]}</strong> has been verified.</p>
            <p>You can now close this tab and return to AIE ResuMaker to complete your student purchase.</p>
            <br>
            <a href="/build" style="background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">Return to AIE ResuMaker</a>
        </body></html>
        """)

    except Exception as e:
        return HTMLResponse(f"""
        <html><body style="font-family: Arial; text-align: center; padding: 50px;">
            <h2 style="color: #dc2626;">❌ Error</h2>
            <p>{str(e)}</p>
        </body></html>
        """)


@app.post("/api/verify-edu-code")
async def verify_edu_code(request: Request):
    """Legacy endpoint - now uses token verification"""
    try:
        data = await request.json()
        token = data.get("token", "").strip()

        if not token:
            return JSONResponse({"error": "Token is required"}, status_code=400)

        if token not in student_verifications:
            return JSONResponse({"error": "Invalid token"}, status_code=400)

        verification = student_verifications[token]

        if datetime.now() > verification["expires"]:
            del student_verifications[token]
            return JSONResponse({"error": "Token expired"}, status_code=400)

        if verification["verified"]:
            return {
                "success": True,
                "verified": True,
                "email": verification["email"]
            }

        return JSONResponse({"error": "Not verified yet. Check your email for the verification link."}, status_code=400)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/verify-edu-status")
async def check_edu_status(email: str = "", token: str = ""):
    """Check if student email is verified"""
    try:
        # Check by token
        if token and token in student_verifications:
            verification = student_verifications[token]
            if verification["verified"] and datetime.now() <= verification["expires"]:
                return {
                    "verified": True,
                    "is_student": True,
                    "email": verification["email"]
                }

        # Check by email
        if email:
            for token_key, verification in student_verifications.items():
                if verification["email"] == email.lower() and verification["verified"]:
                    if datetime.now() <= verification["expires"]:
                        return {
                            "verified": True,
                            "is_student": True,
                            "email": email
                        }

        return {"verified": False, "is_student": is_edu_email(email)}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="landing.html")

@app.get("/voice_chat", response_class=HTMLResponse)
async def voice_chat_page(request: Request):
    """Direct voice chat page."""
    return templates.TemplateResponse(request=request, name="voice_chat.html")

@app.get("/build", response_class=HTMLResponse)
async def build_page(request: Request):
    ref_code = request.query_params.get("ref", "")
    mode = request.query_params.get("mode", "")
    voice_session = request.query_params.get("voice_session", "")
    
    # Track referral visit if ref code provided
    if ref_code and ref_code in referral_codes:
        referral_codes[ref_code]["visits"] += 1
        referral_visits.append({
            "code": ref_code,
            "ip": request.client.host if request.client else "unknown",
            "timestamp": datetime.now(),
            "converted": False
        })
    
    # Check for voice session data (new voice_sessions from voice_api)
    voice_data = None
    if voice_session and voice_session in voice_session_store:
        raw_data = voice_session_store[voice_session].get("data", {}).copy()
        # Parse JSON string fields into proper arrays
        for field in ["experience", "education"]:
            val = raw_data.get(field)
            if isinstance(val, str):
                try:
                    raw_data[field] = json.loads(val)
                except Exception:
                    raw_data[field] = []
        # Parse skills string into array
        if isinstance(raw_data.get("skills"), str):
            raw_data["skills"] = [s.strip() for s in raw_data["skills"].split(",") if s.strip()]
        voice_data = raw_data
    
    # Determine mode
    if mode == "voice":
        return templates.TemplateResponse(request=request, name="voice_chat.html")
    elif mode == "form":
        return templates.TemplateResponse(request=request, name="index.html", context={
            "voice_data": json.dumps(voice_data) if voice_data else "null",
            "session_id": voice_session
        })
    
    # Auto-detect: mobile -> voice, desktop -> form
    user_agent = request.headers.get("user-agent", "").lower()
    is_mobile = any(device in user_agent for device in ["iphone", "android", "ipad", "mobile"])
    
    if is_mobile:
        return templates.TemplateResponse(request=request, name="voice_chat.html")
    else:
        ctx = {
            "voice_data": json.dumps(voice_data) if voice_data else "null",
            "session_id": voice_session
        }
        return templates.TemplateResponse(request=request, name="index.html", context=ctx)

@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    """Terms of Service page"""
    return templates.TemplateResponse(request=request, name="terms.html")

@app.get("/api/jobs/search")
async def search_jobs(query: str = ""):
    """Search job titles via O*NET API proxy"""
    if not query or len(query) < 2:
        return {"results": []}
    
    try:
        response = await http_client.get(
            f"{ONET_BASE_URL}/online/search",
            params={"keyword": query, "start": 1, "end": 20},
            headers={"X-API-Key": ONET_API_KEY},
            timeout=5.0
        )

        if response.status_code == 200:
            data = response.json()
            results = []
            if "occupation" in data:
                for occ in data["occupation"]:
                    results.append({
                        "code": occ.get("code", ""),
                        "title": occ.get("title", ""),
                        "tags": occ.get("tags", [])
                    })
            return {"results": results[:10]}
        else:
            return {"results": [], "error": f"API returned {response.status_code}"}

    except Exception as e:
        return {"results": [], "error": str(e)}

@app.get("/api/jobs/{job_code}")
async def get_job_details(job_code: str):
    """Get detailed job information from O*NET"""
    try:
        response = await http_client.get(
            f"{ONET_BASE_URL}/online/occupations/{job_code}",
            headers={"X-API-Key": ONET_API_KEY},
            timeout=5.0
        )

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API returned {response.status_code}"}

    except Exception as e:
        return {"error": str(e)}

@app.get("/api/jobs/{job_code}/summary")
async def get_job_summary(job_code: str):
    """Get job summary for resume suggestions"""
    try:
        response = await http_client.get(
            f"{ONET_BASE_URL}/online/occupations/{job_code}/summary",
            headers={"X-API-Key": ONET_API_KEY},
            timeout=5.0
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "skills": data.get("skills", []),
                "knowledge": data.get("knowledge", []),
                "abilities": data.get("abilities", [])
            }
        else:
            return {"error": f"API returned {response.status_code}"}

    except Exception as e:
        return {"error": str(e)}

def _load_voice_session_data(session_id: str):
    """Return a voice session's stored 'data' dict, from memory or disk. None if missing."""
    if not session_id:
        return None
    sess = voice_session_store.get(session_id)
    if sess is None:
        path = os.path.join(os.path.dirname(__file__), "voice_sessions", f"{session_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                sess = json.load(f)
        except Exception:
            return None
    return sess.get("data", {}) if isinstance(sess, dict) else None


@app.post("/api/build")
async def build_resume(
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    state: str = Form(""),
    city: str = Form(""),
    linkedin: str = Form(""),
    website: str = Form(""),
    summary: str = Form(""),
    experience: str = Form(""),
    education: str = Form(""),
    skills: str = Form(""),
    projects: str = Form(""),
    competencies: str = Form(""),
    community: str = Form(""),
    certifications: str = Form(""),
    industry: str = Form(""),
    template_style: str = Form("professional"),
    voice_session: str = Form("")
):
    """Build resume and return download URLs"""
    
    # === SESSION-AUTHORITATIVE BUILD (voice/mobile path) ===
    # When a voice_session is present, the stored session data is the source of
    # truth for the rich repeating sections (experience/education/projects/etc.),
    # bypassing the lossy form-DOM round-trip. Desktop form users (no voice_session)
    # keep the original form-DOM path unchanged.
    session_data = _load_voice_session_data(voice_session)
    session_address = ""
    if session_data:
        def _as_list(v):
            if isinstance(v, list):
                return v
            if isinstance(v, str) and v.strip():
                try:
                    return json.loads(v)
                except Exception:
                    return []
            return []
        exp_list  = _as_list(session_data.get("experience"))
        edu_list  = _as_list(session_data.get("education"))
        proj_list = _as_list(session_data.get("projects"))
        comp_list = _as_list(session_data.get("competencies"))
        comm_list = _as_list(session_data.get("community"))
        cert_list = _as_list(session_data.get("certifications"))
        # Prefer an edited form summary if provided, else the session summary
        summary = summary.strip() or session_data.get("summary", "")
        sk = session_data.get("skills")
        if isinstance(sk, list):
            skills_list = [s for s in sk if s]
        elif isinstance(sk, str) and sk.strip():
            skills_list = [s.strip() for s in re.split(r"[|,]", sk) if s.strip()]
        else:
            skills_list = [s.strip() for s in skills.split("|") if s.strip()]
        skills_categorized = session_data.get("skills_categorized") or categorize_skills(skills_list)
        session_address = session_data.get("address", "")
    else:
        # Original form-DOM path (desktop form users)
        exp_list = json.loads(experience) if experience else []
        edu_list = json.loads(education) if education else []
        skills_list = [s.strip() for s in skills.split("|") if s.strip()]
        proj_list = json.loads(projects) if projects else []
        comp_list = json.loads(competencies) if competencies else []
        comm_list = json.loads(community) if community else []
        cert_list = json.loads(certifications) if certifications else []
        skills_categorized = categorize_skills(skills_list)
    # === END SESSION-AUTHORITATIVE BUILD ===
    
    # Build location string from state and city
    location_parts = []
    if city: location_parts.append(city)
    if state: location_parts.append(state)
    location = ", ".join(location_parts) if location_parts else ""
    
    resume_data = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "location": location,
        "address": session_address,
        "linkedin": linkedin,
        "website": website,
        "summary": summary,
        "experience": exp_list,
        "education": edu_list,
        "skills": skills_list,
        "skills_categorized": skills_categorized,
        "projects": proj_list,
        "competencies": comp_list,
        "community": comm_list,
        "certifications": cert_list,
        "industry": industry,
        "template_style": template_style,
        "created_at": datetime.now().isoformat()
    }
    
    resume_id = f"{full_name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    resumes[resume_id] = resume_data
    save_resume_json(resume_id, resume_data)
    # DOCX/PDF are rendered on first download (see download_resume), not on
    # every preview build.

    return {
        "success": True,
        "resume_id": resume_id,
        "download_url": f"/api/download/{resume_id}",
        "download_url_pdf": f"/api/download/{resume_id}?format=pdf",
        "preview_html": generate_preview_html(resume_data, template_style)
    }

def generate_docx(resume_id: str, data: dict):
    """Generate Word document"""
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    
    sections = doc.sections[0]
    sections.top_margin = Inches(0.75)
    sections.bottom_margin = Inches(0.75)
    sections.left_margin = Inches(0.75)
    sections.right_margin = Inches(0.75)
    
    # Name - centered, uppercase, bold
    name = doc.add_paragraph()
    name_run = name.add_run(data["full_name"])
    name_run.bold = True
    name_run.font.size = Pt(18)
    name_run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Contact info
    address = data.get("address", "")
    contact_parts = []
    if address: contact_parts.append(address)
    elif data.get("location"): contact_parts.append(data["location"])
    if data.get("phone"): contact_parts.append(data["phone"])
    if data.get("email"): contact_parts.append(data["email"])
    if data.get("linkedin"): contact_parts.append(data["linkedin"])
    
    if contact_parts:
        contact = doc.add_paragraph(" | ".join(contact_parts))
        contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact.runs[0].font.size = Pt(9)
        contact.runs[0].font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    
    # Horizontal line
    doc.add_paragraph("_" * 80).runs[0].font.color.rgb = RGBColor(0xcc, 0xcc, 0xcc)
    
    # Professional Summary
    if data.get("summary"):
        heading = doc.add_paragraph()
        heading_run = heading.add_run("PROFESSIONAL SUMMARY")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        summary = doc.add_paragraph(data["summary"])
        summary.paragraph_format.space_after = Pt(12)
        summary.runs[0].font.size = Pt(10)
    
    # Technical Skills
    skills_categorized = data.get("skills_categorized", {})
    skills_flat = data.get("skills", [])
    
    if skills_categorized or skills_flat:
        heading = doc.add_paragraph()
        heading_run = heading.add_run("TECHNICAL SKILLS")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        # Handle categorized skills dict
        if skills_categorized and isinstance(skills_categorized, dict):
            for cat, skills in skills_categorized.items():
                if skills:
                    cat_para = doc.add_paragraph()
                    cat_run = cat_para.add_run(f"{cat}: ")
                    cat_run.bold = True
                    cat_run.font.size = Pt(10)
                    
                    # Extract skill names (handle both string list and dict list)
                    skill_names = []
                    for s in skills:
                        if isinstance(s, str):
                            skill_names.append(s)
                        elif isinstance(s, dict):
                            skill_names.append(s.get('name', ''))
                    
                    skills_run = cat_para.add_run(", ".join(skill_names))
                    skills_run.font.size = Pt(10)
        elif isinstance(skills_flat, list):
            # Flat list of strings
            skills_text = ", ".join(skills_flat)
            skills = doc.add_paragraph(skills_text)
            skills.paragraph_format.space_after = Pt(12)
            skills.runs[0].font.size = Pt(10)
        else:
            # Fallback to string
            skills = doc.add_paragraph(str(skills_flat))
            skills.paragraph_format.space_after = Pt(12)
            skills.runs[0].font.size = Pt(10)
    
    # Professional Experience
    if data.get("experience"):
        heading = doc.add_paragraph()
        heading_run = heading.add_run("PROFESSIONAL EXPERIENCE")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        for job in data["experience"]:
            # Job title — Company | Location (dates right-aligned)
            job_header = doc.add_paragraph()
            job_header.paragraph_format.space_after = Pt(2)
            
            title_run = job_header.add_run(f"{job.get('title', '')}")
            title_run.bold = True
            title_run.font.size = Pt(10.5)
            
            if job.get("company"):
                company_run = job_header.add_run(f" — {job['company']}")
                company_run.bold = True
                company_run.font.size = Pt(10.5)
            
            # Location and dates on next line
            location_parts = []
            if job.get("location"): 
                location_parts.append(job["location"])
            elif job.get("city") or job.get("state"):
                if job.get("city"): location_parts.append(job["city"])
                if job.get("state"): location_parts.append(job["state"])
            location_str = ", ".join(location_parts)
            
            if location_str or job.get("dates") or job.get("phone") or job.get("address"):
                loc_date = doc.add_paragraph()
                loc_date.paragraph_format.space_after = Pt(2)
                
                if location_str:
                    loc_run = loc_date.add_run(location_str)
                    loc_run.italic = True
                    loc_run.font.size = Pt(9.5)
                
                if job.get("dates"):
                    if location_str:
                        spacer = loc_date.add_run("  |  ")
                    date_run = loc_date.add_run(job["dates"])
                    date_run.italic = True
                    date_run.font.size = Pt(9.5)
                    date_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
                
                if job.get("phone"):
                    if location_str or job.get("dates"):
                        spacer2 = loc_date.add_run("  |  ")
                    phone_run = loc_date.add_run(job["phone"])
                    phone_run.italic = True
                    phone_run.font.size = Pt(9.5)
                    phone_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            
            if job.get("address"):
                addr = doc.add_paragraph(job["address"])
                addr.paragraph_format.space_after = Pt(2)
                addr.runs[0].italic = True
                addr.runs[0].font.size = Pt(9.5)
                addr.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            
            # Special fields: operators_served, key_rigs
            if job.get("operators_served") or job.get("key_rigs"):
                special = doc.add_paragraph()
                special.paragraph_format.space_after = Pt(4)
                special_parts = []
                if job.get("operators_served"):
                    special_parts.append(f"Key Operators Served: {job['operators_served']}")
                if job.get("key_rigs"):
                    special_parts.append(f"Key Rigs: {job['key_rigs']}")
                special_run = special.add_run(" | ".join(special_parts))
                special_run.font.size = Pt(9)
                special_run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            
            # Description / Bullets
            bullets = job.get('bullets', [])
            description = job.get('description', '')
            
            if bullets and isinstance(bullets, list):
                # Render bullets as a list
                for bullet in bullets:
                    if bullet and isinstance(bullet, str):
                        clean_bullet = bullet.strip()
                        if clean_bullet.startswith('•') or clean_bullet.startswith('-'):
                            clean_bullet = clean_bullet[1:].strip()
                        bullet_para = doc.add_paragraph()
                        bullet_para.paragraph_format.left_indent = Inches(0.2)
                        bullet_para.paragraph_format.space_after = Pt(2)
                        bullet_run = bullet_para.add_run(f"• {clean_bullet}")
                        bullet_run.font.size = Pt(10)
            elif description and isinstance(description, list):
                # Render description list as bullets
                for item in description:
                    if item and isinstance(item, str):
                        clean_item = item.strip()
                        if clean_item.startswith('•') or clean_item.startswith('-'):
                            clean_item = clean_item[1:].strip()
                        bullet_para = doc.add_paragraph()
                        bullet_para.paragraph_format.left_indent = Inches(0.2)
                        bullet_para.paragraph_format.space_after = Pt(2)
                        bullet_run = bullet_para.add_run(f"• {clean_item}")
                        bullet_run.font.size = Pt(10)
            elif description and isinstance(description, str):
                if '\n' in description or '\r' in description:
                    # Multi-line description - render as bullets
                    lines = [line.strip() for line in description.replace('\r', '\n').split('\n') if line.strip()]
                    for line in lines:
                        clean_line = line.strip()
                        if clean_line.startswith('•') or clean_line.startswith('-'):
                            clean_line = clean_line[1:].strip()
                        bullet_para = doc.add_paragraph()
                        bullet_para.paragraph_format.left_indent = Inches(0.2)
                        bullet_para.paragraph_format.space_after = Pt(2)
                        bullet_run = bullet_para.add_run(f"• {clean_line}")
                        bullet_run.font.size = Pt(10)
                else:
                    desc = doc.add_paragraph(description)
                    desc.paragraph_format.space_after = Pt(8)
                    desc.paragraph_format.left_indent = Inches(0.2)
                    desc.runs[0].font.size = Pt(10)
    
    # Projects
    if data.get("projects"):
        heading = doc.add_paragraph()
        heading_run = heading.add_run("PROJECTS")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        for project in data["projects"]:
            if isinstance(project, dict):
                # Project name
                proj_name = doc.add_paragraph()
                proj_name_run = proj_name.add_run(project.get('name', ''))
                proj_name_run.bold = True
                proj_name_run.font.size = Pt(10.5)
                
                # Tech stack
                if project.get("tech"):
                    tech = doc.add_paragraph()
                    tech_run = tech.add_run(project["tech"])
                    tech_run.italic = True
                    tech_run.font.size = Pt(9)
                    tech_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
                
                # Bullets
                proj_bullets = project.get('bullets', [])
                if proj_bullets and isinstance(proj_bullets, list):
                    for bullet in proj_bullets:
                        if bullet and isinstance(bullet, str):
                            clean_bullet = bullet.strip()
                            if clean_bullet.startswith('•') or clean_bullet.startswith('-'):
                                clean_bullet = clean_bullet[1:].strip()
                            bullet_para = doc.add_paragraph()
                            bullet_para.paragraph_format.left_indent = Inches(0.2)
                            bullet_para.paragraph_format.space_after = Pt(2)
                            bullet_run = bullet_para.add_run(f"• {clean_bullet}")
                            bullet_run.font.size = Pt(10)
                elif project.get("description"):
                    if isinstance(project["description"], str):
                        desc = doc.add_paragraph(project["description"])
                        desc.paragraph_format.space_after = Pt(4)
                        desc.runs[0].font.size = Pt(10)
                
                # Result
                if project.get("result"):
                    result = doc.add_paragraph()
                    result_run = result.add_run(project["result"])
                    result_run.italic = True
                    result_run.font.size = Pt(9.5)
                    result_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
    
    # Notable Competencies
    if data.get("competencies"):
        heading = doc.add_paragraph()
        heading_run = heading.add_run("NOTABLE COMPETENCIES")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        for comp in data["competencies"]:
            if isinstance(comp, dict):
                label = comp.get('label', '') or comp.get('name', '')
                desc = comp.get('description', '')
                if label and desc:
                    comp_para = doc.add_paragraph()
                    label_run = comp_para.add_run(f"{label}: ")
                    label_run.bold = True
                    label_run.font.size = Pt(9.5)
                    desc_run = comp_para.add_run(desc)
                    desc_run.font.size = Pt(9.5)
                elif label:
                    comp_para = doc.add_paragraph()
                    label_run = comp_para.add_run(label)
                    label_run.bold = True
                    label_run.font.size = Pt(9.5)
    
    # Education
    if data.get("education"):
        heading = doc.add_paragraph()
        heading_run = heading.add_run("EDUCATION")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        for edu in data["education"]:
            # School — Location
            school = doc.add_paragraph()
            school_run = school.add_run(edu.get('school', ''))
            school_run.bold = True
            school_run.font.size = Pt(10.5)
            
            if edu.get("location"):
                loc_run = school.add_run(f" — {edu['location']}")
                loc_run.bold = True
                loc_run.font.size = Pt(10.5)
            
            # Degree, field, dates
            degree_parts = []
            if edu.get("degree"): degree_parts.append(edu["degree"])
            if edu.get("field"): degree_parts.append(edu["field"])
            if edu.get("dates"): degree_parts.append(edu["dates"])
            if degree_parts:
                degree = doc.add_paragraph(", ".join(degree_parts))
                degree.runs[0].italic = True
                degree.runs[0].font.size = Pt(9.5)
                degree.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            
            # Honors
            if edu.get("honors"):
                honors = doc.add_paragraph(edu["honors"])
                honors.runs[0].font.size = Pt(9)
                honors.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            
            school.paragraph_format.space_after = Pt(8)
    
    # Community Involvement
    if data.get("community"):
        heading = doc.add_paragraph()
        heading_run = heading.add_run("COMMUNITY INVOLVEMENT")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        for item in data["community"]:
            if isinstance(item, dict):
                comm = doc.add_paragraph()
                org = item.get('org', item.get('organization', ''))
                event = item.get('event', '')
                role = item.get('role', '')
                desc = item.get('description', '')
                
                parts = []
                if org: parts.append(org)
                if event: parts.append(event)
                if role: parts.append(f"Role: {role}")
                if desc: parts.append(desc)
                
                comm_run = comm.add_run(' | '.join(parts))
                comm_run.font.size = Pt(10)
    
    # Certifications
    if data.get("certifications"):
        heading = doc.add_paragraph()
        heading_run = heading.add_run("CERTIFICATIONS")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        for cert in data["certifications"]:
            if isinstance(cert, dict):
                cert_para = doc.add_paragraph()
                name_run = cert_para.add_run(cert.get('name', ''))
                name_run.font.size = Pt(10)
                issuer = cert.get('issuer', cert.get('organization', ''))
                if issuer:
                    org_run = cert_para.add_run(f" — {issuer}")
                    org_run.font.size = Pt(10)
                if cert.get("date"):
                    date_run = cert_para.add_run(f", {cert['date']}")
                    date_run.font.size = Pt(9)
                    date_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    
    # References
    refs_data = data.get("references", [])
    if refs_data:
        heading = doc.add_paragraph()
        heading_run = heading.add_run("REFERENCES")
        heading_run.bold = True
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = RGBColor(0x2c, 0x5a, 0xa0)
        
        for ref in refs_data:
            if isinstance(ref, dict):
                ref_para = doc.add_paragraph()
                name_run = ref_para.add_run(ref.get('name', ''))
                name_run.bold = True
                name_run.font.size = Pt(10)
                if ref.get("phone"):
                    phone_run = ref_para.add_run(f" — {ref['phone']}")
                    phone_run.font.size = Pt(10)
    else:
        refs = doc.add_paragraph("*References available upon request*")
        refs.alignment = WD_ALIGN_PARAGRAPH.CENTER
        refs.runs[0].italic = True
        refs.runs[0].font.size = Pt(9)
        refs.paragraph_format.space_before = Pt(16)
    
    output_dir = RESUME_STORAGE_DIR
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{resume_id}.docx")
    doc.save(filepath)
    
    return filepath

def generate_preview_html(data: dict, template_style: str = "professional"):
    """Generate HTML preview of resume based on template style"""
    
    # Build contact line
    contact_parts = []
    if data.get("location"): contact_parts.append(data["location"])
    if data.get("phone"): contact_parts.append(data["phone"])
    if data.get("email"): contact_parts.append(data["email"])
    if data.get("linkedin"): contact_parts.append(data["linkedin"])
    
    contact_line = " | ".join(contact_parts) if contact_parts else ""
    
    # Template-specific CSS
    if template_style == "modern":
        css = _get_modern_css()
    elif template_style == "minimal":
        css = _get_minimal_css()
    else:  # professional (default)
        css = _get_professional_css()
    
    html = f"""
    <div class="resume-preview {template_style}">
        <style>{css}</style>
        <div class="header">
            <div class="name">{data['full_name']}</div>
            <div class="contact">{contact_line}</div>
        </div>
    """
    
    # Rest of the content generation remains the same
    # Professional Summary
    if data.get("summary"):
        html += f"""
        <div class="section-title">Professional Summary</div>
        <div class="summary">{data['summary']}</div>
        """
    
    # Technical Skills
    skills_data = data.get("skills_categorized") or data.get("skills", [])
    if skills_data:
        html += '<div class="section-title">Technical Skills</div>'
        if isinstance(skills_data, dict):
            html += '<div class="skills-grid">'
            for category, skill_list in skills_data.items():
                # Normalize skill_list: dict of {"name": ..., "weight": ...} → list of names
                if skill_list and isinstance(skill_list, list) and len(skill_list) > 0:
                    if isinstance(skill_list[0], dict):
                        skill_names = [s["name"] for s in skill_list if isinstance(s, dict) and "name" in s]
                    else:
                        skill_names = [str(s) for s in skill_list]
                else:
                    skill_names = skill_list if isinstance(skill_list, list) else []
                html += f'''
                <div>
                    <div class="skill-category">{category}</div>
                    <div class="skill-list">{", ".join(skill_names) if skill_names else ""}</div>
                </div>
                '''
            html += '</div>'
        else:
            html += '<div class="skills-grid">'
            html += f'<div class="skill-list">{", ".join(skills_data) if isinstance(skills_data, list) else skills_data}</div>'
            html += '</div>'
    
    # Professional Experience
    if data.get("experience"):
        html += '<div class="section-title">Professional Experience</div>'
        for job in data["experience"]:
            company = job.get('company', '')
            title = job.get('title', '')
            dates = job.get('dates', '')
            location = job.get('location', '')
            description = job.get('description', '')
            
            html += f'''
            <div style="margin-bottom: 10px;">
                <div class="job-header">
                    <span class="job-title-company">{title}{' — ' + company if company else ''}</span>
                    <span class="job-dates">{dates}</span>
                </div>
            '''
            
            # Build location from city/state if not already present
            if not location:
                location_parts = []
                if job.get('city'): location_parts.append(job['city'])
                if job.get('state'): location_parts.append(job['state'])
                location = ", ".join(location_parts)
            
            if location:
                html += f'<div class="job-location">{location}</div>'
            
            if job.get('phone'):
                html += f'<div class="job-contact">Phone: {job["phone"]}</div>'
            
            if job.get('address'):
                html += f'<div class="job-contact">{job["address"]}</div>'
            
            # Handle bullets/description - support both list and string formats
            bullets = job.get('bullets', [])
            description = job.get('description', '')
            
            # If bullets is a list, render as bullet list
            if bullets and isinstance(bullets, list):
                html += '<div class="job-description"><ul>'
                for bullet in bullets:
                    if bullet and isinstance(bullet, str):
                        # Strip bullet markers if present
                        clean_bullet = bullet.strip()
                        if clean_bullet.startswith('•') or clean_bullet.startswith('-'):
                            clean_bullet = clean_bullet[1:].strip()
                        html += f'<li>{clean_bullet}</li>'
                html += '</ul></div>'
            # If description is a list, render as bullet list
            elif description and isinstance(description, list):
                html += '<div class="job-description"><ul>'
                for item in description:
                    if item and isinstance(item, str):
                        clean_item = item.strip()
                        if clean_item.startswith('•') or clean_item.startswith('-'):
                            clean_item = clean_item[1:].strip()
                        html += f'<li>{clean_item}</li>'
                html += '</ul></div>'
            # If description is a string with newlines, split and render as bullets
            elif description and isinstance(description, str):
                if '\n' in description or '\r' in description:
                    lines = [line.strip() for line in description.replace('\r', '\n').split('\n') if line.strip()]
                    if lines:
                        html += '<div class="job-description"><ul>'
                        for line in lines:
                            clean_line = line.strip()
                            if clean_line.startswith('•') or clean_line.startswith('-'):
                                clean_line = clean_line[1:].strip()
                            html += f'<li>{clean_line}</li>'
                        html += '</ul></div>'
                else:
                    html += f'<div class="job-description">{description}</div>'
            
            html += '</div>'
    
    # Projects
    if data.get("projects"):
        html += '<div class="section-title">Projects</div>'
        projects = data["projects"] if isinstance(data["projects"], list) else []
        for project in projects:
            if isinstance(project, dict):
                name = project.get('name', '')
                tech = project.get('tech', '')
                description = project.get('description', '')
                result = project.get('result', '')
                
                html += f'''
                <div style="margin-bottom: 10px;">
                    <div class="project-name">{name}</div>
                '''
                if tech:
                    html += f'<div class="project-tech">{tech}</div>'
                if description:
                    html += f'<div>{description}</div>'
                if result:
                    html += f'<div class="project-result">{result}</div>'
                html += '</div>'
    
    # Notable Competencies
    if data.get("competencies"):
        html += '<div class="section-title">Notable Competencies</div>'
        competencies = data["competencies"] if isinstance(data["competencies"], list) else []
        html += '<div class="competencies-grid">'
        for comp in competencies:
            if isinstance(comp, dict):
                label = comp.get('label', '') or comp.get('name', '')
                desc = comp.get('description', '')
                if label and desc:
                    html += f'<div class="competency-item"><span class="competency-label">{label}:</span> {desc}</div>'
                elif label:
                    html += f'<div class="competency-item"><span class="competency-label">{label}</span></div>'
                else:
                    html += f'<div class="competency-item">{comp}</div>'
            else:
                html += f'<div class="competency-item">{comp}</div>'
        html += '</div>'
    
    # Education
    if data.get("education"):
        html += '<div class="section-title">Education</div>'
        for edu in data["education"]:
            school = edu.get('school', '')
            degree = edu.get('degree', '')
            field = edu.get('field', '')
            dates = edu.get('dates', '')
            location = edu.get('location', '')
            honors = edu.get('honors', '')
            
            html += '<div class="education-item">'
            html += f'<div class="school-name">{school}{' — ' + location if location else ''}</div>'
            
            degree_parts = []
            if degree: degree_parts.append(degree)
            if field: degree_parts.append(field)
            if dates: degree_parts.append(dates)
            if degree_parts:
                html += f'<div class="degree-info">{", ".join(degree_parts)}</div>'
            
            if honors:
                html += f'<div class="honors">{honors}</div>'
            
            html += '</div>'
    
    # Certifications
    if data.get("certifications"):
        html += '<div class="section-title">Certifications</div>'
        for cert in data["certifications"]:
            if isinstance(cert, dict):
                name = cert.get('name', '')
                organization = cert.get('organization', '')
                date = cert.get('date', '')
                
                cert_parts = [name]
                if organization: cert_parts.append(organization)
                if date: cert_parts.append(date)
                html += f'<div>{", ".join(cert_parts)}</div>'
    
    # Community
    if data.get("community"):
        html += '<div class="section-title">Community Involvement</div>'
        for comm in data["community"]:
            if isinstance(comm, dict):
                org = comm.get('org', '') or comm.get('organization', '') or comm.get('event', '')
                description = comm.get('description', '')
                if org and description:
                    html += f'<div class="community-item"><strong>{org}</strong>: {description}</div>'
                elif org:
                    html += f'<div class="community-item"><strong>{org}</strong></div>'
                elif description:
                    html += f'<div class="community-item">{description}</div>'
            else:
                html += f'<div class="community-item">{comm}</div>'
    
    html += "</div>"
    return html

def _get_professional_css():
    """Professional template CSS - traditional, clean"""
    return """
        .resume-preview.professional {
            font-family: 'Times New Roman', Times, serif;
            font-size: 10.5pt;
            line-height: 1.3;
            color: #000;
            max-width: 8.5in;
            margin: 0 auto;
            padding: 0.5in;
        }
        .resume-preview.professional .header {
            text-align: center;
            margin-bottom: 12px;
        }
        .resume-preview.professional .name {
            font-size: 18pt;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 4px;
        }
        .resume-preview.professional .contact {
            font-size: 9pt;
            color: #333;
        }
        .resume-preview.professional .section-title {
            font-size: 11pt;
            font-weight: bold;
            text-transform: uppercase;
            color: #2c5aa0;
            border-bottom: 1px solid #2c5aa0;
            margin-top: 14px;
            margin-bottom: 6px;
            padding-bottom: 2px;
        }
        .resume-preview.professional .summary {
            text-align: justify;
            margin-bottom: 8px;
        }
        .resume-preview.professional .skills-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px 20px;
            margin-bottom: 8px;
        }
        .resume-preview.professional .skill-category {
            font-weight: bold;
            font-size: 10pt;
        }
        .resume-preview.professional .skill-list {
            font-size: 9.5pt;
        }
        .resume-preview.professional .job-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
        }
        .resume-preview.professional .job-title-company {
            font-weight: bold;
            font-size: 10.5pt;
        }
        .resume-preview.professional .job-dates {
            font-style: italic;
            font-size: 9.5pt;
            color: #333;
        }
        .resume-preview.professional .job-location {
            font-size: 9.5pt;
            font-style: italic;
            margin-bottom: 3px;
        }
        .resume-preview.professional .job-description {
            margin-left: 0;
            margin-bottom: 8px;
        }
        .resume-preview.professional .job-description ul {
            margin: 3px 0;
            padding-left: 20px;
        }
        .resume-preview.professional .job-description li {
            margin-bottom: 2px;
        }
    """

def _get_modern_css():
    """Modern template CSS - color accents, cleaner fonts"""
    return """
        .resume-preview.modern {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
            color: #2d3748;
            max-width: 8.5in;
            margin: 0 auto;
            padding: 0.5in;
        }
        .resume-preview.modern .header {
            border-left: 4px solid #4a90e2;
            padding-left: 15px;
            margin-bottom: 20px;
        }
        .resume-preview.modern .name {
            font-size: 22pt;
            font-weight: 700;
            color: #1a365d;
            margin-bottom: 6px;
            letter-spacing: -0.5px;
        }
        .resume-preview.modern .contact {
            font-size: 9.5pt;
            color: #4a5568;
        }
        .resume-preview.modern .section-title {
            font-size: 12pt;
            font-weight: 700;
            color: #4a90e2;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 18px;
            margin-bottom: 8px;
            padding-bottom: 4px;
            border-bottom: 2px solid #e2e8f0;
        }
        .resume-preview.modern .summary {
            color: #4a5568;
            margin-bottom: 10px;
        }
        .resume-preview.modern .skills-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 10px;
        }
        .resume-preview.modern .skill-category {
            background: #ebf8ff;
            color: #2b6cb0;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 9pt;
            font-weight: 600;
        }
        .resume-preview.modern .skill-list {
            font-size: 9.5pt;
        }
        .resume-preview.modern .job-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 4px;
        }
        .resume-preview.modern .job-title-company {
            font-weight: 700;
            font-size: 11pt;
            color: #1a365d;
        }
        .resume-preview.modern .job-dates {
            font-size: 9pt;
            color: #718096;
            background: #f7fafc;
            padding: 2px 8px;
            border-radius: 4px;
        }
        .resume-preview.modern .job-location {
            font-size: 9pt;
            color: #718096;
            margin-bottom: 4px;
        }
        .resume-preview.modern .job-description {
            margin-bottom: 12px;
        }
        .resume-preview.modern .job-description ul {
            margin: 4px 0;
            padding-left: 20px;
        }
        .resume-preview.modern .job-description li {
            margin-bottom: 3px;
            color: #4a5568;
        }
    """

def _get_minimal_css():
    """Minimal template CSS - barebones, whitespace-heavy"""
    return """
        .resume-preview.minimal {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.5;
            color: #333;
            max-width: 7in;
            margin: 0 auto;
            padding: 0.75in;
        }
        .resume-preview.minimal .header {
            margin-bottom: 30px;
            padding-bottom: 15px;
            border-bottom: 1px solid #eee;
        }
        .resume-preview.minimal .name {
            font-size: 24pt;
            font-weight: 300;
            letter-spacing: 2px;
            margin-bottom: 8px;
            color: #000;
        }
        .resume-preview.minimal .contact {
            font-size: 9pt;
            color: #666;
            letter-spacing: 0.5px;
        }
        .resume-preview.minimal .section-title {
            font-size: 10pt;
            font-weight: 400;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #999;
            margin-top: 25px;
            margin-bottom: 10px;
        }
        .resume-preview.minimal .summary {
            color: #555;
            margin-bottom: 10px;
        }
        .resume-preview.minimal .skills-grid {
            margin-bottom: 10px;
        }
        .resume-preview.minimal .skill-category {
            font-weight: 400;
            font-size: 9.5pt;
            color: #666;
        }
        .resume-preview.minimal .skill-list {
            font-size: 9.5pt;
            color: #666;
        }
        .resume-preview.minimal .job-header {
            margin-bottom: 4px;
        }
        .resume-preview.minimal .job-title-company {
            font-weight: 500;
            font-size: 11pt;
        }
        .resume-preview.minimal .job-dates {
            font-size: 9pt;
            color: #999;
            float: right;
        }
        .resume-preview.minimal .job-location {
            font-size: 9pt;
            color: #999;
            margin-bottom: 6px;
        }
        .resume-preview.minimal .job-description {
            margin-bottom: 15px;
            color: #555;
        }
        .resume-preview.minimal .job-description ul {
            margin: 5px 0;
            padding-left: 20px;
        }
        .resume-preview.minimal .job-description li {
            margin-bottom: 4px;
        }
    """


@app.get("/api/download/{resume_id}")
def download_resume(resume_id: str, format: str = "docx"):
    """Download the resume as .docx (default) or .pdf (?format=pdf).

    The file is rendered on first request from the stored resume data, so
    preview builds don't pay for documents nobody downloads. Sync def: FastAPI
    runs it in the threadpool, keeping CPU-bound rendering off the event loop.
    """
    ext = "pdf" if format == "pdf" else "docx"
    filepath = os.path.join(RESUME_STORAGE_DIR, f"{resume_id}.{ext}")
    if not os.path.exists(filepath):
        data = get_resume(resume_id)
        if not data:
            return JSONResponse({"error": "Resume not found"}, status_code=404)
        (generate_pdf if ext == "pdf" else generate_docx)(resume_id, data)
    return FileResponse(filepath, filename=f"resume_{resume_id}.{ext}")

@app.get("/api/companies/search")
async def search_companies(query: str = ""):
    """Search Fortune 1000 companies"""
    if not query or len(query) < 2:
        return {"results": []}
    
    query_lower = query.lower()
    results = []
    for company in companies:
        if query_lower in company.lower():
            results.append(company)
    
    return {"results": results[:10]}  # Limit to 10 suggestions

@app.get("/api/states")
async def get_states():
    """Return list of US states"""
    return {"states": us_cities_data.get("states", {})}

@app.get("/api/cities")
async def get_cities(state: str = ""):
    """Return cities for a given state"""
    if not state:
        return {"cities": []}
    
    cities = us_cities_data.get("cities_by_state", {}).get(state, [])
    return {"cities": cities}


@app.get("/api/universities")
async def get_universities(q: str = ""):
    """Search universities by name"""
    if not q:
        return {"results": universities[:50]}
    
    query_lower = q.lower()
    results = [u for u in universities if query_lower in u.lower()]
    return {"results": results[:10]}

@app.get("/api/degrees")
async def get_degrees():
    """Return list of degree types"""
    return {"degrees": degrees}

@app.get("/api/fields")
async def get_fields(q: str = ""):
    """Search fields of study"""
    if not q:
        return {"results": fields_of_study[:50]}
    
    query_lower = q.lower()
    results = [f for f in fields_of_study if query_lower in f.lower()]
    return {"results": results[:10]}


# Stripe Payment Endpoints

@app.post("/api/referral/create")
async def create_referral(request: Request):
    """Create a new referral code for a user"""
    try:
        data = await request.json()
        user_email = data.get("email", "anonymous")
        
        # Generate unique referral code
        code = secrets.token_urlsafe(8).upper()[:10]
        
        # Store referral code
        referral_codes[code] = {
            "created_by": user_email,
            "created_at": datetime.now(),
            "visits": 0,
            "conversions": 0,
            "reward_unlocked": False
        }
        
        return {
            "success": True,
            "code": code,
            "link": f"{BASE_URL}/build?ref={code}"
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/referral/track")
async def track_referral_visit(request: Request):
    """Track when a referral link is visited"""
    try:
        data = await request.json()
        code = data.get("code", "")
        ip_address = request.client.host if request.client else "unknown"
        
        if not code or code not in referral_codes:
            return JSONResponse({"error": "Invalid referral code"}, status_code=400)
        
        # Record visit
        referral_codes[code]["visits"] += 1
        referral_visits.append({
            "code": code,
            "ip": ip_address,
            "timestamp": datetime.now(),
            "converted": False
        })
        
        return {
            "success": True,
            "visits": referral_codes[code]["visits"],
            "conversions": referral_codes[code]["conversions"],
            "reward_unlocked": referral_codes[code]["reward_unlocked"]
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/referral/stats/{code}")
async def get_referral_stats(code: str):
    """Get referral statistics for a code"""
    if code not in referral_codes:
        return JSONResponse({"error": "Referral code not found"}, status_code=404)
    
    stats = referral_codes[code]
    return {
        "code": code,
        "visits": stats["visits"],
        "conversions": stats["conversions"],
        "reward_unlocked": stats["reward_unlocked"],
        "link": f"{BASE_URL}/build?ref={code}"
    }

@app.post("/api/referral/convert")
async def convert_referral(request: Request):
    """Mark a referral as converted (friend made a purchase)"""
    try:
        data = await request.json()
        code = data.get("code", "")
        
        if not code or code not in referral_codes:
            return JSONResponse({"error": "Invalid referral code"}, status_code=400)
        
        # Mark conversion
        referral_codes[code]["conversions"] += 1
        referral_codes[code]["reward_unlocked"] = True
        
        # Update visit log
        for visit in reversed(referral_visits):
            if visit["code"] == code and not visit["converted"]:
                visit["converted"] = True
                break
        
        return {
            "success": True,
            "conversions": referral_codes[code]["conversions"],
            "reward_unlocked": True
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/create-checkout-session")
async def create_checkout_session(request: Request):
    """Create Stripe Checkout session for premium resume download"""
    try:
        data = await request.json()
        resume_id = data.get("resume_id", "")
        tier = data.get("tier", "regular")  # regular, discount, student
        student_token = data.get("student_token", "")
        
        if not resume_id:
            return JSONResponse({"error": "Resume ID required"}, status_code=400)
        
        # Verify student status if requesting student price
        if tier == "student":
            verified = False
            
            # Check token
            if student_token and student_token in student_verifications:
                verification = student_verifications[student_token]
                if verification["verified"] and datetime.now() <= verification["expires"]:
                    verified = True
            
            if not verified:
                return JSONResponse({
                    "error": "Student verification required. Please verify your .edu email first."
                }, status_code=403)
        
        # Map tier to price ID
        if tier == "student" or tier == "discount":
            price_id = STRIPE_STUDENT_PRICE_ID
        else:
            price_id = STRIPE_PRICE_ID
        
        # Create checkout session
        # Check if user came from referral
        ref_code = data.get("referral_code", "")
        
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}&resume_id={resume_id}",
            cancel_url=f"{BASE_URL}/cancel?resume_id={resume_id}",
            metadata={
                "resume_id": resume_id,
                "tier": tier,
                "referral_code": ref_code
            }
        )
        
        return {"sessionId": session.id, "url": session.url}
    
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/success")
async def payment_success(request: Request, session_id: str = "", resume_id: str = "", ref: str = ""):
    """Handle successful payment - show download page"""
    try:
        # Verify payment with Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == "paid":
            # Payment confirmed - mark resume as premium
            resume = get_resume(resume_id)
            if resume:
                resume["paid"] = True
                resumes[resume_id] = resume
                save_resume_json(resume_id, resume)
            
            # Track referral conversion
            ref_code = ref or session.get("metadata", {}).get("referral_code", "")
            if ref_code and ref_code in referral_codes:
                referral_codes[ref_code]["conversions"] += 1
                referral_codes[ref_code]["reward_unlocked"] = True
            
            return templates.TemplateResponse(
                request=request,
                name="success.html",
                context={
                    "resume_id": resume_id,
                    "download_url": f"/api/download/{resume_id}"
                }
            )
        else:
            return HTMLResponse("Payment not completed. Please try again.")
    
    except Exception as e:
        return HTMLResponse(f"Error verifying payment: {str(e)}")

@app.get("/cancel")
async def payment_cancel(request: Request, resume_id: str = ""):
    """Handle cancelled payment"""
    return templates.TemplateResponse(
        request=request,
        name="cancel.html",
        context={"resume_id": resume_id}
    )

@app.post("/api/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = STRIPE_WEBHOOK_SECRET
    
    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            # For testing without webhook secret
            event = json.loads(payload)
        
        # Handle successful payment
        if event.get("type") == "checkout.session.completed":
            session = event["data"]["object"]
            resume_id = session.get("metadata", {}).get("resume_id", "")
            ref_code = session.get("metadata", {}).get("referral_code", "")
            
            if resume_id:
                resume = get_resume(resume_id)
                if resume:
                    resume["paid"] = True
                    resumes[resume_id] = resume
                    save_resume_json(resume_id, resume)
            
            # Track referral conversion from webhook
            if ref_code and ref_code in referral_codes:
                referral_codes[ref_code]["conversions"] += 1
                referral_codes[ref_code]["reward_unlocked"] = True
        
        return {"status": "success"}
    
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@app.get("/api/check-payment/{resume_id}")
async def check_payment(resume_id: str):
    """Check if resume has been paid for"""
    resume = get_resume(resume_id)
    if not resume:
        return {"paid": False}
    return {"paid": resume.get("paid", False)}


@app.post("/api/preview-timer")
async def get_timed_preview(request: Request):
    """Get preview with 3-second clean timer"""
    try:
        data = await request.json()
        resume_id = data.get("resume_id", "")
        
        if not resume_id:
            return JSONResponse({"error": "Resume not found"}, status_code=404)
        
        resume_data = get_resume(resume_id)
        if not resume_data:
            return JSONResponse({"error": "Resume not found"}, status_code=404)
        # Handle both flat (form builder) and nested (voice) formats
        if "data" in resume_data and "template_style" not in resume_data:
            resume_data = resume_data["data"]
        template_style = resume_data.get("template_style", "professional")
        
        # CSS watermark. (A Playwright-rendered PNG watermark used to be tried
        # first, but Chromium can't run on Render's free tier, so it was a stub.)
        preview_html = generate_preview_html(resume_data, template_style)
        watermarked_html = f'''
            <div style="position:relative;overflow:hidden;">
                <div style="filter:blur(3px);opacity:0.6;pointer-events:none;">{preview_html}</div>
                <div style="position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:60px;pointer-events:none;">
                    <span style="transform:rotate(-30deg);font-size:48px;font-weight:bold;color:rgba(200,0,0,0.3);font-family:sans-serif;white-space:nowrap;">AIE ResuMaker SAMPLE</span>
                    <span style="transform:rotate(-30deg);font-size:48px;font-weight:bold;color:rgba(200,0,0,0.3);font-family:sans-serif;white-space:nowrap;">AIE ResuMaker SAMPLE</span>
                    <span style="transform:rotate(-30deg);font-size:48px;font-weight:bold;color:rgba(200,0,0,0.3);font-family:sans-serif;white-space:nowrap;">AIE ResuMaker SAMPLE</span>
                </div>
            </div>
            '''
        return {
            "success": True,
            "clean_html": preview_html,
            "watermarked_html": watermarked_html,
            "watermarked_image": None
        }

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# reportlab's built-in Times/Helvetica cover only cp1252 and draw any other
# character as a black box ("H■S", "Nguy■n"). The PDF embeds these TrueType
# fonts instead. Liberation Serif/Sans are metric-compatible with Times New
# Roman/Arial, so the layout is unchanged. License (SIL OFL 1.1): fonts/LICENSE.
PDF_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
PDF_FONTS = {
    "LiberationSerif": "LiberationSerif-Regular.ttf",
    "LiberationSerif-Bold": "LiberationSerif-Bold.ttf",
    "LiberationSerif-Italic": "LiberationSerif-Italic.ttf",
    "LiberationSans": "LiberationSans-Regular.ttf",
}


@functools.cache
def _register_pdf_fonts() -> frozenset:
    """Register the PDF fonts (once) and return the code points all of them draw."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    fonts = [TTFont(name, os.path.join(PDF_FONTS_DIR, filename)) for name, filename in PDF_FONTS.items()]
    for font in fonts:
        pdfmetrics.registerFont(font)
    # Lets <b> and <i> in Paragraph markup switch to the matching face.
    pdfmetrics.registerFontFamily("LiberationSerif", normal="LiberationSerif",
                                  bold="LiberationSerif-Bold", italic="LiberationSerif-Italic")
    pdfmetrics.registerFontFamily("LiberationSans", normal="LiberationSans")
    return frozenset.intersection(*(frozenset(font.face.charToGlyph) for font in fonts))


def _pdf_text(value) -> str:
    """Make a user-entered value safe to insert into Paragraph markup. NFC-compose
    accents typed as combining marks (reportlab can't position them: "Nguyê" +
    U+0303 + "n" put the tilde on the n), then escape & < > so the value prints as
    typed. Both happen per value: NFC over finished markup fused a value's leading
    U+0338 with the ">" of the tag before it."""
    return xml_escape(unicodedata.normalize("NFC", str(value)))


def _pdf_markup(text: str, covered: frozenset) -> str:
    """Send the few characters the fonts lack (✓ ★ ⇒ ❖ ...) to reportlab's
    standard fonts, which draw them from Symbol/ZapfDingbats as before. It only
    wraps non-ASCII characters, so the entities _pdf_text writes pass through."""
    return "".join(c if c.isascii() or ord(c) in covered else f'<font name="Times-Roman">{c}</font>'
                   for c in text)


def generate_pdf(resume_id: str, data: dict):
    """Generate PDF document"""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Spacer
    from reportlab.platypus import Paragraph as _Paragraph

    covered = _register_pdf_fonts()

    # Every Paragraph below goes through _pdf_markup, and every user value
    # through _pdf_text where it is inserted into the markup.
    def Paragraph(text, style):
        return _Paragraph(_pdf_markup(text, covered), style)

    output_dir = RESUME_STORAGE_DIR
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{resume_id}.pdf")
    
    doc = SimpleDocTemplate(filepath, pagesize=letter,
                            rightMargin=0.75*inch, leftMargin=0.75*inch,
                            topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    styles = getSampleStyleSheet()
    story = []
    
    # Custom styles
    name_style = ParagraphStyle(
        'Name',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#000000'),
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName='LiberationSerif-Bold'
    )
    
    contact_style = ParagraphStyle(
        'Contact',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#333333'),
        alignment=TA_CENTER,
        spaceAfter=12,
        fontName='LiberationSans'
    )
    
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#2c5aa0'),
        spaceAfter=6,
        spaceBefore=14,
        fontName='LiberationSerif-Bold',
        borderColor=colors.HexColor('#2c5aa0'),
        borderWidth=1,
        borderPadding=2,
        leftIndent=0,
        rightIndent=0
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=8,
        fontName='LiberationSerif'
    )
    
    # Name
    story.append(Paragraph(_pdf_text(data['full_name'].upper()), name_style))
    
    # Contact info
    contact_parts = [_pdf_text(data[k]) for k in ("location", "phone", "email", "linkedin") if data.get(k)]
    
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), contact_style))
    
    # Horizontal line
    story.append(Spacer(1, 12))
    
    # Professional Summary
    if data.get("summary"):
        story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
        story.append(Paragraph(_pdf_text(data["summary"]), normal_style))
    
    # Technical Skills
    if data.get("skills"):
        story.append(Paragraph("TECHNICAL SKILLS", section_style))
        skills_text = ", ".join(map(_pdf_text, data["skills"])) if isinstance(data["skills"], list) else _pdf_text(data["skills"])
        story.append(Paragraph(skills_text, normal_style))
    
    # Professional Experience
    if data.get("experience"):
        story.append(Paragraph("PROFESSIONAL EXPERIENCE", section_style))
        for job in data["experience"]:
            # Job title and company
            title_text = f"<b>{_pdf_text(job.get('title', ''))}</b>"
            if job.get("company"):
                title_text += f" — <b>{_pdf_text(job['company'])}</b>"
            story.append(Paragraph(title_text, ParagraphStyle('JobTitle', parent=normal_style, fontSize=10.5, fontName='LiberationSerif-Bold', spaceAfter=2)))
            
            # Location and dates
            location_parts = []
            if job.get("city"): location_parts.append(_pdf_text(job["city"]))
            if job.get("state"): location_parts.append(_pdf_text(job["state"]))
            location_str = ", ".join(location_parts)
            
            loc_date_parts = []
            if location_str: loc_date_parts.append(f"<i>{location_str}</i>")
            if job.get("dates"): loc_date_parts.append(f"<i>{_pdf_text(job['dates'])}</i>")
            if job.get("phone"): loc_date_parts.append(f"<i>{_pdf_text(job['phone'])}</i>")
            
            if loc_date_parts:
                story.append(Paragraph("  |  ".join(loc_date_parts), ParagraphStyle('JobMeta', parent=normal_style, fontSize=9.5, textColor=colors.HexColor('#666666'))))
            
            # Description / Bullets
            bullets = job.get('bullets', [])
            description = job.get('description', '')
            
            if bullets and isinstance(bullets, list):
                # Render bullets as a list
                bullet_style = ParagraphStyle('JobBullet', parent=normal_style, leftIndent=14, spaceAfter=2, bulletIndent=4)
                for bullet in bullets:
                    if bullet and isinstance(bullet, str):
                        clean_bullet = bullet.strip()
                        if clean_bullet.startswith('•') or clean_bullet.startswith('-'):
                            clean_bullet = clean_bullet[1:].strip()
                        story.append(Paragraph(f"• {_pdf_text(clean_bullet)}", bullet_style))
            elif description and isinstance(description, list):
                # Render description list as bullets
                bullet_style = ParagraphStyle('JobBullet', parent=normal_style, leftIndent=14, spaceAfter=2, bulletIndent=4)
                for item in description:
                    if item and isinstance(item, str):
                        clean_item = item.strip()
                        if clean_item.startswith('•') or clean_item.startswith('-'):
                            clean_item = clean_item[1:].strip()
                        story.append(Paragraph(f"• {_pdf_text(clean_item)}", bullet_style))
            elif description and isinstance(description, str):
                if '\n' in description or '\r' in description:
                    # Multi-line description - render as bullets
                    lines = [line.strip() for line in description.replace('\r', '\n').split('\n') if line.strip()]
                    bullet_style = ParagraphStyle('JobBullet', parent=normal_style, leftIndent=14, spaceAfter=2, bulletIndent=4)
                    for line in lines:
                        clean_line = line.strip()
                        if clean_line.startswith('•') or clean_line.startswith('-'):
                            clean_line = clean_line[1:].strip()
                        story.append(Paragraph(f"• {_pdf_text(clean_line)}", bullet_style))
                else:
                    story.append(Paragraph(_pdf_text(description), ParagraphStyle('JobDesc', parent=normal_style, leftIndent=14)))
    
    # Projects
    if data.get("projects"):
        story.append(Paragraph("PROJECTS", section_style))
        for project in data["projects"]:
            if isinstance(project, dict):
                story.append(Paragraph(f"<b>{_pdf_text(project.get('name', ''))}</b>", ParagraphStyle('ProjectTitle', parent=normal_style, fontSize=10.5, fontName='LiberationSerif-Bold')))
                if project.get("tech"):
                    story.append(Paragraph(f"<i>{_pdf_text(project['tech'])}</i>", ParagraphStyle('ProjectTech', parent=normal_style, fontSize=9, textColor=colors.HexColor('#666666'))))
                if project.get("description"):
                    story.append(Paragraph(_pdf_text(project["description"]), normal_style))
                if project.get("result"):
                    story.append(Paragraph(f"<i>{_pdf_text(project['result'])}</i>", ParagraphStyle('ProjectResult', parent=normal_style, fontSize=9.5, textColor=colors.HexColor('#2c5aa0'))))
    
    # Notable Competencies
    if data.get("competencies"):
        story.append(Paragraph("NOTABLE COMPETENCIES", section_style))
        for comp in data["competencies"]:
            if isinstance(comp, dict):
                label = comp.get('label', '') or comp.get('name', '')
                desc = comp.get('description', '')
                if label and desc:
                    story.append(Paragraph(f"<b>{_pdf_text(label)}:</b> {_pdf_text(desc)}", normal_style))
                elif label:
                    story.append(Paragraph(f"<b>{_pdf_text(label)}</b>", normal_style))
    
    # Education
    if data.get("education"):
        story.append(Paragraph("EDUCATION", section_style))
        for edu in data["education"]:
            school_text = f"<b>{_pdf_text(edu.get('school', ''))}</b>"
            if edu.get("location"):
                school_text += f" — <b>{_pdf_text(edu['location'])}</b>"
            story.append(Paragraph(school_text, ParagraphStyle('School', parent=normal_style, fontSize=10.5, fontName='LiberationSerif-Bold')))
            
            degree_parts = []
            if edu.get("degree"): degree_parts.append(_pdf_text(edu["degree"]))
            if edu.get("field"): degree_parts.append(_pdf_text(edu["field"]))
            if edu.get("dates"): degree_parts.append(_pdf_text(edu["dates"]))
            if degree_parts:
                story.append(Paragraph(f"<i>{', '.join(degree_parts)}</i>", ParagraphStyle('Degree', parent=normal_style, fontSize=9.5, textColor=colors.HexColor('#666666'))))
            
            if edu.get("honors"):
                story.append(Paragraph(_pdf_text(edu["honors"]), ParagraphStyle('Honors', parent=normal_style, fontSize=9, textColor=colors.HexColor('#666666'))))
    
    # Community Involvement
    if data.get("community"):
        story.append(Paragraph("COMMUNITY INVOLVEMENT", section_style))
        for item in data["community"]:
            if isinstance(item, dict):
                text = _pdf_text(item.get("event", ""))
                if item.get("organization"):
                    text += f" | {_pdf_text(item['organization'])}"
                story.append(Paragraph(text, normal_style))
    
    # Certifications
    if data.get("certifications"):
        story.append(Paragraph("CERTIFICATIONS", section_style))
        for cert in data["certifications"]:
            if isinstance(cert, dict):
                text = _pdf_text(cert.get("name", ""))
                if cert.get("organization"):
                    text += f" — {_pdf_text(cert['organization'])}"
                if cert.get("date"):
                    text += f", {_pdf_text(cert['date'])}"
                story.append(Paragraph(text, normal_style))
    
    # References
    story.append(Spacer(1, 16))
    story.append(Paragraph("*References available upon request*", ParagraphStyle('References', parent=normal_style, alignment=TA_CENTER, fontSize=9, fontName='LiberationSerif-Italic')))
    
    doc.build(story)
    return filepath


if __name__ == "__main__":
    import uvicorn
    # Respect Render's dynamic $PORT in production; default 8000 locally.
    # reload=True only when APP_ENV is not production.
    _port = int(os.getenv("PORT", "8000"))
    _reload = os.getenv("APP_ENV", "development") != "production"
    uvicorn.run("main:app", host="0.0.0.0", port=_port, reload=_reload)
