# AIe ResuMaker

Simple resume builder web app.

## Features
- Form-based resume input
- Live preview
- Multiple export formats (.docx, .pdf, .txt)
- O*NET job title integration
- Customizable themes

## Setup

```bash
# Install dependencies
pip install fastapi uvicorn python-docx jinja2 python-multipart

# Run app
cd app
python main.py
```

## Structure
```
resumemaker/
├── app/
│   ├── main.py              # FastAPI backend
│   ├── templates/
│   │   └── index.html       # Frontend
│   └── static/
│       ├── style.css        # Styles
│       └── app.js           # JavaScript
├── PLAN.md
├── ARCHITECTURE.md
├── ENGINE.md
├── JOB-DATA.md
├── UI-DESIGN.md
└── PAYMENT.md
```

## Tech Stack
- Backend: FastAPI (Python)
- Frontend: HTML/JS/CSS (no framework)
- Documents: python-docx
- Payment: Stripe
