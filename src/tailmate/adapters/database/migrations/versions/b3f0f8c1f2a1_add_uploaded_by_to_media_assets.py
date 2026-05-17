"""add_uploaded_by_to_media_assets"""

from alembic import op
import sqlalchemy as sa


revision = "b3f0f8c1f2a1"
down_revision = "0c2b5a17d9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("uploaded_by", sa.String(length=255), nullable=True))


def downgrade() -> None:
    # WARNING: downgrade drops the uploaded_by attribution data from media_assets.
    op.drop_column("media_assets", "uploaded_by")
