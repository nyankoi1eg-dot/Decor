# Canal Asesores Web — análisis de leads (Botmaker)

Estado al 15-sep-2026. **Leer esto antes de tocar nada.**

Reportes publicados:
- [Leads 1–10 sep](https://claude.ai/code/artifact/fcc35ab3-c51b-4e63-8a45-e3274a875293)
- [Cómo terminaron los chats · semana 7–13 sep](https://claude.ai/code/artifact/b3a108a0-94d9-4ff8-aa00-2a3d6feafc21)

## Para retomar

```bash
cd botmaker/asesores-web/scripts
python descargar.py 2026-09-07 2026-09-13 3    # 3 pasadas
python leer_mensajes.py 2026-09-07 2026-09-13  # deja mensajes.json
python reporte_semanal.py 2026-09-07 2026-09-13
```

## Credencial

La inyecta el agent proxy en la cabecera `access-token`, **sin prefijo**. Si el
prefijo tiene `Bearer`, la API responde 401 y el `Reason-Phrase` muestra el token
contaminado — comparar su longitud delata el problema (347 con prefijo, 340 sin él).

**No existe editar una credencial: se borra y se crea de nuevo.** Está en el
diálogo de edición del entorno (no el de creación), bajo *Environment variables*,
en la sección *API credentials*. Requiere plan Pro o Max y rol de owner.

Un 401 a mitad de trabajo **no significa que el token expiró**. El token en uso
tiene `exp` en 2031. El patrón observado —funciona, falla tras una ráfaga larga,
se recupera solo más tarde— es de límite de volumen. Por eso `leer_mensajes.py`
espacia las llamadas.

## Trampas de la API

- `GET /v2.0/chats` exige `long-term-search=true` junto con `from`/`to`, o da 400.
- **Paginación no determinística.** Dos recorridos completos devuelven conjuntos
  distintos. Hay que hacer varias pasadas y unir por `chatId`. Ninguna cifra de
  total es definitiva con una sola pasada.
- Filtrar por `lastSessionCreationTime`, nunca por `creationTime` (fecha de alta
  del contacto, llega hasta 2022).
- **Al deduplicar, conservar la copia más reciente.** Los tags se siguen agregando
  después de la conversación; quedarse con la primera copia leída deja datos viejos.
- Para leer mensajes el parámetro es **`chat-id`**. `chatId` se acepta sin error y
  **se ignora**, devolviendo el flujo global del período — 1500 mensajes idénticos
  para cualquier chat que se pida. Es un error silencioso y fácil de no notar.
- Perú es UTC−5 fijo.
- Descargar **después** de que cierre la semana, no durante: los tags siguen
  cambiando y la foto envejece.

## Alcance

- Denominador: todos los chats del período.
- Fuera del conteo: **cola SAC** (`queueId == "SAC"` o tag `Asesores_SAC`) y el
  **número retirado +51 993 313 227** (`channelId` `...51993313227`). Se reportan aparte.
- Los chats sin `queueId` **sí son** de Asesores Web.

## Clasificación

Tres bloques por cómo terminó el chat:

| | |
|---|---|
| **A** | Terminados por el bot, nunca entraron al funnel |
| **B** | No son leads comerciales (Eje 3 del manual) |
| **C** | Con intención de compra — y cómo terminó |

**La tipificación explica el cierre; cuando no lo explica, manda el tag de mayor
peso.** Los hechos que registra el gestor —una compra, una tienda asignada— pesan
más que cualquier etiqueta.

**Solo vale el vocabulario del manual.** Un tag o tipificación que no figure ahí
no clasifica.

**El eje de intención sale de la sección 5:** el botón «Realizar una compra»
dispara `CONTACTADO`, así que llevar ese tag es haber declarado intención.

### Dos equivalencias aplicadas

Sin ellas la derivación daría cero, porque ninguna existe con el nombre del manual:

- `DERIVADOS` se cuenta como `DERIVADOS_A_TIENDA`
- los tags `TDA*` se cuentan como la variable `U.TDA.*` de la sección 6

## Por qué hace falta leer los mensajes

**La API no devuelve todos los tags que muestra la consola.** Verificado sobre dos
chats que en pantalla llevan `TAG_LOCALIZAR_TIENDA` y por API sólo traen
`Asesores_Venta`. En 1842 chats ese tag aparece 2 veces y `DERIVADO_PERO_NO_COMPRO`
ninguna, cuando el manual lo lista como uno de los siete del funnel.

Leer los mensajes cambió dos bloques enteros:

- de 38 chats "terminados por el bot", **30 pedían comprar**
- de 228 abandonos sin motivo, **144 pedían comprar**

## `Lead_NO_calificado` — no usarla

Cubre el 71% de los cierres y **no está en el manual**. No significa "no quería
comprar": leyendo los mensajes de los 232 de una semana, **141 pedían comprar**.

La diferencia real con `Lead_Calificado` no es intención sino **derivación**:

| | No calificado | Calificado |
|---|---|---|
| `ABANDONO_DE_COMPRA` | 98% | 4% |
| `DERIVADOS` | 0% | 88% |
| Tag de tienda | 0% | 97% |

La aplican 3 operadores reales, 232 veces por semana. El canal dice no usarla.

## Resultados · semana 7–13 sep

Cifras completas en `datos/resultados-2026-09-07_13.json`.

516 recuperados = 467 Asesores Web + 26 SAC + 23 número antiguo. **Cuadra.**

| Bloque | n | % |
|---|---|---|
| C · Con intención de compra | 373 | 79.9% |
| B · No comerciales | 87 | 18.6% |
| A · Terminados por el bot | 7 | 1.5% |

**Embudo:** 467 ingresaron → 406 `CONTACTADO` (86.9%) → *atención: ciego* →
106 derivados (26.1%) → **11 compras** (10.4%). Conversión total 2.36%.

**El hallazgo:** 171 chats pidieron comprar y se perdieron sin motivo registrado
ni derivación. No es un problema de calidad de lead, es de atención.

**Pauta:** 49% del bloque C viene de anuncio, y **ninguna de las 11 compras**.
Dos períodos seguidos con el mismo resultado.

## Datos ciegos

- `EN_ATENCIÓN`, `RECOMPRA` y `DERIVADO_PERO_NO_COMPRO`: **cero usos**. Dos de las
  seis tasas de la sección 9 no se pueden calcular, y el tramo contacto→derivación
  —donde se pierden 300 leads— no se puede diagnosticar.
- Las variables `U.TDA.*` no existen; las tiendas son tags.
- `UTDACORPORATIVO` no está en la sección 6 del manual.
- 86 de 493 chats no devuelven ni un mensaje del cliente pese a tener `CONTACTADO`.
- `PENDIENTE DE COMPRA` (95 usos) describe una etapa real que el manual no
  contempla. Si el equipo lo usa para marcar leads vivos, conviene incorporarlo.

## Preguntas abiertas

1. **¿Por qué la API no devuelve todos los tags?** Mientras siga así, cualquier
   clasificación basada solo en tags está subestimada.
2. **`NOPRODUCTO` es ambiguo** — ¿"sin stock" o "no existe"? Cambia el hallazgo
   de catálogo.
3. **El pico de jueves a domingo.** De los chats sin atender, 31 de 32 caen ahí.
   ¿Caída del bot, cola sin cubrir, o gestores sin cobertura de fin de semana?

## Nota sobre los datos

Este directorio guarda **solo cifras agregadas y scripts**. Los chats crudos y los
mensajes incluyen teléfonos y nombres de clientes y no se versionan: se vuelven a
descargar. El `.gitignore` cubre `raw_*.json` y `mensajes.json`.
