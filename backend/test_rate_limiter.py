import pytest

from fastapi import HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from rate_limiter import enforce_rate_limit


@pytest.fixture
def rate_db(monkeypatch):
    monkeypatch.setenv("ADPILOT_ENVIRONMENT", "development")
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


def make_request(ip="192.0.2.10", headers=None):
    encoded_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or [])
    ]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/auth/login",
        "raw_path": b"/auth/login",
        "query_string": b"",
        "headers": encoded_headers,
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


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ip_limit": 0},
        {"ip_limit": -1},
        {"ip_limit": True},
        {"ip_limit": 1.5},
        {"identity_limit": 0},
        {"identity_limit": -1},
        {"identity_limit": True},
        {"identity_limit": 1.5},
        {"window_seconds": 0},
        {"window_seconds": -1},
        {"window_seconds": True},
    ],
)
def test_invalid_rate_limit_settings_are_rejected(rate_db, kwargs):
    with pytest.raises(ValueError):
        enforce_rate_limit(
            rate_db,
            make_request(),
            "invalid-settings",
            **kwargs,
        )


def test_non_string_identity_is_rejected(rate_db):
    with pytest.raises(ValueError):
        enforce_rate_limit(
            rate_db,
            make_request(),
            "invalid-identity",
            identity=123,
            identity_limit=5,
        )


def test_blank_identity_does_not_create_identity_bucket(rate_db):
    from sqlalchemy import select
    from database import RateLimitBucketDB

    enforce_rate_limit(
        rate_db,
        make_request(),
        "blank-identity",
        identity="   ",
        identity_limit=5,
    )

    buckets = rate_db.execute(
        select(RateLimitBucketDB)
    ).scalars().all()

    assert len(buckets) == 1


def test_cloudflare_ip_is_used_instead_of_x_forwarded_for(
    rate_db, monkeypatch
):
    monkeypatch.setenv("ADPILOT_ENVIRONMENT", "production")

    first = make_request(
        "10.0.0.1",
        [
            ("CF-Connecting-IP", "203.0.113.50"),
            ("X-Forwarded-For", "198.51.100.1"),
        ],
    )

    second = make_request(
        "10.0.0.2",
        [
            ("CF-Connecting-IP", "203.0.113.50"),
            ("X-Forwarded-For", "198.51.100.99"),
        ],
    )

    enforce_rate_limit(
        rate_db, first, "cloudflare-test",
        ip_limit=1, window_seconds=900,
    )

    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(
            rate_db, second, "cloudflare-test",
            ip_limit=1, window_seconds=900,
        )

    assert exc.value.status_code == 429


def test_different_cloudflare_ips_get_separate_buckets(
    rate_db, monkeypatch
):
    monkeypatch.setenv("ADPILOT_ENVIRONMENT", "production")

    for visitor_ip in ("203.0.113.10", "203.0.113.11"):
        enforce_rate_limit(
            rate_db,
            make_request(
                "10.0.0.1",
                [("CF-Connecting-IP", visitor_ip)],
            ),
            "cloudflare-separate",
            ip_limit=1,
            window_seconds=900,
        )


def test_production_rejects_missing_cloudflare_ip(
    rate_db, monkeypatch
):
    monkeypatch.setenv("ADPILOT_ENVIRONMENT", "production")

    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(
            rate_db,
            make_request(),
            "missing-cloudflare-ip",
        )

    assert exc.value.status_code == 503


@pytest.mark.parametrize(
    "headers",
    [
        [("CF-Connecting-IP", "not-an-ip-address")],
        [
            ("CF-Connecting-IP", "203.0.113.10"),
            ("CF-Connecting-IP", "203.0.113.11"),
        ],
    ],
)
def test_production_rejects_invalid_or_duplicate_cloudflare_ip(
    rate_db, monkeypatch, headers
):
    monkeypatch.setenv("ADPILOT_ENVIRONMENT", "production")

    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(
            rate_db,
            make_request(headers=headers),
            "invalid-cloudflare-ip",
        )

    assert exc.value.status_code == 503


def test_development_ignores_cloudflare_header(rate_db, monkeypatch):
    monkeypatch.setenv("ADPILOT_ENVIRONMENT", "development")

    first = make_request(
        "192.0.2.10",
        [("CF-Connecting-IP", "203.0.113.50")],
    )
    second = make_request(
        "192.0.2.10",
        [("CF-Connecting-IP", "203.0.113.99")],
    )

    enforce_rate_limit(
        rate_db, first, "development-ip-test",
        ip_limit=1, window_seconds=900,
    )

    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(
            rate_db, second, "development-ip-test",
            ip_limit=1, window_seconds=900,
        )

    assert exc.value.status_code == 429
