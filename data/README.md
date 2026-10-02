# data/

`data/raw/<run_id>/` holds reproducible Telegram snapshots: one `<channel-slug>.parquet` per channel (one row per message, full text) plus `manifest.json` (run id, fetch time, window, git SHA, per-channel counts).
Produce one with `telegram-scraper snapshot --channel <slug> --start YYYY-MM-DD --end YYYY-MM-DD`; analyses load it with `telegram_scraper.snapshot.load_snapshot` instead of fetching live.
Snapshots are meant to be committed; parquet files can be large (tens of MB for busy channels), so check `du -sh data/raw/*` before committing.
