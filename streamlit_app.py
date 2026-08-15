"""
Streamlit interface for the compliance claims scanner.

This module provides the application entry point and coordinates
the existing scraper, cleaner, scanner, LLM, and report layers.

The underlying business logic remains inside the app package.
"""

import streamlit as st


# Page Configuration
st.set_page_config(
    page_title="Compliance Claims Scanner",
    page_icon="🔎",
    layout="wide",
    )