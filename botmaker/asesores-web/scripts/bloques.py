"""Clasifica los chats de Asesores Web en tres bloques por cómo terminaron.

    A · Terminados por el bot     nunca llegaron a un gestor
    B · No son leads comerciales  fueron atendidos, sin intención de compra
    C · Con intención de compra   cómo terminó esa conversación

Regla acordada con el canal: la tipificación explica el cierre; cuando no lo
explica, manda el tag de mayor peso. Los hechos que registra el gestor —una
compra, una tienda asignada— pesan más que cualquier etiqueta.

Solo se usa el vocabulario del Manual de Tags. `Lead_Calificado` y
`Lead_NO_calificado` cubren el 71% de los cierres pero no figuran en el manual,
y no significan lo que parecen: la diferencia entre ambas no es intención sino
derivación (el 98% de las "no calificado" lleva ABANDONO_DE_COMPRA y ninguna
lleva DERIVADOS). Quedan fuera.

Base del eje de intención — sección 5 del manual: el botón «Realizar una
compra» dispara CONTACTADO automáticamente, así que llevar ese tag es, por
definición del propio flujo, haber declarado intención de compra.
"""
import collections

from botmaker_lib import etiquetas, etiquetas_norm, normalizar, tiendas

# Eje 3 del manual: no son leads comerciales, se filtran antes de medir el funnel.
NO_LEAD = {
    "SolicitaUbicación":     "Solicita ubicación",
    "Propaganda":            "Propaganda / spam",
    "Consulta_atendida":     "Consulta atendida",
    "CONSULTA_ATENDIDA_SAC": "Consulta atendida",
    "CATEGORIIA":            "Preguntan por otra categoría o producto",
}

# Eje 2 del manual: motivo de salida. Las tres de catálogo son el hallazgo
# accionable — no es falla de gestión ni de pauta, es falta de producto.
MOTIVO = {
    "Cliente_no_responde":       "Lead no responde",
    "SINDISEÑO":                 "Sin diseño de producto",
    "/DESCONTINUADO":            "Producto descontinuado",
    "NOPRODUCTO":                "Producto sin stock (etiqueta ambigua)",
    "CORPORATIVO-LEAD-DERIVADO": "Lead derivado",
}

# Tags reales que NO están en el manual y por tanto no clasifican:
# PENDIENTES (246), PENDIENTE DE COMPRA (95), TAG_* de navegación del bot,
# Asesores_Venta / Asesores_SAC (cola), TEST API. `PENDIENTE DE COMPRA` describe
# una etapa del funcionamiento real que el manual no contempla: si el equipo lo
# usa para marcar leads vivos, conviene incorporarlo al manual antes de contarlo.
#
# Fuera del manual: no clasifican. `Sin_respuesta` además es exclusiva de la
# cola SAC y el criterio del canal prohíbe que aparezca acá.
IGNORADAS = {"Lead_Calificado", "Lead_NO_calificado", "Sin_respuesta"}


def tipificacion(chat):
    return (chat.get("variables") or {}).get("typification")


def bloque(chat):
    """Devuelve (bloque, desenlace)."""
    tags, tip = etiquetas_norm(chat), tipificacion(chat)

    # 1. Eje 3: el manual los saca del funnel antes de medir.
    if tip in NO_LEAD:
        return "B", NO_LEAD[tip]

    # 2. Hechos registrados por el gestor, en el orden de prioridad del manual.
    #    Una compra o una tienda asignada prueban la intención por sí solas.
    if "CLIENTE COMPRO" in tags:
        return "C", "Compró"
    if "DERIVADO PERO NO COMPRO" in tags:
        return "C", "Derivado, no compró"
    if {"DERIVADOS", "DERIVADOS A TIENDA"} & tags or tiendas(chat):
        return "C", "Derivado a tienda"

    # 3. Etapa alcanzada, con el motivo que aporte la tipificación.
    if "ABANDONO DE COMPRA" in tags:
        return "C", "Abandono — " + (MOTIVO.get(tip) or "sin motivo tipificado")
    if "EN ATENCION" in tags:
        return "C", "En atención, sin desenlace"
    if "CONTACTADO" in tags:
        return "C", "Contactado, sin avanzar de etapa"

    # 4. Sin ningún tag de estado: nunca entró al funnel comercial.
    if tip in MOTIVO:
        return "C", "Sin tag de estado — " + MOTIVO[tip]
    return "A", "Sin tag del manual"


NOMBRE = {
    "A": "A · Terminados por el bot, nunca entraron al funnel",
    "B": "B · No son leads comerciales (Eje 3 del manual)",
    "C": "C · Leads con intención de compra",
}


def informe(chats, titulo, clasificador=bloque):
    """Imprime la distribución y verifica que la suma cuadre."""
    print("=" * 70)
    print(titulo, f"(n={len(chats)})")
    print("=" * 70)
    res = [clasificador(c) for c in chats]
    total = collections.Counter(b for b, _ in res)
    for b in "CBA":
        n = total.get(b, 0)
        print(f"\n{NOMBRE[b]} — {n} ({100 * n / len(chats):.1f}%)")
        for desenlace, k in collections.Counter(
                d for bb, d in res if bb == b).most_common():
            print(f"     {k:5d}  {desenlace}")
    suma = sum(total.values())
    print(f"\nSUMA {suma} vs {len(chats)} — "
          f"{'CUADRA' if suma == len(chats) else 'NO CUADRA'}")
    return res
