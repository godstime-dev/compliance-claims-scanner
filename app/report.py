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