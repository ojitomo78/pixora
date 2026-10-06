import asyncio
import flet as ft
import tkinter as tk
from tkinter import filedialog
from src.controllers.feed_controller import FeedController
from src.models.post import Post
from src.services.api_client import APIError

class FeedView(ft.Column):
    def __init__(self, current_username: str, feed_controller: FeedController, on_logout):
        super().__init__(expand=True)
        self.current_username = current_username
        self.feed_controller = feed_controller
        self.on_logout = on_logout
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.selected_file_path = ""
        self._post_cards: dict[str, ft.Control] = {}

        self.file_path_text = ft.Text("No has seleccionado ninguna imagen", size=11, color=ft.Colors.GREY_500, italic=True)
        self.status_text = ft.Text("", size=11)
        self.location_input = ft.TextField(
            label="Lugar (opcional)",
            hint_text="Ej.: La Candelaria, Mi Estudio",
            max_length=200,
        )
        self.pose_input = ft.TextField(
            label="Pose utilizada (opcional)",
            hint_text="Ej.: Retrato en picado, Pose de pie",
            max_length=200,
        )

        self.caption_input = ft.TextField(
            label="Título",
            hint_text="Escribe un título para la publicación...",
            multiline=True,
            min_lines=2,
            max_lines=3,
            border_radius=12,
            border_color=ft.Colors.GREY_800,
            fill_color=ft.Colors.GREY_900,
            text_size=13
        )
        self.description_input = ft.TextField(
            label="Descripción",
            hint_text="Describe la fotografía...",
            multiline=True,
            min_lines=2,
            max_lines=4,
            border_radius=12,
            border_color=ft.Colors.GREY_800,
            fill_color=ft.Colors.GREY_900,
            text_size=13,
        )
        self.feed_container = ft.ListView(
            expand=True,
            spacing=16,
            controls=[
                ft.Text(
                    "Cargando publicaciones...",
                    size=12,
                    color=ft.Colors.GREY_400,
                )
            ],
        )

        self.controls = [
            ft.Container(
                content=ft.Row([
                    ft.Row([
                        ft.Container(
                            content=ft.Text(self.current_username[0].upper(), weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            gradient=ft.LinearGradient(colors=[ft.Colors.PURPLE_600, ft.Colors.BLUE_500]),
                            padding=10,
                            shape=ft.BoxShape.CIRCLE
                        ),
                        ft.Column([
                            ft.Text(f"@{self.current_username}", weight=ft.FontWeight.BOLD, size=15),
                            ft.Text("Fotógrafo Creador", size=11, color=ft.Colors.GREY_400)
                        ], spacing=0)
                    ]),
                    ft.IconButton(
                        icon=ft.Icons.LOGOUT_ROUNDED,
                        icon_color=ft.Colors.RED_400,
                        tooltip="Cerrar Sesión",
                        on_click=lambda e: self.on_logout()
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=ft.Padding.symmetric(horizontal=4, vertical=2)
            ),

            ft.Container(
                content=ft.TextButton(
                    "+ Nueva Publicación",
                    icon=ft.Icons.ADD_A_PHOTO_ROUNDED,
                    on_click=self._open_create_post_dialog,
                ),
                alignment=ft.Alignment.CENTER_RIGHT,
            ),

            ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
            self.feed_container
        ]

    def _open_create_post_dialog(self, e):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Nueva publicación"),
            content=ft.Column(
                [
                    self.caption_input,
                    self.description_input,
                    self.location_input,
                    self.pose_input,
                    ft.Row(
                        [
                            ft.TextButton(
                                "Elegir imagen",
                                icon=ft.Icons.FOLDER_OPEN,
                                on_click=self._open_native_file_picker,
                            ),
                            self.file_path_text,
                        ],
                        wrap=True,
                    ),
                    self.status_text,
                ],
                width=420,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton(
                    "Cancelar", on_click=lambda event: event.page.pop_dialog()
                ),
                ft.TextButton("Publicar", on_click=self._handle_create_post),
            ],
        )
        e.page.show_dialog(dialog)

    def _open_native_file_picker(self, e):
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_path = filedialog.askopenfilename(
            title="Selecciona una imagen para Pixora",
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.webp")]
        )
        root.destroy()

        if file_path:
            self.selected_file_path = file_path
            filename = file_path.split("/")[-1].split("\\")[-1]
            self.file_path_text.value = f"📷 {filename}"
            self.file_path_text.color = ft.Colors.GREEN_400
            self.update()

    def _handle_create_post(self, e):
        caption = self.caption_input.value or ""
        success, message = self.feed_controller.create_post(
            self.selected_file_path,
            caption,
            None,
            self.description_input.value or "",
            localizacion_texto=self.location_input.value or "",
            pose_utilizada=self.pose_input.value or "",
        )
        self.status_text.value = message
        self.status_text.color = ft.Colors.GREEN_400 if success else ft.Colors.RED_400
        if not success:
            self.update()
            return

        self.selected_file_path = ""
        self.caption_input.value = ""
        self.description_input.value = ""
        self.location_input.value = ""
        self.pose_input.value = ""
        self.file_path_text.value = "No has seleccionado ninguna imagen"
        self.file_path_text.color = ft.Colors.GREY_500
        e.page.pop_dialog()
        self._render_feed()
        self.update()

    async def load_feed(self):
        try:
            posts = await asyncio.to_thread(self.feed_controller.get_feed)
        except APIError as exc:
            self.feed_container.controls = [
                ft.Text(str(exc), color=ft.Colors.RED_400, size=12)
            ]
        else:
            self._render_feed(posts)
        self.update()

    def _render_feed(self, posts: list[Post] | None = None):
        self.feed_container.controls.clear()
        self._post_cards.clear()
        if posts is None:
            try:
                posts = self.feed_controller.get_feed()
            except APIError as exc:
                self.feed_container.controls.append(
                    ft.Text(str(exc), color=ft.Colors.RED_400, size=12)
                )
                return

        for post in posts:
            like_count = ft.Text(str(post.likes_count), size=12)
            like_button = ft.IconButton(
                icon=(
                    ft.Icons.FAVORITE
                    if post.liked_by_me
                    else ft.Icons.FAVORITE_BORDER
                ),
                icon_color=ft.Colors.RED_400 if post.liked_by_me else ft.Colors.GREY_400,
                tooltip="Me gusta",
            )

            async def toggle_like(event, target=post, button=like_button, count=like_count):
                previous_state = target.liked_by_me
                previous_count = target.likes_count
                target.liked_by_me = not previous_state
                target.likes_count += 1 if target.liked_by_me else -1
                button.icon = (
                    ft.Icons.FAVORITE
                    if target.liked_by_me
                    else ft.Icons.FAVORITE_BORDER
                )
                button.icon_color = (
                    ft.Colors.RED_400 if target.liked_by_me else ft.Colors.GREY_400
                )
                count.value = str(target.likes_count)
                button.disabled = True
                event.page.update()
                try:
                    result = await asyncio.to_thread(
                        self.feed_controller.toggle_like, target.post_id
                    )
                except APIError as exc:
                    target.liked_by_me = previous_state
                    target.likes_count = previous_count
                    button.icon = (
                        ft.Icons.FAVORITE
                        if previous_state
                        else ft.Icons.FAVORITE_BORDER
                    )
                    button.icon_color = (
                        ft.Colors.RED_400 if previous_state else ft.Colors.GREY_400
                    )
                    count.value = str(previous_count)
                    event.page.show_dialog(ft.SnackBar(ft.Text(str(exc))))
                else:
                    target.liked_by_me = result["liked"]
                    target.likes_count = result["likes_count"]
                    count.value = str(target.likes_count)
                    button.icon = (
                        ft.Icons.FAVORITE
                        if target.liked_by_me
                        else ft.Icons.FAVORITE_BORDER
                    )
                    button.icon_color = (
                        ft.Colors.RED_400
                        if target.liked_by_me
                        else ft.Colors.GREY_400
                    )
                button.disabled = False
                event.page.update()

            like_button.on_click = toggle_like
            is_own_post = (
                post.author_id == self.feed_controller.api_client.current_user_id
            )
            options_menu = ft.Container(width=40)

            card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([
                            ft.CircleAvatar(content=ft.Text(post.author[0].upper()), radius=14, bgcolor=ft.Colors.PURPLE_800),
                            ft.Text(f"@{post.author}", weight=ft.FontWeight.BOLD, size=13)
                        ]),
                        options_menu
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

                    ft.Container(
                        content=ft.Image(
                            src=post.image_data,
                            height=240,
                            fit=ft.BoxFit.COVER,
                        ),
                        border_radius=12,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                        on_click=lambda e, image=post.image_data: self._open_lightbox(
                            e, image
                        ),
                    ),

                    ft.Row([
                        ft.Row([
                            like_button,
                            like_count,
                            ft.IconButton(
                                icon=ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
                                tooltip="Comentarios",
                                on_click=lambda e, p_id=post.post_id: self._open_comments(e, p_id),
                            ),
                        ], spacing=2),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

                    ft.Row([
                        ft.Text(f"@{post.author}", weight=ft.FontWeight.BOLD, size=12),
                        ft.Text(post.caption, size=12, color=ft.Colors.GREY_300)
                    ], wrap=True)
                ], spacing=6),
                bgcolor=ft.Colors.GREY_900,
                padding=12,
                border_radius=16,
                border=ft.Border.all(1, ft.Colors.GREY_800)
            )
            if post.location:
                card.content.controls.append(
                    ft.Text(
                        f"📍 {post.location}",
                        size=11,
                        color=ft.Colors.AMBER_400,
                    )
                )
            if post.description:
                card.content.controls.append(
                    ft.Text(post.description, size=12, color=ft.Colors.GREY_300)
                )
            if post.pose_utilizada:
                card.content.controls.append(
                    ft.Text(
                        f"Pose: {post.pose_utilizada}",
                        size=11,
                        color=ft.Colors.PURPLE_300,
                    )
                )
            if is_own_post:
                header = card.content.controls[0]
                header.controls[1] = ft.PopupMenuButton(
                    icon=ft.Icons.MORE_HORIZ,
                    icon_color=ft.Colors.GREY_500,
                    items=[
                        ft.PopupMenuItem(
                            content="Eliminar publicación",
                            icon=ft.Icons.DELETE_OUTLINED,
                            on_click=lambda event, publication_id=post.post_id, card_control=card: self._confirm_delete(
                                event, publication_id, card_control
                            ),
                        )
                    ],
                )
            self.feed_container.controls.append(card)
            self._post_cards[post.post_id] = card

    def _confirm_delete(self, event, post_id: str, card_control: ft.Control):
        async def confirm_delete(confirm_event):
            await self._delete_post(confirm_event, post_id, card_control)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Eliminar publicación"),
            content=ft.Text(
                "¿Estás seguro de que deseas eliminar esta publicación?"
            ),
            actions=[
                ft.TextButton(
                    "Cancelar", on_click=lambda close_event: close_event.page.pop_dialog()
                ),
                ft.TextButton(
                    "Eliminar",
                    on_click=confirm_delete,
                ),
            ],
        )
        event.page.show_dialog(dialog)

    async def _delete_post(self, event, post_id: str, card_control: ft.Control):
        event.page.pop_dialog()
        deleted = await self.feed_controller.delete_post(
            post_id,
            card_control,
            event.page,
            self.feed_container.controls,
        )
        if deleted:
            self._post_cards.pop(post_id, None)

    def _open_lightbox(self, e, image_data: bytes):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Text("Fotografía"),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        tooltip="Cerrar",
                        on_click=lambda event: event.page.pop_dialog(),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            content=ft.Image(
                src=image_data,
                width=1000,
                height=720,
                fit=ft.BoxFit.CONTAIN,
            ),
        )
        e.page.show_dialog(dialog)

    def _open_comments(self, e, post_id: str):
        page = e.page
        comments = ft.Column(spacing=8, height=260, scroll=ft.ScrollMode.AUTO)
        comment_input = ft.TextField(
            hint_text="Escribe un comentario",
            multiline=True,
            min_lines=1,
            max_lines=3,
        )
        message = ft.Text("", size=11)

        def render_comments():
            comments.controls.clear()
            try:
                items = self.feed_controller.get_comments(post_id)
            except APIError as exc:
                comments.controls.append(ft.Text(str(exc), color=ft.Colors.RED_400))
                return
            if not items:
                comments.controls.append(
                    ft.Text("Todavía no hay comentarios.", color=ft.Colors.GREY_400)
                )
            for item in items:
                comments.controls.append(
                    ft.Column(
                        [
                            ft.Text(
                                f"@{item['author']}",
                                weight=ft.FontWeight.BOLD,
                                size=12,
                            ),
                            ft.Text(item["text"], size=12),
                        ],
                        spacing=2,
                    )
                )

        def submit_comment(event):
            text = (comment_input.value or "").strip()
            if not text:
                message.value = "Escribe un comentario antes de enviarlo."
                message.color = ft.Colors.RED_400
                event.page.update()
                return
            try:
                self.feed_controller.add_comment(post_id, text)
            except APIError as exc:
                message.value = str(exc)
                message.color = ft.Colors.RED_400
            else:
                comment_input.value = ""
                message.value = ""
                render_comments()
            event.page.update()

        render_comments()
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Comentarios"),
            content=ft.Column(
                [comments, comment_input, message],
                width=360,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Enviar", on_click=submit_comment),
                ft.TextButton("Cerrar", on_click=lambda event: event.page.pop_dialog()),
            ],
        )
        page.show_dialog(dialog)