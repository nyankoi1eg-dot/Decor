"""Transforma sesiones crudas de Botmaker en filas de embudo listas para BI.

Las etapas se definen ANIDADAS: cada una exige haber pasado la anterior. Es lo
que hace que los porcentajes de conversion se puedan leer como un embudo y no
den por encima de 100%.

    1. ingreso  -> existe la sesion
    2. en_cola  -> la conversacion salio del bot hacia atencion humana
    3. atendido -> un operador efectivamente la trabajo
    4. derivado -> la tipificacion de cierre la marca como derivada a tienda

CADA SENAL SALE DE LA PROPIA SESION, NUNCA DEL ESTADO ACTUAL DEL CHAT
----------------------------------------------------------------------
``chat.tags`` y ``chat.variables`` describen el chat *hoy*, no como termino
esta sesion. Los tags se siguen agregando despues de la conversacion y el
objeto ``chat`` viene repetido e identico en todas las sesiones del mismo
contacto, asi que usarlos contamina sesiones viejas y de otras semanas con el
desenlace de la ultima. Por eso:

  * la derivacion sale del evento ``conversation-close`` -> ``info.typification``
  * la cola sale del evento ``queue-set`` -> ``info.queue``

``chat.queueId`` no se usa: ``GET /v2.0/sessions`` no lo devuelve nunca, y
leerlo dejaba la columna ``cola`` vacia en el 100% de las filas.

Los tags solo se conservan para atribuir la tienda (``TDA*``) y como dato de
auditoria, nunca para decidir una etapa.

ATRIBUCION TEMPORAL
-------------------
El ingreso, la cola y la atencion se cuentan el dia en que ENTRO el chat.
La derivacion se cuenta el dia en que CERRO la conversacion, porque es cuando
el gestor la tipifica: un chat que entra el viernes y se cierra el lunes
deriva el lunes. Por eso ``pct_atendido_a_tienda`` de un dia suelto puede
pasar de 100% (los derivados de ese dia vienen de chats de dias anteriores);
en el total del periodo vuelve a leerse como embudo.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Iterable

# --- Mapeo especifico de Decor Center -------------------------------------
# Tipificaciones de cierre que representan una derivacion a tienda.
TIPIFICACIONES_DERIVACION = {"Lead_Calificado", "CORPORATIVO-LEAD-DERIVADO"}
# Tipificaciones que el negocio considera "consulta atendida".
TIPIFICACIONES_ATENDIDO = {"Consulta_atendida", "CONSULTA_ATENDIDA_SAC"}
# Las tiendas se etiquetan con el prefijo TDA*.
PREFIJO_TAG_TIENDA = "TDA"
# Tag que el equipo usa como "ya se contacto al cliente".
TAG_CONTACTADO = "CONTACTADO"
# Cubo explicito para que la tabla por tienda cuadre con el total de derivados.
SIN_TIENDA = "(sin tienda identificada)"

EVENTO_COLA = "queue-set"
EVENTO_ASIGNACION = "assigned-to-agent"
EVENTO_CIERRE = "conversation-close"

# Botmaker no documenta con que nombre viaja el operador dentro de ``info``.
# Se prueban los candidatos en orden y gana el primero con contenido.
CLAVES_OPERADOR = ("operatorName", "operator", "agentName", "agent",
                   "userName", "user", "closedBy", "by", "email")
#: Idem para el agente al que se asigno el chat (evento ``assigned-to-agent``).
CLAVES_AGENTE = ("agentName", "agent", "operatorName", "operator",
                 "userName", "user", "assignedTo", "to", "email")
#: Etiqueta para las filas sin gestor identificable.
SIN_GESTOR = "(sin gestor identificado)"
# Los eventos no siempre llegan ordenados; se ordenan por la primera de estas
# claves que exista antes de quedarse con "el ultimo".
CLAVES_TIMESTAMP = ("creationTime", "time", "timestamp", "date")


@dataclass(frozen=True)
class MapeoEtapas:
    """Permite ajustar el mapeo sin tocar el codigo (ver ``/config`` en la API)."""

    tipificaciones_derivacion: frozenset[str] = frozenset(TIPIFICACIONES_DERIVACION)
    tipificaciones_atendido: frozenset[str] = frozenset(TIPIFICACIONES_ATENDIDO)
    prefijo_tag_tienda: str = PREFIJO_TAG_TIENDA
    tag_contactado: str = TAG_CONTACTADO
    claves_operador: tuple[str, ...] = CLAVES_OPERADOR
    claves_agente: tuple[str, ...] = CLAVES_AGENTE
    #: Operadores que en realidad son automatizacion y no atencion humana.
    #: El token de API esta emitido a nombre de una persona, asi que los cierres
    #: hechos por el propio token figuran con ese nombre. Vacio = no excluir.
    operadores_excluidos: frozenset[str] = frozenset()


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
    fecha_cierre_local: str | None
    fecha_derivacion: str | None
    origen: str
    cola: str | None
    tipificacion: str | None
    tienda: str | None
    operador_cierre: str | None
    agente_asignado: str | None
    gestor: str | None
    tiendas: list[str] = field(default_factory=list)
    ingreso: bool = True
    en_cola: bool = False
    asignado: bool = False
    cerrado_por_operador: bool = False
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

    El sufijo de milisegundos aparece o no segun el endpoint, asi que se acepta
    cualquiera de las dos formas en vez de reventar con ValueError.
    """
    texto = (creation_time or "").strip().replace("Z", "+00:00")
    momento = dt.datetime.fromisoformat(texto).replace(tzinfo=None)
    local = momento + dt.timedelta(hours=offset_horas)
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ"), local.date().isoformat()


def _orden_evento(evento: dict[str, Any]) -> str:
    for clave in CLAVES_TIMESTAMP:
        valor = evento.get(clave)
        if isinstance(valor, str) and valor:
            return valor
    return ""


def _eventos_por_nombre(sesion: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Agrupa los eventos por nombre, cada grupo ordenado cronologicamente."""
    por_nombre: dict[str, list[dict[str, Any]]] = {}
    for e in sesion.get("events") or []:
        if isinstance(e, dict):
            por_nombre.setdefault(e.get("name") or "", []).append(e)
    for grupo in por_nombre.values():
        grupo.sort(key=_orden_evento)
    return por_nombre


def _info_ultimo(eventos: dict[str, list[dict[str, Any]]], nombre: str) -> dict[str, Any]:
    """``info`` del ultimo evento con ese nombre.

    Se toma el ultimo y no el primero porque una conversacion puede re-encolarse
    o cerrarse mas de una vez: lo que describe el desenlace es el ultimo.
    """
    grupo = eventos.get(nombre) or []
    if not grupo:
        return {}
    info = grupo[-1].get("info")
    return info if isinstance(info, dict) else {}


def _fecha_evento(
    eventos: dict[str, list[dict[str, Any]]], nombre: str, offset_horas: int
) -> str | None:
    """Fecha local del ultimo evento con ese nombre, o ``None`` si no lo hay."""
    grupo = eventos.get(nombre) or []
    if not grupo:
        return None
    marca = _orden_evento(grupo[-1])
    if not marca:
        return None
    try:
        return _fecha_local(marca, offset_horas)[1]
    except ValueError:
        return None


def _texto(valor: Any) -> str | None:
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return None


def _operador(info: dict[str, Any], claves: tuple[str, ...]) -> str | None:
    for clave in claves:
        nombre = _texto(info.get(clave))
        if nombre:
            return nombre
    return None


def sesion_a_fila(
    sesion: dict[str, Any], offset_horas: int = -5, mapeo: MapeoEtapas | None = None
) -> FilaSesion:
    mapeo = mapeo or MapeoEtapas()
    chat = sesion.get("chat") or {}
    ref = chat.get("chat") or {}
    eventos = _eventos_por_nombre(sesion)
    tags = set(chat.get("tags") or [])
    utc, local = _fecha_local(sesion["creationTime"], offset_horas)

    # --- Senales propias de la sesion, leidas de sus eventos ---------------
    cola = _texto(_info_ultimo(eventos, EVENTO_COLA).get("queue"))
    info_cierre = _info_ultimo(eventos, EVENTO_CIERRE)
    tipificacion = _texto(info_cierre.get("typification"))
    operador = _operador(info_cierre, mapeo.claves_operador)
    if operador and operador in mapeo.operadores_excluidos:
        operador = None
    agente = _operador(_info_ultimo(eventos, EVENTO_ASIGNACION), mapeo.claves_agente)
    if agente and agente in mapeo.operadores_excluidos:
        agente = None

    channel_id = ref.get("channelId") or ""
    partes = channel_id.split("-")
    plataforma = partes[1] if len(partes) > 1 else channel_id

    # --- Etapas anidadas ---------------------------------------------------
    cerrado = EVENTO_CIERRE in eventos
    asignado = EVENTO_ASIGNACION in eventos
    # Un operador que cierra la conversacion la trabajo, aunque el chat nunca
    # se le asignara formalmente (criterio B).
    cerrado_por_operador = bool(operador)
    en_cola = EVENTO_COLA in eventos or asignado
    atendido = en_cola and (asignado or cerrado_por_operador)
    derivado = atendido and tipificacion in mapeo.tipificaciones_derivacion

    # Una sola tienda por derivacion, para que la tabla por tienda sume igual
    # que el total de derivados. Si hay varios tags TDA* gana el primero en
    # orden estable; ``tiendas`` conserva todos para poder auditarlo.
    tiendas = sorted(t for t in tags if t.startswith(mapeo.prefijo_tag_tienda))
    tienda = (tiendas[0] if tiendas else SIN_TIENDA) if derivado else None

    # La derivacion se atribuye al dia del cierre, que es cuando el gestor la
    # tipifica. Si el cierre no trae marca de tiempo se cae al dia de ingreso
    # antes que perder la derivacion.
    fecha_cierre = _fecha_evento(eventos, EVENTO_CIERRE, offset_horas)
    fecha_derivacion = (fecha_cierre or local) if derivado else None
    # El gestor es quien la trabajo: manda quien la cerro, y si nadie cerro,
    # el agente al que se le asigno.
    gestor = operador or agente
    if atendido and not gestor:
        gestor = SIN_GESTOR

    return FilaSesion(
        session_id=sesion["id"],
        chat_id=ref.get("chatId") or "",
        contact_id=ref.get("contactId") or "",
        channel_id=channel_id,
        plataforma=plataforma,
        fecha_hora_utc=utc,
        fecha_local=local,
        fecha_cierre_local=fecha_cierre,
        fecha_derivacion=fecha_derivacion,
        origen=sesion.get("startingCause") or "",
        cola=cola,
        tipificacion=tipificacion,
        tienda=tienda,
        operador_cierre=operador,
        agente_asignado=agente,
        gestor=gestor,
        tiendas=tiendas,
        en_cola=en_cola,
        asignado=asignado,
        cerrado_por_operador=cerrado_por_operador,
        atendido=atendido,
        derivado_tienda=derivado,
        tag_contactado=mapeo.tag_contactado in tags,
        cerrado=cerrado,
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


#: Metricas que NO se pueden sumar entre dias. Una persona que escribe el lunes
#: y el martes cuenta una vez por dia y una sola vez en el periodo: sumar la
#: columna da 614 donde el distinct real del periodo da 579. Quien consuma esta
#: salida no debe totalizarlas ni agregarlas por su cuenta.
CAMPOS_NO_ADITIVOS = ("personas_unicas",)


def _bloque_embudo(filas: list[FilaSesion], derivados: int | None = None) -> dict[str, Any]:
    """Cifras del embudo para un conjunto de filas, con sus porcentajes.

    ``derivados`` se puede forzar para el corte diario, donde las derivaciones
    no son las de las sesiones que entraron ese dia sino las que cerraron.
    """
    ingresos = len(filas)
    en_cola = sum(f.en_cola for f in filas)
    atendidos = sum(f.atendido for f in filas)
    # De los chats que ENTRARON en este grupo, cuantos terminaron derivando,
    # sin importar que dia cerraron. Es la unica cifra que comparte poblacion
    # con ingresos/en_cola/atendidos, asi que es la que da porcentajes legibles.
    cohorte = sum(f.derivado_tienda for f in filas)
    if derivados is None:
        derivados = cohorte
    return {
        "ingresos": ingresos,
        "personas_unicas": len({f.chat_id for f in filas if f.chat_id}),
        "en_cola": en_cola,
        "atendidos": atendidos,
        # Imputadas al dia del CIERRE: "cuanto derivamos ese dia" (operativo).
        "derivados_tienda": derivados,
        # Imputadas al dia de INGRESO: "de lo que entro ese dia, cuanto derivo"
        # (conversion). En el total del periodo las dos coinciden.
        "derivados_cohorte": cohorte,
        "sin_cerrar": sum(not f.cerrado for f in filas),
        "pct_ingreso_a_cola": _pct(en_cola, ingresos),
        "pct_cola_a_atendido": _pct(atendidos, en_cola),
        # Sobre la cohorte, no sobre los cierres del dia: dividir derivaciones
        # de otros dias por los atendidos de este daba porcentajes de mas de 100%.
        "pct_atendido_a_tienda": _pct(cohorte, atendidos),
        "pct_conversion_global": _pct(cohorte, ingresos),
    }


def _derivaciones_por_dia(filas: Iterable[FilaSesion]) -> dict[str, int]:
    """Derivaciones agrupadas por el dia en que CERRO la conversacion."""
    conteo: dict[str, int] = {}
    for f in filas:
        if f.derivado_tienda and f.fecha_derivacion:
            conteo[f.fecha_derivacion] = conteo.get(f.fecha_derivacion, 0) + 1
    return conteo


def agregar_por_dia(filas: Iterable[FilaSesion]) -> list[dict[str, Any]]:
    """Agrega al grano que consume Power BI: una fila por dia local.

    Ingresos, cola y atendidos van al dia en que entro el chat; las derivaciones
    al dia en que cerro. Un dia puede por eso mostrar mas derivados que
    atendidos, y ``pct_atendido_a_tienda`` pasar de 100%: son derivaciones de
    chats que entraron antes. El total del periodo si cierra como embudo.

    ``personas_unicas`` es distinct por dia y NO se puede sumar (ver
    ``CAMPOS_NO_ADITIVOS``). ``provisional`` marca los dias que todavia tienen
    sesiones sin cerrar: los ultimos dias de cualquier extraccion son siempre
    provisionales porque las conversaciones siguen abiertas.
    """
    filas = list(filas)
    por_dia: dict[str, list[FilaSesion]] = {}
    for f in filas:
        por_dia.setdefault(f.fecha_local, []).append(f)
    derivaciones = _derivaciones_por_dia(filas)

    salida = []
    for fecha in sorted(set(por_dia) | set(derivaciones)):
        grupo = por_dia.get(fecha, [])
        fila = {"fecha": fecha, "dia_semana": dt.date.fromisoformat(fecha).strftime("%a")}
        fila.update(_bloque_embudo(grupo, derivados=derivaciones.get(fecha, 0)))
        fila["provisional"] = fila["sin_cerrar"] > 0
        salida.append(fila)
    return salida


def agregar_totales(filas: list[FilaSesion]) -> dict[str, Any]:
    """Totales del periodo.

    ``personas_unicas`` se recalcula sobre todo el periodo en vez de sumar la
    columna diaria, que contaria dos veces a quien vuelve otro dia.
    """
    filas = list(filas)
    total = _bloque_embudo(filas)
    total["campos_no_aditivos"] = list(CAMPOS_NO_ADITIVOS)
    total["criterio_atendido"] = "B"  # asignado o cerrado por un operador
    total["asignados"] = sum(f.asignado for f in filas)
    # Cuantas derivaciones cerraron un dia distinto al del ingreso: es la
    # magnitud del desfase entre las dos lecturas de la tabla diaria.
    total["derivaciones_diferidas"] = sum(
        f.derivado_tienda and f.fecha_derivacion != f.fecha_local for f in filas
    )
    total["cerrados_por_operador_sin_asignar"] = sum(
        f.cerrado_por_operador and not f.asignado for f in filas
    )
    return total


def agregar_por_tienda(filas: Iterable[FilaSesion]) -> list[dict[str, Any]]:
    """Una fila por tienda, contando DERIVACIONES (no pares sesion x tag).

    La suma de ``derivaciones`` es exactamente ``derivados_tienda`` del total:
    cada sesion derivada aporta 1 a una sola tienda, y las que no tienen tag
    ``TDA*`` caen en el cubo ``SIN_TIENDA`` en vez de desaparecer. Contar pares
    (sesion x tag) inflaba el corte por tienda por encima del total del embudo.
    """
    conteo: dict[str, int] = {}
    for f in filas:
        if f.derivado_tienda:
            clave = f.tienda or SIN_TIENDA
            conteo[clave] = conteo.get(clave, 0) + 1
    # El cubo sin identificar va siempre al final, no compite por volumen.
    return [
        {"tienda": t, "derivaciones": n}
        for t, n in sorted(conteo.items(), key=lambda kv: (kv[0] == SIN_TIENDA, -kv[1], kv[0]))
    ]


def agregar_por_gestor(filas: Iterable[FilaSesion]) -> list[dict[str, Any]]:
    """Un bloque de embudo por gestor, para las pestanas del reporte.

    Solo entran las sesiones ATENDIDAS: un chat que murio en el bot no tiene
    gestor a quien atribuirselo. Por eso la suma de ``atendidos`` de todos los
    gestores es el total de atendidos del periodo, pero la de ``ingresos`` no
    es el total de ingresos.
    """
    por_gestor: dict[str, list[FilaSesion]] = {}
    for f in filas:
        if f.atendido:
            por_gestor.setdefault(f.gestor or SIN_GESTOR, []).append(f)

    salida = []
    for gestor, grupo in por_gestor.items():
        bloque = {"gestor": gestor}
        bloque.update(_bloque_embudo(grupo))
        bloque["por_tienda"] = agregar_por_tienda(grupo)
        bloque["por_dia"] = agregar_por_dia(grupo)
        salida.append(bloque)
    salida.sort(key=lambda b: (b["gestor"] == SIN_GESTOR, -b["atendidos"], b["gestor"]))
    return salida
