"""SPIKE smoke test: proves the wiring, not the requirements.

This test was written after the code and from no Gherkin scenario, so it does
not satisfy CLAUDE.md rule 6. It exists only so the spike's "the path works"
claim survives past one manual check. Real tests arrive with US-01 onward.
"""

import httpx
import pytest

from app import sources
from app.main import app
from app.models import BookInfo

GOLDEN_ISBN = "9780132350884"

OPEN_LIBRARY_PAYLOAD = {
    f"ISBN:{GOLDEN_ISBN}": {
        "url": "https://openlibrary.org/books/OL24214147M/Clean_Code",
        "title": "Clean Code",
        "authors": [
            {
                "url": "https://openlibrary.org/authors/OL4452558A/Robert_C._Martin",
                "name": "Robert C. Martin",
            }
        ],
        "cover": {
            "small": "https://covers.openlibrary.org/b/id/8479576-S.jpg",
            "medium": "https://covers.openlibrary.org/b/id/8479576-M.jpg",
            "large": "https://covers.openlibrary.org/b/id/8479576-L.jpg",
        },
    }
}

GOOGLE_BOOKS_PAYLOAD = {
    "totalItems": 1,
    "items": [
        {
            "volumeInfo": {
                "title": "Clean Code",
                "description": "Even bad code can function. But if code isn't clean...",
            },
            "saleInfo": {
                "country": "DE",
                "saleability": "FOR_SALE",
                "listPrice": {"amount": 37.99, "currencyCode": "EUR"},
            },
        }
    ],
}


def _handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "openlibrary.org":
        return httpx.Response(200, json=OPEN_LIBRARY_PAYLOAD)
    if host == "www.googleapis.com":
        return httpx.Response(200, json=GOOGLE_BOOKS_PAYLOAD)
    raise AssertionError(f"unexpected upstream request to {request.url}")


@pytest.fixture(autouse=True)
def deterministic_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests assert the pre-agent shape, so pin the deterministic path.

    Without this the agent would run and reach the live LLM, breaking NFR-06's
    requirement that the suite make no network call.
    """
    monkeypatch.setenv("USE_AGENT", "0")


@pytest.fixture
def stubbed_upstreams(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the client seam in sources.py so no network call is made."""
    monkeypatch.setattr(
        sources,
        "_new_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
    )


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_golden_isbn_returns_a_valid_bookinfo(stubbed_upstreams: None) -> None:
    response = await _get(f"/api/books/{GOLDEN_ISBN}")

    assert response.status_code == 200
    book = BookInfo.model_validate(response.json())

    assert book.isbn == GOLDEN_ISBN
    assert book.title == "Clean Code"
    assert "Robert C. Martin" in book.authors
    assert book.cover_url is not None
    assert str(book.price) == "37.99"  # not 37.990000000000002
    assert book.currency == "EUR"
    assert book.description_is_generated is False
    assert book.sources == ["open_library", "google_books"]


async def test_hyphens_and_spaces_are_ignored(stubbed_upstreams: None) -> None:
    response = await _get("/api/books/978-0-13-235088-4")

    assert response.status_code == 200
    assert response.json()["isbn"] == GOLDEN_ISBN


async def test_a_non_isbn_is_refused_without_calling_upstream() -> None:
    # No stub fixture: reaching an upstream would raise in _handler, but with
    # nothing patched a real call would be attempted. Neither happens, because
    # validation rejects the input first.
    response = await _get("/api/books/12345")

    assert response.status_code == 422
