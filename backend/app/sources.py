"""SPIKE: direct HTTP calls to the two upstream sources.

Throwaway code. There is no agent, no MCP client and no LLM here; the real
path arrives with US-05 (Open Library via mcp-open-library) and US-06 (Google
Books). See docs/adr/0004-vertical-slice-spike.md.
"""

import asyncio
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

OPEN_LIBRARY_URL = "https://openlibrary.org/api/books"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"

# NFR-01: one unresponsive source must not hold the whole request open.
TIMEOUT = httpx.Timeout(3.0)

# Open Library's API docs require a descriptive User-Agent with a contact
# address. Unidentified clients are rate-limited to 1 request/second;
# identified ones are allowed 3/second.
OPEN_LIBRARY_HEADERS = {"User-Agent": "ISBN-Lookup/0.1 (akhiljijimon@gmail.com)"}

# Both sources return transient 5xx under load — Google Books was observed
# alternating 200 and 503 "Service temporarily unavailable" on consecutive
# requests, which collapsed a whole lookup into a 404. One retry converts most
# of those into successes.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 0.25


@dataclass
class Identity:
    """What Open Library owns: title, authors, cover."""

    title: str
    authors: list[str]
    cover_url: str | None


@dataclass
class Commerce:
    """What Google Books owns: price, currency, publisher description."""

    price: Decimal | None
    currency: str | None
    description: str | None


def _new_client() -> httpx.AsyncClient:
    """Seam for the smoke test, which patches this to inject a MockTransport."""
    return httpx.AsyncClient(timeout=TIMEOUT)


async def _get_json(
    url: str, params: dict[str, str], headers: dict[str, str] | None = None
) -> Any | None:
    """GET and parse JSON, or None if the source failed in any way.

    Retries once on a transient status (RETRY_STATUSES) or a fast transport
    error. Timeouts are deliberately *not* retried: the per-call budget under
    NFR-01 has already been spent, and a second attempt would double the worst
    case for a failure unlikely to clear in a quarter of a second.
    """
    for attempt in range(MAX_ATTEMPTS):
        is_last = attempt + 1 == MAX_ATTEMPTS
        try:
            async with _new_client() as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException:
            return None
        except httpx.HTTPError:
            if is_last:
                return None
            await asyncio.sleep(RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code in RETRY_STATUSES and not is_last:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS)
            continue

        try:
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    return None


async def fetch_open_library(isbn: str) -> Identity | None:
    """Identity from Open Library, or None if it has no usable record.

    Uses the api/books endpoint rather than /isbn/{isbn}.json because it
    returns author names and a cover URL inline; the other endpoint returns
    author keys that each need a further request.
    """
    key = f"ISBN:{isbn}"
    data = await _get_json(
        OPEN_LIBRARY_URL,
        {"bibkeys": key, "format": "json", "jscmd": "data"},
        headers=OPEN_LIBRARY_HEADERS,
    )
    if not isinstance(data, dict):
        return None

    record = data.get(key)
    if not isinstance(record, dict) or not record.get("title"):
        return None

    authors = [
        author["name"]
        for author in record.get("authors", [])
        if isinstance(author, dict) and author.get("name")
    ]
    cover = record.get("cover") or {}
    return Identity(
        title=record["title"],
        authors=authors,
        cover_url=cover.get("large") or cover.get("medium"),
    )


async def _google_books_volume(isbn: str) -> dict[str, Any] | None:
    """The first matching Google Books volume, or None.

    GOOGLE_BOOKS_API_KEY is required, not optional: anonymous requests hit an
    exhausted shared daily quota and return HTTP 429. Read from the
    environment at call time so the key never appears in source (rule 7).
    """
    params = {"q": f"isbn:{isbn}"}
    api_key = os.environ.get("GOOGLE_BOOKS_API_KEY")
    if api_key:
        params["key"] = api_key

    data = await _get_json(GOOGLE_BOOKS_URL, params)
    if not isinstance(data, dict):
        return None

    items = data.get("items") or []
    if not items:
        return None

    volume = items[0]
    return volume if isinstance(volume, dict) else None


def _identity_from_volume(volume: dict[str, Any]) -> Identity | None:
    """Identity projection of a Google Books volume — a degradation path only.

    Open Library owns identity per FR-07. This exists so the system still
    functions while Open Library is unreachable, and is reached only when
    ALLOW_IDENTITY_FALLBACK is set. Google Books has noisier identity data
    (docs/01-vision.md), so this is worse data, not equivalent data.
    """
    info = volume.get("volumeInfo") or {}
    title = info.get("title")
    if not title:
        return None

    images = info.get("imageLinks") or {}
    return Identity(
        title=title,
        authors=[a for a in info.get("authors", []) if isinstance(a, str)],
        cover_url=images.get("thumbnail") or images.get("smallThumbnail"),
    )


async def fetch_google_books_pair(
    isbn: str,
) -> tuple[Identity | None, Commerce | None]:
    """Both projections from a single request.

    The fallback path needs identity *and* commerce from Google Books. Asking
    twice doubles quota use and gives the second call its own chance to be
    rate-limited — which was observed in practice, silently downgrading a
    publisher description to a generated one.
    """
    volume = await _google_books_volume(isbn)
    if volume is None:
        return None, None
    return _identity_from_volume(volume), _commerce_from_volume(volume)


async def fetch_google_books(isbn: str) -> Commerce | None:
    """Price and publisher description from Google Books."""
    volume = await _google_books_volume(isbn)
    if volume is None:
        return None
    return _commerce_from_volume(volume)


def _commerce_from_volume(volume: dict[str, Any]) -> Commerce:
    """Commercial projection of a Google Books volume."""
    description = volume.get("volumeInfo", {}).get("description")
    list_price = volume.get("saleInfo", {}).get("listPrice") or {}
    amount = list_price.get("amount")

    # str() first: Decimal(37.99) carries the float's binary error into the
    # response body as 37.990000000000002.
    price = Decimal(str(amount)) if amount is not None else None

    return Commerce(
        price=price,
        currency=list_price.get("currencyCode") if price is not None else None,
        description=description,
    )
