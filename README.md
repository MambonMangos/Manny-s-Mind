# Moneyball FPL

A data-driven Fantasy Premier League analytics platform built with Streamlit, SQLAlchemy, and Plotly.

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd moneyball-fpl

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
```

## Running

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`.

## Updating the JSON

1. Visit [https://fantasy.premierleague.com/api/bootstrap-static.json](https://fantasy.premierleague.com/api/bootstrap-static.json)
2. Save the JSON response to `data/bootstrap-static.json`
3. Refresh the Streamlit app – data is loaded automatically on first run

## Database

SQLite is used as the local data store. The database file is created at `data/moneyball.db` on first run.

### Tables

| Table | Purpose |
|---|---|
| `teams` | Club metadata and strength ratings |
| `players` | Full player data from bootstrap-static |
| `gameweeks` | Event metadata |
| `player_gameweek_stats` | Per-player weekly stats (future) |
| `price_history` | Daily price tracking (future) |
| `snapshots` | Weekly full-pool snapshots (future) |

## Architecture

```
moneyball-fpl/
├── app.py                  # Streamlit entry-point
├── database/
│   ├── models.py           # SQLAlchemy ORM models
│   ├── database.py         # Engine & session management
│   └── crud.py             # Upsert / query helpers
├── services/
│   ├── data_loader.py      # JSON → SQLite pipeline
│   ├── scoring.py          # Normalisation & composite scoring
│   └── player_service.py   # High-level queries
├── pages/
│   ├── Player Rankings.py  # Main rankings page
│   └── Team Analysis.py    # Team breakdown page
├── components/
│   ├── metrics.py          # KPI cards
│   ├── sidebar.py          # Filter widgets
│   └── tables.py           # Table renderers
├── utils/
│   └── helpers.py          # Shared utilities
├── assets/                 # Static assets
└── tests/                  # Test suite
```

### Scoring Weights

| Component | Weight | Status |
|---|---|---|
| Minutes Played | 30% | Active |
| xGI / 90 | 25% | Active |
| Value (Pts/£m) | 15% | Active |
| Team Strength | 10% | Active |
| Fixture Difficulty | 10% | Placeholder |
| Ownership | 5% | Active |
| Set Pieces | 5% | Placeholder |

Weights are defined as constants in `services/scoring.py` and can be edited independently.

## Future Roadmap

- **Captain Model** – expected points as captain
- **Transfer Model** – value gain/loss on transfers
- **Fixture Model** – full fixture difficulty ratings
- **Weekly Snapshots** – historical trend tracking
- **Price History** – track price rises and falls
- **Prediction Engine** – projected points per gameweek
