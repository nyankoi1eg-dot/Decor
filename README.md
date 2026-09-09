# Decor — servidores MCP para sesiones remotas de Claude Code

Este repositorio configura servidores MCP para que estén disponibles de forma
permanente en las sesiones de Claude Code que corren en la nube, no solo en la
app de escritorio:

| Servidor | Qué da | Alcance actual |
|---|---|---|
| **`google-analytics`** | Datos de GA4 (paquete [`google-analytics-mcp`](https://pypi.org/project/google-analytics-mcp/), binario `ga4-mcp-server`) | Lectura de la propiedad de producción |
| **`gtm`** | Google Tag Manager ([`sprawz/gtm-mcp-server`](https://github.com/sprawz/gtm-mcp-server), auto-hospedado) | Solo lectura |

## Por qué hace falta esta configuración

Un servidor MCP de tipo `stdio` lo arranca **el cliente** como subproceso local.
El que ya tienes en *Ajustes → Desarrollador* vive en tu ordenador y solo habla con
la app de escritorio: una sesión remota corre en otra máquina y no lo alcanza.

Ninguno de los dos se resuelve copiando el comando y ya: cada uno choca con algo
propio del entorno remoto, y por eso hay un lanzador por servidor en
`.claude/mcp/`.

## Google Analytics 4 (servidor `google-analytics`)

Replicarlo aquí tiene dos obstáculos, y `.claude/mcp/ga4-launch.sh` existe para
resolverlos:

1. **La clave de servicio tiene que ser un fichero.** `ga4-mcp-server` exige que
   `GOOGLE_APPLICATION_CREDENTIALS` apunte a una ruta en disco y comprueba que
   exista. Un entorno remoto solo inyecta secretos como variables de entorno, y el
   contenedor se recicla, así que el lanzador reconstruye el JSON en `/tmp` con
   permisos `600` en cada arranque.
2. **La descarga del paquete se cuelga en IPv6.** En este entorno,
   `files.pythonhosted.org` está en `NO_PROXY`, así que `uv` sale en directo y se
   queda colgado (200 OK, 0 bytes, timeout). Forzando IPv4 o pasando por el proxy
   responde en ~0,1 s. El lanzador vacía `NO_PROXY` para devolver `uv` al proxy.

### Puesta en marcha

#### 1. En Google Cloud — ya hecho

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

#### 2. Codifica la clave en base64

El fichero JSON es multilínea y los formularios de variables de entorno esperan una
sola línea, así que se transporta en base64:

```bash
base64 -w0 ruta/a/tu-clave.json      # Linux
base64 -i ruta/a/tu-clave.json       # macOS
```

#### 3. Declara las variables en el entorno remoto

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

#### 4. Abre una sesión nueva

Los servidores MCP se registran al **arrancar** la sesión: la sesión en la que
añadas esto no verá el servidor, la siguiente sí.

### Verificación

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

### Herramientas que expone

Diez, sobre la GA4 Data API: `search_schema`, `get_property_schema`,
`list_dimension_categories`, `list_metric_categories`, `get_dimensions_by_category`,
`get_metrics_by_category`, `get_ga4_data`, `get_troubleshooting_guide`,
`search_skills` y `setup_ga4_access`.

El flujo recomendado por el propio servidor es descubrir antes de consultar: los
nombres de dimensiones y métricas de GA4 cambiaron respecto a Universal Analytics,
así que conviene pasar por `search_schema` en lugar de escribirlos de memoria.

### Notas

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

## Google Tag Manager (servidor `gtm`)

Se auto-hospeda [`sprawz/gtm-mcp-server`](https://github.com/sprawz/gtm-mcp-server)
(v1.12.3, Go, BSD-3) dentro de la propia sesión. Cubre 101 de los 106 métodos de
la API v2 de GTM y expone 66 herramientas.

### Por qué auto-hospedado y no el endpoint público

El proyecto ofrece un endpoint hospedado en `https://mcp.gtmeditor.com`. **No
sirve aquí**: la política de egress de este entorno lo bloquea (el proxy responde
`403` al CONNECT), así que una sesión remota no lo alcanza. Auto-hospedarlo
además evita que los tokens de Google pasen por un tercero.

Si algún día quieres usar el endpoint público desde la app de escritorio, funciona
sin nada de esto: `claude mcp add --transport http gtm https://mcp.gtmeditor.com`.

### Por qué un hook y no una entrada `stdio` en `.mcp.json`

Este servidor **solo habla Streamable HTTP**; el modo stdio está pendiente
(`TODO(stdio)` en su `main.go`). Un servidor HTTP no lo puede lanzar el cliente
MCP: tiene que estar ya escuchando cuando la sesión registra los servidores. Por
eso `.mcp.json` apunta a `http://127.0.0.1:8391/` y quien lo arranca es un hook
`SessionStart` **síncrono** (`.claude/hooks/session-start.sh` →
`.claude/mcp/gtm-launch.sh`). Síncrono a propósito: uno `async` no garantiza que
el puerto esté escuchando a tiempo.

El tráfico MCP no sale del contenedor — `127.0.0.1` está en `NO_PROXY` — y el
servidor solo escucha en loopback. Las llamadas que sí salen son las suyas a
`tagmanager.googleapis.com`, que el proxy sí permite.

### Puesta en marcha

#### 1. Crea la cuenta de servicio

Puedes reutilizar el proyecto `ga-claude-decorcenter` o usar otro. Crea una cuenta
de servicio **distinta de la de GA4** (así los permisos no se mezclan) y descarga
su clave JSON en *IAM → Cuentas de servicio → Claves*.

Habilita la **Tag Manager API** en el proyecto. No hace falta darle ningún rol de
IAM: el acceso se concede dentro de GTM, no en Google Cloud.

#### 2. Dale acceso de solo lectura en GTM

En **GTM → Administrar → Gestión de usuarios**, añade el `client_email` de la
cuenta de servicio con permiso de **Lectura** sobre la cuenta y el contenedor.

Sin este paso la API devuelve 403 aunque la clave sea válida — igual que pasa con
GA4.

#### 3. Declara las variables en el entorno remoto

| Variable | Valor |
|---|---|
| `GTM_SA_KEY_B64` | La clave JSON en base64 (`base64 -w0 clave.json`) |
| `GTM_MCP_API_KEY` | Una cadena larga y aleatoria que tú eliges (`openssl rand -base64 32`) |

`GTM_MCP_API_KEY` es un secreto compartido **local**: el servidor lo exige en
cada petición y `.mcp.json` lo envía en la cabecera `Authorization`. No es una
credencial de Google y no viaja a ningún sitio; existe para que el servidor no
quede abierto a cualquier proceso del contenedor.

El lanzador también acepta `GTM_SA_KEY_JSON` con el JSON en crudo, si tu entorno
admite valores multilínea.

#### 4. Abre una sesión nueva

Igual que con GA4: los servidores MCP se registran al **arrancar**.

La primera sesión tras definir las variables tarda más en abrir, porque el hook
clona y compila el servidor (Go descarga la toolchain 1.26 y los módulos). El
binario queda cacheado en `~/.cache/gtm-mcp-server/bin/`, así que las siguientes
arrancan en segundos.

### Verificación

```bash
GTM_MCP_API_KEY=... GTM_SA_KEY_B64=... ./.claude/mcp/gtm-launch.sh
```

Un arranque correcto imprime en `stderr`:

```
gtm-launch: servidor GTM escuchando en 127.0.0.1:8391 (v1.12.3)
```

Y el log en `~/.cache/gtm-mcp-server/server.log` debe decir `s2s_mode_enabled`
con `"credential_source":"key_json"`. Si dice `running open`, la clave no llegó.

Comprobado en este entorno: compilación de la v1.12.3, arranque en modo service
account, `401` sin cabecera y con clave incorrecta, `initialize` y `tools/list`
correctos con la clave buena (66 herramientas), y una llamada real a
`list_accounts` que llegó hasta Google. La validación se hizo con una clave
sintética, así que Google la rechazó con `invalid_grant: account not found`: eso
confirma que toda la cadena está bien conectada, pero **el camino con una clave
real y permisos en GTM todavía está sin ejercitar**.

### Alcance de los permisos

El acceso real lo fija el permiso que le des en GTM, no el servidor. Con
**Lectura**, las herramientas de escritura siguen apareciendo en la lista pero
Google las rechaza con 403.

Conviene saber que el servidor pide siempre los scopes de edición y publicación
(`tagmanager.edit.containers`, `tagmanager.publish`, …) porque son fijos en su
código. Un scope no concede nada por sí solo: el permiso de GTM es el que manda.
Para ampliar a edición o publicación más adelante basta con subir el permiso en
*GTM → Gestión de usuarios*; no hay que tocar nada de este repositorio.

Para reducir la superficie de herramientas puedes definir `GTM_TOOL_GROUPS` (por
ejemplo `accounts,workspaces,tags,triggers,variables`); el lanzador la pasa tal
cual.

### Notas

- **Versión fijada.** El lanzador clona la etiqueta `v1.12.3`, no `main`, para que
  una sesión no se lleve por delante un cambio del upstream. Se sube cambiando
  `GTM_MCP_VERSION`.
- **La clave nunca toca el disco.** A diferencia del lanzador de GA4, este servidor
  acepta el JSON por variable de entorno (`GOOGLE_SERVICE_ACCOUNT_KEY_JSON`), así
  que se le pasa directamente y no se materializa ningún fichero.
- **Es software de terceros, no de Google.** Recibe una clave con acceso a la
  configuración de tu tracking. Por eso usa una cuenta de servicio dedicada y
  empieza en solo lectura.
- **Rotación de claves.** Igual que con GA4: si la clave privada sale alguna vez
  de donde se generó, bórrala en *IAM → Claves* y genera otra. El `client_email`
  no cambia, así que el acceso concedido en GTM se mantiene.
- **Puerto.** `8391` por defecto, configurable con `GTM_MCP_PORT`. Si lo cambias,
  actualiza también la URL en `.mcp.json`.
