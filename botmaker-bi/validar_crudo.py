"""Valida un JSON crudo de Botmaker antes de procesarlo.

    python validar_crudo.py botmaker_crudo_2026-09-01_a_2026-09-14.json

Revisa que el archivo tenga la forma que espera `botmaker_bi.funnel` y, sobre
todo, que traiga las senales que necesita el embudo. Un archivo exportado sin
`include-events=true` se lee sin error pero da un embudo de ceros: esto lo
detecta antes de que el numero llegue a un reporte.

No consulta la API: corre sobre el archivo, offline.
"""
from __future__ import annotations

import collections
import json
import sys

from botmaker_bi.funnel import (
    CLAVES_OPERADOR,
    EVENTO_ASIGNACION,
    EVENTO_CIERRE,
    EVENTO_COLA,
    PREFIJO_TAG_TIENDA,
    agregar_por_tienda,
    agregar_totales,
    construir_filas,
)

OK, AVISO, ERROR = "  ok  ", " AVISO", " ERROR"


def _items(datos) -> list[dict]:
    if isinstance(datos, dict):
        if "items" not in datos:
            raise SystemExit(f"{ERROR} falta la clave 'items' (claves: {sorted(datos)[:8]})")
        return datos["items"]
    if isinstance(datos, list):
        return datos
    raise SystemExit(f"{ERROR} el JSON no es ni objeto con 'items' ni lista")


def main(ruta: str) -> int:
    with open(ruta, encoding="utf-8") as fh:
        datos = json.load(fh)
    items = _items(datos)
    print(f"Archivo: {ruta}")
    if isinstance(datos, dict):
        print(f"  envoltorio: desde={datos.get('desde')} hasta={datos.get('hasta')} "
              f"total={datos.get('total')}")
    print(f"{OK} {len(items)} sesiones\n")
    if not items:
        raise SystemExit(f"{ERROR} no hay sesiones que procesar")

    fallos = 0

    # --- campos obligatorios ---
    sin_id = sum(1 for s in items if not s.get("id"))
    sin_fecha = sum(1 for s in items if not s.get("creationTime"))
    for n, que in ((sin_id, "sin 'id'"), (sin_fecha, "sin 'creationTime'")):
        if n:
            print(f"{ERROR} {n} sesiones {que} — son obligatorias")
            fallos += 1
    if not sin_id and not sin_fecha:
        print(f"{OK} todas traen 'id' y 'creationTime'")

    ids = collections.Counter(s.get("id") for s in items)
    repes = sum(v - 1 for v in ids.values() if v > 1)
    if repes:
        print(f"{AVISO} {repes} sesiones repetidas por 'id' (se deduplican solas)")

    # --- eventos: sin esto el embudo da todo cero ---
    con_ev = sum(1 for s in items if s.get("events"))
    if not con_ev:
        print(f"{ERROR} NINGUNA sesion trae 'events'. Exportaste sin "
              f"include-events=true: el embudo daria todo cero.")
        fallos += 1
    else:
        print(f"{OK} {con_ev}/{len(items)} sesiones con 'events'")

    nombres = collections.Counter(
        e.get("name") for s in items for e in (s.get("events") or []) if isinstance(e, dict)
    )
    for ev, papel in ((EVENTO_COLA, "cola"), (EVENTO_ASIGNACION, "asignacion"),
                      (EVENTO_CIERRE, "cierre/derivacion")):
        n = nombres.get(ev, 0)
        if n:
            print(f"{OK} evento '{ev}' ({papel}): {n}")
        else:
            print(f"{ERROR} falta el evento '{ev}' — sin el no hay {papel}")
            fallos += 1

    # --- los campos dentro de info que alimentan las metricas ---
    def info_de(nombre):
        return [e.get("info") for s in items for e in (s.get("events") or [])
                if isinstance(e, dict) and e.get("name") == nombre and isinstance(e.get("info"), dict)]

    colas = [i.get("queue") for i in info_de(EVENTO_COLA) if i.get("queue")]
    if colas:
        top = collections.Counter(colas).most_common(4)
        print(f"{OK} 'info.queue' presente: {', '.join(f'{k} ({v})' for k, v in top)}")
    elif nombres.get(EVENTO_COLA):
        print(f"{ERROR} los eventos '{EVENTO_COLA}' no traen 'info.queue': la cola saldria vacia")
        fallos += 1

    cierres = info_de(EVENTO_CIERRE)
    tips = [i.get("typification") for i in cierres if i.get("typification")]
    if tips:
        print(f"{OK} 'info.typification' presente en {len(tips)}/{len(cierres)} cierres")
        for k, v in collections.Counter(tips).most_common(6):
            print(f"         {k}: {v}")
    elif cierres:
        print(f"{ERROR} ningun cierre trae 'info.typification': no habria derivaciones")
        fallos += 1

    # Cual de las claves candidatas trae el operador. Es el unico dato que no
    # esta documentado, asi que conviene verlo antes de fijar el mapeo.
    halladas = collections.Counter(
        k for i in cierres for k in CLAVES_OPERADOR if isinstance(i.get(k), str) and i[k].strip()
    )
    if halladas:
        print(f"{OK} operador del cierre en: "
              + ", ".join(f"info.{k} ({v})" for k, v in halladas.most_common()))
    elif cierres:
        print(f"{AVISO} ningun cierre identifica al operador: el criterio B "
              f"quedaria igual que el A y no habria corte por gestor")

    # --- tags de tienda ---
    tdas = collections.Counter(
        t for s in items for t in ((s.get("chat") or {}).get("tags") or [])
        if isinstance(t, str) and t.startswith(PREFIJO_TAG_TIENDA)
    )
    if tdas:
        print(f"{OK} {len(tdas)} tiendas distintas en tags {PREFIJO_TAG_TIENDA}*")
    else:
        print(f"{AVISO} sin tags {PREFIJO_TAG_TIENDA}*: todas las derivaciones "
              f"caerian en '(sin tienda identificada)'")

    # --- prueba real: correr el calculo ---
    print("\n--- embudo resultante ---")
    try:
        filas = construir_filas(items)
    except Exception as exc:  # noqa: BLE001 - queremos el motivo, no el traceback
        raise SystemExit(f"{ERROR} el calculo fallo: {type(exc).__name__}: {exc}")

    t = agregar_totales(filas)
    print(f"  ingresos={t['ingresos']}  en_cola={t['en_cola']}  atendidos={t['atendidos']}  "
          f"derivados={t['derivados_tienda']}")
    print(f"  sin_cerrar={t['sin_cerrar']}  asignados={t['asignados']}  "
          f"cierres sin asignar={t['cerrados_por_operador_sin_asignar']}")
    print(f"  conversion global={t['pct_conversion_global']}%")

    fechas = sorted({f.fecha_local for f in filas})
    print(f"  rango de fechas: {fechas[0]} .. {fechas[-1]} ({len(fechas)} dias)")

    suma = sum(x["derivaciones"] for x in agregar_por_tienda(filas))
    if suma == t["derivados_tienda"]:
        print(f"{OK} la tabla por tienda cuadra con el embudo ({suma})")
    else:
        print(f"{ERROR} tabla por tienda={suma} pero derivados={t['derivados_tienda']}")
        fallos += 1

    if not t["en_cola"] or not t["atendidos"]:
        print(f"{ERROR} el embudo da cero en alguna etapa: revisa los eventos")
        fallos += 1

    print()
    if fallos:
        print(f"{ERROR} {fallos} problemas — el archivo no sirve todavia")
        return 1
    print(f"{OK} el archivo sirve. Procesalo con:")
    print(f"      python -m botmaker_bi.cli tabla --crudo {ruta} "
          f"--desde {fechas[0]} --hasta {fechas[-1]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    raise SystemExit(main(sys.argv[1]))
