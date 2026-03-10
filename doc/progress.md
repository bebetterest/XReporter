# XReporter Progress Log

## 2026-03-10

### Completed (v0.1 baseline)

- Bootstrapped Python project (`src/`, `tests/`, `pyproject.toml`, `environment.yml`).
- Implemented CLI commands:
  - `config init`
  - `config show`
  - `collect`
  - `render`
  - `doctor`
- Implemented official X API client with:
  - username lookup
  - followings pagination
  - timeline fetch
  - unresolved referenced tweet backfill
  - retry with exponential backoff for `429/5xx`
- Implemented fixture API client for offline testing.
- Implemented normalization layer for `tweet|retweet|quote|reply`.
- Implemented SQLite schema and upsert strategy.
- Implemented single-page static HTML report renderer.
- Implemented i18n for CLI (`en`, `zh`, `auto` fallback to English).
- Added unit, integration, and end-to-end tests.
- Added bilingual docs:
  - `README.md` / `README_cn.md`
  - `doc/tech_route.md` / `doc/tech_route_cn.md`
  - `doc/progress.md` / `doc/progress_cn.md`
  - `AGENTS.md` / `AGENTS_cn.md`
- Created and validated conda environment `XReporter`.
- Fixed config default-path resolution to evaluate at runtime (improves testability and environment portability).
- Executed full test suite in `XReporter` environment: **16 passed**.
- Completed real API smoke chain in `XReporter`:
  - `config init` with real token (from `.env`, not persisted)
  - `collect --last 12h --following-cap 5` succeeded (`run_id=2`, `activities=3`)
  - `render --run-id 2` succeeded (`.xreporter-local/reports/run_2.html`)
- Fixed X API RFC3339 timestamp format issue by serializing request time with second precision.
- Executed high-cap real test with requested params:
  - `username=betterestli`, `collect --last 12h --following-cap 500`
  - run `3` reached timeline progress `243/411` and then failed with X API `402 CreditsDepleted`
  - partial data persisted (`173` activities) and report rendering still works (`run_3.html`)
- Implemented multi-provider collection via config switch:
  - added `api_provider` (`official|twscrape|socialdata`)
  - added `twscrape_accounts_db_path`
  - legacy config fallback defaults to `official`
- Added `SocialDataApiClient` and `TwscrapeApiClient` adapters while keeping normalization/storage/render path unchanged.
- Added provider-aware client factory and doctor checks:
  - fixture env still has highest priority
  - credential checks now follow selected provider
- Extended `runs` schema with `api_provider` and added auto-migration for existing databases.
- Added new tests for config compatibility, provider selection, storage migration, and new provider adapters.
- Executed full test suite in `XReporter` environment after multi-provider changes: **29 passed**.

### Pending / Next

- Validate against real X API credentials and tune rate-limit behavior with live traffic.
- Extend report content depth (media preview, richer link metadata).
- Add incremental collection strategy to reduce repeated API reads.
- Add stronger observability (structured logs and optional run trace export).
