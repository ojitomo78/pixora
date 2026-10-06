from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from backend import main
from backend.main import CreateComment, _compress_image, _validate_image, app


def test_api_expone_salud_y_rutas():
    with TestClient(app) as client:
        health = client.get("/health")
        schema = client.get("/openapi.json")

    assert health.status_code == 200
    assert "configuration" in health.json()
    assert schema.status_code == 200
    assert "/api/v1/ai/poses" in schema.json()["paths"]
    assert "/api/v1/ai/ask" in schema.json()["paths"]
    assert "/api/v1/posts/{post_id}/comments" in schema.json()["paths"]
    assert "/api/v1/posts/{post_id}/like" in schema.json()["paths"]
    assert "delete" in schema.json()["paths"]["/api/v1/posts/{post_id}"]
    assert "/api/v1/media/{media_id}" in schema.json()["paths"]
    assert "/api/v1/posts/{post_id}/details" in schema.json()["paths"]
    assert "/api/v1/session-types/{session_type_id}/poses" in schema.json()["paths"]
    assert "/api/v1/locations/{location_id}/gallery" in schema.json()["paths"]
    post_schema = schema.json()["components"]["schemas"]
    post_form_ref = schema.json()["paths"]["/api/v1/posts"]["post"]["requestBody"][
        "content"
    ]["multipart/form-data"]["schema"]["$ref"].rsplit("/", 1)[-1]
    assert "visibilidad" not in post_schema[post_form_ref].get("properties", {})


def test_endpoints_protegidos_rechazan_sin_token():
    with TestClient(app) as client:
        response = client.get("/api/v1/posts")

    assert response.status_code == 401


def test_validar_imagen_acepta_jpeg():
    output = BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(output, format="JPEG")

    assert _validate_image(output.getvalue()) is None


def test_validar_imagen_rechaza_archivo_falso():
    with pytest.raises(HTTPException) as error:
        _validate_image(b"not-an-image")

    assert error.value.status_code == 415


def test_comprimir_imagen_redimensiona_a_jpeg_menor_a_un_megabyte():
    output = BytesIO()
    Image.effect_noise((2200, 1500), 100).convert("RGB").save(
        output, format="PNG"
    )

    compressed = _compress_image(output.getvalue())

    with Image.open(BytesIO(compressed)) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= 1920
    assert len(compressed) < 1024 * 1024


def test_publicacion_comprime_imagen_y_guarda_lugar_y_pose(monkeypatch):
    captured = {}
    image_output = BytesIO()
    Image.new("RGB", (2400, 1600), color="blue").save(image_output, format="PNG")

    def fake_create_publication(user_id, location_id, title, description, visibility):
        captured["publication"] = (
            user_id,
            location_id,
            title,
            description,
            visibility,
        )
        return {
            "id_publicacion": 44,
            "id_usuario": user_id,
            "titulo": title,
            "descripcion": description,
            "fecha_publicacion": datetime.now(timezone.utc),
        }

    def fake_save_image(publication_id, content, content_type):
        captured["image"] = (publication_id, content, content_type)

    def fake_save_details(*args):
        captured["details"] = args

    monkeypatch.setattr(main, "list_locations", lambda: [])
    monkeypatch.setattr(main, "create_publication", fake_create_publication)
    monkeypatch.setattr(main, "save_publication_image", fake_save_image)
    monkeypatch.setattr(main, "save_publication_details", fake_save_details)
    app.dependency_overrides[main._current_user] = lambda: {
        "id_usuario": 7,
        "usuario": "ana",
    }
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/posts",
                data={
                    "titulo": "Retrato",
                    "localizacion_texto": "Mi Estudio",
                    "pose_utilizada": "Retrato en picado",
                },
                files={
                    "image": ("photo.png", image_output.getvalue(), "image/png")
                },
            )
    finally:
        app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 201
    assert captured["publication"][1] is None
    assert "Localización indicada: Mi Estudio" in captured["publication"][3]
    assert captured["image"][2] == "image/jpeg"
    assert len(captured["image"][1]) < 1024 * 1024
    assert captured["details"][-1] == "Retrato en picado"


def test_error_interno_de_mongo_no_devuelve_503_y_se_registra(monkeypatch, caplog):
    image_output = BytesIO()
    Image.new("RGB", (32, 32), color="red").save(image_output, format="JPEG")
    deleted = []

    monkeypatch.setattr(
        main,
        "create_publication",
        lambda user_id, location_id, title, description, visibility: {
            "id_publicacion": 45,
            "id_usuario": user_id,
            "titulo": title,
            "descripcion": description,
            "fecha_publicacion": datetime.now(timezone.utc),
        },
    )
    monkeypatch.setattr(
        main,
        "save_publication_image",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("mongo unavailable")),
    )
    monkeypatch.setattr(
        main, "delete_publication", lambda publication_id, user_id: deleted.append(publication_id)
    )
    monkeypatch.setattr(main, "delete_publication_image", lambda _publication_id: None)
    app.dependency_overrides[main._current_user] = lambda: {
        "id_usuario": 7,
        "usuario": "ana",
    }
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/posts",
                data={"titulo": "Retrato"},
                files={
                    "image": ("photo.jpg", image_output.getvalue(), "image/jpeg")
                },
            )
    finally:
        app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 500
    assert deleted == [45]
    assert "mongo unavailable" in caplog.text


def test_comentario_vacio_rechazado():
    with pytest.raises(ValidationError):
        CreateComment(comentario="   ")


def test_http_like_persists_current_user_reaction(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        main,
        "get_publication",
        lambda publication_id: {"id_publicacion": publication_id},
    )

    def fake_toggle(publication_id, user_id):
        captured.update(publication_id=publication_id, user_id=user_id)
        return {"liked": True, "likes_count": 3}

    monkeypatch.setattr(main, "toggle_publication_like", fake_toggle)
    app.dependency_overrides[main._current_user] = lambda: {"id_usuario": 7}
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/posts/44/like")
    finally:
        app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 200
    assert response.json() == {"liked": True, "likes_count": 3}
    assert captured == {"publication_id": 44, "user_id": 7}


def test_feed_returns_like_state_for_signed_in_user(monkeypatch):
    monkeypatch.setattr(
        main,
        "list_publications",
        lambda _limit: [
            {
                "id_publicacion": 44,
                "id_usuario": 7,
                "usuario": "ana",
                "titulo": "Retrato",
                "descripcion": "",
                "localizacion_nombre": None,
                "visibilidad": "publica",
                "fecha_publicacion": datetime.now(timezone.utc),
            }
        ],
    )
    monkeypatch.setattr(main, "list_publication_images", lambda _ids: {44: (b"", "")})
    monkeypatch.setattr(
        main,
        "list_publication_details",
        lambda _ids: {44: {"likes_count": 2, "likes_by": [7, 9]}},
    )
    app.dependency_overrides[main._current_user] = lambda: {"id_usuario": 7}
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/posts")
    finally:
        app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 200
    assert response.json()[0]["likes_count"] == 2
    assert response.json()[0]["liked_by_me"] is True


def test_http_delete_post_cleans_owned_post_and_mongo_data(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main,
        "get_publication",
        lambda publication_id: {
            "id_publicacion": publication_id,
            "id_usuario": 7,
        },
    )
    monkeypatch.setattr(
        main,
        "delete_publication",
        lambda publication_id, user_id: (
            calls.append(("postgres", publication_id, user_id)) or True
        ),
    )
    monkeypatch.setattr(
        main,
        "delete_publication_image",
        lambda publication_id: calls.append(("image", publication_id)),
    )
    monkeypatch.setattr(
        main,
        "delete_publication_details",
        lambda publication_id: calls.append(("details", publication_id)),
    )
    monkeypatch.setattr(
        main,
        "delete_publication_comments",
        lambda publication_id: calls.append(("comments", publication_id)),
    )
    app.dependency_overrides[main._current_user] = lambda: {"id_usuario": 7}
    try:
        with TestClient(app) as client:
            response = client.delete("/api/v1/posts/44")
    finally:
        app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 200
    assert calls == [
        ("postgres", 44, 7),
        ("image", 44),
        ("details", 44),
        ("comments", 44),
    ]
    assert response.json() == {"message": "Eliminado"}


def test_http_delete_post_rejects_another_users_post(monkeypatch):
    deleted = []
    monkeypatch.setattr(
        main,
        "get_publication",
        lambda publication_id: {
            "id_publicacion": publication_id,
            "id_usuario": 9,
        },
    )
    monkeypatch.setattr(
        main,
        "delete_publication",
        lambda *_args: deleted.append(True),
    )
    app.dependency_overrides[main._current_user] = lambda: {"id_usuario": 7}
    try:
        with TestClient(app) as client:
            response = client.delete("/api/v1/posts/44")
    finally:
        app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 403
    assert deleted == []


def test_http_delete_post_returns_clear_database_error_without_500(monkeypatch):
    from psycopg2 import OperationalError

    calls = []
    monkeypatch.setattr(
        main,
        "get_publication",
        lambda publication_id: {
            "id_publicacion": publication_id,
            "id_usuario": 7,
        },
    )
    monkeypatch.setattr(
        main,
        "delete_publication_image",
        lambda publication_id: calls.append(("image", publication_id)),
    )
    monkeypatch.setattr(
        main,
        "delete_publication_details",
        lambda publication_id: calls.append(("details", publication_id)),
    )
    monkeypatch.setattr(
        main,
        "delete_publication_comments",
        lambda publication_id: calls.append(("comments", publication_id)),
    )
    monkeypatch.setattr(
        main,
        "delete_publication",
        lambda *_args: (_ for _ in ()).throw(
            OperationalError("database unavailable")
        ),
    )
    app.dependency_overrides[main._current_user] = lambda: {"id_usuario": 7}
    try:
        with TestClient(app) as client:
            response = client.delete("/api/v1/posts/44")
    finally:
        app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "No se pudo eliminar la publicación de PostgreSQL."
    )
    assert calls == []


def test_http_ai_ask_returns_real_generator_cards_with_gemini_source(monkeypatch):
    expected_cards = [
        {
            "category": "Lugar",
            "title": "Jardín de las luces",
            "description": "Busca luz suave al atardecer y combina planos amplios con detalles.",
            "location": "Bogotá",
        }
    ]
    monkeypatch.setattr(
        main, "generate_recommendation_cards", lambda _prompt: expected_cards
    )
    app.dependency_overrides[main._current_user] = lambda: {"id_usuario": 7}
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/ask",
                json={"prompt": "Lugares para una sesión de fotos"},
            )
    finally:
        app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 200
    assert response.json() == {"cards": expected_cards, "source": "gemini"}
