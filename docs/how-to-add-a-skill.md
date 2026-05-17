# How To Add A Skill

Status: Controlled developer workflow for adding a new Tailmate skill

This guide describes the minimum end-to-end workflow for adding a new skill without breaking the frozen repository boundaries.

## 1. Generate The Scaffold

From the repository root:

```bash
uv run tailmate new-skill <skill_id>
```

The scaffold creates:

- the typed contract in `src/tailmate/contracts/`
- the adapter stub in `src/tailmate/adapters/<skill_id>/`
- the skill package and manifest in `src/tailmate/skills/<skill_id>/`
- unit, integration, and contract test stubs
- a controlled slice record in `docs/<skill_id>-slice.md`

## 2. Replace The Placeholder Fields

The scaffold intentionally generates `TODO_FIELD` placeholders.
Before wiring the skill, replace them with the real domain fields in:

- `src/tailmate/contracts/<skill_id>.py`
- `src/tailmate/adapters/<skill_id>/stub.py`
- `src/tailmate/skills/<skill_id>/skill.py`
- `src/tailmate/skills/<skill_id>/manifest.py`
- `docs/<skill_id>-slice.md`

Keep all code, comments, and technical documentation in English.

## 3. Register The Intent

Every new business capability must be reachable through the existing orchestration path.

Minimum intent wiring steps:

1. Define the intent string in `src/tailmate/agent_runtime/intent_classifier/intents.py`.
2. Add a routing rule in the rule-based classifier or update the LLM intent-classifier prompt.
3. Map the resolved intent to the new skill in the root-agent dispatch path.
4. Confirm the fallback behavior stays deterministic when the skill is disabled or unavailable.

Do not create a parallel routing stack outside the existing root-agent and orchestrator contracts.

## 4. Register The Adapter Dependency

The generated manifest expects an adapter dependency named `<skill_id>_adapter`.

Complete the runtime wiring by:

1. Adding the real adapter implementation behind the generated stub.
2. Registering the dependency builder in the container.
3. Updating the manifest dependency validation if the real adapter exposes a richer interface.

If the skill needs both local and cloud variants, keep the environment selection inside the existing container and adapter seams.

## 5. Add Persistence Carefully

If the skill needs durable state:

1. Add or update the database contract through Alembic migrations.
2. Update `docs/database-migration-runbook.md` if the migration process or rollback expectations change.
3. Keep the storage ownership inside the approved adapter layer.

Do not bypass the frozen contracts with direct ad-hoc persistence inside the skill implementation.

## 6. Expand The Tests

The generated unit test is intentionally minimal and runnable.
Before opening a Pull Request, extend it with:

- happy-path adapter behavior
- validation failures
- adapter error handling

Add integration or contract tests whenever the skill changes routing, persistence, deployment contracts, or public response behavior.

## 7. Update Specs

A skill is a vertical slice, not just a code drop.
Update the relevant spec documents in the same Pull Request:

- `docs/<skill_id>-slice.md`
- `CHANGELOG.md`
- `README.md` when the new skill changes the visible repository capability map
- any deployment or migration documents affected by the new capability

## 8. Pre-PR Checklist

Before opening a merge-ready Pull Request:

```bash
uv run python -m compileall src
uv run mypy
uv run bandit -c pyproject.toml -r src
uv run python -m pytest tests/unit
```

Also run the generated skill-specific test directly:

```bash
uv run python -m pytest tests/unit/test_<skill_id>_skill.py
```
