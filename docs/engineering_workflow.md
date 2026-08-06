# Engineering Workflow — Manny's FPL House

How this project is actually built: leadership, roles, the AI-assisted
implementation loop, human review, approval, and the scientific philosophy that
governs every change to prediction behaviour.

## 1. Project Leadership

| Role | Responsibility |
|---|---|
| **Director** | Final decision-maker. Approves sprints, phase boundaries, model promotions, and any change to prediction/validation behaviour. Freezes prediction behaviour between phases. |
| **Senior Engineering Manager** | Translates Director priorities into scoped sprints (e.g. Phase 1 foundation, Phase 2 security/onboarding, verification sprints). Routes work to workstreams, reviews the evidence, and signs off readiness. |

## 2. Engineering Workstreams

| Workstream | Owner | Scope |
|---|---|---|
| **Platform Engineer** | DevOps / Full-stack | Deployment, configuration, environment, logging, security, git, CI/CD, docs tooling |
| **IT Manager** | Infrastructure | Hosting, backups, operational monitoring, recovery runbooks, environment provisioning |
| **Security Manager** | Security | Access control (`ADMIN_TOKEN` gate), secret handling, audit trail, TLS/SSL posture, dependency scanning, least-privilege CI |
| **Data Engineer** | Data | Database schema, Alembic migrations, FPL API reliability (retry/backoff), persistence, append-only ledgers |
| **ML / Analytics Engineer** | ML | Prediction engines, Feature Store, weights, validation platform, confidence, evidence ladder |
| **QA Engineer** | QA | Test coverage, lint, CI gates, regression safety, verification sprints |
| **Technical Writer** | Docs | Architecture, configuration, deployment, database, prediction, validation, operations, engineering history |

Every component has an owner; nothing drifts unowned. Cross-workstream changes
are coordinated and documented before they land (see `docs/stakeholders.md`).

## 3. The OpenCode Implementation Workflow

Development is assisted by **OpenCode**, an interactive AI coding agent that
works in the repository. The workflow is deliberately structured so the human
keeps control at every decision point:

1. **Investigate first.** Before any code change, the agent reads the relevant
   files, searches the codebase, checks git history and audits. Understanding
   precedes editing.
2. **Plan.** Non-trivial work is captured as an explicit task list (research →
   implement → verify) so progress and intent are visible.
3. **Implement.** Changes are made with the existing code's conventions:
   single source of truth, existing utilities, no duplicate formulas.
4. **Verify.** The full test suite, `ruff check`, and any validation tools run
   before a change is considered done.
5. **Report.** Findings and decisions are summarised for the human — including
   *why* a change was or was not made.

### Rules the agent follows

- **Do not assume — verify.** Audit findings are reproduced or disproven before
  any fix is written (this is why verification sprints exist).
- **No redesign.** Bug fixes and hardening stay local; architecture is only
  changed through an explicit approved plan.
- **Preserve append-only history.** Validation metrics, projection ledgers and
  audit logs are never edited or deleted.
- **Backward compatibility.** Every change must keep existing functionality
  working; tests must pass before and after.

## 4. Human Review and Approval

OpenCode proposes; humans dispose. The loop is:

1. Agent implements and runs the verification gates.
2. **Human review** — a senior engineer (or the Director for behaviour changes)
   reads the diff, the tests, and the verification output.
3. **Approval** — nothing reaches `main` without explicit approval. Model or
   prediction changes additionally require Director sign-off.
4. **Commit** — commits happen only on explicit instruction; `main` stays
   linear and deployable, one logical change at a time.

## 5. Scientific Validation Philosophy

The platform's core discipline is: **a model only earns the right to act by
proving itself against real outcomes.**

- **Freeze.** Between phases, prediction/validation behaviour is frozen — no
  weight tuning or model changes without Director approval. Phase 1 and Phase 2
  explicitly changed *no* prediction behaviour.
- **Shadow / control.** A new model (e.g. V3 expected points) ships alongside
  the production model as a shadow, persisted and validated against actuals
  before it is ever promoted. V1/V2 continue running as control models.
- **Append-only ledger.** Every forecast is a versioned record with a config
  hash; nothing is overwritten, so claims can be audited retroactively.
- **Evidence ladder.** Trust is gated by validated-gameweek count
  (weak → needs_more_data → moderate → strong → established). The tiers are
  sample-size maturity heuristics, **not** formal statistical significance —
  no model change is ever automatic, and each tier requires more validated data.
- **No automatic promotion.** Even with strong evidence, promoting a model is a
  human decision supported by a comparison report, never an automatic switch.

## 6. Code Review

- **Automated gates (CI)** — `.github/workflows/ci.yml` runs on every push/PR
  to `main`: `ruff check`, `pip check`, a secrets-pattern scan, and the full
  `pytest` suite. The job runs with least-privilege `contents: read` permissions.
- **Manual review** — diffs are reviewed for correctness, convention adherence,
  and scope creep. One logical change per branch.
- **Prediction safety** — any diff touching projection/weight/validation code
  is flagged for ML-owner + Director review even when behaviour-preserving.

## 7. Risk Management

- **Audit reports** — formal read-only audits score readiness (e.g. Executive
  Audit, Deployment Readiness) and produce **Critical / High / Medium / Low**
  issue registers with owners.
- **Issue registers** — `MEDIUM_ISSUES_SENIOR_MANAGER.md` / `LOW_ISSUES_SENIOR_MANAGER.md`
  track M-01… and L-01… items; a TD (technical debt) register tracks deferred
  items like engine retirement.
- **Latent-bug discipline** — known defects are documented in place with
  `TODO(latent-bug)` markers and a register, then fixed only through verified
  sprints.
- **Fail loudly** — no silent SSL downgrade, no silently swallowed errors
  where a user action is at risk; graceful degradation is reserved for
  best-effort report sections.

## 8. Evidence-Based Development

- **Config-hash traceability** — every prediction run records the SHA-256 of
  the active config, so a result is always reproducible to the exact weights.
- **Per-workstream reports** — each phase produces Platform, Data, ML, QA,
  Technical Writer and combined reports that become the audit trail.
- **Engineering history** — `ENGINEERING_HISTORY.md` is the authoritative
  retrospective, updated at phase boundaries so future contributors inherit
  the *why*, not just the *what*.

## 9. Decision Records

Significant decisions are captured as decision records (DR-1 … DR-11) in
`ENGINEERING_HISTORY.md` Appendix F — promotion to V3, shadow/control design,
security model, onboarding scope, and more. If a decision changed the
prediction pipeline, the record states what evidence supported it.
