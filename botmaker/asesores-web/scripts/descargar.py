"""Descarga los chats del período desde la API de Botmaker.

Uso:
    python descargar.py 2026-09-01 2026-09-10 [pasadas]

La credencial la inyecta el proxy del entorno en la cabecera `access-token`
(campo Prefijo vacío). No hay que pasarla por línea de comandos ni por código.

Se hacen varias pasadas completas porque la paginación no es determinística;
el resultado son archivos raw_rN.json que clasificar.py une y deduplica.
"""
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.parse

BASE = "https://api.botmaker.com/v2.0/chats"
MAX_PAGINAS = 500


def get(url, reintentos=5):
    for intento in range(reintentos):
        p = subprocess.run(["curl", "-s", "-w", "\n%{http_code}", url],
                           capture_output=True, text=True)
        cuerpo, _, codigo = p.stdout.rpartition("\n")
        if codigo.strip() == "200":
            return json.loads(cuerpo)
        sys.stderr.write(f"  HTTP {codigo.strip()} — reintento {intento + 1}\n")
        if codigo.strip() == "401":
            sys.exit("401: la credencial expiró o el Prefijo no está vacío. "
                     "Corregir en Ajustes del entorno → Credenciales de API.")
        time.sleep(2 * (intento + 1))
    sys.exit(f"no se pudo descargar: {url[:120]}")


def descargar(desde, hasta, salida):
    """Ventana en UTC, deliberadamente más amplia que el período local."""
    params = {"long-term-search": "true",
              "from": f"{desde}T00:00:00.000Z",
              "to": f"{hasta}T00:00:00.000Z"}
    url = BASE + "?" + urllib.parse.urlencode(params)
    chats, vistos, pagina = [], set(), 0
    while url and pagina < MAX_PAGINAS:
        data = get(url)
        pagina += 1
        for c in data.get("items", []):
            cid = c["chat"]["chatId"]
            if cid not in vistos:
                vistos.add(cid)
                chats.append(c)
        url = data.get("nextPage")
    json.dump(chats, open(salida, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  {salida}: {len(chats)} chats en {pagina} páginas")
    return len(chats)


if __name__ == "__main__":
    desde_local = dt.date.fromisoformat(sys.argv[1])
    hasta_local = dt.date.fromisoformat(sys.argv[2])
    pasadas = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    # Margen a ambos lados: el período local en UTC-5 se corre respecto de UTC,
    # y el filtro de la API no cae exactamente sobre lastSessionCreationTime.
    desde = desde_local - dt.timedelta(days=2)
    hasta = hasta_local + dt.timedelta(days=2)
    print(f"ventana UTC {desde} → {hasta}  ({pasadas} pasadas)")
    for i in range(1, pasadas + 1):
        descargar(desde, hasta, f"raw_r{i}.json")
    print("listo. ahora: python clasificar.py")
