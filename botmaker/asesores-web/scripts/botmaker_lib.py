"""Utilidades comunes para el análisis del canal Asesores Web (Botmaker)."""
import datetime as dt
import glob
import json
import re
import unicodedata

# Línea vigente del canal y número retirado (sección 8 del manual).
CANAL_VIGENTE = "decorcenter-whatsapp-51986647563"
NUMERO_ANTIGUO = "decorcenter-whatsapp-51993313227"

# Perú no aplica horario de verano: el offset es fijo.
TZ_PERU = dt.timedelta(hours=-5)


def parse_ts(s):
    """La API mezcla timestamps con y sin fracción de segundo."""
    s = s.replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise ValueError(f"timestamp no reconocido: {s!r}")


def hora_peru(chat):
    """Fecha de la conversación en hora local.

    Se usa lastSessionCreationTime, no creationTime: este último es la fecha de
    alta del contacto y llega hasta 2022 para clientes que ya habían escrito.
    """
    return parse_ts(chat["lastSessionCreationTime"]) + TZ_PERU


def normalizar(s):
    """Quita acentos y unifica separadores para comparar etiquetas."""
    if s is None:
        return None
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[\s_\-]+", " ", s).strip().upper()


def cargar_union(patron="raw_*.json"):
    """Une varias descargas en un solo conjunto, deduplicando por chatId.

    La paginación de la API no es determinística: dos recorridos completos e
    independientes devuelven conjuntos distintos. Por eso se descarga varias
    veces y se toma la unión.

    Ante duplicados se conserva la versión MÁS RECIENTE de cada chat. Los tags
    y la tipificación se siguen agregando después de la conversación, así que
    quedarse con la primera copia leída deja datos viejos.
    """
    union = {}
    for archivo in sorted(glob.glob(patron)):
        for chat in json.load(open(archivo, encoding="utf-8")):
            cid = chat["chat"]["chatId"]
            previo = union.get(cid)
            if previo is None or (parse_ts(chat["lastSessionCreationTime"])
                                  >= parse_ts(previo["lastSessionCreationTime"])):
                union[cid] = chat
    return union


def del_periodo(chats, desde, hasta):
    """Filtra por fecha local, ambos extremos incluidos."""
    return {
        cid: c for cid, c in chats.items()
        if desde <= hora_peru(c).date() <= hasta
    }


def tipificacion(chat):
    return (chat.get("variables") or {}).get("typification")


def etiquetas(chat):
    return chat.get("tags") or []


def etiquetas_norm(chat):
    return {normalizar(t) for t in etiquetas(chat)}


def tiendas(chat):
    """Las tiendas son tags con prefijo TDA/UTDA, no variables U.TDA.*."""
    return [t for t in etiquetas(chat) if t.upper().startswith(("TDA", "UTDA"))]


def es_sac(chat):
    """Tráfico de postventa: no pertenece al canal Asesores Web."""
    return chat.get("queueId") == "SAC" or "Asesores_SAC" in etiquetas(chat)


def mensajes_url(chat_id, desde, hasta):
    """URL para leer los mensajes de UN chat.

    El parámetro es `chat-id`. `chatId` se acepta sin error pero se ignora, y
    la respuesta trae el flujo global de mensajes del período — 1500 mensajes
    de cientos de chats distintos, idénticos para cualquier chat que se pida.
    """
    import urllib.parse
    q = urllib.parse.urlencode({"chat-id": chat_id, "long-term-search": "true",
                                "from": desde, "to": hasta})
    return f"https://api.botmaker.com/v2.0/messages?{q}"
