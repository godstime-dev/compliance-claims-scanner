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
    ComplianceReport,
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


# Scan Results Display
def render_scan_results(scan_result) -> None:
    """
    Display deterministic rule-based scan results.

    The rule-based scanner remains the authoritative source
    for finding count, severity, confidence, and rule metadata.
    """

    st.subheader("Scan Results")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Findings",
            scan_result.total_findings,
            )

    with col2:
        st.metric(
            "High Severity",
            scan_result.high_severity_count,
            )

    with col3:
        st.metric(
            "Medium Severity",
            scan_result.medium_severity_count,
            )

    with col4:
        st.metric(
            "Low Severity",
            scan_result.low_severity_count,
            )

    if not scan_result.findings:
        st.success(
            "No compliance findings were identified."
            )
        return

    st.divider()

    for index, finding in enumerate(
        scan_result.findings,
        start=1,
        ):
        with st.expander(
            f"Finding {index}: {finding.rule_name}"
            ):
            st.markdown("### Rule-Based Finding")

            st.write(f"**Rule:** {finding.rule_name}")

            st.write(f"**Rule ID:** {finding.rule_id}")

            st.write(f"**Category:** {finding.category}")

            st.write(f"**Severity:** {finding.severity.upper()}")

            st.write(f"**Confidence:** {finding.confidence.upper()}")

            st.markdown("**Why This Was Flagged:**")

            st.write(finding.explanation)

            st.markdown("**Matched Text:**")

            st.code(
                finding.matched_text,
                language=None,
                )

            st.markdown("**Context:**")

            st.write(finding.context)

            st.markdown("**Relevant Guidance:**")

            st.write(finding.regulation)

            st.markdown("**Recommendation:**")

            st.write(finding.recommendation)


# Combined Compliance Report Display
def render_compliance_report(report: ComplianceReport) -> None:
    """
    Display the full compliance report: deterministic rule-based
    findings combined with optional LLM contextual analysis.

    Each finding's rule data and AI analysis are shown together,
    in one expander per finding, matching the structure of the
    text and PDF reports. The rule-based severity and confidence
    remain authoritative; AI analysis is contextual enrichment
    only and is never used to override them.

    Args:
        report: Structured compliance report.
    """

    st.subheader("Compliance Report")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Findings", report.total_findings)

    with col2:
        st.metric("High Severity", report.high_severity_count)

    with col3:
        st.metric("Medium Severity", report.medium_severity_count)

    with col4:
        st.metric("Low Severity", report.low_severity_count)

    if not report.findings:
        st.success("No compliance findings were identified.")
        return

    st.divider()

    for index, report_finding in enumerate(report.findings, start=1):
        finding = report_finding.finding
        analysis = report_finding.analysis

        with st.expander(f"Finding {index}: {finding.rule_name}"):
            st.markdown("### Rule-Based Finding")

            st.write(f"**Rule:** {finding.rule_name}")
            st.write(f"**Rule ID:** {finding.rule_id}")
            st.write(f"**Category:** {finding.category}")
            st.write(f"**Severity:** {finding.severity.upper()}")
            st.write(f"**Confidence:** {finding.confidence.upper()}")

            st.markdown("**Why This Was Flagged:**")
            st.write(finding.explanation)

            st.markdown("**Matched Text:**")
            st.code(finding.matched_text, language=None)

            st.markdown("**Context:**")
            st.write(finding.context)

            st.markdown("**Relevant Guidance:**")
            st.write(finding.regulation)

            st.markdown("**Rule Recommendation:**")
            st.write(finding.recommendation)

            st.divider()

            st.markdown("### AI Contextual Analysis")

            st.caption(
                "This analysis provides contextual judgment only. "
                "Rule-based severity and confidence remain authoritative."
                )

            if analysis is None:
                st.warning("AI analysis unavailable for this finding.")
                continue

            st.write(f"**Claim Type:** {analysis.claim_type.value}")

            st.write(
                "**Hedging Detected:** "
                f"{'Yes' if analysis.hedging_detected else 'No'}"
                )

            st.markdown("**Contextual Explanation:**")
            st.write(analysis.contextual_explanation)

            if analysis.qualification_notes:
                st.markdown("**Qualification Notes:**")
                st.write(analysis.qualification_notes)

            st.markdown("**AI Review Recommendation:**")
            st.write(analysis.review_recommendation)


# Report Metadata & Downloads
def render_report_downloads() -> None:
    """
    Display report metadata and download controls for a
    successfully generated compliance report.

    Download controls are shown only when the corresponding
    report file exists in Streamlit session state and can
    still be read from disk.
    """

    report = st.session_state.compliance_report

    if report is None:
        return

    st.divider()

    st.subheader("Report")

    st.write(f"**Scanned URL:** {report.url}")

    st.write(
        f"**Scanned At:** "
        f"{report.scanned_at.strftime('%B %d, %Y at %I:%M %p UTC')}"
        )

    st.write(
        f"**Ruleset Version:** "
        f"{report.ruleset_version}"
        )

    text_report_path = st.session_state.text_report_path
    pdf_report_path = st.session_state.pdf_report_path

    if text_report_path is None and pdf_report_path is None:
        st.info(
            "No report files are currently available for download."
            )
        return

    col1, col2 = st.columns(2)

    if text_report_path is not None:
        try:
            with open(text_report_path, "rb") as text_file:
                text_data = text_file.read()
        except FileNotFoundError:
            text_data = None

        with col1:
            if text_data is not None:
                st.download_button(
                    label="Download Text Report",
                    data=text_data,
                    file_name=text_report_path.name,
                    mime="text/plain",
                    )
            else:
                st.warning("Text report file is no longer available.")

    if pdf_report_path is not None:
        try:
            with open(pdf_report_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()
        except FileNotFoundError:
            pdf_data = None

        with col2:
            if pdf_data is not None:
                st.download_button(
                    label="Download PDF Report",
                    data=pdf_data,
                    file_name=pdf_report_path.name,
                    mime="application/pdf",
                    )
            else:
                st.warning("PDF report file is no longer available.")


# Main Application
def main() -> None:
    """
    Run the Streamlit compliance scanner application.

    The UI renders the scan controls first, then displays
    either the completed compliance report or the raw
    deterministic scan results when report generation fails.
    If no scan has been run yet, a placeholder message is shown.
    """

    initialize_session_state()

    url, scan_clicked = render_scan_controls()

    if scan_clicked:
        run_scan(url)

    compliance_report = st.session_state.compliance_report
    scan_result = st.session_state.scan_result

    if compliance_report is not None:
        render_compliance_report(compliance_report)
        render_report_downloads()

    elif scan_result is not None:
        render_scan_results(scan_result)

    else:
        st.info(
            "Enter a supplement brand's URL above and click "
            "\"Scan Page\" to check for potentially risky "
            "marketing and compliance claims."
            )


if __name__ == "__main__":
    main()