"""ui/inject.py
The one place that injects a hidden script iframe into the app.

Streamlit has deprecated st.components.v1.html (its docs say it will be removed in a later
version). If your Streamlit ever drops it, this file is the only one that needs to change.
The st.iframe fallback is untested: it assumes scripts inside it can still reach the parent page.
"""
import streamlit as st
import streamlit.components.v1 as components


def inject_html(html: str, height: int = 0) -> None:
    """Embed an HTML/JS snippet in a (normally zero-height) iframe."""
    try:
        components.html(html, height=height)
    except AttributeError:
        st.iframe(html, height=max(height, 1))