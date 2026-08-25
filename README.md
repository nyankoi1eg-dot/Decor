# Decor — acceso a Google Analytics 4 desde sesiones remotas

Este repositorio configura el servidor MCP **`google-analytics`** (paquete
[`google-analytics-mcp`](https://pypi.org/project/google-analytics-mcp/), binario
`ga4-mcp-server`) para que esté disponible de forma permanente en las sesiones de
Claude Code que corren en la nube, no solo en la app de escritorio.

## Por qué hace falta esta configuración

Un servidor MCP de tipo `stdio` lo arranca **el cliente** como subproceso local.
El que ya tienes en *Ajustes → Desarrollador* vive en tu ordenador y solo habla con
la app de escritorio: una sesión remota corre en otra máquina y no lo alcanza.

Replicarlo aquí no es copiar el comando y ya. Hay dos obstáculos propios del
entorno remoto, y `.claude/mcp/ga4-launch.sh` existe para resolverlos:

1. **La clave de servicio tiene que ser un fichero.** `ga4-mcp-server` exige que
   `GOOGLE_APPLICATION_CREDENTIALS` apunte a una ruta en disco y comprueba que
   exista. Un entorno remoto solo inyecta secretos como variables de entorno, y el
   contenedor se recicla, así que el lanzador reconstruye el JSON en `/tmp` con
   permisos `600` en cada arranque.
2. **La descarga del paquete se cuelga en IPv6.** En este entorno,
   `files.pythonhosted.org` está en `NO_PROXY`, así que `uv` sale en directo y se
   queda colgado (200 OK, 0 bytes, timeout). Forzando IPv4 o pasando por el proxy
   responde en ~0,1 s. El lanzador vacía `NO_PROXY` para devolver `uv` al proxy.

## Puesta en marcha

### 1. En Google Cloud — ya hecho

La parte de Google está montada y verificada contra la API:

| | |
|---|---|
| Proyecto GCP | `ga-claude-decorcenter` |
| Cuenta de servicio | `claude-mcp@ga-claude-decorcenter.iam.gserviceaccount.com` |
| Cuenta GA4 | DECOR CENTER (`accounts/41077253`) |
| Propiedad | Decorcenter - Producción |
| `GA4_PROPERTY_ID` | `276921254` |

La cuenta de servicio ya figura con acceso de lectura en la propiedad, y tanto la
Analytics Data API como la Admin API responden.

Si algún día hay que rehacerlo desde cero: habilita la **Google Analytics Data
API** en el proyecto, crea la cuenta de servicio con clave JSON (*IAM → Cuentas de
servicio → Claves*), y añade su email en **GA4 → Administrar → Gestión de accesos a
la propiedad** con rol **Lector**. Sin ese último paso la API devuelve 403 aunque
la clave sea válida.

### 2. Codifica la clave en base64

El fichero JSON es multilínea y los formularios de variables de entorno esperan una
sola línea, así que se transporta en base64:

```bash
base64 -w0 ruta/a/tu-clave.json      # Linux
base64 -i ruta/a/tu-clave.json       # macOS
```

### 3. Declara las variables en el entorno remoto

En los ajustes del entorno de Claude Code en la web
([documentación](https://code.claude.com/docs/en/claude-code-on-the-web)), añade:

| Variable | Valor |
|---|---|
| `GA4_PROPERTY_ID` | `276921254` |
| `GA4_SA_KEY_B64` | La cadena base64 del paso 2 |

El lanzador también acepta `GA4_SA_KEY_JSON` con el JSON en crudo, si tu entorno
admite valores multilínea, y respeta un `GOOGLE_APPLICATION_CREDENTIALS` que ya
apunte a un fichero existente (útil en local).

**La clave nunca se commitea.** `.gitignore` bloquea los nombres habituales de
fichero de credenciales, y el secreto viaja solo como variable de entorno.

### 4. Abre una sesión nueva

Los servidores MCP se registran al **arrancar** la sesión: la sesión en la que
añadas esto no verá el servidor, la siguiente sí.

## Verificación

Con las variables ya definidas, desde una sesión remota:

```bash
bash .claude/mcp/ga4-launch.sh </dev/null
```

Un arranque correcto imprime en `stderr`:

```
ga4-launch: credenciales escritas en /tmp/ga4-mcp/service-account.json
Starting GA4 MCP server...
Fetching schema for property '276921254'...
Schema loaded successfully.
```

El montaje se validó completo por stdio: `initialize`, carga de esquema y una
llamada real a `get_ga4_data` (usuarios activos y sesiones de los últimos 7 días)
que devolvió datos de la propiedad.

Si algo falta, el lanzador falla rápido y dice cuál de las dos variables es.

## Herramientas que expone

Diez, sobre la GA4 Data API: `search_schema`, `get_property_schema`,
`list_dimension_categories`, `list_metric_categories`, `get_dimensions_by_category`,
`get_metrics_by_category`, `get_ga4_data`, `get_troubleshooting_guide`,
`search_skills` y `setup_ga4_access`.

El flujo recomendado por el propio servidor es descubrir antes de consultar: los
nombres de dimensiones y métricas de GA4 cambiaron respecto a Universal Analytics,
así que conviene pasar por `search_schema` en lugar de escribirlos de memoria.

## Notas

- **Versión de `mcp` fijada.** Se arranca con `--with 'mcp<2'`, igual que la
  configuración de escritorio: el servidor no es compatible con `mcp` 2.x.
- **Telemetría desactivada.** El paquete envía eventos de uso a un endpoint de
  terceros (`ga4.builditwithai.xyz`) por defecto; `.mcp.json` fija
  `GA_MCP_TELEMETRY=false`.
- **Es software de terceros, no de Google.** Recibe una clave con acceso de lectura
  a los datos de analítica. Por eso usa una cuenta de servicio dedicada
  (`claude-mcp@...`), limitada a rol Lector y solo a la propiedad que necesita.
- **Rotación de claves.** Si una clave privada sale alguna vez del sitio donde se
  generó (se sube a un chat, se pega en un ticket, se manda por correo), deja de
  ser secreta: bórrala en *IAM → Cuentas de servicio → Claves* y genera otra. El
  `client_email` no cambia, así que el acceso concedido en GA4 se mantiene y solo
  hay que actualizar `GA4_SA_KEY_B64`.
