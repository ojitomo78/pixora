from typing import Any

from psycopg2.extras import RealDictCursor

from backend.db_connection import postgres_connection


def _fetch_all(query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with postgres_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, parameters)
            return [dict(row) for row in cursor.fetchall()]


def _fetch_one(query: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = _fetch_all(query, parameters)
    return rows[0] if rows else None


def create_user(
    nombre: str,
    apellido: str,
    usuario: str,
    correo: str,
    password_hash: str,
) -> dict[str, Any]:
    result = _fetch_one(
        """
        INSERT INTO usuarios
            (nombre, apellido, usuario, correo, "contraseña", fecha_registro)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        RETURNING id_usuario, nombre, apellido, usuario, correo, fecha_registro
        """,
        (nombre, apellido, usuario, correo, password_hash),
    )
    if result is None:
        raise RuntimeError("PostgreSQL no devolvió el usuario recién registrado.")
    return result


def get_user_by_identifier(identificador: str) -> dict[str, Any] | None:
    return _fetch_one(
        """
        SELECT id_usuario, nombre, apellido, usuario, correo, "contraseña",
               fecha_registro
        FROM usuarios
        WHERE usuario = %s OR correo = %s
        LIMIT 1
        """,
        (identificador, identificador),
    )


def get_user_by_id(id_usuario: int) -> dict[str, Any] | None:
    return _fetch_one(
        """
        SELECT id_usuario, nombre, apellido, usuario, correo, fecha_registro
        FROM usuarios
        WHERE id_usuario = %s
        LIMIT 1
        """,
        (id_usuario,),
    )


def get_usernames(id_usuarios: list[int]) -> dict[int, str]:
    if not id_usuarios:
        return {}
    rows = _fetch_all(
        """
        SELECT id_usuario, usuario
        FROM usuarios
        WHERE id_usuario = ANY(%s)
        """,
        (id_usuarios,),
    )
    return {row["id_usuario"]: row["usuario"] for row in rows}


def create_publication(
    id_usuario: int,
    id_localizacion: int | None,
    titulo: str,
    descripcion: str,
    visibilidad: str,
) -> dict[str, Any]:
    result = _fetch_one(
        """
        INSERT INTO publicaciones
            (id_usuario, id_localizacion, titulo, descripcion,
             fecha_publicacion, visibilidad)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
        RETURNING id_publicacion, id_usuario, id_localizacion, titulo,
                  descripcion, fecha_publicacion, visibilidad
        """,
        (id_usuario, id_localizacion, titulo, descripcion, visibilidad),
    )
    if result is None:
        raise RuntimeError("PostgreSQL no devolvió la publicación recién creada.")
    return result


def list_publications(limit: int = 20) -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT p.id_publicacion, p.id_usuario, u.usuario, p.id_localizacion,
               l.nombre AS localizacion_nombre, p.titulo, p.descripcion,
               p.fecha_publicacion, p.visibilidad
        FROM publicaciones AS p
        JOIN usuarios AS u ON u.id_usuario = p.id_usuario
        LEFT JOIN localizaciones AS l ON l.id_localizacion = p.id_localizacion
        ORDER BY p.fecha_publicacion DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_publication(id_publicacion: int) -> dict[str, Any] | None:
    return _fetch_one(
        """
        SELECT id_publicacion, id_usuario, id_localizacion, titulo,
               descripcion, fecha_publicacion, visibilidad
        FROM publicaciones
        WHERE id_publicacion = %s
        LIMIT 1
        """,
        (id_publicacion,),
    )


def delete_publication(id_publicacion: int, id_usuario: int) -> bool:
    return _fetch_one(
        """
        DELETE FROM publicaciones
        WHERE id_publicacion = %s AND id_usuario = %s
        RETURNING id_publicacion;
        """,
        (id_publicacion, id_usuario),
    ) is not None


def list_locations(ciudad: str | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT id_localizacion, nombre, ciudad, pais, descripcion, coordenadas
        FROM localizaciones
    """
    parameters: tuple[Any, ...] = ()
    if ciudad:
        query += " WHERE LOWER(ciudad) = LOWER(%s)"
        parameters = (ciudad.strip(),)
    query += " ORDER BY id_localizacion DESC"
    return _fetch_all(query, parameters)


def create_location(
    nombre: str,
    ciudad: str,
    pais: str,
    descripcion: str,
    coordenadas: str,
) -> dict[str, Any]:
    result = _fetch_one(
        """
        INSERT INTO localizaciones
            (nombre, ciudad, pais, descripcion, coordenadas)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id_localizacion, nombre, ciudad, pais, descripcion, coordenadas
        """,
        (nombre, ciudad, pais, descripcion, coordenadas),
    )
    if result is None:
        raise RuntimeError("PostgreSQL no devolvió la localización recién creada.")
    return result


def list_session_types() -> list[dict[str, Any]]:
    return _fetch_all(
        """
        SELECT id_tipo_sesion, nombre, descripcion, categoria, recomendaciones
        FROM tipo_sesion_fotografica
        ORDER BY id_tipo_sesion
        """
    )


def get_session_type_by_name(nombre: str) -> dict[str, Any] | None:
    return _fetch_one(
        """
        SELECT id_tipo_sesion, nombre, descripcion, categoria, recomendaciones
        FROM tipo_sesion_fotografica
        WHERE nombre = %s
        LIMIT 1
        """,
        (nombre,),
    )


def get_session_type_by_id(id_tipo_sesion: int) -> dict[str, Any] | None:
    return _fetch_one(
        """
        SELECT id_tipo_sesion, nombre, descripcion, categoria, recomendaciones
        FROM tipo_sesion_fotografica
        WHERE id_tipo_sesion = %s
        LIMIT 1
        """,
        (id_tipo_sesion,),
    )
