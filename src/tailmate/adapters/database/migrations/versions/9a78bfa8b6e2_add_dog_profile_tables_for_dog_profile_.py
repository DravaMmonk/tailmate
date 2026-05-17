"""add_dog_profile_tables_for_dog_profile_skill"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a78bfa8b6e2"
down_revision = "46ecbdc4202a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dog_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("breed", sa.String(length=255), nullable=True),
        sa.Column("age_months", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("sex", sa.String(length=32), nullable=True),
        sa.Column("neutered", sa.Boolean(), nullable=True),
        sa.Column(
            "medical_history",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "allergies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "current_medications",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("temperament", sa.Text(), nullable=True),
        sa.Column("activity_level", sa.String(length=64), nullable=True),
        sa.Column("diet", sa.Text(), nullable=True),
        sa.Column(
            "raw_notes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "profile_enrichment_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dog_id", sa.String(length=36), nullable=False),
        sa.Column("source_message", sa.Text(), nullable=False),
        sa.Column("strategy_used", sa.String(length=64), nullable=False),
        sa.Column(
            "extracted_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dog_id"], ["dog_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_profile_enrichment_log_dog_id",
        "profile_enrichment_log",
        ["dog_id"],
        unique=False,
    )


def downgrade() -> None:
    # WARNING: downgrade drops dog_profiles and profile_enrichment_log data.
    op.drop_index("ix_profile_enrichment_log_dog_id", table_name="profile_enrichment_log")
    op.drop_table("profile_enrichment_log")
    op.drop_table("dog_profiles")
