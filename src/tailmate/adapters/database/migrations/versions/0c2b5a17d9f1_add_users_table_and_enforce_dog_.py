"""add_users_table_and_enforce_dog_profile_ownership"""

from alembic import op
import sqlalchemy as sa


revision = "0c2b5a17d9f1"
down_revision = "9a78bfa8b6e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("platform_user_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "uq_users_platform_platform_user_id",
        "users",
        ["platform", "platform_user_id"],
        unique=True,
    )

    bind = op.get_bind()
    null_owner_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM dog_profiles WHERE user_id IS NULL")
    ).scalar_one()
    if null_owner_count:
        raise RuntimeError(
            "Cannot enforce dog_profiles.user_id ownership while null owners still exist."
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO users (user_id, platform, platform_user_id, status, role)
            SELECT DISTINCT user_id, 'web', user_id, 'pending', 'owner'
            FROM dog_profiles
            WHERE user_id IS NOT NULL
            ON CONFLICT (user_id) DO NOTHING
            """
        )
    )

    op.alter_column(
        "dog_profiles",
        "user_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.create_index("ix_dog_profiles_user_id", "dog_profiles", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_dog_profiles_user_id_users",
        "dog_profiles",
        "users",
        ["user_id"],
        ["user_id"],
    )


def downgrade() -> None:
    # WARNING: downgrade requires restoring the pre-users snapshot because account ownership
    # data cannot be recovered safely after the users table and dog ownership FK are applied.
    raise NotImplementedError(
        "Migration 0c2b5a17d9f1 cannot be safely reversed. "
        "Restore a pre-migration database snapshot before removing enforced dog ownership."
    )
