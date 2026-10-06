from backend import postgres_access
from backend import db_connection


def test_create_user_uses_exact_users_columns(monkeypatch):
    captured = {}

    def fake_fetch_one(query, parameters):
        captured["query"] = query
        captured["parameters"] = parameters
        return {"id_usuario": 7}

    monkeypatch.setattr(postgres_access, "_fetch_one", fake_fetch_one)

    postgres_access.create_user("Ana", "López", "ana", "ana@example.com", "hash")

    query = captured["query"]
    assert "INSERT INTO usuarios" in query
    assert "(nombre, apellido, usuario, correo, \"contraseña\", fecha_registro)" in query
    assert "RETURNING id_usuario, nombre, apellido, usuario, correo, fecha_registro" in query
    assert captured["parameters"] == (
        "Ana",
        "López",
        "ana",
        "ana@example.com",
        "hash",
    )


def test_locations_and_session_types_only_select_declared_columns(monkeypatch):
    queries = []

    def fake_fetch_all(query, parameters=()):
        queries.append((query, parameters))
        return []

    monkeypatch.setattr(postgres_access, "_fetch_all", fake_fetch_all)

    postgres_access.list_locations("Bogotá")
    postgres_access.list_session_types()

    assert "FROM localizaciones" in queries[0][0]
    assert all(
        column in queries[0][0]
        for column in (
            "id_localizacion",
            "nombre",
            "ciudad",
            "pais",
            "descripcion",
            "coordenadas",
        )
    )
    assert queries[0][1] == ("Bogotá",)
    assert "FROM tipo_sesion_fotografica" in queries[1][0]
    assert all(
        column in queries[1][0]
        for column in (
            "id_tipo_sesion",
            "nombre",
            "descripcion",
            "categoria",
            "recomendaciones",
        )
    )


def test_mongo_collection_accessor_only_allows_confirmed_names(monkeypatch):
    class FakeDatabase:
        def __getitem__(self, name):
            return name

    monkeypatch.setattr(db_connection, "get_mongo_database", lambda: FakeDatabase())

    assert (
        db_connection.get_mongo_collection("CONTENEDORES_FOTOGRAFÍAS")
        == "CONTENEDORES_FOTOGRAFÍAS"
    )
    try:
        db_connection.get_mongo_collection("posts")
    except ValueError as error:
        assert "esquema MongoDB confirmado" in str(error)
    else:
        raise AssertionError("No debe permitirse una colección no confirmada.")


def test_postgres_connector_reads_dsn_from_environment(monkeypatch):
    class FakeConnection:
        closed = 0

    connection_marker = FakeConnection()
    captured = {"pool_calls": [], "getconn_calls": 0, "putconn_calls": 0}

    class FakePool:
        def __init__(self, minconn, maxconn, **kwargs):
            captured["pool_calls"].append((minconn, maxconn, kwargs))

        def getconn(self):
            captured["getconn_calls"] += 1
            return connection_marker

        def putconn(self, connection, close=False):
            assert connection is connection_marker
            assert close is False
            captured["putconn_calls"] += 1

    monkeypatch.setenv("POSTGRES_DSN", "postgresql://local/test")
    monkeypatch.setattr(db_connection, "_postgres_pool", None)
    monkeypatch.setattr(db_connection, "ThreadedConnectionPool", FakePool)

    first_connection = db_connection.get_postgres_connection()
    db_connection.release_postgres_connection(first_connection)
    second_connection = db_connection.get_postgres_connection()
    db_connection.release_postgres_connection(second_connection)

    assert first_connection is second_connection is connection_marker
    assert captured["pool_calls"] == [
        (1, 10, {"dsn": "postgresql://local/test", "connect_timeout": 5})
    ]
    assert captured["getconn_calls"] == 2
    assert captured["putconn_calls"] == 2


def test_create_publication_accepts_an_optional_location(monkeypatch):
    captured = {}

    def fake_fetch_one(query, parameters):
        captured["query"] = query
        captured["parameters"] = parameters
        return {"id_publicacion": 9}

    monkeypatch.setattr(postgres_access, "_fetch_one", fake_fetch_one)

    postgres_access.create_publication(7, None, "Título", "", "publica")

    assert "id_localizacion" in captured["query"]
    assert captured["parameters"] == (7, None, "Título", "", "publica")


def test_delete_publication_is_scoped_to_owner_and_reports_deleted_row(monkeypatch):
    captured = {}

    def fake_fetch_one(query, parameters):
        captured["query"] = query
        captured["parameters"] = parameters
        return {"id_publicacion": 18}

    monkeypatch.setattr(postgres_access, "_fetch_one", fake_fetch_one)

    assert postgres_access.delete_publication(18, 7) is True
    assert "DELETE FROM publicaciones" in captured["query"]
    assert "WHERE id_publicacion = %s AND id_usuario = %s" in captured["query"]
    assert captured["parameters"] == (18, 7)

    monkeypatch.setattr(postgres_access, "_fetch_one", lambda *_args: None)

    assert postgres_access.delete_publication(18, 7) is False
