# Knowledge Base Slice

Version: `v0.14.0`
Status: Verified knowledge retrieval with internal reviewed-chunk management and reindex workflows

This spec records the verified knowledge base retrieval slice.
It exists to keep the orchestrator-port behavior, reviewed-chunk management APIs, deployment contract, and validation scope versioned alongside the code.

## Business Goal

Tailmate should answer curated factual questions from reviewed knowledge without turning the knowledge base into a new skill.
When the verified knowledge base is enabled, the runtime should prefer a vetted answer when one exists and otherwise fall back deterministically.
Operators also need a narrow management surface for reviewed chunk create, preview, import, delete, and embedding refresh without dropping back to ad hoc SQL for every content update.

## Slice Mapping

### Contract

- `src/tailmate/contracts/knowledge.py`
  Defines the Pydantic contract for verified knowledge queries, search hits, reviewed chunk write payloads, preview inputs, and normalized retrieval results.
- `src/tailmate/contracts/constants.py`
  Defines the `knowledge_base` metadata key plus the internal `/kb/chunks*` route constants used by the management APIs.
- `src/tailmate/agent_runtime/services/turn_messages.json`
  Stores the localized verified knowledge answer and out-of-scope response templates.

### Adapter

- `src/tailmate/agent_runtime/ports/knowledge_retriever.py`
  Declares the verified knowledge retrieval port used by the orchestrator.
- `src/tailmate/adapters/knowledge_base/retriever.py`
  Implements the direct PostgreSQL retriever, the Cloud Run gateway retriever, the Vertex embedding client, and the Gemini answer-synthesis client.
- `src/tailmate/adapters/knowledge_base/management.py`
  Implements reviewed chunk create, preview, import, delete, upload parsing, and direct-mode reindex helpers around the canonical `knowledge_chunks` table.
- `src/tailmate/adapters/database/models.py`
  Adds the `knowledge_chunks` table metadata.
- `src/tailmate/adapters/database/migrations/versions/a72d9c5f4e11_add_knowledge_chunks_table_for_verified_.py`
  Creates the checked-in schema revision for the verified knowledge base.
- `src/tailmate/adapters/db_gateway/client.py`
  Adds the gateway client call used by the Cloud Run search path.
- `src/tailmate/adapters/db_gateway/gateway_app.py`
  Exposes `/knowledge/search` for gateway-mode retrieval plus `/kb/chunks`, `/kb/chunks/import`, and `/kb/chunks/<chunk_id>` for reviewed chunk management.

Schema note:

- This slice changes the database schema and therefore requires the checked-in Alembic migration.

### Skill

- No new skill is introduced.
- Verified knowledge retrieval is a read-only orchestrator port, not a registered skill.

### Orchestration

- `src/tailmate/bootstrap/config.py`
  Parses `TAILMATE_KB_ENABLED`, `TAILMATE_EMBEDDING_MODEL`, and `TAILMATE_KB_THRESHOLD`.
- `src/tailmate/bootstrap/container.py`
  Builds the verified knowledge retriever when the flag is enabled and selects direct or gateway mode from the runtime config.
- `src/tailmate/agent_runtime/services/graph_orchestrator.py`
  Calls the retriever before static fallback and falls back cleanly on misses, low-confidence matches, or retriever failures.
- `src/tailmate/agents/root/prompts.py`
  Keeps the verified knowledge answer path aligned with the root-agent response contract.
- `src/tailmate/agents/root/agent.py`
  Surfaces the localized answer while keeping internal knowledge metadata out of the public payload.
- `src/tailmate/entrypoints/kb.py`
  Registers the developer-facing `tailmate kb reindex` command for direct-mode embedding rebuilds.

## Operational Notes

- `TAILMATE_KB_ENABLED=true` turns the verified knowledge base path on; leaving it unset or false keeps the orchestrator on deterministic fallback only.
- Direct mode searches `knowledge_chunks` in PostgreSQL.
- Gateway mode routes `/knowledge/search` through the Cloud Run DB gateway.
- Reviewed chunk management routes stay internal-only and do not widen the public `/v1/` contract.
- `tailmate kb reindex` requires direct database mode and rebuilds embeddings in place for all reviewed rows.
- Both modes use Vertex embeddings and Gemini answer synthesis when the retriever is enabled.
- The reviewed knowledge corpus is loaded from JSONL records into `knowledge_chunks` before rollout.
- The JSONL ingest process is operator-side data preparation, not a runtime skill.

## Validation Path

### Local Sandbox

1. Start the Cloud SQL Auth Proxy with `./scripts/start_cloudsql_proxy.sh`.
2. Apply the schema with `uv run alembic upgrade head`.
3. Run `uv run python -m compileall src tests`.
4. Run `uv run python -m pytest tests/unit/test_knowledge_retriever.py tests/unit/test_kb_cli.py tests/integration/test_container_modes.py tests/integration/test_fallback_orchestration.py tests/unit/test_gateway_app.py tests/contract/test_root_agent_query.py tests/contract/test_deploy_entrypoint.py`.
5. Validate both knowledge modes by enabling `TAILMATE_KB_ENABLED=true` and confirming one direct PostgreSQL path and one Cloud Run gateway path.
6. Validate the internal management surface by creating, previewing, importing, and deleting reviewed chunks through `/kb/chunks*`.
7. Confirm that miss and error cases fall back to the deterministic locale response.

### Cloud Validation

1. Deploy the gateway with `/knowledge/search` enabled.
2. Seed or manage the reviewed corpus through the internal `/kb/chunks*` routes or a trusted direct workflow.
3. Deploy the agent with `TAILMATE_KB_ENABLED=true`, `TAILMATE_EMBEDDING_MODEL`, and `TAILMATE_KB_THRESHOLD`.
4. Run `deployment/agent_engine/smoke_test.py` against hit, out-of-scope, and miss prompts.
5. Confirm that the public response stays localized and that internal `knowledge_base` metadata is not surfaced to callers.

## Release Framing

### Cognition

- Verified knowledge retrieval is a curated fallback capability, not a new business skill.
- The orchestrator now has a read-only knowledge path that can answer from reviewed content before static fallback.

### Action

- Tailmate can now answer supported factual questions from a reviewed knowledge corpus through either direct PostgreSQL search or the Cloud Run gateway.
- Admins can now manage reviewed chunks through narrow internal APIs and rebuild embeddings through a developer CLI command.
- The runtime now returns a localized out-of-scope message when the reviewed knowledge base cannot answer the question.

### Memory

- Knowledge chunks now live in `knowledge_chunks` and are loaded from reviewed JSONL records before rollout.
- The internal retrieval payload stays in `knowledge_base` metadata rather than becoming part of the public response schema.
