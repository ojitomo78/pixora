

from concurrent.futures import ThreadPoolExecutor
import asyncio
import mimetypes
from collections.abc import MutableSequence

import flet as ft
from src.models.post import Post
from src.services.api_client import APIError, ApiClient

class FeedController:
    def __init__(self, api_client: ApiClient | None = None):
        self.api_client = api_client or ApiClient()
        self._image_cache: dict[str, bytes] = {}

    def get_locations(self) -> list[dict[str, str | int]]:
        return self.api_client.request("GET", "/spots")

    def create_post(
        self,
        image_path: str,
        caption: str,
        id_localizacion: int | None,
        descripcion: str = "",
        localizacion_texto: str = "",
        pose_utilizada: str = "",
    ) -> tuple[bool, str]:
        if not image_path.strip():
            return False, "Selecciona una imagen antes de publicar."
        if not caption.strip():
            return False, "Escribe un título antes de publicar."
        try:
            with open(image_path, "rb") as image:
                form_data = {
                    "titulo": caption.strip(),
                    "descripcion": descripcion.strip(),
                    "visibilidad": "publica",
                }
                if id_localizacion is not None:
                    form_data["id_localizacion"] = str(id_localizacion)
                if localizacion_texto.strip():
                    form_data["localizacion_texto"] = localizacion_texto.strip()
                if pose_utilizada.strip():
                    form_data["pose_utilizada"] = pose_utilizada.strip()
                self.api_client.request(
                    "POST",
                    "/posts",
                    data=form_data,
                    files={
                        "image": (
                            image_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
                            image,
                            mimetypes.guess_type(image_path)[0] or "application/octet-stream",
                        )
                    },
                )
        except (APIError, OSError) as exc:
            return False, str(exc)
        return True, "Publicación creada exitosamente."

    def get_feed(self) -> list[Post]:
        posts = self.api_client.request("GET", "/posts")
        result: list[Post | None] = [None] * len(posts)
        active_post_ids = {item["id"] for item in posts}
        self._image_cache = {
            post_id: image
            for post_id, image in self._image_cache.items()
            if post_id in active_post_ids
        }

        missing_images = [
            (index, item)
            for index, item in enumerate(posts)
            if item["id"] not in self._image_cache
        ]
        if missing_images:
            with ThreadPoolExecutor(max_workers=min(8, len(missing_images))) as pool:
                futures = {
                    index: pool.submit(
                        self.api_client.download,
                        f"/api/v1/media/{item['media_id']}",
                    )
                    for index, item in missing_images
                }
                for index, item in missing_images:
                    self._image_cache[posts[index]["id"]] = futures[index].result()

        for index, item in enumerate(posts):
            image_data = self._image_cache[item["id"]]
            post = Post(
                item["id"],
                item["author"],
                image_data,
                item["caption"],
                item.get("description", ""),
                item.get("location"),
                item.get("pose_utilizada"),
                item.get("author_id", ""),
                item.get("likes_count", 0),
                item.get("liked_by_me", False),
            )
            result[index] = post
        return [post for post in result if post is not None]

    def toggle_like(self, post_id: str) -> dict[str, bool | int]:
        return self.api_client.request("POST", f"/posts/{post_id}/like")

    async def delete_post(
        self,
        post_id: str,
        card_control: ft.Control,
        page: ft.Page,
        feed_controls: MutableSequence[ft.Control],
    ) -> bool:
        try:
            await asyncio.to_thread(
                self.api_client.request, "DELETE", f"/posts/{post_id}"
            )
        except APIError as exc:
            page.show_dialog(ft.SnackBar(ft.Text(str(exc))))
            page.update()
            return False

        if card_control in feed_controls:
            feed_controls.remove(card_control)
        page.show_dialog(ft.SnackBar(ft.Text("Publicación eliminada")))
        page.update()
        return True

    def get_comments(self, post_id: str) -> list[dict[str, str]]:
        return self.api_client.request("GET", f"/posts/{post_id}/comments")

    def add_comment(self, post_id: str, text: str) -> dict[str, str]:
        return self.api_client.request(
            "POST", f"/posts/{post_id}/comments", json={"comentario": text}
        )