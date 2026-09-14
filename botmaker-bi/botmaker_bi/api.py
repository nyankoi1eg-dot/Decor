"""Endpoint REST que expone el embudo conversacional a Power BI y a SQL Server.

Formas de consumo
-----------------
* ``GET /funnel/daily``    -> JSON, una fila por dia (grano del dashboard).
* ``GET /funnel/sessions`` -> JSON, una fila por sesion (grano de detalle).
* ``GET /funnel/daily.csv``-> el mismo agregado en CSV.
* ``GET /funnel/summary``  -> totales del periodo + corte por tienda.

Power BI Desktop: Obtener datos -> Web -> Avanzadas, URL del endpoint y el
header ``X-API-Key``. Devolvemos una lista JSON plana, sin envoltorio, para que
el conector la reconozca como tabla sin transformaciones extra.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from .client import BotmakerClient, BotmakerError
from .funnel import (
    agregar_por_dia,
    agregar_por_tienda,
    agregar_totales,
    construir_filas,
)

app = FastAPI(
    title="Decor Center - Embudo conversacional Botmaker",
    version="1.0.0",
    description="Metricas de ingreso, atencion y derivacion a tienda para SQL Server / Power BI.",
)

OFFSET = int(os.environ.get("BI_TIMEZONE_OFFSET", "-5"))
# Mas alla de 7 dias Botmaker exige long-term-search, que encarece la consulta.
DIAS_SIN_LONG_TERM = 7


def verificar_api_key(x_api_key: str | None = None) -> None:
    """Protege el endpoint si ``BI_API_KEY`` esta configurada."""
    esperada = os.environ.get("BI_API_KEY")
    if esperada and x_api_key != esperada:
        raise HTTPException(status_code=401, detail="X-API-Key invalida o ausente")


async def _api_key_header(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    return x_api_key


def _rango(desde: str | None, hasta: str | None) -> tuple[str, str, bool]:
    """Normaliza el rango de fechas locales a la ventana UTC que pide la API.

    Por defecto: la semana pasada completa (lunes a domingo).
    """
    if not desde or not hasta:
        hoy = dt.date.today()
        lunes_actual = hoy - dt.timedelta(days=hoy.weekday())
        inicio = lunes_actual - dt.timedelta(days=7)
        fin = inicio + dt.timedelta(days=6)
        desde = desde or inicio.isoformat()
        hasta = hasta or fin.isoformat()
    try:
        d_ini = dt.date.fromisoformat(desde)
        d_fin = dt.date.fromisoformat(hasta)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Fecha invalida: {exc}") from exc
    if d_fin < d_ini:
        raise HTTPException(status_code=422, detail="'hasta' no puede ser anterior a 'desde'")

    # La API solo acepta UTC con sufijo Z, asi que corremos el offset local.
    ini_utc = dt.datetime.combine(d_ini, dt.time.min) - dt.timedelta(hours=OFFSET)
    fin_utc = dt.datetime.combine(d_fin + dt.timedelta(days=1), dt.time.min) - dt.timedelta(hours=OFFSET)
    long_term = (dt.date.today() - d_ini).days > DIAS_SIN_LONG_TERM
    return ini_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), fin_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), long_term


def _cargar(desde: str | None, hasta: str | None):
    frm, to, long_term = _rango(desde, hasta)
    cliente = BotmakerClient()
    try:
        sesiones = list(cliente.iter_sessions(frm, to, long_term=long_term))
    except BotmakerError as exc:
        raise HTTPException(status_code=502, detail=f"Botmaker: {exc}") from exc
    filas = construir_filas(sesiones, offset_horas=OFFSET)
    # La ventana UTC puede arrastrar bordes; recortamos por fecha local.
    d_ini, d_fin = _rango_local(desde, hasta)
    return [f for f in filas if d_ini <= f.fecha_local <= d_fin]


def _rango_local(desde: str | None, hasta: str | None) -> tuple[str, str]:
    if not desde or not hasta:
        hoy = dt.date.today()
        inicio = hoy - dt.timedelta(days=hoy.weekday() + 7)
        desde = desde or inicio.isoformat()
        hasta = hasta or (inicio + dt.timedelta(days=6)).isoformat()
    return desde, hasta


@app.get("/health", summary="Chequeo de vida")
def health() -> dict[str, Any]:
    return {"status": "ok", "offset_horario": OFFSET}


@app.get("/funnel/daily", summary="Embudo agregado por dia")
def funnel_daily(
    desde: str | None = Query(None, description="Fecha local inicial YYYY-MM-DD"),
    hasta: str | None = Query(None, description="Fecha local final YYYY-MM-DD (inclusive)"),
    x_api_key: str | None = Depends(_api_key_header),
) -> list[dict[str, Any]]:
    verificar_api_key(x_api_key)
    return agregar_por_dia(_cargar(desde, hasta))


@app.get("/funnel/sessions", summary="Detalle por sesion")
def funnel_sessions(
    desde: str | None = Query(None),
    hasta: str | None = Query(None),
    x_api_key: str | None = Depends(_api_key_header),
) -> list[dict[str, Any]]:
    verificar_api_key(x_api_key)
    return [f.as_dict() for f in _cargar(desde, hasta)]


@app.get("/funnel/summary", summary="Totales del periodo y corte por tienda")
def funnel_summary(
    desde: str | None = Query(None),
    hasta: str | None = Query(None),
    x_api_key: str | None = Depends(_api_key_header),
) -> dict[str, Any]:
    verificar_api_key(x_api_key)
    filas = _cargar(desde, hasta)
    return {
        "periodo": dict(zip(("desde", "hasta"), _rango_local(desde, hasta))),
        "totales": agregar_totales(filas),
        "por_tienda": agregar_por_tienda(filas),
        "por_dia": agregar_por_dia(filas),
    }


@app.get("/funnel/daily.csv", summary="Embudo diario en CSV")
def funnel_daily_csv(
    desde: str | None = Query(None),
    hasta: str | None = Query(None),
    x_api_key: str | None = Depends(_api_key_header),
) -> StreamingResponse:
    verificar_api_key(x_api_key)
    datos = agregar_por_dia(_cargar(desde, hasta))
    buffer = io.StringIO()
    columnas = list(datos[0].keys()) if datos else ["fecha"]
    escritor = csv.DictWriter(buffer, fieldnames=columnas)
    escritor.writeheader()
    escritor.writerows(datos)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="funnel_diario.csv"'},
    )
