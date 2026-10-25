import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, get_db
from database import PlatformConnectionDB, PlatformOAuthStateDB, UserDB
from token_crypto import encrypt_token

router = APIRouter(prefix="/platform-oauth", tags=["Platform OAuth"])

STATE_LIFETIME_MINUTES = 10


def create_oauth_state(db: Session, user_id: int, platform: str) -> str:
    raw_state = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(raw_state.encode()).hexdigest()

    db.add(
        PlatformOAuthStateDB(
            state_hash=state_hash,
            user_id=user_id,
            platform=platform,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=STATE_LIFETIME_MINUTES),
        )
    )
    db.commit()
    return raw_state


def consume_oauth_state(
    db: Session, raw_state: str, platform: str
) -> int:
    if not raw_state or len(raw_state) > 500:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    state_hash = hashlib.sha256(raw_state.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    # Atomic update: a valid state can only be consumed once.
    updated = (
        db.query(PlatformOAuthStateDB)
        .filter(
            PlatformOAuthStateDB.state_hash == state_hash,
            PlatformOAuthStateDB.platform == platform,
            PlatformOAuthStateDB.expires_at > now,
            PlatformOAuthStateDB.used_at.is_(None),
        )
        .update(
            {PlatformOAuthStateDB.used_at: now},
            synchronize_session=False,
        )
    )

    if updated != 1:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="OAuth state is invalid, expired, or already used.",
        )

    row = (
        db.query(PlatformOAuthStateDB)
        .filter(PlatformOAuthStateDB.state_hash == state_hash)
        .first()
    )
    if row is None:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    user_id = row.user_id
    db.commit()
    return user_id


@router.post("/{platform}/start")
def start_platform_oauth(
    platform: str,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    platform = platform.strip().lower()

    if platform not in {"google", "meta"}:
        raise HTTPException(
            status_code=400,
            detail="Platform must be 'google' or 'meta'.",
        )

    if platform == "google":
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        if not client_id or not redirect_uri:
            raise HTTPException(
                status_code=503,
                detail="Google OAuth is not configured yet.",
            )

        state = create_oauth_state(db, current_user.id, platform)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/adwords",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        authorization_url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            + urlencode(params)
        )

    else:
        app_id = os.getenv("META_APP_ID")
        redirect_uri = os.getenv("META_REDIRECT_URI")
        version = os.getenv("META_GRAPH_API_VERSION", "")

        if (
            not app_id
            or not redirect_uri
            or not re.fullmatch(r"v\d+\.\d+", version)
        ):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Meta OAuth is not configured. Set META_APP_ID, "
                    "META_REDIRECT_URI, and a valid META_GRAPH_API_VERSION."
                ),
            )

        state = create_oauth_state(db, current_user.id, platform)
        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "ads_read,ads_management,business_management",
            "state": state,
        }
        authorization_url = (
            f"https://www.facebook.com/{version}/dialog/oauth?"
            + urlencode(params)
        )

    return {
        "platform": platform,
        "authorization_url": authorization_url,
        "state_expires_in_seconds": STATE_LIFETIME_MINUTES * 60,
    }



def _exchange_oauth_code(token_url: str, data: dict) -> dict:
    """Exchange an authorization code without exposing provider tokens."""
    try:
        response = httpx.post(token_url, data=data, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="The advertising platform token exchange failed.",
        ) from exc

    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise HTTPException(
            status_code=502,
            detail="The platform returned an invalid token response.",
        )

    return payload


def _save_pending_connection(
    db: Session,
    user_id: int,
    platform: str,
    token_data: dict,
) -> dict:
    """Store encrypted credentials, inactive until an ad account is selected."""
    try:
        connection = PlatformConnectionDB(
            user_id=user_id,
            platform=platform,
            account_id=None,
            access_token=encrypt_token(token_data["access_token"]),
            refresh_token=encrypt_token(token_data.get("refresh_token")),
            is_active=False,
        )
        db.add(connection)
        db.commit()
        db.refresh(connection)
    except Exception:
        db.rollback()
        raise

    return {
        "platform": platform,
        "connection_id": connection.id,
        "status": "pending_account_selection",
        "message": (
            "Authorization succeeded. Select an ad account before "
            "activating this connection."
        ),
    }


@router.get("/google/callback")
def google_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    user_id = consume_oauth_state(db, state or "", "google")

    if error:
        raise HTTPException(
            status_code=400,
            detail="Google authorization was declined or cancelled.",
        )
    if not code or len(code) > 4096:
        raise HTTPException(status_code=400, detail="Missing or invalid code.")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not fully configured.",
        )

    token_data = _exchange_oauth_code(
        "https://oauth2.googleapis.com/token",
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
        },
    )

    return _save_pending_connection(db, user_id, "google", token_data)


@router.get("/meta/callback")
def meta_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    user_id = consume_oauth_state(db, state or "", "meta")

    if error:
        raise HTTPException(
            status_code=400,
            detail="Meta authorization was declined or cancelled.",
        )
    if not code or len(code) > 4096:
        raise HTTPException(status_code=400, detail="Missing or invalid code.")

    app_id = os.getenv("META_APP_ID")
    app_secret = os.getenv("META_APP_SECRET")
    redirect_uri = os.getenv("META_REDIRECT_URI")
    version = os.getenv("META_GRAPH_API_VERSION", "")

    if (
        not app_id
        or not app_secret
        or not redirect_uri
        or not re.fullmatch(r"v\d+\.\d+", version)
    ):
        raise HTTPException(
            status_code=503,
            detail="Meta OAuth is not fully configured.",
        )

    token_data = _exchange_oauth_code(
        f"https://graph.facebook.com/{version}/oauth/access_token",
        {
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )

    return _save_pending_connection(db, user_id, "meta", token_data)
