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


# Provider Client
def _create_openai_client():
    """
    Create and return an OpenAI client.
    """
    from openai import OpenAI
    return OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=REQUEST_TIMEOUT,
        )

def _create_anthropic_client():
    """
    Create and return an Anthropic client.
    """
    from anthropic import Anthropic
    return Anthropic(
        api_key=ANTHROPIC_API_KEY,
        )


def _call_provider(
    system_prompt: str,
    user_prompt: str,
    ) -> str:
    """
    Send a prompt to the configured LLM provider.

    The provider-specific response format is normalized into
    a plain string for the rest of the module.

    Args:
        system_prompt: System-level instructions.
        user_prompt: User-level analysis request.

    Returns:
        Raw text returned by the configured provider.

    Raises:
        LLMTimeoutError: If the provider request times out.
        LLMRequestError: If the provider request fails.
    """

    if LLM_PROVIDER == "openai":
        import openai

        try:
            client = _create_openai_client()
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                    ],
                )
            
            content = response.choices[0].message.content
            if not content:
                raise LLMRequestError(
                    "OpenAI returned an empty response."
                    )
            return content

        except openai.APITimeoutError as exc:
            raise LLMTimeoutError(
                "OpenAI request timed out."
                ) from exc
        
        except openai.APIError as exc:
            raise LLMRequestError(
                f"OpenAI request failed: {exc}"
                ) from exc

    if LLM_PROVIDER == "anthropic":
        import anthropic

        try:
            client = _create_anthropic_client()
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=1000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                    ],
                )
            content = response.content[0].text
            if not content:
                raise LLMRequestError(
                    "Anthropic returned an empty response."
                    )
            return content

        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(
                "Anthropic request timed out."
                ) from exc
        
        except anthropic.APIError as exc:
            raise LLMRequestError(
                f"Anthropic request failed: {exc}"
                ) from exc

    raise LLMRequestError(f"Unsupported LLM provider: {LLM_PROVIDER}")