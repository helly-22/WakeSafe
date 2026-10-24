# Safety

These apply to all code, UI copy, reports and slides. Source: `TEAM_CONTRACTS.md` §1, §3.5-3.8.

## Non-diagnostic language
- Never state or imply that a user has sleep apnea or another disease.
- Use "screening result", "risk signal", "consider discussing with a clinician".
- Do not present model output as validated WHOOP-specific accuracy.
- Show a screening-only disclaimer on every result screen.

## Emergencies
- Red-flag symptoms (chest pain, fainting, severe shortness of breath, stroke symptoms)
  set `urgent_override=True` deterministically.
- When it is set, show call-911 guidance **before** any routine recommendation, and do
  not make a facility list the primary action.
- `Urgent` tier is reserved for that override or a team-approved emergency rule, never
  just a high model probability.
- The app does not dispatch emergency services or guarantee facility availability.

## Data honesty
- Label every value's source: patient-reported, wearable-measured, app-calculated,
  model-estimated or simulated.
- Synthetic data is for UI, tests, fixtures and demos only. Never use it to train or
  evaluate the model, and never present it as real patient data.
- Simulated capacity must carry `capacity_source="simulated"` and a visible UI label.
  Never present it as live hospital capacity.
- Explanations only rephrase structured results. They must not add numbers, diagnoses,
  tiers or destinations, and need a deterministic template fallback.
- Reports and PDFs use structured data only; no independent scoring or invented values.

## Privacy and secrets
- Do not commit credentials, WHOOP tokens, real identifiers, raw private health data,
  datasets or model artifacts excluded by `.gitignore`.
- Never log OAuth tokens or raw sensitive payloads.
- Names and dates of birth are optional and omitted from demo reports.
- No unnecessary server-side persistence; provide a clear-session action.

Required safety tests are listed in `TEAM_CONTRACTS.md` §7.
