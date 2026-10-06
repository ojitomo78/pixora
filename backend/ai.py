import unicodedata
import json
import logging
from typing import Any
from collections.abc import Sequence

from google import genai
from google.genai import types
import httpx

from backend.settings import optional_setting, required_setting

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
_DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    pass


class RecommendationCards(list[dict[str, str]]):
    def __init__(self, cards: list[dict[str, str]], source: str):
        super().__init__(cards)
        self.source = source


def _api_key() -> str:
    try:
        return required_setting("GEMINI_API_KEY")
    except RuntimeError as exc:
        raise AIProviderError(str(exc)) from exc


def selected_ai_provider() -> str:
    provider = optional_setting("AI_PROVIDER", "ollama").casefold()
    if provider in {"ollama", "gemini", "google"}:
        return "gemini" if provider == "google" else provider
    raise AIProviderError(
        "AI_PROVIDER debe ser 'ollama' o 'gemini'."
    )


def ai_provider_configured() -> bool:
    try:
        return (
            selected_ai_provider() == "ollama"
            or bool(optional_setting("GEMINI_API_KEY"))
        )
    except AIProviderError:
        return False


def _generate_ollama_text(prompt: str, *, json_mode: bool = False) -> str:
    base_url = optional_setting("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_URL).rstrip("/")
    model = optional_setting("OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"
    try:
        response = httpx.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        result = response.json().get("response", "")
    except httpx.HTTPStatusError as exc:
        raise AIProviderError(
            f"Ollama rechazó la solicitud (HTTP {exc.response.status_code})."
        ) from exc
    except httpx.RequestError as exc:
        raise AIProviderError(
            "No se pudo conectar con Ollama. Comprueba que Ollama esté iniciado."
        ) from exc
    except (ValueError, AttributeError) as exc:
        raise AIProviderError("Ollama devolvió una respuesta inválida.") from exc
    if not isinstance(result, str) or not result.strip():
        raise AIProviderError("Ollama respondió sin contenido de texto.")
    return result.strip()


def _generate_gemini_text(prompt: str) -> str:
    try:
        client = genai.Client(
            api_key=_api_key(),
            http_options=types.HttpOptions(timeout=45_000),
        )
        response = client.models.generate_content(
            model=optional_setting("GEMINI_TEXT_MODEL", "gemini-3.8-flash"),
            contents=prompt,
        )
    except AIProviderError:
        raise
    except Exception as exc:
        raise AIProviderError("No fue posible obtener una respuesta de Gemini.") from exc
    result = response.text
    if not isinstance(result, str) or not result.strip():
        raise AIProviderError("Gemini respondió sin contenido de texto.")
    return result.strip()


def generate_text(prompt: str) -> str:
    provider = selected_ai_provider()
    if provider == "ollama":
        return _generate_ollama_text(prompt)
    return _generate_gemini_text(prompt)


def generate_recommendation_cards(prompt: str) -> list[dict[str, str]]:
    try:
        provider = selected_ai_provider()
        model_prompt = (
            "Responde en español a la solicitud del usuario. Genera tarjetas "
            "específicas, útiles y dinámicas, respetando la cantidad pedida si se "
            "indica. No afirmes datos actuales que no puedas verificar. Devuelve "
            "únicamente JSON válido con esta forma: "
            '{"cards":[{"category":"Lugar o Pose","title":"...","description":"...",'
            '"location":"..."}]}. Si location no aplica, usa una cadena vacía. '
            "Cada tarjeta debe incluir category, title, description y location.\n"
            f"Solicitud del usuario: {prompt}"
        )
        if provider == "ollama":
            result = _generate_ollama_text(model_prompt, json_mode=True)
        else:
            result = _generate_gemini_text(model_prompt)
        payload = json.loads(result)
        raw_cards = payload["cards"]
        if not isinstance(raw_cards, list) or not raw_cards:
            raise ValueError("La respuesta no contiene tarjetas.")
        if len(raw_cards) > 8:
            raw_cards = raw_cards[:8]
        cards = []
        for card in raw_cards:
            if not isinstance(card, dict):
                raise ValueError("Una tarjeta no es un objeto.")
            normalized = {
                field: card.get(field, "").strip()
                for field in ("category", "title", "description", "location")
            }
            if not all(
                normalized[field]
                for field in ("category", "title", "description")
            ):
                raise ValueError("Una tarjeta tiene campos obligatorios vacíos.")
            cards.append(normalized)
        return RecommendationCards(cards, provider)
    except Exception as exc:
        logger.warning(
            "Gemini recommendations failed; returning static cards (%s).",
            type(exc).__name__,
        )
        return RecommendationCards(
            fallback_recommendation_cards("lugares y poses para fotos en Bogotá"),
            "fallback",
        )


def fallback_recommendation_cards(prompt: str) -> list[dict[str, str]]:
    normalized_prompt = "".join(
        character
        for character in unicodedata.normalize("NFKD", prompt.casefold())
        if not unicodedata.combining(character)
    )
    place_request = any(
        term in normalized_prompt
        for term in ("lugar", "lugares", "spot", "sitio", "locacion", "zona", "vintage")
    )
    pose_request = any(
        term in normalized_prompt
        for term in ("pose", "poses", "sesion", "postura", "retrato", "graduacion")
    )

    cards: list[dict[str, str]] = []
    if place_request or not pose_request:
        cards.extend(
            [
                {
                    "category": "Lugar",
                    "title": "La Candelaria",
                    "description": "Explora sus calles históricas y fachadas coloridas; verifica acceso y condiciones antes de ir.",
                    "location": "Bogotá",
                },
                {
                    "category": "Lugar",
                    "title": "Parque Simón Bolívar",
                    "description": "Prueba composiciones con zonas verdes y espacios abiertos; confirma horarios y permisos.",
                    "location": "Bogotá",
                },
            ]
        )
    if pose_request or not place_request:
        cards.extend(
            [
                {
                    "category": "Pose",
                    "title": "Retrato al contraluz",
                    "description": "Ubica a la persona frente a una fuente de luz y expón para conservar el contorno.",
                    "location": "",
                },
                {
                    "category": "Pose",
                    "title": "Plano medio en movimiento",
                    "description": "Pide un paso natural y captura varias tomas para conseguir una expresión espontánea.",
                    "location": "",
                },
            ]
        )
    return cards


def generate_embedding(text: str) -> list[float]:
    model = optional_setting("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
    try:
        response = httpx.post(
            f"{_API_ROOT}/models/{model}:embedContent",
            headers={"x-goog-api-key": _api_key()},
            json={
                "model": f"models/{model}",
                "content": {"parts": [{"text": text}]},
            },
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AIProviderError(
            f"Gemini rechazó la generación del vector (HTTP {exc.response.status_code})."
        ) from exc
    except httpx.RequestError as exc:
        raise AIProviderError("No fue posible generar el vector con Gemini.") from exc

    payload = response.json()
    embedding = payload.get("embedding", {})
    values: Sequence[float] = embedding.get("values", [])
    if not values and payload.get("embeddings"):
        values = payload["embeddings"][0].get("values", [])
    if not values or not all(isinstance(value, (int, float)) for value in values):
        raise AIProviderError("Gemini respondió con un vector vacío o inválido.")
    return [float(value) for value in values]
