"""
Compliance rule library.

Defines the rule model and the built-in FDA/FTC compliance
rules used by the scanner.

This module does NOT:
- Scan webpage content
- Call an LLM
- Calculate compliance scores

It only defines reusable compliance rules and supporting
constants.
"""

import re
from enum import Enum
from typing import Dict

from dataclasses import dataclass
from typing import List


# Ruleset Metadata
RULESET_VERSION = "1.0.0"


# Severity Levels
class Severity(Enum):
    """
    Indicates the potential regulatory impact of a matched rule.
    """

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"



# Confidence Levels
class Confidence(Enum):
    """
    Indicates how reliable a rule match is expected to be.

    NOTE:
    This is NOT a statistical confidence score. It reflects
    the specificity of the rule itself. For example, a direct
    disease-treatment claim is inherently more reliable than
    a broad advertising phrase.
    """

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# Regex Proximity Windows
PROXIMITY: Dict[str, int] = {
    # Short marketing phrases
    "SHORT": 30,

    # Typical supplement marketing copy
    "MEDIUM": 60,

    # Longer explanatory sentences
    "LONG": 100,
    }


@dataclass(frozen=True)
class ComplianceRule:
    """
    Represents a single compliance rule used by the scanner.

    Each rule defines:
    - What type of claim to detect.
    - The regex patterns used for detection.
    - The regulatory guidance associated with the claim.
    - The severity and confidence assigned to matches.

    Rules are immutable after creation.
    """

    
    # Rule Identification
    id: str
    name: str
    category: str

    
    # Compliance Metadata
    severity: Severity
    confidence: Confidence

    regulation: str

    
    # User-Facing Information
    explanation: str
    recommendation: str

    
    # Detection Logic
    patterns: List[str]

# SHARED VOCABULARY
# Disease Claim Verbs
CLAIM_VERBS = [
    "cure",
    "treat",
    "heal",
    "fight",
    ]

# Diseases & Medical Conditions
DISEASE_TERMS = [
    "diabetes",
    "prediabetes",
    "arthritis",
    "osteoarthritis",
    "cancer",
    "heart disease",
    "cardiovascular disease",
    "high blood pressure",
    "hypertension",
    "obesity",
    "alzheimer",
    "parkinson",
    "depression",
    "anxiety disorder",
    ]

COMMON_ILLNESS_TERMS = [
    "flu",
    "covid",
    "virus",
    "infection"
    ]

# Symptoms & Health Conditions
SYMPTOM_TERMS = [
    "inflammation",
    "chronic inflammation",
    "joint pain",
    "back pain",
    "muscle pain",
    "blood sugar",
    "cholesterol",
    "insomnia",
    "fatigue",
    "brain fog",
    "memory loss",
    "cognitive decline",
    "immune system",
    "gut health",
    "digestive health",
    ]

# Weight-Loss Language
WEIGHT_LOSS_TERMS = [
    "weight loss",
    "lose weight",
    "burn fat",
    "fat burning",
    "fat burner",
    "melt fat",
    "shred fat",
    "drop pounds",
    "rapid weight loss",
    "instant weight loss",
    "belly fat",
    "stubborn fat",
    ]

CORE_WEIGHT_TERMS = [
    "weight loss",
    "lose weight",
    "fat loss",
    "burn fat",
    "melt fat",
    ]

# GLP-1 & Prescription Drug References
GLP1_TERMS = [
    "glp-1",
    "glp1",
    "ozempic",
    "wegovy",
    "mounjaro",
    "zepbound",
    "semaglutide",
    "tirzepatide",
    "natural ozempic",
    ]

# Absolute / Definitive Marketing Language
ABSOLUTE_TERMS = [
    "scientifically proven",
    "clinically proven",
    "proven to work",
    "works every time",
    "100% effective",
    "instant results",
    "permanent results",
    ]

CONTEXTUAL_ABSOLUTE_TERMS = ["guaranteed",]


# Regex Fragment Builders
def _build_word_pattern(words: list[str]) -> str:
    """
    Build a regex alternation from literal words or phrases.

    Each term is escaped before being added to the pattern so
    that regex-special characters inside vocabulary terms are
    treated as literal characters.
    """

    escaped = [
        re.escape(word)
        for word in words
    ]

    return "(?:" + "|".join(escaped) + ")"


def _build_verb_pattern(verbs: list[str]) -> str:
    """
    Build a regex pattern that matches common English verb forms.

    Handles common forms such as:
        treat -> treat, treats, treated, treating
        eliminate -> eliminate, eliminates, eliminated, eliminating
    """

    patterns = []

    for verb in verbs:
        escaped_verb = re.escape(verb)

        if verb.endswith("e"):
            ing_form = re.escape(verb[:-1] + "ing")
        else:
            ing_form = rf"{escaped_verb}ing"

        patterns.append(
            rf"{escaped_verb}"
            rf"(?:s|ed)?"
            rf"|{ing_form}"
        )

    return "(?:" + "|".join(patterns) + ")"


def _build_flexible_phrase_pattern(
    phrases: list[str],
    max_gap: int = 20,
    ) -> str:
    """
    Build a regex pattern for multi-word phrases.

    Allows a limited amount of text between words.

    Example:
        "melt fat"

    Can match:
        "melt fat"
        "melt away fat"
        "melts stubborn fat"
        "melt away stubborn fat"
    """

    patterns = []

    for phrase in phrases:
        words = phrase.split()

        if len(words) == 1:
            patterns.append(
                re.escape(words[0])
            )
            continue

        escaped_words = [
            re.escape(word)
            for word in words
        ]

        pattern = rf".{{0,{max_gap}}}".join(escaped_words)

        patterns.append(pattern)

    return "(?:" + "|".join(patterns) + ")"


# Shared Regex Fragments
CLAIM_VERB_PATTERN = _build_verb_pattern(
    CLAIM_VERBS
    )

PREVENT_PATTERN = _build_verb_pattern(["prevent"])

REVERSE_PATTERN = _build_verb_pattern(["reverse"])

ELIMINATE_PATTERN = _build_verb_pattern(["eliminate"])

DISEASE_PATTERN = _build_word_pattern(
    DISEASE_TERMS
    )

SYMPTOM_PATTERN = _build_word_pattern(
    SYMPTOM_TERMS
    )

COMMON_ILLNESS_PATTERN = _build_verb_pattern(COMMON_ILLNESS_TERMS)

HEALTH_PATTERN = "(?:" + "|".join([DISEASE_PATTERN, SYMPTOM_PATTERN]) + ")"

WEIGHT_PATTERN = _build_flexible_phrase_pattern(
    WEIGHT_LOSS_TERMS,
    max_gap=20,
    )

CORE_WEIGHT_PATTERN = _build_flexible_phrase_pattern(
    CORE_WEIGHT_TERMS,
    max_gap=20,
    )

GLP1_PATTERN = _build_word_pattern(
    GLP1_TERMS
    )

ABSOLUTE_PATTERN = _build_flexible_phrase_pattern(
    ABSOLUTE_TERMS,
    max_gap=20,
    )


# Disease Claim Rules
DISEASE_CLAIM_RULES = [

    ComplianceRule(
        id="FDA001",
        name="Disease Treatment Claim",
        category="Disease Claims",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FDA DSHEA - Disease Claims",
        explanation=(
            "The claim appears to represent the supplement as "
            "treating, curing, healing, reversing, or eliminating "
            "a disease or health condition."
            ),
        recommendation=(
            "Review the claim and consider replacing disease-"
            "treatment language with an appropriate "
            "structure/function claim."
            ),
        patterns=[
            rf"\b{CLAIM_VERB_PATTERN}\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            rf"\b{HEALTH_PATTERN}\b",

            rf"\b{HEALTH_PATTERN}\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            rf"\b{CLAIM_VERB_PATTERN}\b",
            ],
        ),

    ComplianceRule(
        id="FDA002",
        name="Disease Prevention Claim",
        category="Disease Claims",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FDA DSHEA - Disease Claims",
        explanation=(
            "The claim appears to represent the supplement "
            "as preventing a disease or medical condition."
            ),
        recommendation=(
            "Review the claim and consider whether it can be "
            "rephrased as a permissible structure/function claim."
            ),
        patterns=[
            rf"\b{PREVENT_PATTERN}\b"
            rf".{{0,{PROXIMITY['LONG']}}}"
            rf"\b{HEALTH_PATTERN}\b",

            rf"\b{HEALTH_PATTERN}\b"
            rf".{{0,{PROXIMITY['LONG']}}}"
            rf"\b{PREVENT_PATTERN}\b",
            ],
        ),

    ComplianceRule(
        id="FDA003",
        name="Disease Reversal Claim",
        category="Disease Claims",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FDA DSHEA - Disease Claims",
        explanation=(
            "The claim appears to represent the supplement "
            "as reversing or eliminating a disease or health condition."
            ),
        recommendation=(
            "Review the claim and remove or revise disease-reversal "
            "language unless the claim has been appropriately "
            "substantiated and reviewed."
            ),
        patterns=[
            rf"\b{REVERSE_PATTERN}\b"
            rf".{{0,{PROXIMITY['LONG']}}}"
            rf"\b({HEALTH_PATTERN})\b",

            rf"\b{ELIMINATE_PATTERN}\b"
            rf".{{0,{PROXIMITY['LONG']}}}"
            rf"\b({HEALTH_PATTERN})\b",

            rf"\b({HEALTH_PATTERN})\b"
            rf".{{0,{PROXIMITY['LONG']}}}"
            rf"\b(?:{REVERSE_PATTERN}|{ELIMINATE_PATTERN})\b",
            ],
        ),

    ComplianceRule(
        id="FDA004",
        name="Common Illness Claim",
        category="Disease Claims",
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        regulation="FDA DSHEA - Disease Claims",
        explanation=(
            "The claim appears to closely associate the supplement "
            "with treating, curing, or preventing a common illness "
            "such a flu, COVID, or a viral infection. This term is "
            "also common in unrelated marketing copy, so review is "
            "recommended before treating this as a confirmed violation."
            ),
        recommendation=(
            "Review the surrounding context. If this describes immune "
            "support language rather than a direct treatment claim, "
            "it may be compliant as a structure/function claim."
            ),
        patterns=[
            rf"\b{CLAIM_VERB_PATTERN}\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{COMMON_ILLNESS_PATTERN}\b",

            rf"\b{COMMON_ILLNESS_PATTERN}\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{CLAIM_VERB_PATTERN}\b",

            rf"\b{PREVENT_PATTERN}\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{COMMON_ILLNESS_PATTERN}\b",

            rf"\b{ELIMINATE_PATTERN}\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{COMMON_ILLNESS_PATTERN}\b",
            
            rf"\b{REVERSE_PATTERN}\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{COMMON_ILLNESS_PATTERN}\b",
            ],
        )
    ]


# Weight-Loss Claim Rules
WEIGHT_LOSS_CLAIM_RULES = [

    ComplianceRule(
        id="FTC001",
        name="Weight-Loss Efficacy Claim",
        category="Weight Loss",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Compliance Guidance",
        explanation=(
            "The claim appears to promise or directly imply "
            "weight loss or fat loss as a result of using the product."
            ),
        recommendation=(
            "Review the claim and ensure any weight-loss or "
            "fat-loss representation is supported by appropriate "
            "scientific evidence."
            ),
        patterns=[
            rf"\b{WEIGHT_PATTERN}\b",
            ],
        ),

    ComplianceRule(
        id="FTC002",
        name="Rapid Weight-Loss Claim",
        category="Weight Loss",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Compliance Guidance",
        explanation=(
            "The claim appears to promise unusually rapid or "
            "immediate weight loss."
            ),
        recommendation=(
            "Review the claim and avoid implying rapid or "
            "immediate weight loss unless the representation "
            "is appropriately substantiated."
            ),
        patterns=[
            r"\brapid\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{CORE_WEIGHT_PATTERN}\b",

            r"\binstant\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{CORE_WEIGHT_PATTERN}\b",

            r"\b(fast|quick)\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{CORE_WEIGHT_PATTERN}\b",
            ],
        ),

    ComplianceRule(
        id="FTC003",
        name="Specific Weight-Loss Result Claim",
        category="Weight Loss",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Compliance Guidance",
        explanation=(
            "The claim appears to promise a specific amount "
            "of weight loss or a specific fat-loss result."
        ),
        recommendation=(
            "Review the claim and verify that any specific "
            "weight-loss representation is supported by "
            "appropriate evidence."
        ),
        patterns=[
            r"\blose\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            r"\b\d+(?:\.\d+)?\s*"
            r"(?:lbs?|pounds?|kg|kilograms?)\b",

            r"\b\d+(?:\.\d+)?\s*"
            r"(?:lbs?|pounds?|kg|kilograms?)\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{CORE_WEIGHT_PATTERN}\b",
        ],
    ),

    ComplianceRule(
        id="FTC004",
        name="Guaranteed Weight-Loss Claim",
        category="Weight Loss",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Compliance Guidance",
        explanation=(
            "The claim appears to guarantee a weight-loss "
            "or fat-loss result."
        ),
        recommendation=(
            "Review and remove guaranteed-result language "
            "unless the representation can be appropriately "
            "substantiated."
        ),
        patterns=[
            r"\bguarantee(?:d|s)?\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            rf"\b{CORE_WEIGHT_PATTERN}\b",

            rf"\b{CORE_WEIGHT_PATTERN}\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            r"\bguarantee(?:d|s)?\b",
        ],
    ),
]


# GLP-1 / Drug Comparison Claim Rules
GLP1_CLAIM_RULES = [

    ComplianceRule(
        id="FTC010",
        name="GLP-1 Drug Comparison Claim",
        category="Drug Comparisons",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Advertising Principles",
        explanation=(
            "The claim directly compares the supplement to a "
            "prescription weight-loss medication or GLP-1 drug."
            ),
        recommendation=(
            "Review the comparison and ensure that any "
            "representation about equivalence, superiority, "
            "or comparable effects is appropriately substantiated."
            ),
        patterns=[
            rf"\b{GLP1_PATTERN}\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            r"\b(?:alternative|replacement|substitute|"
            r"equivalent|similar|same|better|stronger|"
            r"works\s+like|works\s+as)\b",

            r"\b(?:alternative|replacement|substitute|"
            r"equivalent|similar|same|better|stronger|"
            r"works\s+like|works\s+as)\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            rf"\b{GLP1_PATTERN}\b",
            ],
        ),

    ComplianceRule(
        id="FTC011",
        name="Natural GLP-1 Drug Substitute Claim",
        category="Drug Comparisons",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Advertising Principles",
        explanation=(
            "The claim appears to position the supplement as a "
            "natural substitute or alternative to a prescription "
            "GLP-1 medication."
            ),
        recommendation=(
            "Review and reconsider language positioning the "
            "supplement as a natural replacement for a prescription "
            "drug."
            ),
        patterns=[
            rf"\bnatural\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{GLP1_PATTERN}\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            r"\b(?:alternative|replacement|substitute)\b",

            r"\b(?:alternative|replacement|substitute)\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            r"\bnatural\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{GLP1_PATTERN}\b",

            rf"\bnatural\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            r"\b(?:alternative|replacement|substitute)\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            rf"\b{GLP1_PATTERN}\b",
            ],
        ),

    ComplianceRule(
        id="FTC012",
        name="GLP-1 Effect Claim",
        category="Drug Comparisons",
        severity=Severity.HIGH,
        confidence=Confidence.MEDIUM,
        regulation="FTC Health Products Advertising Principles",
        explanation=(
            "The claim appears to associate the supplement with "
            "the effects or mechanism of a GLP-1 medication."
            ),
        recommendation=(
            "Review claims implying that the product produces "
            "prescription-drug-like GLP-1 effects and verify "
            "appropriate substantiation."
            ),
        patterns=[
            rf"\b({GLP1_PATTERN})\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            r"\b(?:same\s+(?:effects?|results?)|"
            r"similar\s+(?:effects?|results?)|"
            r"results\s+without|results\s+like|"
            r"works\s+the\s+same)\b",

            r"\b(?:same\s+(?:effects?|results?)|"
            r"similar\s+(?:effects?|results?)|"
            r"results\s+without|results\s+like|"
            r"works\s+the\s+same)\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            rf"\b{GLP1_PATTERN}\b",
            ],
        ),
    ]


# Absolute / Unsubstantiated Advertising Claim Rules
ADVERTISING_CLAIM_RULES = [

    ComplianceRule(
        id="FTC020",
        name="Guaranteed Result Claim",
        category="Advertising Claims",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Advertising Principles",
        explanation=(
            "The claim appears to guarantee a specific product "
            "result or outcome."
            ),
        recommendation=(
            "Review the claim and ensure that any guaranteed "
            "result is supported by appropriate evidence. "
            "Consider using qualified language where appropriate."
            ),
        patterns=[
            rf"\b{ABSOLUTE_PATTERN}\b",
            ],
        ),

    ComplianceRule(
        id="FTC021",
        name="Scientific Proof Claim",
        category="Advertising Claims",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Advertising Principles",
        explanation=(
            "The claim presents the product or its effects as "
            "scientifically or clinically proven."
            ),
        recommendation=(
            "Verify that the claim is supported by competent "
            "and reliable scientific evidence and that the "
            "evidence supports the specific representation being made."
            ),
        patterns=[
            r"\bscientifically\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            r"\b(?:proven|validated|confirmed)\b",

            r"\bclinically\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            r"\b(?:proven|validated|confirmed|guaranteed)\b",

            r"\b(?:proven|validated|confirmed)\b"
            rf".{{0,{PROXIMITY['SHORT']}}}"
            r"\b(?:to\s+cure|to\s+treat|to\s+eliminate|to\s+reverse)\b",
            ],
        ),

    ComplianceRule(
        id="FTC022",
        name="No Side Effects Claim",
        category="Advertising Claims",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        regulation="FTC Health Products Advertising Principles",
        explanation=(
            "The claim appears to represent the product as "
            "having no side effects or risks."
            ),
        recommendation=(
            "Review absolute safety language and verify that "
            "the representation is appropriately supported."
            ),
        patterns=[
            r"\bno\s+side\s+effects\b",
            r"\bzero\s+side\s+effects\b",
            r"\bside[- ]effect[- ]free\b",
            r"\bcompletely\s+safe\b",
            r"\b100%\s+safe\b",
            ],
        ),

    ComplianceRule(
        id="FTC023",
        name="Miracle or Guaranteed-Efficacy Claim",
        category="Advertising Claims",
        severity=Severity.MEDIUM,
        confidence=Confidence.MEDIUM,
        regulation="FTC Health Products Advertising Principles",
        explanation=(
            "The claim uses absolute or extraordinary language "
            "that may imply guaranteed or exceptional product efficacy."
            ),
        recommendation=(
            "Review the claim and verify that the representation "
            "is appropriately substantiated. Consider replacing "
            "absolute language with a more specific and supportable claim."
            ),
        patterns=[
            r"\bmiracle\s+(?:product|supplement|formula|pill|solution)\b",

            r"\bmagic\s+(?:pill|supplement|formula|solution)\b",

            r"\bguarantee(?:d|s)?\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            r"\b(?:results|success|effective|efficacy|benefits)\b",

            r"\b(?:results|success|effective|efficacy|benefits)\b"
            rf".{{0,{PROXIMITY['MEDIUM']}}}"
            r"\bguarantee(?:d|s)?\b",
            ],
        ),
    ]


# Rules Registry
RULES = [
    *DISEASE_CLAIM_RULES,
    *WEIGHT_LOSS_CLAIM_RULES,
    *GLP1_CLAIM_RULES,
    *ADVERTISING_CLAIM_RULES,
    ]

_rule_ids = [rule.id for rule in RULES]
assert len(_rule_ids) == len(set(_rule_ids)), (
    f"Duplicate rule IDs found in RULES: "
    f"{[rid for rid in _rule_ids if _rule_ids.count(rid) > 1]}")