# XReporter

XReporter is a CLI-first tool that collects activities from followings of a target X.com user within a selected time window, stores normalized data in SQLite, and renders a static HTML report for review and jump-to-post navigation.

## Current Version

- Version: `0.1.0` (MVI)
- Implemented pipeline: `config -> collect -> sqlite -> render`
- API mode: multi-provider (`official`, `twscrape`, `socialdata`) via config switch
- Offline demo/test mode: fixture API file via `XREPORTER_FIXTURE_FILE`

## Features (v0.1)

- CLI commands:
1. `xreporter config init --username <name> [--lang auto|en|zh] [--db-path <path>] [--report-dir <path>] [--following-cap <int>]`
   - provider options: `[--api-provider official|twscrape|socialdata] [--twscrape-accounts-db-path <path>]`
2. `xreporter config show`
3. `xreporter collect [--username <name>] [--last 12h|24h | --since <ISO8601> --until <ISO8601>] [--following-cap <int>] [--include-replies/--no-include-replies]`
4. `xreporter render [--run-id <id> | --latest] [--output <html_path>]`
5. `xreporter doctor`
- Time range support: `12h`, `24h`, or custom absolute range.
- Activity types: `tweet`, `retweet`, `quote`, `reply`.
- Grouping: retweet/quote/reply grouped by original tweet.
- i18n: English + Chinese, auto locale detection; fallback to English if locale is not Chinese/English.
- Progress visualization using Rich task bars.

## Environment Setup (Conda)

Use a conda environment named `XReporter`.

```bash
conda env create -f environment.yml
conda activate XReporter
```

If the environment already exists:

```bash
conda activate XReporter
pip install -e .[dev]
```

## Credentials

Provider credentials (env only):

```bash
# official
export X_BEARER_TOKEN="<your_token>"

# socialdata
export SOCIALDATA_API_KEY="<your_socialdata_api_key>"

# twscrape (single account v1)
export XREPORTER_TWS_USERNAME="<x_username>"
export XREPORTER_TWS_PASSWORD="<x_password>"
export XREPORTER_TWS_EMAIL="<email_for_verification>"
export XREPORTER_TWS_EMAIL_PASSWORD="<email_password>"
```

XReporter never writes credentials into config files.

## Quick Start

1. Initialize config:

```bash
xreporter config init --username target_user --lang auto
# default api_provider is twscrape for new configs
```

2. Run collection:

```bash
xreporter collect --last 24h
# or
xreporter collect --since 2026-03-09T00:00:00+08:00 --until 2026-03-10T00:00:00+08:00
```

3. Render report:

```bash
xreporter render --latest
```

4. Health check:

```bash
xreporter doctor
```

## Configuration

Default config file path:

- `~/.xreporter/config.toml`

Config schema:

- `username` (string)
- `language` (`auto|en|zh`)
- `db_path` (string)
- `report_dir` (string)
- `following_cap_default` (int, default `200`)
- `include_replies_default` (bool, default `true`)
- `api_provider` (`official|twscrape|socialdata`; legacy config without this field defaults to `official`)
- `twscrape_accounts_db_path` (string, default `~/.xreporter/twscrape_accounts.db`)

## Project Structure

```text
src/xreporter/
  cli.py
  config.py
  i18n.py
  models.py
  normalizer.py
  render.py
  service.py
  storage.py
  time_range.py
  x_api.py
tests/
doc/
```

## Testing

```bash
pytest
```

Covered in tests:

- unit: time range parsing, i18n fallback, activity classification, SQLite idempotency
- integration: API pagination, retry on 429, unresolved referenced tweet fetch
- end-to-end: fixture `collect -> render`, rerun idempotency, bilingual CLI switch

## Notes

- X API access level controls practical coverage and rate limits.
- Provider can be switched in config without changing downstream normalization/storage/rendering.
- For large following lists, tune `--following-cap` based on API quota.
- This repository keeps English and Chinese docs in sync (`*_cn.md`).
