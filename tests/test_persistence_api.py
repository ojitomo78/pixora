from backend import main
from backend.passwords import verify_password


def test_registration_persists_only_hash_and_exact_user_fields(monkeypatch):
    captured = {}
    monkeypatch.setenv("PIXORA_AUTH_SECRET", "s" * 48)

    def fake_create_user(nombre, apellido, usuario, correo, password_hash):
        captured.update(
            nombre=nombre,
            apellido=apellido,
            usuario=usuario,
            correo=correo,
            password_hash=password_hash,
        )
        return {
            "id_usuario": 12,
            "nombre": nombre,
            "apellido": apellido,
            "usuario": usuario,
            "correo": correo,
        }

    monkeypatch.setattr(main, "create_user", fake_create_user)
    response = main.register(
        main.Registration(
            nombre="Ana",
            apellido="López",
            usuario="ana",
            correo="ana@example.com",
            contraseña="mi-clave-segura",
        )
    )

    assert set(captured) == {
        "nombre",
        "apellido",
        "usuario",
        "correo",
        "password_hash",
    }
    assert verify_password("mi-clave-segura", captured["password_hash"])
    assert response["user_id"] == "12"
    assert response["username"] == "ana"
    assert response["access_token"]


def test_login_devuelve_nombre_de_usuario_junto_con_el_token(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_user_by_identifier",
        lambda _: {
            "id_usuario": 12,
            "usuario": "ana",
            "contraseña": "password-hash",
        },
    )
    monkeypatch.setattr(main, "verify_password", lambda *_args: True)
    monkeypatch.setattr(main, "issue_access_token", lambda _: "access-token")

    response = main.login(
        main.LoginCredentials(
            identificador="ana",
            contraseña="mi-clave-segura",
        )
    )

    assert response == {
        "user_id": "12",
        "username": "ana",
        "access_token": "access-token",
    }


def test_pose_recommendation_uses_database_fallback_without_gemini(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        main,
        "get_session_type_by_name",
        lambda _: {
            "id_tipo_sesion": 3,
            "nombre": "Retrato",
            "descripcion": "Retrato en exterior",
            "categoria": "Retrato",
            "recomendaciones": "Usa luz natural lateral.",
        },
    )
    monkeypatch.setattr(main, "list_model_poses", lambda _: [])

    response = main.recommend_poses(main.PoseRequest(session_type="Retrato"), {})

    assert response["source"] == "postgres"
    assert "Usa luz natural lateral." in response["recommendation"]


def test_location_recommendation_falls_back_to_bogota_rows(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "unused-for-fallback")
    requested_cities = []

    def fake_locations(city):
        requested_cities.append(city)
        return (
            []
            if city == "Medellín"
            else [{
                "id_localizacion": 8,
                "nombre": "Mirador",
                "ciudad": "Bogotá",
                "pais": "Colombia",
                "descripcion": "Vista de la ciudad",
                "coordenadas": "4.6, -74.1",
            }]
        )

    monkeypatch.setattr(main, "list_locations", fake_locations)

    def fail_generate_text(prompt):
        assert prompt
        raise main.AIProviderError("Gemini no disponible")

    monkeypatch.setattr(main, "generate_text", fail_generate_text)

    response = main.recommend_spots(
        main.SpotRequest(city="Medellín", photo_type="Retrato"), {}
    )

    assert requested_cities == ["Medellín", "Bogotá"]
    assert response["source"] == "fallback"
    assert [spot["nombre"] for spot in response["spots"]] == [
        "La Candelaria",
        "Monserrate",
        "Parque Simón Bolívar",
        "Chorro de Quevedo",
    ]


def test_pose_recommendation_returns_catalog_when_session_type_is_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(main, "get_session_type_by_name", lambda _: None)

    response = main.recommend_poses(
        main.PoseRequest(session_type="Retrato Urbano"), {}
    )

    assert response["source"] == "fallback"
    assert [pose["nombre_pose"] for pose in response["poses"]] == [
        "Retrato Urbano",
        "Plano Medio",
        "Picado Creativo",
    ]


def test_spot_recommendation_returns_structured_bogota_fallback_when_empty(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(main, "list_locations", lambda _: [])

    response = main.recommend_spots(
        main.SpotRequest(city="Bogotá", photo_type="Urbano"), {}
    )

    assert response["source"] == "fallback"
    assert response["spots"][0]["ciudad"] == "Bogotá"
    assert response["spots"][0]["id_localizacion"] is None


def test_ask_pixora_ai_returns_dynamic_cards(monkeypatch):
    captured = {}

    def fake_cards(prompt):
        captured["prompt"] = prompt
        return [
            {
                "category": "Pose",
                "title": "Retrato al contraluz",
                "description": "Coloca a la persona frente a una ventana.",
                "location": "",
            }
        ]

    monkeypatch.setattr(main, "generate_recommendation_cards", fake_cards)

    response = main.ask_pixora_ai(
        main.AIQuestion(prompt="Dame una pose para retrato"), {}
    )

    assert captured["prompt"] == "Dame una pose para retrato"
    assert response["source"] == "gemini"
    assert response["cards"][0]["title"] == "Retrato al contraluz"


def test_ask_pixora_ai_returns_json_fallback_when_gemini_raises(monkeypatch, caplog):
    def fail_gemini(_prompt):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(main, "generate_recommendation_cards", fail_gemini)

    response = main.ask_pixora_ai(
        main.AIQuestion(prompt="Recomiéndame lugares para fotos"), {}
    )

    assert response["source"] == "fallback"
    assert {card["category"] for card in response["cards"]} == {"Lugar", "Pose"}
    assert "provider unavailable" in caplog.text


def test_ai_ask_http_endpoint_returns_fallback_cards_not_503(monkeypatch):
    monkeypatch.setattr(
        main,
        "generate_recommendation_cards",
        lambda _prompt: (_ for _ in ()).throw(RuntimeError("quota exceeded")),
    )
    main.app.dependency_overrides[main._current_user] = lambda: {"id_usuario": 5}
    try:
        from fastapi.testclient import TestClient

        with TestClient(main.app) as client:
            response = client.post(
                "/api/v1/ai/ask",
                json={"prompt": "Dame poses para una sesión de graduación"},
            )
    finally:
        main.app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "fallback"
    assert {card["category"] for card in payload["cards"]} == {"Lugar", "Pose"}


def test_ai_ask_endpoint_returns_200_when_gemini_is_overloaded(monkeypatch):
    from google.genai.errors import ServerError

    def overloaded_provider(_prompt):
        raise ServerError(503, {"error": {"message": "overloaded"}})

    monkeypatch.setattr(main, "generate_recommendation_cards", overloaded_provider)
    main.app.dependency_overrides[main._current_user] = lambda: {"id_usuario": 5}
    try:
        from fastapi.testclient import TestClient

        with TestClient(main.app) as client:
            response = client.post(
                "/api/v1/ai/ask",
                json={"prompt": "Lugares para hacer fotos de noche"},
            )
    finally:
        main.app.dependency_overrides.pop(main._current_user, None)

    assert response.status_code == 200
    assert response.json()["source"] == "fallback"
    assert {card["category"] for card in response.json()["cards"]} == {
        "Lugar",
        "Pose",
    }
