"""CLI de extraccion y carga.

    # backfill de un rango (fechas locales)
    python -m botmaker_bi.cli extraer --desde 2026-09-07 --hasta 2026-09-13 --salida semana.json

    # carga incremental a SQL Server (lo que se programa a diario)
    python -m botmaker_bi.cli cargar --desde 2026-09-07 --hasta 2026-09-13

    # ver el embudo por consola sin tocar la base
    python -m botmaker_bi.cli tabla --desde 2026-09-07 --hasta 2026-09-13
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys

from .client import BotmakerClient
from .funnel import agregar_por_dia, agregar_por_tienda, agregar_totales, construir_filas

log = logging.getLogger("botmaker_bi")
DIAS_SIN_LONG_TERM = 7


def _ventana_utc(desde: str, hasta: str, offset: int) -> tuple[str, str, bool]:
    d_ini = dt.date.fromisoformat(desde)
    d_fin = dt.date.fromisoformat(hasta)
    ini = dt.datetime.combine(d_ini, dt.time.min) - dt.timedelta(hours=offset)
    fin = dt.datetime.combine(d_fin + dt.timedelta(days=1), dt.time.min) - dt.timedelta(hours=offset)
    long_term = (dt.date.today() - d_ini).days > DIAS_SIN_LONG_TERM
    return ini.strftime("%Y-%m-%dT%H:%M:%SZ"), fin.strftime("%Y-%m-%dT%H:%M:%SZ"), long_term


def _defaults() -> tuple[str, str]:
    """Semana pasada completa, de lunes a domingo."""
    hoy = dt.date.today()
    inicio = hoy - dt.timedelta(days=hoy.weekday() + 7)
    return inicio.isoformat(), (inicio + dt.timedelta(days=6)).isoformat()


def _obtener_filas(desde: str, hasta: str, offset: int):
    frm, to, long_term = _ventana_utc(desde, hasta, offset)
    log.info("Consultando Botmaker %s -> %s (long_term=%s)", frm, to, long_term)
    cliente = BotmakerClient()
    sesiones = list(cliente.iter_sessions(frm, to, long_term=long_term))
    log.info("Sesiones recibidas: %s", len(sesiones))
    filas = construir_filas(sesiones, offset_horas=offset)
    return [f for f in filas if desde <= f.fecha_local <= hasta]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ini_def, fin_def = _defaults()

    parser = argparse.ArgumentParser(prog="botmaker_bi", description=__doc__)
    parser.add_argument("comando", choices=["extraer", "cargar", "tabla"])
    parser.add_argument("--desde", default=ini_def, help=f"Fecha local inicial (def. {ini_def})")
    parser.add_argument("--hasta", default=fin_def, help=f"Fecha local final (def. {fin_def})")
    parser.add_argument("--salida", help="Archivo JSON de salida para 'extraer'")
    parser.add_argument(
        "--offset",
        type=int,
        default=int(os.environ.get("BI_TIMEZONE_OFFSET", "-5")),
        help="Offset horario del negocio (def. -5, Lima)",
    )
    args = parser.parse_args(argv)

    filas = _obtener_filas(args.desde, args.hasta, args.offset)

    if args.comando == "extraer":
        datos = [f.as_dict() for f in filas]
        if args.salida:
            with open(args.salida, "w", encoding="utf-8") as fh:
                json.dump(datos, fh, ensure_ascii=False, indent=2)
            log.info("Escritas %s filas en %s", len(datos), args.salida)
        else:
            json.dump(datos, sys.stdout, ensure_ascii=False, indent=2)
        return 0

    if args.comando == "cargar":
        conn = os.environ.get("MSSQL_CONN")
        if not conn:
            log.error("Falta la variable de entorno MSSQL_CONN")
            return 2
        from .sqlserver import cargar

        n = cargar(conn, filas)
        log.info("Upsert completado: %s filas", n)
        return 0

    # comando 'tabla'
    diario = agregar_por_dia(filas)
    cols = ["fecha", "dia_semana", "ingresos", "personas_unicas", "en_cola", "atendidos",
            "derivados_tienda", "pct_ingreso_a_cola", "pct_cola_a_atendido",
            "pct_atendido_a_tienda", "pct_conversion_global"]
    print(" | ".join(c.rjust(12) for c in cols))
    for r in diario:
        print(" | ".join(str(r[c]).rjust(12) for c in cols))
    print("\nTOTALES:", json.dumps(agregar_totales(filas), ensure_ascii=False))
    print("POR TIENDA:", json.dumps(agregar_por_tienda(filas), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
