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
- [ ] New/updated configuration is versioned in `config/` and activated in `config/active.yaml`.
- [ ] `.env.example` reflects any new environment variables.
- [ ] Migration exists and is reviewed if the schema changed (`alembic revision --autogenerate`, manual review, then test).
- [ ] Documentation updated (`docs/`) for any behavioural or operational change.
- [ ] Prediction/validation behaviour unchanged since last release (or explicitly signed off by ML owner).

### Deploy

- [ ] Pull code to target environment.
- [ ] `uv pip install -r requirements.txt` (or equivalent).
- [ ] Back up the database (`cp data/moneyball.db data/moneyball.db.bak.<date>`).
- [ ] `alembic upgrade head`.
- [ ] Start Streamlit headless on the configured port.
- [ ] Health check: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:<port>` → `200`.
- [ ] Confirm first data load succeeds (check logs; expect FPL API fetch on cold start).

### Post-release

- [ ] Monitor logs for errors (`LOG_LEVEL=INFO` at minimum; `DEBUG` while investigating).
- [ ] Verify a representative page renders (rankings, comparison, model analytics).
- [ ] Record the release (tag in git; note config hash if relevant).

## 3. Monitoring & Logging

- Logging is configured by `utils/logging_setup.py` at app start (`LOG_LEVEL`, `LOG_FILE`).
- Log format: `%(asctime)s %(levelname)s %(name)s %(message)s`.
- Key log events: data load completions (`services/data_loader.py`), API retries/rate-limits (`services/api_client.py`), migration runs (alembic).
- There is currently **no external monitoring** (no health endpoint beyond Streamlit's own, no structured log aggregation). For public hosting, add a synthetic health check and log shipping (Phase 2+).

## 4. Backup & Recovery

- **Backup**: copy the SQLite file. Because WAL mode is on, use a consistent copy:
  ```bash
  sqlite3 data/moneyball.db ".backup data/moneyball.backup.db"
  ```
- **Restore**: stop the app, replace the file, restart.
- **Rollback a migration**: `alembic downgrade -1` (destructive migrations must first be backed up).

## 5. Common Operations

```bash
# Restart the app
pkill -f "streamlit run About.py"; streamlit run About.py --server.headless true --server.port 8501 &

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
| SQLite file loss | Persistent volume + scheduled backups |
| FPL API unavailability / rate limits | Client retry/backoff; avoid frequent refreshes; monitor 429s in logs |
| Cold-start API fetch on restart | Acceptable; consider persisting freshness timestamp (Phase 2) |
| Google Fonts CDN outage | Cosmetic only; fonts degrade gracefully |
| Untracked `.env` drift between environments | Keep `.env.example` authoritative; CI validate |
