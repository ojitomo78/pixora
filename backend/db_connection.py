from contextlib import contextmanager
from threading import Lock
from typing import Any, Iterator

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from backend.settings import ConfigurationError, required_setting

_postgres_pool: ThreadedConnectionPool | None = None
_postgres_pool_lock = Lock()
_mongo_client: MongoClient[Any] | None = None
_mongo_client_lock = Lock()
ALLOWED = {
    "CONTENEDORES_FOTOGRAFÍAS",
    "DETALLES_PUBLICACIONES",
    "COMENTARIOS_COMUNIDAD",
    "GALERÍAS_UBICACIONES",
    "POSES_MODELOS",
}
MONGO_COLLECTION_NAMES = tuple(ALLOWED)


def get_postgres_connection() -> psycopg2.extensions.connection:
    global _postgres_pool
    with _postgres_pool_lock:
        if _postgres_pool is None:
            _postgres_pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=required_setting("POSTGRES_DSN"),
                connect_timeout=5,
            )
        pool = _postgres_pool
    return pool.getconn()


def release_postgres_connection(
    connection: psycopg2.extensions.connection,
) -> None:
    with _postgres_pool_lock:
        pool = _postgres_pool
    if pool is None:
        connection.close()
        return
    pool.putconn(
        connection,
        close=bool(connection.closed),
    )


@contextmanager
def postgres_connection() -> Iterator[psycopg2.extensions.connection]:
    connection = get_postgres_connection()
    try:
        yield connection
        connection.commit()
    except BaseException:
        if not connection.closed:
            try:
                connection.rollback()
            except psycopg2.Error:
                connection.close()
        raise
    finally:
        release_postgres_connection(connection)


def get_mongo_client() -> MongoClient[Any]:
    global _mongo_client
    with _mongo_client_lock:
        if _mongo_client is None:
            client: MongoClient[Any] = MongoClient(
                required_setting("MONGODB_URI"),
                serverSelectionTimeoutMS=5000,
            )
            try:
                client.admin.command("ping")
            except PyMongoError:
                client.close()
                raise
            _mongo_client = client
        return _mongo_client


def get_mongo_database() -> Any:
    database_name = required_setting("MONGODB_DATABASE")
    if database_name != "pixora_db":
        raise ConfigurationError("MONGODB_DATABASE debe ser exactamente 'pixora_db'.")
    return get_mongo_client()[database_name]


def get_mongo_collection(collection_name: str) -> Any:
    if collection_name not in ALLOWED:
        raise ValueError("La colección no está en el esquema MongoDB confirmado.")
    return get_mongo_database()[collection_name]


def close_database_connections() -> None:
    global _postgres_pool
    global _mongo_client
    with _postgres_pool_lock:
        if _postgres_pool is not None:
            _postgres_pool.closeall()
            _postgres_pool = None
    with _mongo_client_lock:
        if _mongo_client is not None:
            _mongo_client.close()
            _mongo_client = None
