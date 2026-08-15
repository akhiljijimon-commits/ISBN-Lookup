# 01 — Vision

## Problem

Book metadata is split across sources that are each good at half the job. Open Library
has dependable identity and authorship but no price. Google Books has a price and a
publisher blurb but noisier identity. Reconciling the two by hand, one ISBN at a time,
is slow and error-prone. Asking a language model directly is faster but worse: it
returns plausible-looking invented titles, authors, prices and blurbs, and gives the
reader no way to tell an invented fact from a real one.

## Goal

One ISBN in, one verified table out. Every fact in that table comes from a tool call
against a named source, and the result records which sources contributed. The language
model is confined to two jobs it is actually good at: normalising the shape of tool
output, and writing a short description when no publisher description exists.

## Target user

Someone who works with books by identifier and needs a quick, trustworthy view of a
single title — a librarian cataloguing an acquisition, a bookseller checking a listing,
an archivist confirming an edition. They know the ISBN already; they need the rest of
the record, and they need to trust it.

Secondary: a developer using this repository as a worked reference for Pydantic AI +
FastAPI + React, where the agent is deliberately kept out of the fact-supplying path.

## Success criteria

1. The golden ISBN `9780132350884` returns the correct title and author, end to end.
2. Zero facts originate from model memory. Every field in a result is attributable to a
   source listed in `sources`.
3. A book with no price available renders "Not available" and returns HTTP 200 — a
   designed state, never an error.
4. A malformed or checksum-invalid ISBN is rejected before any upstream call is made.
5. p95 end-to-end lookup completes within 5 seconds (NFR-01).

## Out of scope

The following are explicitly *not* part of this product:

- Search by title, author or keyword — ISBN is the only input.
- Multi-book or batch lookup.
- User accounts, authentication or authorisation.
- Persistence: no saved history, no result caching, no database.
- Purchase links, retailer price comparison, or price history.
- Editing or correcting the returned data.
- Non-book identifiers: ISSN, ASIN, DOI, LCCN.
- Internationalisation and localisation of the UI.
- Native mobile applications.
- Deployment, hosting and production operations.
