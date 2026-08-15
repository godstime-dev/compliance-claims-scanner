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


# Application State
def initialize_session_state() -> None:
    """
    Initialize Streamlit session state used by the application.

    Existing values are preserved so reruns caused by Streamlit
    interactions do not erase the current scan results.
    """

    if "scan_result" not in st.session_state:
        st.session_state.scan_result = None

    if "compliance_report" not in st.session_state:
        st.session_state.compliance_report = None

    if "text_report_path" not in st.session_state:
        st.session_state.text_report_path = None

    if "pdf_report_path" not in st.session_state:
        st.session_state.pdf_report_path = None