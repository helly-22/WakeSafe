# WakeSafe

> Hackachusetts submission

WakeSafe pulls sleep and biometric data from a user's [WHOOP](https://www.whoop.com/)
wearable, analyzes it for signs of **sleep apnea**, and surfaces findings through a
conversational chat interface (e.g. `/chat/sleep-apnea-flagging-with-whoop`).

## What it does

- **Ingests WHOOP data** — connects via the WHOOP OAuth API to pull sleep, recovery,
  heart rate, and SpO2 metrics.
- **Flags sleep apnea risk** — runs the biometric time-series through detection logic /
  an ML model to surface apnea indicators (e.g. SpO2 dips, respiratory disturbances,
  fragmented sleep).
- **Explains results via chat** — a chat UI lets users ask about their flags and sleep
  trends in plain language.

## Repository layout

```
WakeSafe/
├── backend/            # FastAPI service: WHOOP integration, apnea detection, chat API
│   ├── app/
│   │   ├── api/        # HTTP routes (chat, whoop auth, analysis, health)
│   │   ├── core/       # Config, settings, security, logging
│   │   ├── models/     # Pydantic + DB models (schemas, ORM)
│   │   ├── services/   # Business logic (WHOOP client, apnea analysis, chat)
│   │   ├── ml/         # Sleep-apnea detection models + feature engineering
│   │   ├── db/         # Database session, migrations, repositories
│   │   └── utils/      # Shared helpers
│   └── tests/
├── frontend/           # React + TypeScript app: chat interface + dashboard
│   └── src/
│       ├── components/ # Reusable UI (chat bubbles, charts, cards)
│       ├── pages/      # Route-level views (chat, dashboard, auth callback)
│       ├── features/   # Feature slices (chat, whoop, analysis)
│       ├── hooks/      # Custom React hooks
│       ├── services/   # API clients
│       ├── lib/        # Utilities, types, constants
│       └── assets/     # Images, icons, styles
├── ml/                 # Standalone ML: notebooks, training, datasets, saved models
│   ├── notebooks/
│   ├── data/           # (gitignored) raw + processed datasets
│   ├── models/         # (gitignored) trained model artifacts
│   └── training/       # Training + evaluation scripts
├── infra/              # Deployment: docker, compose, env templates, CI helpers
├── docs/               # Architecture notes, API docs, design decisions
└── scripts/            # Dev/ops scripts (setup, seed, run)
```

## Getting started

See [`docs/SETUP.md`](docs/SETUP.md) once dependencies are added.
