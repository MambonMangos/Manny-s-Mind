# Guide to Our Code — for Someone New to Coding

**To:** New team member learning to read Python  
**From:** The person who wrote these changes  
**Goal:** Explain the code I just wrote so you can read and understand it — and write similar code later.

---

## Part 1: Python Basics You Need

### Variables — a labelled box

```python
player_name = "Salah"
player_score = 10.5
```

A variable is a box with a label. You put a value in it, then use the label to get the value back later. `= "Salah"` means "put the text 'Salah' in the box called `player_name`".

### Functions — a reusable recipe

```python
def greet(name):
    return "Hello " + name
```

A function is a recipe. You give it ingredients (called **parameters** — `name` above). It follows steps and returns a result. You call it like `greet("Manuel")` and get back `"Hello Manuel"`. The word `def` means "define a function". The word `return` means "send back this value as the answer".

### Classes — a blueprint for creating objects

```python
class Player:
    def __init__(self, name):
        self.name = name
```

A class is a blueprint. You use it to create objects (things) that bundle data together. The `__init__` method runs when you create a new object. `self` refers to "this object I'm creating right now". So `self.name = name` means "store the name on this object".

### If/Else — making decisions

```python
if score > 10:
    print("Great")
else:
    print("Needs work")
```

`if` checks a condition (true/false). If true, run the indented block below it. Optionally, `else` runs when the condition is false. Always check the **indentation** — Python uses indentation (spaces at the start of the line) to know which code belongs to which block.

### For loops — doing something repeatedly

```python
for player in all_players:
    print(player.name)
```

A `for` loop takes each item from a list (one at a time), puts it in the variable after `for` (here: `player`), and runs the indented code below.

### Try/Except — handling errors gracefully

```python
try:
    result = risky_function()
except ValueError:
    result = 0
```

`try` says "try to run this code". If a specific error happens (like `ValueError`), the `except` block catches it and runs instead of crashing the whole program.

### Dictionaries — a lookup table

```python
player = {"name": "Salah", "goals": 22}
print(player.get("name", "unknown"))
```

A dictionary (dict) stores key→value pairs. Like a real dictionary: you look up a word (key) and get the definition (value). `.get(key, default)` looks up the key; if missing, returns the default instead of crashing.

### Lists — an ordered collection

```python
players = ["Salah", "Haaland", "Kane"]
first = players[0]  # "Salah"
```

A list is an ordered sequence of items. Index 0 is the first item, index 1 is the second, and so on.

---

## Part 2: What We're Building

"Manny's FPL House" predicts Fantasy Premier League player scores. Every week the app:
1. **Fetches** player data from the FPL website
2. **Builds** a Feature Store — a big table of every stat for every player
3. **Runs** Engines — programs that analyse the data (e.g., "Regression Engine" catches players who are getting lucky")
4. **Stores** results in a database
5. **Shows** a dashboard in the browser

---

## Part 3: What I Changed and Why

### 1. Feature Store (`features/store.py`) — "the one source of truth"

**What this file does:** Creates a big table (DataFrame) with every stat for every player. Other parts of the app read from this table instead of recomputing numbers themselves.

**What I changed:** I added 6 new columns to that big table. Each column holds a pre-computed number so other parts of the app can just read it instead of doing the math themselves.

```
New columns added:
  finishing_ratio     → how well the player scores vs what's expected
  creative_ratio      → how well the player assists vs what's expected
  net_transfers       → transfers_in minus transfers_out
  ownership_tier      → "differential" (<5%), "mid" (5-20%), "template" (>20%)
  transfer_velocity   → how fast the player is being bought/sold
  price_direction_label → "rising", "falling", or "stable"
```

**Why it matters:** Before, two different parts of the app might compute `finishing_ratio` slightly differently and get different answers. Now there's one calculation, one answer, and everyone reads it.

**Key code explained (from `_build_xgi_features`):**

```python
# np.where(condition, value_if_true, value_if_false)
self.df["finishing_ratio"] = np.where(
    f["xg_raw"] > 0,
    df["goals_scored"].fillna(0) / f["xg_raw"],  # actual goals ÷ expected goals
    1.0,  # if xG is 0, finishing_ratio is 1.0 (neutral)
)
```

`self` refers to the FeatureStore object. `self.df` is its big DataFrame (table). `self.df["finishing_ratio"]` creates a new column. `np.where` is like an if/else for every row in the table at once — faster than looping.

```python
# np.where with if/else-if/else (nested where = if/else if/else)
self.df["price_direction_label"] = np.where(
    df["cost_change_event"].fillna(0) > 0, "rising",
    np.where(df["cost_change_event"].fillna(0) < 0, "falling", "stable"),
)
```

This is: `if cost_change > 0 → "rising"; else if cost_change < 0 → "falling"; else → "stable"`.

**The "eager compute" trick:**

```python
store.xgi_features()      # This line also writes columns to self.df
store.market_features()    # Same — side effect writes columns
store.value_features()     # Same
```

Calling these functions does two things: returns the feature table AND writes canonical columns to `store.df` as a side effect. It's like pulling a lever that both gives you a soda AND fills the ice bin for the next person.

---

### 2. Regression Engine (`engines/regression_engine.py`) — "player luck detector"

**What it does:** Figures out which players are overperforming (getting lucky) or underperforming (unlucky) compared to their expected stats.

**What I changed:** Before, this engine calculated `finishing_ratio` and `creative_ratio` itself. Now it reads them from the Feature Store.

**Before (old code):**
```python
finishing_ratio = goals / xg if xg > 0 else 1.0    # manual calculation
creative_ratio = assists / xa if xa > 0 else 1.0    # manual calculation
```

**After (new code):**
```python
finishing_ratio = float(row.get("finishing_ratio", 1.0))  # read from store
creative_ratio = float(row.get("creative_ratio", 1.0))    # read from store
```

`row` is one row of the big table (one player). `.get("finishing_ratio", 1.0)` looks up the value in that column; if missing, uses `1.0`. `float(...)` converts whatever it finds to a decimal number.

**Why it matters:** If we ever change how `finishing_ratio` is calculated, we change it in one place (the Feature Store) instead of hunting down every engine that does the math by hand.

---

### 3. Market Intelligence Engine (`engines/market_intelligence_engine.py`) — "market analyst"

**What it does:** Analyses transfer activity — who's being bought, sold, and what the market thinks.

**What I changed:** Same pattern as above — 4 calculations now come from the Feature Store instead of being computed inline.

**Before (old code — manual math):**
```python
net_transfers = transfers_in - transfers_out                      # subtraction
transfer_velocity = (net_transfers / owner_base) * 100            # division
if selected < 5: ownership_tier = "differential"                  # if/elif/else
if cost_change_event > 0: price_direction = "rising"              # more if/elif/else
```

**After (new code — read from Feature Store):**
```python
net_transfers = int(row.get("net_transfers", 0))
transfer_velocity = float(row.get("transfer_velocity", 0.0))
ownership_tier = str(row.get("ownership_tier", "mid"))
price_direction = str(row.get("price_direction_label", "stable"))
```

`int(...)` converts to whole number. `str(...)` converts to text.

---

### 4. Learning Service (`services/learning_service.py`) — "the reporter"

**What it does:** Generates a weekly report analysing how well our predictions matched reality.

**What I changed:** I protected it from crashing when there's no data to analyse.

```python
if by_type and any(v is not None for v in by_type.values()):
    try:
        top_error = max(by_type, key=by_type.get)
        ...
    except (ValueError, TypeError):
        logger.warning("Could not compute top error type...")
```

Step by step:
1. `by_type and ...` — only proceed if `by_type` is not empty AND `any(v is not None ...)` — at least one value is not None
2. `try:` — attempt the risky operation
3. `max(by_type, key=by_type.get)` — find the key with the highest value in the dictionary
4. `except (ValueError, TypeError):` — if that fails for any reason (e.g., empty values, wrong types), don't crash — just log a warning
5. `logger.warning(...)` — write a message to the log file saying what happened

I also wrapped the whole report-generating section:

```python
try:
    report.insights = _generate_insights(report)
except Exception:
    logger.exception("Failed to generate insights")
    report.insights = ["Error generating insights — review logs"]
```

This means: if anything goes wrong (any error at all), don't crash the program. Instead, write a message in the log explaining what failed, and put a placeholder message in the report so the user sees something instead of a blank error page.

**Why it matters:** If the database is empty (first week of the season), the old code would crash the whole app. Now it gracefully produces a "no data yet" report.

---

### 5. Snapshot Service (`services/snapshot_service.py`) — "save the moment"

**What it does:** Takes a snapshot of every player's stats at the moment we run the pipeline, and saves it to the database.

**What I changed:** Fixed a bug where every snapshot was saved with `player_id = 0` (invalid).

**The bug:**

The Feature Store renames the column `id` to `player_id` so everything is consistent. But the snapshot code was looking for the old name `id`:

```python
# BUG: looking for "id" but column is named "player_id"
"player_id": int(row.get("id", 0)),
```

`.get("id", 0)` searches for a column called `"id"`. The column was renamed to `"player_id"`. So `.get("id", ...)` always returns the default `0`. Every player got `player_id = 0`.

**The fix:**

```python
player_id = int(row.get("player_id", 0) or 0)
if player_id == 0:
    logger.warning("Skipping snapshot row with player_id=0 ...")
    continue  # skip this row, move to the next one
```

`continue` means "skip the rest of this loop iteration and go to the next item". It's like "skip this one, don't save it".

I also added a check at the top:

```python
if "player_id" not in df.columns:
    logger.warning("store.df has no player_id column — skipping snapshot persist")
    return  # exit the function early
```

`return` means "stop this function and go back to wherever it was called from". This prevents the whole snapshot from running if the data is broken.

**Why it matters:** Before, all ~600 players got saved with `player_id=0`, which means the snapshot database was useless — you couldn't tell which player was which.

---

### 6. Tests (`tests/test_production_fixes.py`) — "the proof it works"

**What it does:** 10 automated tests that verify all the fixes above work correctly.

```python
def test_feature_store_has_canonical_columns():
    """H-07: Feature Store must write canonical columns into store.df."""
    from features import build_feature_store

    df = synthetic_players(20)
    store = build_feature_store(players_df=df, gameweek_id=1)

    expected = [
        "finishing_ratio", "creative_ratio",
        "net_transfers", "ownership_tier",
        "transfer_velocity", "price_direction_label",
    ]
    missing = [c for c in expected if c not in store.df.columns]
    assert not missing, f"Canonical columns missing: {missing}"
```

A test function:
1. Sets up some test data (`synthetic_players(20)` creates 20 fake players)
2. Runs the code being tested (`build_feature_store(...)`)
3. Checks the result is correct — `assert` means "I assert this statement is true". If it's false, the test fails with the error message.

`assert not missing` — "I assert that `missing` is an empty list". If any column is missing, the list has items, Python treats a non-empty list as `True`, so `not True` is `False`, and the assertion fails.

Another test pattern — overriding values to test the engine reads (not recomputes):

```python
row = store.df.iloc[0].copy()     # take the first player row
row["finishing_ratio"] = 9.999    # set an absurdly high value
signal = _analyze_player_regression(row, ...)  # run the engine
assert signal.finishing_ratio == 9.999  # it should use OUR value, not recalculate
```

We deliberately put an impossible value (`9.999`) in the column. If the engine reads it, we get `9.999`. If the engine recalculates, we get a normal number (~1.0). The `assert` catches whichever one is wrong.

**Why it matters:** Without tests, you only know the code works on the day you wrote it. Tests tell you every day thereafter.

---

## Part 4: Patterns You'll See Everywhere

### `df = store.df` — "grab the big table"

Many functions start with:

```python
df = store.df
```

This just makes a short alias so we don't type `store.df` 20 times. `df` = DataFrame = the big table.

### `row.get("column_name", default)` — "read a cell safely"

```python
goals = float(row.get("goals_scored", 0) or 0)
```

This reads the `goals_scored` column from the current row. If the column doesn't exist, use `0`. The `float(...)` converts to decimal. The `or 0` is a safety net in case the value is `None` (null/empty).

### `logger.warning(...)` — "leave a note in the log"

```python
logger.warning("Skipping row with player_id=0: %s", player_name)
```

Writes a message to the application log file. Useful for debugging without printing to the screen.

### `try/except` — "plan B"

```python
try:
    risky_operation()
except SomeError:
    fallback_plan()
```

Always have a plan B. If plan A crashes, plan B runs instead.

### `for _, row in df.iterrows():` — "look at every row one at a time"

```python
for _, row in df.iterrows():
    name = row["player_name"]
```

This goes through the table row by row. `_` (underscore) is a Python convention meaning "I don't care about this value" (it's the row number). `row` gives you access to all columns for that player.

### `.get("key", default)` — "safe dictionary lookup"

```python
# Without .get():
name = my_dict["name"]   # CRASHES if "name" doesn't exist

# With .get():
name = my_dict.get("name", "")  # returns "" if missing — no crash
```

Always prefer `.get()` when you're not 100% sure the key exists.

---

## Part 5: Quick Reference — Python Syntax

| Code | Meaning |
|------|---------|
| `=` | Assign a value |
| `==` | Check if two things are equal (not `=`) |
| `!=` | Not equal |
| `if x:` | True if x is not empty, not zero, not None |
| `if x is None:` | True only if x is None (use `is`, not `==` for None) |
| `and` / `or` | Logical AND / OR |
| `not` | Logical NOT |
| `#` | Comment — ignored by Python, just for humans |
| `"""..."""` | Multi-line comment (docstring) |
| `def name():` | Define a function |
| `class Name:` | Define a class |
| `from module import thing` | Import code from another file |
| `import module` | Import a whole module |
| `[]` | List |
| `{}` | Dict |
| `()` | Tuple (like a list but can't be changed) |
| `:  # type hint` | Optional annotation saying what type a variable should be |

---

The most important thing: **read the code top to bottom, track what each variable holds, and remember that almost everything is either a loop, a condition, or a function call.** You've got this.
