# WakeSafe

> Hackachusetts submission

WakeSafe uses wearable-style sleep and recovery summaries (in
[WHOOP](https://www.whoop.com/) format) plus user-reported history to surface
**screening risks**, including sleep apnea risk, and to suggest appropriate care
navigation. It is a screening aid only, not a diagnostic tool.

The default demo runs on **synthetic** WHOOP-format data. Live WHOOP OAuth is optional.
See [`TEAM_CONTRACTS.md`](TEAM_CONTRACTS.md) for ownership, interfaces and safety rules.

## What it does

- **Loads sleep data** — synthetic demo personas by default, CSV upload, or optional
  live WHOOP data via OAuth (sleep, recovery, heart rate, SpO2).
- **Screens for apnea risk** — combines STOP-Bang-style intake with a model trained on
  open sleep-study datasets to give a Low / Moderate / High screening tier.
- **Assesses risks and matches care** — rule-based risk tiers with an emergency
  override for red-flag symptoms, plus ranked care options (capacity is labeled
  static, simulated, live or unknown).
- **Explains and reports** — plain-language explanations of structured results and a
  downloadable clinician PDF report.

## Repository layout

```
WakeSafe/
├── backend/            # FastAPI service: data providers, screening, risks, care, reports
│   ├── app/
│   │   ├── api/        # Thin FastAPI route handlers
│   │   ├── core/       # Config, settings, security, logging
│   │   ├── models/     # Shared Pydantic request/response schemas
│   │   ├── ml/         # Small approved runtime model artifact + metadata
│   │   ├── data/       # Runtime reference data (hospitals.csv)
│   │   ├── services/
│   │   │   ├── whoop/         # Synthetic / CSV / optional WHOOP data providers
│   │   │   ├── screening/     # Runtime features + apnea model inference
│   │   │   ├── risks/         # Rule-based risk assessment
│   │   │   ├── care/          # Facility matching and ranking
│   │   │   ├── explanations/  # Guarded plain-language explanations
│   │   │   └── reports/       # Clinician report data + PDF rendering
│   │   ├── db/         # Unused unless persistence is deliberately added
│   │   └── utils/      # Shared helpers
│   └── tests/
├── frontend/           # React + TypeScript app: intake, dashboard, care map, report
│   └── src/
│       ├── components/ # Reusable UI (charts, cards, banners)
│       ├── pages/      # Route-level views
│       ├── features/   # Feature slices (intake, risks, care, report)
│       ├── hooks/      # Custom React hooks
│       ├── services/   # Typed API client
│       ├── lib/        # Utilities, types, constants
│       └── assets/     # Images, icons, styles
├── ml/                 # Standalone ML: notebooks, training, datasets, saved models
│   ├── notebooks/
│   ├── data/           # (gitignored) raw + processed datasets
│   ├── models/         # (gitignored) trained model artifacts
│   └── training/       # Training + evaluation scripts
├── infra/              # Deployment: docker, compose, env templates, CI helpers
├── docs/               # Architecture notes, API docs, design decisions
├── scripts/            # Dev/ops scripts (setup, seed, run)
├── slides/             # Pitch materials
└── TEAM_CONTRACTS.md   # Ownership, interfaces and safety rules
```

## Getting started

Setup instructions will be added to `docs/SETUP.md` once dependencies are in place.
