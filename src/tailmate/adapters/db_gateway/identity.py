"""Identity resolution helpers shared by the gateway routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import user_platform_connections, users
from tailmate.contracts.constants import PUBLIC_QUERY_PLATFORM
from tailmate.contracts.errors import AuthorizationError, ConflictError, DomainError
from tailmate.tracing import start_span
from sqlalchemy import Select, and_, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError


@dataclass(frozen=True)
class ResolvedUserAccount:
    """Master account data loaded from the canonical users table."""

    user_id: str
    status: str
    role: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class ResolvedPlatformIdentity:
    """Master account plus platform-connection data for a caller identity."""

    user_id: str
    status: str
    role: str
    platform: str
    platform_user_id: str
    connection_status: str
    user_created_at: datetime | None = None
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None


@dataclass(frozen=True)
class DatabaseUserIdentityResolver:
    """Resolve and mutate user accounts plus platform bindings."""

    engine_factory: DatabaseEngineFactory

    def load_user(self, user_id: str) -> ResolvedUserAccount | None:
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            return None
        with start_span(
            "db.identity.load_user",
            attributes={"db.system": "postgresql", "db.operation": "select"},
        ):
            return self._load_user_account(
                select(
                    users.c.user_id,
                    users.c.status,
                    users.c.role,
                    users.c.created_at,
                ).where(users.c.user_id == normalized_user_id)
            )

    def resolve_platform_identity(
        self,
        *,
        platform: str,
        platform_user_id: str,
    ) -> ResolvedPlatformIdentity | None:
        normalized_platform = platform.strip()
        normalized_platform_user_id = platform_user_id.strip()
        if not normalized_platform or not normalized_platform_user_id:
            return None
        with start_span(
            "db.identity.resolve_platform_identity",
            attributes={"db.system": "postgresql", "db.operation": "select"},
        ):
            return self._load_platform_identity(
                select(
                    users.c.user_id,
                    users.c.status,
                    users.c.role,
                    users.c.created_at.label("user_created_at"),
                    user_platform_connections.c.platform,
                    user_platform_connections.c.platform_user_id,
                    user_platform_connections.c.status.label("connection_status"),
                    user_platform_connections.c.connected_at,
                    user_platform_connections.c.disconnected_at,
                )
                .select_from(
                    users.join(
                        user_platform_connections,
                        users.c.user_id == user_platform_connections.c.user_id,
                    )
                )
                .where(
                    user_platform_connections.c.platform == normalized_platform,
                    user_platform_connections.c.platform_user_id == normalized_platform_user_id,
                )
            )

    def register_web_user(self, *, firebase_uid: str) -> ResolvedPlatformIdentity:
        normalized_user_id = firebase_uid.strip()
        if not normalized_user_id:
            raise DomainError("A Firebase uid is required.")

        with start_span(
            "db.identity.register_web_user",
            attributes={"db.system": "postgresql", "db.operation": "insert"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    try:
                        with connection.begin_nested():
                            connection.execute(
                                users.insert().values(
                                    user_id=normalized_user_id,
                                    status="pending",
                                    role="owner",
                                )
                            )
                    except IntegrityError:
                        pass

                    self._upsert_platform_connection(
                        connection,
                        user_id=normalized_user_id,
                        platform=PUBLIC_QUERY_PLATFORM,
                        platform_user_id=normalized_user_id,
                        status="active",
                    )
            finally:
                engine.dispose()

        identity = self.resolve_platform_identity(
            platform=PUBLIC_QUERY_PLATFORM,
            platform_user_id=normalized_user_id,
        )
        if identity is None:
            raise DomainError("The web user could not be registered.")
        return identity

    def ensure_active_platform_user(
        self,
        *,
        platform: str,
        platform_user_id: str,
        role: str = "owner",
    ) -> tuple[ResolvedPlatformIdentity, bool]:
        normalized_platform = platform.strip()
        normalized_platform_user_id = platform_user_id.strip()
        normalized_role = role.strip() or "owner"
        if not normalized_platform or not normalized_platform_user_id:
            raise DomainError("platform and platform_user_id are required.")
        if normalized_platform == PUBLIC_QUERY_PLATFORM:
            raise DomainError("The web platform cannot be auto-provisioned through the bridge.")

        with start_span(
            "db.identity.ensure_active_platform_user",
            attributes={"db.system": "postgresql", "db.operation": "upsert"},
        ):
            existing_identity = self.resolve_platform_identity(
                platform=normalized_platform,
                platform_user_id=normalized_platform_user_id,
            )
            if existing_identity is not None:
                if existing_identity.status == "suspended":
                    raise AuthorizationError("The authenticated user account is suspended.")
                if (
                    existing_identity.status == "active"
                    and existing_identity.connection_status == "active"
                ):
                    return existing_identity, False

                engine = self.engine_factory.create()
                try:
                    with engine.begin() as connection:
                        connection.execute(
                            update(users)
                            .where(users.c.user_id == existing_identity.user_id)
                            .values(status="active")
                        )
                        self._upsert_platform_connection(
                            connection,
                            user_id=existing_identity.user_id,
                            platform=normalized_platform,
                            platform_user_id=normalized_platform_user_id,
                            status="active",
                        )
                finally:
                    engine.dispose()

                refreshed_identity = self.resolve_platform_identity(
                    platform=normalized_platform,
                    platform_user_id=normalized_platform_user_id,
                )
                if refreshed_identity is None:
                    raise DomainError("The platform user could not be activated.")
                return refreshed_identity, False

            generated_user_id = f"user-{uuid4().hex}"
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    connection.execute(
                        users.insert().values(
                            user_id=generated_user_id,
                            status="active",
                            role=normalized_role,
                        )
                    )
                    self._upsert_platform_connection(
                        connection,
                        user_id=generated_user_id,
                        platform=normalized_platform,
                        platform_user_id=normalized_platform_user_id,
                        status="active",
                    )
            except ConflictError:
                recovered_identity = self.resolve_platform_identity(
                    platform=normalized_platform,
                    platform_user_id=normalized_platform_user_id,
                )
                if recovered_identity is None:
                    raise
                if recovered_identity.status == "suspended":
                    raise AuthorizationError("The authenticated user account is suspended.")
                if (
                    recovered_identity.status != "active"
                    or recovered_identity.connection_status != "active"
                ):
                    return self.ensure_active_platform_user(
                        platform=normalized_platform,
                        platform_user_id=normalized_platform_user_id,
                        role=normalized_role,
                    )
                return recovered_identity, False
            finally:
                engine.dispose()

            identity = self.resolve_platform_identity(
                platform=normalized_platform,
                platform_user_id=normalized_platform_user_id,
            )
            if identity is None:
                raise DomainError("The platform user could not be provisioned.")
            return identity, True

    def activate_user(self, *, user_id: str) -> ResolvedUserAccount:
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            raise DomainError("A user_id is required.")

        with start_span(
            "db.identity.activate_user",
            attributes={"db.system": "postgresql", "db.operation": "update"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    row = connection.execute(
                        select(users.c.status).where(users.c.user_id == normalized_user_id)
                    ).mappings().first()
                    if row is None:
                        raise AuthorizationError("The authenticated user is not bound to a Tailmate account.")
                    if str(row["status"]) == "suspended":
                        raise AuthorizationError("The authenticated user account is suspended.")
                    connection.execute(
                        update(users)
                        .where(users.c.user_id == normalized_user_id)
                        .values(status="active")
                    )
            finally:
                engine.dispose()

        account = self.load_user(normalized_user_id)
        if account is None:
            raise DomainError("The user could not be activated.")
        return account

    def upsert_platform_connection(
        self,
        *,
        user_id: str,
        platform: str,
        platform_user_id: str,
        status: str,
    ) -> ResolvedPlatformIdentity:
        normalized_user_id = user_id.strip()
        normalized_platform = platform.strip()
        normalized_platform_user_id = platform_user_id.strip()
        normalized_status = status.strip()
        if not normalized_user_id or not normalized_platform or not normalized_platform_user_id:
            raise DomainError("user_id, platform, and platform_user_id are required.")
        if not normalized_status:
            raise DomainError("status is required.")

        with start_span(
            "db.identity.upsert_platform_connection",
            attributes={"db.system": "postgresql", "db.operation": "upsert"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    if connection.execute(
                        select(users.c.user_id).where(users.c.user_id == normalized_user_id)
                    ).first() is None:
                        raise AuthorizationError(
                            "The authenticated user is not bound to a Tailmate account."
                        )

                    self._upsert_platform_connection(
                        connection,
                        user_id=normalized_user_id,
                        platform=normalized_platform,
                        platform_user_id=normalized_platform_user_id,
                        status=normalized_status,
                    )
            finally:
                engine.dispose()

        identity = self.resolve_platform_identity(
            platform=normalized_platform,
            platform_user_id=normalized_platform_user_id,
        )
        if identity is None:
            raise DomainError("The platform connection could not be saved.")
        return identity

    def disconnect_platform_connection(
        self,
        *,
        user_id: str,
        platform: str,
    ) -> ResolvedPlatformIdentity | None:
        normalized_user_id = user_id.strip()
        normalized_platform = platform.strip()
        if not normalized_user_id or not normalized_platform:
            raise DomainError("user_id and platform are required.")

        with start_span(
            "db.identity.disconnect_platform_connection",
            attributes={"db.system": "postgresql", "db.operation": "update"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    row = connection.execute(
                        select(user_platform_connections.c.platform_user_id).where(
                            user_platform_connections.c.user_id == normalized_user_id,
                            user_platform_connections.c.platform == normalized_platform,
                        )
                    ).mappings().first()
                    if row is None:
                        return None

                    connection.execute(
                        update(user_platform_connections)
                        .where(
                            user_platform_connections.c.user_id == normalized_user_id,
                            user_platform_connections.c.platform == normalized_platform,
                        )
                        .values(
                            status="disconnected",
                            disconnected_at=datetime.now(timezone.utc),
                        )
                    )
                    normalized_platform_user_id = str(row["platform_user_id"])
            finally:
                engine.dispose()

        return self.resolve_platform_identity(
            platform=normalized_platform,
            platform_user_id=normalized_platform_user_id,
        )

    def _load_user_account(self, statement: Select[tuple[object, ...]]) -> ResolvedUserAccount | None:
        engine = self.engine_factory.create()
        try:
            with engine.begin() as connection:
                row = connection.execute(statement).mappings().first()
        finally:
            engine.dispose()

        if row is None:
            return None
        return ResolvedUserAccount(
            user_id=str(row["user_id"]),
            status=str(row["status"]),
            role=str(row["role"]),
            created_at=row.get("created_at"),
        )

    def _load_platform_identity(
        self,
        statement: Select[tuple[object, ...]],
    ) -> ResolvedPlatformIdentity | None:
        engine = self.engine_factory.create()
        try:
            with engine.begin() as connection:
                row = connection.execute(statement).mappings().first()
        finally:
            engine.dispose()

        if row is None:
            return None
        return ResolvedPlatformIdentity(
            user_id=str(row["user_id"]),
            status=str(row["status"]),
            role=str(row["role"]),
            platform=str(row["platform"]),
            platform_user_id=str(row["platform_user_id"]),
            connection_status=str(row["connection_status"]),
            user_created_at=row.get("user_created_at"),
            connected_at=row.get("connected_at"),
            disconnected_at=row.get("disconnected_at"),
        )

    @staticmethod
    def _upsert_platform_connection(
        connection: Connection,
        *,
        user_id: str,
        platform: str,
        platform_user_id: str,
        status: str,
    ) -> None:
        conflicting_connection = connection.execute(
            select(user_platform_connections.c.user_id).where(
                user_platform_connections.c.platform == platform,
                user_platform_connections.c.platform_user_id == platform_user_id,
                user_platform_connections.c.user_id != user_id,
            )
        ).first()
        if conflicting_connection is not None:
            raise ConflictError(
                f"Platform identity '{platform}:{platform_user_id}' is already connected to another account."
            )

        existing_connection = connection.execute(
            select(user_platform_connections.c.user_id).where(
                and_(
                    user_platform_connections.c.user_id == user_id,
                    user_platform_connections.c.platform == platform,
                )
            )
        ).first()
        if existing_connection is None:
            connection.execute(
                user_platform_connections.insert().values(
                    user_id=user_id,
                    platform=platform,
                    platform_user_id=platform_user_id,
                    status=status,
                    disconnected_at=None,
                )
            )
            return

        values: dict[str, object] = {
            "platform_user_id": platform_user_id,
            "status": status,
        }
        if status == "disconnected":
            values["disconnected_at"] = datetime.now(timezone.utc)
        else:
            values["disconnected_at"] = None
        connection.execute(
            update(user_platform_connections)
            .where(
                and_(
                    user_platform_connections.c.user_id == user_id,
                    user_platform_connections.c.platform == platform,
                )
            )
            .values(**values)
        )


def build_internal_session_id(
    *,
    user_id: str,
    platform: str,
    external_conversation_id: str,
) -> str:
    """Return the internal namespaced session id used behind the public gateway."""

    return (
        f"{user_id.strip()}__{platform.strip()}__{external_conversation_id.strip()}"
    )


def generate_external_session_id() -> str:
    """Return a new caller-visible session id."""

    return f"session-{uuid4().hex[:12]}"
