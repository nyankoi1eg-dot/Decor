"""Clasifica los chats del canal Asesores Web por cómo terminaron.

Uso:
    python clasificar.py [desde] [hasta]        # por defecto 2026-09-01 2026-09-10

Lee los raw_*.json que dejó descargar.py y escribe resultados.json.

Regla de desenlace, en orden de prioridad (acordada con el canal):
    1. Compró            — gana sobre cualquier otro estado, y ahí termina
    2. Solicita ubicación — prioridad sobre el tag, salvo que haya comprado
    3. Derivado
    4. Abandono de compra — se desglosa por tipificación en una subsección
    5. resto de tipificaciones
    6. Solo contactado
    7. Sin tag ni tipificación — dato ciego

El tag define la etapa; la tipificación explica el desenlace y lo determina
cuando no hay tag de estado.
"""
import collections
import datetime as dt
import json
import sys

from botmaker_lib import (NUMERO_ANTIGUO, cargar_union, del_periodo, etiquetas,
                          etiquetas_norm, hora_peru, tiendas, tipificacion)

# Tipificaciones que no son leads comerciales (Eje 3 del criterio).
NO_LEAD = {
    "SolicitaUbicación": "Solicita ubicación",
    "Propaganda": "Propaganda / spam",
    "Consulta_atendida": "Consulta atendida",
    "CONSULTA_ATENDIDA_SAC": "Consulta atendida (SAC)",
    "CATEGORIIA": "Otra categoría o producto",
}

# Tipificaciones de pérdida por catálogo — el hallazgo accionable.
CATALOGO = {
    "NOPRODUCTO": "Sin producto (ambigua: no está en el manual)",
    "SINDISEÑO": "Sin diseño de producto",
    "/DESCONTINUADO": "Producto descontinuado",
}

# Nombre legible de cada tipificación. Es una lectura del slug, no el nombre
# oficial de la consola de Botmaker: las marcadas (*) no están en el manual.
NOMBRES = {
    "Lead_NO_calificado": "Lead no calificado (*)",
    "Lead_Calificado": "Lead calificado (*)",
    "Cliente_no_responde": "Cliente no responde",
    "Sin_respuesta": "Sin respuesta (anomalía: es exclusiva de SAC)",
    "CORPORATIVO-LEAD-DERIVADO": "Lead derivado (corporativo)",
    **NO_LEAD, **CATALOGO,
}


def desenlace(chat):
    tags = etiquetas_norm(chat)
    tip = tipificacion(chat)
    if "CLIENTE COMPRO" in tags:
        return "Compró"
    if tip == "SolicitaUbicación":
        return "Solicita ubicación"
    if {"DERIVADOS", "DERIVADOS A TIENDA"} & tags:
        return "Derivado"
    if "ABANDONO DE COMPRA" in tags:
        return "Abandono de compra"
    if tip in NO_LEAD:
        return NO_LEAD[tip]
    if tip in CATALOGO:
        return "Catálogo sin tag de estado"
    if tip in ("Lead_Calificado", "CORPORATIVO-LEAD-DERIVADO"):
        return "Lead calificado sin tag de cierre"
    if tip == "Lead_NO_calificado":
        return "Lead no calificado sin tag"
    if tip == "Cliente_no_responde":
        return "Cliente no responde"
    if tip == "Sin_respuesta":
        return "Sin respuesta (anomalía SAC)"
    if "CONTACTADO" in tags:
        return "Solo contactado"
    return "Sin tag ni tipificación"


def main(desde, hasta):
    periodo = del_periodo(cargar_union(), desde, hasta)
    antiguo = [c for c in periodo.values()
               if c["chat"].get("channelId") == NUMERO_ANTIGUO]
    vigente = [c for c in periodo.values()
               if c["chat"].get("channelId") != NUMERO_ANTIGUO]

    por_desenlace = collections.Counter(desenlace(c) for c in vigente)
    abandonos = [c for c in vigente if desenlace(c) == "Abandono de compra"]
    motivos = collections.Counter(
        NOMBRES.get(tipificacion(c), tipificacion(c) or "(sin tipificación)")
        for c in abandonos)

    con_pauta = [c for c in vigente
                 if (c.get("variables") or {}).get("referralSourceType")]

    def tasas(grupo):
        base = len(grupo)
        der = sum(1 for c in grupo if {"DERIVADOS", "DERIVADOS A TIENDA"} & etiquetas_norm(c))
        com = sum(1 for c in grupo if "CLIENTE COMPRO" in etiquetas_norm(c))
        aba = sum(1 for c in grupo if "ABANDONO DE COMPRA" in etiquetas_norm(c))
        return {"n": base, "derivados": der, "compraron": com, "abandonos": aba}

    resultados = {
        "periodo": [desde.isoformat(), hasta.isoformat()],
        "zona_horaria": "America/Lima (UTC-5), sobre lastSessionCreationTime",
        "total_recuperado": len(periodo),
        "numero_antiguo": len(antiguo),
        "numero_vigente": len(vigente),
        "desenlaces": dict(por_desenlace.most_common()),
        "abandono_por_motivo": dict(motivos.most_common()),
        "tiendas": dict(collections.Counter(
            t for c in vigente for t in tiendas(c)).most_common()),
        "origen": {"con_referral": len(con_pauta),
                   "sin_referral": len(vigente) - len(con_pauta)},
        "tasas_canal_completo": tasas(vigente),
        "tasas_pauta": tasas(con_pauta),
        "inventario_tags": dict(collections.Counter(
            t for c in vigente for t in etiquetas(c)).most_common()),
        "inventario_tipificaciones": dict(collections.Counter(
            tipificacion(c) for c in vigente).most_common()),
        "chats_sin_tag_ni_tipificacion": sorted(
            c["chat"]["chatId"] for c in vigente
            if desenlace(c) == "Sin tag ni tipificación"),
    }

    suma = sum(por_desenlace.values()) + len(antiguo)
    resultados["cuadre"] = {
        "suma_de_cubos": suma,
        "total_api": len(periodo),
        "cuadra": suma == len(periodo),
    }

    json.dump(resultados, open("resultados.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"total recuperado : {len(periodo)}")
    print(f"  número antiguo : {len(antiguo)}")
    print(f"  número vigente : {len(vigente)}")
    for nombre, n in por_desenlace.most_common():
        print(f"     {n:5d}  {nombre}")
    print(f"cuadre: {suma} vs {len(periodo)} — "
          f"{'CUADRA' if suma == len(periodo) else 'NO CUADRA'}")


if __name__ == "__main__":
    desde = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date(2026, 9, 1)
    hasta = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else dt.date(2026, 9, 10)
    main(desde, hasta)
