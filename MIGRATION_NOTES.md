# AIE ResuMaker → Hybrid Migration Notes

## When Ready to Deploy Hybrid to Render

Set these environment variables in the **Render dashboard** (Environment tab).
**Never** put real secret values in this file or any tracked file. Pull live values
from your password manager / Stripe dashboard / Groq console at deploy time.

### Required Environment Variables (set in Render dashboard, NOT in git)

```bash
APP_ENV=production
DEBUG=false
BASE_URL=https://<your-render-url>.onrender.com   # Update after first Render deploy

# Stripe LIVE keys — copy from Stripe Dashboard → Developers → API keys
STRIPE_PUBLISHABLE_KEY=<REDACTED: set in Render dashboard>
STRIPE_SECRET_KEY=<REDACTED: set in Render dashboard>
STRIPE_PRICE_ID=<REDACTED: set in Render dashboard>
STRIPE_STUDENT_PRICE_ID=<REDACTED: set in Render dashboard>
STRIPE_WEBHOOK_SECRET=<REDACTED: set in Render dashboard>

# Groq — copy from console.groq.com → API Keys
GROQ_API_KEY=<REDACTED: set in Render dashboard>
```

> ⚠️ Secret key prefixes are intentionally NOT written in this file to avoid
> in this file to avoid triggering secret scanners. Use your password manager and the Render
> dashboard to set actual values.

> **Email/SMTP removed:** The Gmail SMTP path (referral confirmation emails) is
> deprecated and no longer used. Do not configure SMTP_* variables.

### Deployment Checklist

- [ ] Set all env vars above directly in the Render dashboard (never commit them)
- [ ] Set `APP_ENV=production` and `DEBUG=false`
- [ ] Update `BASE_URL` to your Render URL after first deploy
- [ ] Confirm `.env` and `.env.production` are in `.gitignore` (they are)
- [ ] Run pre-push secret scan (should return nothing):
      `grep -rn 'REDACTED' --include=*.md --include=*.py --include=*.js .`
- [ ] Push to GitHub
- [ ] Deploy to Render
- [ ] Configure Stripe webhook URL in Stripe Dashboard → point at the Render URL

### Where the Original Lives

Archived at: `archive/aie-resumaker/`
(Live credentials live ONLY in your password manager and the Render dashboard —
never in the repo.)