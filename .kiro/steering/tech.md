# Tech

## Stack (agreed in `TEAM_CONTRACTS.md` header)
- Backend: FastAPI with Pydantic models for all API-boundary data.
- Frontend: React + TypeScript, with a typed API client in `frontend/src/services/`.
- ML: standalone training workspace in `ml/`, separate from the backend runtime.

## Rules for implementation
- Shared Pydantic schemas in `backend/app/models/` are the executable source of truth for
  payloads. Request and response models must come from there, not from raw dicts.
- Route handlers stay thin and call the agreed service functions (`TEAM_CONTRACTS.md` §4).
- The frontend never imports Python or calculates risk, scores or tiers itself.
- Missing measurements stay `None`/null. Never default a missing SpO2 to zero.
- Use `Field(default_factory=list)` for Pydantic list defaults.
- Every cross-team function needs a fixture-backed stub so the app runs end to end early.
- No secrets in Git. Commit `.env.example`, never `.env`.

## Pending decisions (do not assume)
Python version, backend package manager, frontend package manager, CI commands, and final
API route names (`TEAM_CONTRACTS.md` §9). Do not create manifests or lockfiles that settle
these until the team confirms, unless the user explicitly directs it.

## Checks (once tooling exists)
Backend: lint and `pytest`. Frontend: typecheck, lint and build. See §6.7 and §7.
