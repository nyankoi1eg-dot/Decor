"""Arma `reporte-botmaker.html`: un único archivo que funciona con doble clic.

Inlina los estilos y los scripts de `botmaker_bi/web/` y cambia la capa de
datos por la que habla con Botmaker directamente desde el navegador, de modo
que no haga falta ni Python ni servidor. El dibujo de los gráficos es el mismo
archivo `render.js` que usa la versión servida: hay una sola copia.

    python construir_archivo_suelto.py [destino.html]
"""
from __future__ import annotations

import pathlib
import re
import sys

WEB = pathlib.Path(__file__).parent / "botmaker_bi" / "web"


def construir() -> str:
    html = (WEB / "index.html").read_text(encoding="utf-8")

    # La clave del servicio sólo aplica a la versión servida.
    html = re.sub(r"\n    <details>.*?</details>\n", "\n", html, flags=re.S)

    html = html.replace(
        "El token no se guarda en el servidor: viaja sólo en esta petición.",
        "Todo ocurre en tu navegador: el token viaja directo a Botmaker.",
    )
    html = html.replace(
        "<title>Reporte de embudo conversacional — Decor Center</title>",
        "<title>Reporte de embudo conversacional — Decor Center</title>\n"
        "<!-- Archivo autónomo: no requiere instalar nada. Se abre con doble clic. -->",
    )

    scripts = "\n".join(
        f"<script>\n{(WEB / n).read_text(encoding='utf-8')}\n</script>"
        for n in ("render.js", "api-botmaker.js", "ui.js")
    )
    # El reemplazo va como lambda: el JS lleva barras invertidas que re.sub
    # interpretaria como escapes de plantilla.
    html = re.sub(
        r'<script src="render\.js"></script>\s*'
        r'<script src="api-servidor\.js"></script>\s*'
        r'<script src="ui\.js"></script>',
        lambda _: scripts,
        html,
    )
    if "<script src=" in html:
        raise SystemExit("Quedaron scripts externos sin inlinar")
    return html


if __name__ == "__main__":
    destino = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "reporte-botmaker.html")
    destino.write_text(construir(), encoding="utf-8")
    print(f"{destino} — {destino.stat().st_size // 1024} KB")
