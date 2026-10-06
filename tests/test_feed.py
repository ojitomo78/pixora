import asyncio
import inspect
import threading
from types import SimpleNamespace

import flet as ft

from src.controllers.feed_controller import FeedController
from src.views.feed_view import FeedView


class FakeApiClient:
    def __init__(self):
        self.access_token = "token"
        self.current_user_id = "user-1"
        self.posts = []
        self.requests = []
        self.submitted = None
        self.deleted = []

    def request(self, method, path, **kwargs):
        self.requests.append((method, path))
        if method == "POST" and path == "/posts":
            file_tuple = kwargs["files"]["image"]
            self.submitted = kwargs["data"]
            self.posts.insert(
                0,
                {
                    "id": "post-1",
                    "author_id": "user-1",
                    "author": "ana",
                    "caption": kwargs["data"]["titulo"],
                    "media_id": "media-1",
                },
            )
            assert file_tuple[1].read() == b"image-content"
            return {}
        if method == "GET" and path == "/spots":
            return [{
                "id_localizacion": 4,
                "nombre": "Parque",
                "ciudad": "Bogotá",
                "pais": "Colombia",
                "descripcion": "",
                "coordenadas": "",
            }]
        if method == "GET" and path == "/posts":
            return self.posts
        if method == "POST" and path == "/posts/post-1/like":
            return {"liked": True, "likes_count": 1}
        if method == "DELETE" and path == "/posts/post-1":
            self.deleted.append(path)
            return {"status": "deleted"}
        raise AssertionError(f"Unexpected request: {method} {path}")

    def download(self, path):
        assert "/media/media-1" in path
        return b"thumbnail"


def test_crear_publicacion_con_imagen(tmp_path):
    api = FakeApiClient()
    feed = FeedController(api)
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"image-content")

    exito, mensaje = feed.create_post(str(image), "Mi primera foto", 4)

    assert exito is True
    assert mensaje == "Publicación creada exitosamente."
    assert len(feed.get_feed()) == 1
    assert feed.get_feed()[0].image_data == b"thumbnail"
    assert api.submitted["titulo"] == "Mi primera foto"
    assert api.submitted["id_localizacion"] == "4"
    assert api.submitted["visibilidad"] == "publica"


def test_feed_view_no_consulta_el_feed_durante_su_constructor():
    api = FakeApiClient()

    FeedView("ana", FeedController(api), lambda: None)

    assert ("GET", "/posts") not in api.requests


def test_get_feed_descarga_imagenes_en_paralelo():
    class ParallelApi(FakeApiClient):
        def __init__(self):
            super().__init__()
            self.download_barrier = threading.Barrier(3)
            self.posts = [
                {
                    "id": f"post-{index}",
                    "author_id": "user-1",
                    "author": "ana",
                    "caption": f"Foto {index}",
                    "media_id": f"media-{index}",
                }
                for index in range(3)
            ]

        def download(self, path):
            self.download_barrier.wait(timeout=2)
            return path.encode()

    feed = FeedController(ParallelApi())

    posts = feed.get_feed()

    assert [post.post_id for post in posts] == ["post-0", "post-1", "post-2"]
    assert [post.image_data for post in posts] == [
        b"/api/v1/media/media-0",
        b"/api/v1/media/media-1",
        b"/api/v1/media/media-2",
    ]


def test_publicacion_sin_imagen_no_llama_api():
    api = FakeApiClient()
    feed = FeedController(api)

    exito, mensaje = feed.create_post("  ", "Sin foto", 4)

    assert exito is False
    assert mensaje == "Selecciona una imagen antes de publicar."
    assert api.posts == []


def test_crear_publicacion_sin_localizacion_omite_el_campo(tmp_path):
    api = FakeApiClient()
    feed = FeedController(api)
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"image-content")

    exito, _ = feed.create_post(str(image), "Foto sin ubicación", None)

    assert exito is True
    assert "id_localizacion" not in api.submitted


def test_crear_publicacion_envia_lugar_libre_y_pose(tmp_path):
    api = FakeApiClient()
    feed = FeedController(api)
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"image-content")

    exito, _ = feed.create_post(
        str(image),
        "Retrato",
        None,
        localizacion_texto="Mi Estudio",
        pose_utilizada="Retrato en picado",
    )

    assert exito is True
    assert api.submitted["localizacion_texto"] == "Mi Estudio"
    assert api.submitted["pose_utilizada"] == "Retrato en picado"


def test_like_and_delete_delegate_to_authenticated_api():
    api = FakeApiClient()
    feed = FeedController(api)

    assert feed.toggle_like("post-1") == {"liked": True, "likes_count": 1}

    class Page:
        def __init__(self):
            self.dialogs = []
            self.updated = False

        def show_dialog(self, dialog):
            self.dialogs.append(dialog)

        def update(self):
            self.updated = True

    page = Page()
    card = ft.Container()
    controls = [card]
    assert asyncio.run(feed.delete_post("post-1", card, page, controls)) is True
    assert api.deleted == ["/posts/post-1"]
    assert controls == []
    assert page.dialogs[-1].content.value == "Publicación eliminada"
    assert page.updated is True


def test_delete_api_error_is_shown_and_card_is_kept():
    class FailingApi(FakeApiClient):
        def request(self, method, path, **kwargs):
            if method == "DELETE":
                from src.services.api_client import APIError

                raise APIError("No autorizado", 403)
            return super().request(method, path, **kwargs)

    class Page:
        def __init__(self):
            self.dialogs = []
            self.updated = False

        def show_dialog(self, dialog):
            self.dialogs.append(dialog)

        def update(self):
            self.updated = True

    page = Page()
    card = ft.Container()
    controls = [card]
    feed = FeedController(FailingApi())

    assert asyncio.run(feed.delete_post("post-1", card, page, controls)) is False
    assert controls == [card]
    assert page.dialogs[-1].content.value == "No autorizado"
    assert page.updated is True


def test_feed_delete_menu_confirms_and_removes_card_without_refetch():
    class Page:
        def __init__(self):
            self.dialogs = []
            self.popped = 0
            self.updated = 0

        def show_dialog(self, dialog):
            self.dialogs.append(dialog)

        def pop_dialog(self):
            self.popped += 1

        def update(self):
            self.updated += 1

    api = FakeApiClient()
    api.posts.append(
        {
            "id": "post-1",
            "author_id": "user-1",
            "author": "ana",
            "caption": "Retrato",
            "media_id": "media-1",
        }
    )
    controller = FeedController(api)
    view = FeedView("ana", controller, lambda: None)
    view._render_feed(controller.get_feed())
    card = view._post_cards["post-1"]
    menu = card.content.controls[0].controls[1]
    page = Page()
    event = SimpleNamespace(page=page)

    assert len(menu.items) == 1
    assert menu.items[0].content == "Eliminar publicación"
    assert menu.items[0].icon == ft.Icons.DELETE_OUTLINED

    menu.items[0].on_click(event)
    assert (
        page.dialogs[-1].content.value
        == "¿Estás seguro de que deseas eliminar esta publicación?"
    )

    confirm_handler = page.dialogs[-1].actions[1].on_click
    assert inspect.iscoroutinefunction(confirm_handler)
    asyncio.run(confirm_handler(event))

    assert api.deleted == ["/posts/post-1"]
    assert view.feed_container.controls == []
    assert page.dialogs[-1].content.value == "Publicación eliminada"
    assert page.updated == 1
