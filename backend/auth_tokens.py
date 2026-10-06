import base64
import hashlib
import hmac
import time

from backend.settings import ConfigurationError, required_setting


_TOKEN_LIFETIME_SECONDS = 60 * 60


def _secret() -> bytes:
    secret = required_setting("PIXORA_AUTH_SECRET").encode("utf-8")
    if len(secret) < 32:
        raise ConfigurationError("PIXORA_AUTH_SECRET debe tener al menos 32 bytes.")
    return secret


def validate_auth_token_secret() -> None:
    _secret()


def issue_access_token(id_usuario: int) -> str:
    expires_at = int(time.time()) + _TOKEN_LIFETIME_SECONDS
    payload = f"{id_usuario}:{expires_at}".encode("ascii")
    encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(_secret(), encoded_payload, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{encoded_payload.decode('ascii')}.{encoded_signature.decode('ascii')}"


def get_user_id_from_access_token(token: str) -> int | None:
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        expected_signature = base64.urlsafe_b64encode(
            hmac.new(
                _secret(),
                encoded_payload.encode("ascii"),
                hashlib.sha256,
            ).digest()
        ).rstrip(b"=")
        if not hmac.compare_digest(
            encoded_signature.encode("ascii"), expected_signature
        ):
            return None

        padded_payload = encoded_payload + "=" * (-len(encoded_payload) % 4)
        payload = base64.urlsafe_b64decode(padded_payload).decode("ascii")
        raw_user_id, raw_expiry = payload.split(":", maxsplit=1)
        id_usuario = int(raw_user_id)
        if int(raw_expiry) <= int(time.time()) or id_usuario <= 0:
            return None
        return id_usuario
    except (ValueError, UnicodeError):
        return None
