# WakeSafe Team Contract

**Status:** Draft for team review\
**Architecture:** FastAPI backend + React/TypeScript frontend +
standalone ML training workspace\
**Purpose:** Keep all three teammates and their coding agents aligned on
module ownership, function interfaces, API schemas, data provenance, and
integration rules.

> This document describes the team agreement. The executable source of
> truth for API payloads is the shared Pydantic schema code in
> `backend/app/models/` (or the agreed schema module within that
> directory). Update both this document and the executable schemas when
> a shared interface changes.

## 1. Product scope and safety boundary

WakeSafe uses wearable-style sleep and recovery summaries plus
user-reported history to surface **screening risks** and suggest
appropriate care navigation. It is not a diagnostic tool.

-   The default demo must work with synthetic WHOOP-format data. Live
    WHOOP OAuth integration is optional.
-   Synthetic demo data may be used for UI, tests, fixtures, and
    demonstrations only. It must never train or evaluate the model, or
    be represented as real patient data.
-   Model evaluation must use the selected open sleep-study datasets and
    report the sample size and limitations.
-   Distinguish **patient-reported**, **wearable-measured**,
    **app-calculated**, **model-estimated**, and **simulated**
    information.
-   Never tell a user they have sleep apnea or another disease. Use
    "screening result," "risk signal," and "consider discussing with a
    clinician."
-   Red-flag symptoms (for example chest pain, fainting, severe
    shortness of breath, or stroke symptoms) must bypass routine care
    recommendations and display emergency guidance to call 911.
-   Never present simulated occupancy as live hospital capacity.
-   Do not commit credentials, real identifiers, WHOOP tokens, raw
    private health data, or downloaded datasets/model artifacts that are
    excluded by `.gitignore`.

## 2. Repository layout and ownership

Keep the current repository architecture. New paths below are the agreed
target locations; create them if they do not yet exist.

``` text
WakeSafe/
├── backend/
│   ├── app/
│   │   ├── api/                 # FastAPI route handlers
│   │   ├── core/                # Settings, security, logging
│   │   ├── models/              # Shared Pydantic request/response schemas ONLY (no ORM models)
│   │   ├── ml/                  # Dhev: small approved runtime model artifact + metadata, loaded by services/screening
│   │   ├── data/                # Helly: runtime reference data (hospitals.csv)
│   │   ├── services/
│   │   │   ├── whoop/           # Dhev: data-provider adapters, if placed here
│   │   │   ├── screening/       # Dhev: runtime feature/model inference
│   │   │   ├── risks/           # Helly: rule-based risk assessment
│   │   │   ├── care/            # Helly: facility matching/capacity
│   │   │   ├── explanations/    # Helly: guarded natural-language explanations
│   │   │   └── reports/         # Ee: structured report + PDF rendering
│   │   ├── db/                  # Unused placeholder; only populated if persistence is deliberately added
│   │   ├── utils/
│   │   └── main.py              # FastAPI application entry point (to be created by Ee)
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── features/
│       ├── hooks/
│       ├── services/            # Typed API client
│       ├── lib/                 # Shared TS types/helpers
│       └── assets/
├── ml/
│   ├── notebooks/
│   ├── data/                    # Downloaded data; ignored by Git
│   ├── models/                  # Trained artifacts; ignored unless explicitly approved
│   └── training/
├── infra/
├── docs/
├── scripts/
├── slides/
├── .kiro/steering/              # Ee: product, tech, structure, ownership, safety rules
├── .gitignore                   # Protected (see Shared / protected files)
├── TEAM_CONTRACTS.md
└── README.md
```

Empty folders for the paths above are committed with `.gitkeep`
placeholders. Owners add their files inside their folders and may delete
the placeholder when the first real file lands. Implementation files
(`main.py`, dependency files, `.env.example`, schemas, services, CI) are
created by their owners as part of their tasks, not in advance.

### Dhev --- data and apnea model

Owns: - `ml/` (training, feature extraction from source datasets,
evaluation scripts and notebooks) - `backend/app/ml/` (only the small,
team-approved runtime model artifact and its metadata; training outputs
stay in the gitignored `ml/models/`) - `backend/app/services/whoop/`
(synthetic/CSV provider adapters and optional WHOOP adapter) -
`backend/app/services/screening/` (runtime features, personal baselines
and model inference) - Associated tests and fixtures for data and
screening functions

Delivers: - `load_nights(...)` - `compute_features(...)` -
`score_apnea(...)` - Dataset-level evaluation outputs and a concise
metrics summary for the pitch.

### Helly --- risk engine and care matching

Owns: - `backend/app/services/risks/` - `backend/app/services/care/` -
`backend/app/services/explanations/` - Facility dataset at the
canonical path `backend/app/data/hospitals.csv` (proposed; pending team
approval) - Tests for rule scoring, urgent
override, explanations and care ranking

Delivers: - `assess_risks(...)` - `recommend_care(...)` - `explain(...)`

### Ee --- app, clinician report and pitch

Owns: - `frontend/` - `backend/app/api/` route handlers and API
integration - `backend/app/services/reports/` - `README.md`, `docs/`,
`.kiro/steering/`, `slides/` - `backend/app/main.py`, `backend/app/core/`
(settings, logging, CORS), `infra/` and `scripts/` (proposed; pending
team approval, since these had no owner) - End-to-end integration tests
and the demo script

Delivers: - Typed React UI for intake, persona selection, dashboard,
care navigation and report download - FastAPI routes that connect the
agreed service functions - `build_report(...)` and a downloadable
clinician PDF - README, limitations/pitch materials and rehearsed demo

### Shared / protected files

-   `backend/app/models/`: shared Pydantic schemas. No agent changes
    these unilaterally. Database/ORM models, if persistence is ever
    added, belong in `backend/app/db/`, not here.
-   `backend/app/utils/`: shared helpers; append-only, and do not change
    existing helpers without telling the others.
-   `requirements.txt` or backend dependency file: append dependencies
    only; coordinate removals and version conflicts.
-   `.gitignore` (already created; it ignores `ml/data/*`, `ml/models/*`,
    `.env*` and raw sleep-study formats), CI configuration and API route
    contracts: changes
    affecting all teammates require review.
-   `TEAM_CONTRACTS.md`: any teammate may propose a change, but the team
    must approve changes that affect interfaces or ownership.

A teammate may review another module but should not commit
implementation changes in another owner's files unless explicitly agreed
in a team message or pull request.

## 3. Shared data contracts

Use Pydantic models for API-boundary data and typed Python structures
for internal service outputs. The names and fields below are the agreed
target interface; if the team already has implemented schemas, compare
them against this section before replacing anything.

### 3.1 `ProfileInput`

User-provided intake data. All fields that are not required for a
particular flow should be optional.

``` python
class ProfileInput(BaseModel):
    age: int | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    neck_circumference_cm: float | None = None
    conditions: list[str] = []
    snoring: bool | None = None
    daytime_tiredness: bool | None = None
    witnessed_breathing_pauses: bool | None = None
    hypertension: bool | None = None
    red_flag_symptoms: list[str] = []
    location_lat: float | None = None
    location_lon: float | None = None
```

Implementation note: use `Field(default_factory=list)` for list defaults
in Pydantic models. Validate age and measurements when supplied. Do not
require a person's name or date of birth for the demo.

### 3.2 `NightRecord`

One record per night, with WHOOP-v2-style field names where applicable.
Provider-specific raw payloads should be normalized before reaching the
shared pipeline.

``` python
class NightRecord(BaseModel):
    night_id: str
    date: date
    resting_heart_rate_bpm: float | None = None
    hrv_rmssd_ms: float | None = None
    spo2_pct: float | None = None
    respiratory_rate_rpm: float | None = None
    skin_temperature_c: float | None = None
    sleep_duration_minutes: float | None = None
    sleep_efficiency_pct: float | None = None
    deep_sleep_minutes: float | None = None
    rem_sleep_minutes: float | None = None
    disturbance_count: int | None = None
    sleep_consistency_pct: float | None = None
    source: Literal["synthetic", "csv", "whoop"] = "synthetic"
```

Missing readings must remain missing (`None`/null); do not silently
replace missing SpO₂ or other measurements with zero.

### 3.3 `FeatureSet`

``` python
class FeatureSet(BaseModel):
    values: dict[str, float | None]
    baseline_z_scores: dict[str, float | None]
    nights_available: int
    nights_with_spo2: int
    data_quality_flags: list[str] = []
    window_start: date | None = None
    window_end: date | None = None
```

Features should include available nightly summaries and useful
personal-baseline deviations. Document units and the aggregation window.
Avoid treating an unavailable signal as normal.

### 3.4 `ApneaScore`

``` python
class ApneaScore(BaseModel):
    tier: Literal["Low", "Moderate", "High"]
    probability: float | None = None
    stop_bang_score: int | None = None
    top_factors: list[str] = []
    model_version: str
    evidence_note: str
```

The probability is optional and must only be populated if the model
produces a meaningful, documented probability. Do not present it as a
diagnosis or as validated WHOOP-specific accuracy.

### 3.5 `RiskItem` and `RiskAssessment`

``` python
class RiskItem(BaseModel):
    risk_id: str
    display_name: str
    tier: Literal["Low", "Moderate", "High", "Urgent"]
    reasons: list[str]
    evidence_rating: Literal["Weak", "Weak to moderate", "Moderate", "Strong"]
    suggested_specialty: str
    source_labels: list[Literal[
        "patient_reported", "wearable_measured", "app_calculated",
        "model_estimated", "simulated"
    ]]

class RiskAssessment(BaseModel):
    risks: list[RiskItem]
    urgent_override: bool
    urgent_reasons: list[str] = []
    rules_version: str
    disclaimer: str
```

`Urgent` is reserved for the explicit red-flag override or another
team-approved emergency rule, not merely a high model probability. The
user interface must render emergency instructions before normal care
recommendations when `urgent_override=True`.

### 3.6 `FacilityRecommendation`

``` python
class FacilityRecommendation(BaseModel):
    facility_id: str
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    specialties: list[str]
    drive_minutes: float | None = None
    capacity_score: float | None = None
    capacity_source: Literal["static", "simulated", "live", "unknown"]
    rank_score: float
    notes: list[str] = []
```

Facility information and specialty listings must be verified against a
credible source. If occupancy is simulated, `capacity_source` must be
`"simulated"` and the UI must show that label. Do not imply that the app
dispatches emergency services or guarantees facility availability.

### 3.7 `CareRecommendations`

``` python
class CareRecommendations(BaseModel):
    recommendations: list[FacilityRecommendation]
    care_tier: Literal["Routine", "Elevated", "Urgent"]
    disclaimer: str
```

For urgent red flags, the API should return emergency guidance and
should not make a routine facility list the primary action.

### 3.8 `Explanation`

``` python
class Explanation(BaseModel):
    summary: str
    risk_explanations: dict[str, str]
    limitations: list[str]
    generated_by: Literal["template", "llm"]
```

Explanations may rephrase structured outputs only. The explanation layer
must not change scores, tiers, measurements, clinical urgency or
recommended destinations. A deterministic template fallback must work if
an LLM is unavailable.

### 3.9 `ClinicianReportData`

``` python
class ClinicianReportData(BaseModel):
    generated_at: datetime
    window_start: date | None = None
    window_end: date | None = None
    profile_summary: dict[str, str | int | float | bool | None]
    apnea_score: ApneaScore | None = None
    risk_assessment: RiskAssessment
    features: FeatureSet
    nights: list[NightRecord]
    explanations: Explanation | None = None
    device_label: str
    data_provenance: list[str]
    model_version: str | None = None
    rules_version: str | None = None
```

The PDF generator uses this structured object; it must not independently
infer risk or invent measurements. Patient identifiers are optional and
should be omitted from demo reports.

## 4. Function contracts by owner

The signatures below are illustrative target signatures. Agree them as a
team and implement them consistently; do not allow agents to silently
alter argument names, return types or semantics.

### 4.1 Dhev: provider and apnea screening

#### `load_nights`

``` python
def load_nights(
    source: Literal["synthetic", "csv", "whoop"] = "synthetic",
    *,
    persona_id: str | None = None,
    csv_file: str | None = None,
    profile: ProfileInput | None = None,
) -> list[NightRecord]:
    ...
```

Requirements: - `synthetic` is the default and works offline. - `csv`
normalizes uploaded CSV data to `NightRecord` and returns useful
validation errors for invalid files. - `whoop` is optional and must fail
gracefully when credentials are not configured. - Never log OAuth tokens
or raw sensitive payloads. - Every record must preserve source
provenance.

#### `compute_features`

``` python
def compute_features(
    nights: list[NightRecord],
    *,
    baseline_nights: int = 14,
) -> FeatureSet:
    ...
```

Requirements: - Calculate documented summaries and baseline deviations
from available nights. - Handle missing signals and insufficient history
explicitly. - Return the number of nights and SpO₂ availability
counts. - Use consistent units and stable feature names. - Do not train
or evaluate models on synthetic records.

#### `score_apnea`

``` python
def score_apnea(
    profile: ProfileInput,
    features: FeatureSet,
) -> ApneaScore:
    ...
```

Requirements: - Combine STOP-Bang-style inputs with the agreed screening
model/rules. - Return the tier and top factors in stable fields. - Do
not claim diagnostic certainty. - Record the model version and evidence
limitations. - Keep thresholds/configuration explicit and tested.

Dhev also owns model training/evaluation scripts under `ml/training/`.
Evaluation must use real open sleep-study data, with subject-wise
validation where feasible, and report dataset size, metrics and
uncertainty. Synthetic personas are for demonstration and testing only.

### 4.2 Helly: risk engine, care matching and explanations

#### `assess_risks`

``` python
def assess_risks(
    profile: ProfileInput,
    features: FeatureSet,
    apnea_score: ApneaScore | None,
) -> RiskAssessment:
    ...
```

Requirements: - Produce the agreed risk items for sleep-disordered
breathing and history-driven categories. - Each risk must include tier,
reasons, evidence rating, specialty and source labels. - Apply the
red-flag override deterministically. - Keep rules versioned and
independently testable. - Do not present weakly supported secondary risk
rules as validated predictions.

#### `recommend_care`

``` python
def recommend_care(
    assessment: RiskAssessment,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    limit: int = 5,
) -> CareRecommendations:
    ...
```

Requirements: - Match facilities to the specialty and care tier. - Rank
using the agreed specialty fit, capacity and proximity formula; document
the formula and missing-data fallback. - Use real facility locations and
verified specialty information. - Label capacity data as static,
simulated, live or unknown. - If `assessment.urgent_override` is true,
return urgent guidance rather than implying that the app can select an
emergency destination or replace calling 911.

#### `explain`

``` python
def explain(
    assessment: RiskAssessment,
    features: FeatureSet,
    apnea_score: ApneaScore | None = None,
) -> Explanation:
    ...
```

Requirements: - Explain existing structured results in plain language. -
Use a template fallback if the LLM is unavailable. - Do not create new
facts, numbers, diagnoses or tiers. - Guard against unsupported
diagnostic wording.

Helly owns facility data and tests for low/medium/high/urgent
conditions, ranking, missing capacity information, and emergency
override behavior.

### 4.3 Ee: API, frontend, report and pitch

#### Frontend API calls

The frontend must use a typed API client in `frontend/src/services/`. It
must not import Python modules or implement its own risk calculations.

Expected endpoints (final route names may be changed only by
agreement): - `GET /api/health` --- service health check. -
`GET /api/demo/personas` --- available synthetic demo personas. -
`POST /api/screening/analyze` --- profile plus selected data
source/persona; returns features, apnea score, risk assessment,
explanations and provenance. - `POST /api/care/recommendations` ---
assessment plus location; returns care recommendations. -
`POST /api/reports/preview` --- returns report metadata/preview data. -
`POST /api/reports/pdf` --- returns a PDF download response.

The analyze endpoint may orchestrate the agreed Dhev and Helly
functions, but route handlers should remain thin. Request and response
models must come from the shared Pydantic schema module.

#### `build_report`

``` python
def build_report(
    profile: ProfileInput,
    nights: list[NightRecord],
    features: FeatureSet,
    apnea_score: ApneaScore | None,
    assessment: RiskAssessment,
    explanations: Explanation | None = None,
) -> ClinicianReportData:
    ...
```

Requirements: - Construct structured report data only; no independent
scoring. - Include patient-reported context, measured trends,
calculated/model-estimated findings, missing-data counts, evidence
limitations and suggested clinical follow-up. - Include report
generation time, data window, model/rules versions and provenance. -
Keep names and dates of birth optional. - Provide a PDF renderer that
supports preview/download, readable black-and-white printing, trend
charts and a nightly-values appendix. - Validate generated wording and
ensure all reported numbers originate from structured data.

#### UI deliverables

-   Synthetic persona picker and CSV upload entry point.
-   Medical-history and STOP-Bang-style intake.
-   Risk dashboard with tiers, reasons, evidence ratings and trend
    charts.
-   Care-navigation map and ranked list.
-   Clearly visible synthetic-data and simulated-capacity labels.
-   Emergency screen for red-flag symptoms.
-   Clinician report preview and download.
-   Screening-only disclaimer on all result screens.
-   Session data deletion/clear-session action; no unnecessary
    server-side persistence.

#### README, docs and pitch

Ee owns: - `README.md`: setup, environment variables, run/test commands,
product flow, data sources, demo steps and limitations. - `docs/`: API
usage and integration notes. - `.kiro/steering/`: product, tech,
structure, team ownership and safety rules. - `slides/`: problem,
solution, demo, honest model results, data limitations, privacy and next
steps.

## 5. API integration contract

### Analyze request

``` json
{
  "data_source": "synthetic",
  "persona_id": "maya_demo",
  "profile": {
    "age": 52,
    "conditions": ["hypertension"],
    "snoring": true,
    "daytime_tiredness": true,
    "witnessed_breathing_pauses": false,
    "red_flag_symptoms": []
  }
}
```

This is an illustrative request; the actual endpoint must validate it
through the shared Pydantic schema.

### Analyze response shape

``` json
{
  "features": {},
  "apnea_score": {
    "tier": "High",
    "probability": null,
    "stop_bang_score": null,
    "top_factors": [],
    "model_version": "fixture-v1",
    "evidence_note": "Synthetic demonstration output; not a clinical prediction."
  },
  "risk_assessment": {
    "risks": [],
    "urgent_override": false,
    "urgent_reasons": [],
    "rules_version": "fixture-v1",
    "disclaimer": "Screening aid only; not a diagnosis."
  },
  "explanation": {
    "summary": "Illustrative demo explanation.",
    "risk_explanations": {},
    "limitations": ["Synthetic demo data."],
    "generated_by": "template"
  },
  "data_provenance": ["synthetic"]
}
```

Fixture values must be visibly labeled as illustrative and must not be
presented as model validation results. The production response should
use the exact shared Pydantic response model, not unvalidated
dictionaries.

## 6. Git and agent collaboration rules

1.  **One owner per module.** Work on a personal feature branch (for
    example `dhev/data-model`, `helly/risk-care`, `ee/app-report`).
2.  **Pull before work.** Each teammate synchronizes with `main` before
    beginning a task and before opening a pull request.
3.  **Use pull requests.** Do not push direct implementation changes to
    `main`; require at least one teammate review where feasible.
4.  **Protect shared schemas.** No agent changes shared Pydantic models
    or endpoint contracts unilaterally.
5.  **Contract-change procedure:**
    -   Open an issue or PR describing the need and
        backward-compatibility impact.
    -   Update this document and the Pydantic schemas together.
    -   Update fixtures, frontend TypeScript types and contract tests.
    -   Notify all teammates before merging.
    -   Merge the contract change before dependent implementation
        changes, or include the change and all dependent updates in one
        coordinated PR.
6.  **Keep PRs scoped.** A teammate should not reformat or rewrite
    another owner's module as part of an unrelated change.
7.  **Run checks.** Backend: lint and `pytest`; frontend: typecheck,
    lint and build. Add CI checks when practical.
8.  **Use stubs early.** All cross-team functions should have a
    fixture-backed implementation or test double so the end-to-end app
    can work before every real module is complete.
9.  **Freeze features before the final demo window.** After the agreed
    feature-freeze point, merge only bug fixes and demo-critical
    changes.
10. **No secrets in Git.** Commit `.env.example`, never `.env`; ignore
    datasets, tokens, private data and generated artifacts unless
    explicitly approved.

## 7. Required shared tests

At minimum, the repository should test:

-   Pydantic request/response schema validation and JSON serialization.
-   Synthetic persona can complete the full API flow.
-   Missing SpO₂ is represented as missing and does not crash analysis.
-   Empty or insufficient nights produce a clear data-quality warning.
-   Synthetic records are rejected by training/evaluation entry points.
-   Red-flag symptoms set `urgent_override=True` and surface call-911
    guidance.
-   Simulated capacity is labeled `"simulated"` in API responses and the
    UI.
-   Explanation text does not introduce numbers absent from structured
    results or assert a diagnosis.
-   Report generation works for Low, Moderate, High and Urgent fixtures.
-   PDF contains provenance, generation time, limitations and a data
    appendix.
-   Frontend typecheck/build succeeds against the agreed API types.

## 8. Definition of done

A module is ready to merge when: - It stays within the owner's assigned
paths. - It implements the agreed signatures and schemas. - It includes
tests and useful error handling. - It does not break the end-to-end
fixture demo. - It follows data provenance, privacy and non-diagnostic
safety requirements. - The pull request explains what changed and notes
any contract impact.

The integrated demo is ready when a judge can select a synthetic
persona, enter history, view screening tiers and explanations, inspect
care navigation, and download a clinician report without needing live
WHOOP credentials or restricted datasets.

## 9. Decisions to confirm before freezing this contract

-   Confirm `backend/app/data/hospitals.csv` as the single canonical
    hospital data location (proposed; the folder now exists).
-   Confirm the proposed ownership of `main.py`, `core/`, `infra/` and
    `scripts/` (Ee), and the role of `backend/app/ml/` (approved runtime
    artifact only).
-   Confirm that the `services/whoop/` folder (which also holds synthetic
    and CSV providers) keeps that name, or rename it (for example
    `providers/`) before anyone writes code there.
-   Confirm the final API route names and whether PDF generation returns
    a direct PDF response or a report ID.
-   Confirm the exact STOP-Bang fields and accepted values for `sex` and
    `conditions`.
-   Confirm the risk categories and evidence-rating vocabulary.
-   Confirm the minimum number of nights required for baseline
    calculations.
-   Confirm the facility ranking formula and fallback behavior when
    capacity or drive-time data is missing.
-   Confirm which optional WHOOP OAuth scopes are actually needed; live
    integration must remain optional.
-   Confirm Python version, package manager, frontend package manager,
    and CI commands.

**Do not mark this contract frozen until these decisions are reviewed by
all three owners.**
