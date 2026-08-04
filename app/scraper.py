"""
Webpage fetching service.

Responsible for downloading raw HTML from a given URL.

This module does NOT:
- Parse HTML
- Extract text
- Perform compliance analysis

It only retrieves webpage content.
"""

from urllib.parse import urlparse

import requests
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    HTTPError,
    InvalidURL,
    MissingSchema,
    SSLError,
    Timeout,
    TooManyRedirects,
    )

from app.config import REQUEST_TIMEOUT, USER_AGENT


class ScraperError(Exception):
    """Base exception for scraper errors."""


class InvalidURLError(ScraperError):
    """Raised when the provided URL is invalid."""


class FetchTimeoutError(ScraperError):
    """Raised when a request times out."""


class FetchFailedError(ScraperError):
    """Raised when a webpage cannot be fetched."""


def _validate_url(url: str) -> str:
    """
    Validate a URL before making a request.

    Args:
        url: URL to validate.

    Returns:
        A cleaned, validated URL.

    Raises:
        InvalidURLError: If the URL is invalid.
    """

    if not url:
        raise InvalidURLError("URL cannot be empty.")

    url = url.strip()

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError(
            "URL must begin with http:// or https://"
            )

    if not parsed.netloc:
        raise InvalidURLError("Invalid domain.")

    return url


def fetch_page(url: str) -> str:
    """
    Fetch raw HTML from a webpage.

    Args:
        url: The webpage URL.

    Returns:
        Raw HTML as a string.

    Raises:
        InvalidURLError:
            If the supplied URL is invalid.

        FetchTimeoutError:
            If the request exceeds the configured timeout.

        FetchFailedError:
            If the page cannot be retrieved or is not an HTML document.
    """

    url = _validate_url(url)

    headers = {
        "User-Agent": USER_AGENT,
        }

    try:
        response = requests.get(
            url=url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            ""
            ).lower()

        if "text/html" not in content_type:
            raise FetchFailedError(
                "URL does not point to an HTML webpage."
                )

        return response.text

    except Timeout as exc:
        raise FetchTimeoutError(
            f"Request timed out after {REQUEST_TIMEOUT} seconds."
            ) from exc

    except TooManyRedirects as exc:
        raise FetchFailedError(
            "Too many redirects."
            ) from exc

    except SSLError as exc:
        raise FetchFailedError(
            "SSL certificate verification failed."
            ) from exc

    except (MissingSchema, InvalidURL) as exc:
        raise InvalidURLError(
            "Invalid URL."
            ) from exc

    except HTTPError as exc:
        status = exc.response.status_code

        raise FetchFailedError(
            f"HTTP {status}: Unable to fetch webpage."
            ) from exc

    except RequestsConnectionError as exc:
        raise FetchFailedError(
            "Failed to connect to the website."
            ) from exc

    except requests.RequestException as exc:
        raise FetchFailedError(
            f"Unexpected request error: {exc}"
            ) from exc