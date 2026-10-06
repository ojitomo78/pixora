from src.controllers.auth_controller import AuthController
from src.views.login_view import LoginView


class FakeApiClient:
    def __init__(self):
        self.access_token = None
        self.current_user_id = None
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/auth/register":
            return {
                "user_id": "user-1",
                "username": "ana",
                "access_token": "token-1",
            }
        if path == "/auth/login":
            return {
                "user_id": "user-1",
                "username": "ana",
                "email": "ana@pixora.com",
                "access_token": "token-1",
            }
        if path == "/profile":
            return {"usuario": "ana"}
        raise AssertionError(f"Unexpected request: {method} {path}")


def test_registro_exitoso():
    api = FakeApiClient()
    auth = AuthController(api)

    exito, mensaje = auth.register_user(
        "Ana", "López", "ana", "ana@pixora.com", "123456"
    )

    assert exito is True
    assert mensaje == "Usuario registrado con éxito."
    assert api.access_token == "token-1"
    assert auth.current_username == "ana"
    assert len(api.calls) == 1


def test_registro_correo_invalido_no_llama_api():
    api = FakeApiClient()
    auth = AuthController(api)

    exito, mensaje = auth.register_user(
        "Ana", "López", "ana", "ana-sin-arroba", "123456"
    )

    assert exito is False
    assert mensaje == "El correo electrónico no es válido."
    assert api.calls == []


def test_login_usa_el_usuario_devuelto_por_la_autenticacion():
    api = FakeApiClient()
    auth = AuthController(api)

    exito, mensaje = auth.login_user("ana@pixora.com", "123456")

    assert exito is True
    assert mensaje == "Bienvenido, ana!"
    assert auth.current_username == "ana"
    assert api.access_token == "token-1"
    assert api.calls[0][2]["json"] == {
        "identificador": "ana@pixora.com",
        "contraseña": "123456",
    }
    assert len(api.calls) == 1


def test_login_y_registro_muestran_formularios_distintos():
    auth = AuthController(FakeApiClient())
    view = LoginView(auth, lambda: None)

    login_labels = [control.label for control in view.form_container.content.controls
                    if isinstance(control, type(view.login_identifier_input))]
    assert login_labels == ["Usuario o correo", "Contraseña"]

    view._set_mode("register")
    registration_labels = [
        control.label
        for control in view.form_container.content.controls
        if isinstance(control, type(view.email_input))
    ]
    assert registration_labels == [
        "Nombre",
        "Apellido",
        "Usuario",
        "Correo electrónico",
        "Contraseña",
    ]
