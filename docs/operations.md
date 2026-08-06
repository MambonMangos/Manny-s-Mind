# Operations Manual & Release Checklist — Manny's FPL House

## 1. Environment

| Item | Value |
|---|---|
| Runtime | Python 3.12, Streamlit 1.60 |
| Port | 8501 (configurable) |
| Database | SQLite file `data/moneyball.db` (WAL mode) |
| External API | `https://fantasy.premierleague.com/api` |
| Config | `config/` YAML + `.env` |
| Migrations | Alembic (`alembic/`) |

## 2. Release Checklist

### Pre-release

- [ ] `ruff check .` passes.
- [ ] `pytest` passes (full suite, including migration + smoke tests).
- [ ] `pip check` passes (no broken/mismatched dependency resolution).
- [ ] `pip-audit` reports no known vulnerabilities (or exceptions are documented).
- [ ] Secrets scan passes: no keys/tokens in tracked files (CI runs `git grep` for known patterns; `gitleaks` is a stronger local option).
- [ ] Dependency-diff reviewed and signed off (what changed, why, vulns addressed).
- [ ] New/updated configuration is versioned in `config/` and activated in `config/active.yaml`.
- [ ] `.env.example` reflects any new environment variables.
- [ ] Migration exists and is reviewed if the schema changed (`alembic revision --autogenerate`, manual review, then test).
- [ ] Documentation updated (`docs/`) for any behavioural or operational change.
- [ ] Prediction/validation behaviour unchanged since last release (or explicitly signed off by ML owner).

### Deploy

- [ ] Pull code to target environment.
- [ ] `uv pip install -r requirements.txt` (or equivalent).
- [ ] Back up the database: `python scripts/backup_db.py` (WAL-consistent online backup).
- [ ] `alembic upgrade head`.
- [ ] Start Streamlit headless on the configured port.
- [ ] Health check: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:<port>` → `200` (Streamlit also exposes `/_stcore/health`).
- [ ] Confirm first data load succeeds (check logs; expect FPL API fetch on cold start).

### Post-release

- [ ] Monitor logs for errors (`LOG_LEVEL=INFO` at minimum; `DEBUG` while investigating).
- [ ] Verify a representative page renders (rankings, comparison, model analytics).
- [ ] Record the release (tag in git; note config hash if relevant).

## 3. Monitoring & Logging

- Logging is configured by `utils/logging_setup.py` at app start (`LOG_LEVEL`, `LOG_FILE`).
- Log format: `%(asctime)s %(levelname)s %(name)s %(message)s`.
- Key log events: data load completions (`services/data_loader.py`), API retries/rate-limits (`services/api_client.py`), migration runs (alembic).
- **Audit log**: mutating actions (ingest, validation, data refresh, persist-to-ledger) are recorded append-only in the `audit_log` table via `services/audit.py` and are visible under *Recent Activity* on the Model Analytics page.
- **Health checks**: Streamlit exposes `/_stcore/health` (returns `ok`). For public hosting, configure an external uptime monitor (e.g. UptimeRobot / Healthchecks.io) against `https://<app>/_stcore/health` and review logs periodically. There is still **no log aggregation** — for self-hosted deployments, point `LOG_FILE` at a rotated, shipped log (Phase 3).

## 4. Backup & Recovery

- **Automated**: `python scripts/backup_db.py` creates a WAL-consistent backup under `data/backups/` (retention via `--keep N`, optional `--offsite-dir`).
  ```bash
  python scripts/backup_db.py --keep 14 --offsite-dir ~/backups/moneyball
  ```
- **Schedule** locally (cron):
  ```bash
  0 3 * * * cd /path/to/repo && .venv/bin/python scripts/backup_db.py
  ```
- **Manual**: `sqlite3 data/moneyball.db ".backup data/moneyball.backup.db"` (WAL-safe).
- **Restore**: stop the app, replace the file, restart.
- **Rollback a migration**: `alembic downgrade -1` (destructive migrations must first be backed up).

## 5. Common Operations

```bash
# Restart the app
pkill -f "streamlit run About.py"; streamlit run About.py --server.headless true --server.port 8501 &

# Back up the database (WAL-consistent)
python scripts/backup_db.py --keep 14

# Force a data refresh
# (click "Refresh Data" in the sidebar, or delete the DB and restart)

# Inspect config versions
python -c "from utils.config import list_versions; print(list_versions('weights'))"

# Compare two weight versions
python -c "from utils.config import compare_versions; print(compare_versions('weights','weights_v2','weights_v3'))"
```

## 6. Known Operational Risks

| Risk | Mitigation |
|---|---|
| SQLite file loss | Persistent volume + scheduled backups (`scripts/backup_db.py` via cron) + offsite copy |
| Unauthorized write access when shared | Set `ADMIN_TOKEN` (secrets/env) to gate ingest/validate/refresh/persist behind the sidebar admin unlock |
| FPL API unavailability / rate limits | Client retry/backoff; avoid frequent refreshes; monitor 429s in logs |
| Cold-start API fetch on restart | Acceptable; consider persisting freshness timestamp (Phase 2) |
| Google Fonts CDN outage | Cosmetic only; fonts degrade gracefully |
| Untracked `.env` drift between environments | Keep `.env.example` authoritative; CI validate |
