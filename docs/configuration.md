# Configuration Reference — Manny's FPL House

Configuration follows a strict hierarchy:

```
Environment Variables (.env)
        ↓
config/*.yaml  (versioned, active.yaml selects the active version)
        ↓
Safe Defaults (utils/constants.py)
```

Lower layers provide defaults; higher layers override them. No deployment-specific assumptions should be baked into source code.

## 1. Environment Variables (`.env`)

Loaded once at startup by `utils/env.py`. Copy `.env.example` to `.env`.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/moneyball.db` | SQLAlchemy database URL |
| `FPL_TEAM_ID` | `472930` | FPL team ID for team pages |
| `FPL_API_BASE_URL` | `https://fantasy.premierleague.com/api` | FPL API base URL |
| `FPL_USER_AGENT` | `MoneyballFPL/1.0` | User-Agent sent to the FPL API |
| `FPL_API_TIMEOUT` | `30` | HTTP timeout (seconds) |
| `FPL_API_MAX_RETRIES` | `3` | Retries before failing |
| `FPL_API_BACKOFF_BASE` | `1.0` | Exponential backoff base (seconds) |
| `FPL_API_ALLOW_INSECURE_SSL` | `false` | **Never** `true` in production; allows TLS verification to be skipped on retry |
| `DATA_STALENESS_SECONDS` | `3600` | FPL data refresh threshold (1 hour) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `LOG_FILE` | unset | Optional log file path (console otherwise) |

Reading `DATABASE_URL`, `FPL_*`, and `LOG_*` lives in `database/database.py`, `utils/constants.py`, and `utils/logging_setup.py` respectively.

## 2. YAML Configuration (`config/`)

Versioned files, one per category. The **active** version is set in `config/active.yaml`:

```yaml
active_versions:
  weights: weights_v3
  fixtures: fixtures_v1
  minutes: minutes_v1
  prediction: prediction_v1
  bookmaker: bookmaker_v1
  features: features_v1
```

| Category | Purpose | Key files |
|---|---|---|
| `weights` | Value-score, projection, rating, transfer, opportunity weights | `weights_v1..v3.yaml` |
| `prediction` | Projection windows, FPL point values, CI z-scores, variance sources, thresholds | `prediction_v1.yaml` |
| `features` | Feature engineering windows, trends, market, regression, fixture thresholds | `features_v1.yaml` |
| `fixtures` | Fixture difficulty configuration | `fixtures_v1.yaml` |
| `minutes` | Minutes projection parameters | `minutes_v1.yaml` |
| `bookmaker` | Bookmaker-engine parameters | `bookmaker_v1.yaml` |

### Changing a Weight (example)

1. Copy `config/weights/weights_v3.yaml` → `config/weights/weights_v4.yaml`.
2. Edit the new file.
3. Switch `config/active.yaml` → `weights: weights_v4`.
4. Restart the app.

The old version is preserved for historical comparison. The loader enforces that `value_score` weights sum to 1.0.

## 3. Safe Defaults (`utils/constants.py`)

- `_DEFAULT_WEIGHTS` — fallback scoring weights if the YAML fails to load.
- Constants like `POSITION_MAP`, `MAX_SEASON_MINUTES`, `FPL_BUDGET`.

## 4. Streamlit Configuration (`.streamlit/config.toml`)

- `[theme]` — dark theme colours.
- `[server] headless = true` — run without a browser.
- `[browser] gatherUsageStats = false` — telemetry off.

Runtime overrides: `--server.port`, `--server.address`, or the `STREAMLIT_SERVER_PORT` / `STREAMLIT_SERVER_ADDRESS` environment variables.

## 5. Notes & Gotchas

- **Config cache**: `utils/config.py` caches parsed YAML in-process. Changes on disk require a restart (or `utils.config.invalidate_cache()`).
- **`.env` precedence**: real environment variables take precedence over `.env` values (standard `python-dotenv` behaviour).
- **No secrets**: the repository contains no API keys. Any future secrets must use `.streamlit/secrets.toml` (gitignored) or environment variables — never source code.
