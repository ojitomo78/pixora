from backend.auth_tokens import get_user_id_from_access_token, issue_access_token
from backend.passwords import hash_password, verify_password


def test_password_hash_is_salted_and_verifiable():
    first_hash = hash_password("pixora-safe-password")
    second_hash = hash_password("pixora-safe-password")

    assert first_hash != second_hash
    assert verify_password("pixora-safe-password", first_hash)
    assert not verify_password("wrong-password", first_hash)


def test_signed_access_token_checks_signature_and_user(monkeypatch):
    monkeypatch.setenv("PIXORA_AUTH_SECRET", "x" * 48)
    token = issue_access_token(42)

    assert get_user_id_from_access_token(token) == 42
    assert get_user_id_from_access_token(f"{token}tampered") is None
