# Team ID Example Standardization Report

**Date:** 2026-08-06
**Role:** Platform Engineer + QA Engineer + Technical Writer
**Goal:** Replace every example/placeholder use of the developer's personal FPL
Team ID with the canonical example `123456`; treat the old value as sensitive
user-specific information and remove it from the public repository.

---

## 1. Result Summary

| Metric | Value |
|---|---|
| Files updated | **10** |
| Replacements made | **28** |
| Remaining references to the old Team ID | **0** (working tree) |
| Full test suite | **170 passed** |
| Ruff | **All checks passed** |
| Onboarding flow | **29 onboarding/team tests passed; modules import cleanly** |

## 2. Canonical Example Team ID

**`123456` is now the canonical example FPL Team ID** used throughout the
project (UI placeholders, onboarding tutorial text, sample code, documentation
examples, code comments, and test fixtures).

## 3. Changes Made (10 files, 28 replacements)

### 3.1 Examples / placeholders / tests → `123456` (5 files, 17 replacements)

| File | Replacements | Nature |
|---|---|---|
| `components/onboarding.py` | 3 | Input placeholder `e.g. 123456`; `/entry/123456/` tutorial text (2) |
| `docs/onboarding.md` | 5 | Sidebar example block; sample `set_current_team_id(123456, …)`; sample `validate_team_id("123456")`; user-guide `/entry/123456/` text (2) |
| `tests/test_api_client.py` | 4 | Test fixtures verifying URL/HTTP-error redaction (any ID is redacted) |
| `tests/test_team_id.py` | 4 | Test fixtures exercising session persistence / change-team |
| `database/models.py` | 1 | Comment example `# e.g. "team:123456"` |

### 3.2 Historical / audit documents → redacted (5 files, 11 replacements)

These documents record the *past defect* factually (the developer's personal
Team ID was once hardcoded in `utils/constants.py`). Replacing the value with
`123456` there would falsify the historical record (123456 was never the
hardcoded value), so the personal ID was **redacted** to the neutral token
`<developer's team ID>` while preserving each statement's meaning.

| File | Replacements | Nature |
|---|---|---|
| `ENGINEERING_HISTORY.md` | 5 | History narrative (2), pre-audit architecture box, risk register R3, product-arc timeline |
| `DEPLOYMENT_READINESS_PHASE1.md` | 3 | Risk table R3, detailed finding, config inventory table |
| `EXECUTIVE_AUDIT_REPORT.md` | 1 | Finding M-13 issue statement |
| `MEDIUM_ISSUES_SENIOR_MANAGER.md` | 1 | Finding M-13 description |
| `docs/ux_discovery_audit.md` | 1 | Discovery audit auth-row snapshot |

## 4. Intentional Exceptions

1. **Historical/audit records** — redacted with `<developer's team ID>` (not
   `123456`) to avoid falsifying the append-only record. Chosen by the owner.
2. **Git history** — the working tree is fully purged, but the old value
   still exists inside earlier commits' blobs. History rewriting (e.g.
   `git filter-repo`) was **not** performed; it is available on request if the
   value must be removed from history before making the repository public.

## 5. Verification

- `grep -rn "472930" .` → **zero matches** across all tracked files
  (excluding `.venv`, `.git`, `data/`).
- `pytest -q` → **170 passed** (full suite; 2648 pre-existing warnings from
  `datetime.utcnow` deprecations and deliberate `# noqa` annotations).
- `ruff check .` → **All checks passed**.
- Onboarding flow → `tests/test_team_id.py` + `tests/test_team_validation.py`:
  **29 passed**; `components.onboarding` and `components.sidebar` import
  cleanly in a fresh environment.
- Documentation/example URLs verified at the source (all reference
  `/entry/123456/`).

## 6. Functional Impact

**None.** No production logic, validation logic, API behavior, runtime session
values, database records, or user-entered Team IDs were modified. This was a
documentation, example, and developer-experience cleanup only. All changed
lines are in docs, UI copy, code comments, or test fixtures.
