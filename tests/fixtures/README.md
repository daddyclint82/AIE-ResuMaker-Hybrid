# Test Fixtures README

## What's Here

| File | Purpose |
|------|---------|
| `clint-devops-ai.json` | **Your actual resume** — 3 jobs, DevOps/AI targeting, full custom summary answers |
| `template-generic.json` | **Copy this** to create new tests for different jobs/targets |

## How to Create a New Test

1. **Copy the template:**
   ```bash
   cp template-generic.json my-new-resume.json
   ```

2. **Fill in your answers** — replace `[BRACKETED]` text with real values

3. **Adjust expected_results:**
   - `jobs`: How many jobs you're adding
   - `bullets_per_job`: How many bullets per job (usually 3)
   - Set `skills_categorized: true` if you want to test Groq categorization

4. **Run it:**
   ```bash
   cd tests
   python run_questionnaire.py fixtures/my-new-resume.json
   ```

## Structure

```
tests/
├── fixtures/
│   ├── clint-devops-ai.json      # Your actual test data
│   ├── template-generic.json     # Start here for new tests
│   └── README.md                 # This file
├── run_questionnaire.py          # Universal runner (works with any fixture)
└── [future: validate_results.py] # Additional validators
```

## Fixture Format

Each fixture is a JSON object with:
- `name`: Human-readable test name
- `target_job`: What job this targets
- `description`: What this test covers
- `answers`: Array of step objects (step, phase, field, value)
- `expected_results`: Validation criteria (job count, bullets, etc.)

## To Add More Jobs

Copy steps `2A1-2A10` and rename to `2B1-2B10`, `2C1-2C10`, etc. Set `_add_job` to `"done"` on the last job.

## To Add Optional Sections

Change `"skip"` to `"yes"` for the section you want, then add the field answers after the decision step.

## Future Fixtures

- `nurse-healthcare.json`
- `electrician-trades.json`
- `software-engineer-tech.json`
- `project-manager-general.json`

---

*All fixtures should be committed to git so tests are reproducible across environments.*