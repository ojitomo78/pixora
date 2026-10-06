from src.models.user import User
from src.services.api_client import APIError, ApiClient

class AuthController:
    def __init__(self, api_client: ApiClient | None = None):
        self.api_client = api_client or ApiClient()
        self.current_email = ""
        self.current_username = ""

    def register_user(
        self,
        nombre: str,
        apellido: str,
        usuario: str,
        correo: str,
        contraseña: str,
    ) -> tuple[bool, str]:
        if not all(value.strip() for value in (nombre, apellido, usuario)):
            return False, "Nombre, apellido y usuario son obligatorios."
        if not User.is_valid_email(correo):
            return False, "El correo electrónico no es válido."

        if not User.is_valid_password(contraseña):
            return False, "La contraseña debe tener al menos 6 caracteres."

        try:
            result = self.api_client.request(
                "POST",
                "/auth/register",
                json={
                    "nombre": nombre.strip(),
                    "apellido": apellido.strip(),
                    "usuario": usuario.strip(),
                    "correo": correo.strip(),
                    "contraseña": contraseña,
                },
            )
        except APIError as exc:
            return False, str(exc)
        access_token = result.get("access_token")
        user_id = result.get("user_id")
        username = result.get("username")
        if not access_token or not user_id or not username:
            return False, "La API no devolvió una sesión válida."
        self.api_client.access_token = access_token
        self.api_client.current_user_id = user_id
        self.current_email = correo
        self.current_username = username
        return True, "Usuario registrado con éxito."

    def login_user(self, identificador: str, contraseña: str) -> tuple[bool, str]:
        try:
            result = self.api_client.request(
                "POST",
                "/auth/login",
                json={"identificador": identificador.strip(), "contraseña": contraseña},
            )
        except APIError as exc:
            return False, str(exc)
        access_token = result.get("access_token")
        user_id = result.get("user_id")
        username = result.get("username")
        if not access_token or not user_id or not username:
            return False, "La API no devolvió una sesión válida."
        self.api_client.access_token = access_token
        self.api_client.current_user_id = user_id
        self.current_email = identificador
        self.current_username = username
        return True, f"Bienvenido, {self.current_username}!"

    def logout(self) -> None:
        self.api_client.access_token = None
        self.api_client.current_user_id = None
        self.current_email = ""
        self.current_username = ""