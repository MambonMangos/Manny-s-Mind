# Public Onboarding & Team ID Management

Manny's FPL House is now a multi-user public application. Every visitor provides
their **own** FPL Team ID before accessing any personalized pages. The app never
defaults to Manny's personal team.

## 1. The Visitor Experience

### First visit

A new visitor lands on `https://mannysfplhouse.com` and sees the **welcome /
onboarding page** instead of a dashboard:

- A short explanation of why the Team ID is needed.
- A Team ID input with a **Continue** button.
- A "Need help finding your Team ID?" expandable help section.
- A reassurance that **no login or password is required** and nothing is stored.

### Validation

On submit the app verifies the Team ID with the official FPL API
(`https://fantasy.premierleague.com/api/entry/<id>/`) and shows:

| Outcome | Message |
|---|---|
| Team found | ✔ "Team found — _&lt;team name&gt;_. Loading your dashboard..." |
| Not found (404) | ❌ "Team ID not found. Double-check your number and try again." |
| API unreachable (timeout / connection) | ❌ "Unable to contact Fantasy Premier League. Please check your connection and try again." |
| Invalid input (empty / non-numeric / out of range) | ❌ "Please enter a valid Team ID — numbers only." |
| Any other failure | ❌ "Something went wrong while checking your team. Please try again." |

No stack traces, exception types, or raw API errors are ever shown.

### Returning in the same session

Once validated, the Team ID lives in `session_state.team_id`. Refreshing the
browser or navigating between pages keeps the session's team. New sessions
re-run onboarding.

### Change Team

The sidebar always shows:

```
Current Team
472930
[ Change Team ]
```

Selecting **Change Team** clears the stored Team ID and returns the visitor to
the onboarding page — no manual browser-state clearing required. Multiple
sequential team changes work without restarting the session.

## 2. Session Architecture

```
Anonymous Visitor
        ↓
Enter Team ID  (components/onboarding.py)
        ↓  validated against the FPL API (services/team_validation.py)
Session Team Context  (utils/team_context.py ↔ session_state.team_id)
        ↓
Every personalized service reads get_current_team_id()
```

- Team identity is per-session Streamlit state. Streamlit isolates sessions, so
  no visitor inherits another visitor's team.
- A `?team_id=NNNN` URL parameter **pre-fills** the onboarding input (nice for
  shared links) but is never trusted as the active team — validation still runs.
- Nothing is persisted to the database and nothing team-specific is logged.

## 3. Developer Guide — Retrieving the Current Team ID

**All** code reads the team from the centralized provider
`utils/team_context.py`:

```python
from utils.team_context import get_current_team_id

team_id = get_current_team_id()          # int | None
assert team_id is not None               # None ⇒ not onboarded
```

Do **not** read `session_state.team_id` directly and never hardcode a team ID.

### Page gating

Personalized pages call the gate at the top of the script (after
`st.set_page_config` and `inject_theme()`):

```python
team_id = require_team()   # renders onboarding + st.stop() when not onboarded
```

`require_team()` returns the validated `int`; it can never return `None` to a
page that continues executing.

### Setting / clearing (used by onboarding and Change Team)

```python
from utils.team_context import set_current_team_id, clear_current_team_id

set_current_team_id(472930, team_name="The Gunners")
clear_current_team_id()
```

### Which pages are gated?

| Page | Team-specific? | Gated |
|---|---|---|
| About (`About.py`) | onboarding host | Yes |
| 1 · My Team | Yes | Yes |
| 2 · Player Rankings | No | No |
| 3 · Team Analysis | No | No |
| 4 · Team History | Yes | Yes |
| 5 · Player Comparison | No | No |
| 6 · Assistant Manager | Yes | Yes |
| 7 · Model Analytics | Admin only | No |
| 8 · Model Comparison | Squad-aware | Yes |

The `services.assistant_manager.engine.run_assistant()` entry point takes an
optional `team_id` and resolves it from the session Team Context when omitted.

## 4. Validation Service

`services/team_validation.py` exposes:

```python
from services.team_validation import validate_team_id, TeamValidationStatus

result = validate_team_id("472930")
result.status       # TeamValidationStatus.{VALID, INVALID_INPUT, NOT_FOUND, ERROR}
result.team_id      # int | None
result.team_name    # str
result.manager_name # str
result.message      # user-friendly, safe to display
```

- Input is sanitized to digits-only within `1..99_999_999` before any API call.
- Validation uses a short timeout (10 s, single retry) so onboarding fails fast.
- The validator never raises; it always returns a structured result.
- The shared API client (`services/api_client.py`) redacts `/entry/<id>` path
  segments from log messages so Team IDs never appear in logs.

## 5. User Guide — Finding Your FPL Team ID

1. Go to [fantasy.premierleague.com](https://fantasy.premierleague.com) and log in.
2. Click **"My Team"** in the top navigation.
3. Look at the web address in your browser — it ends with `/entry/472930/`.
4. The number after `/entry/` (here `472930`) is your Team ID.
5. Enter that number on the onboarding page and click **Continue**.

Team IDs are public on the FPL website — anyone can look up any team by ID.
Entering one only selects *which* team's data to display.

## 6. Security Review Notes

- Team IDs are held in session state only — never persisted, never logged.
- Validation is input-sanitized (digits-only, bounded length) and never surfaces
  internal exceptions.
- URL parameters are treated as hints, never as validated identity.
- Sessions are isolated by Streamlit; there is no shared mutable team state.
- Audit-log actor attribution falls back to `unknown` when no team is active.

## 7. Future Compatibility

The Team Context layer is the foundation for authentication. A future login
system can populate the same provider from a persistent user profile:

```
Anonymous Visitor → Enter Team ID → Session Team Context → Future Login → Persistent User Profile
```

Because every call site reads `get_current_team_id()` and no service depends on
how the team was established, adding user accounts requires no refactor of
existing code.
