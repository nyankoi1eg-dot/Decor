"""Cliente HTTP de la API 2.0 de Botmaker, con paginacion y reintentos."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.botmaker.com/v2.0"
RETRY_STATUS = {429, 500, 502, 503, 504}


class BotmakerError(RuntimeError):
    pass


class BotmakerClient:
    """Envoltorio minimo sobre los endpoints de Botmaker que alimentan el embudo.

    El token se toma de ``BOTMAKER_ACCESS_TOKEN`` salvo que se pase explicito.
    """

    def __init__(
        self,
        access_token: str | None = None,
        base_url: str = BASE_URL,
        timeout: int = 120,
        max_retries: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        token = access_token or os.environ.get("BOTMAKER_ACCESS_TOKEN")
        if token:
            self.session.headers["access-token"] = token
        self.session.headers["Accept"] = "application/json"

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        delay = 2.0
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:  # red caida, DNS, timeout
                last_exc = exc
            else:
                if resp.status_code not in RETRY_STATUS:
                    return resp
                last_exc = BotmakerError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            if attempt < self.max_retries:
                log.warning("Reintentando %s (intento %s): %s", url, attempt + 1, last_exc)
                time.sleep(delay)
                delay *= 2
        raise BotmakerError(f"Fallo tras {self.max_retries} reintentos: {last_exc}")

    def _get_page(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._request("GET", url, params=params)
        # La API responde 204 sin cuerpo cuando el periodo no tiene registros.
        if resp.status_code == 204 or not resp.content:
            return {"items": [], "nextPage": None}
        if resp.status_code != 200:
            raise BotmakerError(f"HTTP {resp.status_code} en {url}: {resp.text[:300]}")
        return resp.json()

    def _paginate(self, path: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Recorre todas las paginas. ``nextPage`` ya viene como URL absoluta."""
        page = self._get_page(f"{self.base_url}{path}", params)
        yield from page.get("items") or []
        seen = 0
        while page.get("nextPage"):
            seen += 1
            if seen > 500:  # cortafuegos ante un nextPage que no avanza
                log.error("Se corto la paginacion de %s tras 500 paginas", path)
                break
            page = self._get_page(page["nextPage"])
            yield from page.get("items") or []

    def iter_sessions(
        self,
        frm: str,
        to: str,
        include_events: bool = True,
        include_variables: bool = True,
        include_open: bool = True,
        long_term: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Sesiones iniciadas en [frm, to).

        Las fechas deben ir en UTC con formato ``YYYY-MM-DDThh:mm:ssZ``; la API
        rechaza desplazamientos tipo ``-05:00``.

        Ojo: este endpoint consume cuota de "BI data sources" en Botmaker, y
        mas aun con los include_*. Persiste el resultado en vez de repetir la
        misma ventana (ver ``cli.py``).
        """
        params: dict[str, Any] = {
            "from": frm,
            "to": to,
            "include-events": str(include_events).lower(),
            "include-variables": str(include_variables).lower(),
            "include-open-sessions": str(include_open).lower(),
        }
        if long_term:  # obligatorio para consultar mas alla de los ultimos 7 dias
            params["long-term-search"] = "true"
        yield from self._paginate("/sessions", params)

    def list_typifications(self) -> list[dict[str, Any]]:
        return self._get_page(f"{self.base_url}/typifications").get("typifications") or []

    def list_queues(self) -> list[dict[str, Any]]:
        return list(self._paginate("/attention-queues", {}))
