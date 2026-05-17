"""split_master_accounts_from_platform_connections"""

from alembic import op
import sqlalchemy as sa


revision = "d4a8f8c7e2b1"
down_revision = ("b3f0f8c1f2a1", "a72d9c5f4e11")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_platform_connections",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("platform_user_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("user_id", "platform"),
    )
    op.create_index(
        "uq_user_platform_connections_platform_platform_user_id",
        "user_platform_connections",
        ["platform", "platform_user_id"],
        unique=True,
    )
    op.create_index(
        "ix_user_platform_connections_user_id",
        "user_platform_connections",
        ["user_id"],
        unique=False,
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO user_platform_connections (
                user_id,
                platform,
                platform_user_id,
                status,
                connected_at,
                disconnected_at
            )
            SELECT
                user_id,
                platform,
                platform_user_id,
                CASE
                    WHEN status = 'active' THEN 'active'
                    ELSE 'pending_verification'
                END,
                created_at,
                NULL
            FROM users
            """
        )
    )

    op.drop_index("uq_users_platform_platform_user_id", table_name="users")
    op.drop_column("users", "platform_user_id")
    op.drop_column("users", "platform")


def downgrade() -> None:
    # WARNING: downgrade requires restoring the pre-split snapshot because collapsing multiple
    # platform connections back into one users row would silently discard connection history.
    raise NotImplementedError(
        "Migration d4a8f8c7e2b1 cannot be safely reversed. "
        "Restore a pre-migration database snapshot before removing platform-connection history."
    )
