"""Retry behaviour in the source layer.

Google Books was observed alternating 200 and 503 on consecutive requests,
which turned a healthy lookup into a 404. These tests pin what is retried,
what is not, and how many requests each case costs.
"""

import httpx
import pytest

from app import sources

URL = "https://example.test/thing"


def _stub(
    monkeypatch: pytest.MonkeyPatch, responses: list[object]
) -> list[httpx.Request]:
    """Serve `responses` in order; return the list of requests actually made."""
    seen: list[httpx.Request] = []
    remaining = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        outcome = remaining.pop(0) if remaining else remaining_default
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, httpx.Response)
        return outcome

    remaining_default = httpx.Response(200, json={"ok": True})
    monkeypatch.setattr(
        sources,
        "_new_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(sources, "RETRY_BACKOFF_SECONDS", 0)
    return seen


async def test_transient_503_is_retried_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub(
        monkeypatch,
        [
            httpx.Response(503, json={"error": {"message": "Service unavailable"}}),
            httpx.Response(200, json={"totalItems": 1}),
        ],
    )

    result = await sources._get_json(URL, {})

    assert result == {"totalItems": 1}
    assert len(seen) == 2


async def test_persistent_503_gives_up_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub(
        monkeypatch,
        [httpx.Response(503, json={}), httpx.Response(503, json={})],
    )

    result = await sources._get_json(URL, {})

    assert result is None
    assert len(seen) == sources.MAX_ATTEMPTS


async def test_429_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """Open Library's per-second limit clears quickly; one retry is worth it."""
    seen = _stub(
        monkeypatch,
        [httpx.Response(429, json={}), httpx.Response(200, json={"ok": 1})],
    )

    assert await sources._get_json(URL, {}) == {"ok": 1}
    assert len(seen) == 2


async def test_timeout_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """The NFR-01 per-call budget is already spent; retrying doubles it."""
    seen = _stub(monkeypatch, [httpx.ReadTimeout("too slow")])

    result = await sources._get_json(URL, {})

    assert result is None
    assert len(seen) == 1


async def test_404_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """A definitive answer, not a transient one."""
    seen = _stub(monkeypatch, [httpx.Response(404, json={})])

    result = await sources._get_json(URL, {})

    assert result is None
    assert len(seen) == 1


async def test_success_makes_exactly_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub(monkeypatch, [httpx.Response(200, json={"ok": 1})])

    assert await sources._get_json(URL, {}) == {"ok": 1}
    assert len(seen) == 1


async def test_retry_recovers_a_whole_google_books_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure this was written for, at the level users experience it."""
    volume = {
        "totalItems": 1,
        "items": [
            {
                "volumeInfo": {"title": "Clean Code", "authors": ["Robert C. Martin"]},
                "saleInfo": {"listPrice": {"amount": 37.99, "currencyCode": "EUR"}},
            }
        ],
    }
    _stub(
        monkeypatch,
        [httpx.Response(503, json={}), httpx.Response(200, json=volume)],
    )

    identity, commerce = await sources.fetch_google_books_pair("9780132350884")

    assert identity is not None
    assert identity.title == "Clean Code"
    assert commerce is not None
    assert str(commerce.price) == "37.99"
