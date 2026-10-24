# Structure

The repository layout is fixed. Canonical tree and comments: `TEAM_CONTRACTS.md` §2 and `README.md`.

```text
backend/app/   api, core, models, ml, data, services/{whoop,screening,risks,care,explanations,reports}, db, utils, main.py
backend/tests/
frontend/src/  components, pages, features, hooks, services, lib, assets
ml/            notebooks, data (ignored), models (ignored), training
infra/  docs/  scripts/  slides/  .kiro/steering/
```

## Placement rules
- `backend/app/models/` holds shared Pydantic schemas only. No ORM models there.
- `backend/app/ml/` holds only a small, team-approved runtime model artifact and metadata.
  Training outputs stay in the gitignored `ml/models/`.
- `backend/app/db/` is an unused placeholder unless persistence is deliberately added.
- Hospital data lives at `backend/app/data/hospitals.csv` (proposed, pending approval).
- Datasets, tokens and model files must not be committed; `.gitignore` is protected.
- Empty folders carry a `.gitkeep`; remove it when the first real file lands.

## Do not
- Do not move, rename or restructure folders without a contract change.
- Do not create files outside the owner's paths (see `ownership.md`).
