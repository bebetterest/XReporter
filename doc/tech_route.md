# XReporter Technical Route (v0.1)

## Principles

- First-principles design: keep only components needed for end-to-end value.
- Bitter lesson alignment: prefer scalable data pipeline primitives (normalized storage, explicit orchestration, replayable runs) over brittle hard-coded logic.
- Modularity first: isolate API, normalization, persistence, rendering, and i18n.

## Architecture

```text
CLI (Typer + Rich)
  -> Config + i18n
  -> CollectorService
       -> provider adapter (XApiClient / TwscrapeApiClient / SocialDataApiClient / FixtureXApiClient)
       -> Normalizer
       -> SQLiteStorage
  -> Report Renderer (static HTML)
```

## Data Model

- `users`: actor and referenced authors
- `tweets`: event and referenced tweets
- `tweet_links`: extracted links from tweet entities
- `activities`: normalized activity rows (`tweet|retweet|quote|reply`)
- `runs`: collection run metadata and status
- `run_activities`: run-to-activity mapping for reproducibility

## Collection Flow

1. Select API provider from config (`api_provider`), with fixture env override.
2. Resolve target user by username.
3. Fetch followings with pagination and cap.
4. Fetch each following's timeline in selected range.
5. Fetch unresolved referenced tweets by IDs.
6. Normalize events into activity records.
7. Upsert users/tweets/activities, attach to run.
8. Finish run with status and counters (`runs.api_provider` persisted for traceability).

## Rendering Flow

1. Select run (`--run-id` or latest).
2. Load run-linked activities.
3. Group retweet/quote/reply by `original_tweet_id`.
4. Render single static HTML with grouped section + chronological timeline.

## i18n Rules

- Supported languages: `en`, `zh`, `auto`.
- `auto` uses local locale.
- If locale is not Chinese or English, use English.

## Reliability

- API retry policy on `429` and `5xx` with exponential backoff + jitter.
- SocialData adapter reuses retry policy on `429/5xx`.
- Failure during collection marks run as `failed` with error message.
- Upsert strategy ensures deduplication across reruns.

## Iteration Roadmap

- v0.2: richer link/media extraction, better timeline filtering, incremental collection.
- v0.3: optional multi-user watchlist, richer report interactions.
- v0.4: analytics views and optional remote storage backend.
