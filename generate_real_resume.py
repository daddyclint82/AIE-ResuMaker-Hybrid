"""
Test: Generate full resume from complete fixture data to verify generators render everything.
This bypasses the voice state machine and feeds the generators directly with rich data.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from main import generate_docx, generate_pdf

# Build the complete data payload from the fixture (all real content)
complete_data = {
    "full_name": "Clint Singleton",
    "email": "clints8282@gmail.com",
    "phone": "936-800-7626",
    "address": "227 Crestwood, Nacogdoches, TX 75961",
    "city": "Nacogdoches",
    "state": "Texas",
    "location": "Nacogdoches, TX",
    "linkedin": "https://linkedin.com/in/clintsingleton",
    "industry": "AI Infrastructure / DevOps",
    "job_title": "AI Infrastructure Engineer",
    "experience_level": "senior",
    "education_level": "bachelor's",
    
    # FULL SUMMARY (all 4 Q&A answers combined)
    "summary": "Hands-on technologist with 15+ years of experience spanning oilfield engineering operations, retail technology management, and modern AI infrastructure development. Proven ability to lead teams, manage complex technical operations, and rapidly iterate from prototype to deployed solution across disparate domains — from drilling mud systems in the Eagle Ford shale to self-hosted AI orchestration platforms. Strong foundation in backend API development, service orchestration, DevOps automation, cross-platform infrastructure, and community-driven technical education. Self-directed learner who combines operational discipline with cutting-edge technical implementation. Key achievements include achieving #1 ranking among all authorized retail stores in the county, delivering cost reduction through active operational planning in oilfield operations, and building and deploying production AI infrastructure serving 24/7.",
    
    # FULL SKILLS (proper list, not the leaked project name)
    "skills": [
        "Python", "JavaScript", "Node.js", "Kubernetes", "Docker", "AWS",
        "Linux", "Bash", "Git", "FastAPI", "Flask", "REST API", "SQLite",
        "HTML5", "CSS3", "Web Audio API", "WebSocket", "systemd",
        "Tailscale", "WSL2", "LLM Inference", "Speech-to-Text",
        "Text-to-Speech", "Microservices", "API Gateway", "DevOps", "CI/CD"
    ],
    "skills_categorized": {
        "Programming & Development": ["Python", "JavaScript", "Node.js", "FastAPI", "Flask", "HTML5", "CSS3", "WebSocket"],
        "DevOps & Infrastructure": ["Kubernetes", "Docker", "AWS", "Linux", "Bash", "Git", "systemd", "Tailscale", "WSL2", "CI/CD"],
        "API & Data": ["REST API", "SQLite", "API Gateway", "Microservices"],
        "AI & Audio": ["LLM Inference", "Speech-to-Text", "Text-to-Speech", "Web Audio API"]
    },
    
    # FULL EXPERIENCE (all 3 jobs with complete bullet lists)
    "experience": [
        {
            "company": "Self-Employed / Independent",
            "title": "AI Infrastructure Engineer",
            "dates": "2025",
            "location": "Nacogdoches, TX | Remote",
            "description": "",
            "bullets": [
                "Designed, deployed, and maintained full-stack AI infrastructure including voice-enabled assistants, Discord bots, and web-based resume builders",
                "Built and operated DaddyClintBot — a persistent-memory Discord assistant with real-time TTS, STT, and LLM integration via Ollama and llama.cpp",
                "Architected ResumeForge, a FastAPI-based resume builder with live HTML preview, automated DOCX/PDF export, Stripe monetization, and O*NET skill categorization",
                "Developed Remote Lucius Agent, an OpenClaw-based multi-channel AI orchestration layer bridging WSL2, Windows, Android, and cloud endpoints via Tailscale mesh networking",
                "Engineered cross-platform networking bridges using Tailscale, WSL2 virtual Ethernet, and systemd service management to connect heterogeneous AI inference endpoints",
                "Created browser-based voice AI pipeline integrating Web Audio API, Piper TTS, Faster Whisper, and WebSocket streaming for real-time conversational UX",
                "Automated deployments via systemd, Docker, Git, Bash, and cron for 24/7 reliability across Windows host, WSL2 Linux, and Android GPU-accelerated inference nodes",
                "Published technical tutorials and community documentation on AI infrastructure setup, enabling other developers to replicate self-hosted LLM stacks on consumer hardware"
            ]
        },
        {
            "company": "AES / Halliburton / Baroid",
            "title": "Mud Engineer / Drilling Fluids Specialist",
            "dates": "2011–2015, 2018–2020, 2021–2023",
            "location": "Eagle Ford, Delaware Basin, Permian Basin | South & West Texas",
            "description": "",
            "bullets": [
                "Ran advanced drilling fluid systems optimized for Eagle Ford, Delaware Basin, and Permian Basin formations",
                "Managed application and logistics of diverse product portfolios on-site, ensuring efficient and effective utilization",
                "Monitored downhole conditions including ECDs, hole volumes, stroke counts, and gas detection during critical operations",
                "Maintained rigorous safety protocols: observations, safety meetings, documentation, and stop cards to both operators and employers",
                "Delivered cost reduction through active operational planning, logistics optimization, and waste minimization",
                "Specialized in water-based mud (WBM) systems in production sections",
                "Built strong problem-solving and communication relationships with rig personnel across multiple operators",
                "Adapted to varying operator safety cultures — from BHP Billiton's stringent third-party requirements to Marathon Oil's operational standards"
            ]
        },
        {
            "company": "AT&T Authorized Retailer (Allcom)",
            "title": "Store Manager",
            "dates": "2015–2018, 2020",
            "location": "Nacogdoches, TX",
            "description": "",
            "bullets": [
                "Led sales floor operations and coached sales associates to maximize customer value and revenue per transaction",
                "Delivered premium digital solutions for customers at the highest service level",
                "Achieved #1 ranking among all authorized retail stores in the county",
                "Managed inventory, scheduling, customer service resolution, and team development",
                "Developed consultative sales approach focused on customer needs rather than transactional volume"
            ]
        }
    ],
    
    # FULL PROJECTS (both projects)
    "projects": [
        {
            "name": "ResumeForge — Professional Resume Builder",
            "tech": "FastAPI, Python, HTML/CSS/JS, SQLite, Stripe, O*NET API | 2025–2026",
            "description": "Architected and deployed full-stack resume builder with live preview, auto-skill categorization, and DOCX export",
            "bullets": [
                "Built responsive HTML/CSS/JS frontend with real-time voice chat integration",
                "Integrated Stripe Checkout for $9.99 resume purchases with webhook verification",
                "Implemented O*NET API-based skill categorization with 42-tier taxonomy and auto-weighting"
            ],
            "result": "Deployed production-ready resume platform with monetization and AI-assisted skill categorization"
        },
        {
            "name": "AI Orchestration & Community Education Platform",
            "tech": "OpenClaw, Node.js, WSL2, Ollama, Tailscale | 2025–2026",
            "description": "Architected complete OpenClaw-based AI assistant infrastructure with persistent memory, agent orchestration, multi-channel integration",
            "bullets": [
                "Deployed persistent-memory AI agents across Discord, webchat, and browser canvas",
                "Built cross-platform LLM routing to local Ollama (WSL2) and remote Android (llama.cpp) endpoints",
                "Created community documentation and tutorials for local AI infrastructure replication"
            ],
            "result": "Active community educator and go-to resource for local AI infrastructure setup"
        }
    ],
    
    # FULL COMPETENCIES (both)
    "competencies": [
        {
            "label": "Operational Leadership",
            "description": "15+ years managing complex field operations, retail teams, safety-critical environments — from drilling rigs with 50+ personnel to retail stores with $2M+ annual revenue"
        },
        {
            "label": "Rapid Prototyping",
            "description": "Built and evaluated 3 distinct bot architectures in 72 hours, moving from concept to working prototype using FastAPI, Node.js, and shell automation"
        }
    ],
    
    # FULL EDUCATION
    "education": [
        {
            "school": "Stephen F. Austin State University",
            "location": "Nacogdoches, TX",
            "degree": "Bachelor of Science, Kinesiology with Art Minor; Physics Major Work",
            "field": "",
            "dates": "",
            "honors": "Dean's List | National Honor Society"
        }
    ],
    
    # FULL COMMUNITY
    "community": [
        {
            "org": "Nacogdoches Jaycees",
            "event": "Nacogdoches 1st Annual Jaycees Mud Run",
            "role": "Participant",
            "description": "Participant in community fundraising mud run event supporting local youth programs"
        }
    ],
    
    # FULL CERTIFICATIONS
    "certifications": [
        {
            "name": "Halliburton Mud Engineer's Certificate",
            "issuer": "Halliburton",
            "organization": "Halliburton",
            "date": "2011"
        }
    ],
    
    # FULL REFERENCES
    "references": [
        {"name": "Billy Bobo", "phone": "936-615-1617"},
        {"name": "Dinesh Hospetti", "phone": "281-541-5748"},
        {"name": "Michael Baker", "phone": "806-891-6525"}
    ],
    
    "template_style": "professional"
}

# ─── GENERATE DOCUMENTS ─────────────────────────────────────────────────────
print("=" * 70)
print("🧪 Generating FULL resume with complete data payload")
print("=" * 70)

resume_id = "clint_full_resume_v1"

docx_path = generate_docx(resume_id, complete_data)
docx_size = os.path.getsize(docx_path)
print(f"\n✅ DOCX: {docx_path}")
print(f"   Size: {docx_size:,} bytes ({docx_size/1024:.1f} KB)")

pdf_path = generate_pdf(resume_id, complete_data)
pdf_size = os.path.getsize(pdf_path)
print(f"\n✅ PDF: {pdf_path}")
print(f"   Size: {pdf_size:,} bytes ({pdf_size/1024:.1f} KB)")

# ─── VERIFICATION ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("📊 CONTENT VERIFICATION")
print("=" * 70)
print(f"Full Name:        {complete_data['full_name']}")
print(f"Job Title:        {complete_data['job_title']}")
print(f"Summary:          {len(complete_data['summary'])} chars")
print(f"Skills (flat):    {len(complete_data['skills'])} items")
print(f"Skills (cat):     {sum(len(v) for v in complete_data['skills_categorized'].values())} items across {len(complete_data['skills_categorized'])} categories")
print(f"Experience jobs:  {len(complete_data['experience'])}")
print(f"  Job 1 bullets:  {len(complete_data['experience'][0]['bullets'])}")
print(f"  Job 2 bullets:  {len(complete_data['experience'][1]['bullets'])}")
print(f"  Job 3 bullets:  {len(complete_data['experience'][2]['bullets'])}")
print(f"Projects:         {len(complete_data['projects'])}")
print(f"Competencies:     {len(complete_data['competencies'])}")
print(f"Education:        {len(complete_data['education'])}")
print(f"Community:        {len(complete_data['community'])}")
print(f"Certifications:   {len(complete_data['certifications'])}")
print(f"References:       {len(complete_data['references'])}")

print("\n" + "=" * 70)
print("🎉 FULL RESUME GENERATED — Compare sizes to previous truncated outputs")
print("=" * 70)
