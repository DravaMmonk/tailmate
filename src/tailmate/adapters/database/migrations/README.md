# Database Migrations

This directory owns Alembic-based schema history for the database-backed conversation state.
This file is a controlled migration document and must be updated when the migration workflow or schema ownership rules change.

Rules:

- every schema change must be represented as a migration script
- runtime code must not create or mutate production schema ad hoc
