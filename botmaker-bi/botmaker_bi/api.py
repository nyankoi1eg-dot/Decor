"""Endpoint REST que expone el embudo conversacional a Power BI y a SQL Server.

Formas de consumo
-----------------
* ``GET /funnel/daily``    -> JSON, una fila por dia (grano del dashboard).
* ``GET /funnel/sessions`` -> JSON, una fila por sesion (grano de detalle).
* ``GET /funnel/daily.csv``-> el mismo agregado en CSV.
* ``GET /funnel/summary``  -> totales del periodo + corte por tienda.
* ``GET /``                -> app web: pide token y rango de fechas, y arma el reporte.

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
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .client import BotmakerAuthError, BotmakerClient, BotmakerError
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


async def _botmaker_token(
    x_botmaker_token: str | None = Header(default=None, alias="X-Botmaker-Token"),
) -> str | None:
    """Token de Botmaker por peticion.

    Permite que cada usuario de la app use su propio token sin que el servidor
    guarde credenciales. Si no viene, se cae a ``BOTMAKER_ACCESS_TOKEN``.
    """
    return x_botmaker_token


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


def _cargar(desde: str | None, hasta: str | None, token: str | None = None):
    frm, to, long_term = _rango(desde, hasta)
    if not token and not os.environ.get("BOTMAKER_ACCESS_TOKEN"):
        raise HTTPException(
            status_code=400,
            detail="Falta el token de Botmaker (header X-Botmaker-Token).",
        )
    cliente = BotmakerClient(access_token=token)
    try:
        sesiones = list(cliente.iter_sessions(frm, to, long_term=long_term))
    except BotmakerAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
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
    token: str | None = Depends(_botmaker_token),
) -> list[dict[str, Any]]:
    verificar_api_key(x_api_key)
    return agregar_por_dia(_cargar(desde, hasta, token))


@app.get("/funnel/sessions", summary="Detalle por sesion")
def funnel_sessions(
    desde: str | None = Query(None),
    hasta: str | None = Query(None),
    x_api_key: str | None = Depends(_api_key_header),
    token: str | None = Depends(_botmaker_token),
) -> list[dict[str, Any]]:
    verificar_api_key(x_api_key)
    return [f.as_dict() for f in _cargar(desde, hasta, token)]


@app.get("/funnel/summary", summary="Totales del periodo y corte por tienda")
def funnel_summary(
    desde: str | None = Query(None),
    hasta: str | None = Query(None),
    x_api_key: str | None = Depends(_api_key_header),
    token: str | None = Depends(_botmaker_token),
) -> dict[str, Any]:
    verificar_api_key(x_api_key)
    filas = _cargar(desde, hasta, token)
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
    token: str | None = Depends(_botmaker_token),
) -> StreamingResponse:
    verificar_api_key(x_api_key)
    datos = agregar_por_dia(_cargar(desde, hasta, token))
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


WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


@app.get("/", include_in_schema=False)
def app_web() -> FileResponse:
    """Sirve la app: pide token y rango de fechas, y arma el reporte."""
    return FileResponse(os.path.join(WEB_DIR, "index.html"), media_type="text/html")


# Montado al final para que no tape las rutas declaradas arriba.
app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
