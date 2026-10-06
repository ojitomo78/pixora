import base64
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING
from pymongo import ReturnDocument

from backend.db_connection import get_mongo_collection

_IMAGE_COLLECTION = "CONTENEDORES_FOTOGRAFÍAS"
_DETAILS_COLLECTION = "DETALLES_PUBLICACIONES"
_COMMENTS_COLLECTION = "COMENTARIOS_COMUNIDAD"
_LOCATION_GALLERY_COLLECTION = "GALERÍAS_UBICACIONES"
_POSES_COLLECTION = "POSES_MODELOS"
_MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


def save_publication_image(
    id_publicacion: int, content: bytes, formato: str
) -> dict[str, Any]:
    if len(content) > _MAX_DOCUMENT_BYTES:
        raise ValueError("La imagen excede el máximo de 10 MB para MongoDB.")
    encoded_image = base64.b64encode(content).decode("ascii")
    document = {
        "id_publicacion": id_publicacion,
        "url_imagen": f"data:{formato};base64,{encoded_image}",
        "formato": formato,
        "tamano_bytes": len(content),
    }
    get_mongo_collection(_IMAGE_COLLECTION).replace_one(
        {"id_publicacion": id_publicacion}, document, upsert=True
    )
    return document


def get_publication_image(id_publicacion: int) -> tuple[bytes, str] | None:
    document = get_mongo_collection(_IMAGE_COLLECTION).find_one(
        {"id_publicacion": id_publicacion},
        {"_id": 0, "id_publicacion": 1, "url_imagen": 1, "formato": 1,
         "tamano_bytes": 1},
    )
    if document is None:
        return None
    prefix = f"data:{document['formato']};base64,"
    image_url = document["url_imagen"]
    if not image_url.startswith(prefix):
        raise ValueError("El documento de imagen no contiene una URL de datos válida.")
    content = base64.b64decode(image_url[len(prefix):], validate=True)
    if len(content) != document["tamano_bytes"]:
        raise ValueError("El tamaño de la imagen no coincide con el documento MongoDB.")
    return content, document["formato"]


def delete_publication_image(id_publicacion: int) -> None:
    get_mongo_collection(_IMAGE_COLLECTION).delete_one(
        {"id_publicacion": id_publicacion}
    )


def list_publication_images(
    id_publicaciones: list[int],
) -> dict[int, tuple[bytes, str]]:
    if not id_publicaciones:
        return {}
    documents = get_mongo_collection(_IMAGE_COLLECTION).find(
        {"id_publicacion": {"$in": id_publicaciones}},
        {"_id": 0, "id_publicacion": 1, "url_imagen": 1, "formato": 1,
         "tamano_bytes": 1},
    )
    images = {}
    for document in documents:
        prefix = f"data:{document['formato']};base64,"
        image_url = document["url_imagen"]
        if not image_url.startswith(prefix):
            raise ValueError("El documento de imagen no contiene una URL de datos válida.")
        content = base64.b64decode(image_url[len(prefix):], validate=True)
        if len(content) != document["tamano_bytes"]:
            raise ValueError("El tamaño de la imagen no coincide con el documento MongoDB.")
        images[document["id_publicacion"]] = (content, document["formato"])
    return images


def save_publication_details(
    id_publicacion: int,
    camara: str,
    lente: str,
    apertura: str,
    iso: int,
    velocidad_obturacion: str,
    pose_utilizada: str | None = None,
) -> None:
    fields = {
        "camara": camara,
        "lente": lente,
        "apertura": apertura,
        "iso": iso,
        "velocidad_obturacion": velocidad_obturacion,
    }
    if pose_utilizada is not None:
        fields["pose_utilizada"] = pose_utilizada
    get_mongo_collection(_DETAILS_COLLECTION).update_one(
        {"id_publicacion": id_publicacion},
        {
            "$set": fields,
            "$setOnInsert": {"id_publicacion": id_publicacion},
        },
        upsert=True,
    )


def get_publication_details(id_publicacion: int) -> dict[str, Any] | None:
    return get_mongo_collection(_DETAILS_COLLECTION).find_one(
        {"id_publicacion": id_publicacion},
        {"_id": 0, "id_publicacion": 1, "camara": 1, "lente": 1,
         "apertura": 1, "iso": 1, "velocidad_obturacion": 1,
         "pose_utilizada": 1},
    )


def list_publication_details(
    id_publicaciones: list[int],
) -> dict[int, dict[str, Any]]:
    if not id_publicaciones:
        return {}
    documents = get_mongo_collection(_DETAILS_COLLECTION).find(
        {"id_publicacion": {"$in": id_publicaciones}},
        {
            "_id": 0,
            "id_publicacion": 1,
            "pose_utilizada": 1,
            "likes_count": 1,
            "likes_by": 1,
        },
    )
    return {
        document["id_publicacion"]: document
        for document in documents
    }


def toggle_publication_like(
    id_publicacion: int, id_usuario: int
) -> dict[str, Any]:
    document = get_mongo_collection(_DETAILS_COLLECTION).find_one_and_update(
        {"id_publicacion": id_publicacion},
        [
            {
                "$set": {
                    "likes_by": {
                        "$let": {
                            "vars": {
                                "current": {"$ifNull": ["$likes_by", []]}
                            },
                            "in": {
                                "$cond": [
                                    {"$in": [id_usuario, "$$current"]},
                                    {
                                        "$filter": {
                                            "input": "$$current",
                                            "as": "liker",
                                            "cond": {"$ne": ["$$liker", id_usuario]},
                                        }
                                    },
                                    {"$concatArrays": ["$$current", [id_usuario]]},
                                ]
                            },
                        }
                    }
                }
            },
            {
                "$set": {
                    "id_publicacion": {
                        "$ifNull": ["$id_publicacion", id_publicacion]
                    },
                    "likes_count": {"$size": "$likes_by"},
                }
            },
        ],
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if document is None:
        raise RuntimeError("MongoDB no devolvió la reacción actualizada.")
    likes_by = document.get("likes_by", [])
    return {
        "liked": id_usuario in likes_by,
        "likes_count": document.get("likes_count", len(likes_by)),
    }


def delete_publication_details(id_publicacion: int) -> None:
    get_mongo_collection(_DETAILS_COLLECTION).delete_one(
        {"id_publicacion": id_publicacion}
    )


def add_publication_comment(
    id_publicacion: int, id_usuario: int, comentario: str
) -> dict[str, Any]:
    document = {
        "id_publicacion": id_publicacion,
        "id_usuario": id_usuario,
        "comentario": comentario,
        "fecha": datetime.now(timezone.utc),
    }
    result = get_mongo_collection(_COMMENTS_COLLECTION).insert_one(document)
    return {**document, "id": str(result.inserted_id)}


def list_publication_comments(
    id_publicacion: int, limit: int = 50
) -> list[dict[str, Any]]:
    documents = get_mongo_collection(_COMMENTS_COLLECTION).find(
        {"id_publicacion": id_publicacion},
        {"_id": 1, "id_publicacion": 1, "id_usuario": 1,
         "comentario": 1, "fecha": 1},
    ).sort("fecha", ASCENDING).limit(limit)
    return [
        {
            "id": str(document["_id"]),
            "id_publicacion": document["id_publicacion"],
            "id_usuario": document["id_usuario"],
            "comentario": document["comentario"],
            "fecha": document["fecha"],
        }
        for document in documents
    ]


def delete_publication_comments(id_publicacion: int) -> None:
    get_mongo_collection(_COMMENTS_COLLECTION).delete_many(
        {"id_publicacion": id_publicacion}
    )


def add_location_gallery_photo(id_localizacion: int, url_foto: str) -> None:
    get_mongo_collection(_LOCATION_GALLERY_COLLECTION).update_one(
        {"id_localizacion": id_localizacion},
        {
            "$setOnInsert": {"id_localizacion": id_localizacion},
            "$addToSet": {"urls_fotos": url_foto},
        },
        upsert=True,
    )


def remove_location_gallery_photo(id_localizacion: int, url_foto: str) -> None:
    get_mongo_collection(_LOCATION_GALLERY_COLLECTION).update_one(
        {"id_localizacion": id_localizacion},
        {"$pull": {"urls_fotos": url_foto}},
    )


def get_location_gallery(id_localizacion: int) -> dict[str, Any] | None:
    return get_mongo_collection(_LOCATION_GALLERY_COLLECTION).find_one(
        {"id_localizacion": id_localizacion},
        {"_id": 0, "id_localizacion": 1, "urls_fotos": 1},
    )


def save_model_pose(
    id_tipo_sesion: int,
    nombre_pose: str,
    descripcion: str,
    modelo_3d_url: str,
) -> dict[str, Any]:
    document = {
        "id_tipo_sesion": id_tipo_sesion,
        "nombre_pose": nombre_pose,
        "descripcion": descripcion,
        "modelo_3d_url": modelo_3d_url,
    }
    result = get_mongo_collection(_POSES_COLLECTION).insert_one(document)
    return {**document, "id": str(result.inserted_id)}


def list_model_poses(id_tipo_sesion: int) -> list[dict[str, Any]]:
    documents = get_mongo_collection(_POSES_COLLECTION).find(
        {"id_tipo_sesion": id_tipo_sesion},
        {"_id": 1, "id_tipo_sesion": 1, "nombre_pose": 1,
         "descripcion": 1, "modelo_3d_url": 1},
    )
    return [
        {
            "id": str(document["_id"]),
            "id_tipo_sesion": document["id_tipo_sesion"],
            "nombre_pose": document["nombre_pose"],
            "descripcion": document["descripcion"],
            "modelo_3d_url": document["modelo_3d_url"],
        }
        for document in documents
    ]


def delete_model_pose(pose_document_id: str) -> bool:
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        object_id = ObjectId(pose_document_id)
    except InvalidId:
        return False
    result = get_mongo_collection(_POSES_COLLECTION).delete_one({"_id": object_id})
    return result.deleted_count == 1
