"""Encryption helpers for AdPilot ad-platform credentials."""

import os

from cryptography.fernet import Fernet, InvalidToken


def _get_cipher() -> Fernet:
    """Load the encryption key from the environment."""
    key = os.getenv("ADPILOT_TOKEN_ENCRYPTION_KEY")

    if not key:
        raise RuntimeError(
            "ADPILOT_TOKEN_ENCRYPTION_KEY is not configured."
        )

    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "ADPILOT_TOKEN_ENCRYPTION_KEY is invalid."
        ) from exc


def encrypt_token(token: str | None) -> str | None:
    """Encrypt a token before storing it in the database."""
    if token is None or token == "":
        return token

    cipher = _get_cipher()
    return cipher.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(token: str | None) -> str | None:
    """Decrypt an encrypted token when the backend needs it."""
    if token is None or token == "":
        return token

    cipher = _get_cipher()

    try:
        return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError(
            "Stored token could not be decrypted. "
            "Check the encryption key and stored data."
        ) from exc
