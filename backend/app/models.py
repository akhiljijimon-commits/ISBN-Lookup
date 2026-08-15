from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

Source = Literal["open_library", "google_books", "llm"]


class BookInfo(BaseModel):
    """The single data contract shared by the agent, the API and the UI."""

    isbn: str = Field(
        description=(
            "The ISBN-13 that was looked up. ISBN-10 input is normalised to "
            "ISBN-13, so this field is always ISBN-13 regardless of the form "
            "the user entered."
        )
    )
    title: str
    authors: list[str]
    cover_url: HttpUrl | None = Field(
        default=None, description="Cover image URL, or None if unavailable"
    )
    price: Decimal | None = Field(
        default=None, description="List price, or None if no source provides one"
    )
    currency: str | None = Field(
        default=None, description="ISO 4217 code, e.g. EUR. None when price is None"
    )
    description: str = Field(description="Short summary, 2-4 sentences")
    description_is_generated: bool = Field(
        description="True if the LLM wrote the description rather than a publisher"
    )
    sources: list[Source] = Field(description="Which sources contributed to this result")
