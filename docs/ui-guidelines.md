# UI Guidelines — Manny's FPL House

Practical rules for writing page code against the design system. See
`docs/design-system.md` for the token model and component inventory.

## 1. Never hardcode a style

No hex values, font sizes, border radii or spacing in page or component code.
Use tokens:

```python
from components.design_tokens import color, RADII

style = f"color: {color('confidence_high')}; border-radius: {RADII['sm']};"
```

If you need a value that doesn't exist, add it to the tokens — do not inline
it.

## 2. The presenter boundary escapes everything

All FPL-sourced strings (player names, teams, reasoning) go through `esc()`
at the HTML presenter layer:

```python
from components.ui.base import esc

return f'<div class="card-title">{esc(player.web_name)}</div>'
```

Never build `unsafe_allow_html=True` strings in a page; never pass raw data
into one. Player web names are external input.

## 3. Every recommendation needs a trust block

Recommendations (transfers, captaincy, chips, projections) are rendered with a
`TrustSection`. If you have a partial signal, show what you have and leave the
rest out — do not invent confidence or accuracy numbers. Rendering "nothing"
is the correct behaviour for missing data.

## 4. Every metric answers "what does this mean?"

A number without a label, unit and context is noise. Use the `.metric-label`
and `.metric-value` pattern via `render_metric_card` / `render_metric_grid`:

```python
render_metric_card("Avg Value Score", f"{df['value_score'].mean():.1f}")
```

Always include the unit (`m`, `%`, `/90`, `/100`) and a human label.

## 5. Prefer existing components over new ones

Before building a badge, card, grid or alert, check `components/ui/` and
`components/domain/`. If you must extend, extend the token/component layer —
not the page.

## 6. Use the shared renderers for status messages

Replace ad-hoc `st.info(...)`, `st.warning(...)`, `st.success(...)`,
`st.error(...)` with the escaping variants from `components.ui`:

```python
from components.ui import render_warning

render_warning(rotation_risk_note)
```

## 7. Layout

- Page structure: `inject_theme()` → `ensure_data_loaded()` →
  `render_refresh_button()` → `page_header(title, subtitle)` → sections.
- Use `section_label` / `section_title` for section headers, `divider()` to
  separate sections.
- Use `render_metric_grid(cards, columns=4)` for KPI rows; it is a responsive
  CSS grid (2-across on small screens), not `st.columns`.
- Keep Streamlit-native widgets (`st.dataframe`, `st.plotly_chart`) for data
  tables and charts — those are fine.

## 8. Accessibility

- Badges carry text labels, not colour alone (e.g. "High Risk", "Strong").
  Colour is redundant reinforcement.
- Don't rely on emoji as the only cue in `EVIDENCE_LEVELS`/`FIXTURE_LEVELS` —
  the text label accompanies it.
- Keep contrast: text colours come from the `text_*` tokens, accents are for
  emphasis only.

## 9. Migration order for remaining pages

1. `pages/8_Model_Comparison.py` — comparison / agreement reports
2. `pages/5_Player_Comparison.py` (also fixes the fixture-slider bounds bug
   at line ~323)
3. `pages/1_My_Team.py`, `2_Player_Rankings.py`, `3_Team_Analysis.py`,
   `4_Team_History.py`, `7_Model_Analytics.py`
4. Consolidate `components/player_card.py` and `components/fixture_widget.py`
   into the domain layer, then remove them.

## 10. Definition of done for a migration

- Page renders unchanged visually (CSS regression test still green).
- No `unsafe_allow_html` strings built in the page.
- No ad-hoc `st.info/warning/success/error` calls outside the shared
  renderers.
- New tests in `tests/test_ui_components.py` where presenters were added.
- `ruff` clean on the touched files; full `pytest` suite green.
