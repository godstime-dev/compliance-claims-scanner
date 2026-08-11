"""
Compliance scanner.

Applies the rule library defined in rules.py to cleaned webpage
text and returns structured compliance findings.

This module does NOT:
- Fetch webpages
- Parse HTML
- Clean webpage text
- Call an LLM
- Generate PDF reports

Its responsibility is limited to rule-based claim detection.
"""

import re
from dataclasses import dataclass
from typing import List
from datetime import datetime, timezone

from app.rules import (
    RULES,
    RULESET_VERSION,
    ComplianceRule,
    )


# Scanner Configuration
"""
Number of characters to include around a matched 
claim when generating contextual text for a finding.
"""
CONTEXT_WINDOW = 120


# Compliance Finding Model
@dataclass(frozen=True)
class ComplianceFinding:
    """
    Represents a single compliance issue detected in webpage text.

    A finding connects the matched text back to the rule that
    detected it and provides enough context for the eventual
    report and LLM analysis.
    """

    # Rule Identification
    rule_id: str
    rule_name: str
    category: str

    # Detection Metadata
    severity: str
    confidence: str

    # Matched Content
    matched_text: str
    context: str

    # Compliance Guidance
    regulation: str
    explanation: str
    recommendation: str


# Scan Result Model
@dataclass(frozen=True)
class ScanResult:
    """
    Represents the complete result of scanning a webpage.

    Contains the original scan metadata and all detected findings.
    Summary counts are computed properties rather than stored
    fields, so they can never drift out of sync with `findings`.
    """

    # Scan Metadata
    url: str
    text_length: int
    scanned_at: datetime
    ruleset_version: str

    # Findings
    findings: List[ComplianceFinding]

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def high_severity_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == "High"
            )

    @property
    def medium_severity_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == "Medium"
            )

    @property
    def low_severity_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == "Low"
            )

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0