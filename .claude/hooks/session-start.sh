#!/usr/bin/env bash
# Hook SessionStart sincrono.
#
# Sincrono a proposito: el servidor GTM MCP habla Streamable HTTP, no stdio,
# asi que tiene que estar ESCUCHANDO antes de que el cliente registre los
# servidores MCP. Un hook async no lo garantiza.
#
# Todo va a stderr: stdout esta reservado para el protocolo de hooks.
set -euo pipefail

DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

if [ -x "$DIR/.claude/mcp/gtm-launch.sh" ]; then
  # Nunca tumbamos el arranque de la sesion por esto.
  "$DIR/.claude/mcp/gtm-launch.sh" || true
fi

exit 0
