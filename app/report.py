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
from typing import List, Optional, Tuple

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

    Summary counts are computed properties rather than stored
    fields, so they can never drift out of sync with `findings`.
    """
    url: str
    scanned_at: datetime
    ruleset_version: str
    findings: List[ReportFinding]

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def high_severity_count(self) -> int:
        return sum(1 for rf in self.findings if rf.finding.severity == "High")

    @property
    def medium_severity_count(self) -> int:
        return sum(1 for rf in self.findings if rf.finding.severity == "Medium")

    @property
    def low_severity_count(self) -> int:
        return sum(1 for rf in self.findings if rf.finding.severity == "Low")


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
        f"High Severity: {report.high_severity_count}",
        f"Medium Severity: {report.medium_severity_count}",
        f"Low Severity: {report.low_severity_count}",
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

    for index, report_finding in enumerate(
        report.findings,
        start=1,
        ):
        finding = report_finding.finding
        analysis = report_finding.analysis

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
                "Context:",
                finding.context,
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
        timestamp = report.scanned_at.strftime("%Y%m%d_%H%M%S")
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
    Save a ComplianceReport as a PDF file.

    The PDF preserves the distinction between deterministic
    rule-based findings and optional LLM contextual analysis.

    Text originating from scraped webpage content or LLM output
    is escaped before being inserted into the PDF, since it is
    not under our control and may contain characters that would
    otherwise be misinterpreted as markup.

    Args:
        report: Structured compliance report.
        output_path: Optional path for the output PDF.

    Returns:
        Path to the saved PDF.
    """

    if output_path is None:
        timestamp = report.scanned_at.strftime("%Y%m%d_%H%M%S")
        base_name = f"compliance_report_{timestamp}"

        output_path = REPORTS_DIR / f"{base_name}.pdf"

        counter = 1
        while output_path.exists():
            output_path = REPORTS_DIR / f"{base_name}_{counter}.pdf"
            counter += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    body_style = styles["BodyText"]

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        )

    story = []

    story.append(
        Paragraph("COMPLIANCE SCREENING REPORT", title_style)
        )

    story.append(Spacer(1, 0.2 * inch))

    story.extend(
        [
            Paragraph(
                f"<b>URL:</b> {_safe(report.url)}",
                body_style,
                ),
            Paragraph(
                f"<b>Scanned:</b> {report.scanned_at.isoformat()}",
                body_style,
                ),
            Paragraph(
                f"<b>Ruleset Version:</b> {report.ruleset_version}",
                body_style,
                ),
            Spacer(1, 0.2 * inch),
            Paragraph("SUMMARY", heading_style),
            Paragraph(
                f"Total Findings: {report.total_findings}",
                body_style,
                ),
            Paragraph(
                f"High Severity: {report.high_severity_count}",
                body_style,
                ),
            Paragraph(
                f"Medium Severity: {report.medium_severity_count}",
                body_style,
                ),
            Paragraph(
                f"Low Severity: {report.low_severity_count}",
                body_style,
                ),
            Spacer(1, 0.25 * inch),
        ]
    )

    if not report.findings:
        story.append(
            Paragraph(
                "No compliance findings were identified.",
                body_style,
                )
            )

    for index, report_finding in enumerate(report.findings, start=1):
        finding = report_finding.finding
        analysis = report_finding.analysis

        story.extend(
            [
                Paragraph(f"FINDING {index}", heading_style),
                Paragraph("<b>RULE-BASED FINDING</b>", body_style),
                Paragraph(
                    f"<b>Rule:</b> {_safe(finding.rule_name)}",
                    body_style,
                    ),
                Paragraph(
                    f"<b>Rule ID:</b> {finding.rule_id}",
                    body_style,
                    ),
                Paragraph(
                    f"<b>Category:</b> {_safe(finding.category)}",
                    body_style,
                    ),
                Paragraph(
                    f"<b>Severity:</b> {finding.severity.upper()}",
                    body_style,
                    ),
                Paragraph(
                    f"<b>Confidence:</b> {finding.confidence.upper()}",
                    body_style,
                    ),
                Spacer(1, 0.08 * inch),
                Paragraph("<b>Matched Text:</b>", body_style),
                Paragraph(
                    f"&quot;{_safe(finding.matched_text)}&quot;",
                    body_style,
                    ),
                Spacer(1, 0.08 * inch),
                Paragraph("<b>Context:</b>", body_style),
                Paragraph(_safe(finding.context), body_style),
                Spacer(1, 0.08 * inch),
                Paragraph("<b>Relevant Guidance:</b>", body_style),
                Paragraph(_safe(finding.regulation), body_style),
                Spacer(1, 0.08 * inch),
                Paragraph("<b>Rule Recommendation:</b>", body_style),
                Paragraph(_safe(finding.recommendation), body_style),
                Spacer(1, 0.12 * inch),
                Paragraph(
                    "<b>AI CONTEXTUAL ANALYSIS</b>",
                    heading_style,
                    ),
            ]
        )

        if analysis is None:
            story.append(
                Paragraph(
                    "AI analysis unavailable for this finding.",
                    body_style,
                    )
                )
        else:
            story.extend(
                [
                    Paragraph(
                        f"<b>Claim Type:</b> {analysis.claim_type.value}",
                        body_style,
                        ),
                    Paragraph(
                        "<b>Hedging Detected:</b> "
                        f"{'Yes' if analysis.hedging_detected else 'No'}",
                        body_style,
                        ),
                    Spacer(1, 0.08 * inch),
                    Paragraph(
                        "<b>Contextual Explanation:</b>",
                        body_style,
                        ),
                    Paragraph(
                        _safe(analysis.contextual_explanation),
                        body_style,
                        ),
                    ]
                )

            if analysis.qualification_notes:
                story.extend(
                    [
                        Spacer(1, 0.08 * inch),
                        Paragraph(
                            "<b>Qualification Notes:</b>",
                            body_style,
                            ),
                        Paragraph(
                            _safe(analysis.qualification_notes),
                            body_style,
                            ),
                        ]
                    )

            story.extend(
                [
                    Spacer(1, 0.08 * inch),
                    Paragraph(
                        "<b>AI Review Recommendation:</b>",
                        body_style,
                        ),
                    Paragraph(
                        _safe(analysis.review_recommendation),
                        body_style,
                        ),
                    ]
                )

        story.append(Spacer(1, 0.25 * inch))

    document.build(story)

    return output_path