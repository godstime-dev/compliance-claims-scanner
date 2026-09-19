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
import time
import requests

from dataclasses import dataclass
from urllib.parse import(
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
    )

from requests.exceptions import RequestException
from urllib.robotparser import RobotFileParser

class CrawlerError(Exception):
    """
    Base exception for crawler-related failures.
    """


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
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    })

TRACKING_PREFIXES = ("utm_",)

# Safe letters, numbers, and basic symbols that can be decoded without breaking a URL.
# Structural symbols are skipped to prevent creating broken links.
_UNRESERVED_PATTERN = re.compile(r"[A-za-z0-9\-._⁓]")


@dataclass(frozen=True)
class NormalizedURL:
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


def _normalize_percent_encoding(component: str) -> str:
    """
    Normalize percent-encoding within a URL path or query component.

    Unreserved ASCII characters (letters, digits, '-', '.', '_', '~')
    are safely decoded back to their literal form.

    NOTE: Multi-byte UTF-8 sequences (e.g., non-ASCII characters like '%c3%a9') 
    will trigger a UnicodeDecodeError inside the single-triplet regex loop. 
    The fallback safely leaves them encoded and standardizes them to uppercase hex.
    """
    def _decode_if_unreserved(match: "re.Match") -> str:
        hex_digits = match.group(1)

        try:
            decode_char = bytes.fromhex(hex_digits).decode(
                "utf-8", errors="strict"
                )
        except (ValueError, UnicodeDecodeError):
            return f"%{hex_digits.upper()}"

        if _UNRESERVED_PATTERN.fullmatch(decode_char):
            return decode_char

        return f"%{hex_digits.upper()}"

    return re.sub(
        r"%([0-9A-Fa-f]{2})",
        _decode_if_unreserved,
        component,
        )

def _normalize_query(query: str) -> str:
    """
    Remove known tracking parameters, preserve all other
    parameters, and sort any other parameter for a
    consistent canonical ordering.

    Query encoding is handled entirely by parse_qsl/urlencode
    here, rather than pre-processing with
    _normalize_percent_encoding(), since running both would
    double-process the same encoded values in potentially
    conflicting ways.
    """
    if not query:
        return ""

    pairs = parse_qsl(query, keep_blank_values=True)

    filtered_pairs = [
        (key, value)
        for key, value in pairs
        if not _is_tracking_parameter(key)
        ]

    filtered_pairs.sort(key=lambda pair: (pair[0], pair[1]))

    return urlencode(filtered_pairs)


def normalize_url(raw_url: str) -> NormalizedURL:
    """
    Produce a canonical representation of a URL.

    Normalization removes syntactic differences that are safely
    known not to affect the resource (fragment, default port,
    hostname casing, tracking parameters, parameter ordering,
    percent-encoding style), but preserves differences whose
    semantic meaning cannot be determined reliably without
    fetching the URL (path casing, trailing slash, www vs
    non-www, http vs https, and any non-tracking query
    parameter).

    This function only produces a canonical URL string — it does
    not decide whether the URL is internal, robots-allowed, or
    otherwise worth crawling. Those are separate, later checks.

    Args:
        raw_url: A URL as discovered from a sitemap or page.

    Returns:
        A NormalizedURL wrapping the canonical string form.

    Raises:
        CrawlerError: If the URL cannot be parsed, uses an
            unsupported scheme, has no hostname, or has a
            malformed port.
    """

    if not raw_url or not raw_url.strip():
        raise CrawlerError("URL cannot be empty.")

    try:
        parts = urlsplit(raw_url.strip())
    except ValueError as exc:
        raise CrawlerError(f"Could not parse URL: {raw_url}") from exc

    if not _is_supported_scheme(parts.scheme):
        raise CrawlerError(
            f"Unsupported URL scheme "
            f"'{parts.scheme or '(none)'}': {raw_url}"
            )

    if not parts.hostname:
        raise CrawlerError(f"URL has no hostname: {raw_url}")

    try:
        port = parts.port
    except ValueError as exc:
        raise CrawlerError(f"Invalid port in URL: {raw_url}") from exc

    scheme = parts.scheme.lower()
    hostname = parts.hostname.lower()

    if port is not None and str(port) == DEFAULT_PORTS.get(scheme):
        port = None

    netloc = hostname if port is None else f"{hostname}:{port}"

    path = parts.path or "/"
    path = _normalize_percent_encoding(path)

    query = _normalize_query(parts.query)

    # Fragment is intentionally dropped, it never reaches the
    # server and cannot affect which resource is returned.
    canonical = urlunsplit((scheme, netloc, path, query, ""))

    return NormalizedURL(value=canonical)


def _is_internal_url(candidate_url: str, base_url: str) -> bool:
    """
    Verify if a candidate URL shares the exact same domain as the base URL.

    This operates as a deterministic local check without executing network requests.
    """
    try:
        candidate = urlsplit(candidate_url)
        base = urlsplit(base_url)
    except ValueError:
        return False

    if not candidate.hostname or not base.hostname:
        return False

    return candidate.hostname.lower() == base.hostname.lower()


UNSAFE_DEFAULT_PATHS = (
    "/admin",
    "/cart",
    "/checkout",
    "/account",
    "/login",
    )


def _is_safe_default_path(url: str) -> bool:
    """
    Verify if a URL path avoids restricted administrative or
    interactive directories.

    This local check runs deterministically without initiating
    any network activity and does not check robots.txt.
    """
    try:
        path = urlsplit(url).path
    except ValueError:
        return False

    normalized_path = path.rstrip("/") or "/"

    for unsafe_path in UNSAFE_DEFAULT_PATHS:
        if (
            normalized_path == unsafe_path
            or normalized_path.startswith(unsafe_path + "/")
            ):
            return False

    return True


class RobotsError(CrawlerError):
    """
    Raised when crawling must halt because access to robots.txt is
    explicitly disallowed, or because the file could not be retrieved
    due to a 5xx server error or persistent network failure.

    Per RFC 9309, an unreachable robots.txt must be treated as
    a full disallow, not an invitation to proceed.
    """


@dataclass(frozen=True)
class RobotsPolicy:
    """
    Represents the resolved robots.txt policy for a domain.

    Attributes:
        parser: A populated urllib.robotparser.RobotFileParser instance if
            robots.txt was retrieved successfully (200 OK), or an empty
            parser if the server returned a 4xx response (e.g., 404 Not Found).
        status: Diagnostic string tracking the exact resolution result.
    """
    parser: "RobotFileParser"
    status: str


# HTTP status codes indicating robots.txt is "unavailable" per RFC 9309.
# When unavailable, the crawler may proceed assuming no restrictions exist.
# Status 429 is deliberately excluded: it signals rate limiting ("back off"),
# not an absence of crawling rules.
_UNAVAILABLE_STATUS_RANGE = range(400, 500)
_RATE_LIMITED_STATUS = 429

# Maximum attempts before treating a 5xx error or network failure as 
# "unreachable" (requiring a full disallow per RFC 9309) rather than retrying.
ROBOTS_FETCH_MAX_RETRIES = 3
ROBOTS_FETCH_RETRY_DELAY_SECONDS = 1.0
ROBOTS_FETCH_TIMEOUT_SECONDS = 10

def _build_robots_url(base_url: str) -> str:
    """
    Constructs the absolute robots.txt URL for a site, preserving the original
    scheme, hostname, and explicit port numbers from the base URL.
    """
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def _sleep_if_retries_remain(
    attempt: int,
    max_attempts: int = ROBOTS_FETCH_MAX_RETRIES,
    base_delay: float = ROBOTS_FETCH_RETRY_DELAY_SECONDS,
    ) -> None:
    """
    Suspends execution with exponential backoff prior to a retry attempt.

    Returns immediately without sleeping if attempt equals or exceeds max_retries,
    avoiding unnecessary delay prior to loop termination or failure raising.

    Args:
        attempt: Current 1-based retry attempt number.
        max_retries: Maximum permitted retries before giving up.
        base_delay: Base delay in seconds applied to exponential scaling.
    """
    if attempt >= max_attempts:
        return

    backoff_delay = base_delay * (2 ** (attempt - 1))
    time.sleep(backoff_delay)


def fetch_robots_policy(
    base_url: str,
    user_agent: str,
    ) -> RobotsPolicy:
    """
    Fetches and resolves the robots.txt policy for a target domain per RFC 9309

    Resolution Strategy:
    - 200 OK: Parses rules normally. If the rules explicitly disallow "/" for
        the configured user-agent, a RobotsError is raised.
    - 4xx (except 429): Classified as "unavailable". RFC 9309 allows crawling
        by default when policy files are missing or inaccessible.
    - 429: Retried with exponential backoff; does not mark the policy as unavailable.
    - 5xx or Network Failure: Retried up to ROBOTS_FETCH_MAX_RETRIES times. Persistent
        failures are treated as "unreachable" and raise a RobotsError (fail-closed).

    Note:
        Although RFC 9309 distinguishes between an explicit "Disallow: /" rule 
        and an unreachable robots.txt file, this crawler deliberately enforces 
        a fail-closed policy: crawling halts whenever access is explicitly 
        denied or policy status remains ambiguous.

    Args:
        base_url: Base site URL containing scheme and hostname.
        user_agent: Crawler user-agent string used for HTTP requests and rule parsing.

    Returns:
        A RobotsPolicy instance containing the resolved RobotFileParser rules.

    Raises:
        RobotsError: If crawling is explicitly disallowed or if robots.txt 
            cannot be reliably retrieved after retries.
    """

    robots_url = _build_robots_url(base_url)
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/plain",
        }

    last_error_description = "unknown error"

    for attempt in range(1, ROBOTS_FETCH_MAX_RETRIES + 1):
        try:
            response = requests.get(
                robots_url,
                headers=headers,
                timeout=ROBOTS_FETCH_TIMEOUT_SECONDS,
                )
        except RequestException as exc:
            last_error_description = f"network error: {exc}"
            _sleep_if_retries_remain(attempt)
            continue
        
        status = response.status_code

        if status == _RATE_LIMITED_STATUS:
            last_error_description = "rate limited (429)"
            _sleep_if_retries_remain(attempt)
            continue

        if status in _UNAVAILABLE_STATUS_RANGE:
            parser = RobotFileParser()
            parser.parse([])
            return RobotsPolicy(
                parser=parser,
                status=f"unavailable_{status}",
                )

        if status == 200:
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())

            if not parser.can_fetch(user_agent, "/"):
                raise RobotsError(
                    f"{base_url} explicitly disallows crawling "
                    f"for user-agent '{user_agent}'."
                    )

            is_empty = not response.text.strip()
            status_label = "empty_rules_allowed" if is_empty else "loaded"

            return RobotsPolicy(parser=parser, status=status_label)

        last_error_description = f"HTTP {status}"
        _sleep_if_retries_remain(attempt)

    raise RobotsError(
        f"Could not reliably retrieve robots.txt for {base_url} "
        f"after {ROBOTS_FETCH_MAX_RETRIES} attempts "
        f"({last_error_description}). Per RFC 9309, an "
        f"unreachable robots.txt must be treated as full disallow."
        )


def _is_allowed_by_robots(
        url: str,
        policy: RobotsPolicy,
        user_agent: str,
        ) -> bool:
        """
        Evaluate whether a target URL is permitted for crawling under a domain's policy.

        Performs an in-memory evaluation against a pre-fetched RobotsPolicy instance
        without triggering network requests.

        Args:
            url: Target URL or path to validate against policy rules.
            policy: Pre-fetched RobotsPolicy instance for target domain.
            user_agent: Crawler user-agent string used to evaluate matching rules.

        Returns:
            True if crawlig the URL is permitted under the policy; False otherwise.
        """
        return policy.parser.can_fetch(user_agent, url)


_robots_policy_cache: dict = {}


def get_robots_policy(
    base_url: str,
    user_agent: str,
    ) -> RobotsPolicy:
    """
    Retrieves and caches the robots.txt policy for a URL's origin.

    Cache keys are structured as (scheme, hostname, port) per RFC 9309 §2.1,
    ensuring distinct policies are maintained for http/https protocols or
    non-standard ports. Transient fetch failures raise a RobotsError and
    bypass cahce storage to allow future retry attempts.

    Args:
        base_url: Any URL belonging to the target domain.
        user_agent: Crawler user-agent string used for policy retrieval

    Returns:
        A RobotsPolicy instance for the specified origin.

    Raises:
        CrawlerError: If a valid hostname cannot be extracted from base_url.
        RobotsError: If crawling is explicitly disallowed or if robots.txt 
            cannot be retrieved after retries.
    """

    parts = urlsplit(base_url)
    hostname = parts.hostname

    if not hostname:
        raise CrawlerError(f"Could not determine hostname for: {base_url}")

    cache_key = (
        parts.scheme.lower(),
        hostname.lower(),
        parts.port,
        )

    if cache_key in _robots_policy_cache:
        return _robots_policy_cache[cache_key]

    policy = fetch_robots_policy(base_url, user_agent)
    _robots_policy_cache[cache_key] = policy

    return policy