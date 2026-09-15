"""Carga del archivo ``.env``.

``.env.example`` prometia que las credenciales se leian de un ``.env``, pero
nada lo leia: sin esto, ``BOTMAKER_ACCESS_TOKEN`` y ``MSSQL_CONN`` solo
funcionaban exportadas a mano en la shell.

Se invoca desde ``botmaker_bi/__init__.py`` para que corra ANTES que cualquier
submodulo, porque ``api.py`` resuelve ``BI_TIMEZONE_OFFSET`` en tiempo de
import y para entonces las variables ya tienen que estar puestas.
"""
from __future__ import annotations

import os
import pathlib

#: Las variables ya presentes en el entorno ganan sobre el archivo: en
#: produccion manda lo que inyecta el orquestador, no un .env olvidado.
SOBRESCRIBIR = False


def _buscar_env(inicio: pathlib.Path) -> pathlib.Path | None:
    """Busca un ``.env`` desde el paquete hacia arriba (y en el cwd)."""
    candidatos = [*inicio.parents, pathlib.Path.cwd()]
    for carpeta in candidatos:
        ruta = carpeta / ".env"
        if ruta.is_file():
            return ruta
    return None


def cargar_env(ruta: str | os.PathLike[str] | None = None) -> bool:
    """Carga el ``.env`` si python-dotenv esta instalado.

    Devuelve ``True`` si se cargo un archivo. No revienta si falta la
    dependencia: el paquete sigue andando con variables de entorno reales, que
    es como corre en servidor.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False

    destino = pathlib.Path(ruta) if ruta else _buscar_env(pathlib.Path(__file__).resolve())
    if destino is None or not destino.is_file():
        return False
    load_dotenv(destino, override=SOBRESCRIBIR)
    return True
