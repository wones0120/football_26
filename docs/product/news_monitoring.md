# News Monitoring

The backend includes a daily allowlisted NFL news and injury monitor aimed at manual DFS research.

The system now works in two layers:

- raw item ingestion and storage
- classification/filtering before report output

## Guardrails

- Uses only configured sources from `backend/news_sources.json`.
- Does not crawl arbitrary article links.
- Stores feed metadata, short summaries, structured injury facts, and source links.
- Preserves raw ingested items even when they are later filtered out of the DFS-facing report.
- Does not store full article text by default.
- Supports `rss`, `injury_table`, and `manual` sources in v1.

## API

- `POST /api/news-monitor/run`
- `GET /api/news-monitor/report/{YYYY-MM-DD}`
- `POST /api/news-monitor/manual-note`
- `POST /api/news-monitor/import-history`

`POST /api/news-monitor/run` accepts:

```json
{
  "run_date": "2026-06-20",
  "force": false,
  "source_ids": ["manual_notes"]
}
```

`POST /api/news-monitor/manual-note` accepts:

```json
{
  "run_date": "2026-06-20",
  "title": "Beat writer note",
  "note_text": "Coach said the backup WR is getting first-team reps.",
  "source_link": "https://example.com/report"
}
```

`POST /api/news-monitor/import-history` accepts:

```json
{
  "path": "/absolute/path/to/history.json",
  "run_date": "2025-10-11",
  "source_id": "historical_import",
  "source_name": "Historical Import"
}
```

Supported import formats:

- `.json` with a top-level list of objects
- `.csv`
- `.tsv`

Required field per row:

- `title`

Useful optional fields:

- `summary`
- `link`
- `published_at`
- `player_name`
- `team`
- `position`
- `season`
- `week`
- `item_type`
- `external_id`

## Daily Scheduler

For local Mac development, the simplest daily scheduler is the repo script:

```bash
scripts/product/news_monitor_scheduler.sh install
```

This creates and loads a `launchd` agent that calls:

- `POST /api/news-monitor/run`

Before posting the news-monitor run, the scheduler checks whether the local FastAPI server is reachable. If it is not, the scheduler exits cleanly and logs a message that it could not get the daily news.

Defaults:

- daily at `08:00` local time
- `API_BASE_URL=http://127.0.0.1:8000/api`
- `API_HEALTHCHECK_TIMEOUT_SECONDS=5`
- `PGDATABASE=football_26_dev`
- `force=false`
- all enabled allowlisted sources

Useful commands:

```bash
scripts/product/news_monitor_scheduler.sh run
scripts/product/news_monitor_scheduler.sh trigger
scripts/product/news_monitor_scheduler.sh status
scripts/product/news_monitor_scheduler.sh uninstall
```

Useful overrides:

```bash
SCHEDULE_HOUR=7 SCHEDULE_MINUTE=30 scripts/product/news_monitor_scheduler.sh install
PGDATABASE=football_26_dev scripts/product/news_monitor_scheduler.sh install
SOURCE_IDS=espn_nfl_news,cbs_nfl_news scripts/product/news_monitor_scheduler.sh install
API_HEALTHCHECK_TIMEOUT_SECONDS=10 scripts/product/news_monitor_scheduler.sh install
FORCE=true scripts/product/news_monitor_scheduler.sh run
RUN_DATE=2025-11-16 scripts/product/news_monitor_scheduler.sh run
```

Logs:

- `~/Library/Logs/football_26/news_monitor_scheduler.out.log`
- `~/Library/Logs/football_26/news_monitor_scheduler.err.log`

If the backend is down when the scheduler fires, the job logs `Could not get the daily news because the backend is unavailable ...` and exits without trying to manage the server process itself.

## Source Configuration

Each source entry includes:

- `source_id`
- `name`
- `source_type`
- `url`
- `enabled`
- `content_mode`
- `notes`
- optional `options`

The default config now includes two verified national RSS examples:

- `espn_nfl_news`
- `cbs_nfl_news`

Both returned RSS successfully on June 21, 2026 and remain disabled by default.

The config also includes disabled placeholder entries for a first batch of official team sources:

- Chiefs
- Bills
- Ravens
- Eagles
- Dolphins
- 49ers

Fill in each team source URL only after you verify that the endpoint is official, stable, and usable without crawling article bodies.

For `injury_table` sources, `options.table_index` and `options.column_map` control how the HTML table is normalized.

## Storage

The service creates these tables on demand:

- `news_monitor_source`
- `news_monitor_run`
- `news_monitor_item`
- `news_monitor_signal`
- `news_monitor_manual_note`

## Filtering Model

Items are ingested first, then classified before report generation. The report currently hides items that are marked as:

- non-NFL
- off-field
- evergreen/general-interest
- not DFS-relevant

This keeps historical raw metadata available for later rule tuning while reducing noise in the daily report.
