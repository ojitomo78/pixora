import base64
from datetime import datetime, timezone

from backend import db_connection, mongo_access


class FakeCollection:
    def __init__(self):
        self.document = None
        self.query = None

    def replace_one(self, query, document, upsert):
        self.query = query
        self.document = document
        assert upsert is True

    def find_one(self, query, _projection):
        self.query = query
        self.projection = _projection
        return self.document

    def insert_one(self, document):
        self.document = document

        class Result:
            inserted_id = "mongo-id"

        return Result()

    def update_one(self, query, update, upsert):
        self.query = query
        self.update = update
        assert upsert is True
        self.document = {
            **update.get("$setOnInsert", {}),
            **update.get("$set", {}),
        }

    def delete_one(self, query):
        self.query = query

        class Result:
            deleted_count = 1

        return Result()

    def delete_many(self, query):
        self.query = query

        class Result:
            deleted_count = 1

        return Result()


def test_image_uses_only_confirmed_container_fields(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(mongo_access, "get_mongo_collection", lambda _: collection)

    document = mongo_access.save_publication_image(5, b"image-bytes", "image/jpeg")

    assert set(document) == {
        "id_publicacion",
        "url_imagen",
        "formato",
        "tamano_bytes",
    }
    assert document["url_imagen"] == (
        "data:image/jpeg;base64,"
        + base64.b64encode(b"image-bytes").decode("ascii")
    )
    assert mongo_access.get_publication_image(5) == (b"image-bytes", "image/jpeg")


def test_image_save_works_when_allowed_collection_is_empty(monkeypatch):
    collection = FakeCollection()

    class EmptyDatabase:
        def __getitem__(self, name):
            assert name == "CONTENEDORES_FOTOGRAFÍAS"
            return collection

    monkeypatch.setattr(db_connection, "get_mongo_database", lambda: EmptyDatabase())
    monkeypatch.setattr(
        mongo_access,
        "get_mongo_collection",
        db_connection.get_mongo_collection,
    )

    document = mongo_access.save_publication_image(19, b"compressed", "image/jpeg")

    assert document["id_publicacion"] == 19
    assert collection.document == document


def test_comment_uses_only_confirmed_community_fields(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(mongo_access, "get_mongo_collection", lambda _: collection)

    result = mongo_access.add_publication_comment(9, 2, "Buen retrato")

    assert set(collection.document) == {
        "id_publicacion",
        "id_usuario",
        "comentario",
        "fecha",
    }
    assert result["id"] == "mongo-id"
    assert isinstance(collection.document["fecha"], datetime)
    assert collection.document["fecha"].tzinfo == timezone.utc


def test_publication_details_store_optional_pose_in_confirmed_collection(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(mongo_access, "get_mongo_collection", lambda _: collection)

    mongo_access.save_publication_details(12, "", "", "", 0, "", "Pose de pie")

    assert collection.document == {
        "id_publicacion": 12,
        "camara": "",
        "lente": "",
        "apertura": "",
        "iso": 0,
        "velocidad_obturacion": "",
        "pose_utilizada": "Pose de pie",
    }


def test_toggle_publication_like_updates_the_atomic_reaction_document(monkeypatch):
    captured = {}

    class LikeCollection:
        def find_one_and_update(
            self, query, pipeline, *, upsert, return_document
        ):
            captured.update(
                query=query,
                pipeline=pipeline,
                upsert=upsert,
                return_document=return_document,
            )
            return {
                "id_publicacion": 12,
                "likes_by": [3, 8],
                "likes_count": 2,
            }

    monkeypatch.setattr(
        mongo_access, "get_mongo_collection", lambda _: LikeCollection()
    )

    result = mongo_access.toggle_publication_like(12, 8)

    assert result == {"liked": True, "likes_count": 2}
    assert captured["query"] == {"id_publicacion": 12}
    assert len(captured["pipeline"]) == 2
    assert captured["upsert"] is True


def test_delete_publication_comments_uses_publication_id(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(mongo_access, "get_mongo_collection", lambda _: collection)

    mongo_access.delete_publication_comments(14)

    assert collection.query == {"id_publicacion": 14}
