"""Tests for the agent path, especially the rule 1 guarantee.

Offline throughout (NFR-06): upstream HTTP is stubbed via the _new_client seam
in sources.py, and the LLM is replaced with a FunctionModel, so no network call
and no credential is needed.
"""

import json
from typing import Any

import httpx
import pytest
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import agent as agent_module
from app import sources
from app.main import app
from app.models import BookInfo

GOLDEN_ISBN = "9780132350884"

OPEN_LIBRARY_PAYLOAD = {
    f"ISBN:{GOLDEN_ISBN}": {
        "title": "clean code  ",  # untidy on purpose: the model normalises it
        "authors": [{"name": "Robert C. Martin"}],
        "cover": {"large": "https://covers.openlibrary.org/b/id/8479576-L.jpg"},
    }
}

GOOGLE_BOOKS_WITH_EVERYTHING = {
    "totalItems": 1,
    "items": [
        {
            "volumeInfo": {"description": "A publisher-written description."},
            "saleInfo": {"listPrice": {"amount": 37.99, "currencyCode": "EUR"}},
        }
    ],
}

GOOGLE_BOOKS_NO_DESCRIPTION = {
    "totalItems": 1,
    "items": [
        {
            "volumeInfo": {},
            "saleInfo": {"listPrice": {"amount": 37.99, "currencyCode": "EUR"}},
        }
    ],
}

EMPTY_OPEN_LIBRARY: dict[str, Any] = {}
EMPTY_GOOGLE_BOOKS = {"totalItems": 0}


def _stub_upstreams(
    monkeypatch: pytest.MonkeyPatch,
    open_library: dict[str, Any],
    google_books: dict[str, Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openlibrary.org":
            return httpx.Response(200, json=open_library)
        if request.url.host == "www.googleapis.com":
            return httpx.Response(200, json=google_books)
        raise AssertionError(f"unexpected upstream request to {request.url}")

    monkeypatch.setattr(
        sources,
        "_new_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _stub_model(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    """Replace the LLM with one that returns exactly `payload` as its output."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(json.dumps(payload))])

    def build() -> Agent[None, BookInfo]:
        return Agent(FunctionModel(respond), output_type=PromptedOutput(BookInfo))

    monkeypatch.setattr(agent_module, "_build_agent", build)


def _stub_model_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    def build() -> Agent[None, BookInfo]:
        raise RuntimeError("LLM endpoint unreachable")

    monkeypatch.setattr(agent_module, "_build_agent", build)


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.fixture(autouse=True)
def agent_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_AGENT", "true")


# --- Rule 1: no fact may originate in the model -----------------------------


async def test_empty_sources_invent_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test rule 1 demands: no sources, no facts, no invention.

    A model that knows this ISBN could easily produce "Clean Code" and
    "Robert C. Martin" from memory. It never gets the chance: with no identity
    there is no result to return, and the agent is not called at all.
    """
    _stub_upstreams(monkeypatch, EMPTY_OPEN_LIBRARY, EMPTY_GOOGLE_BOOKS)
    _stub_model(
        monkeypatch,
        {
            "isbn": GOLDEN_ISBN,
            "title": "Clean Code",
            "authors": ["Robert C. Martin"],
            "cover_url": "https://example.com/invented.jpg",
            "price": "37.99",
            "currency": "EUR",
            "description": "Invented from memory.",
            "description_is_generated": False,
            "sources": ["open_library"],
        },
    )

    response = await _get(f"/api/books/{GOLDEN_ISBN}")

    assert response.status_code == 404
    body = response.text
    assert "Clean Code" not in body
    assert "Robert C. Martin" not in body
    assert "37.99" not in body
    assert "Invented" not in body


async def test_model_cannot_fabricate_price_or_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Facts Python already knows are re-asserted over whatever the model says."""
    _stub_upstreams(monkeypatch, OPEN_LIBRARY_PAYLOAD, GOOGLE_BOOKS_WITH_EVERYTHING)
    _stub_model(
        monkeypatch,
        {
            "isbn": "9999999999999",
            "title": "Clean Code",
            "authors": ["Robert C. Martin"],
            "cover_url": "https://covers.openlibrary.org/b/id/8479576-L.jpg",
            "price": "99.99",  # fabricated
            "currency": "USD",  # fabricated
            "description": "Model-written, though a publisher supplied one.",
            "description_is_generated": False,
            "sources": ["llm"],  # self-declared provenance
        },
    )

    response = await _get(f"/api/books/{GOLDEN_ISBN}")

    assert response.status_code == 200
    book = BookInfo.model_validate(response.json())

    assert str(book.price) == "37.99"  # the tool's price, not the model's
    assert book.currency == "EUR"
    assert book.isbn == GOLDEN_ISBN
    assert book.sources == ["open_library", "google_books", "llm"]
    # A publisher description existed, so the model did not author one.
    assert book.description == "A publisher-written description."
    assert book.description_is_generated is False


# --- FR-10: the generated-description flag ----------------------------------


async def test_description_is_generated_when_publisher_supplies_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_upstreams(monkeypatch, OPEN_LIBRARY_PAYLOAD, GOOGLE_BOOKS_NO_DESCRIPTION)
    _stub_model(
        monkeypatch,
        {
            "isbn": GOLDEN_ISBN,
            "title": "Clean Code",
            "authors": ["Robert C. Martin"],
            "cover_url": "https://covers.openlibrary.org/b/id/8479576-L.jpg",
            "price": "37.99",
            "currency": "EUR",
            "description": "A handbook of agile software craftsmanship.",
            "description_is_generated": False,  # the model gets this wrong
            "sources": [],
        },
    )

    response = await _get(f"/api/books/{GOLDEN_ISBN}")

    book = BookInfo.model_validate(response.json())
    assert book.description == "A handbook of agile software craftsmanship."
    assert book.description_is_generated is True
    assert "llm" in book.sources


async def test_model_normalises_the_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model's actual remit: tidying the shape of tool output."""
    _stub_upstreams(monkeypatch, OPEN_LIBRARY_PAYLOAD, GOOGLE_BOOKS_WITH_EVERYTHING)
    _stub_model(
        monkeypatch,
        {
            "isbn": GOLDEN_ISBN,
            "title": "Clean Code",  # tidied from "clean code  "
            "authors": ["Robert C. Martin"],
            "cover_url": "https://covers.openlibrary.org/b/id/8479576-L.jpg",
            "price": "37.99",
            "currency": "EUR",
            "description": "A publisher-written description.",
            "description_is_generated": False,
            "sources": ["open_library", "google_books"],
        },
    )

    response = await _get(f"/api/books/{GOLDEN_ISBN}")

    assert response.json()["title"] == "Clean Code"


# --- Degradation ------------------------------------------------------------


async def test_unreachable_llm_falls_back_to_deterministic_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_upstreams(monkeypatch, OPEN_LIBRARY_PAYLOAD, GOOGLE_BOOKS_WITH_EVERYTHING)
    _stub_model_raising(monkeypatch)

    response = await _get(f"/api/books/{GOLDEN_ISBN}")

    assert response.status_code == 200
    book = BookInfo.model_validate(response.json())
    assert book.title == "clean code  "  # unnormalised: no model ran
    assert book.sources == ["open_library", "google_books"]
    assert "llm" not in book.sources
    assert book.description_is_generated is False


async def test_use_agent_off_serves_the_deterministic_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_AGENT", "0")
    _stub_upstreams(monkeypatch, OPEN_LIBRARY_PAYLOAD, GOOGLE_BOOKS_WITH_EVERYTHING)

    def unreachable() -> Agent[None, BookInfo]:
        raise AssertionError("agent must not be built when USE_AGENT=0")

    monkeypatch.setattr(agent_module, "_build_agent", unreachable)

    response = await _get(f"/api/books/{GOLDEN_ISBN}")

    assert response.status_code == 200
    assert "llm" not in response.json()["sources"]


def test_system_prompt_forbids_supplying_facts() -> None:
    """Rule 1 must be stated in the prompt, not only enforced in Python."""
    prompt = agent_module.SYSTEM_PROMPT.lower()
    assert "never" in prompt
    assert "own knowledge" in prompt
    assert "2-4 sentences" in prompt
