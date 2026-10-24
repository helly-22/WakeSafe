# Ownership

Full ownership and deliverables: `TEAM_CONTRACTS.md` §2. Collaboration rules: §6.

| Owner | Paths | Delivers |
| --- | --- | --- |
| Dhev | `ml/`, `backend/app/ml/`, `services/whoop/`, `services/screening/` | `load_nights`, `compute_features`, `score_apnea`, evaluation metrics |
| Helly | `services/risks/`, `services/care/`, `services/explanations/`, hospital data | `assess_risks`, `recommend_care`, `explain` |
| Ee | `frontend/`, `backend/app/api/`, `services/reports/`, `README.md`, `docs/`, `.kiro/steering/`, `slides/` | UI, routes, `build_report` and PDF, pitch |

(`services/` paths are under `backend/app/`.)

Proposed, pending team approval: Ee also owns `backend/app/main.py`, `core/`, `infra/`, `scripts/`.

## Shared / protected (no unilateral changes)
- `backend/app/models/` (shared schemas), `.gitignore`, CI config, API route contracts.
- Dependency files: append only; coordinate removals and version conflicts.
- `TEAM_CONTRACTS.md`: propose changes; interface or ownership changes need team approval.

## Working rules
- Stay inside your owner's paths. Reviewing another module is fine; committing
  implementation changes there needs an explicit team agreement.
- Work on a personal branch (for example `ee/app-report`), pull `main` before starting,
  and merge through pull requests.
- Changing a shared contract means updating the doc, the Pydantic schemas, fixtures,
  TypeScript types and contract tests together (`TEAM_CONTRACTS.md` §6.5).
- Do not silently alter agreed function names, argument names, return types or semantics.
