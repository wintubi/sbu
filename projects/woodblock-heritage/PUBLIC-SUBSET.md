# Public subset boundary

This repository directory is a **sanitized engineering slice**, not the full heritage dataset or the historical research project.

## Included

- `app/`: FastAPI + SQLite review/publication service.
- `web/`: same-origin review page (no inline script/style).
- `tests/`: 47 offline tests, synthetic images only.
- `openspec/changes/heritage-evidence-review/`: proposal, design, specs, tasks and decision memo.
- `docs/ACCEPTANCE.md`, `docs/IMPLEMENTATION.md`, `docs/GOLD-SCHEMA.md`.
- `docs/evidence/`: synthetic Chrome/CDP screenshots/logs.
- `scripts/`: demo, gold validator, Chrome/CDP flows.

## Excluded

- Original scanned page images, OCR text, raw candidates and the local `kg` project.
- Historical page import script/results, review worksheet and token/usage logs.
- Local SQLite files, `.env`, API keys, browser profiles and absolute user paths.
- The full 11-volume corpus, real OCR/VLM/Neo4j calls and any domain accuracy claim.

## What it demonstrates

- Three status axes (`validation_status`, `support_status`, `review_status`) with a publication gate.
- Optimistic concurrency, atomic review events/versions, idempotent imports/reviews/publications.
- Immutable publication snapshots and current/historical views.
- Source `access_policy` allow-list, PNG/JPEG header pixel preflight, gold JSONL structural validation.
- Chrome/CDP page flow including conflict reload, revise, reject, publish and history read-only.

## Limits

- No real OCR/VLM extraction, Neo4j publication, authentication, public deployment, or domain gold set.
- The 47 tests are software/contract tests; they do not establish heritage extraction accuracy.
- Chrome/CDP is not a Playwright full E2E suite.

## Run

```powershell
cd projects/woodblock-heritage
python -m pip install -r requirements-dev.txt
python -m pytest
python run.py
```

The default database is under `data/` and is ignored by Git.
