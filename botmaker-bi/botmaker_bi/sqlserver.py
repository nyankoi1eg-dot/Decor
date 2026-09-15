"""Carga incremental hacia SQL Server mediante MERGE (upsert idempotente).

Se persiste el grano de sesion. Los agregados diarios salen de una vista, no de
una segunda tabla, para que no puedan quedar desincronizados.
"""
from __future__ import annotations

import logging
from typing import Iterable, Sequence

from .funnel import FilaSesion

log = logging.getLogger(__name__)

COLUMNAS: Sequence[str] = (
    "session_id",
    "chat_id",
    "contact_id",
    "channel_id",
    "plataforma",
    "fecha_hora_utc",
    "fecha_local",
    "origen",
    "cola",
    "tipificacion",
    "tiendas",
    "en_cola",
    "atendido",
    "derivado_tienda",
    "tag_contactado",
    "cerrado",
)

MERGE_SQL = f"""
MERGE dbo.botmaker_sesion AS destino
USING (SELECT {', '.join(f'? AS {c}' for c in COLUMNAS)}) AS origen
    ON destino.session_id = origen.session_id
WHEN MATCHED THEN UPDATE SET
    {', '.join(f'destino.{c} = origen.{c}' for c in COLUMNAS if c != 'session_id')},
    destino.actualizado_en = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT ({', '.join(COLUMNAS)}, actualizado_en)
    VALUES ({', '.join(f'origen.{c}' for c in COLUMNAS)}, SYSUTCDATETIME());
"""


def _valores(fila: FilaSesion) -> tuple:
    d = fila.as_dict()
    return tuple(
        int(d[c]) if isinstance(d[c], bool) else d[c] for c in COLUMNAS
    )


def cargar(conn_str: str, filas: Iterable[FilaSesion], batch: int = 500) -> int:
    """Hace upsert de las filas. Devuelve cuantas se procesaron.

    Es idempotente: reprocesar una ventana ya cargada actualiza en lugar de
    duplicar, que es justo lo que se necesita porque las sesiones abiertas
    cambian de estado despues de la primera lectura.
    """
    import pyodbc  # import diferido: el endpoint REST no necesita el driver ODBC

    filas = list(filas)
    if not filas:
        log.info("Sin filas que cargar")
        return 0

    with pyodbc.connect(conn_str, autocommit=False) as conn:
        cur = conn.cursor()
        cur.fast_executemany = False  # MERGE con executemany no admite fast_executemany
        total = 0
        for i in range(0, len(filas), batch):
            lote = [_valores(f) for f in filas[i : i + batch]]
            cur.executemany(MERGE_SQL, lote)
            total += len(lote)
            log.info("Cargadas %s/%s filas", total, len(filas))
        conn.commit()
    return total
