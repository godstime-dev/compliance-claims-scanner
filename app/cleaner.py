"""
HTML cleaning service.

Responsible for extracting visible text from raw HTML.

This module does NOT:
- Fetch webpages
- Perform compliance analysis
- Call an LLM

It only converts HTML into clean, readable text. Text from
distinct structural elements (headings, buttons, paragraphs,
list items, etc.) is separated by newlines in the output, so
downstream consumers (scanner.py's context extraction) can tell
where one element's text ends and an unrelated one begins.
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

# Structural block-level tags that should be treated as separate
# lines in the extracted text, so unrelated content (e.g. a
# section heading and a nearby question) never gets glued
# together into one run-on line.
BLOCK_TAGS = (
    "p", "div", "li", "td", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "br", "summary", "button",
    )

# Common storefront UI noise that survives text extraction but
# is not marketing/compliance-relevant copy.
NOISE_PREFIXES = (
    "SHOP ALL",
    "ADD TO CART",
    "BUY NOW",
    "VIEW CART",
    "LOG IN",
    "CHECKOUT",
    )

# Matches short strings made entirely of common icon/symbol
# glyphs (accordion toggles, arrows, bullets) so they don't
# get pulled into extracted text as if they were words.
_ICON_ONLY_PATTERN = re.compile(
    r"^[+\-\u00d7\u2715\u2716\u25b6\u25bc\u203a\u2039»«•·]{1,3}$"
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
    Remove HTML comments. Comments are not visible to users and
    should not be included in compliance analysis.
    """
    comments = soup.find_all(
        string=lambda text: isinstance(text, Comment)
        )
    for comment in comments:
        comment.extract()


def _remove_icon_only_elements(soup: BeautifulSoup) -> None:
    """
    Remove elements whose entire text content is a short run of
    icon/symbol characters (e.g. a "+" accordion toggle), which
    would otherwise be extracted as if it were real content.
    """
    for element in soup.find_all(True):
        text = element.get_text(strip=True)
        if text and _ICON_ONLY_PATTERN.match(text) and not element.find(True):
            element.decompose()


def _insert_block_boundaries(soup: BeautifulSoup) -> None:
    """
    Append a newline marker after each structural block-level
    element, so distinct sections of the page (a heading, a
    button's label, a paragraph) remain separated as individual
    lines once text is extracted, rather than being flattened
    into one continuous run of text.
    """
    for block_tag in soup.find_all(list(BLOCK_TAGS)):
        block_tag.append("\n")


def extract_visible_text(html: str) -> str:
    """
    Extract visible text from raw HTML.

    Distinct structural elements are separated by newlines in
    the returned text. Whitespace within each line is normalized,
    and lines matching common storefront UI noise are dropped.

    Args:
        html: Raw HTML string.

    Returns:
        Clean, human-readable text, with structural elements
        separated by newlines.

    Raises:
        InvalidHTMLError:
            If HTML is empty or invalid, or if no visible text
            could be extracted.
    """

    if not html:
        raise InvalidHTMLError("HTML content cannot be empty.")

    if not isinstance(html, str):
        raise InvalidHTMLError("HTML content must be a string.")

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as exc:
        raise InvalidHTMLError("Failed to parse HTML.") from exc

    _remove_unwanted_tags(soup)
    _remove_comments(soup)
    _remove_icon_only_elements(soup)
    _insert_block_boundaries(soup)

    raw_text = soup.get_text(separator=" ")

    clean_lines = []
    for line in raw_text.split("\n"):
        trimmed = line.strip()

        if not trimmed:
            continue

        if trimmed.upper().startswith(NOISE_PREFIXES):
            continue

        normalized_line = " ".join(trimmed.split())
        clean_lines.append(normalized_line)

    # Joined with newlines, NOT spaces — this preserves the
    # element-boundary information that scanner.py's context
    # extraction relies on to avoid gluing unrelated elements
    # together. Whitespace collapsing for display happens later,
    # scoped to a single context window, not globally here.
    final_text = "\n".join(clean_lines)

    if not final_text:
        raise InvalidHTMLError(
            "No visible text could be extracted from the HTML."
            )

    return final_text