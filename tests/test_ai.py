import pytest
from google.genai.errors import ServerError

from backend.ai import (
    AIProviderError,
    generate_embedding,
    generate_recommendation_cards,
    generate_text,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_gemini_text_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
    request = {}

    class FakeModels:
        def generate_content(self, *, model, contents):
            request["model"] = model
            request["contents"] = contents

            class Response:
                text = "Idea de prueba"

            return Response()

    class FakeClient:
        def __init__(self, **kwargs):
            request.update(kwargs)
            self.models = FakeModels()

    monkeypatch.setattr("backend.ai.genai.Client", FakeClient)

    assert generate_text("prompt") == "Idea de prueba"
    assert request["api_key"] == "test-key"
    assert request["model"] == "gemini-2.5-flash"
    assert request["contents"] == "prompt"


def test_gemini_embedding_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
    def fake_post(url, **kwargs):
        assert url.endswith("/models/gemini-embedding-2:embedContent")
        assert kwargs["json"]["content"]["parts"][0]["text"] == "caption"
        return FakeResponse({"embedding": {"values": [0.25, -0.5]}})

    monkeypatch.setattr("backend.ai.httpx.post", fake_post)

    assert generate_embedding("caption") == [0.25, -0.5]


def test_gemini_requires_api_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(AIProviderError, match="GEMINI_API_KEY"):
        generate_text("prompt")


def test_gemini_rejects_empty_success_response(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class FakeModels:
        def generate_content(self, **_kwargs):
            class Response:
                text = None

            return Response()

    class FakeClient:
        def __init__(self, **_kwargs):
            self.models = FakeModels()

    monkeypatch.setattr("backend.ai.genai.Client", FakeClient)

    with pytest.raises(AIProviderError, match="sin contenido de texto"):
        generate_text("prompt")


def test_gemini_sdk_returns_dynamic_recommendation_cards(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "sdk-test-key")
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
    captured = {}

    class FakeModels:
        def generate_content(self, *, model, contents):
            captured["model"] = model
            captured["prompt"] = contents

            class Response:
                text = (
                    '{"cards":[{"category":"Lugar","title":"Calle vintage",'
                    '"description":"Calles con arquitectura clásica.",'
                    '"location":"Chapinero"}]}'
                )

            return Response()

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = FakeModels()

    monkeypatch.setattr("backend.ai.genai.Client", FakeClient)

    cards = generate_recommendation_cards("Lugares vintage en Chapinero")

    assert cards[0]["title"] == "Calle vintage"
    assert captured["api_key"] == "sdk-test-key"
    assert captured["model"] == "gemini-2.5-flash"
    assert "Lugares vintage en Chapinero" in captured["prompt"]
    assert "únicamente JSON válido" in captured["prompt"]


def test_gemini_client_error_returns_fallback_without_trying_old_models(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "sdk-test-key")
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
    attempted_models = []

    class FakeClient:
        def __init__(self, **_kwargs):
            self.models = self

        def generate_content(self, *, model, **_kwargs):
            attempted_models.append(model)
            raise ServerError(503, {"error": {"message": "overloaded"}})

    monkeypatch.setattr("backend.ai.genai.Client", FakeClient)

    cards = generate_recommendation_cards("Sugiere lugares de Bogotá")

    assert attempted_models == ["gemini-2.5-flash"]
    assert {card["category"] for card in cards} == {"Lugar", "Pose"}
    assert all(card["location"] == "Bogotá" for card in cards if card["category"] == "Lugar")


def test_missing_api_key_returns_both_bogota_fallback_categories(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    cards = generate_recommendation_cards("Recomiéndame una pose")

    assert {card["category"] for card in cards} == {"Lugar", "Pose"}
    assert all(card["location"] == "Bogotá" for card in cards if card["category"] == "Lugar")


def test_default_text_model_is_used_when_not_configured(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "sdk-test-key")
    monkeypatch.delenv("GEMINI_TEXT_MODEL", raising=False)
    requested_models = []

    class FakeModels:
        def generate_content(self, *, model, **_kwargs):
            requested_models.append(model)

            class Response:
                text = (
                    '{"cards":[{"category":"Lugar","title":"Prueba",'
                    '"description":"Descripción detallada.",'
                    '"location":"Bogotá"}]}'
                )

            return Response()

    class FakeClient:
        def __init__(self, **_kwargs):
            self.models = FakeModels()

    monkeypatch.setattr("backend.ai.genai.Client", FakeClient)

    assert generate_recommendation_cards("Sugerencias")[0]["title"] == "Prueba"
    assert requested_models == ["gemini-3.8-flash"]


def test_ollama_text_request_uses_local_server_and_model(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    captured = {}

    def fake_post(url, *, json, timeout):
        captured.update(url=url, json=json, timeout=timeout)
        return FakeResponse({"response": "  Sugerencia local  "})

    monkeypatch.setattr("backend.ai.httpx.post", fake_post)

    assert generate_text("Dame una idea") == "Sugerencia local"
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["json"] == {
        "model": "qwen2.5:3b",
        "prompt": "Dame una idea",
        "stream": False,
    }


def test_ollama_generates_structured_cards_without_google_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    captured = {}

    def fake_post(url, *, json, timeout):
        captured.update(url=url, json=json)
        return FakeResponse(
            {
                "response": (
                    '{"cards":[{"category":"Lugar","title":"Jardín local",'
                    '"description":"Usa luz suave de la tarde.",'
                    '"location":"Bogotá"}]}'
                )
            }
        )

    monkeypatch.setattr("backend.ai.httpx.post", fake_post)

    cards = generate_recommendation_cards("Lugares para retrato")

    assert cards[0]["title"] == "Jardín local"
    assert cards.source == "ollama"
    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    assert captured["json"]["model"] == "qwen2.5:3b"
    assert captured["json"]["format"] == "json"
    assert captured["json"]["stream"] is False


def test_ollama_connection_failure_uses_static_cards(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fail_connection(*_args, **_kwargs):
        import httpx

        raise httpx.ConnectError("Ollama is offline")

    monkeypatch.setattr("backend.ai.httpx.post", fail_connection)

    cards = generate_recommendation_cards("Dame una recomendación")

    assert cards.source == "fallback"
    assert {card["category"] for card in cards} == {"Lugar", "Pose"}


def test_fallback_cards_are_valid_for_pose_and_place_queries():
    from backend.ai import fallback_recommendation_cards

    place_cards = fallback_recommendation_cards("lugares vintage de noche")
    pose_cards = fallback_recommendation_cards("poses para graduación")

    assert all({"category", "title", "description", "location"} <= card.keys() for card in place_cards)
    assert all(card["category"] == "Lugar" for card in place_cards)
    assert all(card["category"] == "Pose" for card in pose_cards)
