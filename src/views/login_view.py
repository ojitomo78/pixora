import flet as ft

from src.controllers.auth_controller import AuthController


class LoginView(ft.Column):
    def __init__(self, auth_controller: AuthController, on_login_success):
        super().__init__()
        self.auth_controller = auth_controller
        self.on_login_success = on_login_success
        self.mode = "login"
        self.alignment = ft.MainAxisAlignment.CENTER
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER

        self.login_identifier_input = ft.TextField(
            label="Usuario o correo", width=300
        )
        self.login_password_input = ft.TextField(
            label="Contraseña", password=True, can_reveal_password=True, width=300
        )
        self.first_name_input = ft.TextField(label="Nombre", width=300)
        self.last_name_input = ft.TextField(label="Apellido", width=300)
        self.username_input = ft.TextField(label="Usuario", width=300)
        self.email_input = ft.TextField(label="Correo electrónico", width=300)
        self.register_password_input = ft.TextField(
            label="Contraseña", password=True, can_reveal_password=True, width=300
        )
        self.message_text = ft.Text(value="", color=ft.Colors.RED_400)
        self.form_container = ft.Container()
        self.controls = [
            ft.Text("Pixora", size=36, weight=ft.FontWeight.BOLD),
            ft.Text("Tu portafolio fotográfico", size=14, color=ft.Colors.GREY_400),
            ft.Container(height=10),
            ft.Row(
                [
                    ft.Button(
                        "Iniciar sesión", on_click=lambda e: self._handle_mode("login")
                    ),
                    ft.Button(
                        "Crear cuenta", on_click=lambda e: self._handle_mode("register")
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            self.form_container,
            self.message_text,
        ]
        self._set_mode("login")

    def _handle_mode(self, mode: str):
        self._set_mode(mode)
        self.update()

    def _set_mode(self, mode: str):
        self.mode = mode
        if mode == "login":
            self.form_container.content = ft.Column(
                [
                    ft.Text("Iniciar sesión", size=20, weight=ft.FontWeight.BOLD),
                    self.login_identifier_input,
                    self.login_password_input,
                    ft.Button("Entrar", on_click=self._handle_login),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            )
        else:
            self.form_container.content = ft.Column(
                [
                    ft.Text("Crear cuenta", size=20, weight=ft.FontWeight.BOLD),
                    self.first_name_input,
                    self.last_name_input,
                    self.username_input,
                    self.email_input,
                    self.register_password_input,
                    ft.Button("Registrarse", on_click=self._handle_register),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            )
        self.message_text.value = ""

    def _handle_login(self, e):
        identifier = self.login_identifier_input.value or ""
        password = self.login_password_input.value or ""
        success, message = self.auth_controller.login_user(identifier, password)
        if success:
            self.message_text.color = ft.Colors.GREEN_400
            self.message_text.value = message
            self.update()
            self.on_login_success()
        else:
            self.message_text.color = ft.Colors.RED_400
            self.message_text.value = message
            self.update()

    def _handle_register(self, e):
        success, message = self.auth_controller.register_user(
            self.first_name_input.value or "",
            self.last_name_input.value or "",
            self.username_input.value or "",
            self.email_input.value or "",
            self.register_password_input.value or "",
        )
        self.message_text.color = ft.Colors.GREEN_400 if success else ft.Colors.RED_400
        self.message_text.value = message
        self.update()
        if success and self.auth_controller.api_client.access_token:
            self.on_login_success()
