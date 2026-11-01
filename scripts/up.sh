#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
# Chemins de Compose relatifs à la racine du dépôt : un chemin absolu avec des espaces serait coupé en plusieurs arguments.
cd "$REPO_ROOT"

sh "$SCRIPT_DIR/gen-certs.sh"

mkdir -p "$REPO_ROOT/span-metier" "$REPO_ROOT/rca" "$REPO_ROOT/exports/rca" "$REPO_ROOT/.orion-state"
# Sous Linux et WSL2, tools tourne sous l'UID 10001 : il doit pouvoir écrire dans ces dossiers montés depuis l'hôte.
chmod 0777 "$REPO_ROOT/span-metier" "$REPO_ROOT/rca" "$REPO_ROOT/exports/rca" "$REPO_ROOT/.orion-state" 2>/dev/null || true
chmod 0666 "$REPO_ROOT/.orion-state/"* 2>/dev/null || true

if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  . "$REPO_ROOT/.env"
  set +a
fi

LOW_MEM="${LOW_MEM:-0}"
COMPOSE_ARGS="-f compose/docker-compose.yml"

if [ "${ORION_USE_LINUX_COMPOSE:-0}" = "1" ]; then
  COMPOSE_ARGS="$COMPOSE_ARGS -f compose/linux.yml"
fi

if [ "$LOW_MEM" = "1" ]; then
  COMPOSE_ARGS="$COMPOSE_ARGS -f compose/low-mem.yml"
fi

if [ -n "${EXTRA_COMPOSE_FILE:-}" ]; then
  COMPOSE_ARGS="$COMPOSE_ARGS -f $EXTRA_COMPOSE_FILE"
fi

# Initialisation du volume de configuration dynamique s'il est vide
docker volume create --label com.docker.compose.project=orion --label com.docker.compose.volume=orion-flags orion_orion-flags >/dev/null 2>&1 || true
docker run --rm -v orion_orion-flags:/data \
  pgvector/pgvector:0.8.7-pg17-bookworm \
  sh -c '[ -s /data/flags.json ] || printf "{\"flags\":{}}\n" > /data/flags.json; chmod 0777 /data && chmod 0666 /data/flags.json' >/dev/null 2>&1 || true

# Nettoyage d'un éventuel verrou postmaster.pid résiduel si postgres-db est arrêté
if docker volume inspect orion_orion-pgdata >/dev/null 2>&1 && ! docker ps --format '{{.Names}}' | grep -q "postgres-db"; then
  docker run --rm -v orion_orion-pgdata:/data \
    pgvector/pgvector:0.8.7-pg17-bookworm \
    rm -f /data/postmaster.pid >/dev/null 2>&1 || true
fi

# shellcheck disable=SC2086
UP_OK=0
for attempt in 1 2 3 4; do
  if docker compose --env-file "$REPO_ROOT/.env" $COMPOSE_ARGS up -d --remove-orphans "$@"; then
    UP_OK=1
    break
  fi
  if [ "$attempt" -lt 4 ]; then
    echo ">>> [up.sh] docker compose up a échoué (attente du démon), nouvelle tentative ($attempt/3) dans 5s..." >&2
    sleep 5
  fi
done

CHECK_OK=0
if python3 "$SCRIPT_DIR/check-interfaces.py"; then
  CHECK_OK=1
fi

if [ "$UP_OK" -ne 1 ] || [ "$CHECK_OK" -ne 1 ]; then
  exit 1
fi

