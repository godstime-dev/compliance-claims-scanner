"""
Streamlit interface for the compliance claims scanner.

This module provides the application entry point and coordinates
the existing scraper, cleaner, scanner, LLM, and report layers.

The underlying business logic remains inside the app package.
"""

import streamlit as st

from app.scraper import (
    InvalidURLError,
    ScraperError,
    fetch_page,
    )

from app.cleaner import (
    CleanerError,
    extract_visible_text,
    )

from app.scanner import scan

from app.llm import analyze_findings

from app.report import (
    ReportValidationError,
    build_report,
    generate_reports,
    validate_report,
    )


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


# URL Input & Scan Controls
def render_scan_controls() -> tuple[str, bool]:
    """
    Render the URL input and scan button.

    Returns:
        A tuple containing the submitted URL and whether
        the scan button was clicked.
    """

    st.title("Compliance Claims Scanner")

    st.write(
        "Scan a supplement brand's webpage for potentially "
        "risky marketing and compliance claims."
        )

    url = st.text_input(
        "Website URL",
        placeholder="https://example.com",
        )

    scan_clicked = st.button(
        "Scan Page",
        type="primary",
        )

    return url.strip(), scan_clicked


# Scan Orchestration
def run_scan(url: str) -> None:
    """
    Execute the complete compliance scanning pipeline.

    The pipeline performs:

    1. Fetch webpage HTML.
    2. Extract visible text.
    3. Run deterministic compliance rules.
    4. Run optional LLM contextual analysis.
    5. Build the structured compliance report.
    6. Generate text and PDF reports.

    Existing scan-dependent session state is cleared before
    starting so stale results cannot remain visible if the
    new scan fails.

    If scraping, cleaning, or rule-based scanning fail, no
    partial results are shown. If a failure occurs after
    rule-based scanning succeeds (LLM analysis, report
    building, or file generation), the deterministic scan
    results remain available and a warning is shown instead
    of a full failure.

    Args:
        url: Website URL to scan.
    """

    st.session_state.scan_result = None
    st.session_state.compliance_report = None
    st.session_state.text_report_path = None
    st.session_state.pdf_report_path = None

    if not url:
        st.warning("Please enter a URL.")
        return

    try:
        with st.spinner("Fetching webpage..."):
            html = fetch_page(url)

        with st.spinner("Extracting webpage content..."):
            text = extract_visible_text(html)

        with st.spinner("Scanning for compliance claims..."):
            scan_result = scan(
                url=url,
                text=text,
                )

        st.session_state.scan_result = scan_result

        try:
            with st.spinner("Running contextual analysis..."):
                llm_results = analyze_findings(scan_result.findings)

            report = build_report(
                url=scan_result.url,
                scanned_at=scan_result.scanned_at,
                ruleset_version=scan_result.ruleset_version,
                results=llm_results,
                )

            validate_report(report)

            with st.spinner("Generating reports..."):
                text_report_path, pdf_report_path = (
                    generate_reports(report)
                    )

            st.session_state.compliance_report = report
            st.session_state.text_report_path = text_report_path
            st.session_state.pdf_report_path = pdf_report_path

            st.success("Scan completed successfully.")

        except ReportValidationError as exc:
            st.warning(
                f"{scan_result.total_findings} finding(s) detected, "
                f"but the report could not be finalized: {exc}"
                )

        except Exception as exc:
            st.warning(
                f"{scan_result.total_findings} finding(s) detected, "
                "but report generation failed. Raw scan results are "
                "still available."
                )
            st.exception(exc)

    except InvalidURLError as exc:
        st.error(f"Invalid URL: {exc}")

    except ScraperError as exc:
        st.error(f"Unable to fetch webpage: {exc}")

    except CleanerError as exc:
        st.error(f"Unable to extract webpage content: {exc}")

    except Exception as exc:
        st.error("An unexpected error occurred while running the scan.")
        st.exception(exc)