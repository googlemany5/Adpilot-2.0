import pytest
from cryptography.fernet import Fernet

from token_crypto import decrypt_token, encrypt_token


def test_token_is_encrypted_and_can_be_decrypted(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ADPILOT_TOKEN_ENCRYPTION_KEY", key)

    original = "fake-test-token-not-a-real-credential"
    encrypted = encrypt_token(original)

    assert encrypted != original
    assert decrypt_token(encrypted) == original


def test_empty_tokens_remain_empty():
    assert encrypt_token(None) is None
    assert encrypt_token("") == ""
    assert decrypt_token(None) is None
    assert decrypt_token("") == ""


def test_missing_encryption_key_is_rejected(monkeypatch):
    monkeypatch.delenv("ADPILOT_TOKEN_ENCRYPTION_KEY", raising=False)

    with pytest.raises(RuntimeError, match="not configured"):
        encrypt_token("fake-test-token")


def test_wrong_key_cannot_decrypt_token(monkeypatch):
    original_key = Fernet.generate_key().decode()
    monkeypatch.setenv("ADPILOT_TOKEN_ENCRYPTION_KEY", original_key)
    encrypted = encrypt_token("fake-test-token")

    wrong_key = Fernet.generate_key().decode()
    monkeypatch.setenv("ADPILOT_TOKEN_ENCRYPTION_KEY", wrong_key)

    with pytest.raises(RuntimeError, match="could not be decrypted"):
        decrypt_token(encrypted)
