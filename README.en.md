# OpenAgent

**English** · [简体中文](./README.md)

Single-user **agent** application: Kernel orchestration, tools and Skills registry, retrieval with verifiable evidence. Document vector/keyword search is a **grounded capability** of the agent, not a standalone “RAG-only” product.

For full architecture and event contracts, see [`OPENAGENT_ARCHITECTURE.md`](./OPENAGENT_ARCHITECTURE.md). For milestones, see [`docs/DEVELOPMENT_PLAN.md`](./docs/DEVELOPMENT_PLAN.md).

## Architecture diagram

![OpenAgent architecture diagram](./docs/openagent-architecture-figma.png)

## Stack

| Layer | Notes |
|--------|--------|
| Backend | Python 3.11+, FastAPI, Uvicorn, SQLite, Qdrant, optional Ollama / OpenAI-compatible APIs |
| Frontend | Next.js 15, React 18, TypeScript, WebSocket streaming chat |
| Config | `config/openagent.yaml` (override path with env `OPENAGENT_CONFIG`) |

## Requirements

- Python **≥ 3.11**
- **Node.js** and **pnpm** (frontend)
- For local models/embeddings: **Ollama** (or OpenAI / vLLM per config)
- **Qdrant**: embedded local path (see config) or remote URL

## Quick start

### 1. Clone and install Python deps

```bash
cd openagent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Configure

Edit [`config/openagent.yaml`](./config/openagent.yaml): `models.generation`, `models.embedding`, `storage` (SQLite path, Qdrant), etc.

Override nested values with environment variables, e.g.:

```bash
export OPENAGENT_MODELS__GENERATION__PROVIDER=ollama
```

### 3. Run the backend

```bash
python scripts/start_server.py
```

Default: `http://127.0.0.1:8000`. Use `OPENAGENT_HOST` and `OPENAGENT_PORT` to change.

### 4. Run the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://127.0.0.1:3000`. If the API is not on port 8000, set the base URL in **Settings** or via `NEXT_PUBLIC_API_BASE`.

## Multi-agent (MVP)

When `orchestration.multi_agent.enabled` is `true` (default) in [`config/openagent.yaml`](./config/openagent.yaml), a user message that **starts with** `trigger_prefix` after trim (default **`[multi]`**) runs a **two-phase** pipeline (analyst → synthesizer). The prefix is **not** part of the question sent to the models.

Example:

```text
[multi] Summarize the key points from the imported documents
```

To disable: `orchestration.multi_agent.enabled: false` or `OPENAGENT_ORCHESTRATION__MULTI_AGENT__ENABLED=false`.

## API and WebSocket

- **REST**: document import, jobs, traces, runtime config, etc. (`backend/api/routes/`).
- **WebSocket**: `ws://<host>:<port>/ws`  
  - Client sends `chat.start` (`query`, `client_request_id`, `stream`, …).  
  - Server pushes `chat.delta`, `chat.retrieval_update`, `chat.evidence_update`, `chat.tool_call_*`, `chat.agent_*`, `chat.completed`, … (aligned with the architecture doc).

## Tests

```bash
# Backend unit tests
pytest tests/unit -q

# Frontend (from frontend/)
pnpm test
pnpm typecheck
pnpm exec eslint "src/**/*.{ts,tsx}" --max-warnings 0
pnpm exec playwright test   # run playwright install first
```

## Repository layout (summary)

```text
openagent/
  README.md
  README.en.md
  OPENAGENT_ARCHITECTURE.md
  config/openagent.yaml
  backend/           # FastAPI, Kernel, retrieval, registry, storage
  frontend/          # Next.js app
  scripts/start_server.py
  tests/unit/
  docs/
```

## License

No `LICENSE` file is included at the repo root; confirm usage terms with the maintainers.
