# LLM test: GPT-OSS 20B vs MiniMax M3.1 Flash

2026-11-20. Picks a replacement for `llama-3.3-70b-versatile`, which Groq retired for non-enterprise keys on 2026-08-16; production is falling back to template summaries.

## Setup

- **Models:** `openai/gpt-oss-20b` on Groq (direct API) vs `minimax-m3.1-flash:cloud` on Ollama Cloud (through the signed-in local Ollama).
- **Prompts:** the exact payloads deployed `main` (bc41a0f) builds, captured by driving `voice_api.process_answer` with a stubbed HTTP client.
- **Candidates:** six made-up people: tech, oil & gas, ICU nurse, finance, electrician, retail.
- **Settings ("ship"):** the app's temperatures, `reasoning_effort: low`, max_tokens 1024 (summary) / 3000 (skills). The skills call keeps `response_format: json_object`.
- **"as-is" check:** today's code unchanged (summary max_tokens 300, default reasoning), on 2 people.
- **Run size:** 28 calls, all HTTP 200, no 429. Cost: GPT-OSS $0.0012, MiniMax $0.0023.

## Scorecard

| | GPT-OSS 20B (Groq) | MiniMax M3.1 Flash (Ollama) |
|---|---|---|
| Median latency, summary / skills | 0.30s / 0.55s | 1.10s / 1.86s |
| Price per 1M tokens (in / out) | $0.075 / $0.30 | $0.15 / $0.60 |
| Skills JSON accepted by the app's parser | 6/6 | 6/6 |
| Skills lost or invented | 0 (one reworded) | 0 (one reworded) |
| Skills weights | all 95 for the nurse and the store manager; retail all in "Other Skills" | spread in every case |
| Summaries: invented numbers / keyword coverage | none / 32 of 33 | none / 31 of 33 |
| Summary voice: first person / buzzwords | "I" or "My" in 6 of 6 / 6 of 6 ("proven", "track record", "seasoned") | "I" in 1 of 6 / 2 of 6 ("proven", "results-driven") |
| Characters the PDF export's fonts lack (U+2011, U+202F) | 12 | 0 |
| Today's 300-token setting (as-is) | cut off 2 of 2 | cut off 1 of 2 |

**Verdict:** MiniMax M3.1 Flash writes better summaries and weights skills properly. GPT-OSS 20B is about 3.5x faster and half the price, but it flattened weights for 2 of 6 people and wrote in the wrong voice. Neither model works with today's 300-token setting.

**Bug found:** the skills prompt reads `data["summary_q1"]` and `data["summary_q4"]`, but the answers live in `context["summary_answers"]` (and q4 also in `data["keywords"]`). In production, "User's Core Edge" and "Target Keywords" are always blank, so skills are never weighted against the job posting. Fixed on the branch that ships MiniMax.

## Final check on the shipped code

The branch's own `voice_api` (not captured payloads) drove the same six people through the summary and skills steps on MiniMax M3.1 Flash, then one resume went through the running server over HTTP. Every call returned HTTP 200 with `finish_reason: stop`; the slowest took 3.0s.

- **Run 1** (job keywords now reach the skills prompt): summaries were clean, but the model added three of the nurse's job keywords as skills she never listed (ICU, Critical Care, Patient Advocacy), listed two retail skills twice and kept "UM VBA". The old prompt's "1-29: ... (only include if user explicitly listed them)" implied the other tiers could include unlisted skills.
- **Run 2** (prompt now allows only the user's skills, each once, and may fix filler words like "um"):

| Check | Result |
|---|---|
| Summaries written by the model | 6 of 6 |
| First person / buzzwords | 0 of 6 / 0 of 6 |
| Invented numbers | none |
| Keyword coverage | 30 of 33 |
| Core edge and keywords present in the skills prompt | 6 of 6 |
| Skills invented / duplicated / in off-list categories | 0 / 0 / 0 (one reword: "mentoring junior devs" to "Mentoring Junior Developers") |
| Distinct weights per person | 6 to 11 |
| Characters the PDF fonts lack | 1 ("H₂S", printed as a black box); the app now NFKC-normalizes model text to "H2S" |

- **Over HTTP:** `/healthz` returned `"llm": true`; the summary step took 1.18s and the skills step 1.54s; both answers were written by the model.
- **Cost:** 26 calls, about $0.005.
- **Not from this change:** retail is offered mostly tech categories by `get_relevant_tiers`, so a store manager's skills land in "Other Skills".

## Outputs, side by side

### Backend Software Engineer (Technology)

Answers: core edge "I build backend systems that stay up and I ship fast without breaking things"; problems "slow APIs, flaky deployments, and databases that fall over under load"; numbers "cut API response time by 45 percent, moved 14 services to Kubernetes, 99.97 uptime last year"; keywords "Python, Go, Kubernetes, AWS, microservices, CI/CD".
Skills given: python, go, fast api, docker, kubernetes, AWS, postgres, redis, terraform, github actions, mentoring junior devs, code review.

**gpt-oss-20b summary:** Backend Software Engineer with a proven track record of delivering resilient, high‑performance systems. I cut API response times by 45 % and moved 14 services to Kubernetes, achieving 99.97 % uptime while ensuring rapid, reliable deployments on AWS. Skilled in Python, Go, microservices, and CI/CD, I eliminate flaky APIs and database failures under load.

**minimax-m3.1-flash summary:** Backend Software Engineer with proven experience building reliable Python and Go microservices on AWS and Kubernetes. I improve API performance, deployment stability, and database scalability, cutting response times by 45%, migrating 14 services to Kubernetes, and maintaining 99.97% uptime while accelerating delivery through effective CI/CD practices.

**gpt-oss-20b skills:** *Programming & Development:* Python 95, Go 90, FastAPI 92 · *Cloud & Infrastructure:* AWS 90, Terraform 80 · *DevOps & Automation:* Docker 85, Kubernetes 88, GitHub Actions 75 · *Databases & Data Storage:* PostgreSQL 85, Redis 80 · *Project & Program Management:* Mentoring Junior Developers 70, Code Review 70

**minimax-m3.1-flash skills:** *Programming & Development:* Python 98, Go 95, Code Review 85 · *Frameworks & Libraries:* FastAPI 95 · *Cloud & Infrastructure:* Docker 92, Kubernetes 94, AWS 96, Terraform 90 · *DevOps & Automation:* GitHub Actions 91 · *Databases & Data Storage:* PostgreSQL 92, Redis 88 · *Project & Program Management:* Mentoring Junior Developers 80

### Production Operator (Oil and Gas)

Answers: core edge "15 years running wells and compressors in East Texas with a clean safety record"; problems "unplanned downtime, equipment failures, and keeping crews safe"; numbers "zero recordable incidents in 6 years, kept 40 wells running at 98 percent uptime"; keywords "SCADA, well testing, H2S, OSHA, preventive maintenance".
Skills given: scada, well testing, compressor maintenance, H2S certified, OSHA 30, forklift, pipeline pigging, crew lead, excel.

**gpt-oss-20b summary:** Seasoned production operator with 15 years of experience running wells and compressors in East Texas, consistently maintaining a clean safety record and zero recordable incidents over six years. Expert in SCADA, well testing, and H2S management, I reduce unplanned downtime and equipment failures while keeping crews safe, achieving 98 % uptime across 40 wells through proactive preventive maintenance and OSHA‑compliant practices.

**minimax-m3.1-flash summary:** Production Operator with 15 years of experience running wells and compressors in East Texas, specializing in SCADA monitoring, well testing, H2S operations, and OSHA-compliant safety practices. Maintained 40 wells at 98% uptime through preventive maintenance and rapid response to equipment failures while achieving zero recordable incidents over six years. Consistently prevents unplanned downtime and keeps crews safe in demanding field environments.

**gpt-oss-20b skills:** *Safety & Risk Management:* H2S certified 95, OSHA 30 90 · *Heavy Equipment Operation:* forklift 85, pipeline pigging 80 · *Project & Program Management:* crew lead 60 · *Machining & Manufacturing:* compressor maintenance 75 · *Quality Control & Inspection:* well testing 70 · *Programming & Development:* scada 65 · *Other Skills:* excel 50

**minimax-m3.1-flash skills:** *Safety & Risk Management:* H2S Certified 95, OSHA 30 92 · *Heavy Equipment Operation:* Compressor Maintenance 88, Forklift Operation 78 · *Electrical Systems:* SCADA 82 · *Project & Program Management:* Crew Lead 58 · *Other Skills:* Well Testing 85, Pipeline Pigging 83, Microsoft Excel 45

### ICU Registered Nurse (Healthcare)

Answers: core edge "calm under pressure, 9 years in critical care, families trust me"; problems "patient deterioration caught too late, short staffing, new nurse onboarding"; numbers "precepted 22 new grads, cut central line infections on my unit by 30 percent"; keywords "ICU, critical care, ACLS, patient advocacy, EHR, Epic".
Skills given: ACLS, BLS, CRRT, ventilator management, Epic, IV therapy, precepting, spanish, patient education, sepsis protocols.

**gpt-oss-20b summary:** Seasoned ICU Registered Nurse with 9 years of critical care experience, adept at remaining calm under pressure and earning families’ trust. Proven in reducing central line infections by 30% and precepting 22 new graduates, I excel in patient advocacy, ACLS protocols, and efficient EHR (Epic) documentation to address deterioration, staffing gaps, and onboarding challenges.

**minimax-m3.1-flash summary:** ICU Registered Nurse with 9 years of critical care experience, recognized for calm leadership under pressure, patient advocacy, and earning families’ trust. Uses Epic, EHR, and ACLS expertise to identify early signs of patient deterioration and improve safe care during short staffing; precepted 22 new graduates and helped reduce central line infections on the unit by 30%.

**gpt-oss-20b skills:** *Healthcare & Medical:* ACLS 95, BLS 95, CRRT 95, ventilator management 95, Epic 95, IV therapy 95, precepting 95, spanish 95, patient education 95, sepsis protocols 95

**minimax-m3.1-flash skills:** *Healthcare & Medical:* ACLS 98, ventilator management 96, CRRT 94, IV therapy 92, sepsis protocols 91, Epic 82, BLS 80, patient education 78 · *Education & Training:* precepting 72 · *Customer Service & Hospitality:* Spanish 65

### Financial Analyst (Finance)

Answers: core edge "I turn messy spreadsheets into clear forecasts leadership actually uses"; problems "budget overruns, slow month-end close, bad forecasts"; numbers "built a forecast model that cut variance from 12 percent to 4 percent, shaved 3 days off close"; keywords "FP&A, financial modeling, Excel, SQL, forecasting, variance analysis".
Skills given: excel, power bi, sql, financial modeling, forecasting, variance analysis, quickbooks, presentations, um vba.

**gpt-oss-20b summary:** Financial Analyst with a proven track record of transforming chaotic spreadsheets into actionable forecasts that leadership trusts. Leveraging advanced FP&A, financial modeling, Excel, and SQL skills, I reduced forecast variance from 12% to 4% and cut month‑end close time by three days, eliminating budget overruns and accelerating decision‑making. My focus on variance analysis and precise forecasting drives accurate, timely insights for strategic planning.

**minimax-m3.1-flash summary:** Financial Analyst with expertise in FP&A, financial modeling, forecasting, and variance analysis across Excel and SQL. Builds clear, decision-ready forecast models that improve planning accuracy and help leadership address budget overruns, with one model reducing forecast variance from 12% to 4%. Streamlines month-end close processes, shaving 3 days from the close cycle while transforming complex financial data into actionable insights.

**gpt-oss-20b skills:** *Financial & Accounting:* Financial Modeling 95, Forecasting 92, Variance Analysis 90, Excel 88, Power BI 85, QuickBooks 70, SQL 70, VBA 70 · *Other Skills:* Presentations 40

**minimax-m3.1-flash skills:** *Financial & Accounting:* financial modeling 98, forecasting 94, variance analysis 92, Excel 90, QuickBooks 74 · *Research & Analysis:* Power BI 86 · *Databases & Data Storage:* SQL 84 · *Programming & Development:* VBA 66 · *Administrative & Operations:* presentations 52

### Licensed Electrician (Construction)

Answers: core edge "journeyman electrician who gets jobs passed on first inspection"; problems "failed inspections, code violations, jobs running over schedule"; numbers "wired 60 plus homes, 100 percent first-pass inspections last 2 years"; keywords "NEC, commercial wiring, troubleshooting, conduit bending, safety".
Skills given: NEC code, conduit bending, troubleshooting, panel upgrades, blueprint reading, PLC basics, OSHA 10, customer service.

**gpt-oss-20b summary:** Seasoned journeyman electrician with a 100 % first‑pass inspection record over the past two years, wiring 60+ residential and commercial properties. Expert in NEC compliance, conduit bending, and advanced troubleshooting, I consistently eliminate code violations and keep projects on schedule while prioritizing safety. My proven track record ensures reliable, high‑quality electrical installations that meet every client’s expectations.

**minimax-m3.1-flash summary:** Licensed Journeyman Electrician with experience in commercial wiring, NEC-compliant installations, conduit bending, and troubleshooting. Successfully wired more than 60 homes and achieved 100% first-pass inspections over the last two years by resolving code violations, preventing failed inspections, and keeping jobs on schedule. Committed to safe, high-quality electrical work that meets code and passes inspection the first time.

**gpt-oss-20b skills:** *Electrical Systems:* NEC code 95, conduit bending 90, panel upgrades 90, troubleshooting 85, blueprint reading 80, PLC basics 70 · *Other Skills:* OSHA 10 40, customer service 30

**minimax-m3.1-flash skills:** *Electrical Systems:* NEC code 98, conduit bending 95, troubleshooting 90, panel upgrades 92, blueprint reading 88, PLC basics 70 · *Other Skills:* OSHA 10 78, customer service 45

### Store Manager (Retail)

Answers: core edge "I build teams that hit numbers and stay"; problems "high turnover, shrink, and missed sales targets"; numbers "grew store sales 18 percent, cut turnover from 70 to 35 percent, managed 25 staff"; keywords "retail management, P&L, inventory, scheduling, customer experience".
Skills given: scheduling, inventory control, loss prevention, hiring, training, P&L, customer service, merchandising, POS systems.

**gpt-oss-20b summary:** Retail manager with a proven track record of building high‑performing teams that hit sales targets and reduce turnover. Increased store sales by 18% while cutting staff turnover from 70% to 35%, managing a 25‑person team and driving P&L, inventory, scheduling, and customer experience excellence. Skilled in retail management, I consistently deliver measurable results and sustainable growth.

**minimax-m3.1-flash summary:** Results-driven retail manager with proven success building high-performing teams and improving store profitability. Grew sales 18%, reduced turnover from 70% to 35%, and managed 25 employees while strengthening customer experience, P&L performance, inventory control, and scheduling.

**gpt-oss-20b skills:** *Other Skills:* scheduling 95, inventory control 95, loss prevention 95, hiring 95, training 95, P&L 95, customer service 95, merchandising 95, POS systems 95

**minimax-m3.1-flash skills:** *Other Skills:* P&L management 95, inventory control 95, scheduling 92, hiring 90, training 88, customer service 88, merchandising 85, POS systems 85 · *Safety & Risk Management:* loss prevention 95
