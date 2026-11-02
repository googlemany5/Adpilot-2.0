"""Atomic, database-backed authentication rate limiting."""

import hashlib
import time

from fastapi import HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from database import RateLimitBucketDB


def _bucket_key(scope: str, identity: str, window_start: int) -> str:
    raw = f"{scope}:{identity}:{window_start}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    """Count requests atomically using the direct client IP and optional identity."""
    if ip_limit < 1 or window_seconds < 1:
        raise ValueError("Rate-limit settings must be positive.")

    client = request.client
    ip_address = client.host if client else "unknown"

    now = int(time.time())
    window_start = (now // window_seconds) * window_seconds

    table = RateLimitBucketDB.__table__
    dialect = db.get_bind().dialect.name

    checks = [("ip", ip_address, ip_limit)]

    if identity and identity_limit is not None:
        checks.append(("identity", identity.strip().lower(), identity_limit))

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
