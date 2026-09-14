# Embudo conversacional Botmaker → SQL Server / Power BI

Extrae de Botmaker cuántas personas entran al chat, cuántas llegan a atención
humana, cuántas son atendidas y cuántas terminan derivadas a una tienda, con el
porcentaje de conversión entre etapas.

Se expone de tres formas, pensadas para convivir:

* **App web** (`botmaker_bi/web/`) — pide el token y el rango de fechas, y arma
  el reporte en pantalla. Es la vía para quien no toca SQL ni Power BI.
* **Endpoint REST** (`botmaker_bi/api.py`) — consulta directa desde Power BI.
* **Cargador incremental** (`botmaker_bi/cli.py` + `sql/`) — persiste en SQL
  Server con `MERGE` idempotente.

## Por qué las dos vías, y cuál usar

La documentación de Botmaker advierte que `/sessions` **suma consumo a las
"BI data sources"** de la cuenta, y más todavía con `include-events` e
`include-variables` (que aquí hacen falta para reconstruir el embudo).

Por eso la vía recomendada para producción es **cargar a SQL Server una vez al
día y apuntar Power BI contra la base**, no contra Botmaker. El endpoint REST
sirve para exploración, para un refresco puntual o para equipos que no tienen
SQL Server en medio. Si se conecta Power BI directo al endpoint, conviene dejar
el refresco en 1–2 veces por día.

## Definición de las etapas

Las etapas son **anidadas**: cada una exige haber pasado la anterior. Sin eso los
porcentajes pasan de 100 % (hay chats que un asesor toma sin que pasen por cola).

| Etapa | Cómo se detecta |
|---|---|
| **Ingresó al chat** | Existe la sesión (`/sessions`). |
| **Pasó a cola** | Evento `queue-set` **o** `assigned-to-agent`. |
| **Atendido** | Evento `assigned-to-agent` (un asesor la tomó). |
| **Derivado a tienda** | Tipificación `Lead_Calificado` / `CORPORATIVO-LEAD-DERIVADO`, o tag `DERIVADOS`, o cualquier tag `TDA*`. |

El prefijo `TDA*` identifica la tienda concreta (`TDAMOLINA`, `TDASALAVERRY`,
…), así que el corte por punto de venta sale gratis.

### Sobre "el tag de atendido"

En la cuenta conviven tres señales distintas y **no son equivalentes**:

| Señal | Qué es | Semana 07–13 sep 2026 |
|---|---|---|
| Evento `assigned-to-agent` | Un asesor tomó la conversación | 491 |
| Tag `CONTACTADO` | Marca manual del equipo | 515 |
| Tipificación `CONSULTA ATENDIDA` (+ variante SAC) | Cierre tipificado | 43 |

Este proyecto usa **el evento** como definición de "atendido", porque es el único
que Botmaker registra a nivel de sesión y con fecha propia. Las otras dos viven
a nivel de *chat* y guardan el estado actual, no el del momento de la sesión: si
un cliente vuelve a escribir la semana siguiente, sus tags de hoy se verían
reflejados también en la sesión vieja.

Si el negocio prefiere otra definición, se cambia en `funnel.py`
(`MapeoEtapas`) sin tocar el resto.

## Puesta en marcha

```bash
pip install -r requirements.txt
cp .env.example .env    # completar BOTMAKER_ACCESS_TOKEN y BI_API_KEY
```

El token se genera en Botmaker → *Integraciones → API*, y viaja en el header
`access-token`.

### Ver el embudo por consola

```bash
python -m botmaker_bi.cli tabla --desde 2026-09-07 --hasta 2026-09-13
```

Sin `--desde/--hasta` toma la semana pasada completa (lunes a domingo).

### Levantar la app y el endpoint

```bash
uvicorn botmaker_bi.api:app --host 0.0.0.0 --port 8080
```

Abriendo `http://localhost:8080/` aparece la app: un campo para el token, el
rango de fechas (con atajos de semana pasada / últimos 7 y 30 días / mes
actual) y el botón que arma el reporte —número de conversión global, tarjetas
de cada etapa, embudo, evolución diaria, tabla y derivaciones por tienda, con
descarga a CSV.

El token **no se guarda en el servidor**: viaja en el header
`X-Botmaker-Token` de esa petición y se usa para llamar a Botmaker. En el
navegador sólo se guarda si se marca "recordar", y en `sessionStorage`, que
muere al cerrar la pestaña. Así cada persona usa su propio token sin que el
servicio almacene credenciales de nadie.

Si en cambio se define `BOTMAKER_ACCESS_TOKEN` en el servidor, el campo puede
quedar vacío y se usa ese token para todas las consultas.

| Ruta | Devuelve |
|---|---|
| `GET /` | La app web. |
| `GET /funnel/daily` | Una fila por día (grano del dashboard). |
| `GET /funnel/daily.csv` | Lo mismo en CSV. |
| `GET /funnel/sessions` | Una fila por sesión (detalle). |
| `GET /funnel/summary` | Totales + corte por tienda + serie diaria. |
| `GET /health` | Chequeo de vida. |

Todas las rutas `/funnel/*` aceptan `?desde=YYYY-MM-DD&hasta=YYYY-MM-DD` en
fecha **local** (por defecto, la semana pasada), toman el token en
`X-Botmaker-Token` y exigen además el header `X-API-Key` si `BI_API_KEY` está
definida. La documentación interactiva queda en `/docs`.

Los gráficos son SVG generados en el navegador, sin librerías externas ni CDN.
La paleta está validada para daltonismo y modo oscuro, y todo valor graficado
aparece también en la tabla.

### Conectar Power BI

*Obtener datos → Web → Avanzadas*:

* URL: `https://TU-HOST/funnel/daily?desde=2026-09-07&hasta=2026-09-13`
* Encabezados: `X-Botmaker-Token` con el token de Botmaker y, si el servidor la
  exige, `X-API-Key` con el valor de `BI_API_KEY`

La respuesta es una lista JSON plana, sin envoltorio, para que el conector la
reconozca como tabla sin pasos de transformación extra.

### Cargar a SQL Server

```bash
sqlcmd -S HOST -d BI -i sql/01_schema.sql
sqlcmd -S HOST -d BI -i sql/02_vistas_powerbi.sql

export MSSQL_CONN="Driver={ODBC Driver 18 for SQL Server};Server=tcp:HOST,1433;Database=BI;UID=...;PWD=...;Encrypt=yes"
python -m botmaker_bi.cli cargar --desde 2026-09-07 --hasta 2026-09-13
```

Se persiste sólo el grano de sesión (`dbo.botmaker_sesion`); los agregados son
vistas (`vw_botmaker_embudo_diario`, `vw_botmaker_derivacion_tienda`,
`vw_botmaker_embudo_cola`), de modo que detalle y agregado no pueden quedar
desincronizados.

La carga es idempotente: reprocesar un rango ya cargado actualiza en lugar de
duplicar. Eso importa porque las sesiones abiertas cambian de estado después de
la primera lectura, así que conviene **reprocesar los últimos 2–3 días** en cada
corrida, no sólo el día anterior:

```cron
30 6 * * * cd /opt/botmaker-bi && python -m botmaker_bi.cli cargar \
  --desde $(date -d '3 days ago' +\%F) --hasta $(date -d 'yesterday' +\%F)
```

## Detalles de la API de Botmaker que conviene conocer

* Las fechas deben ir en **UTC con sufijo `Z`**. Un desplazamiento tipo
  `-05:00` devuelve `HTTP 400`.
* `creationTime` viene en UTC. Agrupar por día sin convertir a hora de Lima
  (UTC−5) manda al día siguiente todo lo ocurrido después de las 19:00.
  Se controla con `BI_TIMEZONE_OFFSET`.
* Un período sin registros responde **`HTTP 204` sin cuerpo**, no un JSON vacío.
* Para consultar más allá de los **últimos 7 días** hace falta
  `long-term-search=true`; se activa solo.
* La paginación viene en `nextPage` como URL absoluta y ya lleva los parámetros.
