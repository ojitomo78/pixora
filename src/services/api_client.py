import os
from typing import Any
from urllib.parse import urlsplit

import httpx

class APIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self, base_url: str | None = None):
        configured_url = (
            base_url or os.getenv("PIXORA_API_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        parsed_url = urlsplit(configured_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("PIXORA_API_URL debe ser una URL HTTP(S) válida.")
        if parsed_url.scheme == "http" and parsed_url.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Usa HTTPS para conectar Pixora a través de una red.")
        self.base_url = configured_url
        self.access_token: str | None = None
        self.current_user_id: str | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, Any, str]] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        try:
            response = httpx.request(
                method,
                f"{self.base_url}/api/v1{path}",
                json=json,
                data=data,
                files=files,
                params=params,
                headers=headers,
                timeout=60,
            )
        except httpx.RequestError as exc:
            raise APIError(
                "No se pudo conectar con Pixora API. Comprueba que el backend esté iniciado."
            ) from exc
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise APIError(str(detail), response.status_code)
        return response.json() if response.content else None

    def download(self, path: str) -> bytes:
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        try:
            response = httpx.get(url, headers=headers, timeout=60)
        except httpx.RequestError as exc:
            raise APIError("No se pudo descargar el medio de la publicación.") from exc
        if response.is_error:
            raise APIError("No se pudo cargar el medio de la publicación.", response.status_code)
        return response.content
