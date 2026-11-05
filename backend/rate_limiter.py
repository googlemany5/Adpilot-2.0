"""Atomic, database-backed authentication rate limiting."""

import hashlib
import ipaddress
import os
import time

from fastapi import HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from database import RateLimitBucketDB


def _bucket_key(scope: str, identity: str, window_start: int) -> str:
    raw = f"{scope}:{identity}:{window_start}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _client_ip_for_rate_limit(request: Request) -> str:
    """Use Cloudflare's visitor IP in production and the socket IP locally."""

    environment = os.getenv(
        "ADPILOT_ENVIRONMENT", "development"
    ).strip().lower()

    if environment == "production":
        cf_values = [
            value.decode("latin-1").strip()
            for name, value in request.scope.get("headers", [])
            if name.lower() == b"cf-connecting-ip"
        ]

        if len(cf_values) != 1:
            raise HTTPException(
                status_code=503,
                detail="Client IP could not be verified.",
            )

        try:
            return str(ipaddress.ip_address(cf_values[0]))
        except ValueError:
            raise HTTPException(
                status_code=503,
                detail="Client IP could not be verified.",
            )

    client = request.client
    return client.host if client and client.host else "unknown"


def _increment_bucket(db, table, dialect, key, window_start):
    values = {
        "bucket_key": key,
        "request_count": 1,
        "window_start": window_start,
    }

    if dialect == "sqlite":
        statement = sqlite_insert(table).values(**values)
    elif dialect == "postgresql":
        statement = postgres_insert(table).values(**values)
    else:
        raise RuntimeError("Rate limiting requires SQLite or PostgreSQL.")

    statement = statement.on_conflict_do_update(
        index_elements=["bucket_key"],
        set_={
            "request_count": table.c.request_count + 1,
            "window_start": window_start,
        },
    ).returning(table.c.request_count)

    return db.execute(statement).scalar_one()


def enforce_rate_limit(
    db,
    request: Request,
    scope: str,
    identity: str = "",
    ip_limit: int = 30,
    identity_limit: int | None = None,
    window_seconds: int = 900,
) -> None:
    """Count requests atomically using the verified client IP and optional identity."""

    if (
        isinstance(ip_limit, bool)
        or not isinstance(ip_limit, int)
        or ip_limit < 1
        or isinstance(window_seconds, bool)
        or not isinstance(window_seconds, int)
        or window_seconds < 1
    ):
        raise ValueError("Rate-limit settings must be positive integers.")

    if identity_limit is not None and (
        isinstance(identity_limit, bool)
        or not isinstance(identity_limit, int)
        or identity_limit < 1
    ):
        raise ValueError("Identity limit must be a positive integer.")

    if not isinstance(identity, str):
        raise ValueError("Rate-limit identity must be a string.")

    if not isinstance(scope, str) or not scope.strip():
        raise ValueError("Rate-limit scope must be a non-empty string.")

    ip_address = _client_ip_for_rate_limit(request)

    now = int(time.time())
    window_start = (now // window_seconds) * window_seconds

    table = RateLimitBucketDB.__table__
    dialect = db.get_bind().dialect.name

    checks = [("ip", ip_address, ip_limit)]

    normalized_identity = identity.strip().lower()
    if normalized_identity and identity_limit is not None:
        checks.append(("identity", normalized_identity, identity_limit))

    try:
        # Remove counters older than 24 hours.
        db.execute(
            delete(table).where(
                table.c.window_start < now - 86400
            )
        )

        for kind, value, limit in checks:
            key = _bucket_key(
                f"{scope}:{kind}",
                value,
                window_start,
            )

            count = _increment_bucket(
                db,
                table,
                dialect,
                key,
                window_start,
            )

            if count > limit:
                db.commit()

                retry_after = max(
                    1,
                    window_start + window_seconds - now,
                )

                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

        db.commit()

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Authentication is temporarily unavailable.",
        )
