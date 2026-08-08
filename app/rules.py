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
