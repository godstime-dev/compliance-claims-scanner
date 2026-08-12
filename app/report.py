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