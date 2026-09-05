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
from datetime import datetime, timezone
from typing import List

from app.rules import (
    RULES,
    RULESET_VERSION,
    ComplianceRule,
    Severity,
    Confidence,
    )


# ==========================================================
# Scanner Configuration
# ==========================================================

# Number of characters to include on EACH SIDE of a matched
# claim when generating contextual text for a finding. Context
# extraction never crosses a newline boundary, regardless of
# this value — see extract_context().
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


# ==========================================================
# Regex Compilation
# ==========================================================
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
            re.compile(pattern, re.IGNORECASE)
            for pattern in rule.patterns
            ]
    return compiled_rules


COMPILED_RULES = compile_rules(RULES)


# ==========================================================
# Context Extraction
# ==========================================================

# If a sentence-bounded snippet comes out shorter than this,
# it's likely not informative on its own (e.g. "Burn Fat." from
# a run-on tag list) — keep expanding to neighboring sentences
# within the same element until this length is reached.
MIN_CONTEXT_LENGTH = 40

# Hard ceiling on expansion, in case an element's text has no
# punctuation at all (a long unbroken run of words) — falls
# back to a plain character window with visible "..." markers.
MAX_CONTEXT_LENGTH = 400


def extract_context(
    text: str,
    start: int,
    end: int,
    window: int = CONTEXT_WINDOW,
    ) -> str:
    """
    Extract surrounding text around a regex match.

    Context is bounded by the surrounding HTML element (never
    crosses a newline, since text on the other side of one came
    from a different, unrelated element).

    Within that boundary, the context expands outward by whole
    sentences (split on ., !, ?) starting from the sentence
    containing the match, continuing until the snippet reaches
    MIN_CONTEXT_LENGTH or the element boundary is reached. This
    avoids returning a fragment too short to be meaningful (e.g.
    a single short tag in a run-on list) while never crossing
    into unrelated sentences beyond what's needed.

    If the element has no sentence-ending punctuation at all
    (or the sentence-bounded result exceeds MAX_CONTEXT_LENGTH),
    falls back to a plain character window with visible "..."
    markers so truncation is never silent.

    Args:
        text: Full cleaned webpage text.
        start: Start position of the regex match.
        end: End position of the regex match.
        window: Fallback window size, used only when no usable
            sentence boundaries are found.

    Returns:
        A trimmed context string from the same element only.
    """

    prev_newline = text.rfind("\n", 0, start)
    line_start = 0 if prev_newline == -1 else prev_newline + 1

    next_newline = text.find("\n", end)
    line_end = len(text) if next_newline == -1 else next_newline

    line = text[line_start:line_end]
    match_start_rel = start - line_start
    match_end_rel = end - line_start

    sentence_end_positions = [
        m.end() for m in re.finditer(r"[.!?]", line)
        ]

    spans = []
    prev = 0
    for pos in sentence_end_positions:
        spans.append((prev, pos))
        prev = pos
    if prev < len(line):
        spans.append((prev, len(line)))

    span_idx = None
    for i, (s, e) in enumerate(spans):
        if s <= match_start_rel < e or s < match_end_rel <= e:
            span_idx = i
            break

    if span_idx is None:
        # No usable sentence structure at all — fall back to a
        # plain character window, marked with "..." if trimmed.
        window_start = max(line_start, start - window)
        window_end = min(line_end, end + window)

        context = text[window_start:window_end]
        context = " ".join(context.split())

        if window_start > line_start:
            context = "... " + context
        if window_end < line_end:
            context = context + " ..."

        return context

    lo, hi = span_idx, span_idx

    def _span_text() -> str:
        return line[spans[lo][0]:spans[hi][1]]

    while (
        len(_span_text().strip()) < MIN_CONTEXT_LENGTH
        and (lo > 0 or hi < len(spans) - 1)
        ):
        expanded = False

        if hi < len(spans) - 1:
            hi += 1
            expanded = True

        if (
            len(_span_text().strip()) < MIN_CONTEXT_LENGTH
            and lo > 0
            ):
            lo -= 1
            expanded = True

        if not expanded:
            break

    context = " ".join(_span_text().split())

    if len(context) > MAX_CONTEXT_LENGTH:
        window_start = max(line_start, start - window)
        window_end = min(line_end, end + window)

        context = text[window_start:window_end]
        context = " ".join(context.split())

        if window_start > line_start:
            context = "... " + context
        if window_end < line_end:
            context = context + " ..."

    return context


# ==========================================================
# Rule Matching
# ==========================================================
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


# ==========================================================
# Scan Result Builder
# ==========================================================
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


# ==========================================================
# Public Scanner Interface
# ==========================================================
def scan(
    url: str,
    text: str,
    rules: List[ComplianceRule] = RULES,
    ) -> ScanResult:
    """
    Run a complete compliance scan on cleaned webpage text.

    This is the main public interface for the scanner.

    Args:
        url: URL of the webpage being scanned.
        text: Cleaned webpage text.
        rules: Compliance rules to apply.

    Returns:
        A complete ScanResult containing all findings
        and scan-level summary information.
    """
    findings = scan_text(text=text, rules=rules)
    return build_scan_result(url=url, text=text, findings=findings)