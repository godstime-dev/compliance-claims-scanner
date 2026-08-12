"""
Application configuration.

Loads all environment variables from .env and exposes them
through a single module for the rest of the application.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# LLM Configuration
LLM_PROVIDER = os.getenv(
    "LLM_PROVIDER",
    "openai"
    ).lower()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-4.1-mini"
    )

ANTHROPIC_MODEL = os.getenv(
    "ANTHROPIC_MODEL",
    "claude-3-5-sonnet-latest"
    )


# Application Configuration
REQUEST_TIMEOUT = int(
    os.getenv("REQUEST_TIMEOUT", 30)
    )

LLM_MAX_CONCURRENT_REQUESTS = int(
    os.getenv("LLM_MAX_CONCURRENT_REQUESTS", 5)
    )

USER_AGENT = os.getenv(
    "USER_AGENT",
    "ComplianceClaimsScanner/1.0"
    )


# Validation
if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY not found."
        )

if LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
    raise ValueError(
        "ANTHROPIC_API_KEY not found."
        )