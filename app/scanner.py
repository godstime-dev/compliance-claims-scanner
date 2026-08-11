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
Number of characters to include on each side of a matched 
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


# Regex Compilation
def compile_rules(
    rules: List[ComplianceRule],
    ) -> dict[str, List[re.Pattern]]:
    """
    Compile all regex patterns associated with the supplied rules.

    Args:
        rules: Compliance rules containing raw regex patterns.

    Returns:
        A dictionary mapping each rule ID to its compiled
        regular expression patterns.
    """

    compiled_rules = {}

    for rule in rules:
        compiled_rules[rule.id] = [
            re.compile(
                pattern,
                re.IGNORECASE,
                )
            for pattern in rule.patterns
            ]

    return compiled_rules

COMPILED_RULES = compile_rules(RULES)


# Context Extraction
def extract_context(
    text: str,
    start: int,
    end: int,
    window: int = CONTEXT_WINDOW,
    ) -> str:
    """
    Extract surrounding text around a regex match.

    The returned context is limited to a configurable number
    of characters before and after the matched text.

    Args:
        text: Full cleaned webpage text.
        start: Start position of the regex match.
        end: End position of the regex match.
        window: Number of surrounding characters to include.

    Returns:
        A trimmed context string containing the matched text
        and surrounding webpage content.
    """

    context_start = max(0, start - window)
    context_end = min(len(text), end + window)

    context = text[context_start:context_end]

    return " ".join(context.split())


# Rule Matching
def scan_text(
    text: str,
    rules: List[ComplianceRule] = RULES,
    ) -> List[ComplianceFinding]:
    """
    Scan cleaned webpage text against the compliance rule library.

    Each regex match becomes a structured ComplianceFinding.

    Args:
        text: Cleaned webpage text.
        rules: Compliance rules to apply.

    Returns:
        A list of detected compliance findings.
    """

    findings: List[ComplianceFinding] = []

    for rule in rules:
        patterns = COMPILED_RULES[rule.id]

        for pattern in patterns:
            for match in pattern.finditer(text):
                matched_text = match.group(0).strip()

                if not matched_text:
                    continue

                context = extract_context(
                    text=text,
                    start=match.start(),
                    end=match.end(),
                    )

                finding = ComplianceFinding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    category=rule.category,
                    severity=rule.severity.value,
                    confidence=rule.confidence.value,
                    matched_text=matched_text,
                    context=context,
                    regulation=rule.regulation,
                    explanation=rule.explanation,
                    recommendation=rule.recommendation,
                    )

                findings.append(finding)

    return findings


# Scan Result Builder
def build_scan_result(
    url: str,
    text: str,
    findings: List[ComplianceFinding],
    ) -> ScanResult:
    """
    Build a complete ScanResult from detected findings.

    Args:
        url: URL of the webpage that was scanned.
        text: Cleaned webpage text.
        findings: Findings returned by scan_text().

    Returns:
        A populated ScanResult instance.
    """

    return ScanResult(
        url=url,
        text_length=len(text),
        scanned_at=datetime.now(timezone.utc),
        ruleset_version=RULESET_VERSION,
        findings=findings,
        )