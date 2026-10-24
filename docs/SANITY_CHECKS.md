# Sanity checks

How to verify WakeSafe locally, and what the last run found.

Last run: 2026-10-24 on `main` at `8a4d5e3`, Windows, Python 3.11.9, Node 24.19.0.

## How to run

Python dependencies come from `requirements.txt` (repo root). Run each suite from the
folder shown; there is no shared `conftest.py` or `pytest.ini` yet.

| Check | Folder | Command |
| --- | --- | --- |
| Backend tests | `backend/` | `python -m pytest -q` |
| ML feature tests | repo root | `python -m pytest ml/tests -q` |
| Script tests | repo root | `python -m pytest scripts/tests -q` |
| Synthetic data tests | `synthetic_data/` | `python -m pytest -q` |
| Frontend install | `frontend/` | `npm ci` |
| Frontend typecheck + build | `frontend/` | `npm run build` |
| Frontend dev server | `frontend/` | `npm run dev` (http://localhost:5173) |

Run the backend tests from `backend/`. From the repo root,
`services/explanations/tests/test_explain.py` fails to import `app`.

## Results

| Check | Result |
| --- | --- |
| Backend tests | 133 passed |
| ML + script tests | 14 passed, 3 skipped (PhysioNet Apnea-ECG data not downloaded; `ml/data/` is gitignored) |
| Synthetic data tests | 45 passed |
| Frontend typecheck + build | Passed (no linter is configured) |

### End-to-end pipeline

No committed test chains every backend module, so a one-off script ran all 66 demo personas
(65 synthetic + 1 fixture) through
`load_nights -> compute_features -> score_apnea -> assess_risks -> recommend_care -> explain`,
plus the CSV upload path and the live-WHOOP stub.

Passed for every persona:

- Every step returns valid contract models, and the report round-trips through JSON.
- Missing SpO2 stays `None`, never 0.
- Synthetic data is flagged as synthetic; CSV uploads are not.
- No apnea probability is exposed.
- Every red-flag persona sets `urgent_override`, gets care tier `Urgent` and 911 guidance.
- `Urgent` never appears without the override.
- No diagnostic wording ("you have ...", "diagnosed with") in explanations or factors.
- Live WHOOP raises `NotImplementedError` without credentials.

Tier spread: apnea Low 39, Moderate 17, High 10; 2 urgent overrides.

## Known issues

1. **Care ranking ignores the real hospital data.** With `backend/app/data/hospitals.csv`,
   all 330 recommendations had no drive time, `capacity_source="unknown"` and no specialty
   match, so every facility scores 0.15 and the list is just CSV order, regardless of risk or
   location. Causes in `services/care/matcher.py`:
   - It reads `latitude`/`longitude`; the CSV has `lat`/`lon`.
   - It matches specialties like `sleep medicine` and `cardiology`; the CSV uses tokens like
     `emergency`, `icu`, `ccu_cardiac`, `med_surg`.
   - It imports `get_capacity_score`, which `capacity.py` does not define, so the capacity
     providers are never used.

   `tests/test_care_matcher.py` only uses the matcher's inline fixture, so the suite misses this.
2. **Signatures differ from `TEAM_CONTRACTS.md` §4.2.** `recommend_care` takes positional
   `user_lat, user_lon, csv_path, max_results` (contract: keyword-only `latitude, longitude,
   limit`). `explain` takes a `ClinicianReportData` (contract: `assessment, features,
   apnea_score`).
3. **`fixtures/nights_sample.csv` holds two people** (P001, P002). The CSV uploader accepts
   one person per file, so uploading it as-is is rejected.
4. **Not built yet:** FastAPI app, `main.py` and routes; `services/reports` (report and PDF);
   live WHOOP OAuth. `requirements.txt` has no `fastapi`/`uvicorn` and no pinned versions.
5. **The frontend runs on built-in mock data** (`VITE_USE_MOCKS=true` by default), since the
   API routes it calls (`/api/demo/personas`, `/api/screening/analyze`) don't exist yet.
