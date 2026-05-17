"""add_knowledge_chunks_table_for_verified_knowledge_base"""

from alembic import op


revision = "a72d9c5f4e11"
down_revision = "9a78bfa8b6e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE knowledge_chunks (
            id VARCHAR(36) PRIMARY KEY,
            content TEXT NOT NULL,
            category VARCHAR(64),
            source_label VARCHAR(255) NOT NULL,
            locale VARCHAR(16) NOT NULL DEFAULT 'en-AU',
            embedding vector(768) NOT NULL,
            reviewed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_knowledge_chunks_embedding
        ON knowledge_chunks
        USING ivfflat (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    # WARNING: downgrade drops knowledge_chunks content and reviewed embedding state.
    op.drop_index("ix_knowledge_chunks_embedding", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
