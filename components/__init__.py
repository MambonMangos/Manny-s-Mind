"""Manny's FPL House design system.

Design tokens (:mod:`components.design_tokens`) -> UI primitives
(:mod:`components.ui`) -> FPL domain components (:mod:`components.domain`).

Layering contract (see docs/design-system.md):

    domain models   dataclasses, no Streamlit / pandas / HTML
    presenters      pure functions returning HTML strings; ALL dynamic
                    text is HTML-escaped here
    renderers       thin functions that touch ``st.*`` only; they delegate
                    to presenters and call ``st.markdown(..., unsafe_allow_html=True)``

Backend services never import this package; only the UI layer does.
"""
