from src.controllers.recommendation_controller import RecommendationController


class FakeApiClient:
    def request(self, method, path, **kwargs):
        if method == "POST" and path == "/ai/poses":
            assert kwargs["json"] == {"session_type": "Retrato urbano"}
            return {"recommendation": "Prueba de IA"}
        if method == "GET" and path == "/spots":
            return [
                {
                    "id_localizacion": 1,
                    "nombre": "Mirador",
                    "ciudad": "Bogotá",
                    "pais": "Colombia",
                    "descripcion": "Vista abierta.",
                    "coordenadas": "4.6, -74.1",
                }
            ]
        if method == "GET" and path == "/session-types":
            return [
                {
                    "id_tipo_sesion": 1,
                    "nombre": "Retrato urbano",
                    "descripcion": "Retrato en ciudad",
                    "categoria": "Retrato",
                    "recomendaciones": "Usa luz lateral.",
                }
            ]
        if method == "POST" and path == "/ai/spots":
            return {"recommendation": "Elige el mirador guardado."}
        if method == "POST" and path == "/ai/ask":
            return {
                "cards": [
                    {
                        "category": "Lugar",
                        "title": "Plaza",
                        "description": "Una plaza tranquila.",
                        "location": "Bogotá",
                    }
                ]
            }
        raise AssertionError(f"Unexpected request: {method} {path}")


def test_generar_recomendaciones_de_poses():
    rec = RecommendationController(FakeApiClient())

    assert rec.recommend_poses("Retrato urbano") == "Prueba de IA"


def test_obtener_lugares_desde_api():
    rec = RecommendationController(FakeApiClient())

    spots = rec.get_spots("Bogotá")

    assert len(spots) == 1
    assert spots[0].nombre == "Mirador"
    assert spots[0].coordenadas == "4.6, -74.1"


def test_obtener_tipos_de_sesion_desde_api():
    rec = RecommendationController(FakeApiClient())

    session_types = rec.get_session_types()

    assert session_types[0].id_tipo_sesion == 1
    assert session_types[0].recomendaciones == "Usa luz lateral."


def test_recomendar_lugar_basado_en_datos():
    rec = RecommendationController(FakeApiClient())

    assert rec.recommend_spots("Bogotá", "Atardecer") == "Elige el mirador guardado."


def test_consultar_ia_libre_devuelve_tarjetas():
    rec = RecommendationController(FakeApiClient())

    cards = rec.ask_ai("Lugares vintage por la noche")

    assert cards[0]["category"] == "Lugar"
    assert cards[0]["title"] == "Plaza"
