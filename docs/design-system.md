# Design System — Manny's FPL House

Single source of truth for how the UI is built: tokens, the component
layering contract, the Trust Layer, and how existing pages migrate onto it.

## 1. Token hierarchy

Colours, typography, spacing, radii and breakpoints live in
`components/design_tokens.py` — nothing else hardcodes a colour, font size or
radius.

Three tiers, with a strict dependency direction (tier 2 reads tier 1, tier 3
reads tier 2, never the other way):

| Tier | Name | Contents | Example |
|------|------|----------|---------|
| 1 | `PALETTE` | raw hex values | `"ink": "#09090b"` |
| 2 | `COLORS` | semantic token → palette key | `"trust_primary": "indigo_500"` |
| 3 | states & primitives | evidence/confidence/risk/fixture groups, typography, spacing, radii, breakpoints | `EVIDENCE_LEVELS`, `TYPOGRAPHY` |

Components ask *what meaning*, never *which hex*:

```python
from components.design_tokens import color

style = f"color: {color('confidence_high')};"
```

Swap a colour by editing `COLORS`; pages never change. Unknown tokens raise
`KeyError` so typos fail fast (`color("confidence_hig")` → error, not a grey
UI).

### State groups

- `EVIDENCE_LEVELS` — 5 levels mirroring the learning service thresholds
  (`weak` 1, `needs_more_data` 2, `moderate` 3, `strong` 5,
  `statistically_significant` 10). `confidence_level_for(pct)` maps 0–100 to
  high/medium/low.
- `CONFIDENCE_LEVELS` / `RISK_LEVELS` / `FIXTURE_LEVELS` — labels + colour
  keys for their respective badges.

### CSS emission

`build_css_variables()` emits the legacy `:root { ... }` custom-property block
byte-for-byte (comment included). `components/theme.py` injects it on every
page. The regression test `tests/test_ui_components.py` pins the block so a
token edit can never silently re-skin the app.

## 2. Component layering contract

Three layers. This is the contract that makes a future REST/React migration
possible: only the renderer layer touches Streamlit.

```
 services/           backend engines & data        (unchanged)
 components/domain/models.py
                     Streamlit-free dataclasses    (the UI's vocabulary)
 components/domain/*.py  presenters (pure HTML)    (escaping happens HERE)
 components/ui/*.py      presenters + renderers    (generic primitives)
 pages/*.py              adapters + render calls   (never hand-built markup)
```

Rules:

1. **Domain models** (`components/domain/models.py`) import nothing from
   Streamlit, pandas, or the backend services. Pages adapt backend objects
   into these shapes.
2. **Presenters** return HTML strings and never call `st.*`. Every dynamic
   value is escaped at this boundary (`esc()` in `components/ui/base.py`).
   A component must never pass unescaped FPL/user data into
   `unsafe_allow_html=True`.
3. **Renderers** are thin: one `st.markdown(html, unsafe_allow_html=True)`
   wrapper per component. Only they touch Streamlit.
4. Pages do not build markup by hand — no inline `f"<div style=...>"` with
   `unsafe_allow_html=True`.

## 3. Primitives (`components/ui/`)

| Module | Provides |
|--------|----------|
| `base.py` | `esc`, `class_attr`, `span`, `div` |
| `badges.py` | position / risk / evidence / confidence / fixture / model-agreement / delta badges |
| `cards.py` | `metric_card_html`, `card_html`, `render_metric_card`, `render_card` |
| `metrics.py` | responsive CSS-grid metric rows (`render_metric_grid`, 2 or 4 cols) |
| `states.py` | empty state + escaped `st.info/warning/error/success` alerts |
| `layout.py` | page header, section label/title, divider, hero title |

All badge levels derive from the state tokens, so a level's colour and label
change in one place.

## 4. Domain components (`components/domain/`)

| Module | Contents |
|--------|----------|
| `models.py` | `PlayerRef`, `Evidence`, `TrustSection`, `ProjectionCard`, `CaptainCard`, `TransferCard`, `ChipCard`, `FixtureCard` |
| `evidence.py` | `evidence_from_gameweeks`, `trust_section_html`, `render_trust_section` |
| `projection.py` | xPts card with CI band + driver list |
| `captain.py` | captaincy card |
| `transfer.py` | out→in transfer card |
| `chip.py` | chip strategy card |
| `fixture.py` | fixture difficulty card |
| `squad.py` | squad rating gauge + summary metric grid |

## 5. Trust Layer (mandatory)

Every recommendation is displayed with a trust block. `TrustSection` carries:

- `evidence` — `Evidence` (level + gameweek count + description)
- `confidence_pct` — 0–100
- `reasoning` — the "why" trail
- `model_agreement` — V3-vs-V2 agreement rate (0–1) or `None`
- `historical_accuracy` — observed accuracy (0–1) or `None`
- `data_quality` — high/medium/low

Rules:

1. **Never fabricate.** If a measure was never recorded it stays `None` and
   the slot is omitted — a missing badge is truthful data.
2. `render_trust_section` renders nothing at all when there is no trust data
   (`trust_section_html(TrustSection()) == ""`).
3. Badges come from `components/ui/badges.py`; the description text and "why"
   reasons are escaped.

## 6. Migration playbook (per page)

1. Identify backend objects the page consumes.
2. Add small adapter functions → domain dataclasses (page-local is fine).
3. Replace hand-built HTML / ad-hoc `st.markdown` with `render_*` calls.
4. Replace ad-hoc `st.info/st.warning/st.success/st.error` with
   `components.ui.render_info/render_warning/render_success/render_error`
   (they escape the message).
5. Replace inline metric cards with `render_metric_grid`.
6. Never mix presenter HTML with page HTML in the same markdown string.

Order: Assistant Manager (done) → Model Comparison → remaining pages →
legacy `components/player_card.py` / `fixture_widget.py` consolidation.
