# XReporter

> Important:
>
> - Using the official X API can be expensive in real-world usage (pricing and quota can become a bottleneck quickly).
> - The SocialData provider integration exists in code/tests, but it has **not** completed full real-world validation in this repository yet.

XReporter is a CLI-first pipeline that:

- collects activity from followings of a target X user in a selected time window,
- normalizes and stores data in SQLite with rerun-safe upsert behavior,
- renders a static HTML report for review and jump-to-post navigation.

Current version: `0.1.0` (MVI), with runnable path `config -> collect -> sqlite -> render`.

## What It Can Do

- Multi-provider collection: `official` / `socialdata` (switch by config).
- Time range modes: `--last 12h|24h` or absolute `--since/--until` (ISO8601).
- Activity normalization: `tweet`, `retweet`, `quote`, `reply`.
- Grouped report sections by original tweet + chronological timeline.
- Non-fatal warning records (`run_warnings`) for provider-level partial failures.
- i18n CLI output (`en`, `zh`, `auto`) with locale fallback to English.
- Offline fixture mode with `XREPORTER_FIXTURE_FILE`.

## Quick Start (3 Minutes)

### 1) Setup environment

Use conda env `XReporter`:

```bash
conda env create -f environment.yml
conda activate XReporter
pip install -e .[dev]
```

### 2) Configure credentials (env only)

```bash
# official
export X_BEARER_TOKEN="<your_token>"

# socialdata
export SOCIALDATA_API_KEY="<your_socialdata_api_key>"
```

XReporter never writes credentials into project config files.

### 3) Initialize config

```bash
xreporter config init --username target_user --lang auto
# default provider for new config: official
```

### 4) Collect + render

```bash
xreporter collect --last 24h
xreporter render --latest
```

### 5) Run health check

```bash
xreporter doctor
```

## CLI Commands

1. `xreporter config init --username <name> [--lang auto|en|zh] [--db-path <path>] [--report-dir <path>] [--following-cap <int>] [--include-replies/--no-include-replies] [--api-provider official|socialdata]`
2. `xreporter config show`
3. `xreporter collect [--username <name>] [--last 12h|24h | --since <ISO8601> --until <ISO8601>] [--following-cap <int>] [--include-replies/--no-include-replies]`
4. `xreporter render [--run-id <id> | --latest] [--output <html_path>]`
5. `xreporter doctor`

## Typical Workflow

```bash
# 1) init once
xreporter config init --username jack --lang auto --following-cap 200

# 2) collect one window
xreporter collect --last 24h

# 3) render latest run
xreporter render --latest

# 4) or render a specific run
xreporter render --run-id 3 --output ./reports/manual_run_3.html
```

## Config Reference

Default config path:

- `~/.xreporter/config.toml`

Config fields:

- `username` (string)
- `language` (`auto|en|zh`)
- `db_path` (string)
- `report_dir` (string)
- `following_cap_default` (int, default `200`)
- `include_replies_default` (bool, default `true`)
- `api_provider` (`official|socialdata`; missing legacy field defaults to `official`)

## Provider Notes

- `official`:
  - Better aligned with canonical X API schema.
  - Requires `X_BEARER_TOKEN`.
  - Cost/rate-limit pressure can be high depending on access tier and usage.
- `socialdata`:
  - Requires `SOCIALDATA_API_KEY`.
  - Adapter handles endpoint fallbacks and schema normalization.
  - Timeline `403` privacy responses are recorded as warnings and skipped.
  - Full production validation status in this repo: pending.
- `fixture`:
  - Set `XREPORTER_FIXTURE_FILE` to run offline demo/tests without real API calls.

## Output and Data Model

- SQLite core tables:
  - `users`, `tweets`, `tweet_links`, `activities`
  - `runs`, `run_activities`, `run_warnings`
- HTML report:
  - warning section (provider/user/API path/raw error)
  - grouped retweet/quote/reply by original post
  - chronological timeline for browsing

## Architecture

```text
CLI (Typer + Rich)
  -> Config + i18n
  -> CollectorService
       -> provider adapter (XApiClient / SocialDataApiClient / FixtureXApiClient)
       -> normalizer
       -> SQLiteStorage
  -> HTML renderer
```

Code layout:

```text
src/xreporter/
  cli.py        # command interface and orchestration
  config.py     # config load/save/default paths
  i18n.py       # language resolution and message catalog
  models.py     # typed data contracts
  normalizer.py # payload -> normalized batch
  service.py    # collect workflow and warning handling
  storage.py    # SQLite schema, upsert, run metadata
  render.py     # static HTML generation
  time_range.py # last/since/until parsing
  x_api.py      # official/socialdata/fixture clients
tests/
doc/
```

## Development and Testing

Run tests:

```bash
conda activate XReporter
pytest
```

Current coverage focus:

- unit: time range parsing, i18n fallback, activity classification, SQLite idempotency
- integration: pagination, retry on `429/5xx`, unresolved referenced tweet fetch
- e2e: fixture `collect -> render`, rerun idempotency, bilingual CLI behavior

## Docs

- English/Chinese docs are maintained in sync (`*_cn.md`).
- Technical route: `doc/tech_route.md` / `doc/tech_route_cn.md`
- Progress log: `doc/progress.md` / `doc/progress_cn.md`
