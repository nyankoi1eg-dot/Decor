"""Transforma sesiones crudas de Botmaker en filas de embudo listas para BI.

Las etapas se definen ANIDADAS: cada una exige haber pasado la anterior. Es lo
que hace que los porcentajes de conversion se puedan leer como un embudo y no
den por encima de 100%.

    1. ingreso  -> existe la sesion
    2. en_cola  -> la conversacion salio del bot hacia atencion humana
    3. atendido -> un asesor efectivamente la tomo
    4. derivado -> quedo derivada a una tienda
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Iterable

# --- Mapeo especifico de Decor Center -------------------------------------
# Tipificaciones que representan una derivacion a tienda.
TIPIFICACIONES_DERIVACION = {"Lead_Calificado", "CORPORATIVO-LEAD-DERIVADO"}
# Tipificaciones que el negocio considera "consulta atendida".
TIPIFICACIONES_ATENDIDO = {"Consulta_atendida", "CONSULTA_ATENDIDA_SAC"}
# Tags que marcan derivacion a tienda. Las tiendas usan el prefijo TDA*.
TAGS_DERIVACION = {"DERIVADOS"}
PREFIJO_TAG_TIENDA = "TDA"
# Tag que el equipo usa como "ya se contacto al cliente".
TAG_CONTACTADO = "CONTACTADO"

EVENTO_COLA = "queue-set"
EVENTO_ASIGNACION = "assigned-to-agent"
EVENTO_CIERRE = "conversation-close"


@dataclass(frozen=True)
class MapeoEtapas:
    """Permite ajustar el mapeo sin tocar el codigo (ver ``/config`` en la API)."""

    tipificaciones_derivacion: frozenset[str] = frozenset(TIPIFICACIONES_DERIVACION)
    tipificaciones_atendido: frozenset[str] = frozenset(TIPIFICACIONES_ATENDIDO)
    tags_derivacion: frozenset[str] = frozenset(TAGS_DERIVACION)
    prefijo_tag_tienda: str = PREFIJO_TAG_TIENDA
    tag_contactado: str = TAG_CONTACTADO


@dataclass
class FilaSesion:
    """Grano base: una sesion. Es lo que se persiste en SQL Server."""

    session_id: str
    chat_id: str
    contact_id: str
    channel_id: str
    plataforma: str
    fecha_hora_utc: str
    fecha_local: str
    origen: str
    cola: str | None
    tipificacion: str | None
    tiendas: list[str] = field(default_factory=list)
    ingreso: bool = True
    en_cola: bool = False
    atendido: bool = False
    derivado_tienda: bool = False
    tag_contactado: bool = False
    cerrado: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["tiendas"] = ",".join(self.tiendas)
        return d


def _fecha_local(creation_time: str, offset_horas: int) -> tuple[str, str]:
    """Devuelve (timestamp UTC normalizado, fecha local YYYY-MM-DD).

    Botmaker entrega ``creationTime`` en UTC. Agrupar por dia sin convertir a
    hora local desplaza a otro dia todo lo ocurrido despues de las 19:00 en Lima.
    """
    momento = dt.datetime.strptime(creation_time, "%Y-%m-%dT%H:%M:%SZ")
    local = momento + dt.timedelta(hours=offset_horas)
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ"), local.date().isoformat()


def sesion_a_fila(
    sesion: dict[str, Any], offset_horas: int = -5, mapeo: MapeoEtapas | None = None
) -> FilaSesion:
    mapeo = mapeo or MapeoEtapas()
    chat = sesion.get("chat") or {}
    ref = chat.get("chat") or {}
    eventos = {e.get("name") for e in (sesion.get("events") or [])}
    tags = set(chat.get("tags") or [])
    variables = chat.get("variables") or {}
    tipificacion = variables.get("typification")
    tiendas = sorted(t for t in tags if t.startswith(mapeo.prefijo_tag_tienda))
    utc, local = _fecha_local(sesion["creationTime"], offset_horas)

    channel_id = ref.get("channelId") or ""
    partes = channel_id.split("-")
    plataforma = partes[1] if len(partes) > 1 else channel_id

    # Etapas anidadas.
    en_cola = EVENTO_COLA in eventos or EVENTO_ASIGNACION in eventos
    atendido = en_cola and EVENTO_ASIGNACION in eventos
    derivado = atendido and bool(
        tipificacion in mapeo.tipificaciones_derivacion
        or (tags & mapeo.tags_derivacion)
        or tiendas
    )

    return FilaSesion(
        session_id=sesion["id"],
        chat_id=ref.get("chatId") or "",
        contact_id=ref.get("contactId") or "",
        channel_id=channel_id,
        plataforma=plataforma,
        fecha_hora_utc=utc,
        fecha_local=local,
        origen=sesion.get("startingCause") or "",
        cola=chat.get("queueId"),
        tipificacion=tipificacion,
        tiendas=tiendas,
        en_cola=en_cola,
        atendido=atendido,
        derivado_tienda=derivado,
        tag_contactado=mapeo.tag_contactado in tags,
        cerrado=EVENTO_CIERRE in eventos,
    )


def construir_filas(
    sesiones: Iterable[dict[str, Any]], offset_horas: int = -5, mapeo: MapeoEtapas | None = None
) -> list[FilaSesion]:
    """Deduplica por ``session_id`` (las ventanas solapadas repiten sesiones)."""
    vistas: dict[str, FilaSesion] = {}
    for s in sesiones:
        fila = sesion_a_fila(s, offset_horas, mapeo)
        vistas[fila.session_id] = fila
    return sorted(vistas.values(), key=lambda f: f.fecha_hora_utc)


def _pct(numerador: int, denominador: int) -> float | None:
    if not denominador:
        return None
    return round(numerador / denominador * 100, 1)


def agregar_por_dia(filas: Iterable[FilaSesion]) -> list[dict[str, Any]]:
    """Agrega al grano que consume Power BI: una fila por dia local."""
    por_dia: dict[str, list[FilaSesion]] = {}
    for f in filas:
        por_dia.setdefault(f.fecha_local, []).append(f)

    salida = []
    for fecha in sorted(por_dia):
        grupo = por_dia[fecha]
        ingresos = len(grupo)
        unicos = len({f.chat_id for f in grupo})
        en_cola = sum(f.en_cola for f in grupo)
        atendidos = sum(f.atendido for f in grupo)
        derivados = sum(f.derivado_tienda for f in grupo)
        salida.append(
            {
                "fecha": fecha,
                "dia_semana": dt.date.fromisoformat(fecha).strftime("%a"),
                "ingresos": ingresos,
                "personas_unicas": unicos,
                "en_cola": en_cola,
                "atendidos": atendidos,
                "derivados_tienda": derivados,
                "pct_ingreso_a_cola": _pct(en_cola, ingresos),
                "pct_cola_a_atendido": _pct(atendidos, en_cola),
                "pct_atendido_a_tienda": _pct(derivados, atendidos),
                "pct_conversion_global": _pct(derivados, ingresos),
            }
        )
    return salida


def agregar_totales(filas: list[FilaSesion]) -> dict[str, Any]:
    ingresos = len(filas)
    en_cola = sum(f.en_cola for f in filas)
    atendidos = sum(f.atendido for f in filas)
    derivados = sum(f.derivado_tienda for f in filas)
    return {
        "ingresos": ingresos,
        "personas_unicas": len({f.chat_id for f in filas}),
        "en_cola": en_cola,
        "atendidos": atendidos,
        "derivados_tienda": derivados,
        "pct_ingreso_a_cola": _pct(en_cola, ingresos),
        "pct_cola_a_atendido": _pct(atendidos, en_cola),
        "pct_atendido_a_tienda": _pct(derivados, atendidos),
        "pct_conversion_global": _pct(derivados, ingresos),
    }


def agregar_por_tienda(filas: Iterable[FilaSesion]) -> list[dict[str, Any]]:
    conteo: dict[str, int] = {}
    for f in filas:
        for tienda in f.tiendas:
            conteo[tienda] = conteo.get(tienda, 0) + 1
    return [
        {"tienda": t, "derivaciones": n}
        for t, n in sorted(conteo.items(), key=lambda kv: -kv[1])
    ]
