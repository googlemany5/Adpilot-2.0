"""Read-only discovery of Google Ads and Meta ad accounts."""

import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, get_db
from database import PlatformConnectionDB, UserDB
from token_crypto import decrypt_token

router = APIRouter(prefix="/account-discovery", tags=["Account Discovery"])


def discover_google_accounts(access_token: str) -> list[dict]:
    """Return accessible Google Ads customer IDs; never modify campaigns."""
    version = os.getenv("GOOGLE_ADS_API_VERSION", "")
    developer_token = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")

    if not re.fullmatch(r"v\d+", version) or not developer_token:
        raise HTTPException(
            status_code=503,
            detail="Google Ads API version or developer token is not configured.",
        )

    try:
        response = httpx.post(
            f"https://googleads.googleapis.com/{version}/customers:listAccessibleCustomers",
            headers={
                "Authorization": f"Bearer {access_token}",
                "developer-token": developer_token,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="Google Ads account discovery failed.",
        )

    resources = payload.get("resourceNames", [])
    if not isinstance(resources, list):
        raise HTTPException(
            status_code=502,
            detail="Google Ads returned an invalid account list.",
        )

    accounts = []
    for resource in resources:
        match = re.fullmatch(r"customers/(\d+)", resource) if isinstance(resource, str) else None
        if match:
            accounts.append({
                "account_id": match.group(1),
                "name": None,
                "platform": "google",
            })

    return accounts


def discover_meta_accounts(access_token: str) -> list[dict]:
    """Return accessible Meta ad accounts; never modify campaigns."""
    version = os.getenv("META_GRAPH_API_VERSION", "")

    if not re.fullmatch(r"v\d+\.\d+", version):
        raise HTTPException(
            status_code=503,
            detail="Meta Graph API version is not configured.",
        )

    try:
        response = httpx.get(
            f"https://graph.facebook.com/{version}/me/adaccounts",
            params={
                "fields": "id,account_id,name,account_status",
                "limit": 100,
            },
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="Meta account discovery failed.",
        )

    rows = payload.get("data", [])
    if not isinstance(rows, list):
        raise HTTPException(
            status_code=502,
            detail="Meta returned an invalid account list.",
        )

    accounts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        account_id = row.get("account_id") or row.get("id")
        if isinstance(account_id, (str, int)) and str(account_id).strip():
            accounts.append({
                "account_id": str(account_id),
                "name": row.get("name"),
                "platform": "meta",
                "account_status": row.get("account_status"),
            })

    return accounts


@router.get("/{connection_id}")
def discover_accounts(
    connection_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Discover accounts for the authenticated user's own connection."""
    connection = (
        db.query(PlatformConnectionDB)
        .filter(
            PlatformConnectionDB.id == connection_id,
            PlatformConnectionDB.user_id == current_user.id,
        )
        .first()
    )

    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if connection.platform not in {"google", "meta"}:
        raise HTTPException(status_code=400, detail="Unsupported platform.")

    try:
        access_token = decrypt_token(connection.access_token)
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Stored credentials could not be decrypted.",
        )

    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="This connection has no access token. Reconnect the platform.",
        )

    if connection.platform == "google":
        accounts = discover_google_accounts(access_token)
    else:
        accounts = discover_meta_accounts(access_token)

    return {
        "connection_id": connection.id,
        "platform": connection.platform,
        "accounts": accounts,
        "read_only": True,
    }
