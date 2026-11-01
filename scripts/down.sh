#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
# Chemins de Compose relatifs à la racine du dépôt : un chemin absolu avec des espaces serait coupé en plusieurs arguments.
cd "$REPO_ROOT"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  . "$REPO_ROOT/.env"
  set +a
fi

COMPOSE_ARGS="-f compose/docker-compose.yml"
if [ -n "${EXTRA_COMPOSE_FILE:-}" ]; then
  COMPOSE_ARGS="$COMPOSE_ARGS -f $EXTRA_COMPOSE_FILE"
fi

docker compose $COMPOSE_ARGS down --remove-orphans "$@"
