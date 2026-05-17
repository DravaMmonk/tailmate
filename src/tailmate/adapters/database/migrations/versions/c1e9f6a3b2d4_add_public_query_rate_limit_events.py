"""add_public_query_rate_limit_events"""

from alembic import op
import sqlalchemy as sa


revision = "c1e9f6a3b2d4"
down_revision = "d4a8f8c7e2b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_query_rate_limit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_public_query_rate_limit_events_user_id_occurred_at",
        "public_query_rate_limit_events",
        ["user_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    # WARNING: downgrade drops public_query_rate_limit_events and the recorded abuse window state.
    op.drop_index(
        "ix_public_query_rate_limit_events_user_id_occurred_at",
        table_name="public_query_rate_limit_events",
    )
    op.drop_table("public_query_rate_limit_events")
