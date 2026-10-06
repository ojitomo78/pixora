from dataclasses import dataclass


@dataclass(frozen=True)
class PhotoSpot:
    id_localizacion: int | None
    nombre: str
    ciudad: str
    pais: str
    descripcion: str
    coordenadas: str


@dataclass(frozen=True)
class PhotoSessionType:
    id_tipo_sesion: int
    nombre: str
    descripcion: str
    categoria: str
    recomendaciones: str
