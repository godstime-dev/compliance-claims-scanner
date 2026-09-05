"""
Compliance report generation for the compliance claims scanner.

This module combines deterministic rule-based findings with
optional LLM contextual analysis and prepares the results for
human-readable reports and PDF export.

The rule-based finding remains authoritative for:
- Severity
- Confidence
- Rule identification
- Regulatory guidance

LLM analysis is optional contextual enrichment and must never
replace or modify those deterministic values.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.llm import LLMAnalysis
from app.scanner import ComplianceFinding
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    )

from pathlib import Path

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.colors import HexColor

# Report Models
@dataclass(frozen=True)
class ReportFinding:
    """
    A compliance finding combined with optional LLM analysis.

    The original ComplianceFinding remains the authoritative
    source for deterministic rule information.
    """
    finding: ComplianceFinding
    analysis: Optional[LLMAnalysis]


@dataclass(frozen=True)
class ComplianceReport:
    """
    Complete structured compliance report for a scanned URL.

    Summary counts reflect distinct claims (findings sharing the
    same rule and matched text are grouped as one), not raw
    regex match occurrences. A phrase repeated 3 times on a page
    counts as 1 finding with 3 occurrences, not 3 findings — the
    raw occurrence total is available separately via
    `total_occurrences`.
    """
    url: str
    scanned_at: datetime
    ruleset_version: str
    findings: List[ReportFinding]

    @property
    def grouped_findings(self) -> List["GroupedFinding"]:
        return group_report_findings(self.findings)

    @property
    def total_occurrences(self) -> int:
        """Raw count of individual regex matches, ungrouped."""
        return len(self.findings)

    @property
    def total_findings(self) -> int:
        """Count of distinct claims, after grouping repeats."""
        return len(self.grouped_findings)

    @property
    def high_severity_count(self) -> int:
        return sum(
            1 for gf in self.grouped_findings
            if gf.finding.severity == "High"
            )

    @property
    def medium_severity_count(self) -> int:
        return sum(
            1 for gf in self.grouped_findings
            if gf.finding.severity == "Medium"
            )

    @property
    def low_severity_count(self) -> int:
        return sum(
            1 for gf in self.grouped_findings
            if gf.finding.severity == "Low"
            )

    @property
    def analyzed_findings_count(self) -> int:
        return sum(
            1 for gf in self.grouped_findings
            if gf.analysis is not None
            )
    
# Display Grouping
@dataclass(frozen=True)
class GroupedFinding:
    """
    A display-only grouping of one or more ReportFinding entries
    that share the same rule and matched text.

    This exists purely for rendering — it never replaces or
    reorders the underlying deterministic findings.

    `occurrence_contexts` preserves every original occurrence's
    raw context, for reference. `distinct_contexts` is the
    de-duplicated version actually meant for display: contexts
    that are identical once normalized (case, whitespace) are
    collapsed into one entry with a repeat count, so a report
    does not repeat the same bare phrase multiple times with
    no additional information each time.
    """
    finding: ComplianceFinding
    analysis: Optional[LLMAnalysis]
    occurrence_contexts: List[str]
    occurrence_count: int
    distinct_contexts: List[Tuple[str, int]]


def _dedupe_contexts(contexts: List[str]) -> List[Tuple[str, int]]:
    """
    Collapse contexts that are identical once normalized
    (case-insensitive, whitespace-collapsed) into one entry each,
    preserving first-seen order and original casing for display.

    Args:
        contexts: Raw context strings, one per occurrence.

    Returns:
        A list of (representative_context, count) pairs.
    """

    order: List[str] = []
    counts: Dict[str, int] = {}
    representatives: Dict[str, str] = {}

    for ctx in contexts:
        key = " ".join(ctx.strip().lower().split())

        if key not in counts:
            counts[key] = 0
            representatives[key] = ctx
            order.append(key)

        counts[key] += 1

    return [(representatives[key], counts[key]) for key in order]


def group_report_findings(
    report_findings: List[ReportFinding],
    ) -> List[GroupedFinding]:
    """
    Group findings sharing the same rule and matched text for
    display purposes.

    This does not alter, drop, or reorder the underlying
    deterministic findings — it only combines repeated
    occurrences of the same claim into one display entry, with
    near-identical contexts further collapsed via
    _dedupe_contexts, so a report does not double-count the
    same underlying language or repeat an identical bare phrase
    multiple times.

    Args:
        report_findings: Findings paired with optional analysis.

    Returns:
        A list of GroupedFinding, one per distinct
        (rule_id, matched_text) pair, in first-seen order.
    """

    groups: Dict[tuple, list] = {}
    order: List[tuple] = []

    for rf in report_findings:
        key = (rf.finding.rule_id, rf.finding.matched_text.lower())

        if key not in groups:
            groups[key] = []
            order.append(key)

        groups[key].append(rf)

    grouped: List[GroupedFinding] = []

    for key in order:
        items = groups[key]
        representative = items[0].finding

        analysis = next(
            (rf.analysis for rf in items if rf.analysis is not None),
            None,
            )

        contexts = [rf.finding.context for rf in items]

        grouped.append(
            GroupedFinding(
                finding=representative,
                analysis=analysis,
                occurrence_contexts=contexts,
                occurrence_count=len(items),
                distinct_contexts=_dedupe_contexts(contexts),
                )
            )

    return grouped

# Report Construction
def build_report(
    url: str,
    scanned_at: datetime,
    ruleset_version: str,
    results: List[
        Tuple[
            ComplianceFinding,
            Optional[LLMAnalysis],
        ]
    ],
    ) -> ComplianceReport:
    """
    Build a structured compliance report from scan findings
    and optional LLM analyses.

    The deterministic ComplianceFinding remains authoritative
    for severity and confidence.

    Args:
        url: URL that was scanned.
        scanned_at: Timestamp of the original scan.
        ruleset_version: Version of the rule library used.
        results: Findings paired with optional LLM analysis.

    Returns:
        A structured ComplianceReport.
    """

    report_findings = [
        ReportFinding(
            finding=finding,
            analysis=analysis,
            )
        for finding, analysis in results
        ]

    return ComplianceReport(
        url=url,
        scanned_at=scanned_at,
        ruleset_version=ruleset_version,
        findings=report_findings,
        )


# Human-Readable Report Formatting
def format_report(report: ComplianceReport) -> str:
    """
    Format a ComplianceReport as a human-readable text report.

    Findings sharing the same rule and matched text are grouped
    into one entry with an occurrence count, so the report does
    not appear to double-count the same underlying claim.

    Deterministic rule information and optional LLM analysis
    are displayed as separate sections.

    If LLM analysis is unavailable, the report explicitly states
    that the analysis could not be generated.

    Args:
        report: Structured compliance report.

    Returns:
        A formatted plain-text representation of the report.
    """

    lines = [
        "COMPLIANCE SCREENING REPORT",
        "=" * 60,
        "",
        f"URL: {report.url}",
        f"Scanned: {report.scanned_at.isoformat()}",
        f"Ruleset Version: {report.ruleset_version}",
        "",
        "SUMMARY",
        "-" * 60,
        f"Total Findings: {report.total_findings}",
        f"Total Occurrences: {report.total_occurrences}",
        f"High Severity: {report.high_severity_count}",
        f"Medium Severity: {report.medium_severity_count}",
        f"Low Severity: {report.low_severity_count}",
        (
            "AI Analysis: "
            f"{report.analyzed_findings_count} of "
            f"{report.total_findings} findings analyzed"
            ),
        "",
        ]

    if not report.findings:
        lines.extend(
            [
                "No compliance findings were identified.",
                "",
                ]
            )
        return "\n".join(lines)

    for index, grouped in enumerate(report.grouped_findings, start=1):
        finding = grouped.finding
        analysis = grouped.analysis

        context_lines = []
        for i, (ctx, count) in enumerate(grouped.distinct_contexts, start=1):
            label = "Inquiry" if ctx.rstrip().endswith("?") else "Claim"
            line = (
                f"{i}. {label}:\n"
                f"{ctx}"
                )
            if count > 1:
                extra = count - 1
                line += (
                    f" (also appears {extra} more "
                    f"time{'s' if extra != 1 else ''} with no "
                    "additional context)"
                    )
            context_lines.append(line)

        padded_context_block = "\n\n".join(context_lines)    
        
        lines.extend(
            [
                f"FINDING {index}",
                "=" * 60,
                "",
                "RULE-BASED FINDING",
                "-" * 60,
                f"Rule: {finding.rule_name}",
                f"Rule ID: {finding.rule_id}",
                f"Category: {finding.category}",
                f"Severity: {finding.severity.upper()}",
                f"Confidence: {finding.confidence.upper()}",
                "",
                "Matched Text:",
                f'"{finding.matched_text}"',
                "",
                f"Occurrences: {grouped.occurrence_count}",
                "",
                "Context:",
                padded_context_block,
                "",
                "Relevant Guidance:",
                finding.regulation,
                "",
                "Rule Recommendation:",
                finding.recommendation,
                "",
                "AI CONTEXTUAL ANALYSIS",
                "-" * 60,
                ]
            )

        if analysis is None:
            lines.extend(
                [
                    "AI analysis unavailable for this finding.",
                    "",
                    ]
                )
        else:
            lines.extend(
                [
                    f"Claim Type: {analysis.claim_type.value}",
                    (
                        "Hedging Detected: "
                        f"{'Yes' if analysis.hedging_detected else 'No'}"
                        ),
                    "",
                    "Contextual Explanation:",
                    analysis.contextual_explanation,
                    "",
                    ]
                )

            if analysis.qualification_notes:
                lines.extend(
                    [
                        "Qualification Notes:",
                        analysis.qualification_notes,
                        "",
                        ]
                    )

            lines.extend(
                [
                    "AI Review Recommendation:",
                    analysis.review_recommendation,
                    "",
                    ]
                )

    return "\n".join(lines)


# Text Report Output
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

def save_text_report(
    report: ComplianceReport,
    output_path: Optional[Path] = None,
    ) -> Path:
    """
    Save a ComplianceReport as a plain-text file.

    If no output path is provided, the report is saved inside
    the project's reports directory using a timestamp-based
    filename.

    Args:
        report: Structured compliance report.
        output_path: Optional path for the output file.

    Returns:
        Path to the saved report.
    """

    if output_path is None:
        timestamp = report.scanned_at.strftime("%B %d, %Y at %I:%M %p UTC")
        base_name = f"compliance_report_{timestamp}"

        output_path = REPORTS_DIR / f"{base_name}.txt"

        counter = 1
        while output_path.exists():
            output_path = REPORTS_DIR / f"{base_name}_{counter}.txt"
            counter += 1

    output_path.parent.mkdir(parents=True, exist_ok=True,)

    output_path.write_text(
        format_report(report),
        encoding="utf-8",
        )

    return output_path


# PDF Report Output
def _safe(text: str) -> str:
    """
    Escape text before inserting it into a ReportLab Paragraph.

    Paragraph interprets a small set of HTML-like tags (e.g. <b>)
    for formatting. Scraped webpage text and LLM-generated text
    are not under our control and may contain characters like
    '<', '>', or '&' that would otherwise be misinterpreted as
    markup or break rendering.
    """
    return xml_escape(text)


def save_pdf_report(
    report: ComplianceReport,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Save a ComplianceReport as a structured, professionally formatted PDF file.
    Uses unified visual tables and containers to avoid disorganized layout sprawl.
    """
    if output_path is None:
        timestamp = report.scanned_at.strftime("%B %d, %Y at %I:%M %p UTC")
        base_name = f"compliance_report_{timestamp}"
        output_path = REPORTS_DIR / f"{base_name}.pdf"
        
        counter = 1
        while output_path.exists():
            output_path = REPORTS_DIR / f"{base_name}_{counter}.pdf"
            counter += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Establish modern, readable typographical styles
    styles = getSampleStyleSheet()
    
    title_style = styles["Title"]
    title_style.fontSize = 24
    title_style.leading = 28
    title_style.textColor = HexColor("#1A365D")  # Deep Navy Professional Anchor
    title_style.alignment = 0  # Left-aligned for a modern aesthetic

    heading_style = styles["Heading2"]
    heading_style.fontSize = 14
    heading_style.leading = 18
    heading_style.textColor = HexColor("#2B6CB0")  # Slate Blue Subheadings
    heading_style.spaceBefore = 10
    heading_style.spaceAfter = 6

    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 14
    body_style.textColor = HexColor("#2D3748")  # Charcoal for crisp reading

    # Page boundaries setup
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )

    story = []

    # 1. Main Document Header Block
    story.append(Paragraph("FDA/FTC COMPLIANCE SCREENING REPORT", title_style))
    story.append(Spacer(1, 0.15 * inch))

    # 2. Metadata Context Box
    meta_text = (
        f"<b>URL:</b> {_safe(report.url)}<br/>"
        f"<b>Scanned:</b> {report.scanned_at.strftime('%B %d, %Y at %I:%M %p UTC')}<br/>"
        f"<b>Ruleset Version:</b> {report.ruleset_version}"
    )
    
    meta_table = Table([[Paragraph(meta_text, body_style)]], colWidths=[7.5 * inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor("#F7FAFC")),
        ('BOX', (0, 0), (-1, -1), 1, HexColor("#E2E8F0")),
        ('PADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.2 * inch))

    # 3. Aggregated Summary Metric Bar
    summary_data = [
        [
            Paragraph(f"<b>Total Findings:</b> {report.total_findings}", body_style),
            Paragraph(f"<b>Occurrences:</b> {report.total_occurrences}", body_style),
            Paragraph(f"<b>High Severity:</b> {report.high_severity_count}", body_style),
            Paragraph(f"<b>Medium:</b> {report.medium_severity_count}", body_style),
            Paragraph(f"<b>Low:</b> {report.low_severity_count}", body_style),
            Paragraph(f"<b>AI Analyzed:</b> {report.analyzed_findings_count}", body_style)
        ]
    ]
    summary_table = Table(
        summary_data,
        colWidths=[1.6*inch, 1.3*inch, 1.3*inch, 1.1*inch, 1.0*inch, 1.2*inch],
        )
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor("#EDF2F7")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, HexColor("#CBD5E0")),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.25 * inch))

    if not report.findings:
        story.append(Paragraph("No compliance findings were identified.", body_style))
        document.build(story)
        return output_path

    # 4. Grouped Findings Loop
    for index, grouped in enumerate(report.grouped_findings, start=1):
        finding = grouped.finding
        analysis = grouped.analysis
        finding_elements = []

        # Section Banner Line
        finding_elements.append(Paragraph(f"FINDING {index}: {finding.rule_name.upper()}", heading_style))
        
        # Format individual tracking occurrences cleanly
        context_entries = []
        for i, (ctx, count) in enumerate(grouped.distinct_contexts, start=1):
            label = "Inquiry" if ctx.rstrip().endswith("?") else "Claim"
            entry = (
                f"<b>{i}. {label}:</b><br/>"
                f"{_safe(ctx)}"
                )
            if count > 1:
                extra = count - 1
                entry += (
                    f"<br/><font color='#718096'><i>(also appears {extra} more "
                    f"time{'s' if extra != 1 else ''} with no "
                    "additional context)</i></font>"
                    )
            context_entries.append(entry)

        context_blocks = "<br/><br/>".join(context_entries)

        # Define Structured Grid Layout data
        grid_table_data = [
            [Paragraph("<b>Rule Identification</b>", body_style), Paragraph(f"{finding.rule_id}<br/><b>Category:</b> {_safe(finding.category)}", body_style)],
            [Paragraph("<b>Risk & Confidence</b>", body_style), Paragraph(f"<b>Severity: </b>{finding.severity.upper()}<br/>" f"<b>Confidence: </b>{finding.confidence.upper()}", body_style)],
            [Paragraph("<b>Matched Flagged Text</b>", body_style), Paragraph(f"<i>&quot;{_safe(finding.matched_text)}&quot;</i><br/><b>Total Hits:</b> {grouped.occurrence_count}", body_style)],
            [Paragraph("<b>Context Occurrences</b>", body_style), Paragraph(context_blocks, body_style)],
            [Paragraph("<b>Regulatory Guidance</b>", body_style), Paragraph(_safe(finding.regulation), body_style)],
            [Paragraph("<b>Rule Recommendation</b>", body_style), Paragraph(_safe(finding.recommendation), body_style)],
        ]

        # Process optional AI enrichment data
        if analysis is None:
            grid_table_data.append([
                Paragraph("<b>AI Contextual Analysis</b>", body_style), 
                Paragraph("<font color='#A0AEC0'>AI analysis unavailable for this finding.</font>", body_style)
            ])
        else:
            ai_details = (
                f"<b>Claim Type:</b> {analysis.claim_type.value}<br/>"
                f"<b>Hedging Flags:</b> {'Yes' if analysis.hedging_detected else 'No'}<br/><br/>"
                f"<b>Contextual Explanation:</b><br/>{_safe(analysis.contextual_explanation)}"
            )
            if analysis.qualification_notes:
                ai_details += f"<br/><br/><b>Qualification Notes:</b><br/>{_safe(analysis.qualification_notes)}"
            
            ai_details += f"<br/><br/><b>AI Review Recommendation:</b><br/>{_safe(analysis.review_recommendation)}"
            
            grid_table_data.append([Paragraph("<b>AI Contextual Analysis</b>", body_style), Paragraph(ai_details, body_style)])

        # Construct and style the isolated matrix layout table
        record_table = Table(grid_table_data, colWidths=[2.0 * inch, 5.5 * inch])
        record_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#E2E8F0")),
            ('BACKGROUND', (0, 0), (0, -1), HexColor("#F7FAFC")),  # Shaded column labels
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        finding_elements.append(record_table)
        finding_elements.append(Spacer(1, 0.25 * inch))

        # Force the entire finding layout block to hold together safely on a single sheet
        story.append(KeepTogether(finding_elements))

    document.build(story)
    return output_path

# Report Validation
class ReportValidationError(Exception):
    """
    Raised when a ComplianceReport contains invalid data.
    """


def validate_report(report: ComplianceReport) -> None:
    """
    Validate the structural integrity of a compliance report.

    This validation does not change or recalculate any finding.
    It only verifies that the report contains the metadata and
    finding information required for rendering.

    Args:
        report: Compliance report to validate.

    Raises:
        ReportValidationError: If the report contains invalid
        or inconsistent data.
    """

    if not report.url.strip():
        raise ReportValidationError(
            "Report URL cannot be empty."
            )

    if not report.ruleset_version.strip():
        raise ReportValidationError(
            "Ruleset version cannot be empty."
            )

    if report.scanned_at is None:
        raise ReportValidationError(
            "Report scan timestamp cannot be missing."
            )

    for index, report_finding in enumerate(
        report.findings,
        start=1,
        ):
        if report_finding.finding is None:
            raise ReportValidationError(
                f"Finding {index} is missing its "
                "ComplianceFinding."
                )

        finding = report_finding.finding

        if not finding.rule_id.strip():
            raise ReportValidationError(
                f"Finding {index} has an empty rule ID."
                )

        if not finding.matched_text.strip():
            raise ReportValidationError(
                f"Finding {index} has empty matched text."
                )


# Public Report Generation
def generate_reports(
    report: ComplianceReport,
    save_text: bool = True,
    save_pdf: bool = True,
    ) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Validate a compliance report and optionally generate
    text and PDF report files.

    If both save_text and save_pdf are False, validation is
    skipped entirely and (None, None) is returned, since there
    is nothing to render.

    Args:
        report: Structured compliance report.
        save_text: Whether to save the plain-text report.
        save_pdf: Whether to save the PDF report.

    Returns:
        A tuple containing:
        - Path to the saved text report, or None if disabled.
        - Path to the saved PDF report, or None if disabled.

    Raises:
        ReportValidationError: If the report is invalid.
    """

    if not save_text and not save_pdf:
        return None, None

    validate_report(report)

    text_path = None
    pdf_path = None

    if save_text:
        text_path = save_text_report(report)

    if save_pdf:
        pdf_path = save_pdf_report(report)

    return text_path, pdf_path