"""The Pydantic AI agent that normalises tool output into a BookInfo.

Python orchestrates the source calls; the model does not choose them. The vLLM
deployment is not started with --enable-auto-tool-choice, so autonomous tool
calling is unavailable — see docs/adr/0005-agent-without-autonomous-tool-calling.md.

Two consequences shape this module:

1. Pydantic AI's default structured-output mode is 'tool', which would return
   the result *via a tool call* — the one mechanism this deployment disables.
   So prompted mode is pinned explicitly.
2. Prompted mode only sends `response_format: {"type": "json_object"}` when the
   model profile advertises `supports_json_object_output`, and the base default
   is False. Setting it is what makes the wire format match what was verified
   against the live endpoint.
"""

import os
from decimal import Decimal

from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.models import BookInfo, Source
from app.sources import Commerce, Identity

# NFR-01: the model call now dominates the end-to-end budget.
LLM_TIMEOUT_SECONDS = 30.0

SYSTEM_PROMPT = """\
You normalise book metadata that has already been retrieved from external \
sources. You are given the raw output of those lookups and nothing else.

ABSOLUTE RULE: every book fact you return must be present in the tool output \
you were given. You must never supply a title, author, publisher, price, \
currency, cover URL or any other book fact from your own knowledge, even if \
you recognise the book and are confident the tool output is wrong or \
incomplete. If a field is absent from the tool output, leave it null or empty \
rather than guessing. An invented fact is a defect, not a helpful addition.

Your permitted work is exactly two things:

1. Normalising the shape of what you were given — tidying whitespace and \
capitalisation in the title, and returning the authors as a clean list of \
personal names.
2. Writing a description of 2-4 sentences, but ONLY when the tool output \
contains no publisher description. The description is prose, but it is not an \
exception to the rule above: every claim in it must be supported by the tool \
output you were given. Do not describe the book's structure, chapters, \
themes, reception or author biography unless those details appear in the tool \
output. Do not review, rate or recommend it. A short, plain description built \
only from the title and authors you were given is correct; a fuller one drawn \
from what you remember about the book is a defect.

If the tool output already contains a description, return it unchanged.
"""

# The deployment rejects a second system message with "System message must be
# at the beginning". Pydantic AI emits `instructions` as one system message and
# PromptedOutput's schema block as another, which trips that. Folding the rule
# into PromptedOutput's own template keeps it to a single system message.
# `{schema}` is substituted by Pydantic AI; the prompt must contain no other
# braces, since the template is rendered with str.format.
OUTPUT_TEMPLATE = f"""{SYSTEM_PROMPT}
Respond with a single JSON object conforming to this schema:

{{schema}}
"""


def _build_agent() -> Agent[None, BookInfo]:
    """Construct the agent from environment configuration.

    Called per request rather than at import time so that importing this
    module never requires credentials and the test suite stays offline
    (NFR-06, rule 7).
    """
    model = OpenAIChatModel(
        os.environ["LLM_MODEL"],
        provider=OpenAIProvider(
            base_url=os.environ["LLM_BASE_URL"],
            api_key=os.environ["LLM_API_KEY"],
        ),
        profile=ModelProfile(
            # Without this flag prompted mode sends no response_format at all.
            supports_json_object_output=True,
            default_structured_output_mode="prompted",
        ),
    )
    return Agent(
        model,
        output_type=PromptedOutput(BookInfo, template=OUTPUT_TEMPLATE),
        # One extra attempt absorbs the occasional schema miss; beyond that the
        # endpoint is misbehaving and the fallback path is the better answer.
        retries=2,
        model_settings=OpenAIChatModelSettings(
            # Qwen3.6 is a reasoning model; its thinking block interferes with
            # structured extraction (ADR-0003).
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            timeout=LLM_TIMEOUT_SECONDS,
            temperature=0.0,
        ),
    )


def _prompt(isbn: str, identity: Identity, commerce: Commerce | None) -> str:
    """Render the tool output the model is allowed to draw on.

    The ISBN is included because BookInfo requires it and the model has no
    other way to know it — without it the model correctly refuses to invent
    one and returns null, failing validation.
    """
    lines = [
        f"The ISBN looked up was {isbn}.",
        "",
        "Tool output from Open Library (identity):",
        f"  title: {identity.title}",
        f"  authors: {identity.authors}",
        f"  cover_url: {identity.cover_url}",
        "",
        "Tool output from Google Books (commerce):",
    ]
    if commerce is None:
        lines.append("  (no result — this source returned nothing)")
    else:
        lines.extend(
            [
                f"  price: {commerce.price}",
                f"  currency: {commerce.currency}",
                f"  description: {commerce.description or '(none supplied)'}",
            ]
        )
    return "\n".join(lines)


def assemble(
    isbn: str,
    identity: Identity,
    commerce: Commerce | None,
    *,
    title: str,
    authors: list[str],
    cover_url: str | None,
    description: str,
    description_is_generated: bool,
    used_llm: bool,
) -> BookInfo:
    """Build a BookInfo, with Python owning every fact it already knows.

    The deterministic path and the agent path both end here, so provenance is
    computed identically either way.
    """
    sources: list[Source] = ["open_library"]
    if commerce is not None:
        sources.append("google_books")
    if used_llm:
        sources.append("llm")

    price: Decimal | None = commerce.price if commerce else None
    return BookInfo(
        isbn=isbn,
        title=title,
        authors=authors,
        cover_url=cover_url,  # type: ignore[arg-type]  # str coerced to HttpUrl
        price=price,
        currency=commerce.currency if commerce and price is not None else None,
        description=description,
        description_is_generated=description_is_generated,
        sources=sources,
    )


def assemble_without_agent(
    isbn: str, identity: Identity, commerce: Commerce | None
) -> BookInfo:
    """The deterministic path: tool output straight into the contract."""
    return assemble(
        isbn,
        identity,
        commerce,
        title=identity.title,
        authors=identity.authors,
        cover_url=identity.cover_url,
        description=(commerce.description if commerce else None) or "",
        # No model ran, so nothing can be model-authored (FR-10).
        description_is_generated=False,
        used_llm=False,
    )


async def normalise(
    isbn: str, identity: Identity, commerce: Commerce | None
) -> BookInfo:
    """Run the agent over the tool output and return a validated BookInfo.

    The model owns title, authors, cover_url and description. Every other
    field is re-asserted from what Python already knows, so a fabricated price
    or a self-declared source is structurally impossible rather than merely
    forbidden by the prompt (FR-09, FR-10, FR-11, NFR-05).
    """
    publisher_description = (commerce.description if commerce else None) or ""
    result = await _build_agent().run(_prompt(isbn, identity, commerce))
    drafted = result.output

    # The model wrote the description only if no publisher supplied one.
    description_is_generated = not publisher_description
    description = (
        drafted.description if description_is_generated else publisher_description
    )

    return assemble(
        isbn,
        identity,
        commerce,
        title=drafted.title,
        authors=drafted.authors,
        cover_url=str(drafted.cover_url) if drafted.cover_url else None,
        description=description,
        description_is_generated=description_is_generated,
        used_llm=True,
    )
