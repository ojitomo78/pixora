from contextlib import asynccontextmanager
from io import BytesIO
import logging
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg2 import Error as PostgresError
from psycopg2.errors import UniqueViolation
from pymongo.errors import PyMongoError
from pydantic import BaseModel, Field, field_validator
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.ai import (
    AIProviderError,
    ai_provider_configured,
    fallback_recommendation_cards,
    generate_recommendation_cards,
    generate_text,
    selected_ai_provider,
)
from backend.auth_tokens import (
    get_user_id_from_access_token,
    issue_access_token,
    validate_auth_token_secret,
)
from backend.db_connection import close_database_connections
from backend.mongo_access import (
    add_publication_comment,
    delete_publication_comments,
    delete_publication_details,
    delete_publication_image,
    get_location_gallery,
    get_publication_details,
    get_publication_image,
    list_model_poses,
    list_publication_details,
    list_publication_comments,
    list_publication_images,
    add_location_gallery_photo,
    save_model_pose,
    save_publication_details,
    save_publication_image,
    toggle_publication_like,
)
from backend.passwords import hash_password, verify_password
from backend.postgres_access import (
    create_location,
    create_publication,
    create_user,
    delete_publication,
    get_publication,
    get_session_type_by_id,
    get_session_type_by_name,
    get_user_by_identifier,
    get_user_by_id,
    get_usernames,
    list_locations,
    list_publications,
    list_session_types,
)
from backend.settings import ConfigurationError, optional_setting

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    close_database_connections()


app = FastAPI(title="Pixora API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in optional_setting(
            "FRONTEND_ORIGINS", "http://localhost:8550,http://127.0.0.1:8550"
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

bearer_scheme = HTTPBearer(auto_error=False)


class Registration(BaseModel):
    nombre: str = Field(min_length=1)
    apellido: str = Field(min_length=1)
    usuario: str = Field(min_length=1)
    correo: str = Field(min_length=3)
    contraseña: str = Field(min_length=6)

    @field_validator("nombre", "apellido", "usuario", "correo", mode="before")
    @classmethod
    def strip_identity_fields(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class LoginCredentials(BaseModel):
    identificador: str = Field(min_length=1)
    contraseña: str = Field(min_length=1)

    @field_validator("identificador", mode="before")
    @classmethod
    def strip_identifier(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class CreatePublicationDetails(BaseModel):
    camara: str
    lente: str
    apertura: str
    iso: int
    velocidad_obturacion: str


class CreatePose(BaseModel):
    nombre_pose: str
    descripcion: str
    modelo_3d_url: str


class AddGalleryPhoto(BaseModel):
    url_foto: str = Field(min_length=1)


class CreateLocation(BaseModel):
    nombre: str
    ciudad: str
    pais: str
    descripcion: str
    coordenadas: str

    @field_validator(
        "nombre", "ciudad", "pais", "descripcion", "coordenadas", mode="before"
    )
    @classmethod
    def strip_location_fields(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class CreateComment(BaseModel):
    comentario: str = Field(min_length=1, max_length=2000)

    @field_validator("comentario", mode="before")
    @classmethod
    def strip_comment(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class PoseRequest(BaseModel):
    session_type: str = Field(min_length=2, max_length=120)

    @field_validator("session_type", mode="before")
    @classmethod
    def strip_session_type(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class SpotRequest(BaseModel):
    city: str = Field(min_length=2, max_length=120)
    photo_type: str = Field(min_length=2, max_length=120)

    @field_validator("city", "photo_type", mode="before")
    @classmethod
    def strip_spot_request_fields(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class AIQuestion(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)

    @field_validator("prompt", mode="before")
    @classmethod
    def strip_prompt(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


def _current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Falta el token de acceso.")
    try:
        id_usuario = get_user_id_from_access_token(credentials.credentials)
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if id_usuario is None:
        raise HTTPException(status_code=401, detail="El token no identifica un usuario.")
    try:
        user = get_user_by_id(id_usuario)
    except PostgresError as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar usuarios.") from exc
    if user is None:
        raise HTTPException(status_code=401, detail="El usuario del token ya no existe.")
    return user


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id_usuario": user["id_usuario"],
        "nombre": user["nombre"],
        "apellido": user["apellido"],
        "usuario": user["usuario"],
        "correo": user["correo"],
        "fecha_registro": user["fecha_registro"],
    }


def _parse_publication_id(raw_id: str) -> int:
    try:
        publication_id = int(raw_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="La publicación no existe.") from exc
    if publication_id <= 0:
        raise HTTPException(status_code=404, detail="La publicación no existe.")
    return publication_id


def _fallback_poses(session_type: dict[str, Any]) -> str:
    recommendations = session_type["recomendaciones"]
    if recommendations:
        return (
            f"Recomendaciones registradas para {session_type['nombre']} "
            f"({session_type['categoria']}): {recommendations}"
        )
    description = session_type["descripcion"]
    if description:
        return f"Tipo de sesión {session_type['nombre']}: {description}"
    return f"Se encontró el tipo de sesión {session_type['nombre']}."


def _fallback_locations(spots: list[dict[str, Any]]) -> str:
    if not spots:
        return "No se encontraron localizaciones registradas; se muestran sugerencias de respaldo para Bogotá."
    entries = [
        (
            f"{spot['nombre']} ({spot['ciudad']}, {spot['pais']}): "
            f"{spot['descripcion']} Coordenadas: {spot['coordenadas']}."
        )
        for spot in spots
    ]
    return "Localizaciones registradas: " + " ".join(entries)


def _bogota_spot_fallback() -> list[dict[str, Any]]:
    return [
        {
            "id_localizacion": None,
            "nombre": nombre,
            "ciudad": "Bogotá",
            "pais": "Colombia",
            "descripcion": "Sugerencia de respaldo; no es una localización guardada.",
            "coordenadas": "",
        }
        for nombre in (
            "La Candelaria",
            "Monserrate",
            "Parque Simón Bolívar",
            "Chorro de Quevedo",
        )
    ]


def _bogota_pose_fallback(id_tipo_sesion: int | None = None) -> list[dict[str, Any]]:
    return [
        {
            "id_tipo_sesion": id_tipo_sesion,
            "nombre_pose": nombre,
            "descripcion": descripcion,
            "modelo_3d_url": "",
        }
        for nombre, descripcion in (
            ("Retrato Urbano", "Retrato con el entorno urbano como fondo."),
            ("Plano Medio", "Encuadre desde la cintura para destacar expresión y contexto."),
            ("Picado Creativo", "Toma desde un ángulo elevado para variar la composición."),
        )
    ]


def _validate_image(content: bytes) -> None:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > 80_000_000:
                raise HTTPException(
                    status_code=413,
                    detail="La resolución de la imagen supera el límite admitido.",
                )
            image.verify()
    except Image.DecompressionBombError as exc:
        raise HTTPException(
            status_code=413, detail="La resolución de la imagen es excesiva."
        ) from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=415, detail="El archivo no es una imagen válida.") from exc


def _compress_image(content: bytes) -> bytes:
    try:
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                image = flattened
            else:
                image = image.convert("RGB")
            image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            quality = 84
            while True:
                output = BytesIO()
                image.save(output, format="JPEG", quality=quality, optimize=True)
                compressed = output.getvalue()
                if len(compressed) < 1024 * 1024:
                    return compressed
                if quality > 70:
                    quality -= 5
                else:
                    width, height = image.size
                    resized = (max(1, int(width * 0.8)), max(1, int(height * 0.8)))
                    if resized == image.size:
                        raise HTTPException(
                            status_code=413,
                            detail="No se pudo reducir la imagen por debajo de 1 MB.",
                        )
                    image = image.resize(resized, Image.Resampling.LANCZOS)
                    quality = 84
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=415, detail="El archivo no es una imagen válida."
        ) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    required = (
        "POSTGRES_DSN",
        "PIXORA_AUTH_SECRET",
        "MONGODB_URI",
        "MONGODB_DATABASE",
    )
    configured = {name: bool(optional_setting(name)) for name in required}
    configured["GEMINI_API_KEY"] = bool(optional_setting("GEMINI_API_KEY"))
    configured["AI_PROVIDER"] = ai_provider_configured()
    configured["OLLAMA_BASE_URL"] = bool(
        optional_setting("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    )
    return {
        "status": "ok" if all(configured[name] for name in required) else "not_configured",
        "configuration": configured,
    }


@app.post("/api/v1/auth/register", status_code=201)
def register(payload: Registration) -> dict[str, Any]:
    try:
        validate_auth_token_secret()
        user = create_user(
            payload.nombre,
            payload.apellido,
            payload.usuario,
            payload.correo,
            hash_password(payload.contraseña),
        )
        access_token = issue_access_token(user["id_usuario"])
    except UniqueViolation as exc:
        raise HTTPException(
            status_code=409,
            detail="El nombre de usuario o el correo ya está registrado.",
        ) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PostgresError as exc:
        raise HTTPException(status_code=503, detail="No se pudo registrar el usuario.") from exc
    return {
        "user_id": str(user["id_usuario"]),
        "username": user["usuario"],
        "access_token": access_token,
    }


@app.post("/api/v1/auth/login")
def login(payload: LoginCredentials) -> dict[str, Any]:
    try:
        user = get_user_by_identifier(payload.identificador)
    except PostgresError as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar usuarios.") from exc
    if user is None or not verify_password(payload.contraseña, user["contraseña"]):
        raise HTTPException(status_code=401, detail="Usuario/correo o contraseña incorrectos.")
    try:
        access_token = issue_access_token(user["id_usuario"])
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "user_id": str(user["id_usuario"]),
        "username": user["usuario"],
        "access_token": access_token,
    }


@app.get("/api/v1/profile")
def get_profile(
    user: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    return _public_user(user)


@app.get("/api/v1/session-types")
def get_session_types(
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> list[dict[str, Any]]:
    try:
        return list_session_types()
    except PostgresError as exc:
        raise HTTPException(
            status_code=503, detail="No se pudieron consultar los tipos de sesión."
        ) from exc


@app.get("/api/v1/posts")
def get_feed(
    user: Annotated[dict[str, Any], Depends(_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[dict[str, Any]]:
    try:
        publications = list_publications(limit)
        images = list_publication_images(
            [item["id_publicacion"] for item in publications]
        )
        details = list_publication_details(
            [item["id_publicacion"] for item in publications]
        )
    except (PostgresError, PyMongoError, ConfigurationError, LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="No se pudo cargar el feed de publicaciones."
        ) from exc
    return [
        {
            "id": str(item["id_publicacion"]),
            "author_id": str(item["id_usuario"]),
            "author": item["usuario"],
            "caption": item["titulo"],
            "description": item["descripcion"],
            "location": item["localizacion_nombre"],
            "pose_utilizada": details.get(item["id_publicacion"], {}).get(
                "pose_utilizada"
            ),
            "likes_count": details.get(item["id_publicacion"], {}).get(
                "likes_count", 0
            ),
            "liked_by_me": user["id_usuario"]
            in details.get(item["id_publicacion"], {}).get("likes_by", []),
            "visibilidad": item["visibilidad"],
            "media_id": str(item["id_publicacion"]),
            "media_url": f"/api/v1/media/{item['id_publicacion']}",
            "created_at": item["fecha_publicacion"].isoformat(),
        }
        for item in publications
        if item["id_publicacion"] in images
    ]


@app.post("/api/v1/posts/{post_id}/like")
def toggle_post_like(
    post_id: str,
    user: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    publication_id = _parse_publication_id(post_id)
    try:
        if get_publication(publication_id) is None:
            raise HTTPException(status_code=404, detail="La publicación no existe.")
        return toggle_publication_like(publication_id, user["id_usuario"])
    except HTTPException:
        raise
    except (PostgresError, PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(
            status_code=503, detail="No se pudo guardar la reacción."
        ) from exc


@app.delete("/api/v1/posts/{post_id}")
def remove_post(
    post_id: str,
    user: Annotated[dict[str, Any], Depends(_current_user)],
) -> JSONResponse:
    publication_id = _parse_publication_id(post_id)
    current_user_id = user["id_usuario"]
    print(
        f"Intentando eliminar publicación {publication_id} "
        f"de usuario {current_user_id}"
    )
    try:
        publication = get_publication(publication_id)
        if publication is None:
            raise HTTPException(status_code=404, detail="La publicación no existe.")
        if publication["id_usuario"] != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="Solo puedes eliminar tus propias publicaciones.",
            )
    except HTTPException:
        raise
    except PostgresError as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo comprobar la propiedad de la publicación en PostgreSQL.",
        ) from exc

    try:
        deleted = delete_publication(publication_id, current_user_id)
    except PostgresError as exc:
        logger.exception(
            "No se pudo eliminar la publicación %s de PostgreSQL.", publication_id
        )
        raise HTTPException(
            status_code=503,
            detail="No se pudo eliminar la publicación de PostgreSQL.",
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="La publicación ya no existe o ya no pertenece a este usuario.",
        )

    try:
        delete_publication_image(publication_id)
        delete_publication_details(publication_id)
        delete_publication_comments(publication_id)
    except (PyMongoError, ConfigurationError, LookupError) as exc:
        logger.exception(
            "No se pudieron limpiar los datos MongoDB de la publicación %s.",
            publication_id,
        )
        raise HTTPException(
            status_code=503,
            detail="La publicación se eliminó en PostgreSQL, pero no se pudieron limpiar sus datos MongoDB.",
        ) from exc
    return JSONResponse(status_code=200, content={"message": "Eliminado"})


@app.post("/api/v1/posts", status_code=201)
def create_post(
    user: Annotated[dict[str, Any], Depends(_current_user)],
    titulo: Annotated[str, Form(min_length=1, max_length=2000)],
    image: Annotated[UploadFile, File()],
    id_localizacion: Annotated[int | None, Form(gt=0)] = None,
    localizacion_texto: Annotated[str, Form(max_length=200)] = "",
    pose_utilizada: Annotated[str, Form(max_length=200)] = "",
    descripcion: str = Form(default="", max_length=2000),
) -> dict[str, Any]:
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Usa una imagen JPEG, PNG o WebP.")
    content = image.file.read(30 * 1024 * 1024 + 1)
    if not content or len(content) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="La imagen original debe pesar hasta 30 MB.")
    _validate_image(content)
    content = _compress_image(content)

    description = descripcion.strip()
    location_text = localizacion_texto.strip()
    if location_text:
        try:
            matched_location = next(
                (
                    location
                    for location in list_locations()
                    if location["nombre"].strip().casefold()
                    == location_text.casefold()
                ),
                None,
            )
        except Exception as exc:
            logger.exception("No se pudo validar la localización de la publicación.")
            raise HTTPException(
                status_code=500,
                detail="No se pudo validar la localización indicada.",
            ) from exc
        if matched_location is not None:
            id_localizacion = matched_location["id_localizacion"]
        else:
            id_localizacion = None
            location_note = f"Localización indicada: {location_text}"
            description = (
                f"{description}\n\n{location_note}".strip()
                if description
                else location_note
            )
    if len(description) > 2000:
        raise HTTPException(
            status_code=422,
            detail="La descripción y la localización juntas no pueden superar 2000 caracteres.",
        )

    try:
        publication = create_publication(
            user["id_usuario"],
            id_localizacion,
            titulo.strip(),
            description,
            "publica",
        )
    except Exception as exc:
        logger.exception("No se pudo crear la publicación en PostgreSQL.")
        raise HTTPException(
            status_code=500,
            detail="No se pudo guardar la publicación.",
        ) from exc

    publication_id = publication["id_publicacion"]
    try:
        save_publication_image(publication_id, content, "image/jpeg")
        if pose_utilizada.strip():
            save_publication_details(
                publication_id,
                "",
                "",
                "",
                0,
                "",
                pose_utilizada.strip(),
            )
    except Exception as exc:
        logger.exception(
            "Falló el guardado de la imagen o sus detalles para publicación %s.",
            publication_id,
        )
        cleanup_error: Exception | None = None
        try:
            delete_publication_image(publication_id)
        except Exception as image_cleanup_error:
            logger.exception(
                "No se pudo limpiar la imagen de la publicación %s.",
                publication_id,
            )
            cleanup_error = image_cleanup_error
        if pose_utilizada.strip():
            try:
                delete_publication_details(publication_id)
            except Exception as details_cleanup_error:
                logger.exception(
                    "No se pudieron limpiar los detalles de publicación %s.",
                    publication_id,
                )
                cleanup_error = details_cleanup_error
        try:
            delete_publication(publication_id, user["id_usuario"])
        except Exception as rollback_error:
            logger.exception(
                "No se pudo revertir la publicación %s en PostgreSQL.",
                publication_id,
            )
            raise HTTPException(
                status_code=500,
                detail="Falló el guardado multimedia y no se pudo revertir la publicación.",
            ) from rollback_error
        if cleanup_error is not None:
            raise HTTPException(
                status_code=500,
                detail="Falló el guardado multimedia y no se pudieron limpiar los datos.",
            ) from cleanup_error
        raise HTTPException(
            status_code=500, detail="No se pudo guardar la imagen de la publicación."
        ) from exc
    return {
        "id": str(publication_id),
        "author_id": str(user["id_usuario"]),
        "author": user["usuario"],
        "caption": publication["titulo"],
        "media_id": str(publication_id),
        "media_url": f"/api/v1/media/{publication_id}",
        "description": description,
        "location": location_text or None,
        "pose_utilizada": pose_utilizada.strip() or None,
        "created_at": publication["fecha_publicacion"].isoformat(),
    }


@app.get("/api/v1/media/{media_id}")
def get_media(
    media_id: str,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> Response:
    try:
        publication_id = int(media_id)
        if publication_id <= 0:
            raise ValueError
        image = get_publication_image(publication_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="La imagen no existe.") from exc
    except (PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudo leer la imagen.") from exc
    if image is None:
        raise HTTPException(status_code=404, detail="La imagen no existe.")
    content, content_type = image
    return Response(content=content, media_type=content_type)


@app.get("/api/v1/posts/{post_id}/comments")
def get_comments(
    post_id: str,
    _: Annotated[dict[str, Any], Depends(_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    publication_id = _parse_publication_id(post_id)
    try:
        if get_publication(publication_id) is None:
            raise HTTPException(status_code=404, detail="La publicación no existe.")
        comments = list_publication_comments(publication_id, limit)
    except HTTPException:
        raise
    except (PostgresError, PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudieron leer los comentarios.") from exc
    try:
        usernames = get_usernames([item["id_usuario"] for item in comments])
    except PostgresError as exc:
        raise HTTPException(status_code=503, detail="No se pudieron leer los autores.") from exc
    return [
        {
            "id": item["id"],
            "author_id": str(item["id_usuario"]),
            "author": usernames.get(item["id_usuario"], str(item["id_usuario"])),
            "text": item["comentario"],
            "created_at": item["fecha"].isoformat(),
        }
        for item in comments
    ]


@app.get("/api/v1/posts/{post_id}/details")
def get_post_details(
    post_id: str,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    publication_id = _parse_publication_id(post_id)
    try:
        if get_publication(publication_id) is None:
            raise HTTPException(status_code=404, detail="La publicación no existe.")
        details = get_publication_details(publication_id)
    except HTTPException:
        raise
    except (PostgresError, PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudieron leer los detalles.") from exc
    if details is None:
        raise HTTPException(status_code=404, detail="La publicación no tiene detalles.")
    return details


@app.put("/api/v1/posts/{post_id}/details")
def save_post_details(
    post_id: str,
    payload: CreatePublicationDetails,
    user: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, str]:
    publication_id = _parse_publication_id(post_id)
    try:
        publication = get_publication(publication_id)
        if publication is None or publication["id_usuario"] != user["id_usuario"]:
            raise HTTPException(status_code=404, detail="La publicación no existe.")
        save_publication_details(
            publication_id,
            payload.camara,
            payload.lente,
            payload.apertura,
            payload.iso,
            payload.velocidad_obturacion,
        )
    except HTTPException:
        raise
    except (PostgresError, PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudieron guardar los detalles.") from exc
    return {"status": "saved"}


@app.post("/api/v1/posts/{post_id}/comments", status_code=201)
def create_comment(
    post_id: str,
    payload: CreateComment,
    user: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    publication_id = _parse_publication_id(post_id)
    try:
        if get_publication(publication_id) is None:
            raise HTTPException(status_code=404, detail="La publicación no existe.")
        comment = add_publication_comment(
            publication_id, user["id_usuario"], payload.comentario
        )
    except HTTPException:
        raise
    except (PostgresError, PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudo guardar el comentario.") from exc
    return {
        "id": comment["id"],
        "author_id": str(user["id_usuario"]),
        "author": user["usuario"],
        "text": comment["comentario"],
        "created_at": comment["fecha"].isoformat(),
    }


@app.get("/api/v1/locations/{location_id}/gallery")
def get_location_photos(
    location_id: int,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    try:
        gallery = get_location_gallery(location_id)
    except (PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar la galería.") from exc
    return gallery or {"id_localizacion": location_id, "urls_fotos": []}


@app.post("/api/v1/locations/{location_id}/gallery", status_code=201)
def add_location_photo(
    location_id: int,
    payload: AddGalleryPhoto,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    try:
        add_location_gallery_photo(location_id, payload.url_foto)
        gallery = get_location_gallery(location_id)
    except (PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudo guardar la foto.") from exc
    return gallery or {"id_localizacion": location_id, "urls_fotos": []}


@app.get("/api/v1/session-types/{session_type_id}/poses")
def get_session_poses(
    session_type_id: int,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> list[dict[str, Any]]:
    try:
        return list_model_poses(session_type_id)
    except (PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudieron consultar las poses.") from exc


@app.post("/api/v1/session-types/{session_type_id}/poses", status_code=201)
def create_session_pose(
    session_type_id: int,
    payload: CreatePose,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    try:
        session_type = get_session_type_by_id(session_type_id)
        if session_type is None:
            raise HTTPException(status_code=404, detail="El tipo de sesión no existe.")
        pose = save_model_pose(
            session_type_id,
            payload.nombre_pose,
            payload.descripcion,
            payload.modelo_3d_url,
        )
    except HTTPException:
        raise
    except (PostgresError, PyMongoError, ConfigurationError, LookupError) as exc:
        raise HTTPException(status_code=503, detail="No se pudo guardar la pose.") from exc
    return pose


@app.get("/api/v1/spots", dependencies=[Depends(_current_user)])
def get_spots(
    city: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    try:
        return list_locations(city)
    except PostgresError as exc:
        raise HTTPException(
            status_code=503, detail="No se pudieron consultar las localizaciones."
        ) from exc


@app.post("/api/v1/spots", status_code=201)
def create_spot(
    payload: CreateLocation,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    try:
        return create_location(
            payload.nombre,
            payload.ciudad,
            payload.pais,
            payload.descripcion,
            payload.coordenadas,
        )
    except PostgresError as exc:
        raise HTTPException(
            status_code=503, detail="No se pudo guardar la localización."
        ) from exc


@app.post("/api/v1/ai/poses")
def recommend_poses(
    payload: PoseRequest,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    try:
        session_type = get_session_type_by_name(payload.session_type)
    except (PostgresError, ConfigurationError):
        session_type = None

    fallback_poses = _bogota_pose_fallback(
        session_type["id_tipo_sesion"] if session_type else None
    )
    if session_type is None:
        return {
            "recommendation": "Sugerencias de respaldo: " + ", ".join(
                pose["nombre_pose"] for pose in fallback_poses
            ),
            "poses": fallback_poses,
            "source": "fallback",
        }
    try:
        saved_poses = list_model_poses(session_type["id_tipo_sesion"])
    except (PyMongoError, ConfigurationError, LookupError, ValueError):
        saved_poses = []
    poses = saved_poses or fallback_poses
    fallback = _fallback_poses(session_type)
    if not ai_provider_configured():
        return {
            "recommendation": fallback,
            "poses": poses,
            "source": "postgres",
        }
    try:
        recommendation = generate_text(
            "Responde en español usando únicamente estos datos registrados; no inventes "
            "poses específicas que no se puedan deducir de ellos. Sugiere ideas para la "
            f"sesión {session_type['nombre']!r}, categoría {session_type['categoria']!r}. "
            f"Descripción: {session_type['descripcion']}. "
            f"Recomendaciones registradas: {session_type['recomendaciones']}."
        )
    except AIProviderError:
        return {
            "recommendation": fallback,
            "poses": poses,
            "source": "postgres",
        }
    return {
        "recommendation": recommendation,
        "poses": poses,
        "source": selected_ai_provider(),
    }


@app.post("/api/v1/ai/spots", dependencies=[Depends(_current_user)])
def recommend_spots(
    payload: SpotRequest,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    try:
        spots = list_locations(payload.city)
    except (PostgresError, ConfigurationError):
        spots = []
    if not spots and payload.city.strip().casefold() != "bogotá":
        try:
            spots = list_locations("Bogotá")
        except (PostgresError, ConfigurationError):
            spots = []
    if not spots:
        fallback_spots = _bogota_spot_fallback()
        return {
            "recommendation": _fallback_locations([]),
            "spots": fallback_spots,
            "source": "fallback",
        }
    fallback = _fallback_locations(spots)
    if not ai_provider_configured():
        return {"recommendation": fallback, "spots": spots, "source": "postgres"}
    public_spots = [
        {
            "nombre": spot["nombre"],
            "ciudad": spot["ciudad"],
            "pais": spot["pais"],
            "descripcion": spot["descripcion"],
            "coordenadas": spot["coordenadas"],
        }
        for spot in spots
    ]
    try:
        text = generate_text(
            f"En español, recomienda lugares solo entre estos registros para fotografía "
            f"{payload.photo_type!r} en {payload.city!r}. No inventes sitios, direcciones, "
            "horarios ni condiciones actuales; si los datos no bastan, dilo claramente. "
            f"Registros: {public_spots}"
        )
    except AIProviderError:
        return {
            "recommendation": fallback,
            "spots": _bogota_spot_fallback(),
            "source": "fallback",
        }
    return {
        "recommendation": text,
        "spots": spots,
        "source": selected_ai_provider(),
    }


@app.post("/api/v1/ai/ask")
def ask_pixora_ai(
    payload: AIQuestion,
    _: Annotated[dict[str, Any], Depends(_current_user)],
) -> dict[str, Any]:
    try:
        cards = generate_recommendation_cards(payload.prompt)
    except Exception:
        logger.exception("Falló el proveedor de IA al generar recomendaciones.")
        return {
            "cards": fallback_recommendation_cards(
                "lugares y poses para fotos en Bogotá"
            ),
            "source": "fallback",
            "message": "Gemini no está disponible; se muestran recomendaciones de respaldo.",
        }
    return {"cards": cards, "source": getattr(cards, "source", "gemini")}
