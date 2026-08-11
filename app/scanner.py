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

from app.rules import (
    RULES,
    ComplianceRule,
    Severity,
    Confidence
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
    severity: Severity
    confidence: Confidence

    # Matched Content
    matched_text: str
    context: str

    # Compliance Guidance
    regulation: str
    explanation: str
    recommendation: str