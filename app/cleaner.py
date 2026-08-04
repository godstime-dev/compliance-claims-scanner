"""
HTML cleaning service.

Responsible for extracting visible text from raw HTML.

This module does NOT:
- Fetch webpages
- Perform compliance analysis
- Call an LLM

It only converts HTML into clean, readable text.
"""

import re

from bs4 import BeautifulSoup, Comment


class CleanerError(Exception):
    """Base exception for HTML cleaning errors."""


class InvalidHTMLError(CleanerError):
    """Raised when invalid HTML is provided."""


# HTML elements that should not contribute to compliance analysis.
#
# NOTE:
# We intentionally DO NOT remove <header> or <footer>. Many supplement
# brands place key marketing claims, hero copy, guarantees, or regulatory
# disclaimers inside these sections.
REMOVABLE_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "form",
    "aside",
    )


def _remove_unwanted_tags(soup: BeautifulSoup) -> None:
    """
    Remove HTML elements that should not contribute
    to compliance analysis.
    """

    for tag in REMOVABLE_TAGS:
        for element in soup.find_all(tag):
            element.decompose()


def _remove_comments(soup: BeautifulSoup) -> None:
    """
    Remove HTML comments.

    Comments are not visible to users and should not
    be included in compliance analysis.
    """

    comments = soup.find_all(
        string=lambda text: isinstance(text, Comment)
        )

    for comment in comments:
        comment.extract()


def _normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace while preserving paragraph breaks.
    """

    # Remove trailing spaces before newlines
    text = re.sub(r"[ \t]+\n", "\n", text)

    # Collapse multiple spaces/tabs into one
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_visible_text(html: str) -> str:
    """
    Extract visible text from raw HTML.

    Args:
        html: Raw HTML string.

    Returns:
        Clean, human-readable text.

    Raises:
        InvalidHTMLError:
            If HTML is empty or invalid, or if no visible text could be extracted.
    """

    if not html:
        raise InvalidHTMLError(
            "HTML content cannot be empty."
            )

    if not isinstance(html, str):
        raise InvalidHTMLError(
            "HTML content must be a string."
            )

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:
        raise InvalidHTMLError(
            "Failed to parse HTML."
            ) from exc

    _remove_unwanted_tags(soup)
    _remove_comments(soup)

    text = soup.get_text(
        separator="\n",
        strip=True,
        )

    text = _normalize_whitespace(text)

    if not text:
        raise InvalidHTMLError(
            "No visible text could be extracted from the HTML."
            )

    return text