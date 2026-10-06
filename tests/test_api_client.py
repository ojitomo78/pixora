import pytest

from src.services.api_client import ApiClient


def test_api_local_http_y_remota_https_permitidas():
    assert ApiClient("http://127.0.0.1:8000").base_url == "http://127.0.0.1:8000"
    assert ApiClient("https://api.pixora.example").base_url == "https://api.pixora.example"


def test_api_remota_http_rechazada():
    with pytest.raises(ValueError, match="HTTPS"):
        ApiClient("http://api.pixora.example")


def test_delete_request_includes_bearer_token(monkeypatch):
    captured = {}

    class Response:
        is_error = False
        content = b"{}"

        def json(self):
            return {"message": "Publicación eliminada"}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr("src.services.api_client.httpx.request", fake_request)
    client = ApiClient()
    client.access_token = "active-session-token"

    result = client.request("DELETE", "/posts/42")

    assert result == {"message": "Publicación eliminada"}
    assert captured["method"] == "DELETE"
    assert captured["headers"]["Authorization"] == (
        "Bearer " + client.access_token
    )
