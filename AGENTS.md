# AGENTS.md

This file defines the working principles for humans and agents in this repository.

## Core Principles

- First principles over accidental complexity.
- Prefer simple, composable modules with explicit interfaces.
- Keep the end-to-end path runnable at all times.
- Optimize for correctness, observability, and repeatability.

## Engineering Rules

- Keep modules focused:
  - `x_api.py`: API access and retry behavior
  - `normalizer.py`: activity normalization
  - `storage.py`: persistence and idempotency
  - `render.py`: report generation
  - `cli.py`: command interface and orchestration
- Use typed Python and explicit data contracts where practical.
- Avoid hidden global state; pass dependencies through constructors/functions.
- Treat reruns as first-class: no duplicate core records.
- Run build, development, and test commands inside the conda environment named `XReporter` (`conda activate XReporter`).

## Testing Policy

- Unit tests for pure logic and edge cases.
- Integration tests for adapter behavior (API, pagination, retry, fallback fetch).
- End-to-end tests for `collect -> render` critical path.
- New behavior must include at least one relevant test.

## Documentation Policy

- Keep docs current with code changes.
- English source docs must have synchronized Chinese counterparts (`*_cn.md`).
- Update at least the following when behavior changes:
  - `README.md` / `README_cn.md`
  - `doc/tech_route.md` / `doc/tech_route_cn.md`
  - `doc/progress.md` / `doc/progress_cn.md`
  - `AGENTS.md` / `AGENTS_cn.md`

## i18n Policy

- CLI supports `en`, `zh`, and `auto`.
- `auto` uses local locale.
- If locale is not Chinese/English, fallback to English.

## Security & Secrets

- Never persist `X_BEARER_TOKEN` in project files.
- Use environment variables for secrets.
- Keep fixture files free of real credentials.

## Iteration Policy

- Deliver minimal viable increments.
- Record milestone status in `doc/progress*.md`.
- Prefer backward-compatible schema extensions where possible.
