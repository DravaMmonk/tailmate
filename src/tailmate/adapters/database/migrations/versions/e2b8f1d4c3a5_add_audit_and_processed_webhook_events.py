"""add_audit_and_processed_webhook_events"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e2b8f1d4c3a5"
down_revision = "c1e9f6a3b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processed_webhook_events",
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "after",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_user_entity",
        "audit_events",
        ["user_id", "entity_type", "entity_id"],
        unique=False,
    )


def downgrade() -> None:
    # WARNING: downgrade drops audit_events and processed_webhook_events history.
    op.drop_index("ix_audit_events_user_entity", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("processed_webhook_events")
