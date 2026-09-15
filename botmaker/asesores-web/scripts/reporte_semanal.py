"""Reporte semanal del canal Asesores Web.

    python reporte_semanal.py 2026-09-07 2026-09-13

Lee los raw_*.json de descargar.py y, si existe mensajes.json, usa lo que el
cliente escribió para resolver lo que los tags no explican.
"""
import collections
import datetime as dt
import json
import os
import sys

import bloques as B
from botmaker_lib import (NUMERO_ANTIGUO, cargar_union, del_periodo,
                          es_sac, etiquetas_norm, hora_peru, tiendas)
from leer_mensajes import que_pidio

TIENDAS = {"TDAMOLINA": "La Molina", "TDASALAVERRY": "Salaverry",
           "TDAARGENTINA": "Argentina", "TDARPANAMA": "Rep. Panamá",
           "TDAPALAO": "Palao", "TDAPIURA": "Piura", "TDAAREQUIPA": "Arequipa",
           "TDATRUJILLO": "Trujillo", "TDAICA": "Ica", "TDACHICLAYO": "Chiclayo",
           "TDAHUANCAYO": "Huancayo", "TDATACNA": "Tacna",
           "TDAECOMMERCE": "Ecommerce", "UTDACORPORATIVO": "Corporativo"}

MSGS = json.load(open("mensajes.json", encoding="utf-8")) if os.path.exists("mensajes.json") else {}


def clasificar(chat):
    """Bloques del manual, completados con los mensajes donde el tag no alcanza."""
    b, desenlace = B.bloque(chat)
    if not MSGS:
        return b, desenlace
    pidio = que_pidio(MSGS.get(chat["chat"]["chatId"]))

    if b == "A":                                    # ningún tag del manual
        return {"compra":    ("C", "Pidió comprar, nunca fue atendido"),
                "ubicacion": ("B", "Solicita ubicación u horario"),
                "postventa": ("B", "Consulta de postventa"),
                "vacio":     ("A", "El cliente no escribió nada"),
                "ambiguo":   ("A", "Solo saludo o clic, sin pedir nada")}[pidio]

    if desenlace == "Abandono — sin motivo tipificado":
        return {"compra":    ("C", "Pidió comprar y se perdió, sin motivo registrado"),
                "ubicacion": ("B", "Solicita ubicación u horario"),
                "postventa": ("B", "Consulta de postventa"),
                "vacio":     ("C", "Abandono sin mensajes recuperables"),
                "ambiguo":   ("C", "Abandono tras saludo o clic, sin pedir nada")}[pidio]

    return b, desenlace


def main(desde, hasta):
    periodo = del_periodo(cargar_union(), desde, hasta)
    antiguo = [c for c in periodo.values() if c["chat"].get("channelId") == NUMERO_ANTIGUO]
    resto = [c for c in periodo.values() if c["chat"].get("channelId") != NUMERO_ANTIGUO]
    sac = [c for c in resto if es_sac(c)]
    canal = [c for c in resto if not es_sac(c)]

    print(f"\nPERÍODO {desde} a {hasta} · hora Perú\n")
    print(f"  {len(periodo):5d}  chats recuperados del API")
    print(f"  {len(canal):5d}  Asesores Web")
    print(f"  {len(sac):5d}  cola SAC — fuera del conteo")
    print(f"  {len(antiguo):5d}  número antiguo +51 993 313 227 — fuera del conteo\n")
    B.informe(canal, "DESENLACE DE LOS CHATS", clasificar)

    tags = lambda c: etiquetas_norm(c)
    contactado = [c for c in canal if "CONTACTADO" in tags(c)]
    atendido = [c for c in canal if "EN ATENCION" in tags(c)]
    derivado = [c for c in canal if {"DERIVADOS", "DERIVADOS A TIENDA"} & tags(c) or tiendas(c)]
    compro = [c for c in canal if "CLIENTE COMPRO" in tags(c)]

    def pct(a, b):
        return f"{100 * a / b:5.1f}%" if b else "   n/d"

    print("\n" + "=" * 70); print("EMBUDO POR ETAPA"); print("=" * 70)
    print(f"  Ingresaron al chat      {len(canal):5d}")
    print(f"  Tag CONTACTADO          {len(contactado):5d}   {pct(len(contactado), len(canal))} de los que ingresaron")
    print(f"  Tag EN_ATENCIÓN         {len(atendido):5d}   " +
          ("CIEGO — el tag no se usa" if not atendido else pct(len(atendido), len(contactado))))
    print(f"  Derivados a tienda      {len(derivado):5d}   {pct(len(derivado), len(contactado))} de CONTACTADO")
    print(f"  Compraron               {len(compro):5d}   {pct(len(compro), len(derivado))} de derivados")
    print(f"\n  conversión ingreso → compra: {100 * len(compro) / len(canal):.2f}%")

    print("\n" + "=" * 70); print("DERIVADOS POR TIENDA"); print("=" * 70)
    der = collections.Counter(t for c in derivado for t in tiendas(c))
    ven = collections.Counter(t for c in compro for t in tiendas(c))
    for t, n in der.most_common():
        fuera = "" if t in TIENDAS else "   ← fuera del manual"
        print(f"  {TIENDAS.get(t, t):14s} {n:4d} derivados · {ven.get(t, 0):2d} compras"
              f" · cierre {pct(ven.get(t, 0), n)}{fuera}")
    sin_tienda = sum(1 for c in derivado if not tiendas(c))
    if sin_tienda:
        print(f"  {'sin tienda':14s} {sin_tienda:4d}   ← dato ciego, sección 6 del manual")

    print("\n" + "=" * 70); print("ORIGEN"); print("=" * 70)
    ref = lambda c: (c.get("variables") or {}).get("referralSourceType")
    for b in "CBA":
        s = [c for c in canal if clasificar(c)[0] == b]
        if s:
            print(f"  bloque {b}: {sum(1 for c in s if ref(c)):4d} de {len(s):4d} vienen de pauta"
                  f" ({pct(sum(1 for c in s if ref(c)), len(s))})")
    print(f"  compras de pauta: {sum(1 for c in compro if ref(c))} de {len(compro)}")

    print("\n" + "=" * 70); print("POR DÍA"); print("=" * 70)
    for d in sorted({hora_peru(c).date() for c in canal}):
        s = [c for c in canal if hora_peru(c).date() == d]
        t = collections.Counter(clasificar(c)[0] for c in s)
        v = sum(1 for c in s if "CLIENTE COMPRO" in tags(c))
        print(f"  {d} {d.strftime('%a')}  total {len(s):4d}"
              f"   A {t.get('A', 0):3d}   B {t.get('B', 0):3d}   C {t.get('C', 0):3d}   compras {v}")


if __name__ == "__main__":
    main(dt.date.fromisoformat(sys.argv[1]), dt.date.fromisoformat(sys.argv[2]))
