"""SPIKE: the vertical slice, proving the end-to-end path works.

Throwaway code. It suspends several CLAUDE.md rules on purpose — see
docs/adr/0004-vertical-slice-spike.md for the full list and the story that
restores each one. Every file here sits at the path the real implementation
will use, so stories overwrite this code rather than build on it.
"""

import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import BookInfo, Source
from app.sources import fetch_google_books, fetch_open_library

app = FastAPI(title="ISBN Lookup (spike)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_THIRTEEN_DIGITS = re.compile(r"^\d{13}$")


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
    if identity is None:
        # BookInfo.title is required, so there is no record to return without
        # identity. The spike's stand-in for FR-15 / FR-16, which US-10 splits
        # into two distinct states.
        raise HTTPException(
            status_code=404, detail=f"No book found for ISBN {normalised}"
        )

    commerce = await fetch_google_books(normalised)

    sources: list[Source] = ["open_library"]
    if commerce is not None:
        sources.append("google_books")

    return BookInfo(
        isbn=normalised,
        title=identity.title,
        authors=identity.authors,
        cover_url=identity.cover_url,  # type: ignore[arg-type]  # str coerced to HttpUrl
        price=commerce.price if commerce else None,
        currency=commerce.currency if commerce else None,
        description=(commerce.description if commerce else None) or "",
        # No LLM in the spike, so nothing is ever model-authored (FR-10).
        description_is_generated=False,
        sources=sources,
    )
