"""
LLM analysis layer for the compliance claims scanner.

This module enriches deterministic rule-based findings with
contextual analysis from an LLM.

The LLM does NOT:
- Change rule-assigned severity.
- Change rule-assigned confidence.
- Create new severity scores.
- Remove or dismiss deterministic findings.

The rule engine remains the authoritative source for severity
and confidence. LLM output is optional contextual enrichment.

If the LLM is unavailable, the underlying ComplianceFinding
remains valid and the analysis gracefully degrades to None.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from app.config import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    REQUEST_TIMEOUT,
    )
from app.scanner import ComplianceFinding


# LLM Exceptions
class LLMError(Exception):
    """Base exception for LLM-related failures."""

class LLMTimeoutError(LLMError):
    """Raised when an LLM request times out."""

class LLMRequestError(LLMError):
    """Raised when an LLM request fails."""

# Claim Type
class ClaimType(str, Enum):
    """
    Classification of how the flagged language appears
    within its surrounding context.

    This classification provides contextual information only.
    It does not modify the rule's severity or confidence.
    """

    DIRECT_CLAIM = "direct_claim"
    QUALIFIED_CLAIM = "qualified_claim"
    COMPARATIVE_CLAIM = "comparative_claim"
    INCIDENTAL_MENTION = "incidental_mention"
    AMBIGUOUS = "ambiguous"


# LLM Analysis Model
@dataclass(frozen=True)
class LLMAnalysis:
    """
    Structured contextual analysis produced by the LLM.

    This model contains only AI-generated contextual information.
    Rule-assigned severity and confidence are intentionally absent
    and must never be modified by the LLM.
    """
    
    # Contextual Classification
    claim_type: ClaimType

    # Contextual Analysis
    contextual_explanation: str
    hedging_detected: bool
    qualification_notes: str

    # Review Guidance
    review_recommendation: str