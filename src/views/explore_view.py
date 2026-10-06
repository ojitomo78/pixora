import asyncio

import flet as ft

from src.services.api_client import APIError


class ExploreView(ft.Column):
    def __init__(self, rec_controller):
        super().__init__(expand=True)
        self.rec_controller = rec_controller
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.active_main_tab = "poses"

        self.btn_poses_tab = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ACCESSIBILITY_NEW, size=18),
                    ft.Text("Poses & IA", weight=ft.FontWeight.BOLD),
                ],
                spacing=6,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border_radius=20,
            bgcolor=ft.Colors.BLUE_600,
            on_click=lambda e: self._switch_main_tab("poses"),
        )
        self.btn_spots_tab = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LOCATION_ON, size=18, color=ft.Colors.GREY_400),
                    ft.Text("Spots & Mapa", weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_400),
                ],
                spacing=6,
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            border_radius=20,
            bgcolor=ft.Colors.GREY_900,
            on_click=lambda e: self._switch_main_tab("spots"),
        )
        self.body_content = ft.Container(expand=True)
        self.controls = [
            ft.Text("Explora e Inspírate", size=18, weight=ft.FontWeight.BOLD),
            ft.Row(
                [self.btn_poses_tab, self.btn_spots_tab],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=10,
            ),
            self.body_content,
        ]
        self._render_poses_view()

    def _switch_main_tab(self, tab: str):
        if self.active_main_tab == tab:
            return
        self.active_main_tab = tab
        active, inactive = (
            (self.btn_poses_tab, self.btn_spots_tab)
            if tab == "poses"
            else (self.btn_spots_tab, self.btn_poses_tab)
        )
        active.bgcolor = ft.Colors.BLUE_600
        active.content.controls[0].color = ft.Colors.WHITE
        active.content.controls[1].color = ft.Colors.WHITE
        inactive.bgcolor = ft.Colors.GREY_900
        inactive.content.controls[0].color = ft.Colors.GREY_400
        inactive.content.controls[1].color = ft.Colors.GREY_400
        if tab == "poses":
            self._render_poses_view()
        else:
            self._render_spots_view()
        self.update()

    def _render_poses_view(self):
        self._render_ai_view(
            "Describe la sesión fotográfica y las poses que necesitas."
        )

    def _render_spots_view(self):
        self._render_ai_view(
            "Describe el lugar, estilo, ciudad y horario que buscas para tus fotos."
        )

    def _render_ai_view(self, hint_text: str):
        prompt_input = ft.TextField(
            label="¿Qué quieres explorar?",
            hint_text=hint_text,
            multiline=True,
            min_lines=2,
            max_lines=4,
            max_length=2000,
            expand=True,
        )
        status = ft.Text("", size=12)
        cards = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)

        def show_card_details(event, card):
            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Row(
                    [
                        ft.Text(card["title"], expand=True),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            tooltip="Cerrar",
                            on_click=lambda close_event: close_event.page.pop_dialog(),
                        ),
                    ]
                ),
                content=ft.Column(
                    [
                        ft.Text(card["category"], color=ft.Colors.AMBER_400),
                        ft.Text(card["description"]),
                        ft.Text(
                            card.get("location", ""),
                            color=ft.Colors.GREY_400,
                        ),
                    ],
                    tight=True,
                    width=460,
                ),
            )
            event.page.show_dialog(dialog)

        async def ask_pixora_ai(event):
            prompt = (prompt_input.value or "").strip()
            if not prompt:
                status.value = "Escribe una pregunta para recibir recomendaciones."
                status.color = ft.Colors.RED_400
                self.update()
                return
            status.value = "Consultando la IA..."
            status.color = ft.Colors.GREY_300
            cards.controls.clear()
            self.update()
            try:
                result = await asyncio.to_thread(
                    self.rec_controller.ask_ai_result, prompt
                )
                recommendations = result["cards"]
                status.value = (
                    f"Pixora encontró {len(recommendations)} ideas. "
                    "Selecciona una tarjeta para ampliarla."
                )
                if result.get("source") == "fallback":
                    status.value = (
                        "La IA no está disponible; "
                        "se muestran recomendaciones de respaldo."
                    )
                status.color = ft.Colors.GREEN_400
                for card in recommendations:
                    cards.controls.append(
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        card["category"],
                                        size=11,
                                        color=ft.Colors.AMBER_400,
                                    ),
                                    ft.Text(
                                        card["title"],
                                        weight=ft.FontWeight.BOLD,
                                        size=14,
                                    ),
                                    ft.Text(
                                        card["description"],
                                        size=12,
                                        color=ft.Colors.GREY_300,
                                        max_lines=3,
                                    ),
                                ],
                                spacing=5,
                            ),
                            bgcolor=ft.Colors.GREY_900,
                            padding=14,
                            border_radius=14,
                            border=ft.Border.all(1, ft.Colors.GREY_800),
                            on_click=lambda click_event, selected=card: show_card_details(
                                click_event, selected
                            ),
                        )
                    )
            except APIError as exc:
                status.value = str(exc)
                status.color = ft.Colors.RED_400
            self.update()

        self.body_content.content = ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.AUTO_AWESOME,
                                        color=ft.Colors.AMBER_400,
                                    ),
                                    ft.Text(
                                        "Pregunta a la IA de Pixora",
                                        weight=ft.FontWeight.BOLD,
                                        size=14,
                                    ),
                                ],
                                spacing=8,
                            ),
                            prompt_input,
                            ft.FilledButton(
                                "Preguntar a la IA de Pixora",
                                icon=ft.Icons.SEND,
                                on_click=ask_pixora_ai,
                            ),
                            status,
                        ],
                        spacing=10,
                    ),
                    bgcolor=ft.Colors.GREY_900,
                    padding=14,
                    border_radius=14,
                ),
                cards,
            ],
            spacing=12,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )
