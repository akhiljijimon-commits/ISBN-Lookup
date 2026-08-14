# ISBN Lookup

React + FastAPI + Pydantic AI. User enters an ISBN, sees book details in a table.

## Stack
- Backend: Python 3.12, FastAPI, Pydantic AI, uv, pytest, ruff, mypy
- Frontend: React 19, TypeScript, Vite, ESLint, vitest
- Data: mcp-open-library (MCP server) for identity/author/cover,
  Google Books API for price/description

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
5. Branch naming: feat/FR-XX-short-name. Conventional commits. Squash merge.
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
