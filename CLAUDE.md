# ISBN Lookup

React + FastAPI + Pydantic AI. User enters an ISBN, sees book details in a table.

## Stack
- Backend: Python 3.12, FastAPI, Pydantic AI, uv, pytest, ruff, mypy
- Frontend: React 19, TypeScript, Vite, ESLint, vitest
- LLM: a self-hosted vLLM endpoint serving nvidia/Qwen3.6-35B-A3B-NVFP4,
  reached through Pydantic AI's OpenAI-compatible provider with a custom
  base_url. This is not the Anthropic API. Configured by LLM_API_KEY,
  LLM_BASE_URL and LLM_MODEL in .env.
  Qwen3.6 is a reasoning model, so requests pass chat_template_kwargs
  {"enable_thinking": false} for structured extraction.
- Data: mcp-open-library (MCP server) for identity/author/cover,
  Google Books API for price/description. GOOGLE_BOOKS_API_KEY is required:
  anonymous requests hit an exhausted shared daily quota and return HTTP 429.

## Commands
Backend (run from ./backend):
  uv run pytest
  uv run ruff check --fix .
  uv run mypy app
  uv run uvicorn app.main:app --reload

Frontend (run from ./frontend):
  npm run build
  npm run dev
  npm run lint

## Rules
1. The LLM NEVER supplies book facts from memory. Every fact comes from a tool
   call. The LLM only normalises fields and writes the description.
2. BookInfo in backend/app/models.py is the single contract. Frontend types are
   GENERATED from /openapi.json. Never hand-write the TypeScript interface.
3. A missing price is a valid, designed state, not an error. Show
   "Not available" in the UI.
4. Every PR closes exactly one user story and updates docs/06-traceability.md.
5. Branch naming: feat/FR-XX-short-name. Conventional commits. Merge commit
   (never squash): branch topology in the commit graph is a project
   deliverable, and squashing erases it.
6. Tests are written from the story's Gherkin acceptance criteria, before
   the implementation.
7. No secrets in code. Use .env, and keep .env.example committed.

## Project layout
backend/app/       FastAPI app, agent, models
backend/tests/     pytest
frontend/src/      React
docs/              requirements, specs, ADRs

## Golden test ISBN
9780132350884 (Clean Code, Robert C. Martin)
