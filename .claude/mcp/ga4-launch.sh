#!/usr/bin/env bash
#
# Arranca el servidor MCP de Google Analytics 4 en un contenedor remoto efimero.
#
# Hace dos cosas que el comando `uvx` pelado no puede hacer aqui:
#
#   1. Materializa la clave de servicio. ga4-mcp-server exige que
#      GOOGLE_APPLICATION_CREDENTIALS apunte a un FICHERO en disco, pero un
#      contenedor remoto solo recibe secretos como variables de entorno. Se
#      escribe la clave a disco en el arranque, con permisos 600.
#
#   2. Enruta la descarga del paquete por el proxy. La salida directa a
#      files.pythonhosted.org se cuelga en IPv6 en este entorno; el proxy
#      resuelve por IPv4 y responde al instante.
#
set -euo pipefail

log() { printf 'ga4-launch: %s\n' "$1" >&2; }
die() { log "ERROR: $1"; exit 1; }

# --- 1. Credenciales -------------------------------------------------------
# Precedencia: un fichero ya montado gana; si no, se reconstruye desde el
# secreto de entorno (base64 preferido: cabe en una sola linea del formulario).
if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]]; then
  log "usando credenciales ya presentes en ${GOOGLE_APPLICATION_CREDENTIALS}"
else
  key_dir="${XDG_RUNTIME_DIR:-/tmp}/ga4-mcp"
  key_file="${key_dir}/service-account.json"
  mkdir -p "$key_dir"
  chmod 700 "$key_dir"

  if [[ -n "${GA4_SA_KEY_B64:-}" ]]; then
    ( umask 077; printf '%s' "${GA4_SA_KEY_B64}" | base64 -d > "$key_file" ) \
      || die "GA4_SA_KEY_B64 no es base64 valido"
  elif [[ -n "${GA4_SA_KEY_JSON:-}" ]]; then
    ( umask 077; printf '%s' "${GA4_SA_KEY_JSON}" > "$key_file" )
  else
    die "falta la clave de servicio: define GA4_SA_KEY_B64 (o GA4_SA_KEY_JSON) en las variables de entorno del entorno remoto"
  fi

  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("type")=="service_account" else 1)' \
    "$key_file" 2>/dev/null \
    || die "la clave descodificada no es un JSON de service account valido"

  export GOOGLE_APPLICATION_CREDENTIALS="$key_file"
  log "credenciales escritas en ${key_file}"
fi

[[ -n "${GA4_PROPERTY_ID:-}" ]] \
  || die "falta GA4_PROPERTY_ID (solo el numero de la propiedad GA4, sin el prefijo 'properties/')"

# --- 2. Red ----------------------------------------------------------------
# NO_PROXY lista files.pythonhosted.org, asi que uv iria en directo y se
# colgaria en IPv6. Vaciarlo lo devuelve al proxy, que si funciona.
if [[ -n "${HTTPS_PROXY:-}" ]]; then
  export NO_PROXY="" no_proxy=""
fi
# El paquete habla con googleapis.com a traves del mismo proxy, que
# re-termina TLS: sin este bundle, google-auth falla la verificacion.
if [[ -f /root/.ccr/ca-bundle.crt ]]; then
  export SSL_CERT_FILE="${SSL_CERT_FILE:-/root/.ccr/ca-bundle.crt}"
  export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-/root/.ccr/ca-bundle.crt}"
fi

# --- 3. Arranque -----------------------------------------------------------
# 'mcp<2' replica el pin de la config de escritorio: mcp 2.x rompe este server.
exec uvx --from google-analytics-mcp --with 'mcp<2' ga4-mcp-server "$@"
