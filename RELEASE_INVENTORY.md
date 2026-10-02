# Release inventory and provenance

This file documents the allowlisted contents of the standalone public-release candidate. No source tree, database, configuration, uploads, logs, Git history, or machine-specific deployment file was copied into this directory.

## Included files

- `.env.example`, `.gitignore`, `.github/workflows/ci.yml`, `LICENSE`, `README.md`, `RELEASE_INVENTORY.md`, `pyproject.toml` — portable project setup, automated checks, license, and scope documentation.
- `app/` — the standalone grounded-chat application plus the isolated learning workspace, public settings/database adapters, prompt, and shared generation/validation helpers. The learning feature was adapted to use its own public environment settings and database boundary.
- `templates/index.html`, `static/app.js`, `static/style.css` — the small browser interface, explicitly included as wheel assets.
- `templates/learning/index.html`, `static/features/learning.{css,js}`, `docs/LEARNING.md`, and `docs/learning-parent.png` — the separate learning workspace browser UI, setup/scope guide, and reviewed capture containing only fictional demo data.
- `data/sample_sources.json` — five fictional handbook sources authored for this release; no database file is included.
- `evaluation/cases.json`, `evaluation/run.py`, `evaluation/run_live.py`, `reports/offline-baseline.json` — 50 authored synthetic questions, retrieval-only and opt-in live evaluation runners, and the reproducible offline output.
- `tests/` — release-scope grounding, evaluation, live-runner, and learning authorization, AI-boundary, persistence, progress, UI, and body-limit tests. Tests use temporary databases and mocked model responses.

- `docs/DEMO.md`, `docs/live-development-results.json`, `docs/demo-desktop.png`, `docs/demo-mobile.png` — reviewed synthetic-only live development evidence and fresh browser captures.
- `app/generation.py`, `app/prompts.py`, `evaluation/run_live.py`, package initializer files, and additional regression tests — shared validation, bounded live evaluation, and installable resources.
- `PORTFOLIO.md` — public project relationships and evidence boundaries.

## Deliberately excluded

The source project's SQLite databases and WAL files, document uploads, generated audio, real model/provider configuration, populated account/course data, `.env` files, machine-specific service/deploy files, user logs and reports, scratch plans, private agent metadata, local caches, original screenshots, and all original Git history are excluded. No original private Git history is included; public history begins with the reviewed standalone release.

## Provenance and licenses

The grounded-chat portion is a focused standalone reimplementation of the selected document-grounded question-and-answer behavior. The learning workspace is an adapted feature port with a separate public settings and storage boundary. Neither includes the original personal database, real account records, provider configuration, or private deployment assets. Sample source material, demo credentials, and evaluation cases are fictional and written for this release. No outside datasets, external code, or third-party documents are bundled.
