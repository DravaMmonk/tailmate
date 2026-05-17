"""SQLAlchemy metadata for database-backed runtime state."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector


metadata = MetaData()
json_document = JSON().with_variant(JSONB, "postgresql")

conversation_sessions = Table(
    "conversation_sessions",
    metadata,
    Column("session_id", String(length=255), primary_key=True),
    Column("turns", JSON, nullable=False, server_default="[]"),
    Column("attributes", JSON, nullable=False, server_default="{}"),
)

public_query_rate_limit_events = Table(
    "public_query_rate_limit_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(length=255), nullable=False),
    Column(
        "occurred_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

processed_webhook_events = Table(
    "processed_webhook_events",
    metadata,
    Column("message_id", String(length=255), primary_key=True),
    Column(
        "received_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

media_assets = Table(
    "media_assets",
    metadata,
    Column("media_id", String(length=36), primary_key=True),
    Column("dog_id", String(length=255), nullable=False),
    Column("session_id", String(length=255), nullable=True),
    Column("resource_kind", String(length=64), nullable=False),
    Column("media_kind", String(length=32), nullable=False),
    Column("content_type", String(length=255), nullable=False),
    Column("source_filename", String(length=255), nullable=False),
    Column("logical_path", String(length=1024), nullable=False, unique=True),
    Column("media_ref", String(length=2048), nullable=False, unique=True),
    Column("uploaded_by", String(length=255), nullable=True),
    Column("sanitization_method", String(length=64), nullable=False),
    Column("sanitization_status", String(length=32), nullable=False, server_default="sanitized"),
    Column("metadata_stripped", Boolean, nullable=False, server_default=text("true")),
    Column("byte_size", Integer, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

users = Table(
    "users",
    metadata,
    Column("user_id", String(length=255), primary_key=True),
    Column("status", String(length=32), nullable=False),
    Column("role", String(length=32), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

user_platform_connections = Table(
    "user_platform_connections",
    metadata,
    Column("user_id", String(length=255), ForeignKey("users.user_id"), primary_key=True),
    Column("platform", String(length=64), primary_key=True),
    Column("platform_user_id", String(length=255), nullable=False),
    Column("status", String(length=32), nullable=False),
    Column(
        "connected_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("disconnected_at", DateTime(timezone=True), nullable=True),
)

dog_profiles = Table(
    "dog_profiles",
    metadata,
    Column("id", String(length=36), primary_key=True),
    Column("user_id", String(length=255), ForeignKey("users.user_id"), nullable=False),
    Column("name", String(length=255), nullable=False),
    Column("breed", String(length=255), nullable=True),
    Column("age_months", Integer, nullable=True),
    Column("weight_kg", Numeric(precision=6, scale=2), nullable=True),
    Column("sex", String(length=32), nullable=True),
    Column("neutered", Boolean, nullable=True),
    Column("medical_history", json_document, nullable=False, server_default="[]"),
    Column("allergies", json_document, nullable=False, server_default="[]"),
    Column("current_medications", json_document, nullable=False, server_default="[]"),
    Column("temperament", Text, nullable=True),
    Column("activity_level", String(length=64), nullable=True),
    Column("diet", Text, nullable=True),
    Column("raw_notes", json_document, nullable=False, server_default="[]"),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

profile_enrichment_log = Table(
    "profile_enrichment_log",
    metadata,
    Column("id", String(length=36), primary_key=True),
    Column("dog_id", String(length=36), ForeignKey("dog_profiles.id"), nullable=False),
    Column("source_message", Text, nullable=False),
    Column("strategy_used", String(length=64), nullable=False),
    Column("extracted_fields", json_document, nullable=False, server_default="{}"),
    Column("confidence", Numeric(precision=4, scale=3), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("trace_id", String(length=64), nullable=False),
    Column("user_id", String(length=255), nullable=False),
    Column("entity_type", String(length=64), nullable=False),
    Column("entity_id", String(length=255), nullable=False),
    Column("action", String(length=32), nullable=False),
    Column("before", json_document, nullable=True),
    Column("after", json_document, nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

knowledge_chunks = Table(
    "knowledge_chunks",
    metadata,
    Column("id", String(length=36), primary_key=True),
    Column("content", Text, nullable=False),
    Column("category", String(length=64), nullable=True),
    Column("source_label", String(length=255), nullable=False),
    Column("locale", String(length=16), nullable=False, server_default="en-AU"),
    Column("embedding", Vector(768), nullable=False),
    Column("reviewed_at", DateTime(timezone=True), nullable=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

Index(
    "uq_user_platform_connections_platform_platform_user_id",
    user_platform_connections.c.platform,
    user_platform_connections.c.platform_user_id,
    unique=True,
)
Index(
    "ix_public_query_rate_limit_events_user_id_occurred_at",
    public_query_rate_limit_events.c.user_id,
    public_query_rate_limit_events.c.occurred_at,
)
Index("ix_user_platform_connections_user_id", user_platform_connections.c.user_id)
Index("ix_dog_profiles_user_id", dog_profiles.c.user_id)
Index(
    "ix_audit_events_user_entity",
    audit_events.c.user_id,
    audit_events.c.entity_type,
    audit_events.c.entity_id,
)
