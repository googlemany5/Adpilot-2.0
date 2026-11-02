import pytest

from fastapi import HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from rate_limiter import enforce_rate_limit


@pytest.fixture
def rate_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def make_request(ip="192.0.2.10"):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/auth/login",
        "raw_path": b"/auth/login",
        "query_string": b"",
        "headers": [],
        "client": (ip, 12345),
        "server": ("testserver", 80),
    })


def test_ip_limit_blocks_request_after_limit(rate_db):
    request = make_request()

    for _ in range(2):
        enforce_rate_limit(
            rate_db, request, "test-ip",
            ip_limit=2,
            window_seconds=900,
        )

    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(
            rate_db, request, "test-ip",
            ip_limit=2,
            window_seconds=900,
        )

    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0


def test_identity_limit_blocks_requests_across_ips(rate_db):
    for ip in ("192.0.2.10", "192.0.2.11"):
        enforce_rate_limit(
            rate_db,
            make_request(ip),
            "test-identity",
            identity="Person@Example.com",
            ip_limit=10,
            identity_limit=2,
            window_seconds=900,
        )

    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(
            rate_db,
            make_request("192.0.2.12"),
            "test-identity",
            identity="person@example.com",
            ip_limit=10,
            identity_limit=2,
            window_seconds=900,
        )

    assert exc.value.status_code == 429


def test_different_identities_have_separate_identity_limits(rate_db):
    for identity in ("one@example.com", "two@example.com"):
        enforce_rate_limit(
            rate_db,
            make_request(),
            "test-separate",
            identity=identity,
            ip_limit=5,
            identity_limit=1,
            window_seconds=900,
        )


def test_expired_buckets_are_cleaned(rate_db):
    from database import RateLimitBucketDB
    from sqlalchemy import select

    rate_db.add(
        RateLimitBucketDB(
            bucket_key="expired-test-bucket",
            request_count=99,
            window_start=1,
        )
    )
    rate_db.commit()

    enforce_rate_limit(
        rate_db,
        make_request(),
        "test-cleanup",
        ip_limit=5,
        window_seconds=900,
    )

    expired = rate_db.execute(
        select(RateLimitBucketDB).where(
            RateLimitBucketDB.bucket_key == "expired-test-bucket"
        )
    ).scalar_one_or_none()

    assert expired is None
