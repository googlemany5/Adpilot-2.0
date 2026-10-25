import httpx
import pytest
from fastapi import HTTPException

import account_discovery as discovery


class FakeResponse:
    def __init__(self, payload, error=None):
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


def api_error():
    request = httpx.Request("GET", "https://example.com")
    return httpx.RequestError("Simulated network failure", request=request)


# Google Ads tests

def test_google_requires_developer_token(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "v99")
    monkeypatch.delenv("GOOGLE_ADS_DEVELOPER_TOKEN", raising=False)

    with pytest.raises(HTTPException) as exc:
        discovery.discover_google_accounts("fake-token")

    assert exc.value.status_code == 503


def test_google_requires_valid_api_version(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "invalid")
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "fake-developer-token")

    with pytest.raises(HTTPException) as exc:
        discovery.discover_google_accounts("fake-token")

    assert exc.value.status_code == 503


def test_google_returns_accessible_customer_ids(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "v99")
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "fake-developer-token")
    monkeypatch.setattr(
        discovery.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse({
            "resourceNames": ["customers/123456", "customers/987654"]
        }),
    )

    result = discovery.discover_google_accounts("fake-token")

    assert result == [
        {"account_id": "123456", "name": None, "platform": "google"},
        {"account_id": "987654", "name": None, "platform": "google"},
    ]


def test_google_ignores_malformed_customer_ids(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "v99")
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "fake-developer-token")
    monkeypatch.setattr(
        discovery.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse({
            "resourceNames": ["customers/123", "invalid", 42, "customers/a12"]
        }),
    )

    result = discovery.discover_google_accounts("fake-token")

    assert [account["account_id"] for account in result] == ["123"]


def test_google_rejects_invalid_response_shape(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "v99")
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "fake-developer-token")
    monkeypatch.setattr(
        discovery.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse({"resourceNames": "not-a-list"}),
    )

    with pytest.raises(HTTPException) as exc:
        discovery.discover_google_accounts("fake-token")

    assert exc.value.status_code == 502


def test_google_network_failure_is_handled(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "v99")
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "fake-developer-token")
    monkeypatch.setattr(
        discovery.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse({}, error=api_error()),
    )

    with pytest.raises(HTTPException) as exc:
        discovery.discover_google_accounts("fake-token")

    assert exc.value.status_code == 502


# Meta Ads tests

def test_meta_requires_valid_api_version(monkeypatch):
    monkeypatch.setenv("META_GRAPH_API_VERSION", "invalid")

    with pytest.raises(HTTPException) as exc:
        discovery.discover_meta_accounts("fake-token")

    assert exc.value.status_code == 503


def test_meta_returns_account_details(monkeypatch):
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v99.0")
    monkeypatch.setattr(
        discovery.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({
            "data": [
                {
                    "id": "act_123",
                    "account_id": "123",
                    "name": "Example Account",
                    "account_status": 1,
                },
                {"id": "act_456", "name": "Second Account"},
            ]
        }),
    )

    result = discovery.discover_meta_accounts("fake-token")

    assert result == [
        {
            "account_id": "123",
            "name": "Example Account",
            "platform": "meta",
            "account_status": 1,
        },
        {
            "account_id": "act_456",
            "name": "Second Account",
            "platform": "meta",
            "account_status": None,
        },
    ]


def test_meta_ignores_malformed_account_rows(monkeypatch):
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v99.0")
    monkeypatch.setattr(
        discovery.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({
            "data": [None, "invalid", {}, {"id": "act_789"}]
        }),
    )

    result = discovery.discover_meta_accounts("fake-token")

    assert len(result) == 1
    assert result[0]["account_id"] == "act_789"


def test_meta_rejects_invalid_response_shape(monkeypatch):
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v99.0")
    monkeypatch.setattr(
        discovery.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({"data": "not-a-list"}),
    )

    with pytest.raises(HTTPException) as exc:
        discovery.discover_meta_accounts("fake-token")

    assert exc.value.status_code == 502


def test_meta_network_failure_is_handled(monkeypatch):
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v99.0")
    monkeypatch.setattr(
        discovery.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse({}, error=api_error()),
    )

    with pytest.raises(HTTPException) as exc:
        discovery.discover_meta_accounts("fake-token")

    assert exc.value.status_code == 502
