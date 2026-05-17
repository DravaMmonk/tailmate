# Database Migration Runbook

Status: Versioned operational runbook for Alembic-managed schema changes

This runbook defines the minimum safe process for database schema changes in Tailmate.
It covers migration generation, staging validation, production execution, dry-run review, and rollback planning for PostgreSQL-backed deployments.

## Scope

Use this runbook for every change that adds, removes, renames, or rewrites database schema in `src/tailmate/adapters/database/migrations/`.

This process applies to direct database deployments and to gateway-backed deployments that still depend on the same Alembic-managed schema.

## Prerequisites

- A clean working tree on a feature branch
- The target revision reviewed in code before any environment is changed
- A staging database or clone that matches the production schema as closely as possible
- A known-good backup or restore point for any production rollout
- Access to the target database URL through `TAILMATE_ALEMBIC_DATABASE_URL`

## 1. Generate The Migration

Create the revision from the repository root:

```bash
uv run alembic revision --autogenerate -m "describe the schema change"
```

Then review the generated file manually:

- verify the `upgrade()` block only contains the intended schema change
- verify the `downgrade()` block is the best available rollback path
- remove accidental column drops, table drops, or index changes before merging
- confirm the revision name, docstrings, and identifiers remain in English

If autogenerate produces unexpected operations, fix the model definitions first and regenerate the migration.

## 2. Validate In Staging

Before production rollout, validate the revision against a staging database:

```bash
TAILMATE_ALEMBIC_DATABASE_URL="$STAGING_DATABASE_URL" uv run alembic check
TAILMATE_ALEMBIC_DATABASE_URL="$STAGING_DATABASE_URL" uv run alembic upgrade head
TAILMATE_ALEMBIC_DATABASE_URL="$STAGING_DATABASE_URL" uv run alembic current
```

Use the staging validation to confirm:

- the migration applies cleanly
- the application still starts against the upgraded schema
- the expected revision appears in `alembic current`
- feature-specific smoke tests still pass after the upgrade

If the migration changes application behavior, run the relevant unit, contract, or integration tests before promoting the release.

## 3. Production Execution

Do not run a production upgrade until the staging validation is complete and the release has been approved.

Use a dry run first:

```bash
TAILMATE_ALEMBIC_DATABASE_URL="$PRODUCTION_DATABASE_URL" uv run alembic upgrade head --sql > migration.sql
```

Review the generated SQL before execution:

- confirm the statements match the expected schema change
- confirm the SQL does not include unintended data loss
- confirm any `ALTER TABLE` or `CREATE INDEX` operations are acceptable for the maintenance window

After review, apply the live migration:

```bash
TAILMATE_ALEMBIC_DATABASE_URL="$PRODUCTION_DATABASE_URL" uv run alembic upgrade head
TAILMATE_ALEMBIC_DATABASE_URL="$PRODUCTION_DATABASE_URL" uv run alembic current
```

Follow the deployment with the relevant application health checks and a schema-aware smoke test.

## 4. Rollback

Before running `alembic downgrade`, classify the target revision boundary.

| Revision | Outcome | Rollback note |
| --- | --- | --- |
| `5e6e5005b32c` | B | Downgrade drops `conversation_sessions`; restore from backup if turn history must survive. |
| `46ecbdc4202a` | B | Downgrade drops `media_assets` rows and media metadata references. |
| `9a78bfa8b6e2` | B | Downgrade drops `dog_profiles` and `profile_enrichment_log`. |
| `a72d9c5f4e11` | B | Downgrade drops `knowledge_chunks` and reviewed embedding state. |
| `0c2b5a17d9f1` | C | Snapshot required; automatic downgrade is intentionally disabled. |
| `b3f0f8c1f2a1` | B | Downgrade drops `uploaded_by` attribution values from `media_assets`. |
| `d4a8f8c7e2b1` | C | Snapshot required; automatic downgrade is intentionally disabled. |
| `c1e9f6a3b2d4` | B | Downgrade drops `public_query_rate_limit_events` and the recorded window state. |
| `e2b8f1d4c3a5` | B | Downgrade drops `processed_webhook_events` idempotency history and `audit_events` mutation history. |

Outcome legend:

- A: Safe and tested reversal.
- B: Reversal is allowed but drops data; restore from backup if the dropped data matters.
- C: Reversal is not safe; restore a pre-migration snapshot instead of running `alembic downgrade`.

Do not run `alembic downgrade` across a C-class boundary. Restore the pre-migration snapshot first, then bring the application back to the last known-good revision.

If the migration has not introduced irreversible data loss, roll back with Alembic:

```bash
TAILMATE_ALEMBIC_DATABASE_URL="$PRODUCTION_DATABASE_URL" uv run alembic downgrade -1
```

If you need to return to a specific revision, downgrade to that revision explicitly:

```bash
TAILMATE_ALEMBIC_DATABASE_URL="$PRODUCTION_DATABASE_URL" uv run alembic downgrade <revision_id>
```

If the schema change is destructive or the data transformation cannot be reversed safely, restore from backup first and then re-apply the last known good revision.

## 5. High-Risk Migration Checklist

Treat the migration as high risk if it includes any of the following:

- dropping a column or table
- renaming a column, table, or constraint
- changing nullability or uniqueness constraints
- converting a column to a new type
- rewriting large data sets during the migration
- creating or rebuilding a large index
- changing a foreign key or primary key relationship

Before production execution, confirm all of the following:

- the rollback path is documented and tested
- the dry-run SQL has been reviewed by another engineer when possible
- the deployment window is approved
- the backup or restore point is current
- the application release is compatible with both the pre-migration and post-migration schema when a rolling rollout is expected

If any item is unresolved, do not apply the production migration.
