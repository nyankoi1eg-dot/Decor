"""Lee lo que el cliente escribió, para clasificar lo que los tags no explican.

Por qué hace falta: la API no devuelve todos los tags que muestra la consola de
Botmaker. Verificado sobre dos chats que en pantalla llevan TAG_LOCALIZAR_TIENDA
y por API sólo traen Asesores_Venta. En 1842 chats descargados ese tag aparece
2 veces y DERIVADO_PERO_NO_COMPRO ninguna, cuando el manual lo lista como uno
de los siete tags del funnel. Esas frecuencias no son creíbles.

Los mensajes sí son fiables, y resolvieron dos bloques enteros:
  · de 38 chats "terminados por el bot", 30 pedían comprar
  · de 228 abandonos sin motivo, 144 pedían comprar

Uso:
    python leer_mensajes.py 2026-09-07 2026-09-13   # deja mensajes.json
"""
import datetime as dt
import json
import re
import subprocess
import sys
import time

from botmaker_lib import (NUMERO_ANTIGUO, cargar_union, del_periodo,
                          es_sac, mensajes_url)

# Espaciado entre llamadas. Una ráfaga de ~500 seguidas terminó en 401
# sostenido; el token no había expirado (su exp es de 2031).
PAUSA = 0.15

UBICACION = re.compile(
    r"ubicaci[oó]n|direcci[oó]n|hasta qu[eé] hora|qu[eé] hora (atienden|abren|cierran)"
    r"|d[oó]nde queda|d[oó]nde est[aá]n|sucursal|c[oó]mo llego", re.I)
POSTVENTA = re.compile(
    r"pedido programado|mi pedido|#\d{9,}|despacho|garant[ií]a|devoluci[oó]n"
    r"|reclamo|factura|boleta", re.I)
COMPRA = re.compile(
    r"gestor de ventas|realizar una compra|compr|precio|cu[aá]nto|cotiz|m2|m²|metro"
    r"|cat[aá]logo|interesad|busco|necesito|quisiera|quiero|tienen|stock|modelo|color"
    r"|medida|instalaci|env[ií]o|delivery|porcelanato|piso|pared|ba[nñ]o|cocina"
    r"|wallpanel|fachaleta|ducha|lavamanos|may[oó]lica|cer[aá]mic|grifer[ií]a", re.I)


def descargar(chats, desde, hasta, salida="mensajes.json"):
    out, total = {}, len(chats)
    for i, chat in enumerate(chats, 1):
        cid = chat["chat"]["chatId"]
        try:
            r = subprocess.run(["curl", "-s", "--max-time", "20",
                                mensajes_url(cid, desde, hasta)],
                               capture_output=True, text=True)
            items = json.loads(r.stdout).get("items", [])
        except Exception:
            items = []
        del_usuario = [(m.get("content", {}).get("text")
                        or m.get("content", {}).get("type") or "")
                       for m in items if m.get("from") == "user"]
        out[cid] = {"n": len(items), "nu": len(del_usuario),
                    "txt": " | ".join(x[:80] for x in del_usuario[:8])}
        if i % 100 == 0:
            print(f"  {i}/{total}", flush=True)
            json.dump(out, open(salida, "w", encoding="utf-8"), ensure_ascii=False)
        time.sleep(PAUSA)
    json.dump(out, open(salida, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def que_pidio(registro):
    """Clasifica un chat por lo que escribió el cliente."""
    if not registro or not registro.get("nu"):
        return "vacio"
    texto = registro.get("txt") or ""
    if POSTVENTA.search(texto):
        return "postventa"
    if UBICACION.search(texto) and not COMPRA.search(texto):
        return "ubicacion"
    if COMPRA.search(texto):
        return "compra"
    return "ambiguo"


if __name__ == "__main__":
    desde = dt.date.fromisoformat(sys.argv[1])
    hasta = dt.date.fromisoformat(sys.argv[2])
    periodo = del_periodo(cargar_union(), desde, hasta)
    chats = [c for c in periodo.values()
             if c["chat"].get("channelId") != NUMERO_ANTIGUO and not es_sac(c)]
    print(f"leyendo mensajes de {len(chats)} chats", flush=True)
    r = descargar(chats, f"{desde}T00:00:00.000Z",
                  f"{hasta + dt.timedelta(days=1)}T05:00:00.000Z")
    print("listo:", len(r))
