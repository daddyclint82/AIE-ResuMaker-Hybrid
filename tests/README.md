# Test Suite Documentation

## File Separation Strategy

### `test_battle_full.py` — Full End-to-End Browser Test
- **Purpose:** Validates the complete user journey through the voice questionnaire.
- **Scope:** All 10 simple fields → multi-job experience with bullets → summary interview → skills categorization → all optional sections (projects, competencies, education, community, certifications, references, links) → preview + DOCX/PDF generation.
- **Runtime:** ~60–90 seconds (Playwright browser automation).
- **When to run:** Before commits, after major feature changes, or when verifying full pipeline integrity.

### `test_optional_boundary_patch.py` — Isolated Backend Regression Test
- **Purpose:** Fast regression guard for the optional section boundary fix (premature `phase=done` bug).
- **Scope:** Bootstraps directly at Community Entry 1, fills 2 entries, verifies `phase="optional"` is preserved at every decision boundary, confirms clean advancement to next section only after explicit "no" response.
- **Runtime:** ~200ms (no browser, direct state machine calls).
- **When to run:** During development of state machine changes, after any modification to `_process_optional()`, `_handle_optional_section()`, or `_advance_optional_section()`.

## Running Tests

```bash
# Fast regression test (backend only)
python3 tests/test_optional_boundary_patch.py

# Full battle test (requires server running on localhost:8000)
python3 tests/test_battle_full.py
```

## Test Data

Both tests use realistic resume data:
- `test_battle_full.py`: Clint Singleton's actual resume content (DevOps Engineer profile)
- `test_optional_boundary_patch.py`: Minimal synthetic data focused on boundary conditions
