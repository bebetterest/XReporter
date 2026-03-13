# XReporter Progress Log

## 2026-03-13

### Completed (report UX + Chinese HTML)

- Optimized static HTML report layout:
  - added run summary dashboard (metadata + counters)
  - improved grouped/timeline/warning card readability and responsive behavior
  - added section counters and clearer navigation chips
- Completed report-level bilingual rendering for `en`/`zh`:
  - localized previously hardcoded action/timeline labels (`by/at/open/open post/unknown`)
  - localized activity type display (`tweet|retweet|quote|reply`) in grouped and timeline blocks
- Extended warning rendering details with warning type and recorded timestamp.
- Extended grouped section to also include `tweet` activities (not only retweet/quote/reply), so original posts now appear in grouped cards.
- Made grouped section and chronological timeline collapsible/expandable, with both sections collapsed by default.
- Updated sort rules:
  - chronological timeline now always sorts newest -> oldest
  - grouped section sorts by action count (desc), and if tied, by latest action time (desc)
- Added a new user-grouped section between grouped-by-original and timeline:
  - grouped by actor user
  - sorted by action count (desc), and if tied, by latest action time (desc)
  - collapsible with default collapsed state
- Added item-level collapse for grouped cards (grouped-by-original and grouped-by-user), default collapsed to improve readability for long content.
- Refactored repository README for open-source onboarding:
  - clearer information hierarchy (overview -> technical route -> quick start -> reference)
  - friendlier navigation and troubleshooting sections for first-time users
  - synchronized English/Chinese README content structure
- Added render tests for Chinese HTML content and extended e2e bilingual coverage to validate zh report output.
- Executed full test suite in `XReporter` environment after report UX/i18n update: **35 passed**.

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
- Improved twscrape credential behavior:
  - if accounts DB already has accounts, doctor/collect no longer force email credentials
  - bootstrap credentials are still required when account pool is empty
- Added tests for twscrape existing-pool credential fallback and doctor credential status.
- Executed full test suite in `XReporter` after twscrape credential fallback update: **31 passed**.
- Extended `runs` schema with `api_provider` and added auto-migration for existing databases.
- Added new tests for config compatibility, provider selection, storage migration, and new provider adapters.
- Added SocialData private-content graceful handling:
  - when timeline fetch returns `403` privacy restriction, record run warning and continue instead of failing the full run
  - new `run_warnings` table and render integration (red warning section with username/link/API path/raw body)
  - added tests for service warning flow, storage warning persistence, and warning rendering
- Executed full test suite in `XReporter` after privacy-warning update: **34 passed**.
- Removed `twscrape` support from runtime and config:
  - providers are now limited to `official|socialdata`
  - removed `TwscrapeApiClient` and twscrape credential/account-pool flow
  - removed `twscrape` dependency from `pyproject.toml`
- Updated tests and bilingual docs to match provider cleanup.
- Executed full test suite in `XReporter` after provider cleanup: **30 passed**.

### Pending / Next

- Validate against real X API credentials and tune rate-limit behavior with live traffic.
- Extend report content depth (media preview, richer link metadata).
- Add incremental collection strategy to reduce repeated API reads.
- Add stronger observability (structured logs and optional run trace export).
