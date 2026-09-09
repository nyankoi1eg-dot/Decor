#!/usr/bin/env bash
# Arranca el servidor GTM MCP (sprawz/gtm-mcp-server) escuchando solo en
# 127.0.0.1, para que la entrada "gtm" de .mcp.json pueda conectarse.
#
# El servidor no habla stdio, solo Streamable HTTP, asi que no puede lanzarlo
# el cliente MCP: tiene que estar escuchando ANTES de que arranque la sesion.
# De eso se encarga el hook SessionStart sincrono que llama a este script.
#
# Es idempotente: si ya hay un servidor sano en el puerto, no hace nada.
set -euo pipefail

PIN="${GTM_MCP_VERSION:-v1.12.3}"
REPO_URL="https://github.com/sprawz/gtm-mcp-server"
PORT="${GTM_MCP_PORT:-8391}"
CACHE="${GTM_MCP_CACHE_DIR:-$HOME/.cache/gtm-mcp-server}"
SRC="$CACHE/src"
BIN="$CACHE/bin/gtm-mcp-server-$PIN"
LOG="$CACHE/server.log"

log() { printf 'gtm-launch: %s\n' "$*" >&2; }

# --- 1. Credenciales -------------------------------------------------------
# Sin ellas no arrancamos: mas vale no tener servidor que uno que responde
# pero falla en cada llamada. Salimos con 0 para no bloquear la sesion.
missing=()
[ -n "${GTM_MCP_API_KEY:-}" ] || missing+=("GTM_MCP_API_KEY")
[ -n "${GTM_SA_KEY_B64:-}${GTM_SA_KEY_JSON:-}" ] || missing+=("GTM_SA_KEY_B64")
if [ ${#missing[@]} -gt 0 ]; then
  log "falta ${missing[*]} en el entorno; no arranco el servidor GTM."
  log "definelas en los ajustes del entorno (ver README) y abre una sesion nueva."
  exit 0
fi

if [ -n "${GTM_SA_KEY_JSON:-}" ]; then
  SA_JSON="$GTM_SA_KEY_JSON"
else
  SA_JSON="$(printf '%s' "$GTM_SA_KEY_B64" | base64 -d 2>/dev/null)" || {
    log "GTM_SA_KEY_B64 no es base64 valido."; exit 0; }
fi
printf '%s' "$SA_JSON" | head -c 1 | grep -q '{' || {
  log "la clave decodificada no es JSON; revisa GTM_SA_KEY_B64."; exit 0; }

# --- 2. Si ya hay uno escuchando, no duplicamos ----------------------------
if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  log "ya hay algo escuchando en 127.0.0.1:$PORT; no arranco otro."
  exit 0
fi

# --- 3. Fuente fijada a una version ---------------------------------------
mkdir -p "$CACHE/bin"
if [ ! -d "$SRC/.git" ]; then
  log "clonando $REPO_URL ($PIN)..."
  rm -rf "$SRC"
  git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$PIN" "$REPO_URL" "$SRC"
elif [ "$(git -C "$SRC" describe --tags --exact-match 2>/dev/null || echo none)" != "$PIN" ]; then
  log "actualizando fuente a $PIN..."
  git -C "$SRC" fetch --quiet --depth 1 origin "refs/tags/$PIN:refs/tags/$PIN"
  git -C "$SRC" checkout --quiet "$PIN"
fi

# --- 4. Compilar (se cachea entre sesiones) --------------------------------
if [ ! -x "$BIN" ]; then
  command -v go >/dev/null || { log "no hay toolchain de Go; no puedo compilar."; exit 0; }
  log "compilando $PIN (solo la primera vez, puede tardar unos minutos)..."
  # go.mod pide Go 1.26; GOTOOLCHAIN=auto lo descarga si el local es menor.
  ( cd "$SRC" && GOTOOLCHAIN=auto go build -o "$BIN" . ) || {
    log "fallo la compilacion; mira la salida de arriba."; rm -f "$BIN"; exit 0; }
fi

# --- 5. Arrancar -----------------------------------------------------------
# La clave de servicio viaja por entorno, nunca toca el disco.
# El servidor solo escucha en loopback: no se expone fuera del contenedor.
cd "$SRC"
GTM_MCP_API_KEY="$GTM_MCP_API_KEY" SA_JSON="$SA_JSON" PORT="$PORT" BIN="$BIN" LOG="$LOG" \
setsid nohup env \
  PORT="$PORT" \
  BASE_URL="http://127.0.0.1:$PORT" \
  SERVICE_ACCOUNT_API_KEY="$GTM_MCP_API_KEY" \
  GOOGLE_SERVICE_ACCOUNT_KEY_JSON="$SA_JSON" \
  LOG_LEVEL="${GTM_MCP_LOG_LEVEL:-info}" \
  ${GTM_TOOL_GROUPS:+GTM_TOOL_GROUPS="$GTM_TOOL_GROUPS"} \
  "$BIN" >"$LOG" 2>&1 < /dev/null &
disown 2>/dev/null || true

# --- 6. Esperar a que escuche ---------------------------------------------
for _ in $(seq 1 40); do
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
    log "servidor GTM escuchando en 127.0.0.1:$PORT ($PIN)"
    exit 0
  fi
  sleep 0.25
done

log "el servidor no llego a escuchar en $PORT. Ultimas lineas de $LOG:"
tail -n 15 "$LOG" >&2 2>/dev/null || true
exit 0
