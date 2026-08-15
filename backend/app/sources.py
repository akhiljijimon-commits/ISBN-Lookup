"""SPIKE: direct HTTP calls to the two upstream sources.

Throwaway code. There is no agent, no MCP client and no LLM here; the real
path arrives with US-05 (Open Library via mcp-open-library) and US-06 (Google
Books). See docs/adr/0004-vertical-slice-spike.md.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

OPEN_LIBRARY_URL = "https://openlibrary.org/api/books"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"

# NFR-01: one unresponsive source must not hold the whole request open.
TIMEOUT = httpx.Timeout(3.0)


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


async def _get_json(url: str, params: dict[str, str]) -> Any | None:
    """GET and parse JSON, or None if the source failed in any way."""
    try:
        async with _new_client() as client:
            response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        return None


async def fetch_open_library(isbn: str) -> Identity | None:
    """Identity from Open Library, or None if it has no usable record.

    Uses the api/books endpoint rather than /isbn/{isbn}.json because it
    returns author names and a cover URL inline; the other endpoint returns
    author keys that each need a further request.
    """
    key = f"ISBN:{isbn}"
    data = await _get_json(
        OPEN_LIBRARY_URL, {"bibkeys": key, "format": "json", "jscmd": "data"}
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


async def fetch_google_books(isbn: str) -> Commerce | None:
    """Price and publisher description from Google Books, unauthenticated.

    GOOGLE_BOOKS_API_KEY is not used: the volumes endpoint serves anonymous
    requests fine at this volume.
    """
    data = await _get_json(GOOGLE_BOOKS_URL, {"q": f"isbn:{isbn}"})
    if not isinstance(data, dict):
        return None

    items = data.get("items") or []
    if not items:
        return None

    volume = items[0]
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
