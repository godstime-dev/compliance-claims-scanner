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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import logging

from app.config import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    REQUEST_TIMEOUT,
    LLM_MAX_CONCURRENT_REQUESTS,
    )
from app.scanner import ComplianceFinding

logger = logging.getLogger(__name__)

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


# Compliance Analysis Prompt
SYSTEM_PROMPT = """
You are a compliance screening assistant for a supplement
brand's marketing content.

Your job is to analyze a deterministic rule-based finding
in the context of the surrounding webpage text.

IMPORTANT:
The rule engine has already assigned the finding's severity
and confidence. Those values are deterministic and
authoritative.

You MUST NOT:
- Change the assigned severity.
- Change the assigned confidence.
- Assign a new severity.
- Assign a new confidence score.
- Dismiss or remove the rule-based finding.
- Provide legal advice.
- State that the content is definitively compliant or
  definitively illegal.

You SHOULD:
- Analyze what the flagged language means in context.
- Determine how the language is being used.
- Identify qualifying, hedging, or limiting language.
- Explain whether surrounding context changes how the
  finding should be interpreted.
- Identify whether the text appears to be a direct claim,
  qualified claim, comparative claim, incidental mention,
  or ambiguous.
- Provide a practical recommendation for human review.

The rule-based finding must remain visible and authoritative
in the final report. Your analysis is contextual enrichment,
not a replacement for the deterministic rule result.

The five allowed claim types are:

1. direct_claim
   The text appears to make a direct assertion about the
   product, its effects, or its ability.

2. qualified_claim
   The statement contains meaningful qualifying, conditional,
   cautious, or limiting language.

3. comparative_claim
   The statement compares the product or its effects to
   another product, drug, ingredient, treatment, or outcome.

4. incidental_mention
   The flagged term appears in a contextual, informational,
   historical, or otherwise non-claiming use.

5. ambiguous
   The available context is insufficient to confidently
   determine how the language is being used.

Be conservative. Do not invent facts that are not present
in the supplied text.

Return ONLY valid JSON matching the requested schema.
"""


def build_user_prompt(finding: ComplianceFinding) -> str:
    """
    Build the user prompt for a single compliance finding.

    The rule-assigned severity and confidence are included as
    reference information only. The LLM must not modify them.
    """

    return f"""
Analyze the following deterministic compliance finding.

RULE INFORMATION
Rule ID: {finding.rule_id}
Rule Name: {finding.rule_name}
Category: {finding.category}
Severity: {finding.severity}
Confidence: {finding.confidence}
Relevant Guidance: {finding.regulation}

MATCHED TEXT
{finding.matched_text}

SURROUNDING CONTEXT
{finding.context}

Provide a structured analysis using exactly these JSON fields:

{{
    "claim_type": "direct_claim | qualified_claim | comparative_claim | incidental_mention | ambiguous",
    "contextual_explanation": "Explain how the flagged language is being used in context.",
    "hedging_detected": true or false (boolean, based on whether qualifying/limiting language is genuinely present),
    "qualification_notes": "Describe any meaningful qualifying or limiting language. Use an empty string if none is present.",
    "review_recommendation": "Provide a practical recommendation for human compliance review."
}}

"claim_type" must be exactly one of the five values listed
above (direct_claim, qualified_claim, comparative_claim,
incidental_mention, or ambiguous), written exactly as shown,
with no additional words or explanation in that field.

Remember:
- Do not change the rule's severity.
- Do not change the rule's confidence.
- Do not create a new severity or confidence score.
- Do not dismiss the deterministic finding.
- Do not provide legal advice.
- Base the analysis only on the supplied text.
"""


# LLM Response Parsing
def _parse_llm_response(response_text: str) -> LLMAnalysis:
    """
    Parse and validate the raw LLM response.

    Args:
        response_text: Raw JSON response returned by the LLM.

    Returns:
        A validated LLMAnalysis instance.

    Raises:
        LLMRequestError: If the response is invalid or malformed.
    """

    try:
        data = json.loads(response_text)

    except json.JSONDecodeError as exc:
        raise LLMRequestError(
            "LLM returned invalid JSON."
            ) from exc

    if not isinstance(data, dict):
        raise LLMRequestError(
            "LLM response must be a JSON object."
            )

    required_fields = {
        "claim_type",
        "contextual_explanation",
        "hedging_detected",
        "qualification_notes",
        "review_recommendation",
        }

    missing_fields = required_fields - data.keys()

    if missing_fields:
        raise LLMRequestError(
            f"LLM response is missing required fields: "
            f"{', '.join(sorted(missing_fields))}"
            )

    try:
        claim_type = ClaimType(data["claim_type"])

    except ValueError as exc:
        raise LLMRequestError(
            f"Invalid claim type returned by LLM: "
            f"{data['claim_type']}"
            ) from exc

    if not isinstance(data["hedging_detected"], bool):
        raise LLMRequestError(
            "hedging_detected must be a boolean."
            )

    if not isinstance(data["contextual_explanation"],str):
        raise LLMRequestError(
            "contextual_explanation must be a string."
            )

    if not data["contextual_explanation"].strip():
        raise LLMRequestError(
            "contextual_explanation must not be empty."
            )

    if not isinstance(data["qualification_notes"],str,):
        raise LLMRequestError(
            "qualification_notes must be a string."
            )

    if not isinstance(data["review_recommendation"],str,):
        raise LLMRequestError(
            "review_recommendation must be a string."
            )

    return LLMAnalysis(
        claim_type=claim_type,
        contextual_explanation=data["contextual_explanation"].strip(),
        hedging_detected=data["hedging_detected"],
        qualification_notes=data["qualification_notes"].strip(),
        review_recommendation=data["review_recommendation"].strip(),
        )


# Single-Finding Analysis
def analyze_finding(
    finding: ComplianceFinding,
    ) -> Optional[LLMAnalysis]:
    """
    Analyze a single deterministic compliance finding with the LLM.

    The original ComplianceFinding is never modified. In particular,
    its rule-assigned severity and confidence remain unchanged.

    Args:
        finding: Deterministic finding produced by scanner.py.

    Returns:
        LLMAnalysis when the LLM analysis succeeds.
        None when the LLM is unavailable or the response cannot
        be processed.
    """

    system_prompt = SYSTEM_PROMPT
    user_prompt = build_user_prompt(finding)

    try:
        response_text = _call_provider(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            )

        return _parse_llm_response(response_text)

    except LLMTimeoutError as exc:
        logger.warning(f"LLM analysis timed out for {finding.rule_id}: {exc}")
        return None

    except LLMRequestError as exc:
        logger.warning(f"LLM analysis failed for {finding.rule_id}: {exc}")
        return None


# Batch Finding Analysis
def analyze_findings(
    findings: List[ComplianceFinding],
    max_workers: int = LLM_MAX_CONCURRENT_REQUESTS,
    ) -> List[Tuple[ComplianceFinding, Optional[LLMAnalysis]]]:
    """
    Analyze multiple compliance findings concurrently.

    Each finding is analyzed independently via its own LLM call.
    Calls are fired in parallel using a thread pool, since each
    call is I/O-bound (waiting on network) rather than CPU-bound.
    A failure for one finding does not affect the others.

    The original ComplianceFinding objects are never modified.
    Input order is preserved in the returned results, regardless
    of the order in which individual calls complete.

    Args:
        findings: Deterministic findings produced by scanner.py.
        max_workers: Maximum number of concurrent LLM calls.

    Returns:
        A list of tuples containing each original finding and
        its optional LLM analysis.

        If analysis fails for a finding, the corresponding
        LLMAnalysis value is None.
    """

    if not findings:
        return []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        analyses = list(executor.map(analyze_finding, findings))

    return list(zip(findings, analyses))