"""
Website crawler for the compliance claims scanner.

Discover a set of crawl-eligible pages starting from one URL,
respecting robots.txt and rate limits, using sitemap-based
discovery as the primary mechanism.

This module does NOT:
- Extract visible text (cleaner.py handles that)
- Run compliance rule (scanner.py handles that)
- Call an LLM
- Generate reports

Its responsibility is limited to discovering which URLs on a
site are safe and worthwhile to crawl(browse).
"""

import re

from dataclasses import dataclass
from urllib.parse import(
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
    )

class CrawlerError(Exception):
    """Base exception for crawler-related failures."""


"""
Only standard http and https links are supported for crawling. 
Anything else (mailto:, tel:, javascript:, ftp:, data:, etc.)
is rejected before normalization even attempts to process it.
"""
SUPPORTED_SCHEMES = ("http", "https")


# Default web ports to strip out during link standardization.
DEFAULT_PORTS = {
    "http": "80",
    "https": "443"
    }

"""
Query parameters known to be tracking noise/marketing clutter
that do not change the actual content of the page. Safe to remove
under that "syntactic, not semantic" normalization principle.
"""
TRACKING_PARAMETERS = frozenset({
    "fbclid",
    "gclid,"
    "msclkid",
    "mc_cid",
    "mc_eid",
    })

TRACKING_PREFIXES = ("utm_",)

# Safe letters, numbers, and basic symbols that can be decoded without breaking a URL.
# Structural symbols are skipped to prevent creating broken links.
_UNRESERVED_PATTERN = re.compile(r"[A-za-z0-9\-._⁓]")


@dataclass(frozen=True)
class NormalizedUrl:
    """
    A fixed template for a perfectly cleaned web address.

    Two URLs normalizing into the exact same value are
    considered the same page and will not be scanned twice.
    """
    value: str


def _is_supported_scheme(scheme: str) -> bool:
    """
    Check whether a URL scheme is one the crawler
    is willing to fetch (http or https only).
    """
    return scheme.lower() in SUPPORTED_SCHEMES


def _is_tracking_parameter(name: str) -> bool:
    """
    Identify if a query parameter is a marketing tracker or ad-attribution tag.
    """
    normalized_name = name.lower()

    if normalized_name in TRACKING_PARAMETERS:
        return True

    return normalized_name.startswith(TRACKING_PREFIXES)