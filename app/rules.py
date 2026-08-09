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
    "prevent",
    "reverse",
    "heal",
    "eliminate",
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
    "infection",
    "virus",
    "flu",
    "covid",
    "alzheimer",
    "parkinson",
    "depression",
    "anxiety disorder",
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
    "guaranteed",
    "scientifically proven",
    "clinically proven",
    "proven to work",
    "works every time",
    "100% effective",
    "no side effects",
    "miracle",
    "instant results",
    "permanent results",
    ]


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

DISEASE_PATTERN = _build_word_pattern(
    DISEASE_TERMS
    )

SYMPTOM_PATTERN = _build_word_pattern(
    SYMPTOM_TERMS
    )

HEALTH_PATTERN = "(?:" + "|".join([DISEASE_PATTERN, SYMPTOM_PATTERN]) + ")"

WEIGHT_PATTERN = _build_flexible_phrase_pattern(
    WEIGHT_LOSS_TERMS,
    max_gap=20,
    )

GLP1_PATTERN = _build_word_pattern(
    GLP1_TERMS
    )

ABSOLUTE_PATTERN = _build_flexible_phrase_pattern(
    ABSOLUTE_TERMS,
    max_gap=20,
    )