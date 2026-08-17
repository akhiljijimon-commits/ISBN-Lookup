"""SPIKE: the vertical slice, proving the end-to-end path works.

Throwaway code. It suspends several CLAUDE.md rules on purpose — see
docs/adr/0004-vertical-slice-spike.md for the full list and the story that
restores each one. Every file here sits at the path the real implementation
will use, so stories overwrite this code rather than build on it.
"""

import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent import assemble_without_agent, normalise
from app.models import BookInfo, Source
from app.sources import (
    Commerce,
    fetch_google_books,
    fetch_google_books_pair,
    fetch_open_library,
)

logger = logging.getLogger(__name__)

# .env lives at the repository root, one level above backend/. Loaded here so
# the documented `uv run uvicorn app.main:app --reload` picks up credentials
# without extra flags (rule 7, NFR-03, NFR-10).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI(title="ISBN Lookup (spike)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_THIRTEEN_DIGITS = re.compile(r"^\d{13}$")

_FALSY = {"0", "false", "no", "off"}
_TRUTHY = {"1", "true", "yes", "on"}


def _use_agent() -> bool:
    """Agent path on by default; USE_AGENT=0 serves the deterministic path."""
    return os.environ.get("USE_AGENT", "true").strip().lower() not in _FALSY


def _allow_identity_fallback() -> bool:
    """Off by default, so the documented architecture is what runs.

    Open Library owns identity (FR-07). This opts into a degradation path for
    the period Open Library is unreachable — see
    docs/adr/0004-vertical-slice-spike.md.
    """
    return os.environ.get("ALLOW_IDENTITY_FALLBACK", "").strip().lower() in _TRUTHY


def _normalise(raw: str) -> str | None:
    """Strip hyphens and spaces; accept only 13 digits.

    No checksum and no ISBN-10 support: that is US-01 (FR-02, FR-03, FR-04).
    """
    candidate = raw.replace("-", "").replace(" ", "")
    return candidate if _THIRTEEN_DIGITS.match(candidate) else None


@app.get("/api/books/{isbn}")
async def get_book(isbn: str) -> BookInfo:
    normalised = _normalise(isbn)
    if normalised is None:
        raise HTTPException(
            status_code=422,
            detail="Enter a 13-digit ISBN. Hyphens and spaces are ignored.",
        )

    identity = await fetch_open_library(normalised)
    identity_source: Source = "open_library"
    commerce: Commerce | None = None

    if identity is not None:
        commerce = await fetch_google_books(normalised)
    elif _allow_identity_fallback():
        # Temporary degradation while Open Library is unreachable. One request
        # yields both projections, so the fallback costs no extra quota.
        identity, commerce = await fetch_google_books_pair(normalised)
        if identity is not None:
            identity_source = "google_books"
            logger.warning(
                "identity for %s served from Google Books fallback", normalised
            )

    if identity is None:
        # BookInfo.title is required, so there is no record to return without
        # identity. The spike's stand-in for FR-15 / FR-16, which US-10 splits
        # into two distinct states.
        raise HTTPException(
            status_code=404, detail=f"No book found for ISBN {normalised}"
        )

    if _use_agent():
        try:
            return await normalise(normalised, identity, commerce, identity_source)
        except Exception:
            # An unreachable or misbehaving LLM degrades to the deterministic
            # result rather than failing a lookup whose facts are already in
            # hand — the same shape as FR-17's price-source degradation.
            logger.warning(
                "agent path failed for %s, falling back to deterministic assembly",
                normalised,
                exc_info=True,
            )

    return assemble_without_agent(normalised, identity, commerce, identity_source)
