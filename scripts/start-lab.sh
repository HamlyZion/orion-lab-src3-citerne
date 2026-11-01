#!/usr/bin/env sh
set -eu

LAB="${1:-}"
case "$LAB" in
  lab1a|lab1b|lab2a|lab2b|lab3|lab4a|lab4b) ;;
  *)
    echo "Usage : $0 <lab1a|lab1b|lab2a|lab2b|lab3|lab4a|lab4b>" >&2
    exit 1
    ;;
esac

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
# Chemins de Compose relatifs à la racine du dépôt : un chemin absolu avec des espaces serait coupé en plusieurs arguments.
cd "$REPO_ROOT"

if [ ! -f "$REPO_ROOT/.env" ]; then
  python3 "$SCRIPT_DIR/check.py"
fi

set -a
. "$REPO_ROOT/.env"
set +a

echo "=== Démarrage de l'état d'exécution pour $LAB ==="

warn_remaining_todo() {
  marker="$1"
  file="$2"
  if [ -f "$REPO_ROOT/$file" ] && grep -q "$marker" "$REPO_ROOT/$file" 2>/dev/null; then
    echo "[AVERTISSEMENT] $file contient encore des marqueurs $marker." >&2
  fi
}

case "$LAB" in
  lab2b)
    warn_remaining_todo "TODO(lab-1b)" "config/prometheus/rules.yml"
    warn_remaining_todo "TODO(lab-2a)" "config/alloy/config.alloy"
    ;;
  lab3|lab4a|lab4b)
    warn_remaining_todo "TODO(lab-1b)" "config/prometheus/rules.yml"
    warn_remaining_todo "TODO(lab-2a)" "config/alloy/config.alloy"
    warn_remaining_todo "TODO(lab-2b)" "config/prometheus/rules.yml"
    ;;
esac

if [ "$LAB" = "lab4a" ]; then
  echo "=== Préparation du volume TSDB de Prometheus (prom-seed, rétention 24h) ==="
  docker compose -f "$REPO_ROOT/compose/docker-compose.yml" -f "$REPO_ROOT/compose/lab4a.yml" rm -sf prometheus prom-seed >/dev/null 2>&1 || true
  docker volume rm -f orion_orion-promdata >/dev/null 2>&1 || true
  docker volume create --label com.docker.compose.project=orion --label com.docker.compose.volume=orion-promdata orion_orion-promdata >/dev/null 2>&1
  docker run --rm -v orion_orion-promdata:/prometheus \
    pgvector/pgvector:0.8.7-pg17-bookworm \
    sh -c "chown -R 65534:65534 /prometheus" >/dev/null 2>&1 || true
  SEED_COMPOSE="-f compose/docker-compose.yml -f compose/lab4a.yml"
  if [ -n "${EXTRA_COMPOSE_FILE:-}" ]; then
    SEED_COMPOSE="$SEED_COMPOSE -f $EXTRA_COMPOSE_FILE"
  fi
  # shellcheck disable=SC2086
  docker compose --env-file "$REPO_ROOT/.env" $SEED_COMPOSE run --rm --no-deps prom-seed
  sh "$SCRIPT_DIR/up.sh"
else
  sh "$SCRIPT_DIR/up.sh"
fi

curl -fsS -X POST http://127.0.0.1:9090/-/reload >/dev/null 2>&1 || true

COMPOSE_ARGS="-f compose/docker-compose.yml"
if [ "${LOW_MEM:-0}" = "1" ]; then
  COMPOSE_ARGS="$COMPOSE_ARGS -f compose/low-mem.yml"
fi
if [ -n "${EXTRA_COMPOSE_FILE:-}" ]; then
  COMPOSE_ARGS="$COMPOSE_ARGS -f $EXTRA_COMPOSE_FILE"
fi

for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
  TOOLS_CID="$(docker ps -q --filter "name=^/orion-tools-1$" --filter "status=running" | head -n 1)"
  if [ -z "$TOOLS_CID" ]; then
    TOOLS_CID="$(docker ps -q --filter "name=tools" --filter "status=running" | head -n 1)"
  fi
  if [ -n "$TOOLS_CID" ]; then
    if docker exec -i "$TOOLS_CID" orion-tools start-lab "$LAB"; then
      break
    fi
  fi
  docker compose --env-file "$REPO_ROOT/.env" $COMPOSE_ARGS up -d tools >/dev/null 2>&1 || true
  if [ "$attempt" -lt 12 ]; then
    echo ">>> [start-lab.sh] En attente du conteneur tools pour start-lab $LAB (tentative $attempt/12)..." >&2
    sleep 3
  else
    echo ">>> [start-lab.sh] Impossible d'exécuter orion-tools start-lab $LAB dans tools" >&2
    exit 1
  fi
done

echo "Environnement $LAB prêt."
