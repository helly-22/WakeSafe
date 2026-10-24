# Product

WakeSafe is a sleep-health **screening and care-navigation** aid. It combines WHOOP-format
sleep/recovery summaries with user-reported history to surface screening risks, suggest
appropriate care, and produce a clinician-ready report. It is not a diagnostic tool.

Detailed requirements: `TEAM_CONTRACTS.md` §1 (scope), §4.3 (UI deliverables), §8 (definition of done).

## Demo behavior
- The default demo runs entirely on **synthetic WHOOP-format data** and must work offline.
- Live WHOOP OAuth is optional and must fail gracefully without credentials.
- CSV upload is a supported data source.
- A judge should be able to: pick a persona, enter history, see screening tiers and
  explanations, inspect care navigation, and download a clinician report.

## Core flow
Intake and persona -> analyze (features, apnea score, risks, explanation) -> care
recommendations -> clinician report preview/PDF.

## Wording
- Use "screening result", "risk signal", "consider discussing with a clinician".
- Never tell a user they have sleep apnea or any disease. See `safety.md`.

## Out of bounds (per the contract)
- No diagnosis, live hospital capacity claims or emergency dispatch.
- No unnecessary server-side persistence; sessions are clearable (`TEAM_CONTRACTS.md` §4.3).
- Anything not listed in `TEAM_CONTRACTS.md` §4.3 is not a committed deliverable.
