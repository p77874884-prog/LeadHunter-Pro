"""Render compatibility wrapper.

Render is trying to start the app with `streamlit run main.py`.
This file imports the real Streamlit app from `app.py`.
"""

import app  # noqa: F401
